# Audit JSONL change ledgers produced by write agents dispatched under
# comment-refactor-at-scale. Checks per-record schema, exact duplicates
# (double-logging after an interruption), and cross-agent file-domain overlap.
# Usage: python audit_ledger.py <logs_dir> [--claims claims.json]
# Exit: 0 clean, 1 violations found, 2 usage/environment error.

import argparse
import io
import json
import sys
from collections import Counter
from pathlib import Path

REQUIRED = {
    "file": str,
    "line": int,
    "action": str,
    "before": str,
    "after": str,
    "reason": str,
}


def _norm(file_value: str) -> str:
    return file_value.replace("\\", "/").strip().lower()


def _ensure_utf8_stdout() -> None:
    # Ledgers carry CJK text; a GBK console would crash on print.
    if getattr(sys.stdout, "encoding", "").lower().replace("-", "") != "utf8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def audit_ledgers(logs_dir: Path) -> list[str]:
    problems: list[str] = []
    ledger_files = sorted(logs_dir.rglob("*.jsonl"))
    if not ledger_files:
        problems.append(f"no .jsonl ledgers found under {logs_dir}")
        return problems
    seen: Counter[tuple] = Counter()
    for ledger in ledger_files:
        for lineno, raw in enumerate(ledger.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            where = f"{ledger.name}:{lineno}"
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as exc:
                problems.append(f"{where}: invalid JSON ({exc.msg})")
                continue
            if not isinstance(rec, dict):
                problems.append(f"{where}: record is not an object")
                continue
            for field, ftype in REQUIRED.items():
                if field not in rec:
                    problems.append(f"{where}: missing field '{field}'")
                elif ftype is int and not isinstance(rec[field], bool) and not isinstance(rec[field], int):
                    problems.append(f"{where}: field '{field}' must be an int")
                elif ftype is str and not isinstance(rec[field], str):
                    problems.append(f"{where}: field '{field}' must be a str")
            if all(f in rec and isinstance(rec[f], REQUIRED[f]) for f in REQUIRED):
                key = (_norm(rec["file"]), rec["line"], rec["action"], rec["before"], rec["after"])
                seen[key] += 1
    for key, n in sorted(seen.items()):
        if n > 1:
            problems.append(f"duplicate record x{n}: file={key[0]} line={key[1]} action={key[2]}")
    return problems


def audit_claims(claims_path: Path) -> list[str]:
    try:
        claims = json.loads(claims_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"claims file unreadable: {exc}"]
    if not isinstance(claims, dict):
        return ["claims file must be a JSON object {agent: [files]}"]
    owners: dict[str, list[str]] = {}
    problems: list[str] = []
    for agent, files in claims.items():
        if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
            problems.append(f"agent '{agent}': file list must be an array of strings")
            continue
        for f in files:
            owners.setdefault(_norm(f), []).append(agent)
    for f, agents in sorted(owners.items()):
        if len(agents) > 1:
            problems.append(f"file-domain overlap: '{f}' claimed by {', '.join(sorted(agents))}")
    return problems


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Audit write-agent JSONL ledgers: schema, duplicates, file-domain overlap"
    )
    parser.add_argument("logs_dir", type=Path, help="directory containing agent *.jsonl ledgers")
    parser.add_argument("--claims", type=Path, help="JSON object mapping agent name -> owned files")
    args = parser.parse_args()
    if not args.logs_dir.is_dir():
        print(f"FAIL: logs_dir not a directory: {args.logs_dir}")
        return 2
    problems = audit_ledgers(args.logs_dir)
    if args.claims:
        problems += audit_claims(args.claims)
    if problems:
        for p in problems:
            print(f"VIOLATION: {p}")
        print(f"FAIL: {len(problems)} problem(s)")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
