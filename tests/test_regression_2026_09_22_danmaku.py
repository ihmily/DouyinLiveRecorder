# 2026-09-22 弹幕链路评审整改的回归锁（CODE_REVIEW_2026-09-22 的 SEV-2217 / MID-2245 / MID-2247）。
#
# 全部离线：websockets.connect 换成假上下文管理器（不触网），日志经临时 sink 捕获，监控枢纽的
# JSONL 边车写在 tmp_path 下，绝不碰仓库真实的 logs/ 目录。
#   ① SEV-2217：on_close / on_reconnect 的文案会同时进 loguru 文件 sink（logs/ 按 300KB 轮转保留
#      多份 = 长期落盘）与监控边车 JSONL（→ Web/GUI 面板）。InvalidProxy 文本自带代理原串（含
#      user:pass@host），故断言「凭据值在两处都消失」而非「调用了掩码函数」。on_reconnect 侧只记
#      一条 debug、自己不过码，只能由 ws_client 侧脱敏保住，故本用例走真实接线。
#   ② MID-2245：B站 _reject_auth 原先复用 WsClient.close()，而 close 置 _stopped 后 connect() 的两条
#      `if self._stopped: break` 出口都不回调 on_close → hub.room_closed() 永不发出，Web 弹幕页把
#      房间永久停在「已连接 / 0 条」。本用例从**真实解码路径**驱动它，不 stub _reject_auth。
#   ③ MID-2247：i18n 门禁（tests/test_i18n_migration.py）判据是 `node.func.value.id == "logger"`，
#      「别名 logger + f-string」对它完全隐形；这里补一条反向 AST 锁把该形态钉死为非法。

import ast
import asyncio
import json
import os
import types
from pathlib import Path
from typing import Any, cast

import pytest

import src.ws_client as ws_client_module
from src.collector import DanmakuCollector
from src.danmaku_monitor import DanmakuMonitorHub
from src.logger import logger
from src.platforms.bilibili import BilibiliDanmaku
from src.ws_client import WsClient

# 凭据样例：口令与账号都是**只在测试里出现的唯一 token**，断言它们在各类产物中消失即可
# 证明脱敏真的发生了（而不是断言「调用过 mask_credentials」）。
_PROXY_ACCOUNT = "danmakuProxyUser"
_PROXY_PASSWORD = "Sup3rDanmakuProxyPw"
_PROXY_ERROR_TEXT = f"http://{_PROXY_ACCOUNT}:{_PROXY_PASSWORD}@10.0.0.1:8080 isn't a valid proxy: handshake refused"


class _FlappingUnderlying:
    # 底层连接的极小替身：只提供 WsClient 需要的 close()/迭代（迭代即抛）。
    def __init__(self, exc: BaseException) -> None:
        self.closed = 0
        self._exc = exc

    async def send(self, data: Any) -> None:
        return None

    async def close(self) -> None:
        self.closed += 1

    def __aiter__(self) -> "_FlappingUnderlying":
        return self

    async def __anext__(self) -> bytes:
        raise self._exc


class _FailingCtx:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def __aenter__(self) -> _FlappingUnderlying:
        return _FlappingUnderlying(self._exc)

    async def __aexit__(self, *exc: Any) -> None:
        return None


def _install_always_failing_connect(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    # MID-66 口径：不 patch websockets 模块本体（会波及同进程其它用例的真实连接），
    # 只把 ws_client 命名空间里的全局名换成浅拷贝替身。
    shim = types.SimpleNamespace(**vars(ws_client_module.websockets))
    shim.connect = lambda *args, **kwargs: _FailingCtx(exc)
    monkeypatch.setattr(ws_client_module, "websockets", shim)


# ---------------------------------------------------------------------------
# ① SEV-2217：真实接线下凭据不得进日志 / 监控边车
# ---------------------------------------------------------------------------


def _room_connected(hub: DanmakuMonitorHub, room: str) -> bool | None:
    # 只读取快照里的 connected（None = 该房间不在枢纽中）。
    rooms: list[dict[str, Any]] = hub.snapshot()["rooms"]
    for entry in rooms:
        if entry.get("name") == room:
            return bool(entry.get("connected"))
    return None


async def test_proxy_credentials_absent_from_logs_and_monitor_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = tmp_path / "danmaku_monitor.jsonl"
    hub = DanmakuMonitorHub(log_path=str(sidecar))
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, BilibiliDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        room_name="房间A",
        platform_name="B站直播",
        write_srt=False,
        monitor=hub,
    )
    # 生产接线：bilibili.py 把 WsClient 的 on_close/on_reconnect 分别指向
    # DanmakuBase._on_close（collector 的回调）与 DanmakuBase._on_reconnect（只记 debug）。
    danmaku = BilibiliDanmaku(on_message=collector._on_message, on_close=collector._on_close)
    # 前置：hub.room_started 在真实链路里由 collector.start() 发出（本用例只关心关闭侧，
    # 不起采集线程）。room_closed 只更新**已登记**的房间，不登记就没有可断开的条目。
    hub.room_started("房间A", "B站直播")
    # room_connected 由 collector._on_ready 发出：先让房间处于「已连接」，
    # 才能证明关闭侧真的把它翻回断开（否则初值就是 False，断言毫无信息量）。
    hub.room_connected("房间A")
    assert _room_connected(hub, "房间A") is True
    _install_always_failing_connect(monkeypatch, ConnectionResetError(_PROXY_ERROR_TEXT))
    client = WsClient(
        url="ws://example.invalid/sub",
        on_message=lambda _d: None,
        on_close=danmaku._on_close,
        on_reconnect=danmaku._on_reconnect,
        heartbeat_interval=1000.0,
        max_reconnect=1,
        reconnect_interval=0.01,
    )

    lines: list[str] = []
    handler_id = logger.add(lambda message: lines.append(str(message)), level="DEBUG")
    try:
        await asyncio.wait_for(client.connect(), timeout=20.0)
    finally:
        logger.remove(handler_id)
    hub.flush()

    assert lines, "未捕获到任何日志，本用例的观察点失效（假绿）"
    sidecar_text = sidecar.read_text(encoding="utf-8") if sidecar.exists() else ""
    assert sidecar_text, "监控边车未落盘，本用例的观察点失效（假绿）"
    for text in lines + [sidecar_text]:
        assert _PROXY_PASSWORD not in text, f"凭据口令泄漏进产物: {text}"
        assert _PROXY_ACCOUNT not in text, f"凭据账号泄漏进产物: {text}"
    # 脱敏不是吞声：文案仍要能定位故障（代理原串仍在、只是凭据被换成 ***）
    assert any("***@" in text for text in lines), f"日志里看不到脱敏后的代理串: {lines}"
    assert any("isn't a valid proxy" in text for text in lines)
    assert "***@" in sidecar_text
    # 配对信号仍在：collector._on_close 必须把房间标记为已断开（否则 MID-2245 的观感回归）
    assert _room_connected(hub, "房间A") is False, "on_close 未把房间从「已连接」翻回断开"


def test_collector_on_close_masks_unmasked_reason(tmp_path: Path) -> None:
    # collector 侧那道「兜底」的独立锁：上游若是**其它**平台实现（不经 WsClient），
    # 传进来的裸凭据文案也必须被拦在日志与边车之前。
    sidecar = tmp_path / "monitor.jsonl"
    hub = DanmakuMonitorHub(log_path=str(sidecar))
    collector = DanmakuCollector(
        danmaku_cls=cast(Any, BilibiliDanmaku),
        danmaku_args={},
        base_filename=str(tmp_path / "video"),
        segment_seconds=None,
        room_name="房间B",
        platform_name="B站直播",
        write_srt=False,
        monitor=hub,
    )
    lines: list[str] = []
    handler_id = logger.add(lambda message: lines.append(str(message)), level="DEBUG")
    try:
        collector._on_close(f"代理不可用: http://{_PROXY_ACCOUNT}:{_PROXY_PASSWORD}@10.0.0.1:8080")
    finally:
        logger.remove(handler_id)
    hub.flush()

    assert len(lines) == 1, f"关闭回调应只留一条日志: {lines}"
    sidecar_text = sidecar.read_text(encoding="utf-8") if sidecar.exists() else ""
    for text in lines + [sidecar_text]:
        assert _PROXY_PASSWORD not in text and _PROXY_ACCOUNT not in text, f"兜底脱敏未生效: {text}"
    assert "***@" in lines[0] and "***@" in sidecar_text


# ---------------------------------------------------------------------------
# ② MID-2245：认证被拒必须经 on_close 上报（真实解码路径驱动）
# ---------------------------------------------------------------------------


async def test_reject_auth_reports_close_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.spider as spider

    closes: list[str] = []
    invalidated: list[int] = []
    monkeypatch.setattr(spider, "invalidate_bili_buvid_cache", lambda: invalidated.append(1))

    underlying = _FlappingUnderlying(ConnectionResetError("unused"))
    client = WsClient(url="ws://example.invalid/sub", on_message=lambda _d: None, on_close=closes.append)
    cast(Any, client)._ws = underlying
    danmaku = BilibiliDanmaku(on_message=lambda _m: None, on_close=closes.append, on_ready=lambda: None)
    danmaku._ws = client

    # 真帧：16B 大头序帧头 + AUTH_REPLY（operation=8, code=-100），protover=0 不解压。
    # 走 decode_message → _decode_packet → _reject_auth，全程不打桩被测逻辑。
    frame = BilibiliDanmaku._encode(json.dumps({"code": -100}), action=8)
    danmaku.decode_message(frame)
    for _ in range(3):  # _reject_auth 经 ensure_future 投递 fail()，让出几轮跑到
        await asyncio.sleep(0)

    assert invalidated == [1], "buvid 缓存失效链被改动（前置行为）"
    assert danmaku._stopped is True
    assert underlying.closed == 1, "被拒后必须关闭底层连接"
    assert len(closes) == 1, f"on_close 应恰好上报一次（MID-2245 前为 0 次）: {closes}"
    assert "认证" in closes[0] and closes[0].strip(), f"reason 文案不可读: {closes[0]!r}"


async def test_ws_client_fail_is_idempotent_and_masks_reason() -> None:
    closes: list[str] = []
    underlying = _FlappingUnderlying(ConnectionResetError("unused"))
    client = WsClient(url="ws://example.invalid/sub", on_message=lambda _d: None, on_close=closes.append)
    cast(Any, client)._ws = underlying

    await client.fail(f"进房认证被拒: 经 http://{_PROXY_ACCOUNT}:{_PROXY_PASSWORD}@10.0.0.1:8080")
    await client.fail("第二次不应再上报")

    assert client._stopped is True
    # 底层连接的 close 可重复（websockets 自身幂等），本用例锁的是「on_close 只投一次」
    assert underlying.closed >= 1, "fail() 未关闭底层连接"
    assert len(closes) == 1, f"on_close 被重复投递: {closes}"
    assert _PROXY_PASSWORD not in closes[0] and _PROXY_ACCOUNT not in closes[0]
    assert "***@" in closes[0]


# ---------------------------------------------------------------------------
# ③ MID-2247：反向 AST 锁——禁止「别名 logger」，禁止任何 logger 绑定收 f-string 文案
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
# 与 pyproject 各工具排除列表同源（AGENTS「排除目录归一化」条目）
_SCAN_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        "node",
        "ffmpeg",
        "downloads",
        "logs",
        "build",
        "dist",
        "backup_config",
        "recordings",
        "typings",
        ".workbuddy",
        ".mimosa",
        ".qoder",
        ".agents",
        ".pnpm-store",
        ".npm-cache",
        ".dsh-validation",
        ".ego-browser-test",
        ".plugin-src",
        ".tmp-dps-extract",
        ".v2c",
    }
)
# 只查「首参是消息」的 loguru 级别方法；add() 的首参是 sink 路径、log() 的首参是级别，
# 两者出现 f-string 都是正常写法（src/logger.py 即如此），纳入判定只会造出假违规。
_LOG_MESSAGE_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical", "success", "trace"})


def _scanned_python_files() -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(_REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in _SCAN_EXCLUDED_DIRS]
        for name in names:
            if name.endswith(".py") or name.endswith(".pyi"):
                files.append(Path(root) / name)
    return sorted(files)


def _is_logger_module(module: str) -> bool:
    # 三种写法都要认：`from loguru import logger`、`from src.logger import logger`，以及相对导入
    # `from .logger import logger`——AST 里后两者的 node.module 分别是 "src.logger" 与 **"logger"**
    # （level=1 不并进 module）。漏掉最后一种就对 src/ws_client.py 等九个模块的 logger 完全失明。
    return module in {"loguru", "logger"} or module.endswith(".logger")


def _loguru_bindings(tree: ast.Module) -> set[str]:
    # 收集「绑定到 loguru logger 的名字」——含 `from loguru import logger as _log`、
    # `from .logger import logger as X`、`from src.logger import logger` 等全部形态。
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _is_logger_module(node.module):
            for alias in node.names:
                if alias.name == "logger":
                    names.add(alias.asname or alias.name)
    return names


def _alias_offenders(source: str) -> list[str]:
    offenders: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _is_logger_module(node.module):
            for alias in node.names:
                if alias.name == "logger" and alias.asname:
                    offenders.append(f"{node.lineno}: {node.module} logger as {alias.asname}")
    return offenders


def _callee_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _message_is_interpolated(node: ast.AST) -> bool:
    # 判据与 MID-68 收紧后的不变量①一致：首参**子树**中存在含 FormattedValue 的 JoinedStr。
    # 唯一收敛处仍是 tr() 的模板位——约定②（格式说明符由调用方预先求值后作实参传入）本就允许
    # tr(...) 实参位写 f-string，一并判违规会把本仓推荐写法打成回归。形参取 ast.AST 而非
    # ast.expr：本函数按子树递归，iter_child_nodes 会产出 ast.arguments/keyword 等非 expr 节点。
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(value, ast.FormattedValue) for value in node.values)
    if isinstance(node, ast.Call):
        if _callee_name(node.func) == "tr":
            return _message_is_interpolated(node.args[0]) if node.args else False
        return False
    for child in ast.iter_child_nodes(node):
        if _message_is_interpolated(child):
            return True
    return False


def _fstring_offenders(source: str) -> list[str]:
    tree = ast.parse(source)
    bindings = _loguru_bindings(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _LOG_MESSAGE_METHODS:
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id not in bindings:
            continue
        if node.args and _message_is_interpolated(node.args[0]):
            offenders.append(f"{node.lineno}: {node.func.value.id}.{node.func.attr}(f-string)")
    return offenders


def test_repo_python_file_scan_is_not_silently_empty() -> None:
    # 自检之一：排除表若写错（例如误把 src 整目录排除），下面两条锁会在「零文件」上假绿。
    files = _scanned_python_files()
    assert len(files) > 50, f"扫描到的 Python 文件过少（{len(files)}），排除表可能把源码整目录漏掉了"
    assert any(p.name == "ws_client.py" for p in files), "src/ws_client.py 不在扫描面上"


def test_no_aliased_loguru_logger_binding_anywhere() -> None:
    # MID-2247 的形态锁：全仓不得给 logger 起别名（`from loguru import logger as _log`）。
    # 别名会同时绕过 i18n 门禁与这条锁要防的 f-string 组合，是「门禁绿但没查」的入口。
    offenders: list[str] = []
    for path in _scanned_python_files():
        try:
            source = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        offenders.extend(f"{path.relative_to(_REPO_ROOT)}:{item}" for item in _alias_offenders(source))
    assert offenders == [], f"存在别名 logger（MID-2247 回归）: {offenders}"


def test_no_interpolated_fstring_passed_to_any_logger_binding() -> None:
    offenders: list[str] = []
    for path in _scanned_python_files():
        try:
            source = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        offenders.extend(f"{path.relative_to(_REPO_ROOT)}:{item}" for item in _fstring_offenders(source))
    assert offenders == [], f"logger 收到 f-string 文案（翻译在查表前完成）: {offenders}"


def test_ws_client_does_not_import_loguru_directly() -> None:
    # 本文件的整改落点单独钉一次：统一走 src/logger.py 的项目 logger。
    source = (_REPO_ROOT / "src" / "ws_client.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "loguru" not in modules, f"ws_client 又直接 import 了 loguru: {sorted(modules)}"
    # 相对导入 `from .logger import logger` 在 AST 里是 module="logger" + level=1
    assert modules & {"logger", "src.logger"}, f"ws_client 未使用项目 logger: {sorted(modules)}"


def test_alias_and_fstring_detectors_actually_see_the_bad_forms() -> None:
    # 防门禁自身假绿（仿 test_gate_predicate_sees_concatenated_fstring 的做法）：
    # 检测器必须认出「别名 logger + f-string」，同时不得把约定② 的推荐写法判成违规。
    bad = "from loguru import logger as _log\n_log.warning(f'心跳超时 {v:.0f}s')\n"
    concat = "from loguru import logger as _log\n_log.warning(f'心跳超时' + (f'{v}s' if v else ''))\n"
    # 相对导入形态：AST 里 node.module 是 "logger"（level 另计），检测器若只认
    # "xxx.logger" 就会对 src/ws_client.py 这类项目 logger 完全失明
    relative = "from .logger import logger\nlogger.warning(f'心跳超时 {v:.0f}s')\n"
    good = (
        "import i18n\nfrom .logger import logger\n"
        "logger.warning(i18n.tr('心跳超时 {seconds}s,关闭连接以触发重连', seconds=f'{v:.0f}'))\n"
    )
    assert _alias_offenders(bad), "别名检测器对最简形态失明"
    assert _fstring_offenders(bad), "f-string 检测器对别名形态失明"
    assert _fstring_offenders(concat), "f-string 检测器看不见拼接形态（MID-68 同族盲区）"
    assert _fstring_offenders(relative), "f-string 检测器对相对导入的项目 logger 失明"
    assert _alias_offenders(good) == []
    assert _fstring_offenders(good) == [], "把约定②（实参位预求值 f-string）误判为违规"
