"""Autolearn — derive ``ProfileField``s from text via a user-supplied LLM.

The MVP ships **no first-party LLM caller**. ``BYOAutolearn`` is the entire
LLM surface: pass any callable ``Callable[[str], str]`` and the rest is
pure string parsing. Same BYO boundary Verifier's ``BYOLLMJudge`` and
Atlas's ``BYOProvider`` already established.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from primal_ai.continuity.profile import ProfileField, UserProfile

_logger = logging.getLogger("primal_ai.continuity")

DEFAULT_AUTOLEARN_PROMPT = """\
You are extracting durable user preferences from a piece of text.

Output ONE fact per line as ``KEY: VALUE``. Use short snake_case keys.
Skip any fact you are not confident about. If you find nothing, output
nothing.

Current profile (for context):
{current_profile}

Text:
{text}
"""

# Default confidence applied to every field extracted by ``BYOAutolearn``.
# Below 1.0 so explicit user-set fields beat autolearn on the higher_confidence
# merge strategy. Above 0.5 so autolearn-derived facts can still displace
# old, low-confidence ones.
_DEFAULT_AUTOLEARN_CONFIDENCE = 0.7


@runtime_checkable
class Autolearn(Protocol):
    """Structural contract for any autolearn extractor.

    Required:
        name (str): Stable identifier surfaced in profile updates.
        extract(text, current_profile=None) -> list[ProfileField]
    """

    name: str

    def extract(
        self,
        text: str,
        current_profile: UserProfile | None = None,
    ) -> list[ProfileField]:
        """Return new ``ProfileField`` entries derived from ``text``."""
        ...


class BYOAutolearn:
    """Bring-your-own-LLM autolearn extractor.

    Same BYO pattern Verifier and Atlas use. ``call_llm`` is the entire
    extension point — supply your own SDK / HTTP client / local model;
    everything else is stdlib string parsing.

    Args:
        call_llm: ``Callable[[str], str]`` invoked with the formatted prompt.
        prompt_template: Template with ``{text}`` + ``{current_profile}``
            slots. Defaults to a sober extract-or-skip prompt.
        name: Identifier surfaced on every ``ProfileField`` ``source``.
        source_label: The ``ProfileField.source`` written into every
            extracted fact. Useful for distinguishing multiple autolearn
            backends in one profile.

    Example:
        >>> from primal_ai import BYOAutolearn
        >>> def my_llm(prompt):
        ...     return "language: ja\\ntimezone: Asia/Tokyo"
        >>> fields = BYOAutolearn(call_llm=my_llm).extract("user prefers japanese")
        >>> sorted(f.key for f in fields)
        ['language', 'timezone']
    """

    def __init__(
        self,
        call_llm: Callable[[str], str],
        prompt_template: str = DEFAULT_AUTOLEARN_PROMPT,
        name: str = "byo_autolearn",
        source_label: str = "autolearn:byo",
    ) -> None:
        self.call_llm = call_llm
        self.prompt_template = prompt_template
        self.name = name
        self.source_label = source_label

    def extract(
        self,
        text: str,
        current_profile: UserProfile | None = None,
    ) -> list[ProfileField]:
        """Format the prompt, invoke the user's LLM, parse the response into ``ProfileField``s."""
        if current_profile is None:
            profile_summary = "(empty)"
        else:
            keys = current_profile.keys()
            profile_summary = (
                ", ".join(f"{k}={current_profile.get(k)}" for k in keys) or "(empty)"
            )
        prompt = self.prompt_template.format(
            text=text,
            current_profile=profile_summary,
        )
        response = self.call_llm(prompt)
        return self._parse(response)

    def _parse(self, response: str) -> list[ProfileField]:
        """Parse a ``KEY: VALUE`` response into ``ProfileField`` instances.

        Lines that don't contain a colon-separator are silently ignored;
        a single WARNING is logged per ``extract`` call summarizing the
        skipped count.
        """
        now = time.time()
        out: list[ProfileField] = []
        skipped = 0
        for raw_line in response.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if ":" not in line:
                skipped += 1
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if not key:
                skipped += 1
                continue
            out.append(
                ProfileField(
                    key=key,
                    value=value,
                    confidence=_DEFAULT_AUTOLEARN_CONFIDENCE,
                    source=self.source_label,
                    updated_at=now,
                ),
            )
        if skipped:
            _logger.warning(
                "BYOAutolearn: skipped %d malformed line(s) (no 'KEY: VALUE' format)",
                skipped,
            )
        return out


# ──────────────────────────────────────────────────────────────────────────
# Autolearn registry
# ──────────────────────────────────────────────────────────────────────────


AutolearnFactory = Callable[[], Autolearn]

_AUTOLEARN_REGISTRY: dict[str, AutolearnFactory] = {}


def register_autolearn(name: str, factory: AutolearnFactory) -> None:
    """Register a name → factory mapping for autolearn lookup.

    The factory takes no arguments and returns a fresh ``Autolearn``.
    Registering twice replaces the prior entry.
    """
    _AUTOLEARN_REGISTRY[name] = factory


def _byo_zero_arg_factory() -> Autolearn:
    """Placeholder that explains why ``BYOAutolearn`` can't be auto-instantiated."""
    raise ValueError(
        "BYOAutolearn requires a call_llm callable; instantiate directly.",
    )


# Pre-register the BYO name so unknown-name errors carry a useful pointer.
register_autolearn("byo", _byo_zero_arg_factory)


__all__ = [
    "Autolearn",
    "AutolearnFactory",
    "BYOAutolearn",
    "DEFAULT_AUTOLEARN_PROMPT",
    "register_autolearn",
]
