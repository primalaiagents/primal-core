"""Atlas bandit selectors — Thompson sampling + UCB1, contextual partitioning.

The bandit layer is an **opt-in upgrade** over the deterministic router
(Session 7). Atlas continues to pick the first healthy candidate by
declared order unless a selector is installed via ``Atlas.set_selector``
or supplied per call as ``context={"selector": "thompson"}``.

Two algorithms ship in MVP, both stdlib-only:

  - :class:`ThompsonBandit` — Beta-Bernoulli posterior; samples
    ``Beta(successes + 1, failures + 1)`` per arm and picks the maximum.
    Uses :func:`random.betavariate` — no NumPy required.
  - :class:`UCB1Bandit` — classic upper-confidence-bound score
    ``mean_reward + c * sqrt(ln(total_pulls) / arm_pulls)``. Untried arms
    score ``+inf`` so every option is explored at least once.

Both bandits support **contextual partitioning** — an outcome carries an
optional ``context_key`` string, and posterior state is kept per
``(provider_name, context_key)`` pair. Atlas reads
``context.get("bandit_context_key", "")`` to choose the partition.

State is JSON-serializable via the shared ``Storage`` Protocol —
``bandit.save(store)`` / ``bandit.load(store)`` round-trip through any
backend. No auto-save (too chatty); the caller decides when.
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from primal_ai.storage import Storage

# ──────────────────────────────────────────────────────────────────────────
# BanditOutcome + ArmState
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BanditOutcome:
    """One feedback signal: the result of a single provider invocation.

    Thompson uses ``success`` (Bernoulli); UCB1 uses ``reward`` (continuous
    in ``[0.0, 1.0]``). ``cost`` and ``latency_ms`` are recorded for
    Phase-2 cost-aware extensions but are not used by the MVP scoring.

    Args:
        provider_name: Name of the provider this outcome belongs to.
        success: Binary success flag. Defaults: ``reward >= 0.5`` derives
            ``success`` when callers populate only ``reward``.
        reward: Continuous reward, typically ``1.0`` for success and
            ``0.0`` for failure.
        cost: Optional per-call dollar cost.
        latency_ms: Optional wall-clock latency.
        context_key: Partition key for contextual bandits. ``""`` for
            non-contextual use.
        timestamp: ``time.time()`` at recording.
    """

    provider_name: str
    success: bool
    reward: float = 0.0
    cost: float | None = None
    latency_ms: float | None = None
    context_key: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "provider_name": self.provider_name,
            "success": self.success,
            "reward": self.reward,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "context_key": self.context_key,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BanditOutcome:
        """Rebuild a ``BanditOutcome`` from a ``to_dict`` payload."""
        return cls(
            provider_name=str(payload["provider_name"]),
            success=bool(payload.get("success", False)),
            reward=float(payload.get("reward") or 0.0),
            cost=payload.get("cost"),
            latency_ms=payload.get("latency_ms"),
            context_key=str(payload.get("context_key") or ""),
            timestamp=float(payload.get("timestamp") or time.time()),
        )


@dataclass
class ArmState:
    """Per-(provider, context_key) state. Mutable; updated under a bandit lock.

    Thompson fields: ``successes`` and ``failures`` (Beta(successes+1,
    failures+1) is the posterior).

    UCB1 fields: ``total_reward`` and ``pulls`` (mean = total_reward / pulls).
    """

    provider_name: str
    context_key: str = ""
    successes: int = 0
    failures: int = 0
    total_reward: float = 0.0
    pulls: int = 0
    last_updated: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "provider_name": self.provider_name,
            "context_key": self.context_key,
            "successes": self.successes,
            "failures": self.failures,
            "total_reward": self.total_reward,
            "pulls": self.pulls,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ArmState:
        """Rebuild an ``ArmState`` from a ``to_dict`` payload."""
        return cls(
            provider_name=str(payload["provider_name"]),
            context_key=str(payload.get("context_key") or ""),
            successes=int(payload.get("successes") or 0),
            failures=int(payload.get("failures") or 0),
            total_reward=float(payload.get("total_reward") or 0.0),
            pulls=int(payload.get("pulls") or 0),
            last_updated=float(payload.get("last_updated") or 0.0),
        )


# ──────────────────────────────────────────────────────────────────────────
# Bandit Protocol
# ──────────────────────────────────────────────────────────────────────────


@runtime_checkable
class Bandit(Protocol):
    """Structural contract for any bandit-driven selector.

    Required:
        name (str): Stable identifier surfaced in
            ``RoutingDecision.selector_name``.
        select(candidates, context) -> str | None
        update(outcome) -> None
        state_for(provider_name, context_key="") -> ArmState | None
        save(store) -> None
        load(store) -> None

    Concrete classes (``ThompsonBandit`` / ``UCB1Bandit``) also expose
    ``select_with_metadata`` — Atlas calls it when present to record per-arm
    scores into the ROUTING_DECISION step. Custom implementations of just
    ``select`` work too; the trajectory simply omits the score metadata.
    """

    name: str

    def select(self, candidates: list[str], context: dict[str, Any] | None = None) -> str | None:
        """Pick a provider name from ``candidates``, or return ``None`` if empty."""
        ...

    def update(self, outcome: BanditOutcome) -> None:
        """Feed an outcome back into the posteriors."""
        ...

    def state_for(self, provider_name: str, context_key: str = "") -> ArmState | None:
        """Return the current state for a (provider, context_key) pair."""
        ...

    def save(self, store: Storage) -> None:
        """Persist all arm state through the ``Storage`` Protocol."""
        ...

    def load(self, store: Storage) -> None:
        """Restore previously-persisted arm state."""
        ...


# ──────────────────────────────────────────────────────────────────────────
# Shared bandit base
# ──────────────────────────────────────────────────────────────────────────


class _BanditBase:
    """Shared plumbing: arm storage, locking, persistence, context-key extraction."""

    name: str = "_base"

    def __init__(self) -> None:
        # Nested dict: provider_name → context_key → ArmState.
        self._arms: dict[str, dict[str, ArmState]] = {}
        self._lock = threading.Lock()

    # ── State accessors ────────────────────────────────────────────────

    def state_for(self, provider_name: str, context_key: str = "") -> ArmState | None:
        """Return the existing state for ``(provider_name, context_key)``, or ``None``."""
        with self._lock:
            return self._arms.get(provider_name, {}).get(context_key)

    def _ensure_arm(self, provider_name: str, context_key: str) -> ArmState:
        """Return (creating if needed) the ``ArmState`` for ``(provider_name, context_key)``.

        Caller must hold ``self._lock``.
        """
        by_ctx = self._arms.setdefault(provider_name, {})
        if context_key not in by_ctx:
            by_ctx[context_key] = ArmState(
                provider_name=provider_name,
                context_key=context_key,
            )
        return by_ctx[context_key]

    @staticmethod
    def _context_key(context: dict[str, Any] | None) -> str:
        """Extract the bandit context key from a routing context dict."""
        if not context:
            return ""
        key = context.get("bandit_context_key")
        return "" if key is None else str(key)

    # ── Persistence ────────────────────────────────────────────────────

    def _storage_key(self) -> str:
        return f"atlas:bandit:{self.name}"

    def save(self, store: Storage) -> None:
        """Persist every arm's state under the bandit's storage key."""
        with self._lock:
            snapshot = {
                provider: {ctx: state.to_dict() for ctx, state in by_ctx.items()}
                for provider, by_ctx in self._arms.items()
            }
        store.put(
            self._storage_key(),
            {
                "bandit_name": self.name,
                "algorithm": type(self).__name__,
                "saved_at": time.time(),
                "arms": snapshot,
            },
        )

    def load(self, store: Storage) -> None:
        """Restore arms from ``store``. No-op if the bandit hasn't been saved yet."""
        payload = store.get(self._storage_key())
        if payload is None:
            return
        arms_raw = payload.get("arms") or {}
        with self._lock:
            self._arms = {}
            for provider, by_ctx_raw in arms_raw.items():
                self._arms[provider] = {
                    ctx: ArmState.from_dict(state) for ctx, state in by_ctx_raw.items()
                }


# ──────────────────────────────────────────────────────────────────────────
# ThompsonBandit
# ──────────────────────────────────────────────────────────────────────────


class ThompsonBandit(_BanditBase):
    """Beta-Bernoulli Thompson sampling over providers.

    For each candidate, sample ``Beta(successes + 1, failures + 1)`` and
    pick the maximum sample. Naturally balances exploration/exploitation:
    arms with few observations have wide posteriors and occasionally win;
    arms with many successes have tight, high-mean posteriors.

    Args:
        name: Identifier surfaced in ``RoutingDecision.selector_name``.
            Also used as the storage key (``atlas:bandit:{name}``).
        seed: Optional RNG seed for deterministic tests.

    Example:
        >>> from primal_ai import (
        ...     Atlas, BanditOutcome, ThompsonBandit,
        ... )
        >>> from primal_ai.storage import InMemoryStorage
        >>> bandit = ThompsonBandit(seed=1)
        >>> bandit.update(BanditOutcome(provider_name="a", success=True))
        >>> bandit.update(BanditOutcome(provider_name="b", success=False))
        >>> # bandit.select(["a", "b"]) tends toward "a"
        >>> store = InMemoryStorage()
        >>> bandit.save(store)
        >>> fresh = ThompsonBandit()
        >>> fresh.load(store)
    """

    name = "thompson"

    def __init__(self, name: str = "thompson", seed: int | None = None) -> None:
        super().__init__()
        self.name = name
        self._rng = random.Random(seed)

    # ── Selection ──────────────────────────────────────────────────────

    def select(self, candidates: list[str], context: dict[str, Any] | None = None) -> str | None:
        """Sample from each candidate's Beta posterior; return the argmax (or ``None`` if empty)."""
        chosen, _, _ = self.select_with_metadata(candidates, context)
        return chosen

    def select_with_metadata(
        self,
        candidates: list[str],
        context: dict[str, Any] | None = None,
    ) -> tuple[str | None, dict[str, float], float | None]:
        """Pick + return ``(chosen, per_arm_samples, posterior_std_for_chosen)``."""
        if not candidates:
            return None, {}, None
        context_key = self._context_key(context)
        scores: dict[str, float] = {}
        with self._lock:
            for name in candidates:
                state = self._ensure_arm(name, context_key)
                alpha = state.successes + 1.0
                beta = state.failures + 1.0
                scores[name] = self._rng.betavariate(alpha, beta)
            chosen = max(scores, key=lambda k: scores[k])
            chosen_state = self._arms[chosen][context_key]
            alpha_c = chosen_state.successes + 1.0
            beta_c = chosen_state.failures + 1.0
        # Beta(α, β) variance = αβ / ((α+β)^2 (α+β+1)). std = sqrt(variance).
        denom = ((alpha_c + beta_c) ** 2) * (alpha_c + beta_c + 1.0)
        std = math.sqrt((alpha_c * beta_c) / denom) if denom > 0 else None
        return chosen, scores, std

    # ── Update ─────────────────────────────────────────────────────────

    def update(self, outcome: BanditOutcome) -> None:
        """Increment ``successes`` or ``failures`` based on ``outcome.success``."""
        with self._lock:
            state = self._ensure_arm(outcome.provider_name, outcome.context_key)
            if outcome.success:
                state.successes += 1
            else:
                state.failures += 1
            state.last_updated = outcome.timestamp


# ──────────────────────────────────────────────────────────────────────────
# UCB1Bandit
# ──────────────────────────────────────────────────────────────────────────


class UCB1Bandit(_BanditBase):
    """Upper-Confidence-Bound 1 over providers.

    Score per arm: ``mean_reward + c * sqrt(ln(total_pulls) / arm_pulls)``.
    Untried arms (``pulls == 0``) score ``+inf`` so every option gets
    explored at least once before any is re-picked. Higher
    ``exploration_constant`` → more exploration; lower → more exploitation.

    Args:
        name: Identifier surfaced in ``RoutingDecision.selector_name``.
        exploration_constant: ``c`` in the UCB1 formula. Default ``2.0``.

    Example:
        >>> from primal_ai import BanditOutcome, UCB1Bandit
        >>> bandit = UCB1Bandit(exploration_constant=2.0)
        >>> bandit.update(BanditOutcome(provider_name="a", success=True, reward=0.9))
        >>> bandit.update(BanditOutcome(provider_name="b", success=True, reward=0.4))
        >>> # bandit.select(["a", "b"]) prefers "a" once both have pulls > 0
    """

    name = "ucb1"

    def __init__(self, name: str = "ucb1", exploration_constant: float = 2.0) -> None:
        super().__init__()
        self.name = name
        self.exploration_constant = exploration_constant

    # ── Selection ──────────────────────────────────────────────────────

    def select(self, candidates: list[str], context: dict[str, Any] | None = None) -> str | None:
        """Return the argmax UCB1 score, or ``None`` on an empty candidate list."""
        chosen, _, _ = self.select_with_metadata(candidates, context)
        return chosen

    def select_with_metadata(
        self,
        candidates: list[str],
        context: dict[str, Any] | None = None,
    ) -> tuple[str | None, dict[str, float], float | None]:
        """Pick + return ``(chosen, per_arm_scores, exploration_term_for_chosen)``."""
        if not candidates:
            return None, {}, None
        context_key = self._context_key(context)
        scores: dict[str, float] = {}
        exploration_terms: dict[str, float] = {}
        with self._lock:
            # Total pulls across THIS context_key only — keep partitions clean.
            total_pulls = sum(
                state.pulls
                for by_ctx in self._arms.values()
                for ctx_key, state in by_ctx.items()
                if ctx_key == context_key
            )
            for name in candidates:
                state = self._ensure_arm(name, context_key)
                if state.pulls == 0:
                    scores[name] = math.inf
                    exploration_terms[name] = math.inf
                else:
                    mean = state.total_reward / state.pulls
                    exploration = self.exploration_constant * math.sqrt(
                        math.log(max(total_pulls, 1)) / state.pulls,
                    )
                    scores[name] = mean + exploration
                    exploration_terms[name] = exploration
            chosen = max(scores, key=lambda k: scores[k])
        chosen_exp = exploration_terms[chosen]
        # Replace any +inf in scores with a JSON-friendly large finite number when
        # we emit per-arm scores; +inf doesn't survive ``json.dumps`` by default.
        finite_scores = {k: (v if math.isfinite(v) else math.inf) for k, v in scores.items()}
        return chosen, finite_scores, (chosen_exp if math.isfinite(chosen_exp) else None)

    # ── Update ─────────────────────────────────────────────────────────

    def update(self, outcome: BanditOutcome) -> None:
        """Accumulate reward and increment pull count for the relevant arm."""
        # UCB1 uses the continuous reward. If the caller only set ``success``,
        # treat True as 1.0 and False as 0.0 for backwards-friendliness.
        reward = outcome.reward
        if reward == 0.0 and outcome.success:
            reward = 1.0
        with self._lock:
            state = self._ensure_arm(outcome.provider_name, outcome.context_key)
            state.pulls += 1
            state.total_reward += reward
            # Also track successes/failures so the same ``ArmState`` shape
            # works for both algorithms (helpful for diagnostics + dashboards).
            if outcome.success:
                state.successes += 1
            else:
                state.failures += 1
            state.last_updated = outcome.timestamp


# ──────────────────────────────────────────────────────────────────────────
# Selector registry
# ──────────────────────────────────────────────────────────────────────────


SelectorFactory = Callable[[], Bandit]

_SELECTOR_REGISTRY: dict[str, SelectorFactory] = {}
_registry_lock = threading.Lock()


def register_selector(name: str, factory: SelectorFactory) -> None:
    """Register a name → factory mapping for ``Atlas.set_selector('name')``.

    The factory takes no arguments and returns a fresh ``Bandit`` instance.
    Registering twice with the same name replaces the prior entry.
    """
    with _registry_lock:
        _SELECTOR_REGISTRY[name] = factory


def registered_selectors() -> list[str]:
    """Return the sorted list of currently-registered selector names."""
    with _registry_lock:
        return sorted(_SELECTOR_REGISTRY)


def resolve_selector(name: str) -> Bandit:
    """Resolve a registry name into a fresh ``Bandit`` instance.

    Raises ``ValueError`` if the name isn't registered.
    """
    with _registry_lock:
        factory = _SELECTOR_REGISTRY.get(name)
    if factory is None:
        raise ValueError(
            f"unknown selector {name!r}; registered: {registered_selectors()}",
        )
    return factory()


def _safe_update(selector: Bandit | None, outcome: BanditOutcome) -> None:
    """Best-effort selector update — never raises into the calling code."""
    if selector is None:
        return
    with suppress(Exception):
        selector.update(outcome)


# Pre-register the built-in selectors so ``Atlas.set_selector("thompson"|"ucb1")``
# works out of the box.
register_selector("thompson", lambda: ThompsonBandit())
register_selector("ucb1", lambda: UCB1Bandit())


__all__ = [
    "ArmState",
    "Bandit",
    "BanditOutcome",
    "SelectorFactory",
    "ThompsonBandit",
    "UCB1Bandit",
    "register_selector",
    "registered_selectors",
    "resolve_selector",
]
