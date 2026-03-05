"""Tests for intelligence suite tools."""
import pytest
from nexus_symdex.parser import parse_file, Symbol
from nexus_symdex.parser.references import extract_references
from nexus_symdex.storage import IndexStore

# Shared test fixtures
MULTI_FILE_JS = {
    "lib/main.js": '''
function main() {
    const result = helper();
    return result;
}

function helper() {
    return utils();
}

function unused() {
    return "never called";
}

function alsoUnused() {
    return "also never called";
}
''',
    "lib/utils.js": '''
function utils() {
    return "utility";
}

function deadUtil() {
    return "dead";
}
''',
}


def _build_test_index(files_dict, storage_path):
    """Helper: parse files, extract refs, save index."""
    all_symbols = []
    all_refs = []
    raw_files = {}
    for path, content in files_dict.items():
        lang = "javascript" if path.endswith(".js") else "python"
        symbols = parse_file(content, path, lang)
        refs = extract_references(content, path, lang)
        # Tag refs with file
        for r in refs:
            r["file"] = path
        all_symbols.extend(symbols)
        all_refs.extend(refs)
        raw_files[path] = content

    languages = {"javascript": len(files_dict)}
    store = IndexStore(base_path=storage_path)
    store.save_index(
        owner="test",
        name="test-repo",
        source_files=list(files_dict.keys()),
        symbols=all_symbols,
        raw_files=raw_files,
        languages=languages,
        references=all_refs,
    )
    return store


def test_find_dead_code_basic(tmp_path):
    """Test that unreferenced functions are detected as dead code."""
    from nexus_symdex.tools.find_dead_code import find_dead_code

    _build_test_index(MULTI_FILE_JS, str(tmp_path))
    result = find_dead_code("test/test-repo", storage_path=str(tmp_path))

    assert "error" not in result
    dead_names = {s["name"] for s in result["dead_symbols"]}
    # These are never called
    assert "unused" in dead_names
    assert "alsoUnused" in dead_names
    assert "deadUtil" in dead_names
    # These ARE called (main is entry point, helper/utils are called)
    assert "main" not in dead_names
    assert "helper" not in dead_names
    assert "utils" not in dead_names


def test_find_dead_code_metadata(tmp_path):
    """Test that result contains expected metadata fields."""
    from nexus_symdex.tools.find_dead_code import find_dead_code

    _build_test_index(MULTI_FILE_JS, str(tmp_path))
    result = find_dead_code("test/test-repo", storage_path=str(tmp_path))

    assert "dead_count" in result
    assert "total_symbols" in result
    assert "_meta" in result
    assert "timing_ms" in result["_meta"]
    assert result["dead_count"] == len(result["dead_symbols"])
    assert result["repo"] == "test/test-repo"


def test_find_dead_code_symbol_details(tmp_path):
    """Test that dead symbol entries contain required fields."""
    from nexus_symdex.tools.find_dead_code import find_dead_code

    _build_test_index(MULTI_FILE_JS, str(tmp_path))
    result = find_dead_code("test/test-repo", storage_path=str(tmp_path))

    for sym in result["dead_symbols"]:
        assert "name" in sym
        assert "file" in sym
        assert "line" in sym
        assert "kind" in sym
        assert "qualified_name" in sym


def test_find_dead_code_not_indexed(tmp_path):
    """Test error when repo is not indexed."""
    from nexus_symdex.tools.find_dead_code import find_dead_code

    result = find_dead_code("test/nonexistent", storage_path=str(tmp_path))
    assert "error" in result


def test_find_dead_code_excludes_test_files(tmp_path):
    """Test that symbols from test files are excluded by default."""
    from nexus_symdex.tools.find_dead_code import find_dead_code

    files = {
        **MULTI_FILE_JS,
        "tests/test_foo.js": '''
function test_something() {
    return unused();
}

function helperForTests() {
    return "test helper";
}
''',
    }
    _build_test_index(files, str(tmp_path))

    # Default: exclude test files
    result = find_dead_code("test/test-repo", storage_path=str(tmp_path))
    dead_names = {s["name"] for s in result["dead_symbols"]}
    assert "helperForTests" not in dead_names  # from test file, excluded

    # With include_tests=True
    result_with_tests = find_dead_code(
        "test/test-repo", include_tests=True, storage_path=str(tmp_path)
    )
    dead_names_with = {s["name"] for s in result_with_tests["dead_symbols"]}
    # test_something starts with test_ so still excluded by entry-point rule
    assert "test_something" not in dead_names_with
    # helperForTests should now appear since it's unreferenced and include_tests is on
    assert "helperForTests" in dead_names_with
