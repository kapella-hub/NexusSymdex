"""Smart context budgeting tool."""

import time
from typing import Optional

from ..storage import IndexStore, CodeIndex, score_symbol, record_savings, estimate_savings, cost_avoided
from ._utils import resolve_repo, resolve_call_targets


def _find_dependency_ids(index, symbol_id: str) -> list[str]:
    """Find symbol IDs of direct dependencies (callees) for a given symbol.

    Looks at call references within the symbol's line range, then resolves
    each callee name to an actual symbol in the index.
    """
    symbol = index.get_symbol(symbol_id)
    if not symbol:
        return []

    target_file = symbol["file"]
    sym_start = symbol["line"]
    sym_end = symbol["end_line"]

    callee_names = set()
    for ref in index.references:
        if ref.get("type") != "call":
            continue
        if ref.get("file") != target_file:
            continue
        ref_line = ref.get("line", 0)
        if sym_start <= ref_line <= sym_end:
            callee_names.add(ref.get("name", ""))

    # Resolve each callee name with scope awareness
    dep_ids = []
    seen: set[str] = set()
    for callee_name in callee_names:
        targets = resolve_call_targets(index, callee_name, target_file)
        for tid in targets:
            if tid != symbol_id and tid not in seen:
                seen.add(tid)
                dep_ids.append(tid)
                break  # Take best match only

    return dep_ids


def _find_file_imports(index, file_path: str) -> list[str]:
    """Find import symbol IDs for a given file.

    Looks at import references for the file, resolves imported names
    to symbols in other files.
    """
    import_names = set()
    for ref in index.references:
        if ref.get("type") != "import" or ref.get("file") != file_path:
            continue
        import_names.add(ref.get("name", ""))

    # Resolve import names to symbols (heuristic: match by name or module)
    dep_ids = []
    for sym in index.symbols:
        if sym.get("file") == file_path:
            continue  # skip same file
        name = sym.get("name", "")
        qname = sym.get("qualified_name", "")
        for imp in import_names:
            if name == imp or imp.endswith(f".{name}") or qname == imp:
                dep_ids.append(sym["id"])
                break

    return dep_ids


def get_context(
    repo: str,
    budget_tokens: int = 4000,
    focus: Optional[str] = None,
    kind: Optional[str] = None,
    include_deps: bool = False,
    storage_path: Optional[str] = None,
) -> dict:
    """Get the most relevant symbols that fit within a token budget.

    Args:
        repo: Repository identifier (owner/repo or just repo name).
        budget_tokens: Max tokens to include (default 4000).
        focus: Optional search query to focus context on.
        kind: Optional symbol kind filter.
        include_deps: When True and focus is set, also include direct
            dependencies (callees and imports) of the focused symbols.
        storage_path: Custom storage path.

    Returns:
        Dict with symbols (including source), plus _meta with budget info.
    """
    start = time.perf_counter()
    budget_tokens = max(100, min(budget_tokens, 100_000))

    try:
        owner, name = resolve_repo(repo, storage_path)
    except ValueError as e:
        return {"error": str(e)}

    store = IndexStore(base_path=storage_path)
    index = store.load_index(owner, name)

    if not index:
        return {"error": f"Repository not indexed: {owner}/{name}"}

    # Get candidate symbols
    if focus:
        candidates = index.search(focus, kind=kind)
        # Score and sort by relevance
        query_lower = focus.lower()
        query_words = set(query_lower.split())
        candidates = sorted(
            candidates,
            key=lambda s: score_symbol(s, query_lower, query_words),
            reverse=True,
        )
    else:
        # No focus: use all symbols, prefer smaller ones (more informative per token)
        candidates = list(index.symbols)
        if kind:
            candidates = [s for s in candidates if s.get("kind") == kind]
        candidates.sort(key=lambda s: s.get("byte_length", 0))

    # Helper to add a symbol to the output
    def _try_add(sym, tag=None):
        nonlocal tokens_used, raw_bytes_total
        byte_length = sym.get("byte_length", 0)
        estimated_tokens = byte_length // 4 or 1

        if tokens_used + estimated_tokens > budget_tokens:
            return False

        source = store.get_symbol_content(owner, name, sym["id"])
        if source is None:
            return False

        tokens_used += estimated_tokens
        raw_bytes_total += byte_length

        entry = {
            "id": sym["id"],
            "kind": sym["kind"],
            "name": sym["name"],
            "file": sym["file"],
            "line": sym["line"],
            "signature": sym["signature"],
            "summary": sym.get("summary", ""),
            "source": source,
            "estimated_tokens": estimated_tokens,
        }
        if tag:
            entry["context_type"] = tag
        symbols_out.append(entry)
        return True

    # Greedily fill budget
    symbols_out = []
    tokens_used = 0
    raw_bytes_total = 0
    included_ids = set()
    deps_included = 0

    for sym in candidates:
        if sym["id"] in included_ids:
            continue
        if _try_add(sym):
            included_ids.add(sym["id"])

            # When include_deps is on, also add direct dependencies
            if include_deps and focus:
                dep_ids = _find_dependency_ids(index, sym["id"])
                dep_ids += _find_file_imports(index, sym["file"])
                for dep_id in dep_ids:
                    if dep_id in included_ids:
                        continue
                    dep_sym = index.get_symbol(dep_id)
                    if dep_sym and _try_add(dep_sym, tag="dependency"):
                        included_ids.add(dep_id)
                        deps_included += 1

    # Token savings
    tokens_saved = estimate_savings(raw_bytes_total * 3, raw_bytes_total)
    total_saved = record_savings(tokens_saved)

    elapsed = (time.perf_counter() - start) * 1000

    meta = {
        "timing_ms": round(elapsed, 1),
        "tokens_used": tokens_used,
        "tokens_budget": budget_tokens,
        "budget_utilization": round(tokens_used / budget_tokens * 100, 1) if budget_tokens else 0,
        "total_symbols_available": len(index.symbols),
        "tokens_saved": tokens_saved,
        "total_tokens_saved": total_saved,
        **cost_avoided(tokens_saved, total_saved),
    }
    if include_deps:
        meta["deps_included"] = deps_included

    return {
        "repo": f"{owner}/{name}",
        "symbols_included": len(symbols_out),
        "symbols": symbols_out,
        "_meta": meta,
    }
