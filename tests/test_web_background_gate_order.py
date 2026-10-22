# -*- coding: utf-8 -*-
# M-18 回归锁：Web 面板「无认证 + 非回环」的安全拒绝必须发生在**任何 stdio 重定向 /
# 控制台隐藏之前**（被测：web.py::main 与 _enter_background_mode 的先后接线）。
#
# 为什么需要这条锁：web_show_console=false 时 _enter_background_mode() 会隐藏控制台窗口
# 并把 sys.stdout/sys.stderr 换成 logs/web_console.log 的文件流。检查若排在其后（曾经的
# 形态），四条拒绝文案全部落进日志文件、只留下 sys.exit(1) 的裸退出码——用户视角是
# 「控制台一闪、面板起不来」，既不知道被安全策略拦下、也不知道怎么放开。
# 顺序属纯接线问题：静态类型检查看不见，功能用例（起不起来服务）也看不见，只有把
# 「背景化」做成可观测的桩，才能在它被挪回检查之前时变红。
#
# 用例不打真服务、不联网：`import main` / `import uvicorn` / `from src.web_api import
# create_app` 三处都在拒绝路径**之后**才被真正使用，统一换成 sys.modules 替身；
# 而 read_web_config（取配置）与 is_loopback_bind_host（判据本体）走 src/web_config.py
# 的真实实现——在测试里重写这两段就等于假绿。

import ast
import io
import sys
import types
from pathlib import Path
from typing import Any

import pytest

import web

_REJECT_MARKER = "拒绝启动"
_INSECURE_MARKER = "严重安全警告"
_NON_LOOPBACK_HOST = "192.168.7.20"


class _BackgroundCalled(RuntimeError):
    # 正向对照（闸门放行）用的哨兵：web.main() 只有穿过安全闸门才会调用 _enter_background_mode，
    # 桩在此抛出即让函数停在「录制引擎线程 + uvicorn 创建」之前——那两段既非被测范围，
    # 也不该在测试里真起服务。
    pass


class _RecordingLogger:
    # web.py 经 `logger.warning(...)` 落安全告警。替身的两个用途：① 不把测试文本真写进
    # 仓库 logs/（loguru 的文件 sink 在 src.logger 导入期就已注册）；② 把告警文本暴露给
    # 断言——M-18 要求拒绝文案除控制台外还有一条日志留痕（pythonw / 冻结 console=False
    # 的窗口化入口 sys.stderr 为 None，print 全部落空）。
    def __init__(self, sink: list[str]) -> None:
        self._sink = sink

    def warning(self, message: object, *args: Any, **kwargs: Any) -> None:
        self._sink.append(str(message))


class _FakeEngineModule:
    # 代替 `main` 模块对象：web.main() 在安全闸门之前只读这四个路径属性
    # （config_file 是 read_web_config 的入参，script_path 决定 logs/ 落点）。
    # 其余属性/方法留到放行分支才有意义，这里给最小可调用形态即可。
    def __init__(self, root: Path, config_file: Path) -> None:
        self.script_path = str(root)
        self.config_file = str(config_file)
        self.url_config_file = str(root / "URL_config.ini")
        self.default_path = str(root / "downloads")
        self.recording_enabled = True

    def main(self, **kwargs: Any) -> None:
        return None

    def cleanup_all_ffmpeg_processes(self) -> None:
        return None


class _DriveResult:
    # 一次 web.main() 驱动的全部可观测面。
    def __init__(self) -> None:
        self.console = io.StringIO()  # 背景化**之前**的真实控制台替身
        self.redirected = io.StringIO()  # 背景化**之后**才存在的日志文件流替身
        self.background_calls: list[tuple[str, str, int]] = []
        self.warnings: list[str] = []
        self.error: BaseException | None = None


def _write_web_config(tmp_path: Path, host: str) -> Path:
    # web_show_console=false 是前提：只有关掉「显示控制台」，背景化才被排在拒绝路径之前执行；
    # web_auth_enable=false + 非回环 web_host 才触发闸门。web_minimize_to_tray=false 保证
    # 即便用例走进放行分支也不会去 import src.web_tray（pystray 需要托盘运行环境）。
    cfg = tmp_path / "config.ini"
    cfg.write_text(
        "[Web]\n"
        f"web_host = {host}\n"
        "web_port = 8000\n"
        "web_auth_enable = false\n"
        "web_show_console = false\n"
        "web_minimize_to_tray = false\n",
        encoding="utf-8",
    )
    return cfg


def _drive_web_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    host: str,
    allow_insecure_env: str | None = None,
) -> _DriveResult:
    res = _DriveResult()

    def fake_enter_background_mode(logs_dir: str, bg_host: str, bg_port: int) -> None:
        res.background_calls.append((logs_dir, bg_host, bg_port))
        # 复刻真实背景化的副作用（stdio 换成日志文件流）：这样一旦闸门被挪回背景化之后，
        # 拒绝文案会落进 res.redirected、res.console 变空，两条断言同时红。
        # 用 setattr 而非直接赋值：sys.stdout 在 typeshed 里是 TextIO，StringIO 不满足该声明。
        setattr(sys, "stdout", res.redirected)
        setattr(sys, "stderr", res.redirected)
        raise _BackgroundCalled

    cfg = _write_web_config(tmp_path, host)
    engine = _FakeEngineModule(tmp_path, cfg)

    monkeypatch.setitem(sys.modules, "main", engine)
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(Server=object, Config=object))
    monkeypatch.setitem(sys.modules, "src.web_api", types.SimpleNamespace(create_app=lambda **kwargs: None))
    monkeypatch.setattr(web, "logger", _RecordingLogger(res.warnings))
    monkeypatch.setattr(web, "_enter_background_mode", fake_enter_background_mode)
    monkeypatch.setattr(sys, "stdout", res.console)
    monkeypatch.setattr(sys, "stderr", res.console)
    if allow_insecure_env is None:
        monkeypatch.delenv("DOUYIN_WEB_ALLOW_INSECURE", raising=False)
    else:
        monkeypatch.setenv("DOUYIN_WEB_ALLOW_INSECURE", allow_insecure_env)

    try:
        web.main()
    except (SystemExit, _BackgroundCalled) as exc:
        # 不接 BaseException：KeyboardInterrupt 必须照常冒出去，否则 Ctrl+C 停不下测试会话。
        res.error = exc
    return res


def test_insecure_bind_rejects_before_any_stdio_redirect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    res = _drive_web_main(monkeypatch, tmp_path, host=_NON_LOOPBACK_HOST)

    exc = res.error
    assert isinstance(exc, SystemExit), f"预期安全拒绝退出，实际 {type(exc).__name__}: {exc}"
    assert exc.code == 1

    out = res.console.getvalue()
    # ① 拒绝文案到达的是**未被重定向**的 stdout/stderr（用户看得见的那一路）。
    assert _REJECT_MARKER in out
    assert _NON_LOOPBACK_HOST in out
    assert "DOUYIN_WEB_ALLOW_INSECURE=1" in out
    # ② 背景化（隐藏控制台 + 重定向 stdio）在拒绝路径上从未发生，日志流里一个字节都不该有。
    assert res.background_calls == []
    assert res.redirected.getvalue() == ""
    # ③ 除控制台外还留了一条 warning 日志（无控制台启动形态的唯一留痕）。
    assert any(_REJECT_MARKER in text for text in res.warnings)


def test_insecure_escape_hatch_warns_before_stdio_redirect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # DOUYIN_WEB_ALLOW_INSECURE=1 的破例路径同样整体前移了：⚠️ 告警必须在 stdio 被换掉
    # 之前打到控制台，否则「已把面板暴露到局域网」这件事在后台模式下只剩日志可查。
    res = _drive_web_main(monkeypatch, tmp_path, host=_NON_LOOPBACK_HOST, allow_insecure_env="1")

    assert isinstance(res.error, _BackgroundCalled), f"闸门应放行、走到背景化，实际 {type(res.error).__name__}"
    out = res.console.getvalue()
    assert _INSECURE_MARKER in out
    assert _REJECT_MARKER not in out
    assert res.redirected.getvalue() == ""
    assert res.background_calls  # 放行后才背景化
    assert any(_INSECURE_MARKER in text for text in res.warnings)


def test_loopback_bind_without_auth_still_backgrounds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 反向对照：闸门不得扩大打击面。回环绑定 + 未启用认证属正常配置，
    # 必须照常进入背景化（说明检查是「拒绝非回环」，不是「拒绝一切 web_show_console=false」）。
    res = _drive_web_main(monkeypatch, tmp_path, host="127.0.0.1")

    assert isinstance(res.error, _BackgroundCalled)
    assert _REJECT_MARKER not in res.console.getvalue()
    assert res.warnings == []
    assert res.background_calls == [(str(tmp_path / "logs"), "127.0.0.1", 8000)]


def _call_sites(fn: ast.FunctionDef) -> tuple[int, int, int]:
    # 返回 (闸门行, sys.exit 行, _enter_background_mode 调用行)。
    gate_line = exit_line = background_line = -1
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "_is_loopback_host" and gate_line < 0:
                gate_line = node.lineno
            elif isinstance(func, ast.Name) and func.id == "_enter_background_mode" and background_line < 0:
                background_line = node.lineno
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "exit"
                and isinstance(func.value, ast.Name)
                and func.value.id == "sys"
                and exit_line < 0
            ):
                exit_line = node.lineno
    return gate_line, exit_line, background_line


def test_security_gate_precedes_backgrounding_in_source() -> None:
    # 结构锁（与上面三条行为锁同向）：直接把「谁先谁后」钉在 AST 上。
    # 有人把检查挪回 _enter_background_mode 之后时，这条给出最直白的失败信息，
    # 不必从「控制台为空 + 背景化被调用」反推接线被改。
    source = Path(str(web.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"), None)
    assert fn is not None, "web.py 的入口函数 main 结构变化，本锁需同步"

    gate_line, exit_line, background_line = _call_sites(fn)
    assert gate_line > 0 and exit_line > 0 and background_line > 0, "找不到闸门判定/退出/背景化三个调用点"
    assert gate_line < background_line, "安全闸门必须早于 _enter_background_mode（stdio 重定向/隐藏控制台）"
    assert exit_line < background_line, "sys.exit(1) 必须早于 _enter_background_mode，否则拒绝文案不可见"
