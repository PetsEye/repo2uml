"""Optional tree-sitter symbol extraction (hybrid backend).

stdlib regex parsing stays the default and the package keeps zero required
dependencies. When `tree_sitter` (+ a language grammar) is importable —
`pip install repo2uml[treesitter]` — parsers union its symbols (classes,
functions, package names) with the regex results for higher precision
(e.g. package-private Java methods the regex misses).

Anything failing here (missing grammar, API drift, parse errors) returns
None and the caller silently keeps stdlib results. Never raises.
"""
from __future__ import annotations

QUERIES = {
    "java": """
        (package_declaration (scoped_identifier) @pkg)
        (class_declaration name: (identifier) @cls)
        (interface_declaration name: (identifier) @cls)
        (enum_declaration name: (identifier) @cls)
        (record_declaration name: (identifier) @cls)
        (method_declaration name: (identifier) @fn)
    """,
    "go": """
        (package_clause (package_identifier) @pkg)
        (type_declaration (type_spec name: (type_identifier) @cls))
        (function_declaration name: (identifier) @fn)
        (method_declaration name: (field_identifier) @fn)
    """,
    "typescript": """
        (class_declaration name: (_) @cls)
        (interface_declaration name: (type_identifier) @cls)
        (function_declaration name: (identifier) @fn)
        (generator_function_declaration name: (identifier) @fn)
        (method_definition name: (_) @fn)
    """,
}
# javascript shares the typescript grammar (non-tsx flavor)
QUERIES["javascript"] = QUERIES["typescript"]


def _load_language(lang: str):
    try:
        import tree_sitter
    except ImportError:
        return None
    try:
        if lang == "java":
            from tree_sitter_java import language as get
        elif lang == "go":
            from tree_sitter_go import language as get
        elif lang in ("typescript", "javascript"):
            from tree_sitter_typescript import language_typescript as get
        else:
            return None
        return tree_sitter.Language(get())
    except (ImportError, Exception):
        return None


def available(lang: str) -> bool:
    return lang in QUERIES and _load_language(lang) is not None


def extract_symbols(lang: str, text: str) -> dict | None:
    """Return {classes, functions, package} or None when unavailable."""
    if lang not in QUERIES:
        return None
    try:
        import tree_sitter
        language = _load_language(lang)
        if language is None:
            return None
        parser = tree_sitter.Parser(language)
        tree = parser.parse(text.encode("utf-8", errors="ignore"))
        query = tree_sitter.Query(language, QUERIES[lang])
        try:
            captures = query.captures(tree.root_node)
        except (AttributeError, TypeError):
            captures = tree_sitter.QueryCursor(query).captures(tree.root_node)
    except Exception:
        return None
    out: dict = {"classes": [], "functions": [], "package": ""}
    try:
        for name, nodes in captures.items():
            for node in nodes:
                try:
                    val = node.text.decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if name == "pkg" and not out["package"]:
                    out["package"] = val
                elif name == "cls" and val not in out["classes"]:
                    out["classes"].append(val)
                elif name == "fn" and val not in out["functions"]:
                    out["functions"].append(val)
    except Exception:
        return None
    return out
