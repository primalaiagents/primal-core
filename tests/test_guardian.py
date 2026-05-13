"""Guardian MVP — policy enforcement, built-ins, combinators, DSL, dry-run, async.

These tests are the contract for the Phase 1 Guardian: a stdlib-only runtime
policy layer that wraps any callable agent with pre/post-execution checks.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────
# Core wrap behavior
# ──────────────────────────────────────────────────────────────────────────


def test_wrap_with_no_policies_is_passthrough() -> None:
    """``Guardian.wrap(agent)`` with no policies returns a callable that calls the agent."""
    from primal_ai import Guardian

    def agent(x: int) -> int:
        return x * 2

    wrapped = Guardian.wrap(agent)
    assert callable(wrapped)
    assert wrapped(21) == 42


def test_wrapped_callable_returns_agents_result() -> None:
    """Wrapped agent returns the underlying agent's result unchanged when no policy fires."""
    from primal_ai import AllowList, Guardian

    def agent(name: str) -> dict[str, str]:
        return {"hello": name}

    wrapped = Guardian.wrap(agent, policies=[AllowList()])  # empty allowlist = no checks
    assert wrapped("primal") == {"hello": "primal"}


def test_pre_policy_violation_propagates() -> None:
    """A pre-policy that raises ``PolicyViolation`` aborts the call."""
    from primal_ai import Guardian, Policy, PolicyViolation

    class RejectAll:
        name = "reject_all"

        def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            raise PolicyViolation(
                policy_name=self.name,
                reason="nope",
                phase="pre",
                context={},
            )

    policy: Policy = RejectAll()

    def agent() -> str:
        return "should not run"

    wrapped = Guardian.wrap(agent, policies=[policy])
    with pytest.raises(PolicyViolation) as exc:
        wrapped()
    assert exc.value.phase == "pre"
    assert exc.value.policy_name == "reject_all"


def test_post_policy_violation_propagates_with_phase_post() -> None:
    """A post-policy that raises ``PolicyViolation`` flags ``phase='post'``."""
    from primal_ai import Guardian, PolicyViolation

    class RejectResult:
        name = "reject_result"

        def check_post(
            self,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
            result: Any,
        ) -> None:
            raise PolicyViolation(
                policy_name=self.name,
                reason="bad result",
                phase="post",
                context={"result": result},
            )

    def agent() -> int:
        return 7

    wrapped = Guardian.wrap(agent, policies=[RejectResult()])
    with pytest.raises(PolicyViolation) as exc:
        wrapped()
    assert exc.value.phase == "post"
    assert exc.value.context["result"] == 7


def test_multiple_policies_execute_in_declared_order() -> None:
    """Pre-checks fire in order, then the agent runs, then post-checks fire in order."""
    from primal_ai import Guardian

    trace: list[str] = []

    class TraceA:
        name = "a"

        def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            trace.append("pre-a")

        def check_post(
            self, args: tuple[Any, ...], kwargs: dict[str, Any], result: Any
        ) -> None:
            trace.append("post-a")

    class TraceB:
        name = "b"

        def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            trace.append("pre-b")

        def check_post(
            self, args: tuple[Any, ...], kwargs: dict[str, Any], result: Any
        ) -> None:
            trace.append("post-b")

    def agent() -> str:
        trace.append("agent")
        return "ok"

    wrapped = Guardian.wrap(agent, policies=[TraceA(), TraceB()])
    wrapped()
    assert trace == ["pre-a", "pre-b", "agent", "post-a", "post-b"]


# ──────────────────────────────────────────────────────────────────────────
# String DSL
# ──────────────────────────────────────────────────────────────────────────


def test_dsl_parses_rate_limit_per_minute() -> None:
    """``"rate_limit:per_minute=60"`` parses into a ``RateLimit`` policy."""
    from primal_ai import RateLimit
    from primal_ai.guardian import parse_policy

    policy = parse_policy("rate_limit:per_minute=60")
    assert isinstance(policy, RateLimit)
    assert policy.per_minute == 60


def test_dsl_parses_max_cost_currency_form() -> None:
    """``"max_cost:$0.10/req"`` parses (README compatibility)."""
    from primal_ai import DollarCap
    from primal_ai.guardian import parse_policy

    policy = parse_policy("max_cost:$0.10/req")
    assert isinstance(policy, DollarCap)
    assert policy.max_per_call == pytest.approx(0.10)


def test_dsl_unknown_name_raises_listing_registered_names() -> None:
    """Unknown policy names raise ``ValueError`` listing the registered ones."""
    from primal_ai.guardian import parse_policy

    with pytest.raises(ValueError) as exc:
        parse_policy("not_a_real_policy")
    msg = str(exc.value)
    assert "not_a_real_policy" in msg
    assert "rate_limit" in msg  # the message lists what IS registered


def test_readme_quickstart_dsl_runs_against_a_fake_agent() -> None:
    """The README quick-start DSL strings parse and run end-to-end against a fake agent."""
    from primal_ai import Guardian

    def fake_agent(query: str) -> str:
        return f"results for {query}"

    wrapped = Guardian.wrap(
        fake_agent,
        policies=["no_external_network", "max_cost:$0.10/req"],
    )
    assert wrapped("Find me a flight to Tokyo under $800") == (
        "results for Find me a flight to Tokyo under $800"
    )


# ──────────────────────────────────────────────────────────────────────────
# Built-in policies
# ──────────────────────────────────────────────────────────────────────────


def test_rate_limit_blocks_after_threshold() -> None:
    """``RateLimit(per_minute=N)`` blocks the (N+1)th call inside one window."""
    from primal_ai import Guardian, PolicyViolation, RateLimit

    def agent() -> int:
        return 1

    # Tiny per-second budget so the test is fast and deterministic.
    wrapped = Guardian.wrap(agent, policies=[RateLimit(per_second=3)])
    for _ in range(3):
        assert wrapped() == 1
    with pytest.raises(PolicyViolation):
        wrapped()


def test_dollar_cap_blocks_when_cost_exceeds() -> None:
    """``DollarCap(max_per_call=X)`` raises when the result's cost exceeds X."""
    from primal_ai import DollarCap, Guardian, PolicyViolation

    def agent() -> dict[str, float]:
        return {"cost": 0.50, "answer": 1.0}

    wrapped = Guardian.wrap(agent, policies=[DollarCap(max_per_call=0.10)])
    with pytest.raises(PolicyViolation) as exc:
        wrapped()
    assert exc.value.phase == "post"


def test_dollar_cap_warns_once_when_result_lacks_cost(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the result has no ``cost`` field, ``DollarCap`` warns once and no-ops."""
    from primal_ai import DollarCap, Guardian

    def agent() -> dict[str, str]:
        return {"answer": "no cost info"}

    wrapped = Guardian.wrap(agent, policies=[DollarCap(max_per_call=0.10)])
    with caplog.at_level(logging.WARNING, logger="primal_ai.guardian"):
        for _ in range(5):
            wrapped()  # must not raise
    # Exactly one WARNING in total, not one per call.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


def test_allow_list_permits_kwargs_in_the_list() -> None:
    """``AllowList(tools=[...])`` permits a kwarg whose tool name is allowed."""
    from primal_ai import AllowList, Guardian

    def agent(*, tool: str) -> str:
        return f"used {tool}"

    wrapped = Guardian.wrap(agent, policies=[AllowList(tools=["search", "calc"])])
    assert wrapped(tool="search") == "used search"


def test_allow_list_blocks_kwargs_not_in_the_list() -> None:
    """``AllowList(tools=[...])`` blocks a kwarg whose tool name is NOT in the list."""
    from primal_ai import AllowList, Guardian, PolicyViolation

    def agent(*, tool: str) -> str:
        return f"used {tool}"

    wrapped = Guardian.wrap(agent, policies=[AllowList(tools=["search"])])
    with pytest.raises(PolicyViolation):
        wrapped(tool="shell")


def test_block_list_blocks_matched_pattern() -> None:
    """``BlockList(patterns=[...])`` blocks a call whose stringified args match."""
    from primal_ai import BlockList, Guardian, PolicyViolation

    def agent(url: str) -> str:
        return url

    wrapped = Guardian.wrap(agent, policies=[BlockList(patterns=[r"evil\.com"])])
    assert wrapped("https://safe.com") == "https://safe.com"
    with pytest.raises(PolicyViolation):
        wrapped("https://evil.com/x")


def test_schema_validator_validates_post_schema() -> None:
    """``SchemaValidator(post_schema=...)`` accepts a result matching the schema."""
    from primal_ai import Guardian, SchemaValidator

    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }

    def agent() -> dict[str, str]:
        return {"answer": "42"}

    wrapped = Guardian.wrap(agent, policies=[SchemaValidator(post_schema=schema)])
    assert wrapped() == {"answer": "42"}


def test_schema_validator_raises_with_useful_reason() -> None:
    """``SchemaValidator`` rejection reason references the offending field."""
    from primal_ai import Guardian, PolicyViolation, SchemaValidator

    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }

    def agent() -> dict[str, int]:
        return {"answer": 42}  # wrong type

    wrapped = Guardian.wrap(agent, policies=[SchemaValidator(post_schema=schema)])
    with pytest.raises(PolicyViolation) as exc:
        wrapped()
    assert "answer" in exc.value.reason


def test_pii_redact_redacts_email_from_string_result() -> None:
    """``PIIRedact`` defaults strip emails out of string results."""
    from primal_ai import Guardian, PIIRedact

    def agent() -> str:
        return "Contact me at alice@example.com please."

    wrapped = Guardian.wrap(agent, policies=[PIIRedact()])
    result = wrapped()
    assert "alice@example.com" not in result
    assert "Contact me" in result  # surrounding text preserved


def test_pii_redact_redacts_configured_fields_from_dict() -> None:
    """``PIIRedact(fields=[...])`` strips named fields from dict results."""
    from primal_ai import Guardian, PIIRedact

    def agent() -> dict[str, str]:
        return {"name": "Alice", "ssn": "123-45-6789"}

    wrapped = Guardian.wrap(agent, policies=[PIIRedact(fields=["ssn"])])
    result = wrapped()
    assert result["name"] == "Alice"
    assert result["ssn"] != "123-45-6789"


# ──────────────────────────────────────────────────────────────────────────
# Combinators
# ──────────────────────────────────────────────────────────────────────────


def test_all_of_short_circuits_on_first_violation() -> None:
    """``AllOf`` stops at the first sub-policy that raises and never runs later ones."""
    from primal_ai import AllOf, Guardian, PolicyViolation

    calls: list[str] = []

    class A:
        name = "a"

        def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            calls.append("a")
            raise PolicyViolation(
                policy_name="a", reason="boom", phase="pre", context={}
            )

    class B:
        name = "b"

        def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            calls.append("b")

    def agent() -> None:
        return None

    wrapped = Guardian.wrap(agent, policies=[AllOf(A(), B())])
    with pytest.raises(PolicyViolation):
        wrapped()
    assert calls == ["a"]


def test_any_of_passes_if_any_sub_policy_passes() -> None:
    """``AnyOf`` is satisfied as soon as one sub-policy accepts the call."""
    from primal_ai import AnyOf, Guardian, PolicyViolation

    class AlwaysFail:
        name = "fail"

        def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            raise PolicyViolation(
                policy_name="fail", reason="x", phase="pre", context={}
            )

    class AlwaysPass:
        name = "pass"

        def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            return None

    def agent() -> str:
        return "ok"

    wrapped = Guardian.wrap(agent, policies=[AnyOf(AlwaysFail(), AlwaysPass())])
    assert wrapped() == "ok"


# ──────────────────────────────────────────────────────────────────────────
# Dry-run mode
# ──────────────────────────────────────────────────────────────────────────


def test_dry_run_records_violations_without_raising() -> None:
    """Under ``Guardian.dry_run``, violations are captured instead of raised."""
    from primal_ai import Guardian, PolicyViolation

    class Rejector:
        name = "rejector"

        def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            raise PolicyViolation(
                policy_name=self.name, reason="x", phase="pre", context={}
            )

    def agent() -> str:
        return "still ran"

    wrapped = Guardian.wrap(agent, policies=[Rejector()])
    with Guardian.dry_run():
        wrapped()
        violations = Guardian.get_dry_run_violations()
    assert len(violations) == 1
    assert violations[0].policy_name == "rejector"


def test_dry_run_returns_agents_real_result() -> None:
    """Under ``Guardian.dry_run``, the agent's real result still flows through."""
    from primal_ai import Guardian, PolicyViolation

    class Rejector:
        name = "rejector"

        def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            raise PolicyViolation(
                policy_name=self.name, reason="x", phase="pre", context={}
            )

    def agent() -> str:
        return "still ran"

    wrapped = Guardian.wrap(agent, policies=[Rejector()])
    with Guardian.dry_run():
        result = wrapped()
    assert result == "still ran"


# ──────────────────────────────────────────────────────────────────────────
# Escalation
# ──────────────────────────────────────────────────────────────────────────


def test_escalate_invokes_custom_handler() -> None:
    """A handler registered via ``set_escalation_handler`` receives violations."""
    from primal_ai import Guardian, PolicyViolation

    seen: list[Any] = []

    def handler(item: Any) -> None:
        seen.append(item)

    Guardian.set_escalation_handler(handler)
    try:
        v = PolicyViolation(policy_name="x", reason="r", phase="pre", context={})
        Guardian.escalate(v)
        assert seen == [v]
    finally:
        Guardian.set_escalation_handler(None)  # restore default


def test_escalate_defaults_to_stderr_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With no custom handler, ``Guardian.escalate`` logs to the primal_ai.guardian logger."""
    from primal_ai import Guardian, PolicyViolation

    Guardian.set_escalation_handler(None)  # ensure default
    v = PolicyViolation(policy_name="x", reason="r", phase="pre", context={})
    with caplog.at_level(logging.WARNING, logger="primal_ai.guardian"):
        Guardian.escalate(v)
    assert any("x" in r.getMessage() for r in caplog.records)


# ──────────────────────────────────────────────────────────────────────────
# Async support
# ──────────────────────────────────────────────────────────────────────────


def test_wrap_auto_detects_async_agent_and_runs_policies() -> None:
    """``Guardian.wrap`` returns an awaitable wrapper when given a coroutine function."""
    from primal_ai import Guardian

    calls: list[str] = []

    class Tracer:
        name = "tracer"

        def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            calls.append("pre")

        def check_post(
            self, args: tuple[Any, ...], kwargs: dict[str, Any], result: Any
        ) -> None:
            calls.append(f"post:{result}")

    async def agent(x: int) -> int:
        return x + 1

    wrapped = Guardian.wrap(agent, policies=[Tracer()])
    result = asyncio.run(wrapped(4))
    assert result == 5
    assert calls == ["pre", "post:5"]


def test_async_policy_violation_propagates_from_awaited_result() -> None:
    """An async wrapped call still raises ``PolicyViolation`` from post checks."""
    from primal_ai import Guardian, PolicyViolation

    class RejectResult:
        name = "reject_result"

        def check_post(
            self, args: tuple[Any, ...], kwargs: dict[str, Any], result: Any
        ) -> None:
            raise PolicyViolation(
                policy_name=self.name, reason="bad", phase="post", context={}
            )

    async def agent() -> int:
        return 1

    wrapped = Guardian.wrap_async(agent, policies=[RejectResult()])
    with pytest.raises(PolicyViolation):
        asyncio.run(wrapped())


# ──────────────────────────────────────────────────────────────────────────
# PolicyViolation serialization
# ──────────────────────────────────────────────────────────────────────────


def test_policy_violation_to_dict_is_json_serializable() -> None:
    """``PolicyViolation.to_dict`` round-trips through ``json.dumps``."""
    from primal_ai import PolicyViolation

    v = PolicyViolation(
        policy_name="rate_limit",
        reason="too many requests",
        phase="pre",
        context={"per_minute": 60, "seen": 61},
    )
    raw = json.dumps(v.to_dict())
    payload = json.loads(raw)
    assert payload["policy_name"] == "rate_limit"
    assert payload["phase"] == "pre"
    assert payload["context"]["seen"] == 61
