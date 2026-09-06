#!/usr/bin/env python3
# Per-module coverage gate check.
#
# Reads the .coverage data file produced by pytest-cov and verifies that each
# declared module meets its minimum coverage threshold.
#
# Thresholds mirror the comments in pyproject.toml:
#    spider.py  >= 50%   stream.py  >= 70%   utils.py   >= 80%
#    ttwid.py   >= 85%   ab_sign.py >= 95%   proxy.py   >= 50%
#
# Usage:
#    # After running pytest with coverage
#    pytest --cov=src --cov-report=term-missing
#    python scripts/check_coverage.py
#
#    # Or specify a custom .coverage data file
#    python scripts/check_coverage.py --data-file path/to/.coverage

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

# -- Per-module coverage thresholds ------------------------------------------
# Keep in sync with pyproject.toml comments
MODULE_THRESHOLDS: dict[str, float] = {
    "src/spider.py": 50,
    "src/stream.py": 70,
    "src/utils.py": 80,
    "src/ttwid.py": 85,
    "src/ab_sign.py": 95,
    "src/proxy.py": 50,
}

# coverage JSON 报告为嵌套异构 dict，统一以 dict[str, object] 建模，读取处用 cast 收敛
CoverageData = dict[str, object]


def _get_coverage_json(data_file: str | None) -> CoverageData:
    # Generate and parse a coverage JSON report.
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        cmd = [sys.executable, "-m", "coverage", "json", "-o", tmp_path]
        if data_file:
            cmd.extend(["--data-file", data_file])

        # 加超时与显式编码：防止 coverage 挂起卡死 CI，并兼容 Windows 非 UTF-8 locale
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            print(f"ERROR: coverage json timed out: {' '.join(cmd)}")
            sys.exit(2)

        if result.returncode != 0:
            # coverage json 可能因全局 fail_under 未达标而返回非零退出码（报告仍已生成），
            # 真正的失败以「JSON 能否生成并解析」为准，此处仅提示不中断。
            print(f"WARN: coverage json exited with code {result.returncode}:\n{result.stderr}", file=sys.stderr)

        try:
            with open(tmp_path, encoding="utf-8") as f:
                return cast(CoverageData, json.load(f))
        except OSError, ValueError:
            print(f"ERROR: failed to read coverage json report: {tmp_path}")
            sys.exit(2)
    finally:
        # 无论成功、失败还是提前退出，都清理临时文件
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def _find_module_coverage(coverage_data: CoverageData, module_path: str) -> CoverageData | None:
    # Locate a module's coverage data in the JSON report.
    files = cast(dict[str, CoverageData], coverage_data.get("files", {}))

    # Direct match
    if module_path in files:
        return files[module_path]

    # Fuzzy match for different path separators / absolute vs relative
    module_normalized = Path(module_path).as_posix()
    for file_path, file_data in files.items():
        file_normalized = Path(file_path).as_posix()
        if file_normalized.endswith(module_normalized):
            return file_data
        if Path(file_normalized).name == Path(module_normalized).name:
            parent = Path(file_normalized).parent.name
            if parent in ("src", ""):
                return file_data

    return None


def check_coverage(data_file: str | None = None) -> int:
    # Check per-module coverage thresholds. Returns 0 if all pass, 1 otherwise.
    coverage_data = _get_coverage_json(data_file)

    failures: list[tuple[str, float, float]] = []
    passes: list[tuple[str, float, float]] = []
    missing_modules: list[str] = []

    for module_path, threshold in sorted(MODULE_THRESHOLDS.items()):
        file_data = _find_module_coverage(coverage_data, module_path)

        if file_data is None:
            missing_modules.append(module_path)
            continue

        summary = cast(CoverageData, file_data.get("summary", {}))
        coverage_pct = cast(float, summary.get("percent_covered", 0.0))

        if coverage_pct >= threshold:
            passes.append((module_path, coverage_pct, threshold))
        else:
            failures.append((module_path, coverage_pct, threshold))

    # Print results
    print("=" * 60)
    print("Per-module coverage gate")
    print("=" * 60)

    if passes:
        print(f"\n[PASS] {len(passes)} module(s) meet threshold:")
        for module, pct, threshold in passes:
            print(f"   {module:25s} {pct:5.1f}%  (>= {threshold:.0f}%)")

    if missing_modules:
        print(f"\n[WARN] {len(missing_modules)} module(s) not found in coverage data:")
        for module in missing_modules:
            print(f"   {module}")

    if failures:
        print(f"\n[FAIL] {len(failures)} module(s) below threshold:")
        for module, pct, threshold in failures:
            deficit = threshold - pct
            print(f"   {module:25s} {pct:5.1f}%  (>= {threshold:.0f}%)  <- {deficit:.1f}% short")
        print(f"\n{'=' * 60}")
        print(f"FAILED: {len(failures)} module(s) did not meet coverage threshold")
        print(f"{'=' * 60}")
        return 1

    print(f"\n{'=' * 60}")
    print(f"PASSED: All {len(passes)} module(s) meet coverage threshold")
    print(f"{'=' * 60}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-module coverage gate check")
    _ = parser.add_argument(
        "--data-file",
        type=str,
        default=None,
        help="Path to .coverage data file (auto-detected by default)",
    )
    args = parser.parse_args()
    sys.exit(check_coverage(data_file=cast(str | None, args.data_file)))


if __name__ == "__main__":
    main()
