# nexus-symdex

Token-efficient MCP server for source code exploration via tree-sitter AST parsing.

Instead of dumping entire files into context, nexus-symdex parses your codebase into symbols (functions, classes, methods, types, constants) and serves only what you need — saving 60-80% of tokens compared to raw file reading.

## Features

- **12 languages**: Python, JavaScript, TypeScript, Go, Rust, Java, PHP, C, C#, Ruby, Kotlin, Swift
- **Smart symbol extraction**: Captures functions, classes, methods, constants, types, variables, and module preambles — plus JS/TS assigned functions (`res.send = function() {}`), arrow functions, CommonJS exports, and prototype assignments
- **Scope-aware references**: Callers/callees resolved with file-scope priority (same file > imported file > dotted name > fallback), minimizing false positives
- **Inline imports**: `get_symbol` and `get_symbols` can include file import statements for full context
- **Byte-offset retrieval**: O(1) source lookup via stored offsets, no re-parsing
- **Incremental indexing**: Only re-parse changed files (hash-based or git-diff)
- **Architecture intelligence**: Dead code detection, import graphs, impact analysis, architecture maps
- **Smart context budgeting**: Fill a token budget with the most relevant symbols + their dependencies
- **File watching**: Auto-reindex on filesystem changes
- **24 tools** for comprehensive code exploration

## Installation

```bash
pip install nexus-symdex
```

Or with AI summary support:

```bash
pip install nexus-symdex[all]
```

### Claude Desktop / MCP Client Configuration

Add to your MCP client config:

```json
{
  "mcpServers": {
    "nexus-symdex": {
      "command": "nexus-symdex"
    }
  }
}
```

## Tools

### Indexing

| Tool | Description |
|------|-------------|
| `index_repo` | Index a GitHub repository by URL (fetches via API) |
| `index_folder` | Index a local folder on disk |
| `invalidate_cache` | Clear cached index for a repository |

### Exploration

| Tool | Description |
|------|-------------|
| `list_repos` | List all indexed repositories |
| `get_file_tree` | Get file tree with per-file summaries |
| `get_file_outline` | Get all symbols in a file (signatures only, no source) |
| `get_repo_outline` | High-level overview of an entire repo |
| `get_symbol` | Get a single symbol by ID with full source; `include_imports` for file context |
| `get_symbols` | Batch-get multiple symbols by ID; `include_imports` for file context |
| `search_symbols` | Search symbols by name, kind, file pattern |
| `search_text` | Regex search across indexed source files |
| `search_all_repos` | Search across all indexed repositories |
| `explain_symbol` | Get symbol with callers, callees, and dependencies |

### Architecture Intelligence

| Tool | Description |
|------|-------------|
| `get_callers` | Find all callers of a symbol |
| `get_dependencies` | Find all dependencies of a symbol |
| `get_impact` | Transitive impact analysis — BFS through caller graph |
| `get_import_graph` | File-to-file dependency graph (adjacency, DOT, or summary) |
| `get_architecture_map` | Auto-classify files into layers (API, core, utility, etc.) |
| `find_dead_code` | Find unreferenced symbols (potential dead code) |
| `get_change_summary` | Diff current files against stored index |

### Smart Context

| Tool | Description |
|------|-------------|
| `get_context` | Fill a token budget with the most relevant symbols; optionally include dependencies |

### File Watching

| Tool | Description |
|------|-------------|
| `watch_folder` | Watch a folder for changes and auto-reindex |
| `unwatch_folder` | Stop watching a folder |
| `list_watches` | List active folder watches |

## Usage Examples

### Index and explore a repo

```
index_folder path="/home/user/my-project"
get_file_tree repo="my-project"
search_symbols repo="my-project" query="authenticate" kind="function"
get_symbol repo="my-project" symbol_id="auth.py::authenticate#function"
```

### Architecture analysis

```
get_architecture_map repo="my-project"
get_import_graph repo="my-project" format="summary"
find_dead_code repo="my-project"
```

### Impact analysis

```
get_impact repo="my-project" symbol_id="utils.py::parse_config#function" max_depth=3
get_callers repo="my-project" symbol_id="db.py::connect#function"
```

### Smart context budgeting

```
get_context repo="my-project" focus="authentication" budget_tokens=4000 include_deps=true
```

## Architecture

```
src/nexus_symdex/
├── server.py              # MCP server, tool registration, request routing
├── parser/
│   ├── extractor.py       # tree-sitter AST walking + symbol extraction
│   ├── languages.py       # Per-language specs (node types, patterns)
│   ├── references.py      # Import/call reference extraction
│   ├── symbols.py         # Symbol dataclass
│   └── hierarchy.py       # Parent-child symbol tree
├── storage/
│   ├── index_store.py     # Index save/load, byte-offset retrieval, caching
│   └── token_tracker.py   # Token savings tracking
├── tools/
│   ├── index_repo.py      # GitHub repo indexing
│   ├── index_folder.py    # Local folder indexing
│   ├── get_context.py     # Smart context budgeting with dependency inclusion
│   ├── find_dead_code.py  # Unreferenced symbol detection
│   ├── get_import_graph.py # File dependency graph
│   ├── get_impact.py      # Transitive impact analysis
│   ├── get_change_summary.py # Index-vs-current diffing
│   ├── get_architecture_map.py # Auto layer classification
│   └── _utils.py          # Shared helpers
├── security/              # Path validation, secret detection
└── summarizer/            # AI-powered symbol summaries (optional)
```

## Development

```bash
git clone https://github.com/morganbarrett/nexus-symdex.git
cd nexus-symdex
pip install -e ".[test]"
pytest
```

## License

MIT
