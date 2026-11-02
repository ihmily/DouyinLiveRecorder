#!/usr/bin/env python3
"""Read-only AST probe for a full-repo review.

Reports counts and a few sample locations for: parse failures, duplicate
top-level definitions, bare `except ...: pass`, `open()` outside a `with`,
dangerous primitives, subprocess calls without `timeout=`, structure metrics
(long functions / deep nesting / many params) and unused-import candidates.

Approximations are labelled as such in the output; treat every hit as a lead,
not a finding, and confirm with a real read before it reaches the report.

Python-only. JS/TS patterns (eval, innerHTML, console.log, TODO/FIXME) need a
text grep; this tool does not pretend to cover them.

Never writes anything. Python 3.8+.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

DEFAULT_SKIP = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node",
    "node_modules",
    "vendor",
    "ffmpeg",
    "build",
    "dist",
    "out",
    "coverage",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".workbuddy",
    "site-packages",
}

CTRL = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Match)
FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
SUBPROC_TIMEOUT_FUNCS = {"run", "call", "check_call", "check_output", "Popen"}
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def iter_py(root: Path, skip: set[str]):
    for path in sorted(root.rglob("*.py")):
        if set(path.relative_to(root).parts) & skip:
            continue
        yield path


def nesting_depth(node: ast.AST, depth: int = 0) -> int:
    best = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (FUNC + (ast.ClassDef,))):
            continue
        best = max(best, nesting_depth(child, depth + 1 if isinstance(child, CTRL) else depth))
    return best


def arg_count(node) -> int:
    args = node.args
    total = len(getattr(args, "posonlyargs", [])) + len(args.args) + len(args.kwonlyargs)
    positional = list(getattr(args, "posonlyargs", [])) + list(args.args)
    if positional and positional[0].arg in ("self", "cls"):
        total -= 1
    return total


def scan_file(path: Path, rel: str, long_fn: int, nest: int, params: int) -> dict:
    out: dict[str, list] = {
        k: []
        for k in (
            "parse_error",
            "duplicate_defs",
            "except_pass_unexplained",
            "except_pass_with_comment",
            "open_without_with",
            "dangerous",
            "subprocess_no_timeout",
            "long_functions",
            "deep_nesting",
            "many_params",
            "unused_imports",
        )
    }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except (OSError, SyntaxError, ValueError) as exc:
        out["parse_error"].append({"file": rel, "line": getattr(exc, "lineno", 0) or 0, "detail": str(exc)[:160]})
        return out

    lines = text.splitlines()
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    seen: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, FUNC + (ast.ClassDef,)):
            seen[node.name] = seen.get(node.name, 0) + 1
    for name, count in seen.items():
        if count > 1:
            out["duplicate_defs"].append({"file": rel, "line": 0, "detail": f"{name} defined {count}x at module level"})

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            lo = max(0, node.lineno - 4)
            hi = min(len(lines), node.lineno + 4)
            window = "\n".join(lines[lo:hi])
            target = "except_pass_with_comment" if "#" in window else "except_pass_unexplained"
            out[target].append({"file": rel, "line": node.lineno, "detail": "except ...: pass"})

        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                cur, inside = node, False
                while cur in parents:
                    cur = parents[cur]
                    if isinstance(cur, ast.withitem):
                        inside = True
                        break
                if not inside:
                    out["open_without_with"].append(
                        {"file": rel, "line": node.lineno, "detail": "open(...) not in with"}
                    )

            if isinstance(func, ast.Name) and func.id in ("eval", "exec"):
                out["dangerous"].append({"file": rel, "line": node.lineno, "detail": func.id})
            if isinstance(func, ast.Attribute):
                owner = func.value
                owner_name = owner.id if isinstance(owner, ast.Name) else ""
                if owner_name == "os" and func.attr == "system":
                    out["dangerous"].append({"file": rel, "line": node.lineno, "detail": "os.system"})
                if owner_name == "pickle" and func.attr in ("load", "loads"):
                    out["dangerous"].append({"file": rel, "line": node.lineno, "detail": "pickle." + func.attr})
                if owner_name == "yaml" and func.attr == "load":
                    has_loader = any(k.arg == "Loader" for k in node.keywords)
                    if not has_loader:
                        out["dangerous"].append(
                            {"file": rel, "line": node.lineno, "detail": "yaml.load without Loader"}
                        )
                if owner_name == "subprocess" and func.attr in SUBPROC_TIMEOUT_FUNCS:
                    if not any(k.arg == "timeout" for k in node.keywords):
                        out["subprocess_no_timeout"].append(
                            {"file": rel, "line": node.lineno, "detail": "subprocess." + func.attr}
                        )
            if any(
                k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords
            ):
                out["dangerous"].append({"file": rel, "line": node.lineno, "detail": "shell=True"})

        if isinstance(node, FUNC):
            length = (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno + 1
            if length >= long_fn:
                out["long_functions"].append(
                    {"file": rel, "line": node.lineno, "detail": f"{node.name} {length} lines"}
                )
            depth = nesting_depth(node)
            if depth >= nest:
                out["deep_nesting"].append({"file": rel, "line": node.lineno, "detail": f"{node.name} depth {depth}"})
            count = arg_count(node)
            if count >= params:
                out["many_params"].append({"file": rel, "line": node.lineno, "detail": f"{node.name} {count} params"})

    if path.name != "__init__.py":
        imported: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    imported[alias.asname or alias.name] = node.lineno
        used: set[str] = set()
        strings: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                cur = node
                while isinstance(cur, ast.Attribute):
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    used.add(cur.id)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                strings.append(node.value)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    used.add(elt.value)
        corpus = "\n".join(strings)
        words = set(WORD.findall(corpus))
        text_words = set(WORD.findall(text))
        for name, line in imported.items():
            if name not in used and name not in words:
                detail = name
                if name in text_words:
                    detail = f"{name} (mentioned elsewhere in the file, check for re-export)"
                out["unused_imports"].append({"file": rel, "line": line, "detail": detail})

    return out


def merge(into: dict, part: dict) -> None:
    for key, items in part.items():
        into.setdefault(key, []).extend(items)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", help="repository root (default: cwd)")
    ap.add_argument("--skip", action="append", default=[], metavar="DIR", help="extra directory name to skip")
    ap.add_argument("--limit", type=int, default=3, help="sample rows per category (default 3)")
    ap.add_argument("--long-fn", type=int, default=200, help="function length threshold (default 200)")
    ap.add_argument("--nest", type=int, default=6, help="nesting depth threshold (default 6)")
    ap.add_argument("--params", type=int, default=9, help="parameter count threshold (default 9)")
    ap.add_argument("--json", action="store_true", help="print full JSON instead of a summary")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}")
        return 2
    skip = set(DEFAULT_SKIP) | set(args.skip)

    result: dict = {}
    files = 0
    for path in iter_py(root, skip):
        files += 1
        merge(result, scan_file(path, path.relative_to(root).as_posix(), args.long_fn, args.nest, args.params))

    if args.json:
        print(json.dumps({"root": str(root), "files": files, "findings": result}, ensure_ascii=False, indent=1))
        return 0

    parsed = files - len(result.get("parse_error", []))
    print(f"python_files={files}  parsed={parsed}  parse_errors={len(result.get('parse_error', []))}")
    labels = [
        ("parse_error", "parse failures"),
        ("duplicate_defs", "duplicate top-level defs"),
        ("except_pass_unexplained", "except-pass without nearby comment"),
        ("except_pass_with_comment", "except-pass with nearby comment (informational)"),
        ("open_without_with", "open() outside with"),
        ("dangerous", "dangerous primitives"),
        ("subprocess_no_timeout", "subprocess calls without timeout= (approximate)"),
        ("long_functions", f"functions >= {args.long_fn} lines"),
        ("deep_nesting", f"nesting >= {args.nest}"),
        ("many_params", f"params >= {args.params}"),
        ("unused_imports", "unused-import candidates (approximate)"),
    ]
    for key, label in labels:
        items = result.get(key, [])
        print(f"{label:<46} {len(items):>5}")
        for item in items[: args.limit]:
            where = f"{item['file']}:{item['line']}" if item.get("line") else item["file"]
            print(f"    {where}  {item['detail']}")
        if len(items) > args.limit:
            print(f"    ... {len(items) - args.limit} more (rerun with --json for the full list)")
    print("note: counts are leads, not findings. Confirm each high-severity hit by reading the code.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
