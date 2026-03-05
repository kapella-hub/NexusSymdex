# Architecture

## Directory Structure

```
NexusSymdex/
├── pyproject.toml
├── README.md
├── SECURITY.md
├── SPEC.md
├── LANGUAGE_SUPPORT.md
├── TOKEN_SAVINGS.md
├── USER_GUIDE.md
│
├── src/nexus_symdex/
│   ├── __init__.py
│   ├── server.py                    # MCP server: 18 tool definitions + dispatch
│   ├── security.py                  # Path traversal, symlink, secret, binary detection
│   │
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── symbols.py               # Symbol dataclass, ID generation, hashing
│   │   ├── extractor.py             # tree-sitter AST walking + symbol extraction
│   │   ├── languages.py             # LanguageSpec registry (7 languages)
│   │   ├── hierarchy.py             # SymbolNode tree building for file outlines
│   │   └── references.py            # Import and call-site extraction from ASTs
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── index_store.py           # CodeIndex, IndexStore: save/load, incremental indexing
│   │   └── token_tracker.py         # Persistent token savings counter (~/.code-index/_savings.json)
│   │
│   ├── summarizer/
│   │   ├── __init__.py
│   │   └── batch_summarize.py       # Docstring → AI → signature fallback
│   │
│   └── tools/
│       ├── __init__.py
│       ├── _utils.py                # Shared helpers (resolve_repo)
│       ├── index_repo.py            # GitHub repository indexing
│       ├── index_folder.py          # Local folder indexing
│       ├── list_repos.py            # List all indexed repos
│       ├── get_file_tree.py         # File structure tree
│       ├── get_file_outline.py      # Symbol hierarchy for a file
│       ├── get_symbol.py            # Retrieve symbol source (single + batch)
│       ├── search_symbols.py        # Weighted symbol search
│       ├── search_text.py           # Full-text content search
│       ├── get_repo_outline.py      # High-level repo overview
│       ├── invalidate_cache.py      # Delete cached index
│       ├── search_all_repos.py      # Cross-repo symbol search
│       ├── get_context.py           # Token-budget-aware context retrieval
│       ├── explain_symbol.py        # LLM-powered symbol explanation
│       ├── get_callers.py           # Find call sites for a symbol
│       ├── get_dependencies.py      # Find what a symbol calls/imports
│       └── watch_folder.py          # File watching with auto-reindex
│
├── tests/
│   ├── fixtures/
│   ├── test_parser.py
│   ├── test_languages.py
│   ├── test_storage.py
│   ├── test_summarizer.py
│   ├── test_tools.py
│   ├── test_server.py
│   ├── test_security.py
│   └── test_hardening.py
│
└── .github/workflows/
    ├── test.yml
    └── benchmark.yml
```

---

## Data Flow

```
Source code (GitHub API or local folder)
    │
    ▼
Security filters (path traversal, symlinks, secrets, binary, size)
    │
    ▼
tree-sitter parsing (language-specific grammars via LanguageSpec)
    │
    ├──▶ Symbol extraction (functions, classes, methods, constants, types)
    │        │
    │        ▼
    │    Post-processing (overload disambiguation, content hashing)
    │        │
    │        ▼
    │    Summarization (docstring → AI batch → signature fallback)
    │
    └──▶ Reference extraction (imports and call sites per file)
    │
    ▼
Storage (JSON index + raw files, atomic writes)
    │
    ▼
MCP tools (discovery, search, retrieval, call graph, explanations)
```

---

## Parser Design

The parser follows a **language registry pattern**. Each supported language defines a `LanguageSpec` describing how symbols are extracted from its AST.

```python
@dataclass
class LanguageSpec:
    ts_language: str
    symbol_node_types: dict[str, str]
    name_fields: dict[str, str]
    param_fields: dict[str, str]
    return_type_fields: dict[str, str]
    docstring_strategy: str
    decorator_node_type: str | None
    container_node_types: list[str]
    constant_patterns: list[str]
    type_patterns: list[str]
```

The generic extractor performs two post-processing passes:

1. **Overload disambiguation**
   Duplicate symbol IDs receive numeric suffixes (`~1`, `~2`, etc.)

2. **Content hashing**
   SHA-256 hashes of symbol source content enable change detection.

### Reference Extraction

The `references.py` module extracts import and call references from source code using tree-sitter. Each reference records:

- **Type** — `import` or `call`
- **Name** — the imported module or called function
- **Line** — source location
- **From symbol** — the containing symbol (populated by downstream tools)

References enable `get_callers` and `get_dependencies` to trace call graphs without requiring a full language server.

---

## Symbol ID Scheme

```
{file_path}::{qualified_name}#{kind}
```

Examples:

* `src/main.py::UserService.login#method`
* `src/utils.py::authenticate#function`
* `config.py::MAX_RETRIES#constant`

IDs remain stable across re-indexing as long as the file path, qualified name, and symbol kind remain unchanged.

---

## Storage

Indexes are stored at `~/.code-index/` (configurable via `CODE_INDEX_PATH`):

* `{owner}-{name}.json` — metadata, file hashes, symbol metadata, references
* `{owner}-{name}/` — cached raw source files

Each symbol records byte offsets, allowing **O(1)** retrieval via `seek()` + `read()` without re-parsing.

Incremental indexing compares stored file hashes with current hashes, reprocessing only changed files. Writes are atomic (temporary file + rename).

---

## Security

All file operations pass through `security.py`:

* Path traversal protection via validated resolved paths
* Symlink target validation
* Secret-file exclusion using predefined patterns
* Binary file detection
* Safe encoding reads using `errors="replace"`

---

## Response Envelope

All tool responses include metadata:

```json
{
  "result": "...",
  "_meta": {
    "timing_ms": 42,
    "repo": "owner/repo",
    "symbol_count": 387,
    "truncated": false,
    "tokens_saved": 2450,
    "total_tokens_saved": 184320,
    "cost_avoided": { "claude_opus": 0.0612, "gpt5_latest": 0.0245 },
    "total_cost_avoided": { "claude_opus": 4.61, "gpt5_latest": 1.84 }
  }
}
```

`tokens_saved` and `total_tokens_saved` are included on all retrieval and search tools. The running total is persisted to `~/.code-index/_savings.json` across sessions.

---

## Search Algorithm

`search_symbols` uses weighted scoring:

| Match type              | Weight                |
| ----------------------- | --------------------- |
| Exact name match        | +20                   |
| Name substring          | +10                   |
| Name word overlap       | +5 per word           |
| Signature match         | +8 (full) / +2 (word) |
| Summary match           | +5 (full) / +1 (word) |
| Docstring/keyword match | +3 / +1 per word      |

Filters (kind, language, file_pattern) are applied before scoring. Results scoring zero are excluded.

---

## Dependencies

| Package                            | Purpose                       |
| ---------------------------------- | ----------------------------- |
| `mcp>=1.0.0,<1.10.0`              | MCP server framework          |
| `httpx>=0.27.0`                    | Async HTTP for GitHub API     |
| `tree-sitter-language-pack>=0.7.0` | Precompiled grammars          |
| `pathspec>=0.12.0`                 | `.gitignore` pattern matching |
| `anthropic>=0.40.0` (optional)     | AI summarization via Claude Haiku |
| `google-generativeai>=0.8.0` (optional) | AI summarization via Gemini Flash |
