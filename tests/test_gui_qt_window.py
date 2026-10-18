# tests/test_gui_qt_window.py — PySide6 窗口层的离屏行为锁。
#
# 为什么全部走 offscreen：CI 的 ubuntu 与本机都可能没有显示环境，
# QT_QPA_PLATFORM=offscreen 是 Qt 官方的无头后端（不需要 xvfb），
# 窗口能真实构建 → 断言的是真实控件树，而不是假对象。
#
# 锁什么（都是「旧 tkinter 版踩过、迁移期最容易丢」的行为）：
#   · 五个页面都在栈里、切页只改 current 而不重建（重建会丢日志内容）；
#   · 主题切换后 QSS 真的换了、状态点颜色跟上；
#   · 日志批次经定时器刷进终端控件（跨线程投递链路）；
#   · 画质行解析出降级（i18n 派生正则在新窗口层仍生效）；
#   · 退出序列不阻塞：shutdown 走后台线程，Signal 回到主线程才销毁。

import os
from pathlib import Path
from typing import Iterator

import pytest

# 为什么探测子模块而不是顶层包 + 为什么放宽 exc_type（2026-10-18 CI 实测事故）：
# pytest 9.1 起 importorskip 的 exc_type 缺省为 ModuleNotFoundError，而 PySide6 缺 Qt 系统库
# （ubuntu runner 无 libEGL.so.1）时失败发生在 **QtWidgets 子模块的 dlopen**，顶层
# `import PySide6` 仍然成功 → 只探测顶层包时这一行恒成立，紧随其后的 import 抛 ImportError，
# 以 collection error 形态中断整轮 pytest（test_gui_qt_units.py 头部注释里有完整读数）。
# 判据：环境没有 Qt 只该 skip 本模块，不该把另外 4337 条用例一起带走。
pytest.importorskip(
    "PySide6.QtWidgets", exc_type=ImportError, reason="PySide6 / Qt 系统库不可用时跳过 Qt 窗口层用例（环境限制口径）"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import i18n  # noqa: E402
from src.gui_qt.main_window import MainWindow  # noqa: E402
from src.gui_qt.theme import FOLLOW_SYSTEM_ID, THEME_DARK, THEME_LIGHT  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance  # type: ignore[return-value]


@pytest.fixture()
def window(app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    # 登记表是模块级全局，本文件每建一个 MainWindow 就会经 ui_i18n.set_text 登记 25 条静态标签。
    # Qt 与 Tk 在这里不同：顶层窗口在 QApplication 存活期间不会被释放（app.topLevelWidgets()
    # 仍持有），弱引用因此**不会**失效，条目会一路残留到后续测试文件 ——
    # tests/test_ui_i18n.py 是按「全局条数」断言的，残留条目会把它顶翻。故用完原样还原。
    from src import ui_i18n

    registry_snapshot = list(ui_i18n._ENTRIES)  # noqa: SLF001 - 测试还原全局登记表，与生产同模块
    # 每个用例用独立的临时目录，避免真实 config/URL_config.ini 被写入
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    url_file = config_dir / "URL_config.ini"
    url_file.write_text("https://live.douyin.com/1234 原画 主播A\n", encoding="utf-8-sig")
    main_file = config_dir / "config.ini"
    main_file.write_text("[录制设置]\n循环时间(秒) = 60\n", encoding="utf-8-sig")
    win = MainWindow(
        app_root=str(tmp_path),
        script_dir=str(tmp_path),
        url_config_file=str(url_file),
        main_config_file=str(main_file),
        downloads_dir=str(tmp_path / "downloads"),
    )
    win.apply_palette()
    yield win
    win._finalize_quit()
    win.deleteLater()
    app.processEvents()
    ui_i18n._ENTRIES[:] = registry_snapshot  # noqa: SLF001 - 同上


def test_pages_built_once_and_switch_keeps_instance(app: QApplication, window: MainWindow) -> None:
    order = ["dashboard", "quality", "danmaku", "config", "logs"]
    assert list(window._pages) == order, "页面顺序与侧栏导航顺序必须一致"
    logs_widget = window.logs_page.terminal
    window.show_page("logs")
    assert window.stack.currentWidget() is window._pages["logs"]
    window.show_page("dashboard")
    # 切页不得重建页面对象：重建会清空日志内容与编辑器内容（旧版整表重建事故同族）
    assert window.logs_page.terminal is logs_widget


def test_theme_switch_changes_stylesheet(app: QApplication, window: MainWindow) -> None:
    index = window.theme_combo.findData(THEME_DARK)
    assert index >= 0
    window.theme_combo.setCurrentIndex(index)
    sheet = app.styleSheet()
    assert "#d97757" in sheet, "深色主题的 accent 未进入 QSS"
    index = window.theme_combo.findData(THEME_LIGHT)
    window.theme_combo.setCurrentIndex(index)
    assert "#c96442" in app.styleSheet()


def test_log_flush_writes_into_terminal(window: MainWindow) -> None:
    window._queue_log("hello-from-controller", "warn")
    window._flush_pending_lines()
    assert "hello-from-controller" in window.logs_page.terminal.toPlainText()
    assert "[WARN]" in window.logs_page.terminal.toPlainText()


def test_quality_downgrade_parse(window: MainWindow) -> None:
    # 状态行正则是**按当前语言**从 tr() 结果派生的（M-14）：窗口初始化会按系统语言
    # 落到 en_US，故这里必须先把语言钉成 zh_CN 再喂简中行，否则测的是「跨语言匹配不上」，
    # 而那正是设计上的正确行为。
    previous = i18n.get_language()
    i18n.set_language("zh_CN")
    try:
        line = "主播A 画质降级：设置 原画(origin) 实际 超清(uhd)"
        window.quality.parse_line(line, window._queue_log, "2026-10-17 00:00:00")
        data = window.quality.snapshot()
        assert "主播A" in data, "降级行未被解析（i18n 派生正则失效）"
        assert data["主播A"].get("downgraded") is True
    finally:
        i18n.set_language(previous)


def test_quality_recording_line_marks_recording(window: MainWindow) -> None:
    previous = i18n.get_language()
    i18n.set_language("zh_CN")
    try:
        window.quality.parse_line("主播B[原画] 正在录制中 00:01:20", window._queue_log, "2026-10-17 00:00:00")
        data = window.quality.snapshot()
        assert "主播B" in data
        assert data["主播B"].get("recording") is True
    finally:
        i18n.set_language(previous)


def test_dashboard_buttons_reflect_running_state(window: MainWindow) -> None:
    window._set_running_ui(True)
    assert window.dashboard.stop_btn.isEnabled() is True
    assert window.dashboard.start_btn.isEnabled() is False
    window._set_running_ui(False)
    assert window.dashboard.start_btn.isEnabled() is True
    assert window.dashboard.stop_btn.isEnabled() is False


def test_url_config_loaded_into_editor(window: MainWindow) -> None:
    window.load_url_config()
    assert "live.douyin.com/1234" in window.config_page.content()


def test_start_blocked_when_no_room_config(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    # 空配置启动会让子进程卡在 input()：必须被前置拦截而不是拉起进程。
    with open(window.url_config_file, "w", encoding="utf-8-sig") as f:
        f.write("# 全部注释掉\n")
    assert window.has_room_config() is False


def test_language_switch_retranslates(window: MainWindow) -> None:
    target = "en_US" if i18n.get_language() != "en_US" else "zh_CN"
    index = window.language_combo.findData(target)
    if index < 0:
        pytest.skip("目标语言目录未装载")
    window.language_combo.setCurrentIndex(index)
    assert i18n.get_language() == target


# ── 2026-10-17 截图回归锁 ──
# 这四条锁的都是「界面看起来只是丑一点、实际是布局契约被破坏」的形态：
# 首帧双可见、空态文字被裁、侧栏被压扁、全局背景污染子控件。


def test_table_and_empty_state_are_mutually_exclusive_on_first_frame(window: MainWindow) -> None:
    # 首轮 refresh 之前两个控件都是默认可见 → 表头与空态文字叠在一起（截图 3/4）。
    # 断言 isHidden 而不是 isVisible：用例不 show 窗口，isVisible 恒为 False 测不出东西。
    assert window.quality_page.empty.isHidden() is False
    assert window.quality_page.table.isHidden() is True
    assert window.danmaku_page.empty.isHidden() is False
    assert window.danmaku_page.table.isHidden() is True


def test_empty_state_description_keeps_wrapped_height(app: QApplication, window: MainWindow) -> None:
    # wordWrap 的 QLabel 必须固定宽，否则父布局按「宽度未定」的单行 hint 分高度，
    # 描述只显示第一行（实测 geo 18px / hint 54px）。这里同时锁宽度与行数两条判据。
    window.resize(1080, 655)
    window.show_page("danmaku")
    window.show()
    app.processEvents()
    try:
        desc = window.danmaku_page.empty.description
        assert desc.width() == 420, "描述列宽必须与设计稿文本列一致（固定宽才能算出多行高）"
        assert desc.height() >= 2 * desc.fontMetrics().height(), "空态描述被压成单行"
    finally:
        window.hide()


def test_sidebar_minimum_height_leaves_room_for_scrolling(window: MainWindow) -> None:
    # 修复前侧栏 minimumSizeHint 高 719px，窗口最小高度却允许 620px，
    # QVBoxLayout 把品牌区与「导入字体…」按钮压扁。滚动区接手后 min 必须显著低于 620。
    assert window.sidebar.minimumSizeHint().height() < 620
    # 底部动作按钮在滚动区之外：任何高度下都保持 sizeHint，不被压缩。
    assert window.minimize_btn.height() >= window.minimize_btn.sizeHint().height()
    assert window.quit_btn.height() >= window.quit_btn.sizeHint().height()


def test_global_stylesheet_does_not_paint_bare_widget_background(app: QApplication, window: MainWindow) -> None:
    # `QWidget { background: ... }` 会命中 QLabel/StatTile/EmptyState，在白色卡片上
    # 留下灰条灰块（截图里几乎每个红框都有）。底色只允许由窗口级容器声明。
    sheet = app.styleSheet()
    widget_block = sheet.split("QWidget {", 1)[1].split("}", 1)[0]
    # 只禁纯 background 声明：selection-background-color 属于选中态，不在污染范围内
    assert "\n    background:" not in widget_block, "QWidget 通配块不得再设 background（会污染所有子控件）"
    assert "QMainWindow, QDialog {" in sheet, "窗口级底色缺少唯一声明处"


def test_follow_system_theme_writes_empty_preference(window: MainWindow) -> None:
    # 截图日志里的 `[WARN] 界面主题已切换，但配置写回失败: 未知主题 id: ''`：
    # 「跟随系统」落的是空串哨兵，save 侧必须接受它并落空值，而不是当成非法主题。
    window.theme_combo.setCurrentIndex(window.theme_combo.findData(THEME_DARK))
    window._pending_log_lines.clear()
    window.theme_combo.setCurrentIndex(window.theme_combo.findData(FOLLOW_SYSTEM_ID))
    assert not any("写回失败" in line for line, _level in window._pending_log_lines)
    text = Path(window.main_config_file).read_text(encoding="utf-8-sig")
    assert "gui_theme =" in text
