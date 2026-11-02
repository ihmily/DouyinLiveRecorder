#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
#
# 发布产物体积报告（打包体积门禁的度量侧）
#
# 职责：把 dist/DouyinLiveRecorder/ 的体积构成「说清楚」——总量、按包聚合、最大单文件，
# 以及最要紧的一条：开发 / 测试工具链有没有被误收进对外分发的产物。
#
# 核心机制：纯文件系统遍历 + 两类聚合（按 _internal 下的顶层包、按单文件）+ 一份泄漏黑名单。
# 不解析 PyInstaller 的中间产物、也不重建依赖图——那些都会随 PyInstaller 版本漂移，而
# 「实际落盘的字节」才是分发体积的唯一事实。
#
# 与其它模块的关系：
#   - build_exe.py 负责「排除」（SPEC_TEMPLATE 的 BLOAT_EXCLUDES），本脚本负责「验证」；
#     两侧是同一件事的两半，改排除清单后必须用本脚本复测。
#   - tests/test_build_exe.py 锁的是排除清单的**内容**（不许删、不许误排生产模块），
#     本脚本给的是**结果**（排完到底少了多少）。内容对了但体积没降，只有本脚本能发现。
#
# 设计取舍：
#   - 泄漏判定用「路径中出现包名目录」而不是 import 图：误收集在冻结产物里表现为
#     _internal/mypy/*.pyd 这样的实文件，路径判定最直接，也不会因为某处动态 import
#     而漏判。
#   - 默认只报告、不失败（--strict 才 exit 1）：体积是连续量，硬阈值会让每次依赖升级
#     都变红；「工具链泄漏」是离散的、非黑即白，故单独做成可断言的一项。
#
# 用法：
#     python scripts/report_bundle_size.py                     # 默认 dist/DouyinLiveRecorder
#     python scripts/report_bundle_size.py path/to/release     # 指定发布目录
#     python scripts/report_bundle_size.py --strict            # 检出泄漏即 exit 1（CI 推荐）
#     python scripts/report_bundle_size.py --json size.json    # 落 JSON 供下次 --compare 比对
#     python scripts/report_bundle_size.py --compare size.json # 与上次报告逐项比对
#
# 退出码（在本文件显式登记）：
#   0  报告已产出，且（--strict 时）没有工具链泄漏
#   1  --strict 命中开发/测试工具链泄漏（产物不合格）
#   2  度量面缺输入：发布目录不存在，或 --compare 指定的基线不存在/读不出/不是合法报告
#      ——后者过去只往报告里追加一行 [warn] 就退 0，是「比对没跑」冒充「比对没问题」
#
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

# 发布目录里**绝不该出现**的开发 / 测试工具链。它们都不在 requirements.txt 里、运行期不会被
# 导入，但只要在 venv 里装了、又被人误加一个顶层 import，就会被静默打进对外分发的 zip
# （2026-09-24 实测：mypy 经 pydantic.v1.mypy 的顶层 import 进了产物，0.71MB / 69 文件）。
# 判定按「相对路径的任一成分等于该名字」（大小写无关），故 mypy/ 与 _internal/mypy 都算命中。
LEAK_PATTERNS: tuple[str, ...] = (
    "pytest",
    "_pytest",
    "mypy",
    "mypyc",
    "mypy_extensions",
    "basedpyright",
    "black",
    "blackd",
    "blib2to3",
    "isort",
    "coverage",
    "pip",
    "pygments",
    "nodejs_wheel",
    "iniconfig",
    "pluggy",
)

DEFAULT_RELEASE = Path("dist") / "DouyinLiveRecorder"


# 报告的数据结构即 --json 落盘的结构（--compare 读回的是同一份），故用 TypedDict 显式声明，
# 而不是 dict[str, object] —— 后者会让每个消费点都得 cast，而 cast 会连带吞掉真实的键名拼写错误。
# largest_files / leaks 用 (体积, 相对路径) 元组：json 会序列化成二元组数组，读回后仍是列表，
# 消费侧无需区分 list 与 tuple。
class BundleReport(TypedDict):
    release: str
    total_bytes: int
    file_count: int
    packages: dict[str, int]
    package_file_counts: dict[str, int]
    largest_files: list[list[int | str]]
    leaks: list[list[int | str]]


def _mb(size: int) -> float:
    # 统一以 MB（二进制，1024 进制）展示，与 build_exe 的打印口径一致，便于日志对齐
    return round(size / 1024 / 1024, 2)


def collect(release: Path) -> BundleReport:
    # 遍历发布目录，产出「总量 / 按包聚合 / 最大单文件 / 泄漏清单」四份数据。
    # 单文件清单只保留 top 40：全量落 JSON 会让报告文件比产物清单还大，而体积分析永远只看
    # 头部那几十项（尾部是大量小文件，没有可操作空间）。
    total = 0
    count = 0
    per_pkg: dict[str, int] = defaultdict(int)
    per_pkg_n: dict[str, int] = defaultdict(int)
    files: list[tuple[int, str]] = []
    for root, _dirs, names in os.walk(release):
        rel_root = Path(root).relative_to(release)
        for name in names:
            path = Path(root) / name
            try:
                size = path.stat().st_size
            except OSError:
                continue
            total += size
            count += 1
            rel = (rel_root / name).as_posix()
            files.append((size, rel))
            parts = rel.split("/")
            # _internal/<pkg>/... 的第二段才是包名；根目录下的 exe 归到 "(根目录)"
            key = "(根目录)" if len(parts) == 1 else (parts[1] if parts[0] == "_internal" else parts[0])
            per_pkg[key] += size
            per_pkg_n[key] += 1
    files.sort(reverse=True)
    leaks = [(size, rel) for size, rel in files if _is_leak(rel)]
    return {
        "release": str(release),
        "total_bytes": total,
        "file_count": count,
        "packages": dict(sorted(per_pkg.items(), key=lambda kv: -kv[1])),
        "package_file_counts": dict(sorted(per_pkg_n.items(), key=lambda kv: -kv[1])),
        "largest_files": [[s, r] for s, r in files[:40]],
        "leaks": [[s, r] for s, r in leaks],
    }


def _is_leak(rel_path: str) -> bool:
    # 路径成分逐一比对（大小写无关）：既覆盖 _internal/mypy/...，也覆盖将来若改成
    # 别的布局时的 <any>/mypy/...；比字符串 contains 更严（不会把 mypy_utils 误判成 mypy）。
    parts = [p.lower() for p in rel_path.split("/")]
    return any(p in LEAK_PATTERNS for p in parts)


def render(report: BundleReport, top: int) -> str:
    # 渲染人类可读报告；--compare 时由调用方再追加一段比对，故本函数只管自身。
    lines: list[str] = []
    total = report["total_bytes"]
    lines.append("=" * 72)
    lines.append(f"发布体积报告：{report['release']}")
    lines.append(f"总计 {_mb(total)} MB / {report['file_count']} 个文件")
    lines.append("")
    lines.append(f"-- 按包聚合（前 {top}） --")
    packages = report["packages"]
    counts = report["package_file_counts"]
    for name, size in sorted(packages.items(), key=lambda kv: -kv[1])[:top]:
        lines.append(f"  {_mb(size):>10} MB  {counts.get(name, 0):>5} files  {name}")
    lines.append("")
    lines.append(f"-- 最大单文件（前 {top}） --")
    # 变量名刻意避开上面的 size：元素类型是 list[int | str]（JSON 数组的解包结果），
    # 复用同名变量会让 mypy 按首次绑定推断成 int 而报 [assignment]。
    for file_size, file_path in report["largest_files"][:top]:
        lines.append(f"  {_mb(int(file_size)):>10} MB  {file_path}")
    lines.append("")
    leaks = report["leaks"]
    lines.append("-- 开发 / 测试工具链泄漏 --")
    if leaks:
        for leak_size, leak_path in leaks[:20]:
            lines.append(f"  [LEAK] {_mb(int(leak_size)):>10} MB  {leak_path}")
        leak_bytes = sum(int(size) for size, _path in leaks)
        lines.append(f"  命中 {len(leaks)} 个文件，合计 {_mb(leak_bytes)} MB")
    else:
        lines.append("  未发现（✅）")
    return "\n".join(lines)


def compare(current: BundleReport, baseline: BundleReport) -> str:
    # 与上次报告比对：只报「总量 + 各包增减」，因为体积回归排查的顺序就是先看总量、
    # 再看是哪个包涨的；单文件级比对噪音太大（.pyd 每次构建都可能差几 KB）。
    cur_total = current["total_bytes"]
    base_total = baseline["total_bytes"]
    delta = cur_total - base_total
    pct = (delta / base_total * 100) if base_total else 0.0
    lines = [
        "",
        "-- 与基线比对 --",
        f"  总量 {_mb(base_total)} MB → {_mb(cur_total)} MB（{delta / 1024 / 1024:+.2f} MB, {pct:+.2f}%）",
    ]
    cur_pkgs = current["packages"]
    base_pkgs = baseline["packages"]
    diffs: list[tuple[int, str, int, int]] = []
    for name in set(cur_pkgs) | set(base_pkgs):
        cur = cur_pkgs.get(name, 0)
        base = base_pkgs.get(name, 0)
        if cur != base:
            diffs.append((abs(cur - base), name, base, cur))
    for _abs, name, b, c in sorted(diffs, reverse=True)[:15]:
        lines.append(f"  {name:24} {_mb(b):>10} MB → {_mb(c):>10} MB（{(c - b) / 1024 / 1024:+.2f} MB）")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="发布产物体积报告")
    _ = parser.add_argument(
        "release", nargs="?", default=str(DEFAULT_RELEASE), help="发布目录（默认 dist/DouyinLiveRecorder）"
    )
    _ = parser.add_argument("--top", type=int, default=20, help="聚合/单文件清单展示条数")
    _ = parser.add_argument("--json", dest="json_path", default="", help="把报告写成 JSON（供 --compare 使用）")
    _ = parser.add_argument("--compare", dest="baseline_path", default="", help="与该 JSON 报告比对")
    _ = parser.add_argument("--strict", action="store_true", help="检出工具链泄漏时以 exit 1 结束（CI 推荐）")
    args = parser.parse_args()

    release = Path(str(args.release))
    if not release.is_dir():
        print(f"[size] 发布目录不存在：{release}", file=sys.stderr)
        return 2

    report = collect(release)
    text = render(report, int(args.top))
    # 比对通道自己没能判定 → rc=2，与「发布目录不存在 → 2」同一档：度量面缺输入时不判
    # 代码不合格（1，那是 --strict 命中泄漏那一档），也不判通过（0）。
    # 旧形态「只追加一行 [warn] 就退 0」的沿革见文件头退出码说明，不在此重复。
    compare_unusable: str | None = None
    if str(args.baseline_path):
        baseline_path = Path(str(args.baseline_path))
        if not baseline_path.is_file():
            compare_unusable = f"基线报告不存在：{baseline_path}"
            text += f"\n\n[warn] 基线报告不存在，跳过比对：{baseline_path}"
        else:
            try:
                # 读回的是上一轮 --json 落盘的同一结构（JSON 只有 dict/list，与 TypedDict 同形）
                baseline: BundleReport = json.loads(baseline_path.read_text(encoding="utf-8"))
                text += compare(report, baseline)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                compare_unusable = f"基线报告不可用（{type(exc).__name__}: {exc}）：{baseline_path}"
                text += f"\n\n[warn] 基线报告不可用，跳过比对：{compare_unusable}"
    print(text)

    if str(args.json_path):
        out = Path(str(args.json_path))
        _ = out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[size] 已写入 JSON 报告：{out}")

    if compare_unusable is not None:
        # 「没跑成的判定」优先于「跑成了且不合格」：把 --strict 的泄漏失败与基线缺失折成同一个 1，
        # 就是拿 rc=1 去怪代码，而比对这一面根本没参与判定。
        print(f"[size][FATAL] --compare 未做判定：{compare_unusable}", file=sys.stderr)
        print("            这是「门禁没跑」，按 rc=2 结束；产物本身是否达标请另跑 --strict。", file=sys.stderr)
        return 2

    if bool(args.strict) and report["leaks"]:
        print("\n[size][FATAL] 发布产物含开发/测试工具链文件（--strict）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
