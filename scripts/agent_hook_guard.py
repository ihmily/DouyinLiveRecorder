#!/usr/bin/env python3
# Qoder 项目级 Hook 执行体：把 AGENTS.md「风险控制（前置）」的红线与「对门禁三面隐形」的约束，
# 落到工具生命周期上的确定性检查点。
#
# 为什么需要 Hook（而不是只靠 AGENTS.md 文字）：那几条约束原本是「prose + 每次人工执行」的形态，
# 而两种后果都不可接受——① 不可逆：批量重装 venv 依赖时沙箱拦截发生在 pip 已开始卸载之后、包目录
# 被清空（AGENTS.md「venv 依赖修复分级处置」）；收尾清理越界会连运行期产物一起删。② 隐形：
# 变异验证标记残留与整文件换行符翻转，对 black / mypy / 注释检查三面全不报错，只有用例真跑到
# 那条分支才现形（AGENTS.md「变异验证的一次性改动必须当轮还原」「注释检查工具·三个盲点」）；
# 新增 `tests/frontend/*.mjs` 忘登记 ci.yml 同理——`node --test <文件>` 不会顺带发现同级其他
# `.mjs`，该文件的全部回归锁在 CI 里从不执行（M-28 实证）；运行时钉定表（`build_exe.py` 的
# `_PINNED_RUNTIME_SHA256` / `scripts/check_runtime_pins.py`）改后不跑 check 同理——空表 /
# 缺平台 / 缺槽位对 black / mypy / 注释检查三面全隐形，只有 check_runtime_pins.py 自己能兜住
# （SEV-10）。判据每次都要执行又容易被忘，正是 Hook
# 的适用面；本文件只做**判定与反馈**，不引入第二套门禁清单。
#
# 事实源关系：约束本体仍是 AGENTS.md。下面的目录名集合、命令形态、登记位置都逐字取自对应条目；
# 改判据时先改 AGENTS.md，再由 tests/test_agent_hook_guard.py 把两侧一致性钉成回归锁
# （受保护目录集合必须与 AGENTS.md「运行期产物目录」口径逐项相等，漂移即红）。
#
# 事件与出口约定（Qoder 官方 Hooks 文档 https://docs.qoder.com/extensions/hooks，2026-10-02 复核）：
#   - stdin 收一个 JSON 事件上下文（PreToolUse / PostToolUse），不是命令行参数。
#   - 出口能力由事件的 Blockable 决定，两条通道不同：
#   - PreToolUse 可阻断：exit 2 阻止命令执行，stderr 作为错误回给 agent（真正的「拦」只在这一站）。
#   - PostToolUse 非阻断：写入已发生、不可撤销；官方退出码表注明 exit 2 的 stderr 注入
#     「only for blockable events」，对本事件不构成可靠通道，故走文档化出口——
#     exit 0 + stdout JSON `hookSpecificOutput.feedback` 即时回传，让 agent 当场修。
#     [历史注] 旧版对 Pre/Post 统一声明「exit 2 = 拦截当前动作」，经 provider 文档证伪后改为上述双轨。
#   - 「当轮还原」的真正切断点因此不在本 Hook 的 Post 一站，而在仍可判红的收尾门禁
#     （tests/test_test_hygiene.py R8 全仓扫描、run_gates.py / CI）——feedback 被忽略时由它们兜住入库前最后一道闸。
#   - 拒绝/反馈消息**不得**回显完整命令原文、prompt 或环境变量值（官方 hook 安全口径），
#     只给规则短 id 与命中的目录名/文件名。
#   - 脚本自身异常一律放行并打一条 stderr 提示：Hook 坏掉绝不能演变成「agent 什么也做不了」，
#     那是把工具故障伪装成代码不合格；真正的质量判定仍由 run_gates.py / CI 承担。
#   - 覆盖边界：PostToolUse 的注册 matcher 是写入类工具（Write|Edit|SearchReplace|MultiEdit），
#     判定只认 tool_input 的 file_path 类字段；Bash/Shell 命令内的文件写入不经该事件——这是
#     已知边界而非漏洞：相关约束（运行时钉定、MUTATION 还原等）由收尾门禁（R8 全仓扫描 /
#     run_gates.py / CI）在入库前兜底，本 Hook 不追求、也做不到覆盖命令级写入。
#   - UTF-8：拒绝理由与反馈都是中文，中文 Windows（cp936）下写 stderr 会抛 UnicodeEncodeError
#     炸掉 Hook 进程（与 MID-63 同根因），故 stdout/stderr 都要 reconfigure 并显式给 errors。
#
# 用法（由 .qoder/settings.json 的 hooks 注册调用，不需要手工执行）：
#   python scripts/agent_hook_guard.py            # 从 stdin 读事件 JSON
#   python scripts/agent_hook_guard.py --self-test  # 内置样例事件自检，验证规则真的会拦
#
# 退出码：0 放行或 Post 侧即时回传（feedback 不是失败）；2 仅 PreToolUse 命中拦截规则；1 仅 --self-test 自检失败时出现。

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

# 项目根目录（脚本在 scripts/ 下，上一级即根），用于把相对 file_path 解析成绝对路径
ROOT = Path(__file__).resolve().parent.parent

# AGENTS.md「CI / workflow 约定」的 dockerignore/gitignore 同源条目把这几个目录定义为
# **运行期产物目录**（录制文件、日志、配置备份）。收尾清理只限本次任务产生的一次性脚本与
# tests/ 下的临时输出，这些目录一律不动。集合内容被 tests/test_agent_hook_guard.py 与
# AGENTS.md 逐项对齐，不得在这里单方面增删。
PROTECTED_RUNTIME_DIRS: tuple[str, ...] = ("downloads", "logs", "backup_config", "recordings")

# AGENTS.md「测试收尾清理临时脚本」的第二条禁区：`**不要**动 scripts/ 下正式维护脚本`。
# 与运行期产物分开建模——它不是产物目录，而是「长期复用代码的家」，误删后果是门禁本身失效。
PROTECTED_MAINTENANCE_DIR = "scripts"

# 删除动作的动词面：PowerShell / cmd / POSIX shell / Python 单行写法都要覆盖。
# 只认动词，不认「出现 delete 字样」——`git status`、`ls` 之类不在此列，避免把只读命令拦下。
_DELETE_VERB_RE = re.compile(
    r"\b(Remove-Item|Rm|Del|Erase|Rd|Rmdir|shutil\.rmtree|os\.remove|os\.unlink|unlink|find)\b",
    re.IGNORECASE,
)

# `find` 只有在带 -delete / -exec rm 时才是删除；`find . -name x` 是只读查询，不得拦。
_FIND_DELETE_RE = re.compile(r"-delete\b|-exec\s+rm\b", re.IGNORECASE)

# 过滤面标记：出现任一即认为这条删除命令带了「按名字/路径挑文件」的白名单，
# AGENTS.md 给出的两条收尾清理命令（-Include *_tmp_*.py / -name '*_tmp_*.py'）都属这一类。
_FILTER_RE = re.compile(r"-Include\b|-name\b|-iname\b|-notmatch\b|-not-like\b|-Exclude\b|-Filter\b", re.IGNORECASE)

# 排除式上下文：受保护目录名若只出现在 -notmatch / not -path 这类**排除式**里，说明它是
# 「不要碰」的白名单而不是删除目标（AGENTS.md 清理命令的 Where-Object 子句正是这种写法）。
_EXCLUSION_RE = re.compile(r"notmatch|not-like|not\s+-path|Exclude", re.IGNORECASE)

# pip 批量重装形态（AGENTS.md「venv 依赖修复分级处置」的三级命令）。
# 只拦批量重装，不拦常规补装：二级处置 `HTTP_PROXY="" HTTPS_PROXY="" pip install --proxy "" <pkg>`
# 是代理可以自行尝试的，拦下来会挡住合法路径。
_PIP_FORCE_REINSTALL_RE = re.compile(r"\bpip[0-9.]*\s+install\b[^|;&\n]*--force-reinstall", re.IGNORECASE)
_PIP_IGNORE_INSTALLED_REQ_RE = re.compile(
    r"\bpip[0-9.]*\s+install\b[^|;&\n]*--ignore-installed\b[^|;&\n]*(?:-r\s|requirements\.txt)",
    re.IGNORECASE,
)

# `git clean` 带 -f 且带 -d/-x 时是工作区级不可逆删除（含未跟踪的运行期产物）。
# AGENTS.md「铁律：临时文件零残留」要求绝对路径、逐个删，禁止顺手 git clean 整个工作区。
_GIT_CLEAN_RE = re.compile(r"\bgit\s+clean\b[^\n]*-[a-zA-Z]*f", re.IGNORECASE)

# 递归+强制删除的开关组合（rm -rf / Remove-Item -Recurse -Force / rd /s /q）。
_RECURSIVE_FORCE_RE = re.compile(
    r"(?:^|\s)-{1,2}(?:Recurse)[^\n]*(?:^|\s)-{1,2}(?:Force)"
    r"|(?:^|\s)-{1,2}(?:Force)[^\n]*(?:^|\s)-{1,2}(?:Recurse)"
    r"|(?:^|\s)-[rRfF]{2,}(?:\s|$)"
    r"|(?:^|\s)/[sS](?:\s|$)[^\n]*(?:^|\s)/[qQ]",
)

# 「裸大范围目标」token：`.` / `*` / `./` 这类没有落到具体文件名的删除目标。
# 用整词相等判定而不是正则，避免把 `*_tmp_*.py` 这种带过滤语义的通配误判成裸 `*`。
_BARE_WIDE_TOKENS: frozenset[str] = frozenset({".", "./", ".\\", "*", "./*", ".\\*", "*", "$PWD", "%CD%", ".", "\\"})

# 变异验证标记（AGENTS.md「变异验证的一次性改动必须当轮还原，并给改动行加变异标记」那条）。
# R8 全仓扫描是**事后**兜底；本 Hook 在写入当下就报，避免残留活到下一次门禁。
# 刻意不在守卫里写完整字面量拼接形态，与 tests/test_test_hygiene.py 的自指规避同理。
_MUTATION_MARK = "MUTA" + "TION-"

# AGENTS.md「注释检查工具·三个盲点」第 3 条的原文判据，逐字复现给 agent（不自己发明新命令，
# 否则反馈里的命令与实际门禁口径会漂移）。写成拼接形式只为不超过 black 的 120 行宽，
# 转义后的字面量与文档里那条一致。
LINE_ENDING_PROBE = (
    'python -c "import pathlib;b=pathlib.Path(f).read_bytes();'
    "print(b.count(b'\\r\\n'), b.count(b'\\n')-b.count(b'\\r\\n'))\""
)

# 前端用例登记位置（AGENTS.md「新增 .mjs 必须同批登记进 ci.yml」）：
# 该步骤用 node-id 精确选取，形态是 tests/frontend/test_x.py::test_x，所以判据取 .py 包装入口。
_CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# P-RUNTIME-PIN 的反馈文案：两个命中分支共用一份定义，改文案只改这一处（2026-10-17 审查：
# 原实现两个分支各抄一遍约 6 行消息，单边修改会静默漂移）。命中文件名由调用方拼入——与
# P-MJS-REGISTER 同口径，且符合模块头「只回显规则短 id 与命中的文件名」的官方 hook 安全约定。
# 文案里的命令形态逐字取自 AGENTS.md 门禁清单（`python scripts/check_runtime_pins.py`），
# 不自己发明新命令，避免反馈与实际门禁口径漂移。
_RUNTIME_PIN_MESSAGE = (
    "本次写入涉及运行时钉定表（`build_exe.py` 的 `_PINNED_RUNTIME_SHA256` 或"
    " `scripts/check_runtime_pins.py`）。AGENTS.md 要求收尾时必须执行"
    " `python scripts/check_runtime_pins.py` 并记录输出，确保钉定表结构完整"
    "（空表 / 缺平台 / 缺槽位对 black / mypy / 注释检查三面全隐形，SEV-10）。"
    " 闭合标记：changed-without-check → check-observed。"
)

# 不参与行尾形态判定的目录名：工具生成目录 + 运行期产物目录 + 第三方运行时。
# 取「pyproject [tool.isort].extend_skip 有的这里也得有」的保守方向（与
# scripts/check_annotations.py 的 EXCLUDE_DIRS 同一口径），比那边更严不会误伤；
# 漂移由 tests/test_agent_hook_guard.py 逐名比对钉住。
# 为什么用**黑名单**而不是「只查 src/scripts/tests」的白名单：Hook 拿到的常常是绝对路径，
# 工作副本目录名随机器变化（本仓就在 D:\DouyinLiveRecorder），白名单会让判定在别的检出路径上
# 静默失效；黑名单只依赖目录名，与检出位置无关。
_SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "node_modules",
        "build",
        "dist",
        "typings",
        "node",
        "ffmpeg",
        "downloads",
        "recordings",
        "logs",
        "backup_config",
        ".agents",
        ".qoder",
        ".qoder-credits",
        ".workbuddy",
        ".codebuddy",
        ".trae",
        ".plugin-src",
        ".dsh-validation",
        ".ego-browser-test",
        ".npm-cache",
        ".pnpm-store",
        ".mimosa",
        ".tmp-dps-extract",
        ".v2c",
    }
)


def ensure_utf8_streams() -> None:
    # 把本进程 stdout/stderr 固定为 UTF-8 且显式给 errors：Hook 的反馈文本是中文，
    # 中文 Windows 控制台默认 cp936，遇到打不出的码点会抛 UnicodeEncodeError 把 Hook 进程本身炸掉
    # （与 scripts/run_gates.ensure_utf8_streams、build_exe._ensure_utf8_streams 同根因同手法）。
    # errors="replace" 只兜底显示，绝不允许「输出失败」升级成「拦截判定丢失」。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except OSError, ValueError:
            # 已被重定向到已关闭/非法句柄时静默放过：本函数只改善输出，不参与判定。
            pass


def read_event() -> dict[str, Any]:
    # 从 stdin 读取事件 JSON。字节读取 + errors="replace"：事件里可能带中文路径或中文内容，
    # 按平台默认编码（GBK locale）解码会抛错；坏字节只损失显示，不影响规则判定。
    raw = sys.stdin.buffer.read()
    if not raw.strip():
        return {}
    loaded = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(loaded, dict):
        return {}
    return loaded


def event_name(event: dict[str, Any]) -> str:
    # 事件名兼容两种字段写法（hook_event_name / hookEventName），缺失时返回空串交调用方放行。
    for key in ("hook_event_name", "hookEventName", "event", "eventName"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def tool_input(event: dict[str, Any]) -> dict[str, Any]:
    # 取工具入参：正常在 tool_input 下；个别形态直接铺在事件顶层，故兜底回退到 event 本体。
    payload = event.get("tool_input")
    if isinstance(payload, dict):
        return payload
    payload = event.get("toolInput")
    if isinstance(payload, dict):
        return payload
    return event


def _statements(command: str) -> list[str]:
    # 按「独立操作」切分：`;`、`&&`、`||`、换行。管道 **不**切——
    # `Get-ChildItem ... | Remove-Item` 是一个逻辑操作，切开会丢掉左侧的路径目标（漏报）。
    parts = re.split(r"&&|\|\||[;\n]", command)
    return [part for part in parts if part.strip()]


def _protected_hit(statement: str, name: str) -> bool:
    # 判定受保护目录是否以**目录形态**出现在这条语句里：
    # 后接 / \ 或以该名字结尾（`Remove-Item -Recurse logs`），且前面不是更长标识符的一部分
    # （避免 `download_logs_table` 这类名字被误命中）。
    for match in re.finditer(rf"(?<![\w.\-]){re.escape(name)}(?![\w.\-])", statement, re.IGNORECASE):
        tail = statement[match.end() : match.end() + 1]
        if tail and tail not in "/\\":
            continue
        head = statement[max(0, match.start() - 60) : match.start()]
        if _EXCLUSION_RE.search(head):
            # 出现在排除式（-notmatch / -Exclude / not -path）里 → 是白名单，不是删除目标。
            continue
        return True
    return False


def check_bash_command(command: str) -> tuple[str, str] | None:
    # 返回 (规则短 id, 给 agent 的反馈) 或 None（放行）。规则全部对应 AGENTS.md 条目原文。
    statements = _statements(command)

    # R-PIP-BULK：批量重装 venv 依赖必须由用户在普通终端执行（沙箱拦截发生在卸载之后）。
    if _PIP_FORCE_REINSTALL_RE.search(command) or _PIP_IGNORE_INSTALLED_REQ_RE.search(command):
        return (
            "R-PIP-BULK",
            "批量重装 venv 依赖已被项目约定拦下：沙箱拦截发生在 pip 已开始卸载之后，会清空包目录。"
            " 请按 AGENTS.md「venv 依赖修复分级处置」走——一级用 `pip download --no-deps` + wheel "
            '直解，二级单个小包 `HTTP_PROXY="" HTTPS_PROXY="" pip install --proxy "" <pkg>`，'
            "三级批量重装须交回用户在普通终端执行。",
        )

    for statement in statements:
        if _GIT_CLEAN_RE.search(statement) and re.search(r"-\w*[dx]", statement):
            # R-WIPE-SCOPE：工作区级 git clean 会连带未跟踪的运行期产物与 tests/ 临时输出。
            return (
                "R-WIPE-SCOPE",
                "`git clean -f...` 属工作区级不可逆删除，AGENTS.md「测试收尾清理临时脚本」只允许"
                " 删除本次任务产生的、路径明确的一次性脚本与输出：请逐个文件按绝对路径删除，"
                "被 safe-delete 拦截时逐文件重试或列出残留交回用户，不得静默跳过。",
            )

        if not _DELETE_VERB_RE.search(statement):
            continue
        if "find" in statement.lower() and not _FIND_DELETE_RE.search(statement):
            # 只读 find 查询（无 -delete/-exec rm）不参与删除判定。
            continue

        for name in PROTECTED_RUNTIME_DIRS + (PROTECTED_MAINTENANCE_DIR,):
            if _protected_hit(statement, name):
                return (
                    "R-CLEAN-SCOPE",
                    f"清理范围越界：该删除语句的目标命中受保护目录 `{name}/`。AGENTS.md 规定收尾清理"
                    " 只限本次任务产生的一次性脚本与 `tests/` 下用例生成的临时输出，运行期产物目录与"
                    " `scripts/` 下正式维护脚本一律不动。确需清理请交回用户确认。",
                )

        if _RECURSIVE_FORCE_RE.search(statement) and not _FILTER_RE.search(statement):
            # 递归+强制删除且没有任何按名字/路径过滤面 → 通配级删除，禁止。
            for token in re.split(r"[\s'\"`;|&()]+", statement):
                if token.lower() in _BARE_WIDE_TOKENS:
                    return (
                        "R-WIPE-SCOPE",
                        "递归/通配整体删除（目标为 `.` 或 `*` 且无 `-Include`/`-name` 之类过滤）被拦下："
                        " AGENTS.md「测试收尾清理临时脚本」要求只删本次任务自己产生的文件，"
                        " 按绝对路径逐个删。请先枚举待删路径再执行。",
                    )
    return None


def _check_runtime_pins_changed(
    path: Path, segments: list[str], anchored: bool | None = None
) -> tuple[str, str] | None:
    # P-RUNTIME-PIN：写入目标命中运行时钉定表所在文件时，即时提醒 agent 收尾跑 check
    # （AGENTS.md「发布链运行时二进制必须 fail-closed 钉定（SEV-10）」第三层防线）。
    #
    # 定位策略分两档（2026-10-17 审查 S1 定稿）：
    #   - 路径在 ROOT 内（anchored=True）按**规范位置**精确锚定：根级 build_exe.py 与
    #     scripts/check_runtime_pins.py。tests/、docs/ 下的同名文件不是钉定表本体，误报会
    #     训练 agent 养成忽略反馈的习惯——放行面同样承重，理由见 tests 放行面用例注释。
    #   - 路径在 ROOT 外（tmp_path、其他检出副本）看不到仓库根在哪，只能退回末尾分段匹配，
    #     与检出位置无关（与 P-MJS-REGISTER 同手法）。
    # dist/、build/ 等工具产物目录内的同名文件一律跳过：PyInstaller 产物里出现同名文件不是
    # 钉定表被改（排除口径与 P-LINE-ENDING 的 _in_skipped_dir 保持一致）。
    #
    # 判定只用 segments（_relative_segments 已小写化）做全等匹配：末段同时蕴含文件名与 .py
    # 后缀，故不再另判 path.stem / path.suffix——stem 未小写化时 `BUILD_EXE.PY` 会漏报，且
    # 两条判断与 segments[-1] 重复，大小写口径分裂正是原实现的问题根因（审查 S2）。
    if _in_skipped_dir(path):
        return None
    if anchored is None:
        anchored = _is_inside_root(path)
    name = segments[-1] if segments else ""
    if name == "build_exe.py" and (not anchored or len(segments) == 1):
        return ("P-RUNTIME-PIN", f"写入 `{path.name}`：{_RUNTIME_PIN_MESSAGE}")
    if (
        len(segments) >= 2
        and segments[-2] == "scripts"
        and name == "check_runtime_pins.py"
        and (not anchored or len(segments) == 2)
    ):
        return ("P-RUNTIME-PIN", f"写入 `{path.name}`：{_RUNTIME_PIN_MESSAGE}")
    return None


def resolve_path(raw: str) -> Path:
    # file_path 可能是绝对路径，也可能相对工作区根；统一解析到 ROOT 之下再判定。
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _relative_segments(path: Path) -> list[str]:
    # 相对 ROOT 的路径分段（小写）；不在 ROOT 内时返回分段列表，由调用方按结构判定。
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return [part.lower() for part in path.parts]
    return [part.lower() for part in rel.parts]


def _is_inside_root(path: Path) -> bool:
    # 路径是否位于 ROOT 之内。判定式与 _relative_segments 逐字同构（resolve + relative_to），
    # 保证「锚定标志」与「分段形态」永不矛盾：符号链接/Junction 让 resolve 结果落在 ROOT 外时，
    # 两侧同时落到「根外」分支（分段取完整路径、锚定关闭），不会出现「短分段却未锚定」的中间态
    # 把根级文件误判成嵌套文件。
    try:
        path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return True


def _in_skipped_dir(path: Path) -> bool:
    # 路径任一分段命中黑名单即跳过判定。按**分段**比对而非子串匹配，
    # 避免 download_logs_table / my.node_modules.pkg 这类名字造成误判。
    return any(part.lower() in _SKIP_DIR_NAMES for part in path.parts)


def check_written_file(path: Path) -> tuple[str, str] | None:
    # PostToolUse 侧判定：写入已发生，这里只做「隐形回归」的即时反馈（非阻断，见模块头双轨口径）。
    if not path.is_file():
        return None
    segments = _relative_segments(path)

    raw = path.read_bytes()

    # P-MUTATION：变异标记残留在生产代码里对 black/mypy/注释检查三面隐形（2026-09-30 实测事故），
    # 只有用例真跑到那条分支才现形——所以必须在写入当下报。
    if _MUTATION_MARK.encode() in raw:
        return (
            "P-MUTATION",
            f"写入内容里仍有变异验证标记（`{_MUTATION_MARK}`）：AGENTS.md 要求一次性改动当轮还原，"
            " 并断言 `read_bytes()==原字节`。该残留对 black / mypy / 注释检查全隐形，"
            " 只会被 tests/test_test_hygiene.py 的 R8 全仓扫描判红。请立即还原改动行。",
        )

    # P-LINE-ENDING：本仓约定每个文件行尾形态单一（纯 CRLF 或纯 LF）。整文件重写会静默翻转形态，
    # ast.parse 与 black 都对此隐形（black 以首个行尾为准）；混存正是「部分重写」留下的指纹。
    if path.suffix.lower() == ".py" and not _in_skipped_dir(path):
        crlf = raw.count(b"\r\n")
        lone_lf = raw.count(b"\n") - crlf
        if crlf and lone_lf:
            return (
                "P-LINE-ENDING",
                "该 .py 文件同时存在 CRLF 与孤立 LF（AGENTS.md「注释检查工具·三个盲点」第 3 条）："
                " 整文件 write_text 会静默转换行尾，对 ast 比对与 black 全隐形。请用 AGENTS.md 的判据"
                f"（{LINE_ENDING_PROBE}）复核并恢复原本形态：本仓两个读数中原本为 0 的那一项必须仍为 0。",
            )

    # P-RUNTIME-PIN：钉定表所在文件（根级 build_exe.py / scripts/check_runtime_pins.py）被修改后，
    # 收尾必须跑一次 `python scripts/check_runtime_pins.py`——空表 / 缺平台 / 缺槽位对 black /
    # mypy / 注释检查三面全隐形（SEV-10），只有该脚本自己能兜住。定位策略（根内精确锚定、
    # 根外末尾分段、跳过工具产物目录）见 _check_runtime_pins_changed 的注释。
    runtime_pin_feedback = _check_runtime_pins_changed(path, segments)
    if runtime_pin_feedback is not None:
        return runtime_pin_feedback

    # P-MJS-REGISTER：新增 tests/frontend/*.mjs 必须同批登记进 ci.yml 的 node-id 清单，
    # 否则该文件的全部回归锁在正常 CI 中从不执行（M-28 实证）。按**目录结构**（…/tests/frontend/x.mjs）
    # 识别，不依赖检出根路径，也不依赖 ROOT 解析成功。
    if len(segments) >= 3 and segments[-3] == "tests" and segments[-2] == "frontend" and path.suffix.lower() == ".mjs":
        wrapper = f"tests/frontend/{path.stem}.py::"
        if not _CI_WORKFLOW.is_file():
            return (
                "P-MJS-REGISTER",
                f"写入了前端用例 `{path.name}`，但找不到 `.github/workflows/ci.yml`，"
                " 无法验证 node-id 登记；请人工确认该文件已进「Gate frontend tests not skipped」清单。",
            )
        if wrapper not in _CI_WORKFLOW.read_text(encoding="utf-8", errors="replace"):
            return (
                "P-MJS-REGISTER",
                f"`{path.name}` 未登记进 ci.yml「Gate frontend tests not skipped」的 node-id 清单"
                f"（应含 `{wrapper}...`）。`node --test <文件>` 只跑被点名的文件，不登记的后果是"
                " 该 .mjs 的全部回归锁在正常 CI 中从不执行（AGENTS.md「测试」M-28）。"
                " 只加 id，不得动 python_build/node_version 常量。",
            )
    return None


def run_self_test() -> int:
    # 内置样例自检：证明规则真的会拦、且放行面不误伤——不依赖 IDE 是否已加载 Hook。
    block_cases: dict[str, str] = {
        "R-PIP-BULK": "pip install --force-reinstall -r requirements.txt",
        "R-CLEAN-SCOPE": "Remove-Item -Recurse -Force ./downloads/",
        "R-WIPE-SCOPE": "rm -rf .",
    }
    allow_cases: list[str] = [
        # AGENTS.md 给出的两条收尾清理命令形态必须放行
        "Get-ChildItem -Recurse -File -Include *_tmp_*.py,tmp_*.py | Where-Object { $_.FullName -notmatch "
        "'\\\\(.venv|node_modules)\\\\' } | Remove-Item -Force",
        "find . -type f \\( -name '*_tmp_*.py' -o -name 'tmp_*.py' \\) -not -path '*/.venv/*' -delete",
        # 二级处置（单个小包补装）与常规开发命令
        'HTTP_PROXY="" HTTPS_PROXY="" pip install --proxy "" brotli',
        "python scripts/run_gates.py",
        "python -m pytest tests/test_agent_hook_guard.py -q",
    ]
    failed = 0
    for expected_rule, command in block_cases.items():
        got = check_bash_command(command)
        if got is None or got[0] != expected_rule:
            print(f"[SELF-TEST FAIL] 应拦未拦：{expected_rule} <- {command}")
            failed += 1
    for command in allow_cases:
        got = check_bash_command(command)
        if got is not None:
            print(f"[SELF-TEST FAIL] 误伤放行面：{got[0]} <- {command}")
            failed += 1

    # PostToolUse 侧同样要自证「真能回传反馈」（非阻断事件，反馈通道见 main 的 JSON feedback 出口），
    # 否则隐形回归又发回「靠人记」。
    # 临时目录一律走 tempfile.mkdtemp + finally rmtree（AGENTS.md「铁律 1：临时文件零残留」，
    # 不往仓内落盘，也不写导入期共享目录）。
    probe_dir = tempfile.mkdtemp(prefix="dlr_hook_selftest_")
    try:
        mutation_probe = Path(probe_dir) / "probe_mutation.py"
        mutation_probe.write_bytes(b"x = 1  # " + _MUTATION_MARK.encode() + b"\n")
        if _expect_rule(check_written_file(mutation_probe), "P-MUTATION", "MUTATION 残留"):
            failed += 1
        # 行尾混存：CRLF + 孤立 LF 同时出现即视为形态被部分重写翻转。
        mixed_probe = Path(probe_dir) / "probe_line_ending.py"
        mixed_probe.write_bytes(b"a = 1\r\nb = 2\n")
        if _expect_rule(check_written_file(mixed_probe), "P-LINE-ENDING", "行尾形态混存"):
            failed += 1
        # 干净形态（单一 LF）不得报。
        clean_probe = Path(probe_dir) / "probe_clean.py"
        clean_probe.write_bytes(b"a = 1\nb = 2\n")
        if check_written_file(clean_probe) is not None:
            print(f"[SELF-TEST FAIL] 误伤放行面：单一行尾形态 {clean_probe}")
            failed += 1
        mjs_probe = Path(probe_dir) / "tests" / "frontend" / "test_probe_unregistered.mjs"
        mjs_probe.parent.mkdir(parents=True, exist_ok=True)
        mjs_probe.write_text("// probe\n", encoding="utf-8")
        if _expect_rule(check_written_file(mjs_probe), "P-MJS-REGISTER", ".mjs 未登记 ci.yml"):
            failed += 1
        # P-RUNTIME-PIN：修改 build_exe.py 必须触发收尾检查提醒。走 check_written_file 主入口
        # 而非直接喂合成 segments——入口自己算 segments 与锚定标志，私有喂入等于把接线回归
        # （判定函数被摘掉、调用点被删）挡在自检之外（2026-10-17 审查 S6）。
        pin_probe = Path(probe_dir) / "build_exe.py"
        pin_probe.write_text("_PINNED_RUNTIME_SHA256 = {}\n", encoding="utf-8")
        if _expect_rule(
            check_written_file(pin_probe),
            "P-RUNTIME-PIN",
            "build_exe.py 变更触发 check_runtime_pins.py",
        ):
            failed += 1
        # P-RUNTIME-PIN：修改 scripts/check_runtime_pins.py 同样触发
        pin_probe2 = Path(probe_dir) / "scripts" / "check_runtime_pins.py"
        pin_probe2.parent.mkdir(parents=True, exist_ok=True)
        pin_probe2.write_text("# probe\n", encoding="utf-8")
        if _expect_rule(
            check_written_file(pin_probe2),
            "P-RUNTIME-PIN",
            "check_runtime_pins.py 变更触发检查",
        ):
            failed += 1
        # P-RUNTIME-PIN：不相关文件不得误触发
        other_file = Path(probe_dir) / "utils.py"
        other_file.write_text("x = 1\n", encoding="utf-8")
        if check_written_file(other_file) is not None:
            print("[SELF-TEST FAIL] P-RUNTIME-PIN 误触发：utils.py")
            failed += 1
        # P-RUNTIME-PIN 锚定放行面：probe_dir 充当仓库根时，tests/ 下的同名文件不是钉定表本体，
        # 不得触发。self-test 不 patch 模块级 ROOT（_CI_WORKFLOW 等导入期常量已按真 ROOT 算好，
        # patch 会让它们指向不存在的工作流），改为显式传 anchored=True + 按 probe_dir 相对路径
        # 取 segments——segments 是实测值，不是凭空捏造的合成串。
        nested_probe = Path(probe_dir) / "tests" / "build_exe.py"
        nested_probe.parent.mkdir(parents=True, exist_ok=True)
        nested_probe.write_text("x = 1\n", encoding="utf-8")
        nested_segments = [part.lower() for part in nested_probe.relative_to(probe_dir).parts]
        if _check_runtime_pins_changed(nested_probe, nested_segments, anchored=True) is not None:
            print("[SELF-TEST FAIL] P-RUNTIME-PIN 误触发：tests/build_exe.py（锚定态）")
            failed += 1
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)
    print("self-test OK" if failed == 0 else f"self-test FAILED: {failed}")
    return 0 if failed == 0 else 1


def _expect_rule(got: tuple[str, str] | None, expected_rule: str, label: str) -> int:
    # 自检子判据：命中预期规则返回 0，否则打一条 FAIL 并返回 1（供调用方累加）。
    if got is None:
        print(f"[SELF-TEST FAIL] 应拦未拦：{expected_rule} <- {label}")
        return 1
    if got[0] != expected_rule:
        print(f"[SELF-TEST FAIL] 命中错误规则：期望 {expected_rule}、实际 {got[0]}（{label}）")
        return 1
    return 0


def main() -> int:
    ensure_utf8_streams()
    if "--self-test" in sys.argv[1:]:
        return run_self_test()
    try:
        event = read_event()
    except (OSError, ValueError) as exc:
        print(f"[agent-hook] 事件 JSON 解析失败，已放行：{exc}", file=sys.stderr)
        return 0

    event = event or {}
    name = event_name(event)
    payload = tool_input(event)

    try:
        if name == "PreToolUse":
            command = payload.get("command")
            if isinstance(command, str) and command:
                verdict = check_bash_command(command)
                if verdict is not None:
                    rule, reason = verdict
                    print(f"[{rule}] {reason}", file=sys.stderr)
                    return 2
        elif name == "PostToolUse":
            # 非阻断事件：exit 2 的 stderr 注入按官方文档仅对 blockable 事件生效，这里不得依赖它。
            # 文档化通道是 exit 0 + stdout JSON `hookSpecificOutput.feedback`——即时回传「当场修」，
            # 撤销写入由收尾门禁（R8 / run_gates.py / CI）在入库前兜底。
            # file_path 的字段名在不同写入工具间不统一（file_path / path / notebook_path），逐一取。
            for key in ("file_path", "filePath", "path", "notebook_path"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    verdict = check_written_file(resolve_path(value))
                    if verdict is not None:
                        rule, reason = verdict
                        print(
                            json.dumps(
                                {
                                    "hookSpecificOutput": {
                                        "hookEventName": "PostToolUse",
                                        "feedback": f"[{rule}] {reason}",
                                    }
                                },
                                ensure_ascii=False,
                            )
                        )
                    return 0
    except OSError as exc:
        # 读盘失败（文件已被后续操作删掉等）不判失败：Hook 只在能拿到证据时才发言。
        print(f"[agent-hook] 检查未完成，已放行：{exc}", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
