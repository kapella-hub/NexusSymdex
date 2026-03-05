# User Guide

## Installation

```bash
pip install nexus-symdex
```

Or from source:

```bash
git clone https://github.com/kapella-hub/NexusSymdex.git
cd NexusSymdex
pip install -e .
```

---

## Configuration

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nexus-symdex": {
      "command": "uvx",
      "args": ["nexus-symdex"],
      "env": {
        "GITHUB_TOKEN": "ghp_xxxxxxxx",
        "ANTHROPIC_API_KEY": "sk-ant-xxxxxxxx"
      }
    }
  }
}
```

All environment variables are optional:

* `GITHUB_TOKEN` enables private repositories and higher GitHub API rate limits.
* `ANTHROPIC_API_KEY` enables AI-generated summaries and symbol explanations via Claude Haiku.
* `GOOGLE_API_KEY` enables AI-generated summaries via Gemini Flash (used if `ANTHROPIC_API_KEY` is not set).
* If no API key is set, summaries fall back to docstrings or signatures.

### VS Code

Add to `.vscode/settings.json`:

```json
{
  "mcp.servers": {
    "nexus-symdex": {
      "command": "uvx",
      "args": ["nexus-symdex"],
      "env": {
        "GITHUB_TOKEN": "ghp_xxxxxxxx"
      }
    }
  }
}
```

### Claude Code Status Line

If you use Claude Code, you can display a live token savings counter in the status bar:

```
Claude Sonnet 4.6 | my-project | 1,280,837 tkns saved · $6.40 saved on Opus
```

Ask Claude Code to set it up:

> "Add NexusSymdex token savings to my status line"

Claude Code will add a segment that reads `~/.code-index/_savings.json` and calculates cost avoided at the Claude Opus rate ($15.00 / 1M tokens). The counter updates automatically after every NexusSymdex tool call.

To add it manually, read `~/.code-index/_savings.json` and extract `total_tokens_saved`:

```js
// Node.js snippet for a statusline hook
const f = path.join(os.homedir(), '.code-index', '_savings.json');
const total = fs.existsSync(f) ? JSON.parse(fs.readFileSync(f)).total_tokens_saved ?? 0 : 0;
const cost  = (total * 15.00 / 1_000_000).toFixed(2);
if (total > 0) output += ` | ${total.toLocaleString()} tkns saved · $${cost} saved on Opus`;
```

---

### Google Antigravity

1. Open the Agent pane, click the `...` menu, then **MCP Servers** and **Manage MCP Servers**
2. Click **View raw config** to open `mcp_config.json`
3. Add the entry below, save, then restart the MCP server from the Manage MCPs pane

```json
{
  "mcpServers": {
    "nexus-symdex": {
      "command": "uvx",
      "args": ["nexus-symdex"],
      "env": {
        "GITHUB_TOKEN": "ghp_xxxxxxxx",
        "ANTHROPIC_API_KEY": "sk-ant-xxxxxxxx"
      }
    }
  }
}
```

---

## Workflows

### Explore a New Repository

```
index_repo: { "url": "fastapi/fastapi" }
get_repo_outline: { "repo": "fastapi/fastapi" }
get_file_tree: { "repo": "fastapi/fastapi", "path_prefix": "fastapi" }
get_file_outline: { "repo": "fastapi/fastapi", "file_path": "fastapi/main.py" }
```

### Explore a Local Project

```
index_folder: { "path": "/home/user/myproject" }
get_repo_outline: { "repo": "local-myproject" }
search_symbols: { "repo": "local-myproject", "query": "main" }
```

### Find and Read a Function

```
search_symbols: { "repo": "owner/repo", "query": "authenticate", "kind": "function" }
get_symbol: { "repo": "owner/repo", "symbol_id": "src/auth.py::authenticate#function" }
```

### Understand a Class

```
get_file_outline: { "repo": "owner/repo", "file_path": "src/auth.py" }
get_symbols: {
  "repo": "owner/repo",
  "symbol_ids": [
    "src/auth.py::AuthHandler.login#method",
    "src/auth.py::AuthHandler.logout#method"
  ]
}
```

### Trace a Call Graph

```
get_callers: { "repo": "owner/repo", "symbol_id": "src/auth.py::login#function" }
get_dependencies: { "repo": "owner/repo", "symbol_id": "src/auth.py::login#function" }
```

### Get a Structured Symbol Explanation

```
explain_symbol: { "repo": "owner/repo", "symbol_id": "src/auth.py::login#function" }
```

Returns: purpose, inputs, output, side effects, and complexity rating.

### Fill a Token Budget with Context

```
get_context: { "repo": "owner/repo", "budget_tokens": 4000, "focus": "authentication" }
```

Returns the most relevant symbols (with source) that fit within 4,000 tokens.

### Search Across All Repos

```
search_all_repos: { "query": "database", "kind": "class" }
```

### Watch a Folder for Changes

```
index_folder: { "path": "/home/user/myproject" }
watch_folder: { "path": "/home/user/myproject" }
list_watches: {}
unwatch_folder: { "path": "/home/user/myproject" }
```

The watcher polls every 5 seconds and triggers incremental reindex on file changes.

### Verify Source Hasn't Changed

```
get_symbol: {
  "repo": "owner/repo",
  "symbol_id": "src/main.py::process#function",
  "verify": true
}
```

The response `_meta.content_verified` will be `true` if the source matches the stored hash and `false` if it has drifted.

### Search for Non-Symbol Content

```
search_text: { "repo": "owner/repo", "query": "TODO", "file_pattern": "*.py" }
```

Use `search_text` for string literals, comments, configuration values, or anything that is not a symbol name.

### Force Re-index

```
invalidate_cache: { "repo": "owner/repo" }
index_repo: { "url": "owner/repo" }
```

---

## Tool Reference

| Tool               | Purpose                               | Key Parameters                                                     |
| ------------------ | ------------------------------------- | ------------------------------------------------------------------ |
| `index_repo`       | Index GitHub repository               | `url`, `use_ai_summaries`, `incremental`                           |
| `index_folder`     | Index local folder                    | `path`, `use_ai_summaries`, `extra_ignore_patterns`, `follow_symlinks`, `incremental` |
| `list_repos`       | List all indexed repositories         | —                                                                  |
| `get_file_tree`    | Browse file structure                 | `repo`, `path_prefix`, `include_summaries`                         |
| `get_file_outline` | Symbols in a file                     | `repo`, `file_path`                                                |
| `get_symbol`       | Full source of one symbol             | `repo`, `symbol_id`, `verify`, `context_lines`                     |
| `get_symbols`      | Batch retrieve symbols                | `repo`, `symbol_ids`                                               |
| `search_symbols`   | Search symbols                        | `repo`, `query`, `kind`, `language`, `file_pattern`, `max_results` |
| `search_text`      | Full-text search                      | `repo`, `query`, `file_pattern`, `max_results`                     |
| `get_repo_outline` | High-level overview                   | `repo`                                                             |
| `invalidate_cache` | Delete cached index                   | `repo`                                                             |
| `search_all_repos` | Cross-repo symbol search              | `query`, `kind`, `language`, `max_results`                         |
| `get_context`      | Token-budget context retrieval        | `repo`, `budget_tokens`, `focus`, `kind`                           |
| `explain_symbol`   | LLM-powered symbol explanation        | `repo`, `symbol_id`                                                |
| `get_callers`      | Find call sites                       | `repo`, `symbol_id`                                                |
| `get_dependencies` | Find outgoing calls/imports           | `repo`, `symbol_id`                                                |
| `watch_folder`     | Auto-reindex on changes               | `path`                                                             |
| `unwatch_folder`   | Stop watching                         | `path`                                                             |
| `list_watches`     | List active watches                   | —                                                                  |

---

## Symbol IDs

Symbol IDs follow the format:

```
{file_path}::{qualified_name}#{kind}
```

Examples:

```
src/main.py::UserService#class
src/main.py::UserService.login#method
src/utils.py::authenticate#function
config.py::MAX_RETRIES#constant
```

IDs are returned by `get_file_outline`, `search_symbols`, `search_text`, and `search_all_repos`. Pass them to `get_symbol`, `get_symbols`, `explain_symbol`, `get_callers`, or `get_dependencies`.

---

## Community Savings Meter

NexusSymdex contributes an anonymous token savings delta to a live global counter at [j.gravelle.us](https://j.gravelle.us) with each tool call. Only two values are ever sent: the tokens saved (a number) and a random anonymous install ID. No code, paths, repo names, or anything identifying is transmitted. Network failures are silent and never affect tool performance.

The anonymous install ID is generated once and stored locally in `~/.code-index/_savings.json`.

To disable, set `JCODEMUNCH_SHARE_SAVINGS=0` in your MCP server env:

```json
{
  "mcpServers": {
    "nexus-symdex": {
      "command": "uvx",
      "args": ["nexus-symdex"],
      "env": {
        "JCODEMUNCH_SHARE_SAVINGS": "0"
      }
    }
  }
}
```

---

## Troubleshooting

**"Repository not found"**
Check the URL format (`owner/repo` or full GitHub URL). For private repositories, set `GITHUB_TOKEN`.

**"No source files found"**
The repository may not contain supported language files (`.py`, `.js`, `.ts`, `.go`, `.rs`, `.java`, `.php`), or files may be excluded by skip patterns.

**Rate limiting**
Set `GITHUB_TOKEN` to increase GitHub API limits (5,000 requests/hour vs 60 unauthenticated).

**AI summaries not working**
Set `ANTHROPIC_API_KEY` (Claude Haiku) or `GOOGLE_API_KEY` (Gemini Flash). Anthropic takes priority if both are set. Without either, summaries fall back to docstrings or signatures.

**explain_symbol returns basic results**
Ensure at least one LLM provider is configured (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or `OPENAI_API_BASE`). Without an LLM, `explain_symbol` falls back to heuristic analysis using the symbol's docstring and signature.

**Stale index**
Use `invalidate_cache` followed by `index_repo` or `index_folder` to force a clean re-index. Alternatively, use `watch_folder` to keep your index up to date automatically.

**Encoding issues**
Files with invalid UTF-8 are handled safely using replacement characters.

---

## Storage

Indexes are stored at `~/.code-index/` (override with the `CODE_INDEX_PATH` environment variable):

```
~/.code-index/
├── _savings.json          # Cumulative token savings counter
├── owner-repo.json        # Index metadata + symbols + references
└── owner-repo/            # Raw source files
    └── src/main.py
```

---

## Tips

1. Start with `get_repo_outline` to quickly understand the repository structure.
2. Use `get_file_outline` before reading source to understand the API surface first.
3. Narrow searches using `kind`, `language`, and `file_pattern`.
4. Batch-retrieve related symbols with `get_symbols` instead of repeated `get_symbol` calls.
5. Use `get_context` with a token budget to efficiently load focused context for a task.
6. Use `get_callers` and `get_dependencies` to trace call graphs before refactoring.
7. Use `search_text` when symbol search does not locate the needed content.
8. Use `search_all_repos` when the target repository is unknown.
9. Use `verify: true` on `get_symbol` to detect source drift since indexing.
10. Use `watch_folder` on active projects to keep the index fresh automatically.
