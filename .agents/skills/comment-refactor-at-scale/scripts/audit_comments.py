#!/usr/bin/env python3
# Candidate inventory for comment-only refactors. Regexes only rank where to look: they cannot
# prove a comment is stale, so every finding needs a code/test check before deletion.
#
# Taxonomy (same as the task ledger): S1 contradictory/code-like, S2 archaeology, S3 duplicate
# or TODO, S4 vague, S5 long/block, K contract wording that must survive. K is not a defect.
#
# Usage:
#   python audit_comments.py --repo <root> [--paths p ...] [--json out.json]
#   python audit_comments.py --repo <root> --themes themes.txt [--baseline <snapshot>]
#   python audit_comments.py --repo <root> --ledger-dir <logs> --ledger-only --strict
# Exit 0 unless --strict and a theme dropped to zero or a ledger hard finding exists.

from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import re
import subprocess
import sys
import tokenize
from collections import Counter
from pathlib import Path

TEXT_EXTS = {".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".css", ".scss", ".html", ".htm", ".vbs", ".vba"}
SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "build",
    "dist",
    "node",
    "ffmpeg",
    "downloads",
    ".workbuddy",
    ".qoder",
}
DEFAULT_EXCLUDE = {"crypto-js.min.js", "douyin_pb2.py", "StopRecording.vbs"}

VAGUE = re.compile(
    r"^#*\s*(初始化|返回|处理|判断|循环|设置|获取|创建|关闭|清理|打印|导入|定义|开始|结束|主函数|"
    r"说明|入口|参数|结果|异常|日志|配置加载|加载配置|默认值|当前值|遍历|检查|调用|赋值|构造|"
    r"销毁|更新|读取|写入|删除|添加|执行)\s*[。:：]?\s*$"
)
ARCH = re.compile(
    r"(20\d\d[-/年]\d{1,2}|此前|原先|原来|曾(经|是|在)|历史|旧版|旧写法|老版本|上一版|早先|早期|"
    r"最初|已废弃|已移除|不再使用|已删除|v\d+\.\d+\.\d+|补丁|整改|回归锁|M-\d+|MID-\d+|MIN-\d+|"
    r"R-\d+|F-\d+|P-[A-Z-]+)"
)
TODO = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b|待办|暂时|临时方案|以后再")
CODEISH = re.compile(
    r"(^\s*(?:def|class|return|if|for|while|import|from|async)\b|=\s*[^=\s]|\(\s*\)|"
    r"\bself\.\w+|\w+\.\w+\(|\w+\s*=\s*\w+)"
)
CONTRACT = re.compile(r"(必须|不得|唯一|永远|绝不|禁止|否则|否则会|务必|顺序|契约|红线)")
CJK = re.compile(r"[\u4e00-\u9fff]")
CODE_START = ("def ", "return", "if ", "for ", "import ", "class ", "async def ")
LEDGER_KEYS = ("file", "line", "action", "category", "before", "after", "reason")


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def comment_items_py(path: Path, text: str) -> list[dict]:
    try:
        toks = tokenize.tokenize(io.BytesIO(path.read_bytes()).readline)
    except tokenize.TokenError, SyntaxError, IndentationError:
        return []
    lines = text.splitlines()
    out = []
    for tok in toks:
        if tok.type != tokenize.COMMENT:
            continue
        row, col = tok.start
        raw = lines[row - 1] if row - 1 < len(lines) else ""
        out.append({"line": row, "end_line": row, "text": tok.string, "full": not raw[:col].strip()})
    return out


def scan_c_like(text: str, allow_line: bool) -> list[dict]:
    # Character scanner, not a regex: `//` inside a string must not start a comment. Regex
    # literals in JS are still a known blind spot (documented in references/audit-scanners.md).
    out: list[dict] = []
    i, n = 0, len(text)
    line, line_start = 1, 0
    in_str: str | None = None
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_str:
            if c == "\\" and nxt:
                i += 2
                continue
            if c == in_str or c == "\n":
                in_str = None
            if c == "\n":
                line += 1
                line_start = i + 1
            i += 1
            continue
        if c in "\"'`":
            in_str = c
            i += 1
            continue
        if allow_line and c == "/" and nxt == "/":
            start = i
            while i < n and text[i] != "\n":
                i += 1
            out.append(
                {
                    "line": line,
                    "end_line": line,
                    "text": text[start:i],
                    "full": not text[line_start:start].strip(),
                }
            )
            continue
        if c == "/" and nxt == "*":
            start, start_line = i, line
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            block = text[start:j]
            end_line = start_line + block.count("\n")
            out.append(
                {
                    "line": start_line,
                    "end_line": end_line,
                    "text": block,
                    "full": not text[line_start:start].strip(),
                }
            )
            line = end_line
            line_start = text.rfind("\n", 0, j) + 1
            i = j
            continue
        if c == "\n":
            line += 1
            line_start = i + 1
        i += 1
    return out


def comment_items_html(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r"<!--.*?-->", text, flags=re.S):
        start = m.start()
        line = text.count("\n", 0, start) + 1
        prefix = text[text.rfind("\n", 0, start) + 1 : start]
        out.append(
            {
                "line": line,
                "end_line": line + m.group(0).count("\n"),
                "text": m.group(0),
                "full": not prefix.strip(),
            }
        )
    return out


def comment_items_vbs(text: str) -> list[dict]:
    out = []
    for idx, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if s.startswith("'") or s.upper().startswith("REM "):
            out.append({"line": idx, "end_line": idx, "text": s, "full": True})
    return out


def comment_items(path: Path, text: str) -> list[dict]:
    suf = path.suffix.lower()
    if suf in (".py", ".pyi"):
        return comment_items_py(path, text)
    if suf in (".js", ".mjs", ".cjs", ".ts"):
        return scan_c_like(text, allow_line=True)
    if suf == ".scss":
        return scan_c_like(text, allow_line=True)
    if suf == ".css":
        return scan_c_like(text, allow_line=False)
    if suf in (".html", ".htm"):
        return comment_items_html(text)
    if suf in (".vbs", ".vba"):
        return comment_items_vbs(text)
    return []


def body_of(text: str) -> str:
    s = text.strip()
    s = re.sub(r"^/\*+|\*/$", "", s).strip()
    s = re.sub(r"^<!--|-->$", "", s).strip()
    s = re.sub(r"^#+", "", s).strip()
    s = re.sub(r"^//+", "", s).strip()
    s = re.sub(r"^'+|^REM\s+", "", s, flags=re.I).strip()
    lines = [re.sub(r"^\*+", "", ln).strip() for ln in s.splitlines()]
    return " ".join(x for x in lines if x)


def merge_blocks(items: list[dict]) -> None:
    # Consecutive full-line comments form one block; block length drives S5 candidate ranking.
    ordered = sorted(items, key=lambda x: (x["line"], x["end_line"]))
    i = 0
    while i < len(ordered):
        if not ordered[i]["full"]:
            i += 1
            continue
        j = i
        while j + 1 < len(ordered) and ordered[j + 1]["full"] and ordered[j + 1]["line"] <= ordered[j]["end_line"] + 1:
            j += 1
        size = ordered[j]["end_line"] - ordered[i]["line"] + 1
        for k in range(i, j + 1):
            ordered[k]["block_len"] = max(size, ordered[k]["end_line"] - ordered[k]["line"] + 1)
            ordered[k]["block_start"] = ordered[i]["line"]
        i = j + 1


def classify(path: Path, items: list[dict], min_block: int) -> list[dict]:
    seen: dict[str, int] = {}
    findings = []
    for item in items:
        body = body_of(item["text"])
        if not body:
            continue
        tags = []
        if item["full"] and (body.startswith(CODE_START) or (CODEISH.search(body) and not CJK.search(body))):
            tags.append("S1")
        if ARCH.search(body):
            tags.append("S2")
        dup_of = None
        if len(body) > 8 and body in seen:
            tags.append("S3")
            dup_of = seen[body]
        else:
            seen.setdefault(body, item["line"])
        if TODO.search(body):
            tags.append("S3")
        if VAGUE.match(item["text"]):
            tags.append("S4")
        # One finding per long block, not one per line; a single over-long line still counts.
        block_hit = item.get("block_len", 1) >= min_block and item.get("block_start") == item["line"]
        if len(item["text"]) > 120 or block_hit:
            tags.append("S5")
        if CONTRACT.search(body):
            tags.append("K")
        if tags:
            findings.append(
                {
                    "file": path.as_posix(),
                    "line": item["line"],
                    "end_line": item["end_line"],
                    "block_len": item.get("block_len", 1),
                    "tags": sorted(set(tags)),
                    "dup_of": dup_of,
                    "text": body[:200],
                }
            )
    return findings


def iter_files(repo: Path, targets: list[str], include_excluded: bool) -> list[Path]:
    if targets:
        picked: list[Path] = []
        for raw in targets:
            p = Path(raw)
            p = p if p.is_absolute() else repo / raw
            if p.is_dir():
                picked.extend(x for x in sorted(p.rglob("*")) if x.is_file())
            elif p.is_file():
                picked.append(p)
        files = picked
    else:
        proc = subprocess.run(
            ["git", "-C", str(repo), "ls-files"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            files = [repo / line for line in proc.stdout.splitlines() if line.strip()]
        else:
            files = [p for p in sorted(repo.rglob("*")) if p.is_file()]
    result = []
    for p in files:
        if p.suffix.lower() not in TEXT_EXTS or not p.is_file():
            continue
        if any(part in SKIP_PARTS for part in p.relative_to(repo).parts):
            continue
        if not include_excluded and p.name in DEFAULT_EXCLUDE:
            continue
        result.append(p)
    return list(dict.fromkeys(result))


def scan(repo: Path, files: list[Path], min_block: int) -> tuple[list[dict], int]:
    findings: list[dict] = []
    total = 0
    for p in files:
        text = read_text(p)
        items = comment_items(p, text)
        total += len(items)
        merge_blocks(items)
        for item in classify(p.relative_to(repo), items, min_block):
            findings.append(item)
    return findings, total


def git_changed(repo: Path, exts: set[str]) -> list[str] | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain=v1", "--untracked-files=no"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return None
    changed = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        xy, rest = line[:2], line[3:]
        if "D" in xy:
            continue
        if "->" in rest:
            rest = rest.split("->")[-1]
        rel = rest.strip().strip('"').replace("\\", "/").lstrip("./")
        if rel and Path(rel).suffix.lower() in exts:
            changed.append(rel)
    return sorted(dict.fromkeys(changed))


def ledger_audit(repo: Path, ledger_dir: Path, allow: set[str]) -> tuple[list[str], list[str]]:
    # Coverage is the one check that catches an interrupted agent: a diff without a ledger
    # record means the change exists but has no stated reason. Claims overlap is delegated to
    # scripts/audit_ledger.py（同目录）.
    hard: list[str] = []
    review: list[str] = []
    files: set[str] = set()
    rows = bad_json = missing_fields = duplicates = 0
    seen_records: set[tuple] = set()
    for path in sorted(ledger_dir.glob("log-*.jsonl")):
        for line in read_text(path).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad_json += 1
                continue
            rows += 1
            if any(k not in rec for k in LEDGER_KEYS):
                missing_fields += 1
            key = (rec.get("file"), rec.get("line"), rec.get("action"), rec.get("category"))
            if key in seen_records:
                duplicates += 1
            seen_records.add(key)
            if rec.get("file"):
                files.add(str(rec["file"]).replace("\\", "/").lstrip("./"))
    if bad_json:
        hard.append(f"ledger: {bad_json} malformed JSON line(s)")
    if missing_fields:
        hard.append(f"ledger: {missing_fields} record(s) missing required keys")
    if duplicates:
        hard.append(f"ledger: {duplicates} duplicate record(s)")
    changed = git_changed(repo, TEXT_EXTS)
    if changed is None:
        review.append("ledger: git status unavailable; coverage not computed")
    else:
        unlogged = [f for f in changed if f not in files and f not in allow]
        if unlogged:
            hard.append(f"ledger: {len(unlogged)} changed file(s) without a record: {', '.join(unlogged[:8])}")
        review.append(
            f"ledger: {rows} record(s), {len(files)} file(s); changed {len(changed)}, unlogged {len(unlogged)}"
        )
    return hard, review


def theme_counts(repo: Path, files: list[Path], phrases: list[str]) -> dict[str, int]:
    counts = {p: 0 for p in phrases}
    for path in files:
        text = read_text(path)
        for item in comment_items(path, text):
            body = body_of(item["text"])
            for phrase in phrases:
                counts[phrase] += body.count(phrase)
    return counts


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError, OSError:
        pass
    ap = argparse.ArgumentParser(description="comment candidate inventory (review aid, not a gate)")
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--paths", nargs="*", default=None)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--min-block", type=int, default=6, help="S5 threshold for consecutive comment lines")
    ap.add_argument("--include-excluded", action="store_true", help="also scan pinned/generated names")
    ap.add_argument("--themes", type=Path, default=None, help="file with one load-bearing phrase per line")
    ap.add_argument("--baseline", type=Path, default=None, help="snapshot for theme survival comparison")
    ap.add_argument("--ledger-dir", type=Path, default=None, help="JSONL ledger directory to audit")
    ap.add_argument("--ledger-only", action="store_true", help="run only the ledger audit")
    ap.add_argument(
        "--allow-unlogged", action="append", default=[], help="changed file allowed to have no ledger record"
    )
    ap.add_argument("--strict", action="store_true", help="exit 1 on a zeroed theme or ledger hard finding")
    args = ap.parse_args()

    repo = args.repo.resolve()
    allow = {x.replace("\\", "/").lstrip("./") for x in args.allow_unlogged}
    ledger_hard: list[str] = []
    ledger_review: list[str] = []
    if args.ledger_dir:
        ledger_hard, ledger_review = ledger_audit(repo, args.ledger_dir.resolve(), allow)
        print("ledger audit:")
        for item in ledger_hard:
            print("  HARD  " + item)
        for item in ledger_review:
            print("  ok    " + item)
        if args.ledger_only:
            return 1 if (args.strict and ledger_hard) else 0

    files = iter_files(repo, args.paths or [], args.include_excluded)
    if not files:
        print("no scannable files")
        return 1 if (args.strict and ledger_hard) else 0

    if args.themes:
        phrases = [
            ln.strip() for ln in read_text(args.themes).splitlines() if ln.strip() and not ln.lstrip().startswith("#")
        ]
        if not phrases:
            print("themes file has no phrases")
            return 0
        current = theme_counts(repo, files, phrases)
        base_counts = None
        if args.baseline and args.baseline.is_dir():
            base = args.baseline.resolve()
            shared = [p for p in files if (base / p.relative_to(repo)).is_file()]
            base_counts = theme_counts(base, [base / p.relative_to(repo) for p in shared], phrases)
        zeroed = []
        rows = []
        for phrase in phrases:
            cur = current[phrase]
            old = base_counts[phrase] if base_counts is not None else None
            row = {"phrase": phrase, "current": cur, "baseline": old}
            if old is not None:
                row["delta"] = cur - old
                row["zeroed"] = old > 0 and cur == 0
                if row["zeroed"]:
                    zeroed.append(phrase)
            rows.append(row)
        print(f"themes: {len(phrases)}; files: {len(files)}; zeroed: {len(zeroed)}")
        for row in rows[: args.limit]:
            base = "-" if row["baseline"] is None else str(row["baseline"])
            mark = " ZEROED" if row.get("zeroed") else ""
            print(f"  {row['current']:5} (base {base:>5})  {row['phrase']}{mark}")
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps({"themes": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1 if (args.strict and zeroed) else 0

    findings, total = scan(repo, files, args.min_block)
    summary = Counter(tag for f in findings for tag in f["tags"])
    per_file = Counter(f["file"] for f in findings)
    payload = {
        "repo": str(repo),
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "scanned_files": len(files),
        "comment_items": total,
        "findings": findings,
        "summary": dict(summary),
        "top_files": per_file.most_common(20),
    }
    print(f"scanned {len(files)} files; {total} comment items; {len(findings)} findings")
    print("tags:", dict(sorted(summary.items())))
    for name, count in per_file.most_common(10):
        print(f"  {count:4}  {name}")
    for item in findings[: args.limit]:
        print(f"  {','.join(item['tags']):12} {item['file']}:{item['line']}  {item['text'][:110]}")
    if len(findings) > args.limit:
        print(f"  ... {len(findings) - args.limit} more (raise --limit or use --json)")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"json: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
