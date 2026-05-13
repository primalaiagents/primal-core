"""Smoke test — every PRIMAL pillar imports cleanly from the top-level package."""

from __future__ import annotations


def test_seven_pillars_import() -> None:
    """All seven pillars are importable from ``primal_ai``."""
    from primal_ai import (
        Atlas,
        Conductor,
        Continuity,
        Guardian,
        Harness,
        Trajectory,
        Verifier,
    )

    pillars = [Guardian, Conductor, Trajectory, Continuity, Verifier, Atlas, Harness]
    assert all(p is not None for p in pillars)
    assert len(pillars) == 7
