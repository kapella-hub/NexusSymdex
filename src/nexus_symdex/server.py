"""MCP server for NexusSymdex."""

import argparse
import asyncio
import json
import os
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent

from .tools.index_repo import index_repo
from .tools.index_folder import index_folder
from .tools.list_repos import list_repos
from .tools.get_file_tree import get_file_tree
from .tools.get_file_outline import get_file_outline
from .tools.get_symbol import get_symbol, get_symbols
from .tools.search_symbols import search_symbols
from .tools.invalidate_cache import invalidate_cache
from .tools.search_text import search_text
from .tools.get_repo_outline import get_repo_outline
from .tools.search_all_repos import search_all_repos
from .tools.get_context import get_context
from .tools.explain_symbol import explain_symbol
from .tools.watch_folder import watch_folder, unwatch_folder, list_watches
from .tools.get_callers import get_callers
from .tools.get_dependencies import get_dependencies
from .tools.get_impact import get_impact
from .tools.get_import_graph import get_import_graph
from .tools.get_change_summary import get_change_summary
from .tools.get_architecture_map import get_architecture_map

from .tools.get_review_context import get_review_context as get_review_context_fn
from .tools.find_dead_code import find_dead_code
from .tools.learn_from_changes import learn_from_changes
from .tools.recall_with_code import recall_with_code
from .tools.review_with_history import review_with_history
from .tools.diff_since_index import diff_since_index
from .tools.get_symbol_history import get_symbol_history
from .tools.suggest_symbols import suggest_symbols
from .tools.get_hotspots import get_hotspots
from .tools.get_type_hierarchy import get_type_hierarchy
from .tools.get_similar_symbols import get_similar_symbols
from .tools.compare_repos import compare_repos
from .tools.export_index import export_index
from .tools._utils import resolve_repo
from .storage import IndexStore


def _get_file_imports(index, file_path: str) -> list[dict]:
    """Get import references for a file."""
    return [
        {"name": ref["name"], "line": ref["line"]}
        for ref in index.references
        if ref.get("type") == "import" and ref.get("file") == file_path
    ]


# Create server
server = Server("NexusSymdex")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        Tool(
            name="index_repo",
            description="Index a GitHub repository's source code. Fetches files, parses ASTs, extracts symbols, and saves to local storage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "GitHub repository URL or owner/repo string"
                    },
                    "use_ai_summaries": {
                        "type": "boolean",
                        "description": "Use AI to generate symbol summaries (requires ANTHROPIC_API_KEY or GOOGLE_API_KEY). Anthropic takes priority if both are set. When false, uses docstrings or signature fallback.",
                        "default": True
                    },
                    "incremental": {
                        "type": "boolean",
                        "description": "When true and an existing index exists, only re-index changed files.",
                        "default": False
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="index_folder",
            description="Index a local folder containing source code. Walks directory, parses ASTs, extracts symbols, and saves to local storage. Works with any folder containing supported language files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to local folder (absolute or relative, supports ~ for home directory)"
                    },
                    "use_ai_summaries": {
                        "type": "boolean",
                        "description": "Use AI to generate symbol summaries (requires ANTHROPIC_API_KEY or GOOGLE_API_KEY). Anthropic takes priority if both are set. When false, uses docstrings or signature fallback.",
                        "default": True
                    },
                    "extra_ignore_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional gitignore-style patterns to exclude from indexing"
                    },
                    "follow_symlinks": {
                        "type": "boolean",
                        "description": "Whether to follow symlinks. Default false for security.",
                        "default": False
                    },
                    "incremental": {
                        "type": "boolean",
                        "description": "When true and an existing index exists, only re-index changed files.",
                        "default": False
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="list_repos",
            description="List all indexed repositories.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_file_tree",
            description="Get the file tree of an indexed repository, optionally filtered by path prefix.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "path_prefix": {
                        "type": "string",
                        "description": "Optional path prefix to filter (e.g., 'src/utils')",
                        "default": ""
                    },
                    "include_summaries": {
                        "type": "boolean",
                        "description": "Include per-file summaries in the tree output",
                        "default": False
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="get_file_outline",
            description="Get all symbols (functions, classes, methods) in a file with signatures and summaries.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file within the repository (e.g., 'src/main.py')"
                    }
                },
                "required": ["repo", "file_path"]
            }
        ),
        Tool(
            name="get_symbol",
            description="Get the full source code of a specific symbol. Use after identifying relevant symbols via get_file_outline or search_symbols.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "symbol_id": {
                        "type": "string",
                        "description": "Symbol ID from get_file_outline or search_symbols"
                    },
                    "verify": {
                        "type": "boolean",
                        "description": "Verify content hash matches stored hash (detects source drift)",
                        "default": False
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Number of lines before/after symbol to include for context",
                        "default": 0
                    },
                    "include_imports": {
                        "type": "boolean",
                        "description": "Include file import statements",
                        "default": False
                    }
                },
                "required": ["repo", "symbol_id"]
            }
        ),
        Tool(
            name="get_symbols",
            description="Get full source code of multiple symbols in one call. Efficient for loading related symbols.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "symbol_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of symbol IDs to retrieve"
                    },
                    "include_imports": {
                        "type": "boolean",
                        "description": "Include file import statements for each symbol's file",
                        "default": False
                    }
                },
                "required": ["repo", "symbol_ids"]
            }
        ),
        Tool(
            name="search_symbols",
            description="Search for symbols matching a query across the entire indexed repository. Returns matches with signatures and summaries.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (matches symbol names, signatures, summaries, docstrings)"
                    },
                    "kind": {
                        "type": "string",
                        "description": "Optional filter by symbol kind",
                        "enum": ["function", "class", "method", "constant", "type"]
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Optional glob pattern to filter files (e.g., 'src/**/*.py')"
                    },
                    "language": {
                        "type": "string",
                        "description": "Optional filter by language",
                        "enum": ["python", "javascript", "typescript", "go", "rust", "java", "php"]
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 10
                    }
                },
                "required": ["repo", "query"]
            }
        ),
        Tool(
            name="invalidate_cache",
            description="Delete the index and cached files for a repository. Forces a full re-index on next index_repo or index_folder call.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="search_text",
            description="Full-text search across indexed file contents. Useful when symbol search misses (e.g., string literals, comments, config values).",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Text to search for (case-insensitive substring match)"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Optional glob pattern to filter files (e.g., '*.py')"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matching lines to return",
                        "default": 20
                    }
                },
                "required": ["repo", "query"]
            }
        ),
        Tool(
            name="get_repo_outline",
            description="Get a high-level overview of an indexed repository: directories, file counts, language breakdown, symbol counts. Lighter than get_file_tree.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="search_all_repos",
            description="Search symbols across ALL indexed repositories. Returns combined results sorted by relevance score.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (matches symbol names, signatures, summaries, docstrings)"
                    },
                    "kind": {
                        "type": "string",
                        "description": "Optional filter by symbol kind",
                        "enum": ["function", "class", "method", "constant", "type"]
                    },
                    "language": {
                        "type": "string",
                        "description": "Optional filter by language",
                        "enum": ["python", "javascript", "typescript", "go", "rust", "java", "php"]
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 20
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_context",
            description="Get the most relevant symbols that fit within a token budget. Returns symbol source code, greedily filling the budget by relevance (if focus query given) or by size (smallest first). With include_deps=true, also includes direct dependencies (callees and imports) of focused symbols.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "budget_tokens": {
                        "type": "integer",
                        "description": "Max tokens to include (default 4000)",
                        "default": 4000
                    },
                    "focus": {
                        "type": "string",
                        "description": "Optional search query to focus context on"
                    },
                    "kind": {
                        "type": "string",
                        "description": "Optional filter by symbol kind",
                        "enum": ["function", "class", "method", "constant", "type"]
                    },
                    "include_deps": {
                        "type": "boolean",
                        "description": "When true and focus is set, also include direct dependencies (callees and imports) of the focused symbols within the budget",
                        "default": False
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="explain_symbol",
            description="Get a structured LLM-powered explanation of a symbol: purpose, inputs, output, side effects, and complexity. Falls back to heuristic explanation if no LLM is available.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "symbol_id": {
                        "type": "string",
                        "description": "Symbol ID from get_file_outline or search_symbols"
                    }
                },
                "required": ["repo", "symbol_id"]
            }
        ),
        Tool(
            name="watch_folder",
            description="Start watching a local folder for file changes and automatically trigger incremental reindex. Requires the folder to be indexed first.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the local folder to watch"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="unwatch_folder",
            description="Stop watching a folder for changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the folder to stop watching"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="list_watches",
            description="List all actively watched folders.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_callers",
            description="Find all call sites that reference a given symbol. Shows where a function/method is called from across the indexed codebase.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "symbol_id": {
                        "type": "string",
                        "description": "Symbol ID to find callers for"
                    }
                },
                "required": ["repo", "symbol_id"]
            }
        ),
        Tool(
            name="get_dependencies",
            description="Find what a symbol calls/imports. Shows outgoing calls and file-level imports for understanding a symbol's dependencies.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "symbol_id": {
                        "type": "string",
                        "description": "Symbol ID to find dependencies for"
                    }
                },
                "required": ["repo", "symbol_id"]
            }
        ),
        Tool(
            name="get_impact",
            description="Transitive impact analysis: if you change a symbol, what else might break? BFS through the caller graph up to max_depth levels.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "symbol_id": {
                        "type": "string",
                        "description": "Symbol ID to analyse impact for"
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth of caller traversal (1-10, default 5)",
                        "default": 5
                    }
                },
                "required": ["repo", "symbol_id"]
            }
        ),
        Tool(
            name="get_import_graph",
            description="Build a file-to-file import dependency graph. Shows which files import which, identifies hubs (most-imported files) and fans (files importing the most). Supports adjacency list, DOT, and summary formats.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format",
                        "enum": ["adjacency", "dot", "summary"],
                        "default": "adjacency"
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional: only show graph for this file and its direct neighbors"
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="get_change_summary",
            description="Compare current file contents against the stored index to show what symbols changed, were added, or were removed since the last index. Requires a local path for the repo.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional path to local folder with current files (required for local repos if not auto-detectable)"
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="get_architecture_map",
            description="Auto-detect architectural layers in a codebase. Classifies every file into a layer (entry, api/routes, core/service, utility, model/data, test, config) using import-graph topology and path heuristics. Also finds the longest import chain (spine).",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="find_dead_code",
            description="Find symbols that are never referenced (called/imported) from anywhere else in the codebase. Detects potential dead code. Excludes common entry points (main, test functions, decorated endpoints) to reduce false positives.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "include_tests": {
                        "type": "boolean",
                        "description": "When true, include symbols from test files in results",
                        "default": False
                    }
                },
                "required": ["repo"]
            }
        ),
        Tool(
            name="get_review_context",
            description="Assemble minimal context for reviewing code changes. Given a list of changed files, finds the changed symbols, their callers (affected code), their dependencies, and related test files. Packs everything into a token budget with priority ordering. Perfect for PR reviews.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository identifier (owner/repo or just repo name)"
                    },
                    "changed_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths that changed (relative to repo root)"
                    },
                    "budget_tokens": {
                        "type": "integer",
                        "description": "Max tokens for context (default 8000)",
                        "default": 8000
                    },
                },
                "required": ["repo", "changed_files"]
            }
        ),
        Tool(
            name="learn_from_changes",
            description="Record code changes to NexusCortex memory. Detects current changes vs stored index and learns the action/outcome for future recall. Requires NexusCortex to be running.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository identifier (owner/repo or just repo name)"},
                    "path": {"type": "string", "description": "Local folder path for change detection"},
                    "message": {"type": "string", "description": "Optional description of what changed and why"},
                },
                "required": ["repo"],
            },
        ),
        Tool(
            name="recall_with_code",
            description="Recall memories from NexusCortex and cross-reference with current code symbols. Combines historical context with live code intelligence for richer task context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Description of what you're trying to do"},
                    "repo": {"type": "string", "description": "Repository identifier (owner/repo or just repo name)"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional filter tags"},
                    "top_k": {"type": "integer", "description": "Max memories to recall (default 5)", "default": 5},
                    "budget_tokens": {"type": "integer", "description": "Token budget for code context (default 4000)", "default": 4000},
                },
                "required": ["task", "repo"],
            },
        ),
        Tool(
            name="review_with_history",
            description="PR review context enriched with historical memory. Combines changed symbols, callers, dependencies, and tests with NexusCortex memories about past changes to the same files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository identifier (owner/repo or just repo name)"},
                    "changed_files": {"type": "array", "items": {"type": "string"}, "description": "List of file paths that changed"},
                    "budget_tokens": {"type": "integer", "description": "Token budget (default 8000)", "default": 8000},
                },
                "required": ["repo", "changed_files"],
            },
        ),
        Tool(
            name="diff_since_index",
            description="Show what changed on disk since the last indexing. Compares stored file hashes against current files to detect new, modified, and deleted files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository identifier (owner/repo or just repo name)"},
                },
                "required": ["repo"],
            },
        ),
        Tool(
            name="get_symbol_history",
            description="Get the change history for a specific symbol across re-indexes. Shows when the symbol's content hash or signature changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository identifier (owner/repo or just repo name)"},
                    "symbol_id": {"type": "string", "description": "Symbol ID to get history for"},
                },
                "required": ["repo", "symbol_id"],
            },
        ),
        Tool(
            name="suggest_symbols",
            description="Given a natural language task description, return the most relevant symbols to read or modify. Combines search relevance, file path heuristics, symbol kind weighting, and caller-count importance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository identifier (owner/repo or just repo name)"},
                    "task": {"type": "string", "description": "Natural language task description (e.g., 'add rate limiting to the API')"},
                    "max_results": {"type": "integer", "description": "Maximum symbols to suggest (default 15)", "default": 15},
                },
                "required": ["repo", "task"],
            },
        ),
        Tool(
            name="get_hotspots",
            description="Rank symbols by how many callers reference them. Identifies the most-depended-on code — high-risk areas for changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository identifier (owner/repo or just repo name)"},
                    "kind": {"type": "string", "description": "Optional filter by symbol kind", "enum": ["function", "class", "method", "constant", "type"]},
                    "min_callers": {"type": "integer", "description": "Minimum caller count to include (default 2)", "default": 2},
                    "max_results": {"type": "integer", "description": "Maximum results (default 20)", "default": 20},
                },
                "required": ["repo"],
            },
        ),
        Tool(
            name="get_type_hierarchy",
            description="For a class or type symbol, show its inheritance chain — parent classes and subclasses found in the indexed codebase.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository identifier (owner/repo or just repo name)"},
                    "symbol_id": {"type": "string", "description": "Symbol ID of a class or type"},
                },
                "required": ["repo", "symbol_id"],
            },
        ),
        Tool(
            name="get_similar_symbols",
            description="Find symbols with similar signatures or structure. Useful for detecting near-duplicates, finding related implementations, or identifying refactoring candidates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository identifier (owner/repo or just repo name)"},
                    "symbol_id": {"type": "string", "description": "Symbol ID to find similar symbols for"},
                    "max_results": {"type": "integer", "description": "Maximum results (default 10)", "default": 10},
                },
                "required": ["repo", "symbol_id"],
            },
        ),
        Tool(
            name="compare_repos",
            description="Diff the symbol surface between two indexed repositories. Shows symbols only in A, only in B, and modified (same name but different content). Useful for comparing forks, versions, or related projects.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_a": {"type": "string", "description": "First repository identifier"},
                    "repo_b": {"type": "string", "description": "Second repository identifier"},
                },
                "required": ["repo_a", "repo_b"],
            },
        ),
        Tool(
            name="export_index",
            description="Export the index as structured markdown or JSON for direct context inclusion. Organized by file with symbol hierarchy, signatures, and summaries.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository identifier (owner/repo or just repo name)"},
                    "format": {"type": "string", "description": "Output format", "enum": ["markdown", "json"], "default": "markdown"},
                    "include_signatures": {"type": "boolean", "description": "Include signatures (default true)", "default": True},
                    "include_summaries": {"type": "boolean", "description": "Include summaries (default true)", "default": True},
                    "path_prefix": {"type": "string", "description": "Optional path prefix filter"},
                },
                "required": ["repo"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    storage_path = os.environ.get("CODE_INDEX_PATH")
    
    try:
        if name == "index_repo":
            result = await index_repo(
                url=arguments["url"],
                use_ai_summaries=arguments.get("use_ai_summaries", True),
                storage_path=storage_path,
                incremental=arguments.get("incremental", False),
            )
        elif name == "index_folder":
            result = index_folder(
                path=arguments["path"],
                use_ai_summaries=arguments.get("use_ai_summaries", True),
                storage_path=storage_path,
                extra_ignore_patterns=arguments.get("extra_ignore_patterns"),
                follow_symlinks=arguments.get("follow_symlinks", False),
                incremental=arguments.get("incremental", False),
            )
        elif name == "list_repos":
            result = list_repos(storage_path=storage_path)
        elif name == "get_file_tree":
            result = get_file_tree(
                repo=arguments["repo"],
                path_prefix=arguments.get("path_prefix", ""),
                include_summaries=arguments.get("include_summaries", False),
                storage_path=storage_path
            )
        elif name == "get_file_outline":
            result = get_file_outline(
                repo=arguments["repo"],
                file_path=arguments["file_path"],
                storage_path=storage_path
            )
        elif name == "get_symbol":
            result = get_symbol(
                repo=arguments["repo"],
                symbol_id=arguments["symbol_id"],
                verify=arguments.get("verify", False),
                context_lines=arguments.get("context_lines", 0),
                storage_path=storage_path
            )
            if arguments.get("include_imports") and "error" not in result:
                owner, repo_name = resolve_repo(arguments["repo"], storage_path)
                store = IndexStore(base_path=storage_path)
                index = store.load_index(owner, repo_name)
                if index:
                    result["imports"] = _get_file_imports(index, result["file"])
        elif name == "get_symbols":
            result = get_symbols(
                repo=arguments["repo"],
                symbol_ids=arguments["symbol_ids"],
                storage_path=storage_path
            )
            if arguments.get("include_imports") and "error" not in result:
                owner, repo_name = resolve_repo(arguments["repo"], storage_path)
                store = IndexStore(base_path=storage_path)
                index = store.load_index(owner, repo_name)
                if index:
                    seen_files: set[str] = set()
                    all_imports: list[dict] = []
                    for sym in result.get("symbols", []):
                        f = sym["file"]
                        if f not in seen_files:
                            seen_files.add(f)
                            all_imports.extend(
                                {"file": f, **imp}
                                for imp in _get_file_imports(index, f)
                            )
                    result["imports"] = all_imports
        elif name == "search_symbols":
            result = search_symbols(
                repo=arguments["repo"],
                query=arguments["query"],
                kind=arguments.get("kind"),
                file_pattern=arguments.get("file_pattern"),
                language=arguments.get("language"),
                max_results=arguments.get("max_results", 10),
                storage_path=storage_path
            )
        elif name == "invalidate_cache":
            result = invalidate_cache(
                repo=arguments["repo"],
                storage_path=storage_path
            )
        elif name == "search_text":
            result = search_text(
                repo=arguments["repo"],
                query=arguments["query"],
                file_pattern=arguments.get("file_pattern"),
                max_results=arguments.get("max_results", 20),
                storage_path=storage_path
            )
        elif name == "get_repo_outline":
            result = get_repo_outline(
                repo=arguments["repo"],
                storage_path=storage_path
            )
        elif name == "search_all_repos":
            result = search_all_repos(
                query=arguments["query"],
                kind=arguments.get("kind"),
                language=arguments.get("language"),
                max_results=arguments.get("max_results", 20),
                storage_path=storage_path,
            )
        elif name == "get_context":
            result = get_context(
                repo=arguments["repo"],
                budget_tokens=arguments.get("budget_tokens", 4000),
                focus=arguments.get("focus"),
                kind=arguments.get("kind"),
                include_deps=arguments.get("include_deps", False),
                storage_path=storage_path,
            )
        elif name == "explain_symbol":
            result = await explain_symbol(
                repo=arguments["repo"],
                symbol_id=arguments["symbol_id"],
                storage_path=storage_path,
            )
        elif name == "watch_folder":
            result = watch_folder(
                path=arguments["path"],
                storage_path=storage_path,
            )
        elif name == "unwatch_folder":
            result = unwatch_folder(
                path=arguments["path"],
                storage_path=storage_path,
            )
        elif name == "list_watches":
            result = list_watches(
                storage_path=storage_path,
            )
        elif name == "get_callers":
            result = get_callers(
                repo=arguments["repo"],
                symbol_id=arguments["symbol_id"],
                storage_path=storage_path,
            )
        elif name == "get_dependencies":
            result = get_dependencies(
                repo=arguments["repo"],
                symbol_id=arguments["symbol_id"],
                storage_path=storage_path,
            )
        elif name == "get_impact":
            result = get_impact(
                repo=arguments["repo"],
                symbol_id=arguments["symbol_id"],
                max_depth=arguments.get("max_depth", 5),
                storage_path=storage_path,
            )
        elif name == "get_import_graph":
            result = get_import_graph(
                repo=arguments["repo"],
                format=arguments.get("format", "adjacency"),
                file_path=arguments.get("file_path"),
                storage_path=storage_path,
            )
        elif name == "get_change_summary":
            result = get_change_summary(
                repo=arguments["repo"],
                path=arguments.get("path"),
                storage_path=storage_path,
            )
        elif name == "get_architecture_map":
            result = get_architecture_map(
                repo=arguments["repo"],
                storage_path=storage_path,
            )
        elif name == "find_dead_code":
            result = find_dead_code(
                repo=arguments["repo"],
                include_tests=arguments.get("include_tests", False),
                storage_path=storage_path,
            )
        elif name == "get_review_context":
            result = get_review_context_fn(
                repo=arguments["repo"],
                changed_files=arguments["changed_files"],
                budget_tokens=arguments.get("budget_tokens", 8000),
                storage_path=storage_path,
            )
        elif name == "learn_from_changes":
            result = await learn_from_changes(
                repo=arguments["repo"],
                path=arguments.get("path"),
                message=arguments.get("message"),
                storage_path=storage_path,
            )
        elif name == "recall_with_code":
            result = await recall_with_code(
                task=arguments["task"],
                repo=arguments["repo"],
                tags=arguments.get("tags"),
                top_k=arguments.get("top_k", 5),
                budget_tokens=arguments.get("budget_tokens", 4000),
                storage_path=storage_path,
            )
        elif name == "review_with_history":
            result = await review_with_history(
                repo=arguments["repo"],
                changed_files=arguments["changed_files"],
                budget_tokens=arguments.get("budget_tokens", 8000),
                storage_path=storage_path,
            )
        elif name == "diff_since_index":
            result = diff_since_index(
                repo=arguments["repo"],
                storage_path=storage_path,
            )
        elif name == "get_symbol_history":
            result = get_symbol_history(
                repo=arguments["repo"],
                symbol_id=arguments["symbol_id"],
                storage_path=storage_path,
            )
        elif name == "suggest_symbols":
            result = suggest_symbols(
                repo=arguments["repo"],
                task=arguments["task"],
                max_results=arguments.get("max_results", 15),
                storage_path=storage_path,
            )
        elif name == "get_hotspots":
            result = get_hotspots(
                repo=arguments["repo"],
                kind=arguments.get("kind"),
                min_callers=arguments.get("min_callers", 2),
                max_results=arguments.get("max_results", 20),
                storage_path=storage_path,
            )
        elif name == "get_type_hierarchy":
            result = get_type_hierarchy(
                repo=arguments["repo"],
                symbol_id=arguments["symbol_id"],
                storage_path=storage_path,
            )
        elif name == "get_similar_symbols":
            result = get_similar_symbols(
                repo=arguments["repo"],
                symbol_id=arguments["symbol_id"],
                max_results=arguments.get("max_results", 10),
                storage_path=storage_path,
            )
        elif name == "compare_repos":
            result = compare_repos(
                repo_a=arguments["repo_a"],
                repo_b=arguments["repo_b"],
                storage_path=storage_path,
            )
        elif name == "export_index":
            result = export_index(
                repo=arguments["repo"],
                format=arguments.get("format", "markdown"),
                include_signatures=arguments.get("include_signatures", True),
                include_summaries=arguments.get("include_summaries", True),
                path_prefix=arguments.get("path_prefix"),
                storage_path=storage_path,
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
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
