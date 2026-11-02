#!/usr/bin/env python3
# 批量文本替换器：白名单枚举 + 字节级保留 + 改前后行尾/BOM 核对。
#
# 为什么不用 Path.read_text / Path.write_text（Python 3.14 / Windows 实测）：
#   read_text() 走通用换行，b"a\r\nb\n" 读成 "a\nb\n"；write_text() 默认 newline=None，
#   写侧把每个 "\n" 换成 os.linesep，LF-only 文件会整体变成 CRLF（整个文件每一行）。
# 本脚本只在 decode 后的 str 上替换命中串，再按原 BOM 编码写回；命中串以外的字节不动。
#
# 非 UTF-8 / 含 NUL 的文件一律跳过并报原因：按猜的编码回写会把乱码写进仓库。
# 默认 dry-run；只打印不改盘。--apply 才落盘，且失败的文件单列、不写。
#
# 退出码：0 成功（含 dry-run）；1 安全断言失败（行尾形态翻转 / 命中数不符）；
#         2 用法或 IO 错误。

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

# 默认拒绝的目录名：gitignore 的忽略目录用 git status 看不见，越界后不可还原。
# 这些是踩过的具体形态（hook 基线、会话产物、代理缓存、运行期产物、构建输出）。
# 需要动其中之一时显式传 --allow-ignored，并自行承担不可还原的后果。
DEFAULT_EXCLUDE_DIRS = (
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mimosa",
    ".workbuddy",
    ".qoder-credits",
    ".qoder",
    ".zcode",
    "downloads",
    "recordings",
    "logs",
    "backup_config",
    "build",
    "dist",
)

UTF8_BOM = b"\xef\xbb\xbf"


def eol_profile(data: bytes) -> dict[str, int]:
    # 直接用字节计数：先数 \r\n，剩下的 \n / \r 才是孤立形态（解码后计数会被文本替换干扰）。
    crlf = data.count(b"\r\n")
    return {
        "crlf": crlf,
        "lf_only": data.count(b"\n") - crlf,
        "cr_only": data.count(b"\r") - crlf,
    }


def eol_style(profile: dict[str, int]) -> tuple[bool, bool, bool]:
    # 比形态而非计数：允许命中串里故意带换行，但不允许「全 LF」被写成「全 CRLF」这类翻转。
    return (profile["crlf"] > 0, profile["lf_only"] > 0, profile["cr_only"] > 0)


def _git(root: Path, args: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, check=False)


def paths_from_git(root: Path, include_untracked: bool) -> list[str]:
    args = ["ls-files", "-z"]
    if include_untracked:
        # --exclude-standard 会剔掉 .gitignore 命中项；已跟踪文件不受 ignore 影响。
        args += ["--others", "--exclude-standard"]
    got = _git(root, args)
    if got.returncode != 0:
        raise SystemExit(f"git ls-files 失败：{got.stderr.decode('utf-8', 'replace').strip()}")
    return [p for p in got.stdout.decode("utf-8", "replace").split("\0") if p]


def ignored_paths(root: Path, paths: list[str]) -> set[str]:
    # git check-ignore 是「这条路径是否被忽略」的唯一权威；手写目录黑名单只能兜底。
    if not paths:
        return set()
    payload = "".join(p + "\0" for p in paths).encode("utf-8")
    got = _git(root, ["check-ignore", "--stdin", "-z"], stdin=payload)
    if got.returncode not in (0, 1):  # 128 = 非 git 仓库等，交给目录黑名单兜底
        return set()
    return {p for p in got.stdout.decode("utf-8", "replace").split("\0") if p}


def paths_from_file(path: Path) -> list[str]:
    # 白名单文件按行读，空行跳过；不做注释语法（路径本身可能含 #）。
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip()]


def collect(args: argparse.Namespace) -> tuple[Path, list[str]]:
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"--root 不是目录：{root}")
    if args.git:
        return root, paths_from_git(root, args.include_untracked)
    if args.files_from is not None:
        return root, paths_from_file(args.files_from)
    return root, list(args.files or [])


def make_replacer(args: argparse.Namespace):
    if args.regex:
        pattern = re.compile(args.pattern)
        return lambda text: pattern.subn(lambda _m: args.replacement, text)
    needle = args.pattern

    def literal(text: str) -> tuple[str, int]:
        return text.replace(needle, args.replacement), text.count(needle)

    return literal


def classify(root: Path, raw_paths: list[str], args: argparse.Namespace):
    # 分三桶：处理、过滤、拒绝。拒绝必须逐条报出原因——静默丢弃候选等于缩小白名单而不自知。
    usable: list[tuple[Path, str]] = []
    refused: list[tuple[str, str]] = []
    filtered = 0
    ignored = set() if args.allow_ignored else ignored_paths(root, raw_paths)
    seen: set[str] = set()
    for raw in raw_paths:
        rel = raw.replace("\\", "/")
        if rel in seen:
            continue
        seen.add(rel)
        if args.include and not any(fnmatch.fnmatch(rel, g) for g in args.include):
            filtered += 1
            continue
        if not args.allow_ignored:
            if rel in ignored:
                refused.append((rel, "git-ignored"))
                continue
            if any(part in DEFAULT_EXCLUDE_DIRS for part in Path(rel).parts[:-1]):
                refused.append((rel, "excluded-dir"))
                continue
        path = (root / rel).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            refused.append((rel, "outside-root"))
            continue
        if path.is_symlink():
            refused.append((rel, "symlink"))
            continue
        if not path.is_file():
            refused.append((rel, "not-a-file"))
            continue
        usable.append((path, rel))
    return usable, refused, filtered


def rewrite_one(path: Path, rel: str, replace, apply: bool) -> tuple[str, dict]:
    raw = path.read_bytes()
    if b"\x00" in raw:
        return "skipped", {"path": rel, "reason": "binary-nul"}
    bom = raw.startswith(UTF8_BOM)
    try:
        text = raw.decode("utf-8-sig" if bom else "utf-8")
    except UnicodeDecodeError as exc:
        return "skipped", {"path": rel, "reason": f"not-utf8: {exc.reason} at byte {exc.start}"}
    new_text, hits = replace(text)
    if hits == 0:
        return "unchanged", {"path": rel, "hits": 0}
    new_raw = ((UTF8_BOM + new_text.encode("utf-8")) if bom else new_text.encode("utf-8"))
    before, after = eol_profile(raw), eol_profile(new_raw)
    if eol_style(before) != eol_style(after):
        # 形态翻转一律拒写：这类损坏不会被 black / pytest 发现，只会进 git diff。
        return "failed", {
            "path": rel,
            "reason": "eol-style-flip",
            "before": before,
            "after": after,
        }
    if apply:
        path.write_bytes(new_raw)
    return "changed", {"path": rel, "hits": hits, "before": before, "after": after, "bom": bom}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="白名单驱动的批量文本替换（默认 dry-run）。")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--git", action="store_true", help="白名单取自 git ls-files（已跟踪文件）")
    src.add_argument("--files-from", type=Path, help="白名单文件，每行一个路径")
    src.add_argument("--files", nargs="+", help="显式路径白名单")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="仓库根，路径相对它解析")
    ap.add_argument("--include", action="append", default=[], help="fnmatch 过滤（相对 posix 路径），可重复")
    ap.add_argument("--pattern", required=True, help="被替换的文本（默认按字面量）")
    ap.add_argument("--replacement", required=True, help="替换成的文本")
    ap.add_argument("--regex", action="store_true", help="把 --pattern 当正则（替换串不做 \\1 展开）")
    ap.add_argument("--expect-changed", type=int, help="预期命中文件数；不符即 rc=1")
    ap.add_argument("--apply", action="store_true", help="落盘；缺省只做 dry-run")
    ap.add_argument("--include-untracked", action="store_true", help="--git 模式下并入未跟踪且未被忽略的文件")
    ap.add_argument("--allow-ignored", action="store_true", help="关闭忽略过滤（不可还原，慎用）")
    ap.add_argument("--json", type=Path, help="把完整报告写成 JSON")
    args = ap.parse_args(argv)

    root, raw_paths = collect(args)
    usable, refused, filtered = classify(root, raw_paths, args)
    replace = make_replacer(args)

    buckets: dict[str, list[dict]] = {"changed": [], "unchanged": [], "skipped": [], "failed": []}
    for path, rel in usable:
        kind, info = rewrite_one(path, rel, replace, args.apply)
        buckets[kind].append(info)

    mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
    print(f"{mode}  root={root}")
    print(
        f"candidates={len(raw_paths)} usable={len(usable)} filtered={filtered} "
        f"refused={len(refused)} changed={len(buckets['changed'])} "
        f"unchanged={len(buckets['unchanged'])} skipped={len(buckets['skipped'])} "
        f"failed={len(buckets['failed'])}"
    )

    # 完整清单是事后审计的唯一输入：只给计数，越界就没法被发现。
    if buckets["changed"]:
        print(f"--- changed ({len(buckets['changed'])}) ---")
        for info in buckets["changed"]:
            b, a = info["before"], info["after"]
            print(
                f"  {info['path']}  hits={info['hits']}  "
                f"crlf {b['crlf']}->{a['crlf']}  lf_only {b['lf_only']}->{a['lf_only']}"
                + ("  bom" if info["bom"] else "")
            )
    if buckets["skipped"]:
        print(f"--- skipped ({len(buckets['skipped'])}) ---")
        for info in buckets["skipped"]:
            print(f"  {info['path']}  {info['reason']}")
    if buckets["failed"]:
        print(f"--- failed ({len(buckets['failed'])}) ---")
        for info in buckets["failed"]:
            print(f"  {info['path']}  {info['reason']}  before={info['before']} after={info['after']}")
    if refused:
        print(f"--- refused ({len(refused)}) ---")
        for rel, reason in refused:
            print(f"  {rel}  {reason}")

    rc = 1 if buckets["failed"] else 0
    if args.expect_changed is not None and len(buckets["changed"]) != args.expect_changed:
        print(
            f"ASSERT FAILED: --expect-changed {args.expect_changed}, "
            f"actual {len(buckets['changed'])}",
            file=sys.stderr,
        )
        rc = 1

    if args.json is not None:
        report = {
            "root": str(root),
            "applied": args.apply,
            "pattern": args.pattern,
            "replacement": args.replacement,
            "counts": {
                "candidates": len(raw_paths),
                "usable": len(usable),
                "filtered": filtered,
                "refused": len(refused),
                **{k: len(v) for k, v in buckets.items()},
            },
            "buckets": buckets,
            "refused": [{"path": p, "reason": r} for p, r in refused],
        }
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report: {args.json}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
