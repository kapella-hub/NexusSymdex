"""MCP server for NexusSymdex."""

import argparse
import asyncio
import inspect
import json
import os
from typing import Optional

from mcp.server import Server
from mcp.types import Tool, TextContent

from .tools import discover_tools

# Build the tool registry once at import time.
_TOOLS = discover_tools()

# Create server
server = Server("NexusSymdex")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["inputSchema"],
        )
        for t in _TOOLS.values()
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    storage_path = os.environ.get("CODE_INDEX_PATH")

    tool = _TOOLS.get(name)
    if not tool:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}, indent=2))]

    try:
        handler = tool["handler"]
        sig = inspect.signature(handler)
        if "storage_path" in sig.parameters:
            arguments["storage_path"] = storage_path

        if tool.get("is_async"):
            result = await handler(**arguments)
        else:
            result = handler(**arguments)

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


async def run_server():
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main(argv: Optional[list[str]] = None):
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="nexus-symdex",
        description="Run the NexusSymdex MCP stdio server.",
    )
    parser.parse_args(argv)
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
