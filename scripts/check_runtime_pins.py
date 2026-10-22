# 运行时二进制 SHA256 钉定表的一致性检查（SEV-10 的门禁侧，CI 可调用）。
#
# 职责：校验 build_exe.py 里那张「按平台分列的运行时二进制钉定表」的**完整性与形状**，
#       并在发布路径上要求每一项都已填入官方值。
#
# 为什么需要单独一个检查：旧实现把表留成了空的 `_PINNED_RUNTIME_SHA256 = {}`，未钉定只 warn
#   后继续（SEV-10）——「空表」在旧实现里是**静默通过**的。本脚本把「空表 / 缺平台 / 缺槽位」
#   从可跳过状态升级为硬失败，因此它是 fail-closed 机器的前半段（后半段是 --require-pinned）。
#
# 两种模式（退出码语义不同，务必区分）：
#   默认（结构模式，进 AGENTS.md「格式化命令」门禁块）
#       —— 只查表的结构：表非空、键覆盖 RELEASE_RUNTIME_KEYS、每键含该平台**实际存在**的全部槽位
#          （通用槽位 + build_exe._EXTRA_EXECUTABLE_URLS 登记的独立归档件，且反向不许多留）、取值要么是
#          64 位小写十六进制、要么是明显的占位/可疑值。占位值只告警不判红：「官方哈希还没人工核实」
#          是开发期常态，不该弄红每个 PR。
#   --strict（发布模式，由 build-release.yml 的 prepare job 执行）
#       —— 占位/可疑值一律判红：发布链路绝不构建未经校验的产物。
#
# 钉定值的唯一事实源是 build_exe.py 的 _PINNED_RUNTIME_SHA256：本脚本动态加载它来取表，
# 「什么算填好了」也一律问 build_exe._slot_is_gated()（= 官方哈希已钉定 ∨ 第 4 类「源码可复现
# 构建」证据齐备 ∨ 官方签名档），这里不复述判定——两处各判一次，迟早演化出两种「已钉定」。
# 签名档的判据是上游公布的分离 GPG 签名 + 带外钉死的 40 位主钥指纹（登记在 _RUNTIME_GPG_SIGNATURES）。
# 本脚本新增的义务只是**按档播报**（[NOTE] 行），让报告不把「靠签名管住」说成「有 64 位十六进制哈希」。
# 同理**不得**把哈希副本写进 workflow：CI 用 --emit-env 的输出注入 DLR_RUNTIME_SHA256，
# 换版本只改 build_exe.py 一处。
# --strict 的失败集合只覆盖**发布矩阵真正构建的运行时键**；表里为本地/未来构建方保留的额外键
# （如 macos-x64）未钉定时只告警、且**必须把告警打出来**——没有 runner 产出它们，要求钉定既不拦下
# 任何真实产物，又制造「每个键都被管住了」的错觉。矩阵覆盖检查（第 4 段）才是防漏的那半。
#
# 用法：
#   python scripts/check_runtime_pins.py              # 结构检查（本地门禁 / ci.yml static）
#   python scripts/check_runtime_pins.py --strict     # 发布检查（build-release.yml prepare）
#   python scripts/check_runtime_pins.py --emit-env   # 打印 DLR_RUNTIME_SHA256 的 JSON 值（CI 注入用）
#
# --emit-env 与 --strict 可叠加（M-92，2026-10-21）：导出通道**先跑与默认模式同一套结构校验**，
#   校验不过就拒绝导出并按 check() 的分级返回（2 结构缺陷 / 1 --strict 下的未钉定项）。
#   stdout 只允许出现 JSON 一行（build-release.yml 用 pins=$(... --emit-env) 取用），报告走 stderr。
#
# 退出码：0 通过；1 --strict 下存在未钉定项（发布被拦）；2 结构缺陷 / 取不到表
#         （属「门禁本身失效」，与「代码不合格」区分，同 run_gates.py 口径）。

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent

# runner 标签 → 运行时键。与 build-release.yml 的 matrix.include 四平台一致：
# windows-latest / ubuntu-latest 为 x64，ubuntu-24.04-arm 为 linux aarch64，macos-latest 为 arm64（Apple Silicon）。
# 若矩阵将来改用显式架构标签或再加平台，须同步这张映射，否则会出现
# 「表里有键、矩阵里没平台」（无害）或「矩阵有平台、表里缺键」（本脚本报红）。
RUNNER_TO_RUNTIME_KEY = {
    "windows-latest": "windows-x64",
    "ubuntu-latest": "linux-x64",
    "ubuntu-24.04-arm": "linux-arm64",
    "macos-latest": "macos-arm64",
}

_OS_TAGS = ("windows", "linux", "macos")
_ARCH_TAGS = ("x64", "arm64")
_WORKFLOW = ROOT / ".github" / "workflows" / "build-release.yml"


def _load_build_exe() -> Any:
    # 以文件路径动态加载根目录 build_exe.py：scripts/ 不在包路径内，且 build_exe 在 import 期
    # 只做常量定义（main() 受 __name__ 守卫保护），加载是安全的。之所以「加载」而不是「AST 复制
    # 一份判定」：钉定表与其合法性判定的唯一事实源都在 build_exe.py，复制就会造出第二份事实源。
    path = ROOT / "build_exe.py"
    spec = importlib.util.spec_from_file_location("_runtime_pins_probe", path)
    if spec is None or spec.loader is None:
        print(f"ERROR: 无法加载 {path}", file=sys.stderr)
        sys.exit(2)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ValueError, TypeError, ImportError, SyntaxError, AttributeError) as exc:
        # M-93（2026-10-21）：build_exe.py 是**门禁自己的输入**，它读不出来 / 语法坏 / 顶层
        # import 失败时，旧形态是一条 Traceback + rc=1。而本文件头把 rc=1 明确留给
        # 「--strict 查到未钉定项」（= 发布链真的有问题），rc=2 才是「门禁本身失效」。
        # 取不到表就没有任何判定发生，必须走 rc=2，否则排障方向整体错掉。
        print(
            f"ERROR: 门禁自身失效：加载 {path} 失败 - {type(exc).__name__}: {exc}\n"
            "       钉定表取不到 = 「门禁没跑」，按 rc=2 处理；不要把它读成「发布链有未钉定项」。",
            file=sys.stderr,
        )
        sys.exit(2)
    return module


# 本门禁从 build_exe 取用的全部属性（判定口径一项都不许缺）。
# 为什么要点名清单：这些是 build_exe 的私有符号，改名/删除在 build_exe 侧不会有任何提示，
# 而本脚本直取属性时以 AttributeError 崩溃栈出场 = rc=1，与文件头「结构缺陷 / 取不到表 → rc=2」
# 的分级契约冲突（rc=1 会被读成「发布链查出了问题」，而真相是「门禁自己没查」）。
# 清单必须与 check()/emit_env() 的取用点同源；新增取用点同批登记，否则探测形同虚设。
_REQUIRED_BUILD_EXE_ATTRS: tuple[str, ...] = (
    "_PINNED_RUNTIME_SHA256",
    "RUNTIME_SLOTS",
    "RELEASE_RUNTIME_KEYS",
    "runtime_slots_for",
    "_slot_is_gated",
    "_is_source_build_marker",
    "_is_signature_marker",
    "_is_signature_satisfied",
    "UNVERIFIED_PIN",
    "SOURCE_BUILD_PROVENANCE",
    "OFFICIAL_SIGNATURE_PIN",
)


def _require_build_exe_attrs(module: Any) -> None:
    # 一次性探测并整批点名缺失项：只探第一个缺失符号的话，修一处还得再跑一次才见到下一处
    missing = [name for name in _REQUIRED_BUILD_EXE_ATTRS if not hasattr(module, name)]
    if missing:
        print(
            f"ERROR: {ROOT / 'build_exe.py'} 缺少发布链门禁依赖的属性 {missing}"
            "——属「门禁本身失效」，按 rc=2 处理；请先恢复/改名该属性，不要把它读成钉定表有问题",
            file=sys.stderr,
        )
        sys.exit(2)


def _runtime_matrix_keys() -> list[str]:
    # 从 build-release.yml 的 matrix.include 里解析出实际参与发布的 runner 标签，
    # 映射为运行时键。解析失败即报「门禁本身失效」，绝不退化成「无平台可查 → 通过」。
    if not _WORKFLOW.exists():
        print(f"ERROR: 找不到 {_WORKFLOW}，无法校验发布矩阵与钉定表的覆盖关系", file=sys.stderr)
        sys.exit(2)
    try:
        text = _WORKFLOW.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # M-93 同族：workflow 读不出来时旧形态是 rc=1 + Traceback，而「读不到矩阵」等于
        # 覆盖面无从核对 —— 与文件头「取不到表 → rc=2」同档。
        print(
            f"ERROR: 门禁自身失效：读取 {_WORKFLOW} 失败 - {type(exc).__name__}: {exc}\n"
            "       矩阵读不到就没有做过覆盖关系核对，按 rc=2 处理。",
            file=sys.stderr,
        )
        sys.exit(2)
    oses = re.findall(r"^\s*-\s*os:\s*([A-Za-z0-9._-]+)\s*$", text, re.MULTILINE)
    if not oses:
        print("ERROR: 未能从 build-release.yml 解析出 matrix 的 os 列表（结构可能已变更）", file=sys.stderr)
        sys.exit(2)
    unknown = [o for o in oses if o not in RUNNER_TO_RUNTIME_KEY]
    if unknown:
        print(
            f"ERROR: 发布矩阵出现未登记的 runner 标签 {unknown}，"
            f"请同步 scripts/check_runtime_pins.py 的 RUNNER_TO_RUNTIME_KEY",
            file=sys.stderr,
        )
        sys.exit(2)
    return [RUNNER_TO_RUNTIME_KEY[o] for o in oses]


def check(strict: bool) -> int:
    # 返回 0 通过 / 1 发布级失败（--strict 下存在未钉定项）/ 2 结构缺陷。
    module = _load_build_exe()
    # L-29：属性缺失（含被改名/删除）一律走 rc=2，不留 AttributeError 崩溃栈的 rc=1。探测必须在
    # 这里一次做完、而不是逐处 getattr 兜底：下面的判定口径全部取自 build_exe，缺一项就等于「没查」，
    # 而「没查」与「查过且通过」在 CI 里必须分得开（同 MID-63 口径）。
    _require_build_exe_attrs(module)
    table = cast("dict[str, dict[str, str]]", module._PINNED_RUNTIME_SHA256)
    slots = cast("tuple[str, ...]", module.RUNTIME_SLOTS)
    # 按运行时键查「该平台实际有几个槽」：macOS 的 ffprobe 是独立归档、需要自己的钉定项，
    # 而 windows/linux 的 ffprobe 随 ffmpeg 同包、没有独立公布值。槽位清单的事实源在
    # build_exe._EXTRA_EXECUTABLE_URLS，本脚本只问 runtime_slots_for()，不自判（并行清单禁令）。
    runtime_slots_for = cast("Any", module.runtime_slots_for)
    declared_keys = cast("tuple[str, ...]", module.RELEASE_RUNTIME_KEYS)
    # 判定口径一律取自 build_exe（见文件头）：本脚本不自己判形状，也不复制槽位/键清单
    slot_is_gated = cast("Any", module._slot_is_gated)
    is_marker = cast("Any", module._is_source_build_marker)
    is_sig_marker = cast("Any", module._is_signature_marker)
    is_sig_satisfied = cast("Any", module._is_signature_satisfied)
    placeholder = cast(str, module.UNVERIFIED_PIN)
    # 报错文案里引用的两个标记常量一律取自 build_exe，不在本文件复述字面值（并行事实源禁令）
    source_build_pin = cast(str, module.SOURCE_BUILD_PROVENANCE)
    signature_pin = cast(str, module.OFFICIAL_SIGNATURE_PIN)
    matrix_keys = _runtime_matrix_keys()

    problems: list[str] = []  # 结构缺陷 → rc=2
    unpinned: list[str] = []  # 矩阵内未钉定项 → --strict 时 rc=1
    unpinned_offmatrix: list[str] = []  # 矩阵外的键：只告警，绝不静默丢弃
    declared_class: list[str] = []  # 第 4 类已满足的槽位（显式列出，不与「已钉定」混为一谈）
    declared_sig: list[str] = []  # 官方签名档已满足的槽位（同上，另一种满足方式）

    # 1) 空表必须硬失败：SEV-10 的原始缺陷形态就是「表为空且无人察觉」
    if not table:
        problems.append("_PINNED_RUNTIME_SHA256 为空——未钉定的运行时二进制会被无校验打进发布包")

    # 2) 键形状与覆盖面：声明的运行时键必须逐个存在，不得多写不认识的键
    for key in declared_keys:
        if key not in table:
            problems.append(f"缺少运行时键 {key} 的钉定段")
    for key in table:
        if key not in declared_keys:
            problems.append(f"钉定段 {key} 不在 RELEASE_RUNTIME_KEYS 内（矩阵/表漂移）")
        os_tag, _, arch_tag = key.partition("-")
        if os_tag not in _OS_TAGS or arch_tag not in _ARCH_TAGS:
            problems.append(f"钉定键 {key} 不符合 <os>-<arch> 形态")

    # 3) 每个键都要覆盖该平台**实际存在**的槽位（见 runtime_slots_for），且取值合法或明确未钉定
    for key, entry in table.items():
        if not isinstance(entry, dict):
            problems.append(f"{key} 的值不是 {{槽位: 哈希}} 映射")
            continue
        expected_slots = runtime_slots_for(key)
        for slot in expected_slots:
            value = str(entry.get(slot, ""))
            if slot not in entry:
                problems.append(f"{key} 缺少槽位 {slot} 的钉定项")
                continue
            if slot_is_gated(value, key, slot):
                if is_marker(value):
                    declared_class.append(f"{key}/{slot} 走第 4 类（源码可复现构建，三件证据齐备）")
                elif is_sig_satisfied(value, key, slot):
                    # 与「已钉定 64 位十六进制」分开播报：这一档靠的是官方分离签名 + 带外钉死的
                    # 主钥指纹，报告里若把它算作「已钉定」就等于谎称发布链拿到的是一手哈希。
                    declared_sig.append(f"{key}/{slot} 走官方签名档（无公布哈希，判据 = GPG 验签 + 钉定指纹）")
                continue
            if is_marker(value):
                # 声明了第 4 类但证据不齐 = 与「未钉定」同等处置。这条是防「换个标记拿免检」的关键：
                # 标记若比 64 位十六进制更容易填，放宽判定就等于把闸口拆了。
                unpinned.append(f"{key}/{slot} 声明为第 4 类但证据不齐（三件证据缺任一或形状不符）")
                continue
            if is_sig_marker(value):
                # 同一条防线用在签名档上：光有标记、签名表里却没这一槽（或指纹形状不符）必须同等拦下。
                unpinned.append(
                    f"{key}/{slot} 声明为官方签名档但未满足（该槽未在 _RUNTIME_GPG_SIGNATURES 登记，或指纹非 40 位十六进制）"
                )
                continue
            reason = "仍是占位标记" if value == placeholder else ("取值为空" if not value else f"形状非法（{value!r}）")
            bucket = unpinned if key in matrix_keys else unpinned_offmatrix
            bucket.append(f"{key}/{slot} 未钉定：{reason}")
        # 反向：表里多出一个该平台并不存在的下载槽位同样要报——它意味着「有人在钉定表里给一个
        # 没有下载点的组件留了通行证」，而 runtime_slots_for() 的事实源里并没有这一项。
        for slot in entry:
            if slot not in expected_slots:
                problems.append(f"{key} 含槽位 {slot} 的钉定项，但该平台没有这个下载点（表与来源漂移）")

    # 4) 与发布矩阵的覆盖关系（跨文件同源检查，防「矩阵加了平台、表里没这一份」）
    for key in matrix_keys:
        if key not in table:
            problems.append(f"发布矩阵需要 {key}，但钉定表无该段")

    per_key_slots = sorted({len(runtime_slots_for(key)) for key in table})
    # 空表在前面已判为结构缺陷（problems 非空即 rc=2），但打印发生在 rc 判定之前，所以这里仍要
    # 能吃下「一个键都没有」——否则报告会以 IndexError 崩掉，把「表为空」换成一句栈回溯。
    if not per_key_slots:
        span = "0"
    elif len(per_key_slots) == 1:
        span = str(per_key_slots[0])
    else:
        span = f"{per_key_slots[0]}~{per_key_slots[-1]}"
    print(f"运行时二进制钉定表：{len(table)} 个运行时键 × {span} 个槽位（通用 {len(slots)} 个，独立归档件按平台另计）")
    print(f"发布矩阵运行时键：{', '.join(matrix_keys)}")

    if problems:
        print("\n[FAIL] 钉定表结构缺陷（门禁本身失效，按 rc=2 处理）:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    for line in declared_class:
        print(f"[NOTE] {line}")
    for line in declared_sig:
        print(f"[NOTE] {line}")

    if unpinned_offmatrix:
        # 矩阵外的键：本地/未来构建方保留的段。只告警，但**必须打出来**——静默省略等于让后来
        # 的人以为「表里所有键都被 --strict 管着」。
        print(
            f"\n[WARN] {len(unpinned_offmatrix)} 个槽位未钉定，但其运行时键不在发布矩阵内（无 runner 产出，不参与 --strict 判定）:"
        )
        for u in unpinned_offmatrix:
            print(f"  - {u}")

    if unpinned:
        print(f"\n[WARN] {len(unpinned)} 个**矩阵内**槽位尚未钉定（官方哈希待人工核实）:")
        for u in unpinned:
            print(f"  - {u}")
        if strict:
            print(
                "\n[FAIL] --strict（发布路径）：发布矩阵所需槽位存在未钉定项即终止。"
                "请核对官方公布值后写入 build_exe.py 的 _PINNED_RUNTIME_SHA256，"
                "或由 CI 注入 DLR_RUNTIME_SHA256；上游确实不公布哈希时改走第 4 类"
                f"（{source_build_pin} + 三件证据，见 W1）"
                f"或官方签名档（{signature_pin}"
                " + _RUNTIME_GPG_SIGNATURES 登记签名 URL 与完整主钥指纹）。",
                file=sys.stderr,
            )
            return 1
        print("  → 本地门禁放行；build-release.yml 的 prepare job 以 --strict 拦下发布。")
    elif not unpinned_offmatrix:
        print("\n[OK] 全部槽位均已钉定（64 位十六进制）、已按第 4 类给出齐备证据，或已按官方签名档钉定指纹")
    return 0


def emit_env(strict: bool = False) -> int:
    # 打印 DLR_RUNTIME_SHA256 应取的 JSON（按运行时键分列），供 CI 注入 build job。
    # 占位值原样导出：build_exe 侧仍按形状判定为未钉定，因此这条通道不会把
    # 「没填」伪装成「已填」。
    #
    # M-92（2026-10-21）：导出通道**必须先跑与 check() 完全相同的结构校验**再打印。
    # 旧形态只探测属性存在就打印并 return 0 —— 于是一张「空表 / 缺键 / 缺槽位 / 键形状不符」的
    # 钉定表照样能被导出进 CI（build_exe 侧的 fail-closed 只是纵深第二层，不是这条通道的自证）。
    # 校验复用 check() 本体而不是另写一份判据：两处各判一次迟早演化出两种「结构合法」。
    # 返回值沿用 check() 的分级：2 = 结构缺陷（门禁没判成），1 = --strict 下的未钉定项，
    # 0 才允许导出。stdout 必须**只有 JSON**（build-release.yml 以 pins=$(... --emit-env) 取它），
    # 故校验期间把 stdout 重定向到缓冲区：失败时把人类可读报告转写 stderr，成功时整段丢弃。
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        rc = check(strict=strict)
    if rc != 0:
        report = buffer.getvalue()
        if report:
            sys.stderr.write(report)
        print(
            "ERROR: --emit-env 拒绝导出：钉定表未通过结构检查（判定见上），"
            f"把破损的表透传给 build job 等于用「导出成功」冒充「表可用」。rc={rc}",
            file=sys.stderr,
        )
        return rc
    module = _load_build_exe()
    # 同 check()：--emit-env 是 CI 注入钉定值的通道，属性缺失时也必须 rc=2（门禁自己没跑成），
    # 而不是 rc=1 崩溃栈——build job 会把「拿不到表」读成「表里有未钉定项」。
    _require_build_exe_attrs(module)
    table = cast("dict[str, dict[str, str]]", module._PINNED_RUNTIME_SHA256)
    print(json.dumps(table, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行时二进制 SHA256 钉定表一致性检查")
    _ = parser.add_argument("--strict", action="store_true", help="发布模式：存在未钉定项即失败")
    _ = parser.add_argument("--emit-env", action="store_true", help="输出 DLR_RUNTIME_SHA256 的 JSON 值")
    args = parser.parse_args(argv)
    if cast(bool, args.emit_env):
        return emit_env(strict=cast(bool, args.strict))
    return check(strict=cast(bool, args.strict))


if __name__ == "__main__":
    sys.exit(main())
