# 一次性本地门禁入口（CI 之外唯一需要记住的门禁调用点）。
#
# 职责：把 AGENTS.md「格式化命令（门禁唯一基准）」章节列出的全部 --check 型门禁命令
#       按原顺序在本机一次性跑完，任一失败以非 0 退出——把「CI 变红才知道红」提前到本地。
#
# 核心机制：命令清单**不在本脚本内复制**，而是运行时从 AGENTS.md 对应章节的 bash 代码块逐字
#           解析。该章节是门禁命令的唯一事实源；另写一份清单就制造并行事实源，章节更新后门禁
#           会静默漂移。解析以 ` ```bash ` 围栏为硬边界：围栏外的行（如「isort 收尾清理」小节的
#           PowerShell `Get-ChildItem ... | Remove-Item`）即使含管道也绝不参与。
#
# 控制约定（对齐 AGENTS.md「格式化命令」章节）：
#   - `black .` / `isort .`（不带 --check）是写操作，永不进入本回路：解析时兜底拦截，即便章节
#     代码块被误加入写型命令，本地门禁也不会改动手里的未提交文件。
#   - `mypy` 不带路径参数，检查范围取 pyproject [tool.mypy].files（收窄仅用于排障）；
#     `mypy --platform linux` 属条件增跑，此处照单执行，不做智能判断。
#   - 门禁块行首的 `NAME=value ` 前缀按 bash 语义解析为**子进程环境变量**后从命令行剥掉
#     （cmd.exe 不认这种前缀，直送会被当成参数）。PYTHONUTF8=1 另有一份硬默认，见 GATE_CHILD_ENV。
#   - 子进程 stderr 命中 FATAL_STDERR_PATTERNS 即判失败，即使 rc=0——isort 的「Unable to parse
#     file」走 UserWarning 通道、rc 恒 0，只认退出码就是门禁假绿。
#   - **本进程自己的** stdout/stderr 也必须是 UTF-8：两路输出最终都落在本进程 stdout 上，中文
#     Windows（cp936）下 black 成功行的 `✨` 会让那次写入抛 UnicodeEncodeError 而炸掉门禁进程。
#   - 执行形态：能按参数列表表达的命令走 shell=False（见 build_gate_argv），只有含 shell 结构符、
#     或行首要执行 .bat/.cmd 时才退回 shell=True 字符串形态；清单事实源与判定口径均不变。
#
# 用法：
#   python scripts/run_gates.py                          # 全量门禁（在仓库根目录执行）
#   python scripts/run_gates.py --list                   # 只列出解析到的命令，不执行
#   python scripts/run_gates.py --only mypy --only black # 收窄排障：子串匹配，参数形式不变
#   python scripts/run_gates.py --keep-going             # 失败后续跑剩余门禁，最后汇总
#
# 退出码：0 全部通过；1 至少一条门禁失败（门禁变红）；2 清单来源缺失/为空/含写型命令
#         （属「没跑」而非「跑过」，与真失败区分）；3 门禁可执行文件缺失（环境问题，便于排障）。
#  两档归属（都是「门禁自己没跑成」，不得伪造成 0 或 1）：
#   - 某条门禁子进程超过 GATE_CHILD_TIMEOUT_SECONDS 未结束 → 被终止并按 2 汇总（失败明细仍打印）；
#   - check_executables 的 import 探测超时 → 按「工具不可用」处理，走既有的 3。

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# 项目根目录（scripts/ 的上一级），同时作为门禁命令的 cwd
ROOT = Path(__file__).resolve().parent.parent

# 门禁清单唯一事实源：AGENTS.md 的章节标题前缀 + 代码块围栏语言标记。
# 用前缀匹配是因为标题带括号后缀（现形如「## 格式化命令（门禁唯一基准）」），且后缀措辞可能再变；
# 整串相等会让门禁因标题改字而静默解析到空清单。
SECTION_PREFIX = "## 格式化命令"
FENCE_LANG = "```bash"

# 写型格式化命令兜底拦截（AGENTS.md 约定：black/isort 不带检查开关会改写文件，
# 不得进入门禁回路）。按「模块词 + 缺检查开关」判定，而不是匹配整条命令字面量，
# 避免将来给命令加公共参数（如 --extend-exclude）时判定失效。
# 开关集合必须按各工具实际 CLI 写全：isort 的检查开关是 `--check-only`，没有 `--check`
# （首版只写 --check 导致门禁自带的 isort 行被自己拦下，rc=2）。black 只认 `--check`：
# --check-ast / --check-lines 不参与「是否写盘」判定，列入会抬高拦截阈值造成漏拦。
WRITE_GUARD: dict[str, tuple[str, ...]] = {
    "black": ("--check",),
    "isort": ("--check-only",),
}

# 子进程环境的硬默认。
# isort 用**平台默认编码**读源文件：GBK locale 下含中文注释的文件会抛
# UnicodeEncodeError → 只发一条 UserWarning「Unable to parse file」就跳过、rc 仍为 0，
# 于是门禁在本地全绿却根本没查这些文件（被跳过的个数随仓库内容漂移，核对命令见 AGENTS.md）。
# PYTHONUTF8=1 强制 UTF-8 读写，等价于 `-X utf8`，跨平台一致。
# 与门禁块行首前缀的关系：前缀是**事实源里的声明**（ci.yml 逐字镜像），
# 这里是**兜底**——即便有人在文档里删掉前缀，本地门禁也不会退回假绿形态。
GATE_CHILD_ENV: dict[str, str] = {"PYTHONUTF8": "1"}

# 「告警即失败」清单：这些子串出现在门禁子进程的 stderr 里，即代表该工具**跳过了文件**
# 而非「检查通过」。新增同类形态直接加一行，不要改成「忽略告警」。
# pytest 的 warnings summary 走 stdout，主回路的逐行 stderr 转发覆盖不到它，故由 ci.yml 的
# "Gate pytest warnings summary" 步骤与下方 gate_pytest_warnings_summary() 单独承担；
# 该兜底回路自己也接管 pytest 的 stderr 并按本清单判定（rc=0 命中即失败）。
FATAL_STDERR_PATTERNS: tuple[str, ...] = (
    "Unable to parse file",  # isort/black：编码或解析失败的静默跳过（UserWarning，rc=0）
)

# bash 风格的行首环境变量前缀：`NAME=value` 后必须跟空白，且值不含空格（门禁命令均为如此）
_ENV_PREFIX_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(\S*)\s+")

# —— 有界执行 ——————————————————————————————————————————
# 三条子进程回路都必须带 timeout：门禁工具挂住（mypy 卡在某个文件、black 撞上缓存锁、
# 探测子进程起不来）时 run_gates 会一路阻塞到 CI job 超时，那份红里**没有任何一条门禁的结论**。
# 超时统一按本文件头已有的 rc=2 档收口（「没跑」而非「跑过」）：
# 既不得退 0（假绿），也不得退 1（那会把「工具挂住」报成「代码不合格」，指错排障方向）。
GATE_CHILD_TIMEOUT_SECONDS = 900.0  # 单条门禁：全仓 mypy/black 的慢机器量级 × 余量，仍远小于 job 超时
GATE_KILL_GRACE_SECONDS = 30.0  # 超时后 kill 的收尾宽限；仍不退出就放弃等待并按「没跑成」出结论
GATE_READER_JOIN_SECONDS = 30.0  # stderr 读线程的收束宽限；它也必须**有界**，否则读端成了新的无界阻塞点
PROBE_TIMEOUT_SECONDS = 60.0  # check_executables 的 `python -c importlib.util.find_spec` 探测
# 超时的哨兵退出码：与 GNU timeout(1) 的 124 同值，便于人眼与 CI 日志对齐。
# 已知边界：某条门禁工具自己以 124 退出时会被归到「没跑成」这一档（退 2 而不是 1）——
# 宁可把「工具内部超时」保守地当成「门禁没给出结论」，也不反过来把挂住判成通过。
GATE_TIMEOUT_RC = 124

# 只有「这条命令确实要靠 shell 解释」时才退回 shell=True 的字符串形态。
# 判据取 shell 结构符而不是「整条命令是否简单」：出现任一结构符就无法按参数列表等价表达，
# 硬拆成 argv 会把管道/重定向当字面参数传给工具（比原来的失败更难看懂）。
# `$( `/`${ ` 是命令替换与变量展开，反引号同；`&` 同时覆盖后台与 &&。
_SHELL_STRUCTURES: tuple[str, ...] = ("|", "&", ">", "<", "`", "$(", "${")

# Windows 上 CreateProcess 不能直接执行批处理（只认 .exe，PATH 搜索也只补 .exe），
# 必须由 cmd.exe 解释；行首解析到这两种扩展名时保持 shell 形态，绝不改成 argv 后
# 把「找不到可执行文件」伪装成门禁失败（同 rc=3「工具没装」与 rc=1「代码不合格」必须分档的口径）。
_BATCH_SUFFIXES: tuple[str, ...] = (".bat", ".cmd")


def ensure_utf8_streams() -> None:
    # 把**本进程**的 stdout/stderr 也换成 UTF-8：是那套语义的另一半，只钉子进程仍会失效。
    # GATE_CHILD_ENV 只管得到子进程，而两路输出最终都落在**本进程 stdout** 上——run_command
    # 逐行读子进程 stderr 再写 sys.stdout，black 成功行的 `All done! ✨ 🍰 ✨` 则走子进程 stdout
    # 的直接继承写入。中文 Windows 的 cp936 编不出 U+2728 → UnicodeEncodeError 炸掉门禁自身，
    # 表象是「rc=1 且只剩一段 Traceback」，而触发它的那条门禁其实是**通过**的。
    #
    # errors="replace"：将来某条门禁输出更冷门的码点，也只能丢一个字符的显示，绝不允许再演变成
    # 「门禁进程崩溃 → 整回路没有结论」。与 build_exe._ensure_utf8_streams 同一手法。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except ValueError, OSError:
            # 已被重定向到已关闭/非法句柄时静默放过：本函数只改善输出，不参与判定。
            pass


def split_env_prefix(line: str) -> tuple[dict[str, str], str]:
    # 剥掉行首的 `NAME=value ` 前缀（可连续多个），返回 (环境变量, 裸命令)。
    # 必须由 extract 侧剥掉而不是丢给 shell：本地门禁的默认 shell 可能是 cmd.exe，
    # 它会把 `PYTHONUTF8=1` 当作命令的第一个参数而不是环境变量赋值。
    env: dict[str, str] = {}
    rest = line
    while True:
        m = _ENV_PREFIX_PATTERN.match(rest)
        if not m:
            return env, rest.strip()
        env[m.group(1)] = m.group(2)
        rest = rest[m.end() :]


def extract_gate_env(agents_path: Path) -> dict[str, str]:
    # 收集门禁块里声明的全部行首环境变量（多次声明以最后一次为准）。
    # 与 extract_gate_commands 读同一份围栏，故不会引入第二份事实源。
    if not agents_path.exists():
        return {}
    lines = agents_path.read_text(encoding="utf-8").splitlines()
    span = _section_span(lines)
    if span is None:
        return {}
    env: dict[str, str] = {}
    for line in _first_fenced_block(lines[span[0] : span[1]]):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        prefix_env, _ = split_env_prefix(_strip_trailing_comment(stripped))
        env.update(prefix_env)
    return env


def _diagnose_empty_source(agents_path: Path) -> str:
    # 当 extract_gate_commands 返回空清单时，给出**具体的章节漂移诊断**。
    # 把「rc=2 但只给一句笼统提示」细化到「哪个解析步骤断了」：文件不存在、章节标题漂移、
    # 缺 bash 围栏、围栏内容为空——四种失败模式各有不同修法，诊断必须指向具体动作。
    if not agents_path.exists():
        return f"文件不存在: {agents_path}"
    lines = agents_path.read_text(encoding="utf-8").splitlines()
    span = _section_span(lines)
    if span is None:
        # 尝试发现近似标题（如「## 格式化命令」被改成「## 格式化命令表」以外的名字）
        similar = [ln.strip() for ln in lines if ln.strip().startswith("## ") and "格式化" in ln]
        hint = ""
        if similar:
            hint = f"（发现近似标题: {similar}）"
        return f"未找到以 {SECTION_PREFIX!r} 开头的章节{hint}。" f"请检查 AGENTS.md 是否存在以 ## 格式化命令 开头的章节"
    block = _first_fenced_block(lines[span[0] : span[1]])
    if not block:
        return f"章节 {SECTION_PREFIX!r} 内未找到 ```bash 代码块"
    non_empty = [ln for ln in block if ln.strip() and not ln.strip().startswith("#")]
    if not non_empty:
        return f"章节 {SECTION_PREFIX!r} 的 ```bash 代码块内没有有效命令行"
    return "原因未知：解析函数返回空但章节/围栏/命令行均存在"


def extract_gate_commands(agents_path: Path) -> list[str]:
    # 从 AGENTS.md「格式化命令」章节的第一个 bash 代码块逐行提取门禁命令。
    # 返回按原顺序排列的命令字符串列表；章节缺失时返回空列表，交调用方判定 rc=2。
    if not agents_path.exists():
        return []
    lines = agents_path.read_text(encoding="utf-8").splitlines()

    span = _section_span(lines)
    if span is None:
        return []
    block = _first_fenced_block(lines[span[0] : span[1]])
    out: list[str] = []
    for line in block:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # 行尾注释必须先剥掉再执行：本地门禁的默认 shell 是 cmd.exe，不像 bash
        # 那样原生识别 `#`，`mypy   # 不带路径参数…` 直送会把注释当参数报 unrecognized
        _, command = split_env_prefix(_strip_trailing_comment(stripped))
        if command:
            out.append(command)
    return out


def _strip_trailing_comment(line: str) -> str:
    # 剥行尾注释：只认「空白 + #」为注释起点（避免切碎 URL/含 # 的参数字面量）。
    # 门禁命令均为简单命令行，不处理引号内的 #（shell=True 下双引号内的 # 本就不参与展开）。
    cut = len(line)
    for i in range(1, len(line)):
        if line[i] == "#" and line[i - 1] in " \t":
            cut = i
            break
    return line[:cut].strip()


def _section_span(lines: list[str]) -> tuple[int, int] | None:
    # 定位「格式化命令」章节正文区间 [start, end)。
    # 章节到下一个**同级**二级标题前结束：startswith("## ") 对 "### " 为 False（第三字符
    # 不是空格），故「basedpyright」/「isort 收尾清理」两个子小节会留在章节体内；但它们的
    # 命令分在 ```powershell / ```bash 围栏里——「isort 收尾」那个也是 bash 围栏且含 rm 型
    # 清理命令，靠「只取第一个 bash 块」拦截，不得改成「扫描全章节所有 bash 块」。
    for i, line in enumerate(lines):
        if line.startswith(SECTION_PREFIX):
            start = i + 1
            for j in range(start, len(lines)):
                if lines[j].startswith("## ") and not lines[j].startswith("### "):
                    return (start, j)
            return (start, len(lines))
    return None


def _first_fenced_block(section: list[str]) -> list[str]:
    # 取章节内第一个 ```bash 围栏块的内容行（不含围栏本身）。
    # 围栏结束标记写 "```"（不加语言名）：结束行以 ``` 开头，开始行等于 ```bash，
    # 靠「先匹配开始再匹配结束」的顺序自然区分。
    collecting = False
    out: list[str] = []
    for line in section:
        stripped = line.strip()
        if not collecting:
            if stripped.startswith(FENCE_LANG):
                collecting = True
            continue
        if stripped.startswith("```"):
            break
        out.append(line)
    return out


def is_write_command(cmd: str) -> bool:
    # 判定 black / isort 是否处于写模式（未显式传 --check / --check-only）。
    # 模块名只从两种位置识别：`python -m <module>` 的 <module>，或脚本名（argv[0] 的 basename）。
    # 不能扫描全部 token 判同名：isort 的门禁写法 `--profile black` 里的参数值 black
    # 会被误判成「裸 black 调用」（首版实测即此坑），故只认结构位置，不认任意 token。
    try:
        argv = shlex.split(cmd.replace("\\", "/"))
    except ValueError:
        return False
    targets = set(WRITE_GUARD)
    module_pos: int | None = None
    if argv:
        script = Path(argv[0]).name
        if script in ("python", "python3", "py") and len(argv) >= 2 and argv[1] == "-m":
            module_pos = 2
        elif script in targets:
            module_pos = 0
    if module_pos is None or module_pos >= len(argv) or argv[module_pos] not in targets:
        return False
    check_flags = WRITE_GUARD[argv[module_pos]]
    rest = argv[module_pos + 1 :]
    # 精确匹配：`--check` 或 `--check=...`（工具未来改带值开关时不至于漏判）
    return not any(any(tok == f or tok.startswith(f + "=") for f in check_flags) for tok in rest)


def run_command(cmd: str, extra_env: dict[str, str] | None = None) -> tuple[int, float, list[str]]:
    # 执行单条门禁命令，返回 (退出码, 耗时秒, stderr 命中的致命告警子串列表)。
    # 输出通道的**实际**分工：
    #   stdout —— **不接管**（未传 stdout=，子进程直接继承本进程 stdout 句柄），故既不读也不扫。
    #             工具进度/结果行因此原样到达终端，代价是**本函数看不见 stdout**：只走 stdout 的
    #             失效信号全在盲区。pytest warnings summary 正是这种形态，故由
    #             gate_pytest_warnings_summary() 显式 PIPE 单独接管（可复核判据：
    #             grep -n "stdout=" scripts/run_gates.py → run_command 内无、该函数内有）。
    #   stderr —— 逐行**边转发边扫描**（stdout=sys.stdout）：既不能吞掉（人要看），也不能只看 rc
    #             ——isort 跳过文件时 rc=0（实测告警确实落在 stderr）。
    # 退出码：rc != 0 一律判失败（由 main() 的 `if rc == 0 and not hits:` 收口），--keep-going
    #         只控制「是否继续跑后续命令」，不影响该判定。
    #         **保留值** GATE_TIMEOUT_RC(124)：它不表示「工具查出了
    #         问题」，只表示「这条门禁到点没结束、没给出任何结论」，由 main() 单独记账并让整回路
    #         以 rc=2 收口（本文件头：2＝没跑而非跑过）。同时 stderr 的逐行转发挪进工作线程——
    #         纯阻塞式迭代在主线程里等同于「读端无界」，加在 wait 上的 timeout 也救不回来。
    # 解释器换绑：清单里的 `python` 统一换到当前解释器（见 _rebind_interpreter）——Windows 上
    # python / py 启动器与 venv 可能混用，不换绑就会让门禁跑在与 pytest 不同的解释器上，
    # 即「本地绿、CI 红」的成因。shell=True 只在 build_gate_argv 判「必须靠 shell 解释」时使用：
    # 字符串形态经 cmd.exe /c 时，解释器路径含空格的 venv 能否跑起来取决于 cmd 的引号剥层实现
    # （换台机器才知道红不红），参数列表把引号这一层整个消掉。
    t0 = time.monotonic()
    # stdin=DEVNULL：门禁子进程不得继承调用方的 stdin。管道/IDE harness 下父进程的 stdin
    # 可能已关闭，子进程（含 site 初始化）碰它即抛 OSError WinError 6（本地实测：pytest 经
    # 管道调用时偶发）；门禁命令均不需要交互输入，接空设备是唯一安全选择。
    child_env = dict(os.environ)
    child_env.update(GATE_CHILD_ENV)
    if extra_env:
        child_env.update(extra_env)
    argv = build_gate_argv(cmd)
    proc = subprocess.Popen(
        argv if argv is not None else _rebind_interpreter(cmd),
        shell=argv is None,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env,
    )
    hits: list[str] = []

    def _drain_stderr() -> None:
        # 逐行转发并扫描（语义与旧实现逐字一致），只是挪进线程：挪动的唯一理由是
        # 「读端阻塞时主线程要能按时给出超时结论」，判定口径一分不改。
        if proc.stderr is None:
            return
        for raw in proc.stderr:
            sys.stdout.write(raw)
            sys.stdout.flush()
            for pattern in FATAL_STDERR_PATTERNS:
                if pattern in raw and pattern not in hits:
                    hits.append(pattern)

    if proc.stderr is None:
        # 未接管 stderr 的形态（用例替身/异常环境）：没有读端可阻塞，直接按超时预算等退出
        reader: threading.Thread | None = None
    else:
        reader = threading.Thread(target=_drain_stderr, name="run-gates-stderr-drain", daemon=True)
        reader.start()

    timed_out = False
    try:
        # 读端已经挪到线程里，主线程只需给**进程本身**设界：挂住不退出 → 到点 TimeoutExpired；
        # 无限刷 stderr → 管道写满后子进程自己阻塞在 write 上、同样不会退出 → 还是到点超时。
        # 两条无界路径因此收敛成同一个有界判据，且预算从 run_command 的入口(t0)起算。
        proc.wait(timeout=max(0.0, t0 + GATE_CHILD_TIMEOUT_SECONDS - time.monotonic()))
    except subprocess.TimeoutExpired:
        timed_out = True
    if not timed_out and reader is not None:
        # 进程已结束 → 管道必然关闭，读线程只剩把缓冲里的尾巴读完，所以这里给短宽限就够。
        # 宽限期仍未退出＝stderr 的告警扫描面不完整（「跳过文件即门禁失效」同族），
        # 保守按「没跑成」处理，不得拿着半截扫描结果宣布 PASS。
        reader.join(timeout=GATE_READER_JOIN_SECONDS)
        if reader.is_alive():
            print("    -> [WARN] stderr 读线程未在宽限期内退出，本次告警扫描面不完整", flush=True)
            timed_out = True
    if timed_out:
        # 「门禁没跑成」的收口：先 kill 再等一小段，等不到也放行——继续等就还是无界阻塞。
        proc.kill()
        try:
            proc.wait(timeout=GATE_KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        return GATE_TIMEOUT_RC, time.monotonic() - t0, hits
    rc = proc.returncode if proc.returncode is not None else 1
    return rc, time.monotonic() - t0, hits


def _rebind_interpreter(cmd: str) -> str:
    # 只替换行首的 `python `/`python3 `（含引号包裹的绝对路径形式），不动参数里的 python 字样
    for name in ("python3", "python"):
        if cmd.startswith(name + " "):
            return f'"{sys.executable}" {cmd[len(name) + 1 :]}'
    # 裸 console-script（如 `mypy`）不在 PATH 时退化为 `python -m mypy`：
    # AGENTS.md 逐字规定的是 `mypy`（不带路径），Windows venv 未激活时 where 找不到
    # 可执行文件属环境差异而非代码不合格，换用 -m 形式保持检查范围与参数完全不变。
    head = cmd.split(" ", 1)[0]
    if head and "\\" not in head and "/" not in head and shutil.which(head) is None:
        return f'"{sys.executable}" -m {cmd}'
    return cmd


def build_gate_argv(cmd: str) -> list[str] | None:
    # 能按参数列表执行的命令拆成 argv 交 shell=False，拆不了的回 None 由调用方退回原 shell
    # 形态。为何优先 argv：shell=True 时 Python 实际执行 [cmd.exe, "/c", 整串]，再经 list2cmdline
    # 给整串加外层引号并把内层引号转义；而 cmd.exe 对 /c 后面那段有「首尾引号成对就再剥一层」的
    # 既有规则——解释器路径含空格的 venv 能否跑取决于引号层数与 cmd 实现细节（失败信息只是一句
    # 「命令语法不正确」）。argv 形态不产生引号层，空格由进程 API 按数组边界处理，Windows 与
    # POSIX 走同一条代码，不再出现「本地一套引号语义、CI 另一套」的分叉。
    try:
        # posix=False：默认模式会把反斜杠当转义符吃掉，Windows 绝对路径 `C:\venv\Scripts\python.exe`
        # 会被切成 `C:venvScriptspython.exe`（argv[0] 根本不存在，整条门禁退化成「工具没跑」）。
        # 代价是 token 保留外层引号，故随后逐 token 手工剥一层。
        raw_tokens = shlex.split(cmd, posix=False)
    except ValueError:
        return None
    argv: list[str] = []
    for token in raw_tokens:
        if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
            token = token[1:-1]
        argv.append(token)
    if not argv:
        return None
    if any(any(struct in token for struct in _SHELL_STRUCTURES) for token in argv):
        # 含 shell 结构：参数列表无法等价表达，保持原形态（绝不静默把 `|` 当字面参数传下去）
        return None
    head, rest = argv[0], argv[1:]
    if head in ("python", "python3", "py"):
        # 与 _rebind_interpreter 同一语义：行首解释器一律换成**当前解释器**，参数原样保留
        return [sys.executable, *rest]
    resolved = shutil.which(head)
    if resolved is None:
        if "/" in head or "\\" in head:
            # 带路径分隔符却找不到 → 交回 shell 形态让它报「命令不存在」（rc=127/1），
            # 不在这里换成 FileNotFoundError 崩栈（同 AGENTS.md ：按名字起子进程必须能降级）
            return None
        # 裸 console-script 不在 PATH 时退化为 `-m <name>`（与 _rebind_interpreter 同一退化口径）
        return [sys.executable, "-m", head, *rest]
    if resolved.lower().endswith(_BATCH_SUFFIXES):
        # CreateProcess 不执行批处理（PATH 搜索也只补 .exe），这一支必须留 shell 形态
        return None
    return [resolved, *rest]


def check_executables(cmds: list[str]) -> list[str]:
    # 预检命令解释器是否存在（python/mypy 等），返回缺失的可执行文件名。
    # 门禁失败与「工具没装」必须区分：后者不该被报告成「代码不合格」。
    # 裸 console-script 不在 PATH 时还要看能否 `python -m <name>`（当前解释器装了该包
    # 但未生成/未暴露 scripts 目录的情形，如 venv 未激活的 Windows），与 _rebind_interpreter
    # 的退化路径保持一致，否则会误报 rc=3。
    missing: list[str] = []
    for cmd in cmds:
        try:
            argv = shlex.split(cmd.replace("\\", "/"))
        except ValueError:
            continue
        head = Path(argv[0]).name if argv else ""
        if head in ("python", "python3", "py"):
            # 行首解释器由 _rebind_interpreter 换绑到 sys.executable，必然可用
            continue
        if head and shutil.which(head) is None and _module_unavailable(head):
            missing.append(head)
    return sorted(set(missing))


def _module_unavailable(name: str) -> bool:
    # 当前解释器能否以 -m 方式加载该模块（不能→才算真缺失）；同 run_command，不继承 stdin
    # 两条配套改动，缺一即本函数不可用：
    #   ① capture_output —— 旧形态不接管两路输出，探测子进程的一句 traceback / 告警会直接混进
    #      门禁自己的 stdout，把「工具在不在」这一句结论写在一段陌生输出中间（判定面被污染）。
    #      这里不需要转发（结果只是 rc），所以两路都收进缓冲区、不打印。
    #   ② timeout —— 探测本身也可能挂（解释器启动被杀软拦、site 初始化卡网络盘）。返回 True
    #      即「不可用」，走 main() 的 rc=3「工具没装（环境问题）」档：既不把挂住读成「装好了」，
    #      也不退成 rc=1 让人以为代码不合格。
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import importlib.util, sys as s; s.exit(0 if importlib.util.find_spec({name!r}) else 1)",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(
            f"WARN: 探测 {name!r} 是否可 import 的子进程超过 {PROBE_TIMEOUT_SECONDS:.0f}s 未结束，按不可用处理",
            file=sys.stderr,
        )
        return True
    return proc.returncode != 0


# pytest 退出码 → 语义：兜底门禁必须把 rc 说明白，否则「rc=4 用法错」与「rc=5 一条用例都没
# 跑到」会被读成「跑过且无告警 = 通过」。口径以 _pytest.exitcodes 为准（2 中断、4 用法错、
# 5 未收集到用例），避免后来者照抄错的映射。
PYTEST_RC_SEMANTICS: dict[int, str] = {
    0: "全部用例通过",
    1: "存在失败用例",
    2: "执行被中断（KeyboardInterrupt / --exitfirst / 会话超时）",
    3: "pytest 内部错误（常见于收集期 ImportError）",
    4: "用法错误（命令行参数有误，根本没开始执行）",
    5: "未收集到任何用例（testpaths 错位 / 用例文件全部收集失败）",
}

# 「跑到过用例」的最低见证：pytest 结尾汇总行的 `N passed`。
# 只有 rc=0 不足以证明回路有效——收集到 0 条用例时 pytest 也会返回 0（旧形态），
# 且 `-q --co` 之类的误用会让 stdout 里根本没有汇总行。
# 锚定行首（可带 `-rA`/非 -q 模式的 `=+ ` 前缀），避免把日志正文里出现的
# 「1 passed」字样当成「真跑到了用例」的凭据。
_PYTEST_PASSED_PATTERN = re.compile(r"(?m)^(?:=+ )?(\d+) passed\b")


def _pytest_passed_count(out: str) -> int:
    # 从 pytest 输出里取「通过用例数」；取末次汇总行（-q 只在结尾打一次，
    # 但 --reruns / -p xdist 等场景会先打中间行，故以最后一次读数为准）。
    # 匹配不到即返回 0，由调用方判「门禁没跑到用例」。
    counts = _PYTEST_PASSED_PATTERN.findall(out)
    return int(counts[-1]) if counts else 0


def gate_pytest_warnings_summary() -> tuple[bool, str]:
    # pytest 的 warnings summary 兜底（与 ci.yml "Gate pytest warnings summary" 同一形态）。
    # 它不进「格式化命令」清单、也不并入主回路的逐行 stderr 扫描——warnings summary 走 stdout，
    # 而把 pytest 写进那一章会让「格式化命令唯一基准」变成隐式测试清单（另见 main() 末尾）。
    # 返回 (通过, 诊断信息)：通过=True 表示「pytest 正常跑完且 warnings summary 为空」。
    #
    # 三条 fail-closed 判据，缺一即门禁自我证明失效：
    #   ① 取真实退出码。丢弃 rc 时，pytest 以 rc=2/3/4/5 崩溃（收集期 ImportError、参数写错、
    #      一条用例都没跑到）只要 stdout 里没有 `= warnings summary =` 就照样 PASS。
    #   ② 接管 stderr 并扫同一份 FATAL_STDERR_PATTERNS：插件加载失败与编码错误只走 stderr，
    #      stderr=DEVNULL 会直接吞掉。用 subprocess.run 一次性读两路（= communicate()），
    #      以免「stdout 读满前 stderr 塞满」的管道死锁——这也是不能退回 Popen+read() 的原因。
    #   ③ 见证「真的跑到了用例」：输出里必须有 `N passed` 且 N > 0。
    # 三条一律**不得**退回「没查到就当通过」：与 / 该同口径，「没查到」一律非 0
    # 退出并给出下一步命令。
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
            # 主回路的 Popen 与 _module_unavailable 的 run 都已有上界，
            # 唯独本条没有。pytest 卡在一条永不返回的用例上时会把整个 run_gates 拖到 job 超时，
            # 而那份红里没有任何一条门禁的结论。超时按「门禁没跑成」返回 False（调用方以 rc=1
            # 收口），绝不伪装成 PASS。
            timeout=GATE_CHILD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        dur = time.monotonic() - t0
        raw_partial = exc.stdout
        if raw_partial is None:
            partial_out = ""
        elif isinstance(raw_partial, bytes):
            partial_out = raw_partial.decode("utf-8", errors="replace")
        else:
            partial_out = str(raw_partial)
        return False, (
            f"pytest 超过 {GATE_CHILD_TIMEOUT_SECONDS:.0f}s 未结束，已终止（{dur:.1f}s）："
            f"warnings summary 无从判定。末段输出: "
            f"{' | '.join(line.strip() for line in partial_out.strip().splitlines()[-5:] if line.strip())}"
        )
    dur = time.monotonic() - t0
    out = str(proc.stdout or "")
    err = str(proc.stderr or "")
    rc = int(proc.returncode)

    hits = [pattern for pattern in FATAL_STDERR_PATTERNS if pattern in err]
    if rc != 0:
        semantics = PYTEST_RC_SEMANTICS.get(rc, f"未登记的退出码 {rc}")
        detail = ""
        if hits:
            detail += f"；stderr 命中致命告警 {hits}"
        tail = " | ".join(line.strip() for line in err.strip().splitlines()[-5:] if line.strip())
        if tail:
            detail += f"；stderr 末尾: {tail}"
        return False, f"pytest 以 rc={rc}（{semantics}）退出，warnings summary 无从判定{detail}（{dur:.1f}s）"
    if hits:
        return False, f"pytest rc=0 但 stderr 命中致命告警 {hits}（跳过/降级即门禁失效，{dur:.1f}s）"
    passed = _pytest_passed_count(out)
    if passed <= 0:
        tail = " | ".join(line.strip() for line in out.strip().splitlines()[-5:] if line.strip())
        return False, (
            f"pytest rc=0 但输出里没有「N passed」汇总行（通过用例数=0）："
            f"门禁根本没跑到用例，不得判通过（{dur:.1f}s）。末段输出: {tail}"
        )
    if "= warnings summary =" in out:
        return False, f"pytest warnings summary 非空（{passed} passed，{dur:.1f}s）"
    return True, f"pytest {passed} passed 且 warnings summary 为空 ({dur:.1f}s)"


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_streams()
    parser = argparse.ArgumentParser(
        prog="run_gates",
        description="一次性运行 AGENTS.md「格式化命令」章节声明的全部本地门禁（只跑 --check 形式）",
    )
    parser.add_argument("--list", action="store_true", help="只打印解析到的门禁命令，不执行")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="PATTERN",
        help="只跑命令中含该子串的门禁（可重复），用于收窄排障；参数形式不变",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="任一失败也继续跑完剩余门禁，最后汇总（默认首个失败即停）",
    )
    args = parser.parse_args(argv)

    cmds = extract_gate_commands(ROOT / "AGENTS.md")
    if not cmds:
        diag = _diagnose_empty_source(ROOT / "AGENTS.md")
        print("ERROR: 无法从 AGENTS.md「格式化命令」章节解析出门禁命令清单", file=sys.stderr)
        print(f"       诊断: {diag}", file=sys.stderr)
        print("       本地门禁是「没有跑」而不是「跑过了」，请勿宣布完成。", file=sys.stderr)
        return 2

    if args.only:
        cmds = [c for c in cmds if any(p in c for p in args.only)]
        if not cmds:
            print(f"ERROR: --only {args.only} 未匹配到任何门禁命令", file=sys.stderr)
            return 2

    # 兜底拦截：写型格式化命令绝不允许进入回路，宁可拒绝执行也不改动工作区
    unsafe = [c for c in cmds if is_write_command(c)]
    if unsafe:
        print("ERROR: 门禁清单中出现写型格式化命令（black/isort 未带 --check）:", file=sys.stderr)
        for c in unsafe:
            print(f"  {c}", file=sys.stderr)
        return 2

    if args.list:
        for c in cmds:
            print(c)
        return 0

    missing = check_executables(cmds)
    if missing:
        print(f"ERROR: 以下门禁工具不可用: {', '.join(missing)}", file=sys.stderr)
        print("       先修环境（见 AGENTS.md「依赖缺失排查顺序」），这不是代码通过。", file=sys.stderr)
        return 3

    failed: list[str] = []
    stalled: list[str] = []  # 到点没结束、因此**没有结论**的门禁
    total_t0 = time.monotonic()
    gate_env = extract_gate_env(ROOT / "AGENTS.md")
    if gate_env:
        print(f"门禁子进程环境变量（来自 AGENTS.md 门禁块行首前缀）：{gate_env}")
    for i, cmd in enumerate(cmds, 1):
        print(f"\n[{i}/{len(cmds)}] $ {cmd}", flush=True)
        rc, dur, hits = run_command(cmd, gate_env)
        if rc == GATE_TIMEOUT_RC:
            # 单列一档：这条门禁子进程被到点终止，既没检查任何文件、也没打印任何判定。
            # 并进 failed 退 1 就是拿「工具挂住」冒充「代码不合格」；退 0 更是假绿。
            print(f"    -> [NO-VERDICT] 超过 {GATE_CHILD_TIMEOUT_SECONDS:.0f}s 未结束，已终止（{dur:.1f}s）")
            stalled.append(cmd)
            if not args.keep_going:
                break
            continue
        if rc == 0 and not hits:
            print(f"    -> [PASS] ({dur:.1f}s)")
            continue
        if rc != 0:
            print(f"    -> [FAIL] rc={rc} ({dur:.1f}s)")
        else:
            # rc=0 但 stderr 命中致命告警：工具跳过了文件 = 这一条门禁根本没查完
            print(f"    -> [FAIL] rc=0 但 stderr 命中致命告警 {hits}（跳过文件即门禁失效，{dur:.1f}s）")
        failed.append(cmd)
        if not args.keep_going:
            break

    total = time.monotonic() - total_t0
    print("\n" + "=" * 72)
    if stalled:
        # 本文件头的分级：2 = 「没跑」而非「跑过」。挂住/被到点终止的门禁没给出任何结论，
        # 把它并进 failed 退 1 就是把「工具没跑成」报成「代码不合格」；而失败项的明细仍然打出来，
        # 只是由汇总码统一收在「门禁没跑」这一档（详见 AGENTS.md「格式化命令」的口径）。
        print(f"门禁未能判定：{len(stalled)} 条超时无结论（共 {len(cmds)} 条，耗时 {total:.1f}s）")
        for c in stalled:
            print(f"  [NO-VERDICT] {c}")
        if failed:
            print(f"另有 {len(failed)} 条明确失败（明细如下），但汇总码仍按「门禁没跑」= 2：")
            for c in failed:
                print(f"  [FAIL] {c}")
        print("按 AGENTS.md「完成定义」，此时不得宣布完成。")
        print("=" * 72)
        return 2
    if failed:
        print(f"门禁未通过：{len(failed)} 条失败（共 {len(cmds)} 条，耗时 {total:.1f}s）")
        for c in failed:
            print(f"  [FAIL] {c}")
        print("按 AGENTS.md「完成定义」，此时不得宣布完成。")
        print("=" * 72)
        return 1
    print(f"门禁全绿：{len(cmds)} 条全部通过（耗时 {total:.1f}s）")
    print("=" * 72)
    # DoD 第 1 步还包含 pytest（0 警告）+ check_coverage.py + basedpyright。
    # warnings summary 兜底在此直接执行、但不进上方命令清单：那一章只声明格式化门禁，
    # 把测试门禁写进去就又造出一处并行事实源。
    print("\n[pytest warnings summary 兜底]")
    ok, msg = gate_pytest_warnings_summary()
    if ok:
        print(f"  [PASS] {msg}")
    else:
        print(f"  [FAIL] {msg}")
        print("  有告警被吞掉，请先修根因，不得加 filterwarnings 压制。")
        print("=" * 72)
        return 1
    print("提醒：完成定义第 1 步还需 scripts/check_coverage.py + basedpyright。")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
