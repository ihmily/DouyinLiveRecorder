#!/usr/bin/env python3
# Prove a comment-only refactor left executable content untouched, file by file.
#
# Three independent metrics per file, because each one is blind to a different class of
# damage: (1) structural signature -- ast.dump for Python, comment-stripped code-line
# sequences for JS/CSS/HTML/VBS; (2) byte-level CRLF/LF shape, invisible to both the AST
# and most formatters; (3) parseability, so a swallowed newline that turns code into a
# comment cannot pass as "equal".
#
# Usage:
#   python verify_equivalence.py --base <baseline_dir> [--repo <root>] [path ...]
#   python verify_equivalence.py --base <baseline_dir>            # whole baseline set
#   python verify_equivalence.py --base <baseline_dir> --allow-skips
#
# A file with no baseline is a FAILURE by default: a snapshot that silently skipped the file
# proves nothing about it. `--allow-skips` downgrades that to a printed SKIP for known exclusions.
# Encoding is detected from the BOM (UTF-8 / UTF-16LE / UTF-16BE) before EOL comparison, because
# byte-level CRLF detection cannot see line endings inside UTF-16 text.
# Exit 0 only when every checked file passes all metrics.

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

SUPPORTED = (".py", ".js", ".mjs", ".cjs", ".ts", ".css", ".scss", ".html", ".htm", ".vbs", ".vba")


def strip_c_style(src: str) -> list[str]:
    # Character scanner instead of a regex: `//` or `/*` inside a string literal must not
    # start a comment, otherwise deleting a comment would look like deleting code.
    out: list[str] = []
    buf: list[str] = []
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
            i += 1
            continue
        if in_str:
            buf.append(c)
            if c == "\\" and nxt:
                buf.append(nxt)
                i += 2
                continue
            if c == in_str:
                in_str = None
            if c == "\n":
                in_str = None
            i += 1
            continue
        if c in "\"'`":
            in_str = c
            buf.append(c)
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
        if c == "\n":
            line = "".join(buf).strip()
            buf = []
            if line:
                out.append(line)
            i += 1
            continue
        buf.append(c)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def strip_html(src: str) -> list[str]:
    import re

    body = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    return [line.strip() for line in body.splitlines() if line.strip()]


def strip_vbs(src: str) -> list[str]:
    out = []
    for line in src.splitlines():
        s = line.strip()
        if s and not s.startswith("'") and not s.upper().startswith("REM "):
            out.append(s)
    return out


def signature(path: Path, text: str):
    suf = path.suffix.lower()
    if suf == ".py":
        return ast.dump(ast.parse(text), include_attributes=False)
    if suf in (".js", ".mjs", ".cjs", ".ts"):
        return strip_c_style(text)
    if suf in (".css", ".scss"):
        return strip_c_style(text)
    if suf in (".html", ".htm"):
        return strip_html(text)
    if suf in (".vbs", ".vba"):
        return strip_vbs(text)
    return None  # unknown type: fall back to exact bytes


def decode_source(data: bytes) -> tuple[str, str, bool]:
    # Treating a UTF-16 file as UTF-8 yields NUL-laden text, so both the AST and the EOL profile
    # become meaningless. Detect the BOM first; the returned label is part of the comparison.
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16"), "utf-16-le", True
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16-be", True
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8", True
    return data.decode("utf-8"), "utf-8", False


def encoding_label(encoding: str, bom: bool) -> str:
    return f"{encoding}{'+bom' if bom else ''}"


def eol_shape_text(text: str) -> tuple[str, str]:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    kinds = [name for name, count in (("crlf", crlf), ("lf", lf), ("cr", cr)) if count]
    if len(kinds) > 1:
        return (kinds[0], "mixed")
    return (kinds[0] if kinds else "none", "pure")


def read_text(path: Path) -> tuple[str, str, bool]:
    return decode_source(path.read_bytes())


def compare_pair(current: Path, baseline: Path) -> tuple[bool, list[str]]:
    # One comparison entry point, used by the CLI and by refactor_guard.py, so the two tools
    # cannot drift on what "equivalent" means.
    current_data, baseline_data = current.read_bytes(), baseline.read_bytes()
    try:
        current_text, current_encoding, current_bom = decode_source(current_data)
        baseline_text, baseline_encoding, baseline_bom = decode_source(baseline_data)
    except UnicodeDecodeError:
        if current_data == baseline_data:
            return True, []
        return False, ["bytes differ (binary or not UTF-8/UTF-16)"]

    reasons: list[str] = []
    current_label = encoding_label(current_encoding, current_bom)
    baseline_label = encoding_label(baseline_encoding, baseline_bom)
    if current_label != baseline_label:
        reasons.append(f"encoding {baseline_label} -> {current_label}")

    try:
        current_signature = signature(current, current_text)
        baseline_signature = signature(baseline, baseline_text)
    except SyntaxError as exc:
        return False, [f"syntax error: {exc}"]

    if current_signature is None or baseline_signature is None:
        if current_data != baseline_data:
            reasons.append("bytes differ (unknown file type)")
    elif current_signature != baseline_signature:
        reasons.append("signature differs -> executable content changed")

    current_eol = eol_shape_text(current_text)
    baseline_eol = eol_shape_text(baseline_text)
    if current_eol != baseline_eol:
        reasons.append(f"EOL shape {baseline_eol} -> {current_eol}")
    return not reasons, reasons


def collect_pairs(repo: Path, base: Path, targets: list[str]) -> list[tuple[Path, Path]]:
    if targets:
        rels = []
        for raw in targets:
            p = (repo / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
            try:
                rel = p.relative_to(repo)
            except ValueError:
                print(f"SKIP(outside repo) {raw}")
                continue
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file() and f.suffix.lower() in SUPPORTED:
                        rels.append(f.relative_to(repo))
            else:
                rels.append(rel)
        return [(repo / r, base / r) for r in dict.fromkeys(rels)]
    # Whole-baseline mode: only compare file types this tool knows how to judge. The snapshot may
    # also contain manifest.json or docs; treating those as deleted code files is a false alarm.
    rels = [
        f.relative_to(base)
        for f in sorted(base.rglob("*"))
        if f.is_file() and f.suffix.lower() in SUPPORTED
    ]
    return [(repo / r, base / r) for r in rels]


def main() -> int:
    ap = argparse.ArgumentParser(description="comment-only equivalence verifier")
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root (default: cwd)")
    ap.add_argument("--base", type=Path, required=True, help="baseline snapshot directory")
    ap.add_argument("--quiet", action="store_true", help="only print failures and the summary")
    ap.add_argument("--allow-skips", action="store_true", help="downgrade a missing baseline to SKIP")
    ap.add_argument("targets", nargs="*", help="files or directories to check (default: whole baseline)")
    args = ap.parse_args()

    repo, base = args.repo.resolve(), args.base.resolve()
    if not base.is_dir():
        print(f"FAIL: baseline directory not found: {base}")
        return 1

    ok = bad = skipped = 0
    for cur, old in collect_pairs(repo, base, args.targets):
        rel = cur.relative_to(repo).as_posix()
        if not cur.exists():
            print(f"FAIL(deleted) {rel}")
            bad += 1
            continue
        if not old.exists():
            message = f"no baseline: {rel}"
            if args.allow_skips:
                print(f"SKIP({message})")
                skipped += 1
            else:
                print(f"FAIL({message})")
                bad += 1
            continue
        if cur.read_bytes() == old.read_bytes():
            ok += 1
            if not args.quiet:
                print(f"OK(unchanged) {rel}")
            continue
        try:
            same, reasons = compare_pair(cur, old)
        except OSError as exc:
            print(f"FAIL(unreadable) {rel}: {exc}")
            bad += 1
            continue
        if same:
            ok += 1
            if not args.quiet:
                print(f"OK {rel}")
            continue
        # A swallowed newline turns the next code line into a comment: the file stops parsing,
        # which is reported separately from a signature mismatch by compare_pair().
        print(f"FAIL {rel}: " + "; ".join(reasons))
        bad += 1

    verdict = "ALL OK" if bad == 0 else f"{bad} FAILED"
    print(f"{verdict} -- checked {ok + bad}, ok {ok}, skipped {skipped}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
