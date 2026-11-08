"""Local stdio MCP server entry point for EdgeForge Engine."""

from __future__ import annotations

from appbuilder.mcp.tools import ENGINE_MCP_TOOLS

SERVER_NAME = "edgeforge-engine"


def register_tools(mcp: object) -> None:
    """Register the bounded Phase 4 Engine MCP tool vocabulary."""

    for tool in ENGINE_MCP_TOOLS:
        mcp.tool()(tool)


def create_mcp_server() -> object:
    """Create a FastMCP server with all Engine tools registered."""

    from fastmcp import FastMCP

    mcp = FastMCP(SERVER_NAME)
    register_tools(mcp)
    return mcp


def main() -> None:
    """Run the local stdio MCP server."""

    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
