"""Find what a symbol calls/imports (its dependencies)."""

import time
from typing import Optional

from ..storage import IndexStore
from ._utils import resolve_repo


def get_dependencies(
    repo: str,
    symbol_id: str,
    storage_path: Optional[str] = None,
) -> dict:
    """Find what a symbol calls/imports.

    Filters the stored references to those within the symbol's line range,
    returning both imports and outgoing calls.

    Args:
        repo: Repository identifier (owner/repo or just repo name).
        symbol_id: Symbol ID to find dependencies for.
        storage_path: Custom storage path.

    Returns:
        Dict with imports and calls lists, plus metadata.
    """
    start = time.perf_counter()

    try:
        owner, name = resolve_repo(repo, storage_path)
    except ValueError as e:
        return {"error": str(e)}

    store = IndexStore(base_path=storage_path)
    index = store.load_index(owner, name)

    if not index:
        return {"error": f"Repository not indexed: {owner}/{name}"}

    symbol = index.get_symbol(symbol_id)
    if not symbol:
        return {"error": f"Symbol not found: {symbol_id}"}

    target_file = symbol["file"]
    sym_start = symbol["line"]
    sym_end = symbol["end_line"]

    imports = []
    calls = []

    for ref in index.references:
        ref_file = ref.get("file", "")
        ref_line = ref.get("line", 0)

        # For imports: match file-level imports (line before symbol or at top of file)
        # For calls: match within the symbol's line range
        if ref_file != target_file:
            continue

        if ref["type"] == "import":
            # Include file-level imports (they're dependencies of all symbols in the file)
            imports.append({
                "name": ref["name"],
                "line": ref_line,
            })
        elif ref["type"] == "call":
            if sym_start <= ref_line <= sym_end:
                calls.append({
                    "name": ref["name"],
                    "line": ref_line,
                })

    # Deduplicate by name while preserving order
    seen_imports: set[str] = set()
    unique_imports = []
    for imp in imports:
        if imp["name"] not in seen_imports:
            seen_imports.add(imp["name"])
            unique_imports.append(imp)

    seen_calls: set[str] = set()
    unique_calls = []
    for call in calls:
        if call["name"] not in seen_calls:
            seen_calls.add(call["name"])
            unique_calls.append(call)

    elapsed = (time.perf_counter() - start) * 1000

    return {
        "symbol_id": symbol_id,
        "symbol_name": symbol["name"],
        "file": target_file,
        "import_count": len(unique_imports),
        "call_count": len(unique_calls),
        "imports": unique_imports,
        "calls": unique_calls,
        "_meta": {"timing_ms": round(elapsed, 1)},
    }
