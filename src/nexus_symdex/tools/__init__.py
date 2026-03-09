"""MCP tools package."""

import importlib
import pkgutil


def discover_tools() -> dict[str, dict]:
    """Auto-discover TOOL_DEF(s) from all tool modules.

    Scans every non-private module in this package for a ``TOOL_DEF`` dict
    (single tool) or ``TOOL_DEFS`` list (multiple tools) and returns a
    mapping of tool name to its definition dict.
    """
    tools: dict[str, dict] = {}
    package = importlib.import_module("nexus_symdex.tools")
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        if module_name.startswith("_"):
            continue
        module = importlib.import_module(f".{module_name}", package="nexus_symdex.tools")
        if hasattr(module, "TOOL_DEF"):
            defn = module.TOOL_DEF
            tools[defn["name"]] = defn
        elif hasattr(module, "TOOL_DEFS"):
            for defn in module.TOOL_DEFS:
                tools[defn["name"]] = defn
    return tools
