"""Shared helpers for tool modules."""

from collections import Counter
from typing import Optional

from ..parser.symbols import Symbol
from ..storage import IndexStore


def resolve_repo(repo: str, storage_path: Optional[str] = None) -> tuple[str, str]:
    """Parse 'owner/repo' or look up single name. Returns (owner, name).

    Raises ValueError if repo not found.
    """
    if "/" in repo:
        return repo.split("/", 1)
    store = IndexStore(base_path=storage_path)
    repos = store.list_repos()
    matching = [r for r in repos if r["repo"].endswith(f"/{repo}")]
    if not matching:
        raise ValueError(f"Repository not found: {repo}")
    return matching[0]["repo"].split("/", 1)


def generate_file_summaries(symbols: list[Symbol]) -> dict[str, str]:
    """Generate one-line summaries per file from symbol data.

    Example output: "3 functions, 2 classes: MyClass, helper, process_data"
    """
    # Group symbols by file
    by_file: dict[str, list[Symbol]] = {}
    for sym in symbols:
        by_file.setdefault(sym.file, []).append(sym)

    summaries = {}
    for file_path, file_syms in by_file.items():
        # Count kinds
        kind_counts: Counter[str] = Counter()
        names = []
        for sym in file_syms:
            kind_counts[sym.kind] += 1
            # Only include top-level symbol names (no parent)
            if not sym.parent:
                names.append(sym.name)

        # Build kind string: "3 functions, 2 classes"
        kind_parts = []
        for kind in ["class", "function", "method", "type", "constant"]:
            count = kind_counts.get(kind, 0)
            if count:
                label = kind + ("es" if kind == "class" else "s") if count > 1 else kind
                kind_parts.append(f"{count} {label}")

        kind_str = ", ".join(kind_parts)
        # Append top-level names (limit to 5)
        if names:
            name_str = ", ".join(names[:5])
            if len(names) > 5:
                name_str += f" (+{len(names) - 5} more)"
            summaries[file_path] = f"{kind_str}: {name_str}" if kind_str else name_str
        elif kind_str:
            summaries[file_path] = kind_str

    return summaries
