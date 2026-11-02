#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 日志配置模块 - 基于 Loguru，控制台彩色输出 + 日志文件轮转存储

import configparser
import os
import sys
from contextvars import ContextVar
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    # 仅存根里存在的 TypedDict（loguru/__init__.pyi），运行时不可导入
    from loguru import Record

# 布尔配置解析（零依赖模块，import 它不会引入本仓其它模块，故不构成循环导入；
# logger.py 早于 main.py 执行、src/__init__.py 又以 .logger 形式先加载本模块，
# 因此这里只能依赖 src/config_bool.py，不能用 src/config_io.py 或 src/utils.py）
from src.config_bool import parse_config_bool

__all__ = [
    "logger",
    "rebind_console_sink",
    "child_process_env",
    "remove_file_sinks",
    "add_file_sinks",
    "ROOM_FIELD",
    "set_room_context",
    "get_room_context",
]

# GUI 父进程环境标记：gui.py 必须在导入任何 src 模块**之前**设置。GUI 进程只做面板展示与配置
# 管理、不执行录制，绝不能持有录制日志文件（logs/streamget.log / logs/PlayURL.log）的句柄：
# 双方双开同一文件时，任一方到达轮转阈值（rotation="300 KB"）都要先 os.rename 改名，而对方
# 句柄未关即抛 PermissionError WinError 32 —— 轮转永不成功、该进程的文件日志自此全量静默丢失，
# 且每条日志向 stderr 吐一段 Logging error（2026-08-29 实测：streamget.log 卡在 300031 字节）。
# 故 GUI 进程改为独占写 logs/gui.log（单进程单句柄、轮转安全）。
# 改名标记时必须同步两处：gui.py 的设置处与下方 child_process_env。
GUI_PARENT_ENV = "DLR_GUI_PARENT"

# 当前进程是否为 GUI 父进程：本模块在导入期求值，故 GUI 入口必须先设标记再导入 src。
# 判定走全仓唯一布尔入口 parse_config_bool：本仓布尔口径（关键约定 #9）认 是/true/t/yes/y/on/1。
# [历史注] 原手写 `== "1"` 会把 DLR_GUI_PARENT=TRUE / on / 是 判成「不是 GUI 父进程」，GUI 进程
# 照样双开录制日志文件，回到 GUI_PARENT_ENV 头注记录的轮转故障面。env 未设置时
# parse_config_bool(None, False) 仍返回 False，非 GUI 进程语义逐字不变。
_gui_parent = parse_config_bool(os.environ.get(GUI_PARENT_ENV), False)


def _app_root() -> str:
    # 返回应用程序根目录（exe 同级目录）：源码运行时为主脚本（sys.argv[0]）所在目录；冻结运行
    # （PyInstaller onedir + contents_directory='_internal'）返回 exe 所在目录，即 _internal 的父目录
    # ——src/ 及依赖包都在 _internal 里，而 config/ ffmpeg/ node/ 等运行时资源与 exe 同级，
    # 这样取值才能让它们在打包后被直接读写。
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.realpath(sys.executable))
    return os.path.split(os.path.realpath(sys.argv[0]))[0]


# 移除默认处理器
logger.remove()

# ==================== 房间日志关联字段（extra["room"]） ====================
# 多房间并发录制时所有房间线程共用同一条文件 sink，enqueue=True 下各房间的行按到达顺序交织
# 落盘，排障时切不出单个房间的链路（手写的 [record_name] 前缀只覆盖部分行）。房间线程的日志
# 调用点分散在 main.py 与 src/* 数十个模块，逐处 logger.bind() 不现实，故用 ContextVar 承载
# 「当前房间」，再由全局 patcher 写进 record["extra"]：
#   - ContextVar 与 logger.contextualize 同机制，取值按线程 / asyncio 任务隔离，房间线程内
#     asyncio.run() 创建的 Task 会复制上下文因而同样带标记；但**新建线程不继承**，弹幕采集线程、
#     转码线程池等仍需关键字辅助排查。
#   - patcher 在**调用线程**内、handler.emit（入队）之前执行，取到的必然是本线程的值，
#     不会被队列的消费线程串味。
# 默认值必须经 logger.configure(extra=...) 提供，**不可删**：未绑定房间的日志（主循环、GUI 进程、
# 弹幕采集线程、转码线程池）在格式里引用 {extra[room]} 时会 KeyError，loguru 不抛异常而是对
# **每一条**日志向 stderr 吐一段 "Logging error in Loguru Handler" 并丢弃该行——等于自造噪声 + 静默丢日志。
ROOM_FIELD = "room"
_room_var: ContextVar[str] = ContextVar("dlr_room_context", default="")


def set_room_context(room: str) -> None:
    # 绑定当前线程 / 任务的房间关联字段；传空串表示解绑（回到「未绑定」状态）
    _room_var.set(room or "")


def get_room_context() -> str:
    # 读取当前线程 / 任务绑定的房间值：供需要把日志归属到房间的旁路读取（如 Web/GUI
    # 侧把并发链路的问题归因到具体房间），也供用例直接断言线程隔离语义。
    return _room_var.get()


def _room_patcher(record: Record) -> None:
    # extra 里已有非空值 = 调用点显式 bind() / contextualize(room=...)，其优先级高于
    # 线程级兜底（patcher 在 extra 合并之后执行，不判断就会静默覆盖调用点绑定）。
    room = _room_var.get()
    if room and not record["extra"].get(ROOM_FIELD):
        record["extra"][ROOM_FIELD] = room


# configure(extra=...) 只重置默认 extra 字典，handlers 缺省时不动已注册 sink；
# 必须在任何引用 {extra[room]} 的文件 sink 注册之前生效，故置于导入期靠前位置。
logger.configure(extra={ROOM_FIELD: ""}, patcher=_room_patcher)

# 控制台日志格式（彩色）
custom_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> - <level>{message}</level>"

# 控制台 sink 的 handler id：供 rebind_console_sink() 在 stderr 被重定向后重建
_console_sink_id: int | None = None


# 控制台该不该着色：判定口径单点收敛到这里，导入期注册与 rebind_console_sink() 共用一份实现。
# 原形态是两处各写一份、导入期那份硬编码 colorize=True，于是 stderr 已被重定向到文件时
# （web.py 后台模式接走 logs/web_console.log、或 `python main.py > x.log` 之类手工重定向）
# ANSI 转义序列照样落进日志文件污染内容，而排障恰恰要看这个文件。getattr 兜底：无 isatty 的
# 重定向流（测试里的 StringIO、自定义转发对象）一律按非 tty 处理，不得改成裸 `sys.stderr.isatty()`。
def _console_colorize() -> bool:
    return bool(getattr(sys.stderr, "isatty", lambda: False)())


# 按当前 sys.stderr 建立/重建控制台 sink。loguru 的 sink 在 add() 时即绑定具体对象，**不会**因
# 之后 sys.stderr 被替换而跟着变。Web 后台模式（web.py::_enter_background_mode）在本模块导入
# 之后才把 sys.stdout/sys.stderr 重定向到 logs/web_console.log 并 SW_HIDE 隐藏控制台窗口——
# 不重建 sink 的话，全部 DEBUG/WARNING 仍写往已被隐藏的控制台，web_console.log 里只剩 print
# 输出，排障时会误判「没有日志 = 没有发生」（实测据此把「探针假绿」错判成「校验未执行」）。
def rebind_console_sink() -> None:
    global _console_sink_id
    if _console_sink_id is not None:
        try:
            logger.remove(_console_sink_id)
        except ValueError:
            # handler 已不存在（如调用方执行过 logger.remove()）：id 失效，忽略即可
            pass
        _console_sink_id = None
    if sys.stderr is None:
        return
    # 重定向到文件后不再着色：ANSI 转义序列会污染日志文本。与导入期那处共用 _console_colorize()，
    # 两处口径不会再各自漂移。
    _console_sink_id = logger.add(
        sink=sys.stderr, format=custom_format, level="DEBUG", colorize=_console_colorize(), enqueue=True
    )


# 构造录制子进程的启动环境：剔除 GUI 父进程标记（否则子进程同样被判为 GUI、不写录制日志
# 文件，录制日志将全量丢失），并固定子进程输出编码为 UTF-8。
# gui.py 拉起录制核心（main.py / 冻结 CLI exe）时必须经此函数，禁止直接透传 os.environ；
# base 传 None 时以当前进程环境为底。
def child_process_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    env.pop(GUI_PARENT_ENV, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# 控制台 sink 始终保留（与是否启用日志文件无关）。pythonw.exe 与 console=False 的冻结 exe 不分配
# 控制台，此时 sys.stdin/stdout/stderr **全为 None**；loguru 拒绝把 None 当 sink，裸写
# logger.add(sink=sys.stderr, ...) 会在模块导入期直接抛 TypeError: Cannot log to objects of type
# 'NoneType'，于是 gui.py（经 src.web_config → src.__init__ → node_install → logger 传导）在 import
# 期静默死亡——窗口化运行既无窗口也无报错。故此处先判空，无控制台时跳过、由下方文件 sink 兜底。
if sys.stderr is not None:
    # colorize 走 _console_colorize()：导入期同样可能发生在 stderr 已被重定向之后（例如被
    # `> file` 启动、或上层入口先重定向再 import src.logger），硬编码 True 会把 ANSI 转义序列写进
    # 日志文件。判空守卫（sys.stderr is None 时不加 sink）不得移除。
    _console_sink_id = logger.add(
        sink=sys.stderr, format=custom_format, level="DEBUG", colorize=_console_colorize(), enqueue=True
    )

# 运行时资源根目录（exe 同级：config/ logs/ downloads/ 等），
# 与 _app_root() 保持一致；冻结后指向 exe 父目录而非 _internal。
script_path = _app_root()

# 录制日志文件 sink 的 handler id：供停止录制归档流程（src/log_archive.py）
# 经 remove_file_sinks() 关闭句柄、add_file_sinks() 重建，导入期注册与运行期重建共用同参。
_streamget_sink_id: int | None = None
_playurl_sink_id: int | None = None


# 文件 sink 的行格式：房间字段固定在级别与位置之间，未绑定时该列为空——列结构恒定，才能按
# 「| 序号N 主播名 |」整段列匹配切出单房间链路。
_STREAMGET_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[room]} | {name}:{function}:{line} - {message}"
)
_PLAYURL_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {extra[room]} | {message}"


# 两个录制文件 sink 的分档口径（改任一处都要同步，排查链路靠它定位该看哪个文件）：INFO 级 →
# logs/PlayURL.log（直播流 URL 等用户可见进展），其余级别 → logs/streamget.log。两者同为
# retention=3、rotation="300 KB"、encoding="utf-8"、enqueue=True、serialize=False。
# 注意排查 Web 后台模式的问题一律先看这两个文件，web_console.log 只含 print 与控制台重定向内容。
# 注册 DEBUG 级文件 sink（排除 INFO），返回 handler id。
def _add_streamget_sink() -> int:
    return logger.add(
        f"{script_path}/logs/streamget.log",
        level="DEBUG",
        format=_STREAMGET_FORMAT,
        filter=lambda i: i["level"].name != "INFO",
        serialize=False,
        enqueue=True,
        retention=3,
        rotation="300 KB",
        encoding="utf-8",
    )


# 注册 INFO 级文件 sink（直播流 URL 等），返回 handler id。
def _add_playurl_sink() -> int:
    return logger.add(
        f"{script_path}/logs/PlayURL.log",
        level="INFO",
        format=_PLAYURL_FORMAT,
        filter=lambda i: i["level"].name == "INFO",
        serialize=False,
        enqueue=True,
        retention=3,
        rotation="300 KB",
        encoding="utf-8",
    )


# 移除并关闭录制日志文件 sink：loguru remove() 会先 flush enqueue 队列再关闭文件句柄，
# 保证归档改名前内容完整落盘。幂等：sink 未注册（GUI 父进程 / 配置关闭 / 已移除）时为 no-op。
def remove_file_sinks() -> None:
    global _streamget_sink_id, _playurl_sink_id
    if _streamget_sink_id is not None:
        try:
            logger.remove(_streamget_sink_id)
        except ValueError:
            pass
        _streamget_sink_id = None
    if _playurl_sink_id is not None:
        try:
            logger.remove(_playurl_sink_id)
        except ValueError:
            pass
        _playurl_sink_id = None


# 两个录制 sink **逐个独立**注册，id 只清各自的；第一个失败不阻止第二个尝试。
# [历史注] 曾同处一个 try/except OSError，第二个失败会把已注册 streamget 的 handler id 一并置
# None，该 sink 无法再经 remove_file_sinks() 关闭（Windows 下其归档改名自此永久 PermissionError，
# 归档链路对该文件失效）。
def _register_recording_sinks() -> None:
    global _streamget_sink_id, _playurl_sink_id
    if _streamget_sink_id is None:
        try:
            _streamget_sink_id = _add_streamget_sink()
        except OSError:
            _streamget_sink_id = None
    if _playurl_sink_id is None:
        try:
            _playurl_sink_id = _add_playurl_sink()
        except OSError:
            _playurl_sink_id = None


# 重新注册录制日志文件 sink（归档改名后恢复日志写入，loguru add() 即创建全新同名文件）。
# 与导入期注册同参数；GUI 父进程或「是否启用日志文件」关闭时不注册。
def add_file_sinks() -> None:
    global _streamget_sink_id, _playurl_sink_id
    if _gui_parent or not _log_to_file:
        return
    # 加异常兜底——本函数由日志归档流程在改名后调用，此处抛错会连带中断归档调用方，
    # 且失败原因只会出现在 stderr。OSError 的逐 sink 处理见 _register_recording_sinks。
    try:
        _register_recording_sinks()
    except OSError:
        # 降级为仅控制台：日志文件不可写不应阻断归档等业务流程
        _streamget_sink_id = None
        _playurl_sink_id = None


# 读取「是否将日志导出到 logs 文件夹」。本模块经 src.utils 被极早导入、早于 main.py 读配置，
# 故这里用 configparser 直接读 config.ini，不依赖 main.py 的执行顺序；默认启用以向后兼容。
_log_to_file: bool = True
try:
    _cfg_parser = configparser.RawConfigParser()
    _files_read = _cfg_parser.read(f"{script_path}/config/config.ini", encoding="utf-8-sig")
    # 取值口径与 main.py 统一（parse_config_bool：是/否、true/false、1/0、yes/no、on/off，
    # 大小写不敏感）。[历史注] 原实现是 `!= "否"`，false / 0 / no 会被判成「开启」，与 main.py
    # 的字典查表语义相反；空值与无法识别的值仍按 True（保留「仅显式否才关闭」的兼容行为）。
    _log_to_file = parse_config_bool(_cfg_parser.get("录制设置", "是否启用日志文件(是/否)"), True)
except configparser.NoSectionError, configparser.NoOptionError:
    # 配置项缺失时保持默认启用（向后兼容）
    pass
except Exception:
    # 任何读取异常都不应影响日志模块初始化
    pass

# 文件 sink 注册加异常兜底。logger.add(..., sink=路径) 在 delay=False（默认）时立即创建并
# 打开目标文件，logs/ 不可写（只读挂载、杀软占用、权限不足、路径被占为文件）时会在导入期直接抛
# OSError——而本模块经 src.utils 等被极早导入，等于**程序在导入阶段崩溃且没有任何日志可查**。
# 与上方「任何读取异常都不应影响日志模块初始化」同口径：失败时降级为仅控制台。
if _log_to_file:
    if _gui_parent:
        # GUI 父进程：仅写本进程独占的 gui.log（同款轮转/保留策略），绝不创建录制日志文件
        # streamget.log / PlayURL.log（双开句柄导致轮转失败的完整因果见 GUI_PARENT_ENV）。gui.log
        # 的行格式刻意不带 {extra[room]}：GUI 进程不执行录制，该列恒为空，加上去只会多一个永久空白栏。
        try:
            _ = logger.add(
                f"{script_path}/logs/gui.log",
                level="DEBUG",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
                serialize=False,
                enqueue=True,
                retention=3,
                rotation="300 KB",
                encoding="utf-8",
            )
        except OSError:
            # 落盘不可用：降级为仅控制台，绝不因日志文件问题阻断启动
            _log_to_file = False
    else:
        # 两个录制文件 sink 分档注册（INFO 与其余级别的口径见上方两个 _add_*_sink）
        # 逐 sink 独立注册（原因见 _register_recording_sinks 注释）
        _register_recording_sinks()
