#!/usr/bin/env python3
# 全仓只读审查的基线快照与只读自证（标准库，Python 3.14）。
#
# snapshot：记录 HEAD/分支/工作区状态、逐跟踪文件 sha256、HEAD 与工作区的冲突块、
#           AST 解析失败、按分区的文件/行数。输出只写 --out（默认 %TEMP%），拒绝写入仓库。
# verify：  重算清单并报告 changed/added/removed，用于证明审查期除报告外未改仓库。
#
# 退出码：0 成功；1 脚本或 git 错误；2 verify 检测到漂移。

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SCHEMA = 1

TEXT_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".mjs",
    ".html",
    ".css",
    ".md",
    ".toml",
    ".ini",
    ".yaml",
    ".yml",
    ".sh",
    ".vbs",
    ".proto",
    ".json",
    ".txt",
    ".cfg",
}

AREA_ORDER = [
    "根目录",
    "src 顶层",
    "src/gui_qt",
    "src/platforms",
    "src/proto",
    "src/javascript",
    "web",
    "scripts",
    "tests",
    "tests/frontend",
    "typings",
    ".github",
    "config",
    "docs",
    "其他",
]

SRC_SUBDIRS = {"src/gui_qt", "src/platforms", "src/proto", "src/javascript"}
TOP_DIRS = {"web", "scripts", "tests", "typings", ".github", "config", "docs"}


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                pass


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def _git(root: Path, *args: str, allow_rc: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    proc = _run(["git", *args], root)
    if proc.returncode not in allow_rc:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"git {' '.join(args)} rc={proc.returncode}: {detail[:500]}")
    return proc


def _repo_root(start: Path) -> Path:
    proc = _run(["git", "rev-parse", "--show-toplevel"], start)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"当前目录不在 git 仓库内: {start} ({detail[:200]})")
    return Path(proc.stdout.strip()).resolve()


def _tracked_files(root: Path) -> list[str]:
    proc = _git(root, "ls-files", "-z")
    return sorted(item for item in proc.stdout.split("\0") if item)


def _untracked_files(root: Path) -> list[str]:
    # 预存未跟踪文件也必须进基线：它们同样是只读承诺的一部分，且常是并发包的在途产物。
    proc = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted(item for item in proc.stdout.split("\0") if item)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _line_count(path: Path) -> int | None:
    # None = 二进制（前 8 KiB 含 NUL）；行数按字节数 \n，避免解码差异影响读数。
    with open(path, "rb") as fh:
        head = fh.read(8192)
        if b"\x00" in head:
            return None
        fh.seek(0)
        raw = fh.read()
    if not raw:
        return 0
    return raw.count(b"\n") + (0 if raw.endswith(b"\n") else 1)


def _area(rel: str) -> str:
    parts = PurePosixPath(rel).parts
    if not parts:
        return "其他"
    if parts[0] == "src":
        if len(parts) >= 2:
            key = f"src/{parts[1]}"
            if key in SRC_SUBDIRS:
                return key
        return "src 顶层"
    if parts[0] in TOP_DIRS:
        if parts[0] == "tests" and len(parts) >= 2 and parts[1] == "frontend":
            return "tests/frontend"
        return parts[0]
    if len(parts) == 1:
        return "根目录"
    return "其他"


def _conflict_stats(root: Path, rev: str | None = None) -> dict[str, object]:
    args = ["git", "grep", "-c", "^<<<<<<< "]
    if rev:
        args.append(rev)
    proc = _git(root, *args, allow_rc=(0, 1))
    rows: list[tuple[str, int]] = []
    for line in proc.stdout.splitlines():
        path, sep, count = line.rpartition(":")
        if not sep:
            continue
        try:
            rows.append((path, int(count)))
        except ValueError:
            continue
    rows.sort(key=lambda item: (-item[1], item[0]))
    return {
        "blocks": sum(count for _, count in rows),
        "files": len(rows),
        "top": [{"path": path, "blocks": count} for path, count in rows[:10]],
    }


def _ast_census(root: Path, files: list[str]) -> dict[str, object]:
    ok = 0
    broken: list[str] = []
    for rel in files:
        if not rel.endswith(".py"):
            continue
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8-sig", errors="replace")
            ast.parse(text, filename=rel)
        except SyntaxError as exc:
            broken.append(f"{rel}:{exc.lineno}: {exc.msg}")
        except ValueError as exc:
            broken.append(f"{rel}: {exc}")
        else:
            ok += 1
    return {"ok": ok, "broken": len(broken), "broken_files": broken[:50]}


def _status_entries(root: Path) -> list[str]:
    proc = _git(root, "status", "--porcelain=v1", "-z")
    return [entry for entry in proc.stdout.split("\0") if entry]


def _default_out() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(tempfile.gettempdir()) / f"dlr-review-snapshot-{stamp}"


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def cmd_snapshot(args: argparse.Namespace) -> int:
    root = _repo_root(Path.cwd())
    out = Path(args.out).expanduser().resolve() if args.out else _default_out().resolve()
    if _is_within(out, root):
        raise RuntimeError(f"拒绝写入仓库内: {out}（基线必须落在仓库之外，默认 %TEMP%）")

    tracked = set(_tracked_files(root))
    untracked = _untracked_files(root)
    files = sorted(tracked | set(untracked))
    manifest: dict[str, dict[str, object]] = {}
    totals: dict[str, dict[str, int]] = {}
    missing_tracked: list[str] = []
    for rel in files:
        path = root / rel
        area = _area(rel)
        acc = totals.setdefault(area, {"files": 0, "lines": 0})
        acc["files"] += 1
        if not path.is_file():
            # 索引里有、工作区没有：仍要进 manifest，否则 verify 会把它误报成「新增」。
            missing_tracked.append(rel)
            manifest[rel] = {"sha256": None, "size": None, "tracked": rel in tracked, "missing": True}
            continue
        manifest[rel] = {
            "sha256": _hash_file(path),
            "size": path.stat().st_size,
            "tracked": rel in tracked,
        }
        if PurePosixPath(rel).suffix.lower() in TEXT_SUFFIXES:
            lines = _line_count(path)
            if lines is not None:
                acc["lines"] += lines

    head = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    status = _status_entries(root)
    facts: dict[str, object] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": root.as_posix(),
        "head": head,
        "branch": branch,
        "tracked_files": len(tracked),
        "untracked_files": len(untracked),
        "missing_tracked": missing_tracked,
        "status_entries": len(status),
        "status_sample": status[:200],
        "untracked": untracked[:200],
        "conflicts": {
            "head": _conflict_stats(root, "HEAD"),
            "worktree": _conflict_stats(root),
        },
        "ast": _ast_census(root, sorted(manifest)),
        "inventory": [
            {"area": area, "files": totals[area]["files"], "lines": totals[area]["lines"]}
            for area in AREA_ORDER
            if area in totals
        ],
    }
    manifest_payload: dict[str, object] = {
        "schema": SCHEMA,
        "generated_at": facts["generated_at"],
        "repo_root": facts["repo_root"],
        "head": head,
        "branch": branch,
        "files": manifest,
    }

    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    facts_path = out / "facts.json"
    _write_json(manifest_path, manifest_payload)
    _write_json(facts_path, facts)

    conflicts = facts["conflicts"]
    assert isinstance(conflicts, dict)
    head_conf = conflicts["head"]
    work_conf = conflicts["worktree"]
    ast_info = facts["ast"]
    assert isinstance(head_conf, dict) and isinstance(work_conf, dict) and isinstance(ast_info, dict)

    print(f"SNAPSHOT {out.as_posix()}")
    print(f"MANIFEST {manifest_path.as_posix()}")
    print(f"FACTS    {facts_path.as_posix()}")
    print(
        f"HEAD {head} branch {branch} tracked={len(tracked)} untracked={len(untracked)} "
        f"manifest={len(manifest)} missing_tracked={len(missing_tracked)} status_entries={len(status)}"
    )
    print(
        f"CONFLICTS head blocks={head_conf['blocks']} files={head_conf['files']} | "
        f"worktree blocks={work_conf['blocks']} files={work_conf['files']}"
    )
    print(f"AST ok={ast_info['ok']} broken={ast_info['broken']}")
    print("INVENTORY")
    for row in facts["inventory"]:
        assert isinstance(row, dict)
        print(f"  {row['area']:<16} files={row['files']:<5} lines={row['lines']}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = _repo_root(Path.cwd())
    manifest_path = Path(args.manifest).expanduser().resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, dict):
        raise RuntimeError(f"manifest 缺少 files 对象: {manifest_path}")

    changed: list[str] = []
    removed: list[str] = []
    for rel, entry in files.items():
        path = root / rel
        was_missing = isinstance(entry, dict) and entry.get("missing") is True
        if not path.is_file():
            if not was_missing:
                removed.append(rel)
            continue
        if was_missing:
            changed.append(rel)
            continue
        expected = entry.get("sha256") if isinstance(entry, dict) else None
        if not isinstance(expected, str) or _hash_file(path) != expected:
            changed.append(rel)

    current = set(_tracked_files(root)) | set(_untracked_files(root))
    added = sorted(current - set(files))
    patterns = [PurePosixPath(item.replace("\\", "/")).as_posix() for item in (args.allow_added or [])]
    unexpected = [
        rel for rel in added if not any(fnmatch.fnmatch(PurePosixPath(rel).as_posix(), pat) for pat in patterns)
    ]

    def _print_list(label: str, rows: list[str]) -> None:
        print(f"{label} {len(rows)}")
        for rel in rows[:50]:
            print(f"  {rel}")
        if len(rows) > 50:
            print(f"  ... {len(rows) - 50} more")

    print(f"MANIFEST {manifest_path.as_posix()}")
    print(f"HEAD_NOW {_git(root, 'rev-parse', '--short', 'HEAD').stdout.strip()}")
    _print_list("CHANGED", sorted(changed))
    _print_list("REMOVED", sorted(removed))
    _print_list("ADDED", added)
    if patterns:
        print(f"ALLOWED_PATTERNS {patterns}")
    _print_list("UNEXPECTED_ADDED", unexpected)
    drift = bool(changed or removed or unexpected)
    print(f"RESULT {'DRIFT' if drift else 'PASS'}")
    return 2 if drift else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="全仓只读审查的基线快照与只读自证（只写仓库之外）。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="记录基线并写 manifest.json / facts.json")
    snapshot.add_argument(
        "--out",
        default=None,
        help="输出目录；必须在仓库之外。默认 %%TEMP%%/dlr-review-snapshot-<UTC 时间戳>。",
    )
    snapshot.set_defaults(func=cmd_snapshot)

    verify = sub.add_parser("verify", help="重算 manifest 并报告 changed/added/removed")
    verify.add_argument("--manifest", required=True, help="snapshot 生成的 manifest.json")
    verify.add_argument(
        "--allow-added",
        action="append",
        default=[],
        help="允许新增的路径，可重复，支持通配（例如 docs/worklog/CODE_REVIEW_*.md）。",
    )
    verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
