#!/usr/bin/env python3
"""Scope table + sha256 baseline for a read-only full-repo review.

Default mode prints an area x files x lines table and writes a baseline JSON
outside the repository (temp dir by default). `--check` re-hashes and reports
drift, which proves the review stayed read-only and surfaces concurrent edits.

Never writes inside the repository. Python 3.8+.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
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

TEXT_EXT = {
    ".py",
    ".pyi",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".vue",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".md",
    ".txt",
    ".rst",
    ".sh",
    ".bash",
    ".ps1",
    ".bat",
    ".cmd",
    ".vbs",
    ".sql",
    ".proto",
    ".po",
    ".pot",
    ".xml",
    ".gradle",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
}


def git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=str(root), capture_output=True, check=False)
    except OSError:
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout.decode("utf-8", "replace")


def is_git_repo(root: Path) -> bool:
    return git(root, "rev-parse", "--is-inside-work-tree").strip() == "true"


def list_files(root: Path, include_untracked: bool, skip: set[str]) -> list[str]:
    """Return repo-relative POSIX paths. Prefers git's index; falls back to rglob."""
    if is_git_repo(root):
        raw = git(root, "ls-files", "-z")
        if include_untracked:
            raw += git(root, "ls-files", "-z", "--others", "--exclude-standard")
        files = [p for p in raw.split("\0") if p]
        files = sorted(set(files))
    else:
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    kept = []
    for rel in files:
        if any(part in skip for part in Path(rel).parts):
            continue
        kept.append(rel)
    return kept


def group_of(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) == 1:
        return "(root)"
    first = parts[0]
    if first == "src":
        return "src/ (top-level)" if len(parts) == 2 else "src/" + parts[1]
    if first == "tests":
        if len(parts) >= 3 and parts[1] == "frontend":
            return "tests/frontend"
        return "tests/"
    return first + "/"


def measure(path: Path) -> tuple[str, int, int]:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if b"\x00" in data[:8000]:
        return digest, len(data), -1
    text = data.decode("utf-8", "replace")
    return digest, len(data), len(text.splitlines())


def build(root: Path, include_untracked: bool, skip: set[str]) -> dict:
    files = list_files(root, include_untracked, skip)
    entries: dict[str, dict] = {}
    groups: dict[str, dict] = {}
    missing = 0
    for rel in files:
        path = root / rel
        if not path.is_file():
            missing += 1
            continue
        digest, size, lines = measure(path)
        entries[rel] = {"sha256": digest, "size": size, "lines": lines}
        g = groups.setdefault(group_of(rel), {"files": 0, "text_files": 0, "lines": 0})
        g["files"] += 1
        if lines >= 0:
            g["text_files"] += 1
            g["lines"] += lines
    tracked_lines = sum(e["lines"] for e in entries.values() if e["lines"] >= 0)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "root": str(root),
        "head": git(root, "rev-parse", "--short", "HEAD").strip(),
        "dirty_files": len([x for x in git(root, "status", "--porcelain").splitlines() if x.strip()]),
        "groups": groups,
        "totals": {
            "files": len(entries),
            "text_files": sum(1 for e in entries.values() if e["lines"] >= 0),
            "lines": tracked_lines,
            "binary_files": sum(1 for e in entries.values() if e["lines"] < 0),
            "missing_on_disk": missing,
        },
        "files": entries,
    }
    return payload


def print_table(payload: dict, top: int) -> None:
    groups = payload["groups"]
    ordered = sorted(groups.items(), key=lambda kv: (-kv[1]["lines"], kv[0]))
    head = payload["head"] or "(no git)"
    print("area                          files  text  lines")
    print("-" * 48)
    shown = 0
    for name, g in ordered:
        if top and shown >= top and g["lines"] == 0:
            continue
        print(f"{name:<28} {g['files']:>6} {g['text_files']:>5} {g['lines']:>7}")
        shown += 1
    t = payload["totals"]
    print("-" * 48)
    print(f"{'TOTAL':<28} {t['files']:>6} {t['text_files']:>5} {t['lines']:>7}")
    print(
        f"head={head}  dirty_files={payload['dirty_files']}  "
        f"binary={t['binary_files']}  missing_on_disk={t['missing_on_disk']}  "
        f"at={payload['generated_at']}"
    )


def write_baseline(payload: dict, out: str | None) -> str:
    if out:
        target = Path(out)
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = Path(tempfile.gettempdir()) / f"review-baseline-{stamp}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(target)


def check(root: Path, baseline_path: Path, include_untracked: bool, skip: set[str]) -> int:
    try:
        old = json.loads(baseline_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: cannot read baseline: {exc}")
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: baseline is not valid JSON: {exc}")
        return 2
    old_files = old.get("files", {})
    cur = build(root, include_untracked, skip)
    cur_files = cur["files"]

    changed = [p for p in old_files if p in cur_files and old_files[p]["sha256"] != cur_files[p]["sha256"]]
    added = sorted(set(cur_files) - set(old_files))
    removed = sorted(set(old_files) - set(cur_files))

    print(f"baseline={baseline_path}")
    print(f"baseline_at={old.get('generated_at')}  now={cur['generated_at']}")
    print(f"changed={len(changed)}  added={len(added)}  removed={len(removed)}")
    for label, items in (("changed", changed), ("added", added), ("removed", removed)):
        for rel in items[:20]:
            print(f"  {label}: {rel}")
        if len(items) > 20:
            print(f"  {label}: ... {len(items) - 20} more")
    if not (changed or added or removed):
        print("RESULT: clean (read-only holds; no concurrent drift between snapshots)")
        return 0
    print("RESULT: drift (either concurrent edits or the review wrote something - inspect the list)")
    return 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", help="repository root (default: cwd)")
    ap.add_argument("--out", default=None, help="baseline JSON path (default: <tempdir>/review-baseline-*.json)")
    ap.add_argument("--check", default=None, metavar="BASELINE", help="re-hash and compare against a baseline")
    ap.add_argument("--include-untracked", action="store_true", help="also hash untracked, non-ignored files")
    ap.add_argument("--skip", action="append", default=[], metavar="DIR", help="extra directory name to skip")
    ap.add_argument("--json", action="store_true", help="print the full payload instead of the table")
    ap.add_argument("--no-write", action="store_true", help="do not write a baseline file")
    ap.add_argument("--top", type=int, default=40, help="max areas after the non-empty ones (0 = all)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}")
        return 2
    skip = set(DEFAULT_SKIP) | set(args.skip)

    if args.check:
        return check(root, Path(args.check).resolve(), args.include_untracked, skip)

    payload = build(root, args.include_untracked, skip)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    else:
        print_table(payload, args.top)
    if not args.no_write:
        print(f"baseline_written={write_baseline(payload, args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
