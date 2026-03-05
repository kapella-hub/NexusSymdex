"""PR review context tool — assemble minimal context for understanding code changes."""

import time
from typing import Optional

from ..storage import IndexStore
from ._utils import resolve_repo


def get_review_context(
    repo: str,
    changed_files: list[str],
    budget_tokens: int = 8000,
    storage_path: Optional[str] = None,
) -> dict:
    """Assemble minimal context for reviewing changed files.

    For each changed file:
    1. Find all symbols in that file
    2. Find callers of those symbols (who's affected?)
    3. Find dependencies of those symbols (what do they use?)
    4. Find related test files
    5. Pack everything into a token budget

    Args:
        repo: Repository identifier.
        changed_files: List of file paths that changed.
        budget_tokens: Max tokens for the assembled context.
        storage_path: Custom storage path.

    Returns:
        Dict with changed symbols, affected callers, dependencies, and test files.
    """
    start = time.perf_counter()
    budget_tokens = max(500, min(budget_tokens, 200_000))

    try:
        owner, name = resolve_repo(repo, storage_path)
    except ValueError as e:
        return {"error": str(e)}

    store = IndexStore(base_path=storage_path)
    index = store.load_index(owner, name)
    if not index:
        return {"error": f"Repository not indexed: {owner}/{name}"}

    # 1. Find changed symbols
    changed_symbols = []
    changed_sym_ids = set()
    for sym in index.symbols:
        if sym.get("file") in changed_files:
            changed_symbols.append(sym)
            changed_sym_ids.add(sym["id"])

    # 2. Find callers of changed symbols (affected code)
    caller_ids = set()
    for sym in changed_symbols:
        sym_name = sym.get("name", "")
        sym_qname = sym.get("qualified_name", "")
        for ref in index.references:
            if ref.get("type") != "call":
                continue
            ref_name = ref.get("name", "")
            # Match by name or qualified name
            if ref_name == sym_name or ref_name == sym_qname or ref_name.endswith(f".{sym_name}"):
                ref_file = ref.get("file", "")
                if ref_file in changed_files:
                    continue  # Skip callers in the same changed files
                ref_line = ref.get("line", 0)
                # Find the symbol that contains this reference
                for candidate in index.symbols:
                    if candidate.get("file") != ref_file:
                        continue
                    if candidate.get("line", 0) <= ref_line <= candidate.get("end_line", 0):
                        if candidate["id"] not in changed_sym_ids:
                            caller_ids.add(candidate["id"])
                        break

    # 3. Find dependencies of changed symbols
    dep_ids = set()
    for sym in changed_symbols:
        sym_file = sym.get("file", "")
        sym_start = sym.get("line", 0)
        sym_end = sym.get("end_line", 0)

        # Find calls within the symbol's range
        for ref in index.references:
            if ref.get("file") != sym_file:
                continue
            if ref.get("type") != "call":
                continue
            ref_line = ref.get("line", 0)
            if sym_start <= ref_line <= sym_end:
                callee_name = ref.get("name", "")
                bare_name = callee_name.split(".")[-1] if "." in callee_name else callee_name
                for candidate in index.symbols:
                    cand_name = candidate.get("name", "")
                    if cand_name == bare_name and candidate["id"] not in changed_sym_ids:
                        dep_ids.add(candidate["id"])
                        break

    # 4. Find related test files
    test_files = set()
    for f in index.source_files:
        f_lower = f.lower()
        if "test" in f_lower or "spec" in f_lower:
            # Check if any changed file's module name appears in the test file name
            for changed in changed_files:
                base = changed.split("/")[-1].rsplit(".", 1)[0]
                if base in f:
                    test_files.add(f)

    # 5. Get test file symbols
    test_sym_ids = set()
    for sym in index.symbols:
        if sym.get("file") in test_files and sym["id"] not in changed_sym_ids:
            test_sym_ids.add(sym["id"])

    # 6. Pack into budget with priority: changed > callers > deps > tests
    tokens_used = 0
    result_changed = []
    result_callers = []
    result_deps = []
    result_tests = []

    def _add_symbol(sym_id, target_list, tag):
        nonlocal tokens_used
        sym = index.get_symbol(sym_id)
        if not sym:
            return False
        byte_length = sym.get("byte_length", 0)
        est_tokens = byte_length // 4 or 1

        if tokens_used + est_tokens > budget_tokens:
            return False

        source = store.get_symbol_content(owner, name, sym_id)
        if source is None:
            return False

        tokens_used += est_tokens
        target_list.append({
            "id": sym_id,
            "name": sym["name"],
            "kind": sym["kind"],
            "file": sym["file"],
            "line": sym["line"],
            "signature": sym["signature"],
            "source": source,
            "context_type": tag,
        })
        return True

    # Add in priority order
    for sym in changed_symbols:
        _add_symbol(sym["id"], result_changed, "changed")

    for sid in sorted(caller_ids):
        _add_symbol(sid, result_callers, "caller")

    for sid in sorted(dep_ids):
        _add_symbol(sid, result_deps, "dependency")

    for sid in sorted(test_sym_ids):
        _add_symbol(sid, result_tests, "test")

    elapsed = (time.perf_counter() - start) * 1000

    return {
        "repo": f"{owner}/{name}",
        "changed_files": changed_files,
        "sections": {
            "changed": result_changed,
            "callers": result_callers,
            "dependencies": result_deps,
            "tests": result_tests,
        },
        "related_test_files": sorted(test_files),
        "_meta": {
            "timing_ms": round(elapsed, 1),
            "tokens_used": tokens_used,
            "tokens_budget": budget_tokens,
            "changed_symbols": len(result_changed),
            "affected_callers": len(result_callers),
            "dependencies": len(result_deps),
            "test_symbols": len(result_tests),
        },
    }
