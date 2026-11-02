# tests/test_regression_root_entries.py —— CODE_REVIEW_2026-10-18 根目录入口修复的回归锁。
#
# 覆盖 L-01：web.py::_cap_web_console_log —— 后台模式启动侧把超限的 logs/web_console.log
# 就地截断为末尾若干 KB（起点强制对齐整行首），失败只留痕不阻断后台化。
#
# 全部离线：不起 Web 服务、不联网；产物一律 tmp_path。打桩边界：只替换两个体积阈值常量，
# 截断、对齐、返回值三段逻辑一律走 web.py 真实实现。
#
# 原 L-02（legacy tkinter GUI 退出链的 PID 复用防线）已随该实现退役删除；窗口层的进程清理
# 回归锁在 tests/test_gui_qt_units.py。

import ast
from pathlib import Path
from typing import Any

import pytest

import web

# web.py 的导入期副作用只有 _fix_encoding()（就地 reconfigure 宿主 stdio）：模块顶层导入即落在
# pytest 收集期、早于 conftest 的函数级 stdio 快照，与 tests/test_web_background_gate_order.py 同形态。


# ---------------------------------------------------------------------------
# L-01：web_console.log 的启动侧大小上限


def _set_limits(monkeypatch: pytest.MonkeyPatch, *, max_bytes: int, keep_bytes: int) -> None:
    # 体积阈值常量注入小值，免得为「超限」一格真写 2 MB+ 的文件（AGENTS 允许打桩的就是这类
    # 阈值/时间常量；截断、对齐、返回值三段逻辑一律走 web.py 真实实现）
    monkeypatch.setattr(web, "_WEB_CONSOLE_MAX_BYTES", max_bytes)
    monkeypatch.setattr(web, "_WEB_CONSOLE_KEEP_BYTES", keep_bytes)


def test_cap_web_console_log_leaves_under_limit_file_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 形态①：未超限 → 返回 0 且文件逐字节不动（首次后台化 / 正常轮次不得被「收拢」误伤）
    path = tmp_path / "web_console.log"
    original = b"line one\nline two\n"
    path.write_bytes(original)
    _set_limits(monkeypatch, max_bytes=len(original), keep_bytes=4)
    assert web._cap_web_console_log(str(path)) == 0
    assert path.read_bytes() == original, "未超限时一个字节都不许动"


def test_cap_web_console_log_drops_oldest_and_starts_at_line_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 形态②：超限 → 丢弃字节数 = 原大小 − 余量、余量不高于 keep、留下的必须从整行首开始
    # （起点落在某行中间会留下半行：事后按行匹配的排查脚本首行读到残缺内容，
    # 且被切断的多字节 UTF-8 序列会连解码都一起坏掉）
    lines = [f"L{i:03d} 一行\n".encode() for i in range(10)]
    original = b"".join(lines)
    size = len(original)
    line_len = len(lines[0])
    # 让「保留窗口的起点」正好落在第 4 行中间（size − keep = 3×行宽 + 2），
    # 于是对齐整行首这件事有活可干：不实现对齐的话，首行就是残缺的 L003 半行
    keep_bytes = size - (3 * line_len + 2)
    path = tmp_path / "web_console.log"
    path.write_bytes(original)
    _set_limits(monkeypatch, max_bytes=size // 2, keep_bytes=keep_bytes)

    dropped = web._cap_web_console_log(str(path))
    kept = path.read_bytes()
    assert dropped == 4 * line_len, f"起点未对齐到整行首（丢 {dropped}，应丢 {4 * line_len} = 前 4 整行）"
    assert dropped == size - len(kept), f"返回值与实删字节数不一致: 返回 {dropped} / 实删 {size - len(kept)}"
    assert len(kept) <= keep_bytes, f"余量超过 keep 上限: {len(kept)} > {keep_bytes}"
    assert kept == original[4 * line_len :], "留下的内容不是原文件的整行后缀 → 丢的不是最早的整段"
    assert kept.startswith(lines[4]), f"首行不是从整行首开始（残缺头一行会污染按行匹配）: {kept[:20]!r}"


def test_cap_web_console_log_drops_whole_block_without_newline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 形态③：保留窗口内一个换行都没有（单条超长 print）→ 整块丢弃、余量归 0，
    # 上限优先于留痕（不得为「留一行」而把半行留在文件头）
    original = b"x" * 50
    path = tmp_path / "web_console.log"
    path.write_bytes(original)
    _set_limits(monkeypatch, max_bytes=20, keep_bytes=10)
    assert web._cap_web_console_log(str(path)) == 50
    assert path.read_bytes() == b""


def test_cap_web_console_log_missing_file_returns_zero_without_creating_it(tmp_path: Path) -> None:
    # 形态④：文件不存在（首次后台化）→ 返回 0，且**不得**顺手创建这只文件
    # （创建即把「归档链路按 .name 找句柄」的契约提前绑到一个空文件上）
    path = tmp_path / "web_console.log"
    assert not path.exists()
    assert web._cap_web_console_log(str(path)) == 0
    assert not path.exists(), "取不到大小时不得创建文件"


def test_cap_web_console_log_failure_is_reported_and_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 截断失败绝不阻断后台化（日志继续追加也远好过面板起不来），但必须留下一条可见告警，
    # 且返回 0 让调用方不去打「已丢弃 N KB」那句结论。
    # 判据只问「有没有留痕 + 文件是否原样 + 返回值」，不钉告警文案（M-26：文案会漂，字面锁会空转）。
    original = b"y" * 50
    path = tmp_path / "web_console.log"
    path.write_bytes(original)
    _set_limits(monkeypatch, max_bytes=20, keep_bytes=10)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise OSError(13, "Permission denied")

    # raising=False：web.py 里 `open` 是内建名、不是模块全局，替身只能以「新增全局名」的形态
    # 遮蔽到内建查找之前（teardown 由 monkeypatch 直接删掉这个新增名，不留残留）
    monkeypatch.setattr(web, "open", _boom, raising=False)
    assert web._cap_web_console_log(str(path)) == 0
    assert path.read_bytes() == original, "截断失败后不得留下半截内容"
    assert capsys.readouterr().out.strip() != "", "失败必须留痕（静默即等于把故障伪装成正常）"


def test_console_log_cap_is_called_before_the_append_stream_opens() -> None:
    # 调用点契约：截断必须早于 `open(log_path, "a")`。此刻 sys.stdout/stderr 还是真实控制台、loguru
    # 控制台 sink 也尚未 rebind，没有任何句柄握着这只文件；挪到重定向之后，Windows 下对未关句柄的
    # 文件做截断必抛 PermissionError，而这条链路完全静默，只有结构锁看得见。
    tree = ast.parse(Path(web.__file__).read_text(encoding="utf-8"), filename=str(web.__file__))
    fn = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_enter_background_mode"
        ),
        None,
    )
    assert fn is not None, "web.py 里找不到 _enter_background_mode，本判据失去基准（不得当成通过）"
    cap_at: int | None = None
    open_at: int | None = None
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        called = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if called == "_cap_web_console_log":
            cap_at = node.lineno if cap_at is None else min(cap_at, node.lineno)
        elif (
            called == "open"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "a"
        ):
            open_at = node.lineno if open_at is None else min(open_at, node.lineno)
    assert cap_at is not None, "_enter_background_mode 里没有 _cap_web_console_log 调用（上限防线被摘）"
    assert open_at is not None, "_enter_background_mode 里找不到追加流 open(..., 'a')，判据失去基准"
    assert cap_at < open_at, f"截断调用（第 {cap_at} 行）没有早于追加流打开（第 {open_at} 行）"
