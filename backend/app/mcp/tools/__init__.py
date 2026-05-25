"""MCP tool modules — imported to register handlers with the MCP registry."""
from __future__ import annotations

# Each module is imported to trigger @mcp_registry.register decorators.
# Import order does not matter — registration is by tool name.

import app.mcp.tools.system  # noqa: F401
import app.mcp.tools.funnel  # noqa: F401
import app.mcp.tools.write  # noqa: F401
import app.mcp.tools.dangerous  # noqa: F401
import app.mcp.tools.workspace  # noqa: F401
import app.mcp.tools.context  # noqa: F401
import app.mcp.tools.workflows  # noqa: F401
