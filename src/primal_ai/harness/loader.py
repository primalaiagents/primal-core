"""Tool registration helpers — module-level shortcuts forwarding to the Harness singleton.

Kept thin on purpose. The real registry lives at ``Harness.tools``; these
helpers exist so users can ``from primal_ai import register_tool`` without
naming the facade.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from primal_ai.harness.discovery import ToolInfo
    from primal_ai.storage import Storage


def register_tool(tool: ToolInfo, *, store: Storage | None = None) -> None:
    """Module-level shortcut for ``Harness.register_tool``."""
    from primal_ai.harness._core import Harness

    Harness.register_tool(tool, store=store)


def unregister_tool(name: str, *, store: Storage | None = None) -> None:
    """Module-level shortcut for ``Harness.unregister_tool``."""
    from primal_ai.harness._core import Harness

    Harness.unregister_tool(name, store=store)


__all__ = ["register_tool", "unregister_tool"]
