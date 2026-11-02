#!/usr/bin/env python3
# Reproducible guard rails for a comment-only refactor.
#
# `verify_equivalence.py` proves the executable content did not change. That is necessary but not
# sufficient: the remaining failures are about scope and facts.
#   snapshot  -- record what the baseline actually covers (hash, encoding, BOM, EOL, density).
#   preflight -- fail before editing when a covered file is missing, a per-file density floor is
#                already crossed, a verbatim test lock would be removed, or a code-level
#                `path.py:<line>` anchor would drift.
#   guard     -- after editing, separate a real code change from a comment-only change, and list
#                measured readings that disappeared from comments.
#
# Usage:
#   python refactor_guard.py snapshot  --repo . --base .workbuddy/<task>-base --all
#   python refactor_guard.py preflight --repo . --base .workbuddy/<task>-base
#   python refactor_guard.py guard     --repo . --base .workbuddy/<task>-base --strict-readings
#
# Exit 0 only when no FAIL remains. Stdlib only; Python >= 3.10.

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_comment_refs as ccr  # noqa: E402
import verify_equivalence as ve  # noqa: E402

MANIFEST = "manifest.json"
DEFAULT_EXTS = (".py", ".js", ".mjs", ".cjs", ".ts", ".css", ".scss", ".html", ".htm", ".vbs", ".vba")
DEFAULT_EXCLUDE_GLOBS = ("*.min.js", "*.min.css", "*.map")
EXCLUDE_DIRS = set(ccr.EXCLUDE_DIRS) | {".ruff_cache", ".tox", ".idea", ".vscode"}
MAX_BYTES = 2 * 1024 * 1024

# Ticket-like IDs used by review packages. The prefix whitelist matters: a broad
# `[A-Z]+-\d+` also matches encodings such as UTF-8 and would report a removed encoding
# name as a removed test lock.
TICKET_RE = re.compile(r"\b(?:MID|MIN|SEV|WD|CR|MI|M|S|F|L|R|W)-?\d+[A-Za-z]?\b|\bSEV-N\d+\b")
HIST_RE = re.compile(r"\[历史注[^\]]*\]?")
ANCHOR_RE = re.compile(r"([A-Za-z0-9_./\\-]+\.(?:py|js|mjs|ts|vbs)):(\d+)")
READING_RE = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?\s*(?:MB/s|KB/s|GB/s|KB|MB|GB|TB|kB|B|ms|us|μs|ns|s|秒|分钟|小时|天|%|‰|倍|次|行|个|条|项|Hz|fps)"
)
SLASH_SEQ_RE = re.compile(r"(?<![\w/])\d+(?:/\d+){1,5}(?![\w/])")


def decode_bytes(data: bytes) -> tuple[str, str, bool]:
    # EOL detection on raw bytes is wrong for UTF-16: `\r\n` is stored as 0D 00 0A 00, so a
    # UTF-16LF rewrite looks byte-identical to the UTF-16 one. Decode first, compare later.
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16"), "utf-16-le", True
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16-be", True
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8", True
    return data.decode("utf-8"), "utf-8", False


def encoding_label(encoding: str, bom: bool) -> str:
    return f"{encoding}{'+bom' if bom else ''}"


def eol_profile(text: str) -> dict[str, int | str]:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    kinds = sum(1 for count in (crlf, lf, cr) if count)
    shape = "mixed" if kinds > 1 else ("crlf" if crlf else ("lf" if lf else ("cr" if cr else "none")))
    return {"crlf": crlf, "lf": lf, "cr": cr, "shape": shape}


def comment_stats(path: Path, text: str) -> tuple[int, int, float]:
    total = len(text.splitlines())
    lines = {line for line, _ in ccr.comments_with_lines(path, text)}
    return len(lines), total, round(100.0 * len(lines) / total, 2) if total else 0.0


def record_for(repo: Path, rel: Path) -> dict:
    data = (repo / rel).read_bytes()
    text, encoding, bom = decode_bytes(data)
    comment_lines, total_lines, density = comment_stats(repo / rel, text)
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "encoding": encoding,
        "bom": bom,
        "eol": eol_profile(text),
        "comment_lines": comment_lines,
        "total_lines": total_lines,
        "density": density,
    }


def matches_glob(rel: Path, globs: tuple[str, ...] | list[str]) -> bool:
    posix = rel.as_posix()
    return any(PurePosixPath(posix).match(pattern) for pattern in globs)


def walk_files(repo: Path, start: Path, exts, exclude_globs) -> list[Path]:
    out: list[Path] = []
    for path in sorted(start.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() not in exts:
            continue
        if matches_glob(rel, exclude_globs):
            continue
        out.append(rel)
    return out


def collect_targets(repo: Path, targets: list[str], exts, use_all: bool, exclude_globs):
    selected: list[Path] = []
    skipped: list[dict[str, str]] = []
    if use_all:
        selected = walk_files(repo, repo, exts, exclude_globs)
    else:
        if not targets:
            raise SystemExit("snapshot: pass file/dir paths or --all")
        for raw in targets:
            path = Path(raw)
            path = (path if path.is_absolute() else repo / raw).resolve()
            try:
                rel = path.relative_to(repo)
            except ValueError:
                skipped.append({"path": str(path), "reason": "outside repo"})
                continue
            if path.is_dir():
                selected.extend(walk_files(repo, path, exts, exclude_globs))
            elif path.is_file():
                if any(part in EXCLUDE_DIRS for part in rel.parts):
                    skipped.append({"path": rel.as_posix(), "reason": "excluded directory"})
                elif matches_glob(rel, exclude_globs):
                    skipped.append({"path": rel.as_posix(), "reason": "excluded glob"})
                else:
                    selected.append(rel)
            else:
                skipped.append({"path": rel.as_posix(), "reason": "not found"})
    seen: set[str] = set()
    unique: list[Path] = []
    for rel in selected:
        key = rel.as_posix()
        if key not in seen:
            seen.add(key)
            unique.append(rel)
    return unique, skipped


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def git_output(repo: Path, args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def git_head(repo: Path) -> str | None:
    out = git_output(repo, ["rev-parse", "HEAD"])
    return out.strip() if out else None


def git_changed(repo: Path) -> list[str]:
    out = git_output(repo, ["diff", "--name-only", "HEAD", "--"])
    return [line.strip() for line in (out or "").splitlines() if line.strip()]


def load_manifest(base: Path) -> dict:
    path = base / MANIFEST
    if not path.is_file():
        raise SystemExit(f"FAIL: manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def emit(title: str, items: list[str], limit: int) -> None:
    print(f"\n== {title} == {len(items)}")
    for item in items[:limit]:
        print("  " + item)
    if len(items) > limit:
        print(f"  ... {len(items) - limit} more (raise --limit)")


def cmd_snapshot(args) -> int:
    repo = args.repo.resolve()
    base = args.base.resolve()
    if base.exists() and not base.is_dir():
        print(f"FAIL: baseline path is a file: {base}")
        return 1
    if base.is_dir() and any(base.iterdir()):
        print(f"FAIL: baseline directory is not empty: {base}")
        return 1

    files, skipped = collect_targets(repo, args.paths, args.ext, args.all, args.exclude_glob)
    files = [rel for rel in files if not is_under(repo / rel, base)]
    records: dict[str, dict] = {}
    for rel in files:
        path = repo / rel
        if path.stat().st_size > args.max_bytes:
            skipped.append({"path": rel.as_posix(), "reason": f"larger than {args.max_bytes} bytes"})
            continue
        try:
            record = record_for(repo, rel)
        except UnicodeDecodeError:
            skipped.append({"path": rel.as_posix(), "reason": "not valid UTF-8/UTF-16 text"})
            continue
        records[rel.as_posix()] = record
        dest = base / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())

    base.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": 1,
        "repo": str(repo),
        "git_head": git_head(repo),
        "file_count": len(records),
        "files": records,
        "skipped": skipped,
    }
    (base / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"snapshot: {len(records)} files -> {base}")
    if skipped:
        print(f"skipped: {len(skipped)} (recorded in {MANIFEST}; excluded files must stay excluded)")
        for item in skipped[: args.limit]:
            print(f"  {item['path']}  ({item['reason']})")
    return 0


def comment_tokens(path: Path, text: str) -> set[str]:
    tokens: set[str] = set()
    for _, block in ccr.comments_with_lines(path, text):
        tokens.update(TICKET_RE.findall(block))
        for match in HIST_RE.finditer(block):
            phrase = match.group(0)
            tokens.add(phrase)
            # Tests often assert the opening prefix only (`"[历史注 2026-09-30"`), without `]`.
            # A bare `[历史注` prefix is not a unique lock: unrelated notes share it, so removing
            # one note would be reported as removing text another test cites. Keep the no-`]`
            # prefix only when it carries a date/ticket ID.
            if phrase.endswith("]") and re.search(r"\d", phrase[:-1]):
                tokens.add(phrase[:-1])
    return tokens


def walk_scope(repo: Path, scope: list[str], exts) -> list[Path]:
    out: set[Path] = set()
    for raw in scope:
        start = (repo / raw).resolve()
        if not is_under(start, repo):
            continue
        if start.is_dir():
            out.update(walk_files(repo, start, exts, ()))
        elif start.is_file():
            out.add(start.relative_to(repo))
    return sorted(out, key=lambda path: path.as_posix())


TICKET_ONLY_RE = re.compile(r"(?:MID|MIN|SEV|WD|CR|MI|M|S|F|L|R|W)-?\d+[A-Za-z]?|SEV-N\d+")


def needle_in_line(line: str, needle: str) -> bool:
    # Bare ticket IDs are prefixes of longer IDs (`M-2` matches inside `M-22` with a plain
    # substring test). Require token boundaries for them; phrases and `[历史注 ...` prefixes
    # stay substring matches because they contain punctuation/Chinese text.
    if TICKET_ONLY_RE.fullmatch(needle):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])", line) is not None
    return needle in line


def search_corpus(repo: Path, needles: list[str], scope: list[str], exts) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for rel in walk_scope(repo, scope, exts):
        try:
            text, _, _ = decode_bytes((repo / rel).read_bytes())
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for needle in needles:
                if needle_in_line(line, needle):
                    hits.setdefault(needle, []).append(f"{rel.as_posix()}:{lineno}")
    return hits


def removed_locks(repo: Path, base: Path, files: dict, current: dict, args) -> tuple[list[str], list[str]]:
    all_removed: set[str] = set()
    for rel in files:
        if rel not in current:
            continue
        try:
            old_text, _, _ = decode_bytes((base / rel).read_bytes())
        except (OSError, UnicodeDecodeError):
            continue
        old_tokens = comment_tokens(base / rel, old_text)
        new_tokens = comment_tokens(repo / rel, current[rel])
        all_removed |= old_tokens - new_tokens
    if not all_removed:
        return [], []
    hits = search_corpus(repo, sorted(all_removed), args.lock_scope, args.ext)
    fails: list[str] = []
    warns: list[str] = []
    for token, places in hits.items():
        where = ", ".join(sorted(set(places))[: args.limit])
        message = f"locked phrase removed: {token!r} still referenced at {where}"
        (warns if args.no_strict_locks else fails).append(message)
    return fails, warns


def build_suffix_map(repo: Path) -> dict[str, set[str]]:
    suffix: dict[str, set[str]] = {}
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        parts = rel.as_posix().split("/")
        for index in range(len(parts)):
            suffix.setdefault("/".join(parts[index:]), set()).add(rel.as_posix())
    return suffix


def check_anchors(repo: Path, files: dict, current: dict, args) -> tuple[list[str], list[str]]:
    fails: list[str] = []
    warns: list[str] = []
    suffix = build_suffix_map(repo)
    for rel in walk_scope(repo, args.anchor_scope, args.ext):
        try:
            text, _, _ = decode_bytes((repo / rel).read_bytes())
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in ANCHOR_RE.finditer(line):
                raw = match.group(1).replace("\\", "/")
                while raw.startswith("./"):
                    raw = raw[2:]
                number = int(match.group(2))
                target = raw if raw in files else None
                if target is None:
                    candidates = suffix.get(raw)
                    if candidates and len(candidates) == 1:
                        target = next(iter(candidates))
                where = f"{rel.as_posix()}:{lineno} -> {match.group(0)}"
                if target is None:
                    warns.append(f"anchor target not found: {where}")
                    continue
                if target not in files:
                    warns.append(f"anchor target not snapshotted: {where}")
                    continue
                current_text = current.get(target)
                if current_text is None:
                    continue
                current_lines = len(current_text.splitlines())
                baseline_lines = files[target]["total_lines"]
                if number > current_lines:
                    fails.append(f"stale anchor beyond EOF: {where} (file has {current_lines} lines)")
                elif current_lines != baseline_lines:
                    fails.append(
                        f"line anchor drift: {where}; {target} lines {baseline_lines} -> {current_lines}. "
                        "Roll back the anchored file or migrate the anchor to a symbol in a separate change."
                    )
    return fails, warns


def cmd_preflight(args) -> int:
    repo = args.repo.resolve()
    base = args.base.resolve()
    manifest = load_manifest(base)
    files: dict[str, dict] = manifest["files"]
    skipped = {item["path"] for item in manifest.get("skipped", [])}
    fails: list[str] = []
    warns: list[str] = []
    infos: list[str] = []

    if args.changed:
        changed = git_changed(repo)
        if not changed:
            infos.append("git diff is empty or unavailable; coverage check used the manifest only")
        for rel in changed:
            path = Path(rel)
            if path.suffix.lower() not in args.ext or matches_glob(path, args.exclude_glob):
                continue
            if rel not in files and rel not in skipped:
                fails.append(f"changed but not snapshotted: {rel}")
    if args.paths:
        requested, _ = collect_targets(repo, args.paths, args.ext, False, args.exclude_glob)
        for rel in requested:
            if rel.as_posix() not in files:
                fails.append(f"requested but not snapshotted: {rel.as_posix()}")

    current: dict[str, str] = {}
    for rel, record in files.items():
        path = repo / rel
        if not path.is_file():
            fails.append(f"missing since snapshot: {rel}")
            continue
        try:
            text, encoding, bom = decode_bytes(path.read_bytes())
        except UnicodeDecodeError:
            fails.append(f"no longer decodable as UTF-8/UTF-16: {rel}")
            continue
        current[rel] = text
        current_encoding = encoding_label(encoding, bom)
        baseline_encoding = encoding_label(record["encoding"], record["bom"])
        if current_encoding != baseline_encoding:
            fails.append(f"encoding changed: {rel} {baseline_encoding} -> {current_encoding}")
        current_eol = eol_profile(text)
        baseline_eol = record["eol"]
        if current_eol["shape"] != baseline_eol["shape"]:
            fails.append(f"EOL shape changed: {rel} {baseline_eol['shape']} -> {current_eol['shape']}")
        if encoding.startswith("utf-16") or bom:
            infos.append(f"encoding-aware file: {rel} ({current_encoding})")

        if path.suffix.lower() in args.density_ext:
            _, _, density = comment_stats(path, text)
            baseline_density = record["density"]
            if density < args.floor:
                if baseline_density < args.floor:
                    infos.append(f"PRE-EXISTING below floor: {rel} {baseline_density}% -> {density}%")
                else:
                    fails.append(
                        f"density below floor: {rel} {baseline_density}% -> {density}% < {args.floor}%"
                    )
            elif density < args.floor + args.near:
                warns.append(f"near floor: {rel} {baseline_density}% -> {density}% (floor {args.floor}%)")

    lock_fails, lock_warns = removed_locks(repo, base, files, current, args)
    fails.extend(lock_fails)
    warns.extend(lock_warns)
    anchor_fails, anchor_warns = check_anchors(repo, files, current, args)
    fails.extend(anchor_fails)
    warns.extend(anchor_warns)

    emit("coverage", fails, args.limit)
    emit("PRE-EXISTING / encoding-aware", infos, args.limit)
    emit("warnings", warns, args.limit)
    print(f"\n== summary == FAIL {len(fails)} | WARN {len(warns)} | INFO {len(infos)} | files {len(files)}")
    return 0 if (args.warn_only or not fails) else 1


def readings_in_comments(path: Path, text: str) -> set[str]:
    readings: set[str] = set()
    for _, block in ccr.comments_with_lines(path, text):
        readings.update(item.strip() for item in READING_RE.findall(block))
        readings.update(SLASH_SEQ_RE.findall(block))
    return readings


def cmd_guard(args) -> int:
    repo = args.repo.resolve()
    base = args.base.resolve()
    manifest = load_manifest(base)
    files: dict[str, dict] = manifest["files"]

    targets = sorted(files)
    if args.paths:
        selected, _ = collect_targets(repo, args.paths, args.ext, False, args.exclude_glob)
        targets = [rel.as_posix() for rel in selected]

    fails: list[str] = []
    warns: list[str] = []
    unchanged = 0
    for rel in targets:
        record = files.get(rel)
        if record is None:
            fails.append(f"no baseline: {rel}")
            continue
        current_path, baseline_path = repo / rel, base / rel
        if not current_path.is_file():
            fails.append(f"deleted: {rel}")
            continue
        if not baseline_path.is_file():
            fails.append(f"baseline missing: {rel}")
            continue
        try:
            current_data = current_path.read_bytes()
            baseline_data = baseline_path.read_bytes()
        except OSError as exc:
            fails.append(f"unreadable: {rel} ({exc})")
            continue
        if current_data == baseline_data:
            unchanged += 1
            continue
        try:
            same, reasons = ve.compare_pair(current_path, baseline_path)
        except (UnicodeDecodeError, SyntaxError) as exc:
            fails.append(f"non-comment change: {rel} -- unparsable ({exc})")
            continue
        if not same:
            fails.append(f"non-comment change: {rel} -- " + "; ".join(reasons))

        try:
            current_text, _, _ = decode_bytes(current_data)
            baseline_text, _, _ = decode_bytes(baseline_data)
        except UnicodeDecodeError:
            continue
        lost = sorted(readings_in_comments(current_path, baseline_text) - readings_in_comments(current_path, current_text))
        if lost:
            message = f"readings lost: {rel} -- {', '.join(lost[: args.limit])}"
            (fails if args.strict_readings else warns).append(message)

    emit("non-comment changes", [item for item in fails if item.startswith(("non-comment", "deleted", "no baseline"))], args.limit)
    emit("readings lost", [item for item in fails + warns if item.startswith("readings lost")], args.limit)
    emit("other failures", [item for item in fails if not item.startswith(("non-comment", "readings lost", "deleted", "no baseline"))], args.limit)
    emit("warnings", [item for item in warns if not item.startswith("readings lost")], args.limit)
    print(
        f"\n== summary == FAIL {len(fails)} | WARN {len(warns)} | unchanged {unchanged} | "
        f"checked {len(targets)} | readings strict={args.strict_readings}"
    )
    return 0 if not fails else 1


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root (default: cwd)")
    parser.add_argument("--base", type=Path, required=True, help="baseline directory containing manifest.json")
    parser.add_argument("--ext", nargs="+", default=list(DEFAULT_EXTS), help="file extensions in scope")
    parser.add_argument("--exclude-glob", nargs="+", default=list(DEFAULT_EXCLUDE_GLOBS), help="generated/minified files to skip")
    parser.add_argument("--limit", type=int, default=20, help="max lines printed per bucket")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="snapshot / preflight / guard for comment-only refactors")
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="copy in-scope files and write manifest.json")
    add_common(snapshot)
    snapshot.add_argument("--all", action="store_true", help="snapshot the whole repo (with exclusions)")
    snapshot.add_argument("--max-bytes", type=int, default=MAX_BYTES, help="skip files larger than this")
    snapshot.add_argument("paths", nargs="*", help="files or directories (default with --all)")
    snapshot.set_defaults(func=cmd_snapshot)

    preflight = sub.add_parser("preflight", help="check coverage, density, locks, anchors, encoding")
    add_common(preflight)
    preflight.add_argument("--no-changed", dest="changed", action="store_false", default=True, help="skip the git changed-set coverage check")
    preflight.add_argument("--floor", type=float, default=13.0, help="per-file comment density floor (default: 13.0)")
    preflight.add_argument("--near", type=float, default=3.0, help="report files within this margin of the floor")
    preflight.add_argument("--density-ext", nargs="+", default=[".py"], help="extensions the density floor applies to")
    preflight.add_argument("--lock-scope", nargs="+", default=["tests", "scripts"], help="where verbatim locks are searched")
    preflight.add_argument("--anchor-scope", nargs="+", default=["tests", "scripts"], help="where path:line anchors are searched")
    preflight.add_argument("--no-strict-locks", dest="no_strict_locks", action="store_true", help="report removed locks as warnings")
    preflight.add_argument("--warn-only", action="store_true", help="always exit 0")
    preflight.add_argument("paths", nargs="*", help="files or directories that must be covered")
    preflight.set_defaults(func=cmd_preflight)

    guard = sub.add_parser("guard", help="verify comment-only changes and measured-reading survival")
    add_common(guard)
    guard.add_argument("--strict-readings", action="store_true", help="treat a lost measured reading as a failure")
    guard.add_argument("paths", nargs="*", help="files or directories (default: every changed manifest file)")
    guard.set_defaults(func=cmd_guard)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
