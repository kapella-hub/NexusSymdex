"""End-to-end server tests."""

import pytest
import json

from nexus_symdex.server import server, list_tools, call_tool, _get_file_imports


@pytest.mark.asyncio
async def test_server_lists_all_tools():
    """Test that server lists all 19 tools."""
    tools = await list_tools()

    assert len(tools) == 43

    names = {t.name for t in tools}
    expected = {
        "index_repo", "index_folder", "list_repos", "get_file_tree",
        "get_file_outline", "get_symbol", "get_symbols", "search_symbols",
        "invalidate_cache", "search_text", "get_repo_outline",
        "search_all_repos", "get_context", "explain_symbol",
        "watch_folder", "unwatch_folder", "list_watches",
        "get_callers", "get_dependencies",
        "find_dead_code", "get_import_graph", "get_impact",
        "get_change_summary", "get_architecture_map",
        "get_review_context",
        "learn_from_changes", "recall_with_code", "review_with_history",
        "diff_since_index", "get_symbol_history", "suggest_symbols",
        "get_hotspots", "get_type_hierarchy", "get_similar_symbols",
        "compare_repos", "export_index",
        "get_evolution_timeline", "get_complexity_metrics",
        "get_contributors", "get_code_churn",
        "extract_conventions", "detect_patterns", "scaffold_symbol",
    }
    assert names == expected


@pytest.mark.asyncio
async def test_index_repo_tool_schema():
    """Test index_repo tool has correct schema."""
    tools = await list_tools()

    index_repo = next(t for t in tools if t.name == "index_repo")

    assert "url" in index_repo.inputSchema["properties"]
    assert "use_ai_summaries" in index_repo.inputSchema["properties"]
    assert "url" in index_repo.inputSchema["required"]


@pytest.mark.asyncio
async def test_search_symbols_tool_schema():
    """Test search_symbols tool has correct schema."""
    tools = await list_tools()

    search = next(t for t in tools if t.name == "search_symbols")

    props = search.inputSchema["properties"]
    assert "repo" in props
    assert "query" in props
    assert "kind" in props
    assert "file_pattern" in props
    assert "max_results" in props

    # kind should have enum
    assert "enum" in props["kind"]
    assert set(props["kind"]["enum"]) == {"function", "class", "method", "constant", "type"}


@pytest.mark.asyncio
async def test_get_symbol_has_include_imports_param():
    """Test get_symbol tool schema includes include_imports parameter."""
    tools = await list_tools()
    tool = next(t for t in tools if t.name == "get_symbol")
    props = tool.inputSchema["properties"]
    assert "include_imports" in props
    assert props["include_imports"]["type"] == "boolean"
    assert props["include_imports"]["default"] is False


@pytest.mark.asyncio
async def test_get_symbols_has_include_imports_param():
    """Test get_symbols tool schema includes include_imports parameter."""
    tools = await list_tools()
    tool = next(t for t in tools if t.name == "get_symbols")
    props = tool.inputSchema["properties"]
    assert "include_imports" in props
    assert props["include_imports"]["type"] == "boolean"
    assert props["include_imports"]["default"] is False


def test_get_file_imports_filters_correctly():
    """Test _get_file_imports returns only import refs for the given file."""

    class FakeIndex:
        references = [
            {"type": "import", "name": "os", "line": 1, "file": "main.py"},
            {"type": "import", "name": "sys", "line": 2, "file": "main.py"},
            {"type": "call", "name": "print", "line": 5, "file": "main.py"},
            {"type": "import", "name": "json", "line": 1, "file": "other.py"},
        ]

    result = _get_file_imports(FakeIndex(), "main.py")
    assert result == [
        {"name": "os", "line": 1},
        {"name": "sys", "line": 2},
    ]


def test_get_file_imports_empty_for_unknown_file():
    """Test _get_file_imports returns empty list for a file with no imports."""

    class FakeIndex:
        references = [
            {"type": "import", "name": "os", "line": 1, "file": "main.py"},
        ]

    result = _get_file_imports(FakeIndex(), "nonexistent.py")
    assert result == []
