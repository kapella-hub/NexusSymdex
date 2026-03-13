#!/bin/bash
# NexusSymdex SessionStart hook
# Checks if current project is indexed and primes Claude with coding instructions.
# Plain text stdout on exit 0 is injected into Claude's context.

# Read cwd from stdin JSON (hook input provides session context)
# Use Python with fallback chain — python3 (Linux/Mac), python (Windows), py -3 (Windows launcher)
INPUT=$(cat)
PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo "py -3")
PROJECT_DIR=$(echo "$INPUT" | $PYTHON -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)

# Fallback to PWD if cwd not in input
if [ -z "$PROJECT_DIR" ]; then
  PROJECT_DIR="$PWD"
fi

if [ -z "$PROJECT_DIR" ]; then
  echo "NexusSymdex: Could not determine project directory."
  exit 0
fi

FOLDER_NAME=$(basename "$PROJECT_DIR")

# Check if the project is indexed
# NexusSymdex stores indices at ~/.code-index/local-<folder_name>.json
INDEX_FILE="$HOME/.code-index/local-${FOLDER_NAME}.json"
if [ ! -f "$INDEX_FILE" ]; then
  echo "NexusSymdex: Project '$FOLDER_NAME' is not indexed. Run index_folder(path='$PROJECT_DIR') to enable code intelligence."
  exit 0
fi

cat <<EOF
NexusSymdex code intelligence is active for repo 'local/$FOLDER_NAME'.

Before writing any code, call these tools to understand the codebase:
1. get_architecture_map(repo='local/$FOLDER_NAME') — understand layers and module roles
2. extract_conventions(repo='local/$FOLDER_NAME') — learn naming patterns and conventions

Coding guidelines:
- Prefer search_symbols/suggest_symbols over raw Grep/Glob when exploring code
- Use get_file_outline instead of reading entire files to understand structure
- Before modifying public APIs or widely-used symbols, call get_callers and get_impact
- After multi-file changes, call get_review_context to self-check for broken references
- If tool calls fail with "Repository not found", call list_repos() to discover the correct repo identifier
EOF
