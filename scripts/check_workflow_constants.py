# CI / Build-Release 版本常量一致性门禁。
#
# ci.yml 的 setup job 与 build-release.yml 的 prepare job 各自在 consts 步骤声明
# python_build / node_version 两个运行环境常量。AGENTS.md「CI / workflow 约定」要求
# 「版本常量跨 workflow 同值」，但两份文件独立维护、改一处须同步另一处——纯靠人工对齐
# 已被证明会漂移。本脚本在两侧各自提取后比对，不一致即红。
#
# 提取策略：正则匹配 `echo "key=value"` 形态（GitHub Actions 的 GITHUB_OUTPUT 写入惯例），
# 刻意不引入 PyYAML 依赖——两份文件都只在一个 consts 步骤内写这些 key，精确匹配 key= 前缀即可。
#
# 退出码：0 一致；1 常量不一致；2 workflow 文件缺失或提取失败（门禁本身没数据可判）。
#

import re
import sys
from pathlib import Path

# 项目根目录（scripts/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent

# 需要校验的常量键——AGENTS.md「CI / workflow 约定」列出的跨 workflow 同值项
CONST_KEYS = ("python_build", "node_version")

# 须比对的两份 workflow
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"
BR_PATH = ROOT / ".github" / "workflows" / "build-release.yml"


def extract_consts(workflow_path: Path) -> dict[str, str]:
    # 从 workflow 文件的 consts 步骤提取版本常量：匹配 echo "key=value" / echo 'key=value'。
    # 只取第一个匹配——本脚本职责是「跨文件一致性」，同文件内重复声明不在检测范围内。
    if not workflow_path.exists():
        print(f"ERROR: workflow 文件不存在: {workflow_path}", file=sys.stderr)
        sys.exit(2)
    text = workflow_path.read_text(encoding="utf-8")
    result: dict[str, str] = {}
    for key in CONST_KEYS:
        # 匹配 echo "key=value" —— value 不含引号/换行，用 [^\s"']+ 足够
        pattern = rf'echo\s+["\']?{re.escape(key)}=([^\s"\']+)["\']?'
        m = re.search(pattern, text)
        if not m:
            print(
                f"ERROR: 无法从 {workflow_path.name} 提取 {key}（consts 步骤可能已变更形态）",
                file=sys.stderr,
            )
            sys.exit(2)
        result[key] = m.group(1)
    return result


def main() -> int:
    ci_vals = extract_consts(CI_PATH)
    br_vals = extract_consts(BR_PATH)

    errors: list[str] = []
    for key in CONST_KEYS:
        ci_v = ci_vals[key]
        br_v = br_vals[key]
        if ci_v == br_v:
            print(f"  [OK]   {key}: {ci_v}（ci.yml == build-release.yml）")
        else:
            errors.append(
                f"  [FAIL] {key}: ci.yml={ci_v}  build-release.yml={br_v}"
                f"  ——改一处须同步另一处（AGENTS.md「CI / workflow 约定」）"
            )

    if errors:
        print("\n版本常量跨 workflow 不一致:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    print("\n[PASS] ci.yml 与 build-release.yml 版本常量一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
