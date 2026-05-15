"""Version pin — guards against accidental version bumps."""

from __future__ import annotations


def test_version() -> None:
    """``primal_ai.__version__`` matches the published 0.2.0 release."""
    from primal_ai import __version__

    assert __version__ == "0.2.0"
