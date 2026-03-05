"""Search symbols across all indexed repositories."""

import time
from typing import Optional

from ..storage import IndexStore, score_symbol, record_savings, estimate_savings, cost_avoided


def search_all_repos(
    query: str,
    kind: Optional[str] = None,
    language: Optional[str] = None,
    max_results: int = 20,
    storage_path: Optional[str] = None,
) -> dict:
    """Search symbols across ALL indexed repositories.

    Args:
        query: Search query (matches symbol names, signatures, summaries, docstrings).
        kind: Optional filter by symbol kind.
        language: Optional filter by language.
        max_results: Maximum results to return (clamped to 1..100).
        storage_path: Custom storage path.

    Returns:
        Dict with combined search results and _meta envelope.
    """
    start = time.perf_counter()
    max_results = max(1, min(max_results, 100))

    store = IndexStore(base_path=storage_path)
    repos = store.list_repos()

    if not repos:
        return {"error": "No indexed repositories found."}

    query_lower = query.lower()
    query_words = set(query_lower.split())

    all_scored = []
    total_symbols = 0
    repos_searched = 0

    for repo_info in repos:
        repo_id = repo_info["repo"]
        owner, name = repo_id.split("/", 1)
        index = store.load_index(owner, name)
        if not index:
            continue

        repos_searched += 1
        total_symbols += len(index.symbols)

        results = index.search(query, kind=kind)

        if language:
            results = [s for s in results if s.get("language") == language]

        for sym in results:
            score = score_symbol(sym, query_lower, query_words)
            if score > 0:
                all_scored.append({
                    "repo": repo_id,
                    "id": sym["id"],
                    "kind": sym["kind"],
                    "name": sym["name"],
                    "file": sym["file"],
                    "line": sym["line"],
                    "signature": sym["signature"],
                    "summary": sym.get("summary", ""),
                    "score": score,
                })

    # Sort by score descending, truncate
    all_scored.sort(key=lambda x: x["score"], reverse=True)
    truncated = len(all_scored) > max_results
    results_out = all_scored[:max_results]

    # Estimate token savings: sum byte_length of returned symbols vs raw file sizes
    # (simplified: use byte_length from symbols as response size proxy)
    response_bytes = 0
    for item in results_out:
        # Look up the original symbol to get byte_length
        repo_id = item["repo"]
        owner, name = repo_id.split("/", 1)
        idx = store.load_index(owner, name)
        if idx:
            sym = idx.get_symbol(item["id"])
            if sym:
                response_bytes += sym.get("byte_length", 0)

    # Rough estimate: assume each file is ~2KB on average
    raw_bytes = response_bytes * 3 if response_bytes else 0
    tokens_saved = estimate_savings(raw_bytes, response_bytes)
    total_saved = record_savings(tokens_saved)

    elapsed = (time.perf_counter() - start) * 1000

    return {
        "query": query,
        "result_count": len(results_out),
        "repos_searched": repos_searched,
        "results": results_out,
        "_meta": {
            "timing_ms": round(elapsed, 1),
            "total_symbols_scanned": total_symbols,
            "truncated": truncated,
            "tokens_saved": tokens_saved,
            "total_tokens_saved": total_saved,
            **cost_avoided(tokens_saved, total_saved),
        },
    }
