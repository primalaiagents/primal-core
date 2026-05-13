"""Version pin — guards against accidental version bumps in scaffolding."""

from __future__ import annotations


def test_version() -> None:
    """``primal_ai.__version__`` is the pre-alpha 0.0.1 scaffolding marker."""
    from primal_ai import __version__

    assert __version__ == "0.0.1"
