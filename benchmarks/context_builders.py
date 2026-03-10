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

STORAGE_PATH = str(Path(__file__).parent / "repos" / ".click-index")
REPO = "local/click"

_enc = tiktoken.encoding_for_model("gpt-4")


def count_tokens(text: str) -> int:
    """Count tokens using the GPT-4 tokenizer."""
    return len(_enc.encode(text))


def build_symdex_context(question: dict, repo: str = REPO) -> tuple[str, int]:
    """Build focused context using NexusSymdex tools.

    Strategy:
    1. Get architecture overview for file-level context
    2. Search for relevant symbols using search_hints
    3. Get full source for top matches via get_symbol
    4. Get smart context via get_context with include_deps=True
    5. Combine into a single context string

    Returns:
        (context_string, token_count)
    """
    sections: list[str] = []

    # 1. Architecture overview (cheap, gives file-level context)
    arch = get_architecture_map(repo, storage_path=STORAGE_PATH)
    if "error" not in arch:
        arch_lines = ["## Architecture Overview"]
        for layer_name, layer_info in arch.get("layers", {}).items():
            files = layer_info.get("files", [])
            desc = layer_info.get("description", "")
            if files:
                file_list = ", ".join(files[:10])
                arch_lines.append(f"- **{layer_name}**: {file_list} ({desc})")
        sections.append("\n".join(arch_lines))

    # 2. Search for relevant symbols using search_hints
    seen_symbol_ids: set[str] = set()
    search_hints = question.get("search_hints", [])
    symbol_sources: list[str] = []

    for hint in search_hints:
        result = search_symbols(
            repo, hint, max_results=5, storage_path=STORAGE_PATH
        )
        if "error" in result:
            continue
        for match in result.get("results", []):
            sym_id = match["id"]
            if sym_id in seen_symbol_ids:
                continue
            seen_symbol_ids.add(sym_id)

            # 3. Get full source for top matches
            sym_detail = get_symbol(repo, sym_id, storage_path=STORAGE_PATH)
            if "error" in sym_detail:
                continue
            source = sym_detail.get("source", "")
            if source:
                header = f"### {sym_detail['kind']} {sym_detail['name']} ({sym_detail['file']}:{sym_detail['line']})"
                symbol_sources.append(f"{header}\n```python\n{source}\n```")

    if symbol_sources:
        sections.append("## Relevant Symbols\n" + "\n\n".join(symbol_sources))

    # 4. Get smart context with dependencies
    focus_query = " ".join(search_hints) if search_hints else question.get("question", "")
    ctx = get_context(
        repo,
        budget_tokens=4000,
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

    context_string = "\n\n".join(sections) if sections else "(no context found)"
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
