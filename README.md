## Cut code-reading token costs by up to **99%**

Most AI agents explore repositories the expensive way:
open entire files, skim thousands of irrelevant lines, repeat.

**NexusSymdex indexes a codebase once and lets agents retrieve only the exact symbols they need** — functions, classes, methods, constants — with byte-level precision.

| Task                   | Traditional approach | With NexusSymdex |
| ---------------------- | -------------------- | --------------- |
| Find a function        | ~40,000 tokens       | ~200 tokens     |
| Understand module API  | ~15,000 tokens       | ~800 tokens     |
| Explore repo structure | ~200,000 tokens      | ~2k tokens      |

Index once. Query cheaply forever.
Precision context beats brute-force context.

---

# NexusSymdex

### Structured code retrieval for AI agents

![License](https://img.shields.io/badge/license-dual--use-blue)
![MCP](https://img.shields.io/badge/MCP-compatible-purple)
![Local-first](https://img.shields.io/badge/local--first-yes-brightgreen)
![Polyglot](https://img.shields.io/badge/parsing-tree--sitter-9cf)
[![PyPI version](https://img.shields.io/pypi/v/nexus-symdex)](https://pypi.org/project/nexus-symdex/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/nexus-symdex)](https://pypi.org/project/nexus-symdex/)

**Stop dumping files into context windows. Start retrieving exactly what the agent needs.**

NexusSymdex indexes a codebase once using tree-sitter AST parsing, then allows MCP-compatible agents (Claude Desktop, VS Code, Claude Code, Google Antigravity, and others) to **discover, search, and retrieve code by symbol** instead of brute-reading files.

Every symbol stores:
- Signature and kind
- Qualified name and file location
- One-line summary
- Byte offsets into the original file
- Content hash for drift detection

Full source is retrieved on demand using O(1) byte-offset seeking.

---

## Why agents need this

Agents waste money when they:

- Open entire files to find one function
- Re-read the same code repeatedly
- Consume imports, boilerplate, and unrelated helpers

NexusSymdex provides precision context access:

- Search symbols by name, kind, or language
- Outline files without loading full contents
- Retrieve exact symbol implementations only
- Trace call graphs with `get_callers` and `get_dependencies`
- Auto-fill token budgets with `get_context`
- Search across all indexed repos simultaneously
- Watch folders for automatic re-indexing on file changes

Agents do not need larger context windows. They need structured retrieval.

---

## How it works

1. **Discovery** — GitHub API or local directory walk
2. **Security filtering** — traversal protection, secret exclusion, binary detection
3. **Parsing** — tree-sitter AST extraction + reference analysis
4. **Storage** — JSON index + raw files stored locally (`~/.code-index/`)
5. **Retrieval** — O(1) byte-offset seeking via stable symbol IDs

### Stable Symbol IDs

```
{file_path}::{qualified_name}#{kind}
```

Examples:

- `src/main.py::UserService.login#method`
- `src/utils.py::authenticate#function`

IDs remain stable across re-indexing when path, qualified name, and kind are unchanged.

---

## Installation

### Prerequisites

- Python 3.10+
- pip

### Install

```bash
pip install nexus-symdex
```

Verify:

```bash
nexus-symdex --help
```

---

## Configure MCP Client

> **PATH note:** MCP clients often run with a limited environment where `nexus-symdex` may not be found even if it works in your terminal. Using [`uvx`](https://github.com/astral-sh/uv) is the recommended approach — it resolves the package on demand without requiring anything to be on your system PATH. If you prefer `pip install`, use the absolute path to the executable instead:
> - **Linux:** `/home/<username>/.local/bin/nexus-symdex`
> - **macOS:** `/Users/<username>/.local/bin/nexus-symdex`
> - **Windows:** `C:\\Users\\<username>\\AppData\\Roaming\\Python\\Python3xx\\Scripts\\nexus-symdex.exe`

### Claude Desktop / Claude Code

Config file location:

| OS      | Path |
| ------- | ---- |
| macOS   | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux   | `~/.config/claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

**Minimal config (no API keys needed):**

```json
{
  "mcpServers": {
    "nexus-symdex": {
      "command": "uvx",
      "args": ["nexus-symdex"]
    }
  }
}
```

**With optional AI summaries and GitHub auth:**

```json
{
  "mcpServers": {
    "nexus-symdex": {
      "command": "uvx",
      "args": ["nexus-symdex"],
      "env": {
        "GITHUB_TOKEN": "ghp_...",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

After saving the config, **restart Claude Desktop / Claude Code** for the server to appear.

### Google Antigravity

1. Open the Agent pane, click the `...` menu, then **MCP Servers** and **Manage MCP Servers**
2. Click **View raw config** to open `mcp_config.json`
3. Add the entry below, save, then restart the MCP server from the Manage MCPs pane

```json
{
  "mcpServers": {
    "nexus-symdex": {
      "command": "uvx",
      "args": ["nexus-symdex"]
    }
  }
}
```

Environment variables are optional:

| Variable            | Purpose                                      |
| ------------------- | -------------------------------------------- |
| `GITHUB_TOKEN`      | Higher GitHub API limits / private access    |
| `ANTHROPIC_API_KEY` | AI-generated summaries via Claude Haiku (takes priority) |
| `GOOGLE_API_KEY`    | AI-generated summaries via Gemini Flash      |

---

## Usage Examples

```
index_folder: { "path": "/path/to/project" }
index_repo:   { "url": "owner/repo" }

get_repo_outline: { "repo": "owner/repo" }
get_file_outline: { "repo": "owner/repo", "file_path": "src/main.py" }
search_symbols:   { "repo": "owner/repo", "query": "authenticate" }
get_symbol:       { "repo": "owner/repo", "symbol_id": "src/main.py::MyClass.login#method" }
search_text:      { "repo": "owner/repo", "query": "TODO" }
search_all_repos: { "query": "database" }
get_context:      { "repo": "owner/repo", "budget_tokens": 4000, "focus": "auth" }
get_callers:      { "repo": "owner/repo", "symbol_id": "src/auth.py::login#function" }
get_dependencies: { "repo": "owner/repo", "symbol_id": "src/auth.py::login#function" }
explain_symbol:   { "repo": "owner/repo", "symbol_id": "src/auth.py::login#function" }
watch_folder:     { "path": "/path/to/project" }
```

---

## Tools (18)

| Tool               | Purpose                                    |
| ------------------ | ------------------------------------------ |
| `index_repo`       | Index a GitHub repository                  |
| `index_folder`     | Index a local folder                       |
| `list_repos`       | List indexed repositories                  |
| `get_file_tree`    | Repository file structure                  |
| `get_file_outline` | Symbol hierarchy for a file                |
| `get_symbol`       | Retrieve full symbol source                |
| `get_symbols`      | Batch retrieve symbols                     |
| `search_symbols`   | Search symbols with filters                |
| `search_text`      | Full-text search                           |
| `get_repo_outline` | High-level repo overview                   |
| `invalidate_cache` | Remove cached index                        |
| `search_all_repos` | Search symbols across all indexed repos    |
| `get_context`      | Token-budget-aware context retrieval       |
| `explain_symbol`   | LLM-powered structured symbol explanation  |
| `get_callers`      | Find all call sites for a symbol           |
| `get_dependencies` | Find what a symbol calls and imports       |
| `watch_folder`     | Auto-reindex on file changes               |
| `unwatch_folder`   | Stop watching a folder                     |
| `list_watches`     | List actively watched folders              |

Every tool response includes a `_meta` envelope with timing, token savings, and cost avoided:

```json
"_meta": {
  "timing_ms": 4.3,
  "tokens_saved": 48153,
  "total_tokens_saved": 1280837,
  "cost_avoided": { "claude_opus": 1.2038, "gpt5_latest": 0.4815 },
  "total_cost_avoided": { "claude_opus": 32.02, "gpt5_latest": 12.81 }
}
```

`total_tokens_saved` and `total_cost_avoided` accumulate across all tool calls and persist to `~/.code-index/_savings.json`.

---

## Supported Languages

| Language   | Extensions    | Symbol Types                            |
| ---------- | ------------- | --------------------------------------- |
| Python     | `.py`         | function, class, method, constant, type |
| JavaScript | `.js`, `.jsx` | function, class, method, constant       |
| TypeScript | `.ts`, `.tsx` | function, class, method, constant, type |
| Go         | `.go`         | function, method, type, constant        |
| Rust       | `.rs`         | function, type, impl, constant          |
| Java       | `.java`       | method, class, type, constant           |
| PHP        | `.php`        | function, class, method, type, constant |

See [LANGUAGE_SUPPORT.md](LANGUAGE_SUPPORT.md) for full semantics.

---

## Security

Built-in protections:

- Path traversal prevention (owner/name sanitization + `_safe_content_path` enforcement)
- Symlink escape protection
- Secret file exclusion (`.env`, `*.pem`, etc.)
- Binary detection
- Configurable file size limits

See [SECURITY.md](SECURITY.md) for details.

---

## Local LLMs (Ollama / LM Studio)

You can use local, privacy-preserving AI models to generate summaries and symbol explanations by providing an OpenAI-compatible endpoint.

For **Ollama**, run a model locally, then configure the MCP server:
```json
"env": {
  "OPENAI_API_BASE": "http://localhost:11434/v1",
  "OPENAI_MODEL": "qwen3-coder"
}
```

For **LM Studio**, ensure the Local Server is running (usually on port 1234):
```json
"env": {
  "OPENAI_API_BASE": "http://127.0.0.1:1234/v1",
  "OPENAI_MODEL": "openai/gpt-oss-20b"
}
```

> [!TIP]
> **Performance Note:** Local models can be slow to load into memory on their first request, potentially causing the MCP server to time out and fall back to generic signature summaries. It is highly recommended to **pre-load the model** in Ollama or LM Studio before starting the server, or increase the `OPENAI_TIMEOUT` environment variable (e.g., to `"120.0"`) to allow more time for generation.

---

## Environment Variables

| Variable                    | Purpose                   | Required |
| --------------------------- | ------------------------- | -------- |
| `GITHUB_TOKEN`              | GitHub API auth           | No       |
| `ANTHROPIC_API_KEY`         | Symbol summaries and explanations via Claude Haiku (takes priority) | No       |
| `GOOGLE_API_KEY`            | Symbol summaries and explanations via Gemini Flash | No       |
| `OPENAI_API_BASE`           | Base URL for local LLMs (e.g. `http://localhost:11434/v1`) | No |
| `OPENAI_API_KEY`            | API key for local LLMs (default: `local-llm`) | No |
| `OPENAI_MODEL`              | Model name for local LLMs (default: `qwen3-coder`) | No |
| `OPENAI_TIMEOUT`            | Timeout in seconds for local requests (default: `60.0`) | No |
| `CODE_INDEX_PATH`           | Custom cache path         | No       |
| `JCODEMUNCH_SHARE_SAVINGS`  | Set to `0` to disable anonymous community token savings reporting | No       |

### Community Savings Meter

Each tool call contributes an anonymous delta to a live global counter at [j.gravelle.us](https://j.gravelle.us). Only two values are ever sent: the tokens saved (a number) and a random anonymous install ID. No code, paths, repo names, or anything identifying is transmitted.

The anon ID is generated once and stored in `~/.code-index/_savings.json`.

To disable, set `JCODEMUNCH_SHARE_SAVINGS=0` in your MCP server env.

---

## Documentation

- [USER_GUIDE.md](USER_GUIDE.md) — Installation, configuration, workflows, and tool reference
- [ARCHITECTURE.md](ARCHITECTURE.md) — Internal design, data flow, and module structure
- [SPEC.md](SPEC.md) — Technical specification for all tools and data models
- [SECURITY.md](SECURITY.md) — Security controls and threat model
- [LANGUAGE_SUPPORT.md](LANGUAGE_SUPPORT.md) — Supported languages and adding new ones
- [TOKEN_SAVINGS.md](TOKEN_SAVINGS.md) — Token savings methodology and benchmarks

---

## Star History

<a href="https://www.star-history.com/#kapella-hub/NexusSymdex&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=kapella-hub/NexusSymdex&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=kapella-hub/NexusSymdex&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=kapella-hub/NexusSymdex&type=date&legend=top-left" />
 </picture>
</a>

---

## License (Dual Use)

This repository is **free for non-commercial use** under the terms below.
**Commercial use requires a paid commercial license.**

---

## Copyright and License Text

Copyright (c) 2026 J. Gravelle

### 1. Non-Commercial License Grant (Free)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to use, copy, modify, merge, publish, and distribute the Software for **personal, educational, research, hobby, or other non-commercial purposes**, subject to the following conditions:

1. The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

2. Any modifications made to the Software must clearly indicate that they are derived from the original work, and the name of the original author (J. Gravelle) must remain intact. He's kinda full of himself.

3. Redistributions of the Software in source code form must include a prominent notice describing any modifications from the original version.

### 2. Commercial Use

Commercial use of the Software requires a separate paid commercial license from the author.

"Commercial use" includes, but is not limited to:

- Use of the Software in a business environment
- Internal use within a for-profit organization
- Incorporation into a product or service offered for sale
- Use in connection with revenue generation, consulting, SaaS, hosting, or fee-based services

For commercial licensing inquiries, contact:
j@gravelle.us | https://j.gravelle.us

Until a commercial license is obtained, commercial use is not permitted.

### 3. Disclaimer of Warranty

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT.

IN NO EVENT SHALL THE AUTHOR OR COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
