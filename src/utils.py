#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import functools
import hashlib
import inspect
import io
import json
import os
import random
import re
import shutil
import signal
import stat
import string
import subprocess
import sys
import tempfile
import threading
import traceback
import zipfile
from collections import OrderedDict
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, ParamSpec, TypeVar, cast
from urllib.parse import parse_qs, urlparse

import i18n

# 工具函数模块 - 提供通用工具函数，包括配置文件读写、文件操作、字符串处理等


# URL scheme 白名单校验：仅放行 http(s) 与 ws(s)，防 URL_config.ini 写入 file:// / gopher:// / ftp://
# 造成 SSRF（stream_select 的流地址校验与后续解析链路会按 URL 触发请求）。
# 定义在 utils 而非 spider：真正的请求入口（async_http / sync_http）在依赖链更底层，反向 import spider
# 会成环，定义在 spider 时该函数零生产调用、退化成纸面防御；utils 无业务依赖，各层可直接引用。
_SAFE_URL_SCHEMES = frozenset({"http", "https", "ws", "wss"})


def is_safe_http_url(url: str) -> bool:
    # 校验 scheme 是否在白名单内；空串/缺 scheme 的相对路径一律拒绝。
    # 还必须校 netloc：只看 scheme 时裸 "http://" 同样过闸，而各处对「缺主机名」的报错口径不同源
    # （异步侧 _internal_stream_target_reason、同步侧 urllib 自带报错），故在此前移成单点拒绝。
    parsed = urlparse(url)
    return parsed.scheme in _SAFE_URL_SCHEMES and bool(parsed.netloc)


# ─────────────────────────────────────────────────────────────
# JS 执行
#
# 多个平台（LiveMe / 嗨秀 / 抖音 X-Bogus / 咪咕）需调 node 子进程执行签名脚本；execjs 内部即起子进程
# 并阻塞等 stdout，在「每房间独立线程 + 独立事件循环」模型下会**冻结该房间的整个事件循环**（咪咕最坏
# 30s），且每次调用都重新读文件 + compile。本组工具统一解决两点：① 按 (路径, mtime) 缓存编译产物；
# ② 把阻塞段丢进专用线程池，协程侧只 await。

# path -> (源文件 mtime, 编译产物)。mtime 参与键判定：脚本更新后自动重编译，无需重启进程
# （开发期频繁改签名脚本的场景）。
_js_compile_cache: dict[str, tuple[float, object]] = {}
_js_compile_lock = threading.Lock()

# ── 签名脚本完整性钉定 ──
# src/javascript/ 下的脚本是各平台签名算法的混淆产物（内含 eval），经 execjs 交给 node 执行；它们
# 是**被执行的代码**，一旦被篡改（供应链投毒、误操作覆盖、下载到错误版本）就静默产出错误签名，
# 表现为「某平台突然全部解析失败」且极难归因。本表记录基线 SHA256，供 get_compiled_js /
# run_node_script_async 比对。
# 属 AGENTS「三类钉定/校验互不覆盖」的**第③类（签名脚本层）**：只钉得住胶水脚本，钉不住真正被执行
# 的 wasm 模块，也不覆盖发布期（①）与运行期自动安装（②）的二进制。
#
# 默认**只告警不阻断**：平台改版时用户/维护者必须能自行更新脚本，强制校验会把正当更新变成「程序
# 不可用」。CI / 加固部署可设 DLR_JS_STRICT_HASH=1 让哈希不符拒绝执行；更新脚本后必须把新哈希同步
# 到此处（注明来源版本/日期）。[历史注] 曾移除 laixiu / taobao-sign 两条（零调用点，后者注释里留有
# 真实抓包凭据）。
# 表与目录的一致性由 tests/test_utils.py::TestJsPinTable::test_every_executable_js_is_pinned 常驻
# 断言（两侧集合**相等**，未登记的 .js 与表里残留的已删键都判红）。本表无「白名单外的例外」：
# vendored 的 crypto-js.min.js 也照样登记——将来若确需不钉定的脚本，须在此注明理由并同步放宽那条
# 用例，不要靠 _check_js_hash 的静默分支。
_JS_SHA256_EXPECTED: dict[str, str] = {
    # 口径：对 .js 的**原始字节**求 SHA256（rb 读取，不受 CRLF/LF 转换影响）；内容一变即须重算。
    # [历史注] 历次重算（尾部补换行、脱敏、去死代码）均为非行为改动，签名链路未动。
    "crypto-js.min.js": "9d13c4dba10bbf2b04d6c4e21c2246abf43be0fd356596c402d08eb4f9f0aecd",
    "haixiu.js": "e6ad6ce966868c56e08f3ae78056467ecdba38060692e47d536ad2210ac354c5",
    # 2026-10-28 重算：按 CODE_REVIEW_2026-10-27 4.2 删除 liveme.js 内 6 处调试打印
    # （纯日志面改动，签名算法与入参形态逐字未动）。
    "liveme.js": "0ee11b8f775d519c5a16f255b901d080bfc647f3e748ffaf012d1346d003c8a9",
    "migu.js": "65d9ebedad8a7ddd830175c989440c2d5b3770bc3913f965af6930d2a9e2c39a",
    "x-bogus.js": "41b3f4def2486df1008730e74590352fbe29a0f411509cbecc108b8eebf4a529",
}


# 「未登记」告警按文件名去重一次：run_node_script_async 每次调用都算哈希（migu 签名每房间每轮一次），
# 不去重则同一条告警按房间数×轮数刷屏、把真线索淹掉。进程级集合，随进程生命周期结束。
_js_unpinned_warned: set[str] = set()
_js_unpinned_warned_lock = threading.Lock()


def _js_unpinned_first_seen(name: str) -> bool:
    # True = 本进程首次遇到这个未登记的文件名（调用方据此决定是否告警）。
    with _js_unpinned_warned_lock:
        if name in _js_unpinned_warned:
            return False
        _js_unpinned_warned.add(name)
        return True


def _check_js_hash(js_path: str, raw: bytes) -> None:
    # 比对签名脚本哈希与钉定值；不符时按严格模式开关决定告警还是拒绝。
    name = os.path.basename(js_path)
    expected = _JS_SHA256_EXPECTED.get(name)
    # 未登记文件也走同一条告警路径：静默 return 会让「src/javascript/ 里多出第 6 个 .js」既不进
    # 钉定面、也不留痕迹。刻意不把未登记升级成 strict 拒绝——动态生成/第三方的临时脚本不该被钉定表
    # 误伤，「拒绝执行」只保留给「登记过但内容变了」这一种可归因情形。复用已登记那条「与钉定值不符」
    # 文案（只把期望值写成未登记），不新造 msgid（新 msgid 要求四份语言目录 + 重编译 .mo 同改）。
    unpinned = expected is None
    if unpinned and not _js_unpinned_first_seen(name):
        return
    actual = hashlib.sha256(raw).hexdigest()
    if not unpinned and actual == expected:
        return
    shown_expected = "未登记（_JS_SHA256_EXPECTED 无该键，本次已跳过校验）" if unpinned else str(expected)
    strict = os.environ.get("DLR_JS_STRICT_HASH", "").strip().lower() in ("1", "true", "yes")
    if strict and not unpinned:
        raise RuntimeError(
            f"签名脚本 {name} 的 SHA256 与钉定值不符，已按 DLR_JS_STRICT_HASH=1 拒绝执行"
            f"（期望 {shown_expected}，实际 {actual}）"
        )
    logger.warning(
        i18n.tr(
            "签名脚本 {name} 的 SHA256 与钉定值不符（期望 {expected}，实际 {actual}）；"
            "若你刚更新过该脚本请同步更新 utils._JS_SHA256_EXPECTED，否则请核查文件是否被篡改",
            name=name,
            expected=shown_expected,
            actual=actual,
        )
    )


def get_compiled_js(js_path: str) -> object:
    # 读取并编译 JS 脚本，按 (路径, mtime) 缓存；被并发调用时由锁串行化。
    try:
        mtime = os.path.getmtime(js_path)
    except OSError:
        mtime = 0.0
    with _js_compile_lock:
        cached = _js_compile_cache.get(js_path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        # 读字节再解码：哈希必须对原始字节计算（BOM / 换行形态都会影响摘要，
        # 用解码后的 str 反算会与文件实际内容不一致）
        with open(js_path, "rb") as f:
            raw = f.read()
        _check_js_hash(js_path, raw)
        # 解码必须带 errors="replace"：脚本属外部可改写的输入（用户手工更新、编辑器存成 GBK），
        # UnicodeDecodeError 会穿出本函数并被 76 处平台解析的 trace_error_decorator 归成「JS 执行环境
        # 异常」，把「一个脚本文件的编码问题」误报成整条签名链故障；换成 U+FFFD 后 execjs 报的是语法
        # 错误，故障仍可见但归因落在真正的文件上。
        source = raw.decode("utf-8", errors="replace")
        compiled = execjs.compile(source)
        _js_compile_cache[js_path] = (mtime, compiled)
        return compiled


def _js_runtime_accepts_timeout(call_fn: Callable[..., object]) -> bool:
    # 兼容闸：timeout= 只有部分 JS 运行时接受。
    #   · exejs（requirements 首选）：call(key, *args, timeout=None) → 内部 subprocess.run(timeout=…)，
    #     超时 kill 子进程；
    #   · 新版 PyExecJS：call(*args, **kwargs) 里 kwargs.get("timeout") 同样有效；
    #   · 已停止维护的 PyExecJS 1.5.1（回退分支可能拿到）：call(self, name, *args) 不收关键字 → 多传
    #     即 TypeError，会让该环境下全部 JS 签名平台瞬间作废。
    # 故只在签名确实接受时透传；不接受时超时语义完全由外层 asyncio.wait_for 保证（代价：那条路径上
    # node 子进程不会被主动 kill，仅 await 侧能脱身）。
    try:
        parameters = inspect.signature(call_fn).parameters
    except TypeError, ValueError:  # pragma: no cover - C 实现等取不到签名的情形
        return False
    if "timeout" in parameters:
        return True
    return any(param.kind is inspect.Parameter.VAR_KEYWORD for param in parameters.values())


async def run_js_async(js_path: str, func_name: str, *args: object, timeout: float = 30.0) -> object:
    # 异步执行 JS 脚本中的 func_name（阻塞段整体丢线程池，事件循环不被冻结）。返回值由各平台
    # 脚本约定为 str / dict，调用方自行 cast。
    #
    # 超时预算必须**双保险**，两层缺一即留洞——
    #   ① 运行时侧的 timeout= 是唯一能真正回收 node 子进程的一层（execjs 内部起子进程并在超时
    #      时 kill），但它只管子进程，管不到本协程；
    #   ② asyncio.wait_for 管 await 侧：阻塞段跑在工作线程里，而**线程不可取消**，① 一旦不生效
    #      （回退分支的 PyExecJS 1.5.1 不收 timeout；或子进程已死而管道未关）await 就永久挂住。
    #      本仓房间线程模型是「每房间一个线程 + 各自 asyncio.run 逐轮驱动」，挂死即该轮永不返回、
    #      且**不归还网络信号量**（main.py 侧 `with semaphore: asyncio.run(...)`），单个房间就能把
    #      调度容量永久吃掉一格——正是本仓最忌的静默挂死形态。
    # 外层预算刻意与内层同值：调用方拿到的最坏等待就是 timeout。两类超时异常一律**上抛**，交调用方
    # 的 trace_error_decorator 兜底并计入按 host 的失败样本——在本函数里吞成返回值会让熔断器看不到
    # 坏线路。
    def _sync_call() -> object:
        call_fn = cast("Callable[..., object]", getattr(get_compiled_js(js_path), "call"))
        kwargs: dict[str, float] = {"timeout": timeout} if _js_runtime_accepts_timeout(call_fn) else {}
        return cast(object, call_fn(func_name, *args, **kwargs))

    return await asyncio.wait_for(
        asyncio.get_running_loop().run_in_executor(_js_executor(), _sync_call), timeout=timeout
    )


# JS 阻塞段**不能**丢进 `asyncio.to_thread` 的默认线程池：默认池由 asyncio 自己管，`asyncio.run()`
# 收尾时 `shutdown_default_executor()` 给的是 **300 秒** join 超时，正好对上「内层超时语义失效 →
# 工作线程永久阻塞」这条可达形态（PyExecJS 1.5.1 不收 timeout；execjs 在 kill 后又调一次不带超时的
# communicate），后果是房间线程停摆 5 分钟。改自有池后 asyncio.run 不再等它，房间线程只受本函数的
# timeout 约束。上限 4 个 worker：JS 签名是短任务，池只是「别冻结事件循环」的载体，堆大只会放大
# 「一堆线程同时挂死」时的资源占用。
# 残余风险（如实登记）：worker 仍是非守护线程，解释器退出时 _python_exit 仍会 join 它们；真正闭合
# 要靠自管 Popen + communicate(timeout) + 进程树 kill，属独立的签名执行链，不在本次范围。
_JS_EXECUTOR: object | None = None
_JS_EXECUTOR_LOCK = threading.Lock()


def _js_executor() -> "ThreadPoolExecutor":
    global _JS_EXECUTOR
    with _JS_EXECUTOR_LOCK:
        if _JS_EXECUTOR is None:
            _JS_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="js-call")
        return cast("ThreadPoolExecutor", _JS_EXECUTOR)


# ── node 子进程超时后的进程树回收 ────────────────────────
# 与 src/notify.py 的 _kill_process_tree 同一套口径（POSIX: start_new_session + killpg；
# Windows: taskkill /T /F 一律 argv 列表、禁 shell=True；任一步失败退化到 kill 直接子进程）。
# **刻意不 import notify 那份实现**：notify 顶层 `import main`（要用 main.os_type / 推送配置），而
# utils 位于依赖链最底层，反向依赖会把整套录制引擎锁体系带进只读工具层。两份实现同构但各自独立，
# 改这里的回收判据时**须一并核对 src/notify.py 的对应分支**。
# 平台判定做成模块级常量而非函数内读 os.name：用例可 monkeypatch 它让 Windows 分支在 Linux CI 上
# 真实执行（AGENTS「平台专属分支的测试不得靠 skipif 让 CI 跳过」）。
_NODE_TREE_KILL_VIA_TASKKILL = os.name == "nt"

# taskkill 自身的时限（秒）：不得让「回收进程树」变成第二个挂起点（与 notify 同值）。
_NODE_TREE_KILL_TIMEOUT_SECONDS = 5.0

# 超时后收尸的时限（秒）。必须收尸：Popen.__del__ 见到 returncode 仍为 None 就发 ResourceWarning
# ("subprocess ... is still running")，而门禁要求「pytest 0 警告」；但等待一律带上限。
_NODE_REAP_TIMEOUT_SECONDS = 5.0


# POSIX 进程组回收：node 以 start_new_session=True 启动 ⇒ 自成会话，进程组 ID == 子进程 PID，
# killpg 一次收掉脚本 + 它起的全部孙进程（只 kill 直接子进程会留下握着管道写端的孙进程）。
# os.killpg/os.getpgid 与 signal.SIGKILL 都是 POSIX-only 符号（typeshed 在 win32 下不导出），必须用
# sys.platform **字面量**早返回门控，mypy 的 linux / win32 双跑才都能过；门控方向写反静态检查发现
# 不了，由 tests/test_utils.py::TestRunNodeScriptTimeoutBudget::test_posix_gate_direction_is_locked_in_source
# 断言「早返回行在 killpg 行之前且比较的是 == "win32"」锁住。
def _kill_posix_process_group(pid: int) -> None:
    if sys.platform == "win32":
        return
    os.killpg(os.getpgid(pid), signal.SIGKILL)


# 超时后回收**整棵进程树**并收尸；任何失败一律退化到只杀直接子进程，绝不向调用方抛出——
# 本函数的职责只是清理，超时语义由此后调用方继续上抛的 TimeoutExpired 决定。
def _kill_node_process_tree(process: subprocess.Popen[bytes], script_name: str) -> None:
    try:
        if _NODE_TREE_KILL_VIA_TASKKILL:
            # Windows：taskkill /T（递归子树）/F（强制），argv 列表调用、禁 shell=True；capture_output
            # 后按字节原样丢弃、**不做解码**（中文 Windows 上 taskkill 按 GBK 码页回显本地化消息，
            # AGENTS「探测子进程输出一律按字节比较」同源）。
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                timeout=_NODE_TREE_KILL_TIMEOUT_SECONDS,
                check=False,
            )
        else:
            _kill_posix_process_group(process.pid)
    except Exception as e:
        # 典型落点：Linux CI 上被强制走 Windows 分支时没有 taskkill（FileNotFoundError）、taskkill
        # 自身超时、孙进程已自行退出（ProcessLookupError）。留痕但不改写结果——下面 finally 仍会
        # kill + wait 直接子进程。script_name 只传 basename：路径里的用户目录名不进日志。
        logger.warning(
            i18n.tr(
                "回收 node 签名子进程树失败: {script} - {type_name}: {e}",
                script=script_name,
                type_name=type(e).__name__,
                e=e,
            )
        )
    finally:
        try:
            process.kill()
        except OSError:
            # 进程已自行退出（ProcessLookupError 是 OSError 子类）正是期望结果，无需上报
            pass
        # 只 wait、**绝不再读一次管道**：subprocess.run 的超时分支正是在 kill 后又调了一次
        # 不带超时的 communicate() 才永久挂住的（该根因）。
        try:
            process.wait(timeout=_NODE_REAP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            # SIGKILL 尚未生效（不可中断睡眠 / 任务管理器挂住）：在这里继续等就等于把一次
            # 挂死换成另一次挂死，故按上限放手，交给 CPython 的活跃子进程回收机制兜底。
            pass


async def run_node_script_async(script_path: str, *args: str, timeout: float = 30.0) -> str:
    # 异步执行 node 脚本（阻塞段丢线程池，事件循环不被冻结）；咪咕签名等「整段脚本 + 命令行参数」
    # 形态走此入口。内部用自管 Popen + communicate(timeout)：subprocess.run 的 timeout 分支在 kill
    # 后还会调一次**不带超时**的 communicate()，孙进程握着管道写端时那次读取永远等不到 EOF。
    #
    # 本入口同样做脚本哈希校验——migu.js 是唯一走本入口的脚本，即「整段脚本直接交给 node 执行」这一
    # 最易被动手脚的形态。「读文件算哈希 → 再把**路径**交给 node」是 check-then-use，两步之间文件可被
    # 替换（具备写权限者即绕过钉定表），故改为「读一次字节 → 校验 → 把**同一份字节**经 stdin 交给 node
    # （`node - arg…`）」，TOCTOU 窗口消除。
    # 取舍（再换方案前务必知道）：经 stdin 执行的脚本里 __filename 为 "-"、__dirname 指向进程 CWD，
    # 故脚本**不能**依赖自身所在目录解析相对路径（require('./x') / 读同目录 wasm 等）。当前唯一使用者
    # migu.js 只读 process.argv[2]，不受影响。若将来接入依赖 __dirname 的脚本，请改为「校验通过后把
    # 内容复制进 mkdtemp 私有目录再执行该副本」（代价：需同步复制相对依赖、清理临时目录），不要直接
    # 退回传路径。
    def _sync_run() -> str:
        with open(script_path, "rb") as f:
            raw = f.read()
        _check_js_hash(script_path, raw)
        argv = ["node", "-", *args]
        if _NODE_TREE_KILL_VIA_TASKKILL:
            # Windows：不传 start_new_session（CPython 的 Windows 侧那是 unused_start_new_session），
            # 进程树一律交 taskkill /T。
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            # POSIX：让 node 自成会话/进程组 ⇒ _kill_posix_process_group 的 killpg 能一次收掉
            # 整棵树（孙进程继承着 stdout 管道的写端，只 kill 直接子进程时永远读不到 EOF）。
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        try:
            stdout, _stderr = proc.communicate(input=raw, timeout=timeout)
        except subprocess.TimeoutExpired:
            # 回收整棵树后**原样上抛**：与 run_js_async 一致，本函数不吞超时（吞了会让熔断器
            # 看不到坏线路），超时语义交调用方（spider._get_dd_calcu 一律转 ProgramError）。
            _kill_node_process_tree(proc, os.path.basename(script_path))
            raise
        if proc.returncode != 0:
            # 非零退出抛 CalledProcessError，由调用方转成平台错误（不得静默返回空串——那会被下游
            # 当成「签名为空」的另一种故障形态）。
            raise subprocess.CalledProcessError(proc.returncode, argv)
        # input=bytes 与 text=True 互斥，故这里按字节捕获再显式解码 UTF-8（与旧实现同口径）
        out: bytes = stdout or b""
        # 这里只能给 errors="replace"，不能只给 encoding——只传 encoding 会把错误处理器重置回 strict，
        # 于是「node 在 GBK locale 下回显本地化消息」时 UnicodeDecodeError 取代真正的
        # CalledProcessError，故障归因整体丢失。脱敏也无法在字节层做：规则是 str 形态的正则
        # （_SECRET_*_RE），强行拼一套等于造出第二份判据，故仍落在调用方（各解析函数对 str 结果过码）。
        # 回归锁：tests/test_utils.py::TestDecodeErrorsNeverEscape。
        return out.decode("utf-8", errors="replace").strip()

    # 超时预算双保险，形态与 run_js_async 一致（两层缺一即留洞，挂死代价见该函数注释）：
    # ① 内层 communicate(timeout=) 是唯一能真正回收 node 进程树的一层，但它只管子进程与本线程；
    # ② 外层 asyncio.wait_for 管 await 侧——线程不可取消，① 一旦不生效（管道被孙进程拖住、有人把
    #    执行方式改回不带超时的形态、Popen 构造本身阻塞）await 就永久挂住。
    # 外层预算刻意与内层同值：调用方拿到的最坏等待就是 timeout。两类超时异常一律**上抛**。
    # [历史注] 本函数刻意走 asyncio.to_thread 默认池而非 _JS_EXECUTOR 自有池：
    # 与 run_js_async 的差异在于本函数内层 communicate 必带 timeout 且超时即回收进程树
    # （_kill_node_process_tree），线程不会被无限拖死，自有池防的「shutdown_default_executor
    # 300s join」形态在此不成立；两函数为何不同池，以本注为准。
    return await asyncio.wait_for(asyncio.to_thread(_sync_run), timeout=timeout)


# 优先使用 exejs（PyExecJS 的活跃维护继任者），未安装时回退到 PyExecJS
try:
    import exejs as execjs

    ProgramError = execjs.ExejsProgramError
except ImportError:
    import execjs  # type: ignore[no-redef]
    from execjs import ProgramError  # type: ignore[no-redef]

import configparser

from .logger import logger

OptionalStr = str | None
OptionalDict = dict[str, object] | None

# 表情符号匹配模式（模块级编译一次）：remove_emojis 经 clean_name 被每个房间每轮多次调用（80+ 房间
# 每秒可达数百次），原先每次调用都拼接 10 段字符串再 re.compile。提为常量后省去构建与编译开销，
# 匹配语义完全不变。
_EMOJI_PATTERN = re.compile(
    "["
    + "\U0001f1e0-\U0001f1ff"  # flags (iOS)
    + "\U0001f300-\U0001f5ff"  # symbols & pictographs
    + "\U0001f600-\U0001f64f"  # emoticons
    + "\U0001f680-\U0001f6ff"  # transport & map symbols
    + "\U0001f700-\U0001f77f"  # alchemical symbols
    + "\U0001f780-\U0001f7ff"  # Geometric Shapes Extended
    + "\U0001f800-\U0001f8ff"  # Supplemental Arrows-C
    + "\U0001f900-\U0001f9ff"  # Supplemental Symbols and Pictographs
    + "\U0001fa00-\U0001fa6f"  # Chess Symbols
    + "\U0001fa70-\U0001faff"  # Symbols and Pictographs Extended-A
    + "\U00002702-\U000027b0"  # Dingbats
    + "]+",
    flags=re.UNICODE,
)


class Color:
    # 终端彩色输出常量类（ANSI SGR 码）
    RED: str = "\033[31m"
    GREEN: str = "\033[32m"
    YELLOW: str = "\033[33m"
    BLUE: str = "\033[34m"
    MAGENTA: str = "\033[35m"
    CYAN: str = "\033[36m"
    WHITE: str = "\033[37m"
    RESET: str = "\033[0m"

    @staticmethod
    def print_colored(text: str, color: str) -> None:
        # 注意：实参由调用方在查表前插值，故 i18n 提取器扫不到这里的文案（AGENTS「i18n 扫描
        # 盲区清单」第 ① 类），新增用户可见文案须手工登记进四语目录。
        print(f"{color}{text}{Color.RESET}")


P = ParamSpec("P")
R = TypeVar("R")


def _log_guarded_exception(e: Exception, func: Callable[..., object], fallback_type_name: str) -> None:
    # 异常落日志的唯一实现（同步/异步两支原先各抄一份、共 4 段逐字重复的判定+文案），按类型分流：
    #   · ProgramError（JS 运行时环境级故障）→ warning + i18n 模板；
    #   · 其它 → error + 带行号与兜底值类型的归因串。
    # ProgramError 分支必须与 generic 分支同口径（函数名/异常类型/异常内容齐备）：否则环境级故障
    # （Node 缺失 / 签名脚本执行失败）会被静默降级成「未开播」，非中文语言下还混入英文且无归因线索。
    if isinstance(e, ProgramError):
        logger.warning(
            i18n.tr(
                "JS 执行环境异常（Node.js 缺失或签名脚本执行失败）: 类型: {type_name}, {masked} in function {func_name}",
                type_name=type(e).__name__,
                masked=mask_credentials(str(e)),
                func_name=func.__name__,
            )
        )
        return
    tb = traceback.extract_tb(e.__traceback__) if e.__traceback__ else None
    error_line = tb[-1].lineno if tb else "unknown"
    # str(e) 须过码：本装饰器是 76 处平台解析的中央异常漏斗，InvalidURL/TooManyRedirects 等的 str
    # 内嵌完整 URL（可能带 token 参数），直落日志即凭据明文持久化。现网 raise 点已手工过码，此处
    # 兜住未来新路径。先拼到变量再传 logger——直接把 f-string 传进 logger 会触发「翻译在查表前完成」
    # 的形态锁（tests/test_regression_danmaku.py）。
    error_info = (
        f"message: type: {type(e).__name__}, {mask_credentials(str(e))} in function {func.__name__}"
        f" at line: {error_line}, fallback type: {fallback_type_name}"
    )
    logger.error(error_info)


def _make_trace_error_guard(func: Callable[P, R], fallback_factory: Callable[[], R]) -> Callable[P, R]:
    # 错误追踪装饰器的共用实现（同步/异步两支）：吞掉异常并返回 fallback，日志同时标注函数名与兜底
    # 值类型，便于定位「错误被伪装成正常结果」的现场。两支除 await 外逻辑一致。
    #
    # fallback 必须是**工厂**而非值：装饰时只构造一次会让 76 处平台解析函数返回**同一个 dict 实例**，
    # 任何调用方对返回值写入都会污染全局兜底并跨房间、跨轮次串数据。改成每次调用新建后该类「偶发脏
    # 数据」从结构上不再可能；兜底值类型名仍在装饰时算一次（只用于日志文案）。
    fallback_type_name = type(fallback_factory()).__name__
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return cast(R, await func(*args, **kwargs))
            except Exception as e:
                _log_guarded_exception(e, func, fallback_type_name)
                return fallback_factory()

        return cast(Callable[P, R], async_wrapper)

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            _log_guarded_exception(e, func, fallback_type_name)
            return fallback_factory()

    return wrapper


def trace_error_decorator(func: Callable[P, R]) -> Callable[P, R]:
    # 错误追踪装饰器：吞掉异常并返回 {"is_live": False}。绝大多数被装饰函数（各平台
    # get_xxx_stream_data）返回含 is_live 键的 dict，调用方据其判定未开播。返回 str/tuple/None 的
    # 函数必须改用 trace_error_decorator_or_none，否则调用方会静默拿到一个 dict，把错误伪装成正常
    # 结果（解包时抛 ValueError 又被这层兜底二次吞掉，根因彻底丢失）。
    return _make_trace_error_guard(func, lambda: cast(R, {"is_live": False}))


def trace_error_decorator_or_none(func: Callable[P, R]) -> Callable[P, R]:
    # trace_error_decorator 的类型匹配变体：出错返回 None，供返回 str/tuple 等类型的函数
    # （login_*、get_*_info、get_*_tk）使用，调用方按 falsy 处理失败、判空后再解包。
    return _make_trace_error_guard(func, lambda: cast(R, None))


def check_md5(file_path: str | Path) -> str:
    # 整文件读入算 MD5。唯一生产用途是 config_io 的热加载变更检测（比对 config.ini /
    # URL_config.ini 这类小文件）；下载产物的完整性校验一律用下方 sha256_of_file。
    with open(file_path, "rb") as fp:
        file_md5 = hashlib.md5(fp.read()).hexdigest()
    return file_md5


# 分块计算文件 SHA256：用于下载产物完整性校验。整读几百 MB 二进制会瞬时占用大量内存，分块
# （1MB/块）保持内存恒定。ffmpeg_install 与 node_install 原先各写一份，收敛到此为唯一实现。
def sha256_of_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# 校验本地缓存的压缩包是否完整可用：os.path.exists 只证明文件存在，分不清「下载完整」与「下载被
# 中断的残缺文件」。zipfile.is_zipfile 读尾部 End Of Central Directory 记录，残缺包（无 EOCD）返回
# False——足以拦住最常见的中断残留形态，且不解压全文、开销极小。
# node_install 原先只判 exists()，残缺 zip 被当成「已下载」并把错误哈希固化成基线、此后永久失败且
# 不自愈；收敛到 utils 后两条安装路径共用同一判据。
def is_valid_zip(path: str | Path) -> bool:
    # 模块顶已导入 zipfile，不在此重复 import（本函数不是导入期敏感的路径）
    try:
        return bool(zipfile.is_zipfile(path))
    except OSError, ValueError:
        return False


def unzip_file(zip_path: str | Path, extract_to: str | Path, delete: bool = True) -> None:
    # 解压 ZIP 到指定目录（含 Zip Slip 目录穿越校验 + 解压炸弹防护）。node_install / ffmpeg_install
    # 共用同一份实现——原先两处逐字重复，任一处打安全补丁都会漏掉另一处。
    # exist_ok=True：「先 exists 再 makedirs」是两步 TOCTOU，node/ffmpeg 并发安装时后到者会吃到
    # FileExistsError 并被上层归成「安装失败」。
    os.makedirs(extract_to, exist_ok=True)

    extract_root = os.path.realpath(extract_to)
    # 解压炸弹防护（审查）：恶意压缩包可声明极小尺寸但解压后膨胀到磁盘满 / OOM。
    # 上限：单文件 4GB、累计 8GB、压缩比 100x（正常压缩比通常 <10x，FFmpeg 二进制 ~70MB）；
    # 宁可误拦合法大包（用户改 max_total_size 重试），不可放过炸弹。
    _MAX_ENTRY_SIZE = 4 * 1024 * 1024 * 1024
    _MAX_TOTAL_SIZE = 8 * 1024 * 1024 * 1024
    _MAX_RATIO = 100

    total_uncompressed = 0
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        # 符号链接成员必须在 extractall 之前拒绝：目录穿越校验只看**成员路径字面量**，含「link -> /etc」
        # 再写「link/xxx」的包能让后续写入跟着链接走出 extract_root——ffmpeg/node 安装包来自外部下载
        # 源，属真实攻击面（zipfile 自 3.13 起会对链接做一次落地复核，但那是同库实现细节、只覆盖部分
        # 形态，不能替代本层显式拒绝）。判据取 Unix 权限位高 16 位：zip 无「这是链接」的独立标志位。
        for info in zip_ref.infolist():
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"Symlink entry in zip file: {info.filename}")
        # 防止 Zip Slip 目录穿越攻击：校验每个成员解压后的真实路径
        for member in zip_ref.namelist():
            member_path = os.path.realpath(os.path.join(extract_root, member))
            if not member_path.startswith(extract_root + os.sep) and member_path != extract_root:
                raise ValueError(f"Unsafe path in zip file: {member}")
            info = zip_ref.getinfo(member)
            if info.file_size > _MAX_ENTRY_SIZE:
                raise ValueError(f"Zip entry too large (bomb?): {member} declared {info.file_size} bytes")
            total_uncompressed += info.file_size
            # 压缩比校验：恶意包可仅写 1 字节并循环引用，未压缩累计总和炸出数 TB；
            # 物理大小阈值取磁盘占用超 10MB 才有意义（小包算压缩比误差大）
            if info.compress_size > 0 and info.file_size > 10 * 1024 * 1024:
                ratio = info.file_size / info.compress_size
                if ratio > _MAX_RATIO:
                    raise ValueError(
                        f"Zip compression ratio too high (bomb?): {member} ratio={ratio:.1f}x "
                        f"({info.compress_size} -> {info.file_size})"
                    )
            if total_uncompressed > _MAX_TOTAL_SIZE:
                raise ValueError(f"Zip total uncompressed size too large (bomb?): {total_uncompressed} bytes")
        zip_ref.extractall(extract_to)

    if delete and os.path.exists(zip_path):
        os.remove(zip_path)


def dict_to_cookie_str(cookies_dict: Mapping[str, object]) -> str:
    # cookie 字典 -> `k=v; k=v` 的请求头字符串
    cookie_str = "; ".join([f"{key}={value}" for key, value in cookies_dict.items()])
    return cookie_str


# ini 解析器的唯一构造入口：read_ini_value 与 update_config 都经它取。
# 必须是 src/config_read.py::tolerant_config_parser（strict=False + interpolation=None），不得就地
# 写 configparser.ConfigParser(interpolation=None)：后者 strict 默认 True，遇到「同节两行同名键」时
# 在 read() 里就抛 DuplicateOptionError，于是 [Cookie]/[Authorization] 的 cookie/token 刷新在这种
# 配置形态下**永远写不回**，用户只看到一条「Error occurred while reading the configuration file」。
# preserve_case 取默认 False：这两处历史上用的就是默认 optionxform（键名一律转小写），
# `read_ini_value(..., "GUI", "Gui_Font")` 这类大小写混排入参靠的正是「转小写后比较」。
# **延迟导入是硬约束**：src/config_read → src/web_config → src/utils 是既有依赖链（web_config 顶层
# `from src.utils import atomic_write_text`），提到顶层会形成导入环（utils 只执行到一半即 ImportError）。
def _tolerant_ini_parser() -> configparser.ConfigParser:
    from src.config_read import tolerant_config_parser

    return tolerant_config_parser()


def read_ini_value(file_path: str | Path, section: str, key: str) -> str | None:
    # 按**文件路径**读取 ini 配置项，每次调用重新解析文件、不写回、缺键返回 None。
    # 关闭插值：值中的裸 %（如 cookie、时间格式）不应触发 InterpolationSyntaxError；解析器经
    # _tolerant_ini_parser() 构造，同节重复键不再让整份文件读不出。
    # 方法名刻意不叫 read_config_value：那与 src/config_io.read_config_value（接收已解析 parser、
    # 缺键会补写默认值）同名不同义，混用极易传错参数（见 CODE_REVIEW_FIX_1 ）。
    config = _tolerant_ini_parser()

    try:
        _ = config.read(file_path, encoding="utf-8-sig")
    except Exception as e:
        logger.warning(i18n.tr("Error occurred while reading the configuration file: {e}", e=e))
        return None

    # MI-19：凭据键/节缺失的提示改走 logger——print 不进日志文件，用户提交日志求助时看不到
    # 「凭据键缺失」这一关键原因（本函数是 [Cookie] 的读取入口）。
    if section in config:
        if key in config[section]:
            return config[section][key]
        logger.warning(i18n.tr("Key [{key}] does not exist in section [{section}].", key=key, section=section))
    else:
        logger.warning(i18n.tr("Section [{section}] does not exist in the file.", section=section))

    return None


# [历史注] 兼容别名 `read_config_value = read_ini_value`（三参路径形态）已删除：全仓零调用点
# （main.py 的 100+ 处同名调用全部指向 src.config_io）。`utils.read_ini_value` 是唯一入口。


# ── 原子写的可注入落盘原语（测试缝）─────────────────────
# 要求「fsync 必须先于 os.replace」成为可断言的不变量，但用例不能 patch stdlib `os` 模块本体
# （全进程生效，会波及 loguru enqueue 线程与 harness 守护线程）。经这两个模块级名字调用后，测试
# 只需 monkeypatch.setattr(utils, "_fsync_file"/"_replace", spy) 即可观察调用顺序；封装内部仍是
# 运行时查 `os.` 属性，故其它用例 patch `os.replace` 依旧命中同一条路径。
def _fsync_file(fd: int) -> None:
    os.fsync(fd)


def _replace(src: str, dst: str) -> None:
    os.replace(src, dst)


def _fsync_dir(dir_path: str) -> None:
    # 对父目录 fsync：让「rename 改了目录项」这条元数据本身也落盘（POSIX 语义）。以只读方式
    # 打开目录仅 POSIX 支持，Windows 无此语义 → 按平台字面量早返回（同 i18n._windows_ui_language
    # / web_tray 的门控写法，不用 # type: ignore）。
    if sys.platform == "win32":
        return
    try:
        fd = os.open(dir_path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_text(file_path: str | Path, text: str, encoding: str = "utf-8-sig", errors: str | None = None) -> bool:
    # 原子写文本：同目录临时文件写完后 os.replace 覆盖，读方只会看到旧/新完整内容；返回是否成功落盘。
    # errors=None 即 codec 默认的 strict；唯一的非默认调用方是 remove_duplicate_lines 的回退轮
    # （surrogateescape）——那一轮读进来的代理码点必须原样还原成原字节，写侧若仍按 strict 处理会抛
    # UnicodeEncodeError，让「非 UTF-8 文件不再被转码损坏」在读侧成立、写侧破功。
    # 收敛原因（WD-15）：原子写原先分散在 config_io，而 utils.update_config 与
    # config_io.update_anchor_name 仍用 open(..., "w")——后者先把文件截断为 0 字节，此时进程被杀 /
    # 掉电 / 磁盘满，读方将读到空文件（全部配置或全部房间配置丢失）。此处收敛为唯一实现。
    #
    # close() 只把数据交给内核页缓存，随后 os.replace 改目录项，两者落盘顺序无保证
    # （ext4 ordered-mode 只是常见情况）→ 掉电可留下「新目录项 + 空数据页」的 0 字节配置。故
    # replace 前 flush+fsync 文件、replace 后 fsync 父目录。fsync 失败按 best-effort 吞掉：在「内容
    # 已完整写入页缓存、只是无法确认耐久」时拒绝发布，等于把一次防掉电加固变成「配置写不进去」。
    # （临时文件名）：原为 f"{path}.{pid}.tmp"，同进程两个线程写同一目标会共用 tmp 名
    # （open("w") 互相截断）→ 改用 tempfile.mkstemp(dir=父目录)，O_EXCL 由内核保证命名唯一。
    # （权限）：os.replace 后目标继承临时文件的模式，mkstemp 固定 0600，会让整文件重写偏离
    # 原文件权限。故写前记录原 mode、replace 前把 tmp chmod 回同值（Windows 上只影响只读位）。
    path_str = str(file_path)
    parent = os.path.dirname(os.path.abspath(path_str)) or os.getcwd()
    try:
        orig_mode: int | None = stat.S_IMODE(os.stat(path_str).st_mode)
    except OSError:
        orig_mode = None  # 目标不存在（首次写入）时按 mkstemp 默认的 0600 落盘
    try:
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=os.path.basename(path_str) + ".", suffix=".tmp")
    except OSError as e:
        logger.warning(i18n.tr("写入配置文件失败（已保留原文件）: {err}", err=e))
        return False
    try:
        with os.fdopen(fd, "w", encoding=encoding, errors=errors, newline="") as f:
            _ = f.write(text)
            f.flush()
            try:
                _fsync_file(f.fileno())
            except OSError:
                pass  # 见上方该注释：仅无法确认耐久时不阻断发布
        # 目标此前不存在时**显式**落 0600，而不是只靠 mkstemp 的默认权限。
        # 为什么要显式写一次：os.replace 后目标继承临时文件的模式，而 mkstemp 的 0600 是「与
        # umask 相与」的结果——本仓的凭据文件（config.ini 含明文 Cookie/账号密码）此前只有
        # utils.update_config 一条路径在写完 chmod 0600，首次创建与缺键补写都只经本函数，
        # 多用户 POSIX 主机上等于「凭据文件权限由 umask 决定」。既有文件一律**保留原 mode**
        # （下方 orig_mode 分支不变）：收紧别人正在共享的文件会造成新故障，加固只做在
        # 「还没有原权限可继承」的那一刻。os.chmod 在 Windows 上只影响只读位，故本条只帮到 POSIX。
        apply_mode = orig_mode if orig_mode is not None else 0o600
        try:
            os.chmod(tmp, apply_mode)
        except OSError:
            pass
        _replace(tmp, path_str)
    except (OSError, UnicodeError) as e:
        # 补 UnicodeError。原只接 OSError，而 f.write(text) 在 text 含目标编码无法表示的
        # 字符时抛 UnicodeEncodeError（ValueError 子类）——它会穿出本函数，且 *.tmp 已由 mkstemp
        # 建好却没人删，留下半写临时文件在配置目录里（备份/打包/云同步都会带上它）。
        # 清理与告警走与 OSError 完全相同的路径。
        logger.warning(i18n.tr("写入配置文件失败（已保留原文件）: {err}", err=e))
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
    _fsync_dir(parent)
    return True


# 取「URL 配置文件的写入锁」：与 config_io.update_file / delete_line / web_api 各端点共用
# main.file_update_lock（RLock，可在已持锁的调用栈里重入）。
# utils.replace_url / remove_duplicate_lines 是直接重写 URL_config.ini 的两条旁路
# （花椒地址失效自动注释走前者、主循环启动去重走后者），原先既不持锁也非原子，会与主循环热加载、
# Web 面板的原子写互相截断/覆盖。锁必须惰性取：utils 位于依赖链最底层，顶层 `import main` 会构成
# 循环导入（main → src.* → utils）。取不到时（独立脚本 / 单测直接 import utils）退化为本地锁：
# 仍保证 utils 内部两条写路径互斥，且 atomic_write_text 本身原子，不会留半写文件。
_utils_local_write_lock = threading.RLock()


def _url_config_write_lock() -> threading.RLock:
    try:
        import main as _main
    except ImportError:  # pragma: no cover - 仅在 main 不可导入的独立脚本环境发生
        return _utils_local_write_lock
    # main.py 顶部已把 __main__ 注册为 sys.modules["main"]，故这里不会二次执行入口脚本；
    # 属性缺失只可能出现在极早期（main 正在执行、尚未定义该锁）→ 同样退化为本地锁。
    return cast("threading.RLock", getattr(_main, "file_update_lock", _utils_local_write_lock))


def update_config(file_path: str | Path, section: str, key: str, new_value: str) -> None:
    # 更新 ini 中单个配置项：整文件重解析后由 atomic_write_text 原子写回（关闭插值，避免 cookie
    # 等含 % 的值被 BasicInterpolation 转义 / 反解析）。
    #
    # 读改写全程持 main.file_update_lock（复用 _url_config_write_lock 的惰性取法）——本函数
    # 被多个房间线程并发调用（cookie/token 刷新回写），「整文件读 → 改单键 → 原子写回」不持锁时
    # 两个线程各自基于同一份旧快照，后写者覆盖前写者的单键改动。锁必须盖住 config.read 与
    # config.write 全程。
    #
    # 写法语义（勿与「直写 open(path,"w")」的旧实现混淆）：WD-15 起经 atomic_write_text（同目录
    # tmp + os.replace），不再先把文件截断为 0 字节。连带后果——os.replace 只校验目标**所在目录**的
    # 写权限，与目标文件自身的权限位无关，故「把文件 chmod 成只读」在这里**不保证**写失败（Windows
    # 反之，只读属性会让 replace 直接失败）。tests/test_utils.py 的只读用例因此只断言「不抛异常 +
    # 原内容不丢」，不得按「必然失败」写。
    with _url_config_write_lock():
        # 解析器换成 _tolerant_ini_parser()。原先的 strict=True 形态下，同节重复键让 read()
        # 直接抛 DuplicateOptionError → 被下面的 except 吞成 warning 并 return，**cookie/token 的刷新
        # 永远写不回**；容错读取后重复键按「最后一次取值」折叠进内存态，写回产物每键只剩一行，仍能被
        # strict 解析器整份读出（回归锁：tests/test_utils.py::TestDuplicateKeyWriteback）。
        config = _tolerant_ini_parser()

        try:
            _ = config.read(file_path, encoding="utf-8-sig")
        except Exception as e:
            logger.warning(i18n.tr("An error occurred while reading the configuration file: {e}", e=e))
            return

        if section not in config:
            logger.warning(i18n.tr("Section [{section}] does not exist in the file.", section=section))
            return

        config[section][key] = new_value

        buf = io.StringIO()
        config.write(buf)
        if not atomic_write_text(file_path, buf.getvalue()):
            # atomic_write_text 内部已按 i18n 打印了失败原因，此处只中止后续步骤
            return
    # config.ini 含 [Cookie]/[账号密码] 等明文凭据，写入后收紧为仅属主可读写
    # （best-effort：Windows 上 os.chmod 仅影响只读属性，失败忽略）
    try:
        os.chmod(str(file_path), 0o600)
    except OSError:
        pass
    logger.debug(
        i18n.tr(
            "The value of {key} under [{section}] in the configuration file has been updated.",
            key=key,
            section=section,
        )
    )


def get_file_paths(directory: str) -> list[str]:
    # 递归收集指定目录下所有文件的绝对路径（os.walk 拼接，不跟随符号链接环）
    file_paths: list[str] = []
    for root, _, files in os.walk(directory):
        for file in files:
            file_paths.append(os.path.join(root, file))
    return file_paths


def remove_emojis(text: str, replace_text: str = "") -> str:
    # 移除表情符号（模式为模块级常量 _EMOJI_PATTERN，此处不再重复编译）
    return _EMOJI_PATTERN.sub(replace_text, text)


def remove_duplicate_lines(file_path: str | Path) -> None:
    # 移除文件中的重复行（URL_config.ini 启动期去重）。
    # 整文件重写必须持 main.file_update_lock + 原子写（与 config_io 的 update_file/
    # delete_line 同一把锁），否则与主循环热加载 / Web 面板写入并发时会读到半写文件、或在 Windows
    # 上让对端的 os.replace 直接失败。编码回退分支必须先 clear() 首轮结果——首轮按 utf-8-sig
    # 读出的行可能已带 U+FFFD 替换字符，不清空就会把两轮混合的键写回文件。
    #
    # ①（行尾）：两处读一律 newline=""。默认 universal newlines 会把 \r\n 读成 \n，而写侧
    # atomic_write_text 走 newline="" 不做翻译，于是本函数每次执行都会把整份 URL_config.ini 的 CRLF
    # 永久改成 LF；而它在 main() 启动期被**无条件**调用一次，等于每次开机重写一遍。
    # ②（去重键）：键只剥行尾（rstrip("\r\n")），不再 strip()。旧写法回写的是 strip 过的行
    # （行首缩进丢失），且 `url` 与 `url ` 被判成同一行、其中一条房间地址被**静默删掉**。现在键只用于
    # 判重，回写的是该键首次出现时的**原始行**（含原行尾）；仅行尾形态不同仍算同一行，与
    # config_io.delete_line 比较口径一致。
    # ③（编码）：两轮都显式 utf-8-sig，回退轮另加 errors="surrogateescape"——无法解码的
    # 字节映射为代理码点、写回时（同一 errors）还原成原字节，不再静默转码损坏 GBK/UTF-16 文件；
    # BOM 语义保持「读时剥一枚、写时补一枚」往返，既不丢也不重复加。
    # 键 -> 首次出现的原始行（含原行尾）；OrderedDict 的插入序即回写顺序
    unique_lines: OrderedDict[str, str] = OrderedDict()
    text_encoding = "utf-8-sig"
    with _url_config_write_lock():
        try:
            with open(file_path, "r", encoding=text_encoding, newline="") as input_file:
                for line in input_file:
                    _ = unique_lines.setdefault(line.rstrip("\r\n"), line)
        except UnicodeDecodeError:
            # 非 UTF-8 文件（GBK/UTF-16 等）：显式编码 + surrogateescape 重读，保证回写的
            # 内容字节与原文件一致（见上方，不再回落到宿主 locale）
            unique_lines.clear()
            with open(file_path, "r", encoding=text_encoding, errors="surrogateescape", newline="") as input_file:
                for line in input_file:
                    _ = unique_lines.setdefault(line.rstrip("\r\n"), line)
        out = "".join(unique_lines.values())
        if out and not out.endswith(("\n", "\r")):
            # 末行原本无行尾时补 \n（与 replace_url 的同一口径，不引入新的差异形态）
            out += "\n"
        _ = atomic_write_text(file_path, out, encoding=text_encoding, errors="surrogateescape")


def check_disk_capacity(file_path: str | Path, show: bool = False) -> float:
    # 检查指定文件所在磁盘的剩余空间（GB）
    absolute_path = os.path.abspath(file_path)
    directory = os.path.dirname(absolute_path)
    disk_usage = shutil.disk_usage(directory)
    disk_root = Path(directory).anchor
    free_space_gb = disk_usage.free / (1024**3)
    if show:
        # 三段 f-string 相加的首参是 ast.BinOp，i18n 门禁看不见、翻译在查目录前就已插值。
        # GB 数值按约定在调用方预求值（:.2f 不进模板），实参名沿用目录里既有 msgid 的
        # disk_usage / disk_usage_2（同模板内重名加 _2 后缀）。
        print(
            i18n.tr(
                "{disk_root} Total: {disk_usage} GB Used: {disk_usage_2} GB Free: {free_space_gb} GB\n",
                disk_root=disk_root,
                disk_usage=f"{disk_usage.total / (1024**3):.2f}",
                disk_usage_2=f"{disk_usage.used / (1024**3):.2f}",
                free_space_gb=f"{free_space_gb:.2f}",
            )
        )
    return free_space_gb


def handle_proxy_addr(proxy_addr: str | None) -> str | None:
    # 代理地址归一：无协议前缀时补 http://（httpx / ffmpeg 的 proxy 参数都要求带 scheme，
    # 而配置项「代理地址」允许用户只写 host:port）；已含 :// 的地址（socks5:// 等）原样保留，
    # 不二次添加。空值统一归成 None——调用方以「None = 不走代理」判定，不能留空串。
    if proxy_addr:
        if "://" not in proxy_addr:
            proxy_addr = "http://" + proxy_addr
    else:
        proxy_addr = None
    return proxy_addr


def generate_random_string(length: int) -> str:
    # 生成指定长度的随机串（大写字母 + 数字，用于访客标识等；非密码学安全）
    characters = string.ascii_uppercase + string.digits
    random_string = "".join(random.choices(characters, k=length))
    return random_string


def jsonp_to_json(jsonp_str: str) -> OptionalDict:
    # JSONP -> JSON 对象。re.DOTALL 支持跨行内容；回调名允许含点号（如 a.b(...)）
    pattern = r"([\w.]+)\((.*)\);?\s*$"
    match = re.search(pattern, jsonp_str, re.DOTALL)

    if match:
        _, json_str = match.groups()
        json_obj: dict[str, object] = cast(dict[str, object], json.loads(json_str))
        return json_obj
    else:
        raise Exception("No JSON data found in JSONP response.")


# 段级精确替换（该由 config_io._rewrite_line_by_match 下沉为此处唯一实现——utils.replace_url 与
# config_io.update_file 必须同一匹配口径，而 config_io 依赖 utils、反向导入会成环）。
# old_str 仅在「等于整行（去行尾换行与首尾空白后）」或「等于行内某个半角/全角逗号分隔段（strip 后）」
# 时才替换为 new_str；返回重写后的整行文本（保留原行尾与多逗号），未命中返回 None。
# 整行 str.replace 的旧写法在 URL 前缀重叠时（.../room1 与 .../room12）会把别的配置行静默改坏。
def rewrite_line_by_segment(text_line: str, old_str: str, new_str: str) -> str | None:
    raw = text_line.rstrip("\r\n")
    eol = text_line[len(raw) :]
    target = old_str.strip()
    if not target:
        return None
    # 整行匹配：raw.strip() 同时容忍首尾空白；两种命中形态都要 rstrip 掉 new_str 自带的
    # 换行，否则与补上的 eol 拼成双换行
    cleaned_new = new_str.rstrip("\r\n")
    if raw.strip() == target:
        return f"{cleaned_new}{eol}"
    # 段级匹配：按半角/全角逗号切分并保留分隔符。new_str 允许含逗号（"new_url,主播: 名称"），
    # 与原 substring 语义兼容，又不会误伤相似前缀行
    parts = re.split(r"([,，])", raw)
    hit = False
    for i in range(0, len(parts), 2):
        if parts[i].strip() == target:
            parts[i] = cleaned_new
            hit = True
    if not hit:
        return None
    return "".join(parts) + eol


def replace_url(file_path: str | Path, old: str, new: str) -> None:
    # 替换文件中的 URL：逐行段级精确匹配，避免子串替换误伤包含相同 URL 片段的其他行。
    # 本函数是花椒「地址失效自动注释」的唯一写盘路径（spider.py 直接调用），原先既不持
    # main.file_update_lock 也非原子写 → 与主循环热加载 / Web 面板原子写并发时 ① truncate 窗口内被
    # 读到空/半写文件（房间被误判已删除）、② Windows 上目标被 open("w") 持句柄会让对端 os.replace
    # 抛 PermissionError（那次注释就此丢失）、③ 两写方交错时后写者整体回退先写者的改动。
    # newline=""：读不翻译行尾、写回原样，避免一次替换把整份 URL_config.ini 的 CRLF 改成 LF。
    # 匹配口径从「整行相等才换、否则子串 replace」改为段级精确匹配（rewrite_line_by_segment）。
    # 旧口径的 elif `old in line` 是无边界子串替换——数字 ID 前缀重叠的两行（…/l/123456 与
    # …/l/1234567）在自动注释时会把兄弟房间整行换成「#短URL+长号尾巴」静默禁用。
    with _url_config_write_lock():
        try:
            with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError) as e:
            # 复用已在四语目录里的 "An error occurred: {masked}" 模板（新增模板须同步五处目录
            # 并重编译 .mo，收益不抵成本）；异常类型与路径按本仓「异常日志带类型与上下文」的
            # 硬约定拼进实参，路径过 mask_credentials（配置路径可能含用户目录名）。
            logger.warning(
                i18n.tr(
                    "An error occurred: {masked}",
                    masked=mask_credentials(f"读取配置文件失败，跳过 URL 替换: {type(e).__name__}: {e} in {file_path}"),
                )
            )
            return
        out_lines: list[str] = []
        for line in lines:
            rewritten = rewrite_line_by_segment(line, old, new)
            if rewritten is not None:
                # 末行无行尾时补 \n（与改前的 open("w") 写法语义一致，不引入新的差异形态）
                if not rewritten.endswith("\n"):
                    rewritten += "\n"
                out_lines.append(rewritten)
            else:
                out_lines.append(line)
        _ = atomic_write_text(file_path, "".join(out_lines), encoding="utf-8-sig")


def get_query_params(url: str, param_name: OptionalStr) -> dict[str, list[str]] | list[str]:
    # 取 URL 查询参数。**返回值与 spider.get_params 不同、不可互换**：本函数经 parse_qs 返回
    # list（param_name 为 None 时返回 dict[str, list[str]]，指定键时返回该键的**值列表**，
    # 键缺失是空 list）；spider.get_params 返回首个值的 str 或 None。调用方要单值时须自己取
    # [0] 并判空——把两者的返回形态互相套用会拿到 list 而非 str。
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)

    if param_name is None:
        return query_params
    else:
        values = query_params.get(param_name, [])
        return values


# 脱敏 URL / 代理地址中的凭据后再写日志：logs 下的日志会轮转保留多份，把带 user:pass 的代理地址
# 或带 signature/token 的直链直接写进去等于凭据长期落盘。只抹凭据，保留 host/path 与其余查询
# 参数以便定位问题。
# 2026-09-20 ：原实现只有「scheme://user:pass@」+「key=」两条正则，实测 9 条样本里
# cookie= / sid_guard= / ttwid= / `Authorization: Bearer …` / JSON 体 `"access_token": "…"` 全部
# 原样保留——根因是两条正则都要求字面 `=`，头形态与 JSON 形态永不匹配；且代理形态依赖 `://`，
# 配置里常见的无 scheme 写法 `user:pass@host:port` 不识别。现补齐三形态（查询串 / 请求头 /
# JSON 体）并扩充键名黑名单。
# 三形态共用的凭据键名黑名单（比较时统一小写，故此处全部小写书写）。
# 新平台出现新键名时只需在此加一条，三形态同时生效。
_SECRET_KEYS: tuple[str, ...] = (
    "signature",
    "sign",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "apikey",
    "api_key",
    "secret",
    "key",
    "x-bogus",
    "a-bogus",
    "a_bogus",
    "ms_token",
    "nonce",
    "sid",
    "sid_guard",
    "session",
    "sessionid",
    "session_id",
    "auth",
    "authorization",
    "proxy-authorization",
    "ticket",
    "pwd",
    "passwd",
    "password",
    "wssecret",
    "txsecret",
    "cookie",
    "set-cookie",
    "set_cookie",
    "ttwid",
    "verifyfingerprint",
    "verify_fingerprint",
    # 平台把复合键写成 camelCase（accessToken / wsAuth / msToken / verifyFp / idToken /
    # refreshToken / tk）。裸名 token/auth 的右半截前一位是字母（accessToken 的 token 前是 s），
    # 与下方驼峰分支之间存在盲区：黑名单若不含整段 camelCase 键名，只靠边界分支也匹配不到。
    # 故整段 camelCase 键名按小写形式入表。复核判据是「值确实消失」，见
    # tests/test_regression_utils.py::TestCamelCaseCredentialLeak::test_compound_keys_value_disappears。
    "accesstoken",
    "refreshtoken",
    "idtoken",
    "mstoken",
    "wsauth",
    "txauth",
    "verifyfp",
    "tk",
    "csrf",
    "csrftoken",
    "xsrf",
    "xsrftoken",
    # B 站主会话凭据与 CSRF 键、抖音 Cookie 会话键——四个键此前整体逃逸（query 形态实测
    # 原样返回）。`sessionid`/`sid` 已在表内但覆盖不到带后缀的变体（sessionid_ss 的 ss 前是 _、
    # sid_tt 同理，交替式要求整段命中），须按整段小写补录。复核判据是「值确实消失」，见
    # tests/test_utils.py::TestMaskCredentialsCoverage。
    "sessdata",
    "bili_jct",
    "sessionid_ss",
    "sid_tt",
    # 2026-10-21：报告实测逃逸的短键名与变体。
    # `sig`/`jwt` 是平台签名与令牌的最短常见写法（原表只有 signature/sign，sig 整体不命中）；
    # `sig_` 前缀变体（sig_time / sig_nonce）由 `sig` 命不中（下划线不在边界分支的允许集内），
    # 故按整段补录。复核语料见 tests/test_utils.py::TestMaskCredentialsCoverage::test_s07_*。
    "sig",
    "jwt",
    "sig_time",
    "sig_nonce",
    # ④：中文凭据键。config.ini 的 [账号密码]/[Authorization] 节与 Web 面板都可能出现中文键名，
    # 原表全为 ASCII 键，这些行整体逃逸。口径与 src/web_config.py 的敏感键判定对齐。
    "密码",
    "口令",
    "令牌",
    "授权码",
    "密钥",
    "秘钥",
    "会话",
    # 2026-10-30（M-10）：推送接口链接（钉钉/微信/bark）的值是含个人 key 的 URL——bark 形态把
    # key 放在路径段（https://api.day.app/<key>/…），无 key=value 可匹配，四形态全逃逸；消费点
    # 虽有 msg_push._mask_url(mask_last_segment=True) 补掩，但新消费点若只依赖 mask_credentials
    # 即漏。键名入表后由 ini 行形态整行掩值（复核语料 tests/test_utils.py::TestMaskCredentialsCoverage）。
    "接口链接",
)
# 长名排在前面：交替式虽会回溯，但「先试长名」明显减少无谓回溯（sid/sid_guard、token/access_token）。
# 短名（tk/key/nonce）不得把长名切碎——长名优先 + 右侧紧随的 `=`/`:`/`"` 字面量共同保证「先配长名」，
# 故排序口径必须保留。
_SECRET_KEY_ALT = "|".join(sorted(_SECRET_KEYS, key=lambda _k: (-len(_k), _k)))

# camelCase 边界分支。原实现三条形态的键名前只有左顾 (?<![A-Za-z0-9])，于是
# 「字母紧跟」的 camelCase 复合键被**整体**排除——accessToken 的 token 前是 s、wsAuth 的 auth
# 前是 s。斗鱼 getH5PlayV1 下发的流地址恒挂 `wsAuth`，每个房间每轮选源都会把可用的完整拉流
# 直链写进 logs/streamget.log（300KB 轮转保留多份）。修法两层、缺一即漏：① 已知驼峰键名的
# **整段小写形式**加入 _SECRET_KEYS；② 补这条「词内驼峰转折」边界分支，使尚未登记的新驼峰键
# 也能被裸名 token/auth 等命中。
# 为什么边界分支必须与 (?i) 分离：键名交替式需要大小写不敏感，但「小写字母紧跟大写字母」这一
# 判据在 (?i) 下会失效——(?i) 把 [A-Z] 折成 a-z，`design` 的 `s|i` 也会被当成驼峰转折，从而把
# 公开参数 design=2 抹成 design=***。故**不**在整条 pattern 上加 (?i)，而是给键名交替式套局部
# (?i:...)：边界断言保持大小写敏感、键名大小写不敏感。于是 design/presigned 天然不命中，而
# accessToken（s→T）、wsAuth（s→A）、msToken（s→T）、verifyFp（y→F）全部命中。
_SECRET_CAMEL_BOUNDARY = r"(?<=[a-z])(?=[A-Z])"
# 独立参数形态（键名前不是字母/数字）：my_token= / x-signature= / access_token= 由此命中
_SECRET_PLAIN_BOUNDARY = r"(?<![A-Za-z0-9])"
# 全小写「不透明前缀 + 凭据词」的第三个边界分支：mytoken= / apitoken= / 前缀 + key= 这类「词内但
# 无驼峰转折」的复合键。黑名单只登记了驼峰形式，此形态既不满足左顾（token 前是字母）也不满足驼峰
# 分支（无大写转折）→ 第三条漏抹路径。与驼峰分支一样**不设 (?i)**：全大写写法（MYTOKEN=）无小写
# 前缀、不属于本形态，由整段键名经左顾分支覆盖；若误加 (?i)，design 的 `sign` 会被误伤。
# 2026-10-21：候选集从 `token|key` 扩为加入 secret/signature/password/passwd/auth，
# 使 mysecret= / mysignature= / mypassword= / myauth= 这类复合键被覆盖。
# **刻意不加 `sign`**：`design=2` 与 `presigned=1` 是公开参数（tests/test_regression_utils.py
# 与 tests/test_utils.py 的反向棘轮都钉了「不得误抹」），而 "design" 的 "sign" 恰好落在本分支的
# 匹配位置上——加进去就会把它们抹成 de***/pre***。`sign=` 形态本身由 _SECRET_KEYS 里的整段键名
# 经左顾分支覆盖，所以不加进本分支并不构成缺口。
_SECRET_LOWER_COMPOUND_BOUNDARY = r"(?<=[a-z])(?=(?i:(?:token|key|secret|signature|password|passwd|auth)))"

# 形态一：查询串 key=value。键名前缀 = 三种边界之一；`(?:...)` 必须把两个边界整体包住再拼键名，
# 否则 `|` 作用域落到最外层会让键名成为可选、只剩 `=` 参与匹配（实测会把 https:// 整段抹成 ***）。
# 值只取到 & / 空白 / 引号 为止、**键名不动**——误抹只损失一个参数值，不破坏 URL 结构。
# (?i:...) 只包键名：边界断言不折大小写（理由见上方）。
_SECRET_QUERY_RE = re.compile(
    r"((?:(?:"
    + _SECRET_PLAIN_BOUNDARY
    + r"|"
    + _SECRET_CAMEL_BOUNDARY
    + r"|"
    + _SECRET_LOWER_COMPOUND_BOUNDARY
    + r")(?i:(?:"
    + _SECRET_KEY_ALT
    + r"))=))[^&\s\"']+"
)
# 形态二：请求头 Name: value（Authorization: Bearer xxx 这类值含空格，故整段抹到分隔符）。
# 键名前缀与形态一同构（同一组边界常量、同一 (?i) 包法）；值取到 , ; 引号 或行尾为止。
# 两条配套边界：① 独立参数分支**不得**追加 quote 排除——shell 命令串里的带引号 header
# （`--header "Authorization: Bearer X"`）键名前恰是引号，排除它会让 Bearer 值重新漏抹
# （tests/test_notify_script_guard.py 全组是这条的回归锁）；② 驼峰分支**不得**再叠
# `(?<![A-Za-z0-9"'])` guard——它与驼峰分支自身的 (?<=[a-z]) 在同一位置互斥，会让驼峰分支恒不
# 匹配（死代码），驼峰复合键（myToken: xxx）整值明文落日志。三分支与查询串形态**逐字同构**。
# 形态一之二：百分号编码的查询串（`…%3Ftoken%3DSECRET…`）。平台回跳参数（backurl/redirect_uri）
# 常把整段 URL 编码后塞进一个参数值，字面 `=` 判据一条也不命中，token/signature 因此明文进日志
# （CODE_REVIEW_2026-10-29 M-17 实测：`%3Ftoken%3DSECRETVALUE` 原样返回）。键名按明文匹配——
# 编码层只包住分隔符 `%3D`、键名本身未被编码；值取到下一个分隔符为止（值内若还有 %xx 会早停，
# 但前缀已整体抹掉，残余只能是编码后的尾部而不是可读口令）。键名前的分隔符也已被编码
# （`%3F` = ?、`%26` = &），末字符是字母，故不能复用 `_SECRET_PLAIN_BOUNDARY`——改为显式认
# 「编码分隔符」或非字母数字，两种前导形态。
_SECRET_ENCODED_BOUNDARY = r"(?:(?<![A-Za-z0-9])|(?<=%3[fF])|(?<=%26))"
_SECRET_ENCODED_QUERY_RE = re.compile(
    r"((" + _SECRET_ENCODED_BOUNDARY + r"(?i:(" + _SECRET_KEY_ALT + r"))%3[dD]))[^&%\s\"']+"
)
_SECRET_HEADER_RE = re.compile(
    r"((?:(?:"
    + _SECRET_PLAIN_BOUNDARY
    + r"|"
    + _SECRET_CAMEL_BOUNDARY
    + r"|"
    + _SECRET_LOWER_COMPOUND_BOUNDARY
    + r")(?i:(?:"
    + _SECRET_KEY_ALT
    + r"))\s*:\s*))[^,;\r\n\"']+"
)
# 形态三：JSON 体 "key": value（边界由闭合引号/字面量边界给出，最保守）。键名整体被
# 引号包裹，无需驼峰分支——(?i) 下 "accessToken" 与 "accesstoken" 同形，两侧引号使折大小写不产生
# design 那类误判。
# ③（CODE_REVIEW_2026-10-21）：值段原只认 `"字符串"`，平台以**数值**下发凭据（`{"ms_token": 12345}`、
# `{"token": 123}`、`{"sign": 1}`）时整条逃逸——报告实测三条语料全部原样返回。现值段扩为
# 字符串 / 数字（含负数与小数）/ true / false / null，与 JSON 标量全集对齐。
_SECRET_JSON_RE = re.compile(r'(?i)("(?:' + _SECRET_KEY_ALT + r')"\s*:\s*)("[^"]*"|-?\d+(?:\.\d+)?|true|false|null)')
# 形态四：ini 行 `键 = 值`（config.ini 的 [Cookie]/[Authorization]/[账号密码] 正是「键 空格 = 空格 值」）。
# ①（CODE_REVIEW_2026-10-21）：前三种形态都要求值紧跟在 `=`/`:` 之后或值被引号包住，而 ini 行的
# 值常含空格（`Authorization = Bearer xxx`）且后面直接到行尾 → 原实现整体逃逸。此处**只按行**抹到行尾：
#   · 锚定行首 `^` 且前缀限定为「不含 = 与 : 的短串」（≤40 字符），避免跨语句把日志后半段整段吞掉；
#   · 值后无分隔符约束（`.+` 到行尾），因为 ini 值允许空格。
# 该形态必须排在查询串之后：查询串已把 URL 里的 key=value 抹成 *** 时，本形态再抹一次是幂等的。
_SECRET_INI_LINE_RE = re.compile(
    r"(?im)^([ \t]*[^\r\n=:]{0,40}?(?i:(?:" + _SECRET_KEY_ALT + r"))(?:[(（][^\r\n=:]{0,20}[)）])?\s*=\s*)[^\r\n]*"
)
# ⑤（CODE_REVIEW_2026-10-30 M-10）：键名判据原先要求凭据词后紧跟 `\s*=`，基线模板真实键
# 「发件人密码(授权码)」（main.py 读取、SMTP 授权码）因「密码」后有括号尾缀整体逃逸（探针实测
# 原样返回）。现允许「凭据词 + 至多一段括号注释」再接 =。刻意不放开任意尾缀：那样 presigned=1
# （sign + 尾缀 "ed"）会被误抹，破坏 tests/test_utils.py 反向棘轮（test_lookalike_keys_are_not_swallowed）。
# 代理凭据：scheme://user:pass@host 与无 scheme 的 user:pass@host:port（配置项「代理地址」允许两种
# 写法，后者要过 handle_proxy_addr 才补前缀，故日志里常是裸串）
_PROXY_CREDENTIAL_RE = re.compile(r"(?i)(://)[^/@\s]+@")
_BARE_PROXY_CREDENTIAL_RE = re.compile(r"(?i)(?<![/\w.])[^\s/:@\"']+:[^\s/@\"']+@")


def mask_credentials(text: str) -> str:
    # 抹去代理凭据（scheme://user:pass@ 与 user:pass@host 两种形态）+ 三形态的凭据值。
    # 顺序无关（五类模式的匹配域互不重叠），但先做代理再做键值，可保证
    # "http://u:p@host/?token=x" 一条文本里两处凭据都被覆盖。
    #
    # 遗留（单列待办）：逐个调用点「记得过码」本身就是缺口——main.py 的直下失败日志与
    # PlayURL.log 源地址仍是裸流地址。治本是在 src/logger.py 注册 loguru patcher，对每条 record
    # 统一过一遍 mask_credentials；但那会改动 sink 行格式与若干按整行断言的用例，故另案处理。
    masked = _PROXY_CREDENTIAL_RE.sub(r"\1***@", text)
    masked = _BARE_PROXY_CREDENTIAL_RE.sub("***@", masked)
    # JSON 形态已改为「两段捕获」（值段不再单独捕获闭合引号），替换串随之从 \1***\3 变为 \1***。
    masked = _SECRET_JSON_RE.sub(r"\1***", masked)
    masked = _SECRET_HEADER_RE.sub(r"\1***", masked)
    masked = _SECRET_QUERY_RE.sub(r"\1***", masked)
    masked = _SECRET_ENCODED_QUERY_RE.sub(r"\1***", masked)
    # ①：ini 行兜底放最后——它按「行」整段抹到行尾，必须在前三形态把行内 key=value 处理完之后
    # 再兜一次（幂等），否则会先把 `x=1&token=y` 这种行整段吞掉、丢掉可读的定位信息。
    return _SECRET_INI_LINE_RE.sub(r"\1***", masked)
