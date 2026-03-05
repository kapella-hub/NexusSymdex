"""Extract import and call references from source code using tree-sitter."""

from tree_sitter_language_pack import get_parser

from .languages import LANGUAGE_REGISTRY, _ensure_plugins_loaded


def extract_references(content: str, filename: str, language: str) -> list[dict]:
    """Extract import and call references from source code.

    Args:
        content: Raw source code.
        filename: File path (for context).
        language: Language name (must be in LANGUAGE_REGISTRY).

    Returns:
        List of dicts: {"type": "import"|"call", "name": str, "line": int, "from_symbol": str|None}
    """
    _ensure_plugins_loaded()
    if language not in LANGUAGE_REGISTRY:
        return []

    spec = LANGUAGE_REGISTRY[language]
    source_bytes = content.encode("utf-8")

    parser = get_parser(spec.ts_language)
    tree = parser.parse(source_bytes)

    refs: list[dict] = []
    _walk_for_references(tree.root_node, source_bytes, language, refs)
    return refs


def _walk_for_references(node, source_bytes: bytes, language: str, refs: list[dict]):
    """Recursively walk AST to find import and call nodes."""
    _extract_node_references(node, source_bytes, language, refs)
    for child in node.children:
        _walk_for_references(child, source_bytes, language, refs)


def _extract_node_references(node, source_bytes: bytes, language: str, refs: list[dict]):
    """Extract references from a single AST node based on language."""
    node_type = node.type
    line = node.start_point[0] + 1

    # --- Imports ---
    if language == "python":
        if node_type == "import_statement":
            # import X, import X.Y
            for child in node.children:
                if child.type == "dotted_name":
                    name = _node_text(child, source_bytes)
                    refs.append({"type": "import", "name": name, "line": line, "from_symbol": None})
        elif node_type == "import_from_statement":
            # from X import Y, Z
            module = None
            for child in node.children:
                if child.type == "dotted_name" and module is None:
                    module = _node_text(child, source_bytes)
                elif child.type == "dotted_name" and module is not None:
                    name = _node_text(child, source_bytes)
                    refs.append({"type": "import", "name": f"{module}.{name}", "line": line, "from_symbol": None})
                elif child.type == "import_prefix":
                    continue
            # If no named imports found (e.g. from X import *), record module
            if module and not any(r["line"] == line for r in refs):
                refs.append({"type": "import", "name": module, "line": line, "from_symbol": None})

    elif language in ("javascript", "typescript"):
        if node_type == "import_statement":
            source = node.child_by_field_name("source")
            if source:
                name = _node_text(source, source_bytes).strip("'\"")
                refs.append({"type": "import", "name": name, "line": line, "from_symbol": None})

    elif language == "go":
        if node_type == "import_spec":
            path_node = node.child_by_field_name("path")
            if path_node:
                name = _node_text(path_node, source_bytes).strip('"')
                refs.append({"type": "import", "name": name, "line": line, "from_symbol": None})

    elif language == "rust":
        if node_type == "use_declaration":
            arg = node.child_by_field_name("argument")
            if arg:
                name = _node_text(arg, source_bytes)
                refs.append({"type": "import", "name": name, "line": line, "from_symbol": None})

    elif language == "java":
        if node_type == "import_declaration":
            for child in node.children:
                if child.type == "scoped_identifier":
                    name = _node_text(child, source_bytes)
                    refs.append({"type": "import", "name": name, "line": line, "from_symbol": None})
                    break

    elif language == "php":
        if node_type == "namespace_use_declaration":
            for child in node.children:
                if child.type == "namespace_use_clause":
                    name = _node_text(child, source_bytes)
                    refs.append({"type": "import", "name": name, "line": line, "from_symbol": None})

    # --- Calls (language-agnostic for common patterns) ---
    if node_type == "call" and language == "python":
        func = node.child_by_field_name("function")
        if func:
            name = _node_text(func, source_bytes)
            refs.append({"type": "call", "name": name, "line": line, "from_symbol": None})

    elif node_type == "call_expression" and language in ("javascript", "typescript", "go", "rust"):
        func = node.child_by_field_name("function")
        if func:
            name = _node_text(func, source_bytes)
            refs.append({"type": "call", "name": name, "line": line, "from_symbol": None})

    elif node_type == "method_invocation" and language == "java":
        name_node = node.child_by_field_name("name")
        obj_node = node.child_by_field_name("object")
        if name_node:
            name = _node_text(name_node, source_bytes)
            if obj_node:
                name = f"{_node_text(obj_node, source_bytes)}.{name}"
            refs.append({"type": "call", "name": name, "line": line, "from_symbol": None})

    elif node_type == "function_call_expression" and language == "php":
        func = node.child_by_field_name("function")
        if func:
            name = _node_text(func, source_bytes)
            refs.append({"type": "call", "name": name, "line": line, "from_symbol": None})

    elif node_type == "member_call_expression" and language == "php":
        name_node = node.child_by_field_name("name")
        if name_node:
            name = _node_text(name_node, source_bytes)
            refs.append({"type": "call", "name": name, "line": line, "from_symbol": None})


def _node_text(node, source_bytes: bytes) -> str:
    """Get the text content of an AST node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")
