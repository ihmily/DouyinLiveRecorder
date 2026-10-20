#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# DouyinLiveRecorder Web 管理面板入口
#
# 启动方式: python web.py
# 浏览器访问: http://localhost:8000
#
# 与 main.py 共用同一录制引擎（通过 import main 触发初始化），
# 在守护线程运行 main.main()；默认主线程运行 uvicorn，启用 Qt 系统托盘时反之
# ——主线程要让给 Qt 事件循环（QApplication 建在子线程会段错误，见 src/web_tray.py 文件头），
# uvicorn 改跑在守护线程。
import asyncio
import ctypes
import os
import signal
import sys
import threading
from datetime import datetime
from typing import TYPE_CHECKING, cast

import i18n
from src.logger import logger

if TYPE_CHECKING:
    import uvicorn

    from src.web_tray import WebConsoleTray

# 确保项目根在 sys.path
_script_dir = os.path.dirname(os.path.realpath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)


# 中文 Windows 控制台（尤其 PyInstaller 冻结后）stdout 默认 GBK 编码，
# 打印中文/emoji 会出现乱码，emoji（如警告符 ⚠）还会抛 UnicodeEncodeError 崩溃。
# 统一改为 UTF-8 输出，并把控制台代码页切到 65001，保证冻结后中文正常显示。
def _reconfigure_stream(stream: object) -> None:
    # 用 getattr 探测 reconfigure 是否存在（避免 isinstance 依赖具体类型、
    # 也避免将 Any 传入 hasattr），仅当为可调用时才执行。
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            _ = reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# kernel32/user32 DLL 句柄缓存为模块级单例：
# 1) 避免每次进入后台模式都重复加载（WinDLL 构造虽轻量但无意义）；
# 2) 保证同一进程内 argtypes/restype 声明只设置一次，行为一致；
# 3) 加载失败时 _KERNEL32/_USER32 仍为 None，后续调用会自动重试。
_KERNEL32: ctypes.CDLL | None = None
_USER32: ctypes.CDLL | None = None


# 加载 kernel32 DLL（WinDLL）并声明参数/返回类型，失败返回 None。
def _get_kernel32() -> ctypes.CDLL | None:
    global _KERNEL32
    if _KERNEL32 is not None:
        return _KERNEL32
    # 平台专属符号必须先用 sys.platform 字面量早返回（AGENTS.md「平台专属符号条目」约定）：
    # 否则 mypy --platform linux 会因 WinDLL 不存在于 Linux typeshed 而报 attr-defined，
    # 与非 Windows 运行期「AttributeError 被 except 吞掉返回 None」的结果一致，故行为不变。
    if sys.platform != "win32":
        return None
    # 用 ctypes.WinDLL 而非 ctypes.windll：后者在 3.14 仍可用但属遗留形态，AGENTS「Python 版本」条
    # 要求新代码统一 WinDLL（对齐本文件与 gui.py 的惯例）。
    # 显式声明 argtypes/restype：GetConsoleWindow 返回 HWND（64 位指针，避免被截断），
    # SetConsole*CP 返回 BOOL（明确 restype 为 c_int）。
    try:
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        dll.SetConsoleOutputCP.argtypes = [ctypes.c_uint]
        dll.SetConsoleOutputCP.restype = ctypes.c_int
        dll.SetConsoleCP.argtypes = [ctypes.c_uint]
        dll.SetConsoleCP.restype = ctypes.c_int
        dll.GetConsoleWindow.restype = ctypes.c_void_p
        _KERNEL32 = dll
        return dll
    except Exception:
        return None


# 加载 user32 DLL（WinDLL），失败返回 None。
def _get_user32() -> ctypes.CDLL | None:
    global _USER32
    if _USER32 is not None:
        return _USER32
    # 同 _get_kernel32：平台专属符号必须先 sys.platform 字面量早返回，行为不变（见该处注释）。
    if sys.platform != "win32":
        return None
    try:
        dll = ctypes.WinDLL("user32", use_last_error=True)
        dll.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        dll.ShowWindow.restype = ctypes.c_int
        _USER32 = dll
        return dll
    except Exception:
        return None


# 将标准输出/错误流重配置为 UTF-8，并在 Windows 下将控制台代码页设为 65001。
def _fix_encoding() -> None:
    _streams: list[object] = [getattr(sys, "stdout", None), getattr(sys, "stderr", None)]
    for _s in _streams:
        if _s is not None:
            _reconfigure_stream(_s)
    if sys.platform == "win32":
        try:
            _k32 = _get_kernel32()
            if _k32 is not None:
                # 两个调用均返回 BOOL（成功非 0）；失败不影响后续，返回值显式丢弃。
                _ = _k32.SetConsoleOutputCP(65001)
                _ = _k32.SetConsoleCP(65001)
        except Exception:
            pass


_fix_encoding()


# 进入后台模式：把 stdout/stderr 重定向到 logs/web_console.log，
# Windows 下另隐藏控制台窗口（SW_HIDE）、其他平台仅重定向输出；程序可经 Web 面板或任务管理器管理。

# web_console.log 的启动侧大小上限（L-01，2026-10-18 审查）。
# 为什么做在「启动侧」而不是「每次写入侧」：本文件与 src/log_archive.py 的
# `_rebind_web_console()` 共同维护的是**一只普通文件流**（追加 + 行缓冲），
# print() 与 loguru 的控制台 sink（`rebind_console_sink()` 绑定的就是 sys.stderr 这个对象）都写它。
# 改成写入侧轮转意味着换掉这只流对象，而 `log_archive._streams_bound_to()` 按
# 「sys.stdout/sys.stderr 的 .name 指向该文件」找句柄——换成包装对象或另开一只 loguru 文件 sink
# 都会让「停止录制时 flush+close+改名」那条链路认不出句柄（AGENTS「停止录制流程日志归档」硬约束），
# 故写入侧轮转需要 src/log_archive.py 同批改，不在本次范围。
# 为什么 loguru 的 rotation= 也救不了：loguru 0.7.3 实测对**流对象 sink** 直接抛
# `TypeError: add() got an unexpected keyword argument 'rotation'`（rotation 只对路径型 sink 生效），
# 而换成路径型 sink 会让 print 与 loguru 各持一只句柄、改名时必抛 PermissionError。
# 真正无界的形态因此只剩这一条：崩溃 / 强杀 / 断电等没走到 atexit 归档的退出把上一轮内容整份
# 留在原地，下一次后台化以 "a" 打开即在其后继续追加，归档链路对此完全无感。
# 上限取 2 MB、保留末尾 512 KB：本仓 loguru 文件 sink 的 rotation 量级是 300 KB，
# web_console 另要装 print 与 uvicorn 的访问输出，故取一个数量级更大的固定上限。
_WEB_CONSOLE_MAX_BYTES = 2 * 1024 * 1024
_WEB_CONSOLE_KEEP_BYTES = 512 * 1024

# Qt 托盘模式下 uvicorn 跑在守护线程：事件循环退出后给它这么长的收尾窗口。
# 超时即放弃等待、清理段照常执行（守护线程不会挡住进程退出），
# 但不给这段窗口的话，清理段（ffmpeg / 连接池）会落在 HTTP 请求处理中间。
_SERVER_JOIN_TIMEOUT = 10.0


# 超限则把 web_console.log 就地截断为末尾若干 KB，返回丢弃的字节数（0 = 无需处理）。
# 只在 `open(log_path, "a")` **之前**调用：此刻 sys.stdout/stderr 还是真实控制台、
# loguru 控制台 sink 也尚未 rebind，没有任何句柄握着这个文件——Windows 下对句柄未关的文件
# 做截断/改名必抛 PermissionError（AGENTS「停止录制流程日志归档」条）。
# 因此本函数的调用点不得挪到重定向之后，也不得顺手改上面那只流的打开参数
# （与 log_archive._rebind_web_console() 是「同参数」契约，那边只管归档后的重开）。
def _cap_web_console_log(log_path: str) -> int:
    try:
        size = os.path.getsize(log_path)
    except OSError:
        # 文件不存在（首次后台化）或取不到大小：按原样追加，与修复前逐字一致
        return 0
    if size <= _WEB_CONSOLE_MAX_BYTES:
        return 0
    try:
        with open(log_path, "r+b") as handle:
            _ = handle.seek(max(0, size - _WEB_CONSOLE_KEEP_BYTES))
            tail = handle.read()
            # 起点必须对齐到整行首：截断落在某行中间会留下一条半行——事后按行匹配的排查脚本
            # 读到的头一行是残缺内容，且半行也可能是被切断的多字节 UTF-8 序列。
            newline_at = tail.find(b"\n")
            if newline_at >= 0:
                tail = tail[newline_at + 1 :]
            else:
                # 末块连一个换行都没有（单条超长 print）：整块丢弃，上限优先于留痕
                tail = b""
            handle.seek(0)
            handle.truncate()
            _ = handle.write(tail)
        return size - len(tail)
    except OSError as e:
        # 截断失败绝不阻断后台化：日志继续追加也远好过面板起不来，但要留下一条可见告警
        print(i18n.tr("[web] web_console.log 超限截断失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
        return 0


def _enter_background_mode(logs_dir: str, host: str, port: int) -> None:
    log_path = os.path.join(logs_dir, "web_console.log")

    # 重定向前先向控制台输出提示（窗口即将隐藏）
    print("[web] 进入后台运行模式，控制台窗口将隐藏")
    print(i18n.tr("[web] 日志文件: {log_path}", log_path=log_path))
    print(i18n.tr("[web] 访问地址: http://{host}:{port}", host=host, port=port))
    _flush = getattr(sys.stdout, "flush", None)
    if callable(_flush):
        _ = _flush()

    # L-01：先按上限收拢历史，再开追加流（调用点顺序即判据，见 _cap_web_console_log）
    _dropped = _cap_web_console_log(log_path)
    if _dropped > 0:
        print(
            i18n.tr(
                "[web] web_console.log 已超过 {max_mb} MB 上限，丢弃最早的 {dropped_kb} KB",
                max_mb=_WEB_CONSOLE_MAX_BYTES // (1024 * 1024),
                dropped_kb=_dropped // 1024,
            )
        )

    # 重定向输出到日志文件（buffering=1 行缓冲，确保日志实时写入）
    log_stream = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = log_stream
    sys.stderr = log_stream
    # 关键：loguru 的控制台 sink 在 src.logger 导入期（main() 中 import main 时）就已绑定
    # 当时的 sys.stderr 对象，不会因这里的重新赋值而跟着变。不重建 sink，DEBUG/WARNING
    # 日志会全部写往随后被 SW_HIDE 隐藏的控制台窗口，web_console.log 里只剩 print 输出，
    # 排障时会把「日志没进来」误判成「事件没发生」。
    # 实测故障形态（2026-08 虎牙 403 排查）：因 web_console.log 无校验日志，「探针假绿」被误判成
    # 「探针未执行」——排查 Web 模式问题一律先看 logs/streamget.log / PlayURL.log（文件 sink
    # 不受此重定向影响、一直在正常写入）。
    try:
        from src.logger import rebind_console_sink

        rebind_console_sink()
    except Exception:
        pass

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'=' * 60}")
    print(i18n.tr("[{ts}] Web 管理面板进入后台运行模式", ts=ts))
    print(i18n.tr("控制台窗口已隐藏，访问地址: http://{host}:{port}", host=host, port=port))
    print(i18n.tr("日志文件: {log_path}", log_path=log_path))
    print("如需恢复控制台显示，请在 config.ini 设置 web_show_console = true 后重启")
    print(f"{'=' * 60}\n")

    # Windows: 隐藏控制台窗口（SW_HIDE = 0）
    if sys.platform == "win32":
        try:
            _k32 = _get_kernel32()
            _user32 = _get_user32()
            if _k32 is not None and _user32 is not None:
                # GetConsoleWindow.restype 已设为 c_void_p，返回值即句柄，无需再 cast。
                hwnd = _k32.GetConsoleWindow()
                if hwnd:
                    _user32.ShowWindow(hwnd, 0)
        except Exception:
            pass


# 判断给定 host 是否为回环地址（仅本机可访问）。
def _is_loopback_host(host: str) -> bool:
    # SEV-04：实现下沉到 src.web_config.is_loopback_bind_host，与 web_api 中间件的
    # 「每请求重跑非回环 + 无认证不变量」共用同一份判定口径。旧版是字符串精确比较，
    # 只认 127.0.0.1/localhost/::1/[::1] 四种写法，127.0.0.53 这类整段 127/8 会被算成
    # 「非回环」——两处口径一旦分叉，启动检查与运行期检查就会给出矛盾的结论。
    from src.web_config import is_loopback_bind_host

    return is_loopback_bind_host(host)


# uvicorn 服务线程体（仅 Qt 托盘占用主线程时使用）。
def _serve_forever(server: "uvicorn.Server") -> None:
    # 与主线程 asyncio.run(server.serve()) 同语义：serve() 内的 capture_signals() 检测到
    # 非主线程会直接跳过信号注册（uvicorn 0.54 起有该守卫），不会抛 ValueError。
    # 异常不吞：未捕获异常由 threading.excepthook 打到 stderr（已重定向进 web_console.log），
    # 比吞掉好定位；线程结束本身由托盘的看门狗感知并放开 Qt 事件循环。
    asyncio.run(server.serve())


# Ctrl+C 收尾（仅 Qt 托盘模式需要）：把信号从 uvicorn 手里接过来。
def _install_sigint_shutdown(server: "uvicorn.Server", tray: "WebConsoleTray") -> None:
    # 主线程跑 Qt 事件循环时 Ctrl+C 不再由 uvicorn 接管（见 _serve_forever 注释），
    # 需自己装 handler：置 should_exit 让 serve() 优雅返回，循环退出交给 run_event_loop
    # 的看门狗（服务线程结束即 quit）；第二次 Ctrl+C 才强制放开循环，不再等服务线程。
    state = {"count": 0}

    def _handler(_signum: int, _frame: object) -> None:
        state["count"] += 1
        server.should_exit = True
        if state["count"] > 1:
            tray.request_quit()

    signal.signal(signal.SIGINT, _handler)


# Web 管理面板入口：启动录制引擎守护线程与 uvicorn HTTP 服务。
def main() -> None:
    # 导入 main 模块：触发模块级初始化（FFmpeg 检查、配置读取、备份线程等），
    # 但不进入主循环（因 main() 已被包装为函数）。
    import uvicorn

    import main
    from src.web_api import create_app
    from src.web_config import read_web_config

    config_file = main.config_file
    url_config_file = main.url_config_file
    downloads_root = main.default_path
    logs_dir = os.path.join(main.script_path, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # 读取 Web 配置（提前读取以便决定是否隐藏控制台）
    web_cfg = read_web_config(config_file)
    host: str = cast(str, web_cfg["web_host"])
    port: int = cast(int, web_cfg["web_port"])

    # 不安全绑定防护（C1）：未启用认证时拒绝监听非回环地址，防止局域网内未授权访问
    # （文件下载/配置读写）。需显式设置环境变量 DOUYIN_WEB_ALLOW_INSECURE=1 才放行。
    # M-18（2026-09-29）确立的不变量：**安全拒绝必须发生在任何 stdio 重定向 / 控制台隐藏之前**。
    # 本块此前落在 `_enter_background_mode()` 之后，`web_show_console=false` 时执行到这里窗口
    # 已经 SW_HIDE、sys.stdout/sys.stderr 已经指向 logs/web_console.log，四条拒绝文案全部进了
    # 日志文件——用户视角只剩「控制台一闪、面板起不来」，必须翻日志才知道是被安全策略拦下。
    # 现整体前移到背景化之前；F-22（2026-09-12）要求的「保持在录制引擎线程与 uvicorn 创建之前」
    # 同时成立（本块仍早于二者，daemon 线程不会先读配置、初始化调度器，日志里不留
    # 「启动成功过」的假痕迹）。
    # [历史注] F-22 原注释自称此处「拒绝即零副作用退出」——已被证伪并改正：拒绝曾发生在背景化
    # 之后，「隐藏窗口」与「重定向 stdio」两项副作用已经落地。
    # 为什么不能更提前（仍在 `import main` 之后）：`read_web_config` 的入参 `main.config_file`
    # 由 main 的模块级 `_app_root()` 解析（冻结后指向 exe 同级目录），提前到 import 之前就拿不到
    # 与录制端同源的配置文件路径，只能另写一套路径推导（与「运行时资源与 exe 同级」约定分叉）。
    # 故「零副作用」收敛为可证且用户可见的口径：**无 stdio 副作用的拒绝**。
    # SEV-04：本检查只在启动瞬间评估一次，而面板写接口可热改 web_auth_enable / web_host，
    # 同款不变量现由 src/web_api.py 的鉴权中间件按**每个 /api/* 请求**重跑（判定口径与本处同源：
    # web_config.is_loopback_bind_host + 同一枚 DOUYIN_WEB_ALLOW_INSECURE 逃生阀），
    # 本处保留为「零副作用拒绝启动」的第一道。
    # （上行「零副作用」的准确口径见本块开头 M-18 注：可保证的是无 stdio 副作用。）
    if not web_cfg["web_auth_enable"] and not _is_loopback_host(host):
        allow_insecure = os.environ.get("DOUYIN_WEB_ALLOW_INSECURE", "").strip().lower() in ("1", "true", "yes")
        if not allow_insecure:
            _reject_msg = i18n.tr(
                "[web] ❌ 拒绝启动: 未启用 Web 认证时不允许监听非回环地址 ({host})。请二选一:", host=host
            )
            print(_reject_msg)
            print("      1. config.ini [Web] 节设置 web_auth_enable = true 并配置 web_password；")
            print("      2. 或设置 web_host = 127.0.0.1 仅限本机访问。")
            print("      如确需在无认证状态暴露到局域网，请设置环境变量 DOUYIN_WEB_ALLOW_INSECURE=1 后重启（不推荐）。")
            # M-18：文案此时已落到真实控制台；再补一条 warning 是为一类仍看不见的启动形态兜底——
            # pythonw.exe 与冻结 console=False 的窗口化入口 sys.stderr 为 None（见 AGENTS
            # 「无控制台环境 sys.stderr is None」条），print 直接落空，日志文件是唯一留痕；桌面双击
            # 启动时控制台随 sys.exit 立即销毁，用户无法回看。loguru 的**文件** sink 在 src.logger
            # 导入期就已注册，与本块先后无关；控制台 sink 的重建仍归 `_enter_background_mode`，
            # 顺序约束未动。
            try:
                logger.warning(_reject_msg)
            except Exception:
                pass
            sys.exit(1)
        # WD-07：破例路径把可被利用的具体能力列清楚并写入日志——用户照抄环境变量时至少知道
        # 自己在开放什么，也便于事后审计「这台机器何时以无认证方式对局域网开放过」。
        # [历史注] 2026-09-22 MIN-2247 前此处是未走 i18n 的裸多行字符串、直接作 logger.warning
        # 首参（违反「首参须为 tr 模板或常量」不变量）；现为单行模板、取值全部走 i18n.tr。
        _insecure_msg = i18n.tr(
            "[web] ⚠️ 严重安全警告: Web 面板正以「无认证 + 非回环地址」运行，能访问该地址的任何人可执行：\n"
            "① 读写全部配置（仅「自定义脚本执行命令」被禁止）；② 读取 logs 下的运行日志；"
            "③ 遍历并下载 downloads 下全部录制文件；④ 增删改直播间并可提交任意地址"
            "（存在被用作内网探测跳板的风险）；⑤ 启停录制。\n"
            "建议立即在 config.ini [Web] 节设置 web_auth_enable = true 并配置 web_password，"
            "然后删除环境变量 DOUYIN_WEB_ALLOW_INSECURE 并重启。\n"
            "另请注意（M-10）：绑定 0.0.0.0/:: 的远程部署下，写操作另受 Origin 同源校验约束——"
            "未在 config.ini 的 web_allowed_hosts 登记访问用主机名/IP 时，面板会「读得到、写不了」；"
            "该登记须手工编辑 config.ini 完成。"
        )
        print(_insecure_msg)
        try:
            logger.warning(_insecure_msg)
        except Exception:
            pass

    # M-18：背景化（隐藏控制台 + 重定向 stdout/stderr）必须在上面那道安全闸门**之后**——
    # 一旦执行到这里，后续任何拒绝/异常文案用户都只能翻 logs/web_console.log 才看得到。
    # 不得把 `_enter_background_mode` 挪回检查之前。
    if not web_cfg["web_show_console"]:
        _enter_background_mode(logs_dir, host, port)

    # Web 模式默认不自动开启录制：录制引擎线程保持运行（配置热加载/调度器就绪），
    # 但不拉起任何房间线程，由面板「开始录制」按钮经 POST /api/recording/toggle 手动触发。
    # CLI/GUI 直跑不受影响（recording_enabled 默认 True）
    main.recording_enabled = False
    recorder_thread = threading.Thread(
        target=main.main,
        name="recorder-engine",
        daemon=True,
        # non_interactive=True：URL_config 为空时跳过 input() 阻塞，避免守护线程在非交互环境下 EOFError 崩溃
        kwargs={"non_interactive": True},
    )
    recorder_thread.start()
    setattr(main, "_recorder_thread", recorder_thread)  # 供 get_status() 检测存活（I6）
    print(i18n.tr("[web] 录制引擎已在守护线程启动 (tid={ident})", ident=recorder_thread.ident))

    app = create_app(
        config_file=config_file,
        url_config_file=url_config_file,
        downloads_root=downloads_root,
        logs_dir=logs_dir,
        # SEV-N03 修复（2026-09-21，CODE_REVIEW_2026-09-21）：把**本进程实际要绑定的**地址与端口
        # 交给应用，供「非回环 + 无认证」不变量与 Origin 同源判定使用。二者此前读 config.ini 的
        # web_host/web_port，而这两个键本身可经 PUT /api/config 热改写（监听地址却要重启才变），
        # 于是判定基准可由请求方伪造。这里就是那条接线的唯一入口，删除它会让两道防线退回旧形态。
        bind_host=host,
        bind_port=port,
    )

    # uvicorn Server 实例（而非 uvicorn.run）：便于托盘「退出程序」通过设置
    # server.should_exit 触发优雅关闭，而非强制结束进程（避免 ffmpeg 残留）。
    #
    # MID-35：显式 proxy_headers=False。uvicorn 的默认值是 True 且
    # forwarded_allow_ips 默认含 127.0.0.1，于是它的 ProxyHeaders 中间件会在**本仓鉴权
    # 中间件之前**用请求头里 X-Forwarded-For 的**最左值**（完全由请求方自填）覆盖
    # scope["client"] —— 把面板包成 HTTPS 的常见本机反代部署下，
    # 「仅信任 web_trusted_proxy 的 XFF」这条防线直接失效：request.client.host 已是伪造值，
    # 攻击者每请求换一个键即可绕过 5 次/300s 的登录限流。关掉后 scope["client"] 恒为原始
    # socket 对端，XFF 的解释权收敛到 src/web_api.py::_get_client_ip 一处
    # （直连对端确属可信代理时才从右往左剥）。真实反代部署请把反代地址写进
    # config.ini [Web] web_trusted_proxy。
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info", proxy_headers=False))

    # 系统托盘：Windows 下将控制台窗口改为「最小化到托盘」而非任务栏。
    # start() 的返回值是契约（见 src/web_tray.py::start）：True = Qt 事件循环已占用主线程，
    # uvicorn 必须挪到守护线程；False = 已静默降级，主线程照旧跑 uvicorn。
    tray = None
    qt_owns_main_thread = False
    if web_cfg.get("web_minimize_to_tray", True):
        from src.web_tray import WebConsoleTray

        tray = WebConsoleTray(host=host, port=port, server=server)
        qt_owns_main_thread = tray.start()

    print(i18n.tr("[web] Web 管理面板启动中: http://{host}:{port}", host=host, port=port))
    # MID-2253（2026-09-22）：tr() 的**值参**不得是中文常量——模板 "[web] 认证: {web_auth_enable}"
    # 会被翻译，值不翻则 en_US 渲染成「Authentication: 开启」、中英混杂（中文下完全看不出）。
    # 值先各自 tr 取本地化字面量（两个新词条已合并进 i18n/ 四目录；控制台播报文案不涉及
    # 前端内嵌目录，无需同步 web/app.js）。也不能直接传裸布尔：{web_auth_enable} 会渲染成
    # True/False，比中文更不可读。
    _auth_text = i18n.tr("已启用") if web_cfg["web_auth_enable"] else i18n.tr("未启用")
    print(i18n.tr("[web] 认证: {web_auth_enable}", web_auth_enable=_auth_text))
    # 不安全绑定检查已上移至引擎线程启动之前（见上方 F-22 注释）
    # M-18（2026-09-29）追加：该检查现已同时上移到 `_enter_background_mode()` 之前，
    # 「拒绝文案必须在 stdio 被重定向之前落到真实控制台」这条顺序约束见该块开头注释。

    # 阻塞运行；托盘「退出程序」或 Ctrl+C 会将 should_exit 置真，serve() 优雅返回。
    # server.serve() 为 async 协程，必须用 asyncio.run 驱动事件循环真正运行，
    # 否则仅生成一个被丢弃的协程对象，Web 服务不会启动。
    # Qt 托盘模式下主线程要让给 Qt 事件循环（QApplication 建在子线程会段错误，
    # 实测见 src/web_tray.py 文件头），故 uvicorn 改跑在守护线程。
    server_thread: threading.Thread | None = None
    if qt_owns_main_thread:
        server_thread = threading.Thread(target=_serve_forever, args=(server,), name="uvicorn-server", daemon=True)
        server_thread.start()

    try:
        if qt_owns_main_thread and tray is not None:
            _install_sigint_shutdown(server, tray)
            tray.run_event_loop(stop_when=lambda: server_thread is not None and not server_thread.is_alive())
        else:
            asyncio.run(server.serve())
    finally:
        # 事件循环已退出（托盘「退出程序」/ Ctrl+C / Qt 自行退出）：先给服务线程一个收尾窗口，
        # 否则下面的 ffmpeg / 连接池清理会落在 HTTP 请求处理中间。
        if server_thread is not None:
            server_thread.join(_SERVER_JOIN_TIMEOUT)
        # 优雅关闭：serve() 正常返回或抛异常（如端口被占用）都执行清理，
        # 主动终止 ffmpeg 子进程并释放 HTTP 连接池，杜绝退出后残留孤儿进程。
        # M-01（2026-10-18 审查）：录后转码线程池的显式收尾必须排在 ffmpeg / 连接池清理**之前**，
        # 与本文件之外的两条既有退出链（main.safe_exit、main 磁盘满退出）同一口径、同一顺序。
        # 机理见 main.py::_shutdown_postprocess_executor 上方注释（ThreadPoolExecutor 的 worker
        # 是非守护线程，threading._register_atexit(_python_exit) 又晚于本仓三个 atexit 钩子登记，
        # 于是「池内 join」恒早于 ffmpeg 清理与日志归档，单个转封装任务上限 3600s）：Web 面板
        # 退出不经 safe_exit，此前完全没有人替主进程把顺序拿回来，表现为「点了退出长时间无响应、
        # 录制中的 ffmpeg 在这一小时里不被终止」。
        try:
            main._shutdown_postprocess_executor()
        except Exception as e:
            # 逐字复用 main.py::_shutdown_postprocess_executor 内部那条 msgid（不带 [web] 前缀、
            # 四目录已备译文）：退出链的同一件事不得各写一份文案，多一个键就多一处四目录漂移面
            print(i18n.tr("后处理线程池收尾失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
        try:
            main.cleanup_all_ffmpeg_processes()
        except Exception as e:
            # MID-2251 同族：清理失败只带 {e} 时，Windows 下 socket.timeout / TimeoutError
            # 的 str() 为空串，日志里只剩「[web] 清理 ffmpeg 进程失败: 」一行空白尾巴，
            # 分不清是进程已消失、权限不足还是挂在与 ffmpeg 的管道上。
            print(i18n.tr("[web] 清理 ffmpeg 进程失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
        try:
            from src.async_http import close_all_clients_sync

            close_all_clients_sync()
        except Exception as e:
            print(i18n.tr("[web] 清理 HTTP 连接池失败: {type_name}: {e}", type_name=type(e).__name__, e=e))

        # serve() 已返回（优雅关闭），收起托盘图标，进程随后正常退出。
        if tray is not None:
            tray.stop()


if __name__ == "__main__":
    main()
