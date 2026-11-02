#!/usr/bin/env python3
# Cross-check every reference that appears *inside a comment* against the code that
# survives comment stripping. A comment-only refactor deletes and rewrites text, so stale
# or invented anchors (tests/test_x.py::test_y, src/foo.py, `symbol_name`) get introduced
# silently and only bite later when someone trusts them.
#
# Findings are layered: HIGH = provably wrong (cited file/anchor/symbol does not exist),
# LOW = mentions that only make sense in context (bare filenames, prose product names).
#
# Usage:
#   python check_comment_refs.py [--repo DIR] [--paths p1 p2 ...] [--strict] [--limit N] [--all]
# Exit 1 only with --strict and at least one HIGH finding.

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path

SRC_EXTS = {".py", ".js", ".mjs", ".cjs", ".ts", ".css", ".scss", ".html", ".htm", ".vbs"}
REF_EXTS = r"py|js|mjs|cjs|ts|css|html|md|ini|json|ya?ml|vbs|po|mo|txt|yml"
EXCLUDE_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
                ".ruff_cache", ".tox", ".coverage", "build", "dist", "node", "ffmpeg", "downloads", "logs",
                ".workbuddy", ".qoder"}
SKIP_GLOBS = ("*.min.js", "*.min.css", "*.map")
PROSE_NAMES = {"node.js", "vue.js", "react.js", "deno.js", "next.js", "three.js", "lodash.js", "jquery.js"}
IGNORE_WORDS = re.compile(r"^(https?|ftp|utf|gbk|crlf|lf|argv|kwargs|args|self|cls|TODO|FIXME)")

PATH_RE = re.compile(r"[A-Za-z0-9_.\-/]*[A-Za-z0-9_\-/]+\.(?:" + REF_EXTS + r")")
ANCHOR_RE = re.compile(r"([A-Za-z0-9_.\-/]+\.(?:py|js|mjs|vbs))(::([A-Za-z0-9_*]+))(::([A-Za-z0-9_*]+))?")
LINE_RE = re.compile(r"([A-Za-z0-9_.\-/]+\.(?:" + REF_EXTS + r")):(\d+)")
BACKTICK_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z0-9_]+)*)`")
JS_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", flags=re.S)


PLACEHOLDER_RE = re.compile(r"(?:^|/)(?:x|xx|xxx|test_x|sample|example|foo|bar|template)[-_.]?\w*\.(?:py|js|mjs|vbs)$", re.I)


def iter_files(root: Path, exts):
    for p in sorted(root.rglob("*")):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if any(p.match(pattern) for pattern in SKIP_GLOBS):
            continue
        if p.is_file() and p.suffix.lower() in exts:
            yield p


def read(path: Path) -> str:
    # BOM-aware: a UTF-16LE VBS decoded as UTF-8 becomes NUL-separated noise and its comments
    # are never scanned, so the scanner silently loses the whole file.
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def blank_code_keep_comments(src: str) -> str:
    # Replace code with same-length spaces so comment spans keep their original offsets.
    out: list[str] = []
    i, n = 0, len(src)
    in_str: str | None = None
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if in_str:
            out.append(" ")
            if c == "\\" and nxt:
                out.append(" ")
                i += 2
                continue
            if c == in_str or c == "\n":
                in_str = None
            i += 1
            continue
        if c in "\"'`":
            in_str = c
            out.append(" ")
            i += 1
            continue
        if c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(src[i:j])
            i = j
            continue
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(src[i:j])
            i = j
            continue
        out.append(c if c == "\n" else " ")
        i += 1
    return "".join(out)


def blank_comments_drop_code(src: str) -> str:
    # Opposite mask: comments removed, code kept -- what a comment edit must not change.
    out: list[str] = []
    i, n, in_block = 0, len(src), False
    in_str: str | None = None
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if in_block:
            if c == "*" and nxt == "/":
                in_block = False
                i += 2
                continue
            out.append("\n" if c == "\n" else "")
            i += 1
            continue
        if in_str:
            out.append(c)
            if c == "\\" and nxt:
                out.append(nxt)
                i += 2
                continue
            if c == in_str or c == "\n":
                in_str = None
            i += 1
            continue
        if c in "\"'`":
            in_str = c
            out.append(c)
            i += 1
            continue
        if c == "/" and nxt == "*":
            in_block = True
            i += 2
            continue
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def code_tokens(path: Path, text: str) -> set[str]:
    """Identifiers that exist once comments are gone -- the only set a comment may cite."""
    suf = path.suffix.lower()
    if suf == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return set()
        # Walk the AST instead of regexing ast.dump: a string constant's value (`"missing"`)
        # is data, not an identifier, and must not make a stale comment anchor look valid.
        ids: set[str] = set()
        type_params = tuple(
            cls
            for cls in (
                getattr(ast, "TypeVar", None),
                getattr(ast, "ParamSpec", None),
                getattr(ast, "TypeVarTuple", None),
            )
            if cls is not None
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                ids.add(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                ids.add(node.name)
            elif isinstance(node, ast.arg):
                ids.add(node.arg)
            elif isinstance(node, ast.alias):
                ids.add(node.asname or node.name.split(".")[0])
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                ids.update(node.names)
            elif isinstance(node, ast.Attribute):
                ids.add(node.attr)
            elif isinstance(node, ast.keyword) and node.arg:
                ids.add(node.arg)
            elif isinstance(node, ast.ExceptHandler) and isinstance(node.name, str):
                ids.add(node.name)
            elif type_params and isinstance(node, type_params):
                ids.add(node.name)
            elif isinstance(node, ast.MatchAs) and node.name:
                ids.add(node.name)
            elif isinstance(node, ast.MatchStar) and node.name:
                ids.add(node.name)
            elif isinstance(node, ast.MatchMapping) and node.rest:
                ids.add(node.rest)
        return ids
    if suf in (".vbs",):
        return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))
    return set(re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", blank_comments_drop_code(text)))


def comments_with_lines(path: Path, text: str) -> list[tuple[int, str]]:
    suf = path.suffix.lower()
    if suf == ".py":
        try:
            toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return [(text.count("\n", 0, m.start()) + 1, m.group(0))
                    for m in re.finditer(r"^[ \t]*#.*$", text, flags=re.M)]
        return [(t.start[0], t.string) for t in toks if t.type == tokenize.COMMENT]
    if suf in (".js", ".mjs", ".cjs", ".ts", ".css", ".scss"):
        masked = blank_code_keep_comments(text)
        return [(text.count("\n", 0, m.start()) + 1, m.group(0)) for m in JS_COMMENT_RE.finditer(masked)]
    if suf in (".html", ".htm"):
        return [(text.count("\n", 0, m.start()) + 1, m.group(0)) for m in re.finditer(r"<!--.*?-->", text, flags=re.S)]
    if suf == ".vbs":
        out = []
        for idx, line in enumerate(text.splitlines(), start=1):
            if line.strip().startswith("'") or line.strip().upper().startswith("REM "):
                out.append((idx, line))
        return out
    return []


def norm_rel(token: str) -> str:
    tok = token.replace("\\", "/")
    while tok.startswith("./"):
        tok = tok[2:]
    return tok.lstrip("/")


def main() -> int:
    ap = argparse.ArgumentParser(description="comment-reference integrity scanner")
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--paths", nargs="*", default=None, help="only scan comments in these files/dirs")
    ap.add_argument("--strict", action="store_true", help="exit 1 when HIGH findings exist")
    ap.add_argument("--limit", type=int, default=60, help="max findings printed per bucket")
    ap.add_argument("--show-low", action="store_true", help="also print bare-filename mentions")
    ap.add_argument("--show-ok-count", action="store_true", help="also print how many references resolved")
    args = ap.parse_args()

    repo = args.repo.resolve()
    universe_paths: set[str] = set()
    for p in repo.rglob("*"):
        if p.is_file() and not any(part in EXCLUDE_DIRS for part in p.relative_to(repo).parts):
            universe_paths.add(p.relative_to(repo).as_posix())
    basenames = {p.rsplit("/", 1)[-1] for p in universe_paths}
    top_levels = {p.split("/", 1)[0] for p in universe_paths}
    suffix_map: dict[str, set[str]] = {}
    for p in universe_paths:
        parts = p.split("/")
        for k in range(len(parts)):
            suffix_map.setdefault("/".join(parts[k:]), set()).add(p)

    def resolve(tgt: str) -> str | None:
        # Comments often cite a partial path (`ui_i18n.py`, `sync_version.py::check_all`);
        # accept it only when exactly one repo file ends with that suffix.
        if tgt in universe_paths:
            return tgt
        cands = suffix_map.get(tgt)
        return next(iter(cands)) if cands and len(cands) == 1 else None

    src_files = list(iter_files(repo, SRC_EXTS))
    universe_ids: set[str] = set()
    line_counts: dict[str, int] = {}
    token_cache: dict[str, set[str]] = {}
    for p in src_files:
        text = read(p)
        rel = p.relative_to(repo).as_posix()
        ids = code_tokens(p, text)
        token_cache[rel] = ids
        universe_ids |= ids
        line_counts[rel] = text.count("\n") + 1

    targets = src_files
    if args.paths:
        targets = []
        for raw in args.paths:
            p = Path(raw)
            p = p if p.is_absolute() else repo / raw
            if p.is_dir():
                targets.extend(iter_files(p, SRC_EXTS))
            elif p.is_file():
                targets.append(p)

    high: list[str] = []
    med: list[str] = []
    low: list[str] = []
    drift: list[str] = []
    resolved = 0

    for path in targets:
        rel = path.relative_to(repo).as_posix()
        text = read(path)
        for line, block in comments_with_lines(path, text):
            where = f"{rel}:{line}"
            for m in ANCHOR_RE.finditer(block):
                fpath, _, mid, _, leaf = m.groups()
                tgt = resolve(norm_rel(fpath))
                if tgt is None:
                    if PLACEHOLDER_RE.search(norm_rel(fpath)):
                        med.append(f"[anchor] {where}: {m.group(0)} (placeholder name)")
                    else:
                        high.append(f"[anchor] {where}: {m.group(0)} (file not found)")
                    continue
                ids = token_cache.get(tgt)
                if ids is None:
                    ids = code_tokens(repo / tgt, read(repo / tgt))

                def hit(name: str) -> bool:
                    if name.endswith("*"):
                        stem = name.rstrip("*")
                        return any(sid == stem or sid.startswith(stem) for sid in ids) or name in universe_ids
                    return name in ids or name in universe_ids

                segs = [s for s in (mid, leaf) if s]
                missing = [s for s in segs if not hit(s)]
                if missing:
                    high.append(f"[anchor] {where}: {m.group(0)} (missing {'/'.join(missing)})")
                else:
                    resolved += 1
            for m in LINE_RE.finditer(block):
                raw, num = norm_rel(m.group(1)), int(m.group(2))
                tgt = resolve(raw)
                if tgt is None:
                    if "/" in raw and raw.split("/")[0] not in top_levels:
                        med.append(f"[line-anchor] {where}: {m.group(0)} (not a repo root)")
                    else:
                        high.append(f"[line-anchor] {where}: {m.group(0)} (file not found)")
                elif (cap := line_counts.get(tgt)) and num > cap:
                    high.append(f"[line-anchor] {where}: {m.group(0)} (file has {cap} lines)")
                else:
                    drift.append(f"[drift-prone] {where}: {m.group(0)}")
            for m in PATH_RE.finditer(block):
                tok = m.group(0)
                if tok.lower() in PROSE_NAMES or "::" in tok:
                    continue
                if re.search(r"\.(?:py|js|mjs|css|html|md)/", tok):
                    continue  # chained mention like main.py/web.py/gui.py
                tgt = norm_rel(tok)
                if "/" in tok:
                    if resolve(tgt):
                        resolved += 1
                    elif tok.split("/")[0] in top_levels:
                        if PLACEHOLDER_RE.search(tgt):
                            med.append(f"[path] {where}: {tok} (placeholder name)")
                        else:
                            high.append(f"[path] {where}: {tok} (repo path not found)")
                    else:
                        med.append(f"[external-path] {where}: {tok} (not a repo root; likely external or generated)")
                elif tgt in basenames:
                    resolved += 1
                else:
                    low.append(f"[bare-name] {where}: {tok}")
            for m in BACKTICK_RE.finditer(block):
                tok = m.group(1)
                if IGNORE_WORDS.match(tok):
                    continue
                if "::" in tok:
                    head, _, tail = tok.partition("::")
                    tgt = resolve(norm_rel(head))
                    if tgt:
                        ids = token_cache.get(tgt, universe_ids)
                        if tail in ids or tail in universe_ids:
                            resolved += 1
                        else:
                            high.append(f"[symbol] {where}: {tok}")
                        continue
                    high.append(f"[symbol] {where}: {tok} (file not found)")
                    continue
                if tok in universe_ids:
                    resolved += 1
                else:
                    low.append(f"[bare-symbol] {where}: {tok}")

    print(f"scanned {len(targets)} files" + (f"; resolved {resolved} references" if args.show_ok_count else ""))
    if drift:
        print(f"\nline-number anchors (drift on any insert/delete): {len(drift)}")
        for item in drift[: args.limit]:
            print("  " + item)
    if high:
        print(f"\nHIGH -- provably stale or invented references: {len(high)}")
        for item in high[: args.limit]:
            print("  " + item)
        if len(high) > args.limit:
            print(f"  ... {len(high) - args.limit} more (raise --limit)")
    else:
        print("\nHIGH: none")
    if med:
        print(f"\nMED -- outside the repo tree or placeholder names (verify by hand): {len(med)}")
        for item in med[: args.limit]:
            print("  " + item)
    if low:
        print(f"\nLOW -- needs context (repeat with --show-low to list): {len(low)}")
        if args.show_low:
            for item in low[: args.limit]:
                print("  " + item)
    return 1 if (args.strict and high) else 0


if __name__ == "__main__":
    sys.exit(main())
