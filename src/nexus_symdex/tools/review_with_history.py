"""PR review context enriched with historical memory from NexusCortex."""

import asyncio
import os
import re
import time
from typing import Optional

from ..cortex import CortexClient
from .get_review_context import get_review_context
from .get_architecture_map import get_architecture_map

_cortex = CortexClient()

_WARNING_PATTERN = re.compile(
    r"\b(regression|bug|broke|failed|revert)\b",
    re.IGNORECASE,
)


async def review_with_history(
    repo: str,
    changed_files: list[str],
    budget_tokens: int = 8000,
    storage_path: Optional[str] = None,
) -> dict:
    """Assemble PR review context and enrich it with historical memory.

    Combines NexusSymdex's structural review context (changed symbols,
    callers, dependencies, tests) with NexusCortex's per-file historical
    insights.  When Cortex is unavailable, the standard review context is
    still returned — history sections are simply empty.

    Args:
        repo: Repository identifier (owner/repo or just repo name).
        changed_files: List of file paths that changed.
        budget_tokens: Max tokens for the structural review context.
        storage_path: Custom storage path for the index store.

    Returns:
        Dict with review sections, per-file history, warnings, and metadata.
    """
    start = time.perf_counter()

    # 1. Standard review context (synchronous call)
    review = get_review_context(repo, changed_files, budget_tokens, storage_path)
    if "error" in review:
        return review

    cortex_available = _cortex.is_available

    # 2. Recall historical context per file (parallel)
    history: dict[str, dict] = {}
    if cortex_available:
        repo_name = review.get("repo", repo).split("/")[-1]

        async def _recall_file(filepath: str) -> tuple[str, dict]:
            basename = os.path.basename(filepath)
            task = f"Previous changes to {basename} in {repo_name}"
            result = await _cortex.recall(
                task=task,
                tags=[basename, repo_name],
                top_k=3,
            )
            context_block = result.get("context_block", "")
            has_history = bool(context_block) and "error" not in result
            return filepath, {
                "context_block": context_block if has_history else "",
                "has_history": has_history,
            }

        recall_results = await asyncio.gather(
            *[_recall_file(f) for f in changed_files],
            return_exceptions=True,
        )
        for item in recall_results:
            if isinstance(item, Exception):
                continue
            filepath, file_history = item
            history[filepath] = file_history
    else:
        for f in changed_files:
            history[f] = {"context_block": "", "has_history": False}

    # 3. Fire-and-forget architecture snapshot to Cortex
    if cortex_available:
        try:
            arch_map = get_architecture_map(repo, storage_path)
            if "error" not in arch_map:
                repo_tag = review.get("repo", repo)
                asyncio.create_task(_stream_architecture(arch_map, repo_tag))
        except Exception:
            pass

    # 4. Generate warnings from historical context
    warnings = _extract_warnings(history)

    # 5. Assemble response
    elapsed = (time.perf_counter() - start) * 1000
    files_with_history = sum(1 for h in history.values() if h.get("has_history"))

    return {
        "repo": review["repo"],
        "changed_files": changed_files,
        "review": review.get("sections", {}),
        "history": history,
        "warnings": warnings,
        "related_test_files": review.get("related_test_files", []),
        "_meta": {
            "timing_ms": round(elapsed, 1),
            "tokens_used": review.get("_meta", {}).get("tokens_used", 0),
            "cortex_available": cortex_available,
            "files_with_history": files_with_history,
        },
    }


async def _stream_architecture(arch_map: dict, repo_tag: str) -> None:
    """Stream architecture snapshot to Cortex. Exceptions are silenced."""
    try:
        await _cortex.stream(
            source="nexus-symdex:architecture",
            payload=arch_map,
            tags=[repo_tag],
        )
    except Exception:
        pass


def _extract_warnings(history: dict[str, dict]) -> list[str]:
    """Scan historical context blocks for warning-worthy keywords."""
    warnings = []
    for filepath, info in history.items():
        context = info.get("context_block", "")
        if not context:
            continue
        match = _WARNING_PATTERN.search(context)
        if match:
            keyword = match.group(0).lower()
            basename = os.path.basename(filepath)
            warnings.append(
                f"{filepath}: Previous changes mention '{keyword}' (see history for {basename})"
            )
    return warnings
