"""Context builders for NexusSymdex vs raw file benchmark comparison.

Two strategies:
- symdex: uses search, get_symbol, get_context, and architecture map for focused context
- raw: reads full file contents for all relevant files
"""

import sys
from pathlib import Path
from typing import Optional

# Add NexusSymdex src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import tiktoken

from nexus_symdex.storage import IndexStore
from nexus_symdex.tools.search_symbols import search_symbols
from nexus_symdex.tools.get_symbol import get_symbol
from nexus_symdex.tools.get_context import get_context
from nexus_symdex.tools.get_architecture_map import get_architecture_map
from nexus_symdex.tools.get_file_outline import get_file_outline
from nexus_symdex.tools.get_dependencies import get_dependencies

STORAGE_PATH = str(Path(__file__).parent / "repos" / ".click-index")
REPO = "local/click"

_enc = tiktoken.encoding_for_model("gpt-4")


def count_tokens(text: str) -> int:
    """Count tokens using the GPT-4 tokenizer."""
    return len(_enc.encode(text))


def _format_outline(outline: dict) -> str:
    """Format a file outline into a compact string."""
    lines = []
    for sym in outline.get("symbols", []):
        indent = ""
        sig = sym.get("signature", sym["name"])
        summary = f" — {sym['summary']}" if sym.get("summary") else ""
        lines.append(f"  {sym['kind']} {sig}{summary} (L{sym['line']})")
        for child in sym.get("children", []):
            csig = child.get("signature", child["name"])
            csummary = f" — {child['summary']}" if child.get("summary") else ""
            lines.append(f"    {child['kind']} {csig}{csummary} (L{child['line']})")
    return "\n".join(lines)


def build_symdex_context(question: dict, repo: str = REPO) -> tuple[str, int]:
    """Build focused context using NexusSymdex tools.

    Improved strategy (v2):
    1. File outlines for all relevant files (cheap, shows full structure)
    2. Search for symbols using search_hints, get full source
    3. Follow dependencies from top search hits (callers/deps)
    4. Smart context for broader understanding
    5. Token budget cap: never exceed raw file context size

    Returns:
        (context_string, token_count)
    """
    sections: list[str] = []
    search_hints = question.get("search_hints", [])
    relevant_files = question.get("relevant_files", [])

    # Compute raw context size as budget cap
    raw_ctx, raw_tokens = build_raw_context(question, repo)
    token_budget = raw_tokens  # never exceed what raw files would cost

    # Scale search depth based on budget: small files need fewer search hits
    max_search_results = 5 if token_budget > 10000 else 3 if token_budget > 5000 else 2
    max_dep_targets = 3 if token_budget > 10000 else 1

    # --- 1. File outlines for relevant files (cheap, high signal) ---
    outlined_files: set[str] = set()
    outline_parts: list[str] = []
    for basename in relevant_files:
        outline = get_file_outline(repo, basename, storage_path=STORAGE_PATH)
        if "error" not in outline and outline.get("symbols"):
            outlined_files.add(basename)
            formatted = _format_outline(outline)
            outline_parts.append(f"### {basename}\n{formatted}")
    if outline_parts:
        sections.append("## File Structure\n" + "\n\n".join(outline_parts))

    # --- 2. Search for relevant symbols, get full source ---
    seen_symbol_ids: set[str] = set()
    search_hit_ids: list[str] = []  # ordered list for dependency tracing
    symbol_sources: list[str] = []

    for hint in search_hints:
        result = search_symbols(
            repo, hint, max_results=max_search_results, storage_path=STORAGE_PATH
        )
        if "error" in result:
            continue
        for match in result.get("results", []):
            sym_id = match["id"]
            if sym_id in seen_symbol_ids:
                continue
            seen_symbol_ids.add(sym_id)
            search_hit_ids.append(sym_id)

            sym_detail = get_symbol(repo, sym_id, storage_path=STORAGE_PATH)
            if "error" in sym_detail:
                continue
            source = sym_detail.get("source", "")
            if source:
                header = f"### {sym_detail['kind']} {sym_detail['name']} ({sym_detail['file']}:{sym_detail['line']})"
                symbol_sources.append(f"{header}\n```python\n{source}\n```")

    if symbol_sources:
        sections.append("## Relevant Symbols\n" + "\n\n".join(symbol_sources))

    # --- 3. Follow dependencies from top search hits ---
    dep_parts: list[str] = []
    for sym_id in search_hit_ids[:2]:  # top 2 hits only
        deps = get_dependencies(repo, sym_id, storage_path=STORAGE_PATH)
        if "error" in deps:
            continue
        # Get source for called symbols that we haven't seen
        for call in deps.get("calls", [])[:max_dep_targets]:
            target_id = call.get("target_id", "")
            if not target_id or target_id in seen_symbol_ids:
                continue
            seen_symbol_ids.add(target_id)
            sym_detail = get_symbol(repo, target_id, storage_path=STORAGE_PATH)
            if "error" in sym_detail:
                continue
            source = sym_detail.get("source", "")
            if source:
                header = f"### {sym_detail['kind']} {sym_detail['name']} ({sym_detail['file']}:{sym_detail['line']}) [dependency]"
                dep_parts.append(f"{header}\n```python\n{source}\n```")

    if dep_parts:
        sections.append("## Dependencies\n" + "\n\n".join(dep_parts))

    # --- 4. Smart context for broader understanding ---
    # Only add if we're still under budget
    current_text = "\n\n".join(sections) if sections else ""
    current_tokens = count_tokens(current_text) if current_text else 0
    remaining_budget = token_budget - current_tokens

    if remaining_budget > 500:
        focus_query = search_hints[0] if search_hints else question.get("question", "")
        ctx_budget = min(remaining_budget, 4000)
        ctx = get_context(
            repo,
            budget_tokens=ctx_budget,
            focus=focus_query,
            include_deps=True,
            storage_path=STORAGE_PATH,
        )
        if "error" not in ctx:
            ctx_parts: list[str] = []
            for sym in ctx.get("symbols", []):
                sym_id = sym["id"]
                if sym_id in seen_symbol_ids:
                    continue
                seen_symbol_ids.add(sym_id)
                source = sym.get("source", "")
                if source:
                    tag = f" [{sym['context_type']}]" if "context_type" in sym else ""
                    header = f"### {sym['kind']} {sym['name']} ({sym['file']}:{sym['line']}){tag}"
                    ctx_parts.append(f"{header}\n```python\n{source}\n```")
            if ctx_parts:
                sections.append("## Additional Context\n" + "\n\n".join(ctx_parts))

    # --- 5. Enforce token budget cap ---
    context_string = "\n\n".join(sections) if sections else "(no context found)"
    tokens = count_tokens(context_string)

    # If over budget, trim from the end (keep at least file outlines)
    while tokens > token_budget and len(sections) > 1:
        sections.pop()
        context_string = "\n\n".join(sections)
        tokens = count_tokens(context_string)

    return context_string, tokens


def build_raw_context(question: dict, repo: str = REPO) -> tuple[str, int]:
    """Build context by reading full files listed in the question.

    Strategy:
    1. Load index from IndexStore
    2. For each file in question's relevant_files, find matching source file
    3. Read full file content from the content directory
    4. Return combined context

    Returns:
        (context_string, token_count)
    """
    owner, name = repo.split("/", 1)
    store = IndexStore(base_path=STORAGE_PATH)
    index = store.load_index(owner, name)

    if not index:
        return "(index not found)", 0

    relevant_basenames = question.get("relevant_files", [])
    content_dir = store._content_dir(owner, name)

    sections: list[str] = []
    for basename in relevant_basenames:
        # Match basename against indexed source_files
        matched: Optional[str] = None
        for sf in index.source_files:
            if Path(sf).name == basename:
                matched = sf
                break

        if not matched:
            continue

        file_path = content_dir / matched
        if not file_path.exists():
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        sections.append(f"## {matched}\n```python\n{content}\n```")

    context_string = "\n\n".join(sections) if sections else "(no files found)"
    tokens = count_tokens(context_string)
    return context_string, tokens
