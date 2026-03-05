"""Smart context budgeting tool."""

import time
from typing import Optional

from ..storage import IndexStore, CodeIndex, score_symbol, record_savings, estimate_savings, cost_avoided
from ._utils import resolve_repo


def get_context(
    repo: str,
    budget_tokens: int = 4000,
    focus: Optional[str] = None,
    kind: Optional[str] = None,
    storage_path: Optional[str] = None,
) -> dict:
    """Get the most relevant symbols that fit within a token budget.

    Args:
        repo: Repository identifier (owner/repo or just repo name).
        budget_tokens: Max tokens to include (default 4000).
        focus: Optional search query to focus context on.
        kind: Optional symbol kind filter.
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

    # Greedily fill budget
    symbols_out = []
    tokens_used = 0
    raw_bytes_total = 0

    for sym in candidates:
        byte_length = sym.get("byte_length", 0)
        estimated_tokens = byte_length // 4  # ~4 bytes per token
        if estimated_tokens == 0:
            estimated_tokens = 1

        if tokens_used + estimated_tokens > budget_tokens:
            continue  # Skip this one, try smaller ones

        # Retrieve source content
        source = store.get_symbol_content(owner, name, sym["id"])
        if source is None:
            continue

        tokens_used += estimated_tokens
        raw_bytes_total += byte_length

        symbols_out.append({
            "id": sym["id"],
            "kind": sym["kind"],
            "name": sym["name"],
            "file": sym["file"],
            "line": sym["line"],
            "signature": sym["signature"],
            "summary": sym.get("summary", ""),
            "source": source,
            "estimated_tokens": estimated_tokens,
        })

    # Token savings
    tokens_saved = estimate_savings(raw_bytes_total * 3, raw_bytes_total)
    total_saved = record_savings(tokens_saved)

    elapsed = (time.perf_counter() - start) * 1000

    return {
        "repo": f"{owner}/{name}",
        "symbols_included": len(symbols_out),
        "symbols": symbols_out,
        "_meta": {
            "timing_ms": round(elapsed, 1),
            "tokens_used": tokens_used,
            "tokens_budget": budget_tokens,
            "budget_utilization": round(tokens_used / budget_tokens * 100, 1) if budget_tokens else 0,
            "total_symbols_available": len(index.symbols),
            "tokens_saved": tokens_saved,
            "total_tokens_saved": total_saved,
            **cost_avoided(tokens_saved, total_saved),
        },
    }
