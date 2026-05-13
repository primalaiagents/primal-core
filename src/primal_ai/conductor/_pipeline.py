"""``Pipeline`` + ``PipelineStep`` — declarative linear multi-agent flows.

MVP scope: linear pipelines only. Each step delegates to one agent; the
prior step's output (optionally transformed) becomes the next step's
input. Halts on the first failed step. Records lifecycle events on the
Conductor's bus.

Branching, parallel fan-out, and persistence are documented as Phase 2
work in CONDUCTOR_ROADMAP.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from primal_ai.conductor._core import Conductor
from primal_ai.conductor._delegation import DelegationStatus
from primal_ai.conductor._events import Event, EventKind


@dataclass(frozen=True)
class PipelineStep:
    """One step in a ``Pipeline``.

    Args:
        name: Step identifier, used as the key in the result dict.
        agent_name: Resolve the target via the default registry's name.
            Mutually exclusive with ``capability`` (if both are set,
            ``agent_name`` wins).
        capability: Resolve the target by capability instead. Either
            ``agent_name`` or ``capability`` must be provided.
        input_transform: Optional callable applied to the prior step's
            output before it becomes the next step's input. ``None``
            (the default) passes the prior output through unchanged.
        output_key: Reserved for Phase 2 multi-output graphs; currently
            ignored.
    """

    name: str
    agent_name: str | None = None
    capability: str | None = None
    input_transform: Callable[[Any], Any] | None = None
    output_key: str | None = None


class Pipeline:
    """Linear multi-agent pipeline.

    Example:
        >>> from primal_ai import Pipeline, PipelineStep
        >>> pipeline = Pipeline(
        ...     name="search-then-summarize",
        ...     steps=[
        ...         PipelineStep(name="search", capability="search"),
        ...         PipelineStep(name="summarize", capability="summarize"),
        ...     ],
        ... )
        >>> # pipeline.run({"query": "flights to tokyo"})
    """

    def __init__(self, name: str, steps: list[PipelineStep]) -> None:
        self.name = name
        self.steps: list[PipelineStep] = list(steps)

    def run(self, initial_input: Any) -> dict[str, Any]:
        """Execute every step in order. Halt on the first failed delegation.

        Returns:
            A dict with one entry per completed step plus the meta keys:
              - ``_final``  — the last successful step's output (or ``None``
                if the pipeline failed before any step succeeded).
              - ``_failed`` — only present on failure; names the offending
                step.
        """
        Conductor.event_bus.publish(
            Event(
                kind=EventKind.PIPELINE_STARTED.value,
                payload={"pipeline": self.name, "step_count": len(self.steps)},
            ),
        )

        outputs: dict[str, Any] = {}
        current_input: Any = initial_input
        for step in self.steps:
            target_input = (
                step.input_transform(current_input)
                if step.input_transform is not None
                else current_input
            )
            # Resolve the explicit agent (if any) up front so mypy can see
            # the list is ``list[Agent]`` rather than ``list[Agent | None]``.
            named_agent = (
                Conductor.get_agent(step.agent_name)
                if step.agent_name is not None
                else None
            )
            agents_arg = [named_agent] if named_agent is not None else None
            result = Conductor.delegate(
                task=f"pipeline:{self.name}/{step.name}",
                agents=agents_arg,
                capability=step.capability,
                input=target_input,
            )
            if result.status != DelegationStatus.SUCCESS:
                outputs["_failed"] = step.name
                outputs["_final"] = None
                Conductor.event_bus.publish(
                    Event(
                        kind=EventKind.PIPELINE_FAILED.value,
                        payload={
                            "pipeline": self.name,
                            "failed_step": step.name,
                            "result": result.to_dict(),
                        },
                    ),
                )
                return outputs

            outputs[step.name] = result.output
            current_input = result.output
            Conductor.event_bus.publish(
                Event(
                    kind=EventKind.PIPELINE_STEP_COMPLETED.value,
                    payload={"pipeline": self.name, "step": step.name},
                ),
            )

        outputs["_final"] = current_input
        Conductor.event_bus.publish(
            Event(
                kind=EventKind.PIPELINE_COMPLETED.value,
                payload={"pipeline": self.name, "final": current_input},
            ),
        )
        return outputs


__all__ = ["Pipeline", "PipelineStep"]
