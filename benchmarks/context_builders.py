"""Context builders for NexusSymdex vs raw file benchmark comparison.

V3: Adaptive Multi-Strategy Context Assembly
- PRECISE: small files (<8K) → raw files + outline header + annotations + bridges
- ENRICHED: medium files (8-20K) → annotated raw + outline + bridges
- SURGICAL: large files (>20K) → outlines + targeted symbols + deps + bridges

Key insight: don't replace raw content — ENRICH it with NexusSymdex intelligence.
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
from nexus_symdex.tools.get_file_outline import get_file_outline
from nexus_symdex.tools.get_dependencies import get_dependencies

from benchmarks.classifier import classify_question, classify_file_strategy
from benchmarks.bridging import find_cross_references, format_bridges
from benchmarks.annotator import annotate_file

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
        sig = sym.get("signature", sym["name"])
        summary = f" -- {sym['summary']}" if sym.get("summary") else ""
        lines.append(f"  {sym['kind']} {sig}{summary} (L{sym['line']})")
        for child in sym.get("children", []):
            csig = child.get("signature", child["name"])
            csummary = f" -- {child['summary']}" if child.get("summary") else ""
            lines.append(f"    {child['kind']} {csig}{csummary} (L{child['line']})")
    return "\n".join(lines)


def _read_raw_file(basename: str, index, store) -> Optional[str]:
    """Read a raw file from the index content directory."""
    owner, name = "local", "click"
    content_dir = store._content_dir(owner, name)
    for sf in index.source_files:
        if Path(sf).name == basename:
            fpath = content_dir / sf
            if fpath.exists():
                return fpath.read_text(encoding="utf-8", errors="replace")
    return None


def _get_outline_header(basename: str, repo: str) -> str:
    """Get a compact file outline header."""
    outline = get_file_outline(repo, basename, storage_path=STORAGE_PATH)
    if "error" in outline or not outline.get("symbols"):
        return ""
    return f"### Structure of {basename}\n{_format_outline(outline)}"


# ---------------------------------------------------------------------------
# Strategy: PRECISE (raw < 8K tokens)
# Include raw files entirely + outline header + annotations + bridges
# Strictly better than raw: same content plus intelligence
# ---------------------------------------------------------------------------

def _strategy_precise(
    question: dict, repo: str, relevant_files: list[str],
    index, store, intent: str,
) -> str:
    """Raw files enriched with outlines, annotations, and cross-references."""
    sections = []

    for basename in relevant_files:
        # Outline header first
        header = _get_outline_header(basename, repo)
        if header:
            sections.append(header)

        # Annotated raw content
        raw = _read_raw_file(basename, index, store)
        if raw:
            annotated = annotate_file(repo, basename, raw,
                                      storage_path=STORAGE_PATH, max_annotations=15)
            sections.append(f"### {basename} (annotated source)\n```python\n{annotated}\n```")

    # Cross-file references
    if len(relevant_files) > 1:
        bridges = find_cross_references(repo, relevant_files, storage_path=STORAGE_PATH)
        bridge_text = format_bridges(bridges[:15])
        if bridge_text:
            sections.append(bridge_text)

    # For mechanism/change intents, add dependency context for key symbols
    if intent in ("mechanism", "change"):
        search_hints = question.get("search_hints", [])
        seen = set()
        dep_parts = []
        for hint in search_hints[:2]:
            result = search_symbols(repo, hint, max_results=2, storage_path=STORAGE_PATH)
            if "error" in result:
                continue
            for match in result.get("results", []):
                sym_id = match["id"]
                if sym_id in seen:
                    continue
                seen.add(sym_id)
                deps = get_dependencies(repo, sym_id, storage_path=STORAGE_PATH)
                if "error" in deps:
                    continue
                for call in deps.get("calls", [])[:2]:
                    tid = call.get("target_id", "")
                    if tid and tid not in seen:
                        seen.add(tid)
                        detail = get_symbol(repo, tid, storage_path=STORAGE_PATH)
                        if "error" not in detail and detail.get("source"):
                            dep_parts.append(
                                f"### {detail['kind']} {detail['name']} "
                                f"({detail['file']}:{detail['line']}) [dependency]\n"
                                f"```python\n{detail['source']}\n```"
                            )
        if dep_parts:
            sections.append("## Key Dependencies\n" + "\n\n".join(dep_parts))

    return "\n\n".join(sections) if sections else "(no context found)"


# ---------------------------------------------------------------------------
# Strategy: ENRICHED (raw 8K-20K tokens)
# Annotated raw files + outline headers + bridges
# Budget-aware: may trim least-relevant files if over budget
# ---------------------------------------------------------------------------

def _strategy_enriched(
    question: dict, repo: str, relevant_files: list[str],
    index, store, intent: str, raw_tokens: int,
) -> str:
    """Annotated raw with outlines and bridges.

    Intentionally uses more tokens than raw — the annotations and outlines
    are the intelligence layer that makes NexusSymdex strictly better.
    """
    sections = []

    for basename in relevant_files:
        # Outline header
        header = _get_outline_header(basename, repo)
        if header:
            sections.append(header)

        # Annotated raw content
        raw = _read_raw_file(basename, index, store)
        if raw:
            annotated = annotate_file(repo, basename, raw,
                                      storage_path=STORAGE_PATH, max_annotations=20)
            sections.append(f"### {basename} (annotated source)\n```python\n{annotated}\n```")

    # Cross-file references
    if len(relevant_files) > 1:
        bridges = find_cross_references(repo, relevant_files, storage_path=STORAGE_PATH)
        bridge_text = format_bridges(bridges[:15])
        if bridge_text:
            sections.append(bridge_text)

    return "\n\n".join(sections) if sections else "(no context found)"


# ---------------------------------------------------------------------------
# Strategy: SURGICAL (raw > 20K tokens)
# Outlines + targeted symbols + deps + bridges
# Most aggressive token savings
# ---------------------------------------------------------------------------

def _strategy_surgical(
    question: dict, repo: str, relevant_files: list[str],
    index, store, intent: str, raw_tokens: int,
) -> str:
    """Focused extraction with outlines, search hits, deps, and bridges."""
    sections = []
    search_hints = question.get("search_hints", [])
    budget = raw_tokens

    # 1. File outlines
    outline_parts = []
    for basename in relevant_files:
        header = _get_outline_header(basename, repo)
        if header:
            outline_parts.append(header)
    if outline_parts:
        sections.append("## File Structure\n" + "\n\n".join(outline_parts))

    # 2. Search for relevant symbols
    seen_ids: set[str] = set()
    hit_ids: list[str] = []
    sym_parts: list[str] = []

    # Adjust search depth by intent
    max_results = 5 if intent == "mechanism" else 3

    for hint in search_hints:
        result = search_symbols(repo, hint, max_results=max_results,
                                storage_path=STORAGE_PATH)
        if "error" in result:
            continue
        for match in result.get("results", []):
            sid = match["id"]
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            hit_ids.append(sid)
            detail = get_symbol(repo, sid, storage_path=STORAGE_PATH)
            if "error" not in detail and detail.get("source"):
                sym_parts.append(
                    f"### {detail['kind']} {detail['name']} "
                    f"({detail['file']}:{detail['line']})\n"
                    f"```python\n{detail['source']}\n```"
                )

    if sym_parts:
        sections.append("## Relevant Symbols\n" + "\n\n".join(sym_parts))

    # 3. Dependencies from top hits
    dep_parts = []
    for sid in hit_ids[:3]:
        deps = get_dependencies(repo, sid, storage_path=STORAGE_PATH)
        if "error" in deps:
            continue
        for call in deps.get("calls", [])[:3]:
            tid = call.get("target_id", "")
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                detail = get_symbol(repo, tid, storage_path=STORAGE_PATH)
                if "error" not in detail and detail.get("source"):
                    dep_parts.append(
                        f"### {detail['kind']} {detail['name']} "
                        f"({detail['file']}:{detail['line']}) [dependency]\n"
                        f"```python\n{detail['source']}\n```"
                    )
    if dep_parts:
        sections.append("## Dependencies\n" + "\n\n".join(dep_parts))

    # 4. Cross-file references
    if len(relevant_files) > 1:
        bridges = find_cross_references(repo, relevant_files, storage_path=STORAGE_PATH)
        bridge_text = format_bridges(bridges[:15])
        if bridge_text:
            sections.append(bridge_text)

    # 5. Smart context to fill remaining budget
    current = "\n\n".join(sections)
    remaining = budget - count_tokens(current)
    if remaining > 500:
        focus = search_hints[0] if search_hints else question.get("question", "")
        ctx = get_context(repo, budget_tokens=min(remaining, 4000),
                          focus=focus, include_deps=True,
                          storage_path=STORAGE_PATH)
        if "error" not in ctx:
            extra = []
            for sym in ctx.get("symbols", []):
                sid = sym["id"]
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                source = sym.get("source", "")
                if source:
                    tag = f" [{sym['context_type']}]" if "context_type" in sym else ""
                    extra.append(
                        f"### {sym['kind']} {sym['name']} "
                        f"({sym['file']}:{sym['line']}){tag}\n"
                        f"```python\n{source}\n```"
                    )
            if extra:
                sections.append("## Additional Context\n" + "\n\n".join(extra))

    # Budget enforcement
    text = "\n\n".join(sections)
    while count_tokens(text) > budget and len(sections) > 1:
        sections.pop()
        text = "\n\n".join(sections)

    return text if text else "(no context found)"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_symdex_context(question: dict, repo: str = REPO) -> tuple[str, int]:
    """Build context using adaptive multi-strategy assembly (v3).

    1. Classify question intent (location/mechanism/change)
    2. Compute raw file size to select strategy (precise/enriched/surgical)
    3. Build context using the selected strategy
    4. All strategies include NexusSymdex intelligence (outlines, annotations,
       cross-references) on top of the most complete raw content the budget allows

    Returns:
        (context_string, token_count)
    """
    relevant_files = question.get("relevant_files", [])
    intent = classify_question(question)

    # Load index once for shared use
    store = IndexStore(base_path=STORAGE_PATH)
    index = store.load_index("local", "click")

    # Compute raw context size for strategy selection
    raw_ctx, raw_tokens = build_raw_context(question, repo)
    strategy = classify_file_strategy(raw_tokens)

    if strategy == "precise":
        context = _strategy_precise(question, repo, relevant_files, index, store, intent)
    elif strategy == "enriched":
        context = _strategy_enriched(question, repo, relevant_files,
                                     index, store, intent, raw_tokens)
    else:
        context = _strategy_surgical(question, repo, relevant_files,
                                     index, store, intent, raw_tokens)

    tokens = count_tokens(context)
    return context, tokens


def build_raw_context(question: dict, repo: str = REPO) -> tuple[str, int]:
    """Build context by reading full files listed in the question.

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
