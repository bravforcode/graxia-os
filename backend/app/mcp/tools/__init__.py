"""MCP tools — system, funnel, write (approval-gated), dangerous (blocked), workspace, and context."""
from __future__ import annotations

# Import all tool modules to trigger @mcp_registry.register decorators
import app.mcp.tools.system  # noqa: F401
import app.mcp.tools.funnel  # noqa: F401
import app.mcp.tools.write  # noqa: F401
import app.mcp.tools.dangerous  # noqa: F401
import app.mcp.tools.workspace  # noqa: F401
import app.mcp.tools.context  # noqa: F401
