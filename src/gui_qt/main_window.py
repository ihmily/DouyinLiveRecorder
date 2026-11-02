# -*- coding: utf-8 -*-
# 主窗口：侧边栏 + 顶栏 + 五个页面 + Toast。
#
# 为什么跨切面逻辑都在这里：页面只管 widget 与渲染，子进程生命周期、配置文件的跨进程冲突、
# 主题/语言/缩放的运行态切换、退出序列必须有唯一拥有者，否则同一件事在两处各实现一遍会随
# 时间漂移。分法是「单窗口协调器 + 纯 widget 页面」。
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from typing import cast

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import i18n
from src.config_bool import parse_config_bool
from src.config_read import tolerant_config_parser, warn_duplicate_options
from src.logger import logger
from src.ui_fonts import (
    SUPPORTED_FONT_SUFFIXES,
    install_font_file,
    load_font_file_preference,
    load_font_preference,
    save_font_preference,
)
from src.ui_i18n import T, retranslate_all, set_text
from src.ui_icons import (
    GUI_ICON_KEY,
    GUI_SECTION,
    MAX_ICON_BYTES,
    SUPPORTED_ICON_SUFFIXES,
    current_icon_path,
    install_icon_file,
    load_icon_preference,
    save_icon_preference,
    validate_icon_bytes,
)
from src.ui_scale import (
    AUTO_SCALE_ID,
    SCALE_PRESETS,
    auto_scale_for_screen,
    load_scale_preference,
    save_scale_preference,
)

# 主题 ID 与「跟随系统」的判定复用 src/ui_theme（config.ini [GUI] gui_theme 的读写事实源），
# 显示名用本包自己的 THEME_LABELS，避免窗口层反向依赖共享层的展示文案。
from src.ui_theme import THEME_IDS, detect_system_appearance, load_theme_preference, save_theme_preference
from src.web_config import parse_url_config, update_config_line

from . import theme as theme_module
from .danmaku_monitor import DanmakuMonitor
from .pages.config import ConfigPage
from .pages.danmaku import DanmakuPage
from .pages.dashboard import DashboardPage
from .pages.quality import QualityPage

# 模块名刻意不是 logs.py：pyproject 的 [tool.mypy].exclude 里有裸名 `logs`（它本意是
# 排除运行期产物目录 logs/），裸名做子串匹配会让 `src/gui_qt/pages/logs.py` 在无参 mypy
# 下被静默漏查——tests/test_run_gates.py::test_mypy_exclude_never_shadows_source_files
# 就是守这条的（改名是它期望的修法，收紧 exclude 会影响别的平台/目录形态）。
from .pages.runlog import LogsPage
from .quality_monitor import QualityMonitor
from .recorder import RecorderController
from .settings_dialog import AdvancedSettingsDialog
from .shared import config_change_verdict, normalize_editor_text, read_config_snapshot, save_text_to_file
from .theme import FOLLOW_SYSTEM_ID, THEME_LABELS, palette
from .tray import TrayIcon
from .widgets import ArrowComboBox, StatusDot, Toast, action_button, connect_click, nav_button

# 周期链间隔（毫秒）：与旧版逐值对齐（日志 200 / 状态 3s 有录制、10s 空闲 / 弹幕 1s）。
_LOG_FLUSH_INTERVAL = 200
_STATUS_INTERVAL_ACTIVE = 3000
_STATUS_INTERVAL_IDLE = 10000
_DANMAKU_INTERVAL = 1000
# 三条周期链的异常留痕限频窗口（秒，M-15）：持续故障逐次落日志会刷满日志页，
# 完全静默又让编程错误不可见。
_CHAIN_WARN_INTERVAL_SECONDS = 30.0


class MainWindow(QMainWindow):
    # 退出清理完成后请求销毁窗口：回调来自工作线程，必须经 Signal 回到主线程，
    # 跨线程排队封送由 Qt 框架保证（旧版需要自管事件泵）。
    shutdownFinished = Signal()
    # M-11：任意线程都能往日志缓冲里追加，但「启动刷新定时器」这一步只能在主线程做
    # （QTimer 跨线程 start() 会被 Qt 拒绝：Timers cannot be started from another thread）。
    # 于是本信号承担「有新日志」的投递，槽函数在主线程里启表。
    logQueued = Signal()

    def __init__(
        self,
        *,
        app_root: str,
        script_dir: str,
        url_config_file: str,
        main_config_file: str,
        downloads_dir: str,
    ) -> None:
        # 五条路径由 app.py 在入口层解析（冻结包走 _internal 回退）后传入，
        # 这里不做二次推断：路径判定的唯一事实源应该只有一处，否则两处会各自漂移。
        super().__init__()
        self.app_root = app_root
        self.script_dir = script_dir
        self.url_config_file = url_config_file
        self.main_config_file = main_config_file
        self.downloads_dir = downloads_dir

        self._palette = palette(theme_module.THEME_LIGHT, 1.0)
        self._theme_follow_system = True
        self._scale_follow_system = True
        # M-80：_resolve_initial_theme_and_scale 产出的最终缩放百分数（供下拉启动回填），
        # 100 只是「尚未解析」的占位。
        self._initial_scale_percent = 100
        self._selected_font_family = ""
        self._font_file_pref = ""
        self._imported_font_families: list[str] = []
        # 导入的托盘 / 窗口图标路径（空 = 用内置 assets/app.ico，仍缺失则回落到 Qt 默认）
        self._icon_file_pref = ""

        self._quitting = False
        self._chain_warn_at: dict[str, float] = {}
        self._pending_log_lines: list[tuple[str, str]] = []
        self._nav_buttons: dict[str, QPushButton] = {}
        self._pages: dict[str, QWidget] = {}
        self._advanced_dialog: AdvancedSettingsDialog | None = None
        self._status_cache: tuple[str, str] | None = None
        self._status_cache_mtime = 0.0
        self._url_disk_snapshot: str | None = None
        self._url_last_mtime = 0.0
        # M-12：冲突框是模态的，模态事件循环期间状态链定时器照旧触发，
        # 这个重入守卫保证「一次外部改动最多问一次」。
        self._url_conflict_asked = False
        # S-01：结束动作有两条投递通道（停止工作线程的 ended 信号 + 读线程的 EOF 哨兵），
        # 手动停止时两条都会到达，按会话号去重才不会打两遍结束日志。
        self._finish_handled_session: int | None = None
        self._config_baseline = ""
        self.tray: TrayIcon | None = None

        self.recorder = RecorderController(url_config_file, app_root, script_dir)
        self.quality = QualityMonitor()
        self.danmaku = DanmakuMonitor(os.path.join(app_root, "logs", "danmaku_monitor.jsonl"), self._queue_log)

        self._resolve_initial_theme_and_scale()
        self._build_ui()
        # M-80：偏好下拉的启动回填点（必须在 _build_ui 之后——下拉是它建的）。
        self._sync_pref_combo_positions()
        self._wire_recorder()
        self._start_timers()
        self._setup_tray()
        # 图标必须在托盘建好之后才应用：托盘图标由 TrayIcon 持有，窗口图标另走 QApplication，
        # 两者同源于本调用（窗口图标在托盘不可用时同样要生效）。
        self._apply_icon_preference()

        self.load_url_config()
        self._apply_language_preference()
        self.refresh_status()

    # ─── 构建 UI ───

    def _build_ui(self) -> None:
        # 侧栏定宽、顶栏定高、内容区自适应：272/52 是设计稿的固定值，
        # 缩放只作用于圆角与间距，不改这两条骨架尺寸（否则小屏上侧栏会挤掉内容）。
        self.setWindowTitle("DouyinLiveRecorder")
        central = QWidget()
        central.setObjectName("content")
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = self._build_sidebar()
        shell.addWidget(self.sidebar)

        main_col = QVBoxLayout()
        main_col.setContentsMargins(0, 0, 0, 0)
        main_col.setSpacing(0)
        main_col.addWidget(self._build_topbar())
        self.stack = QStackedWidget()
        self._build_pages()
        main_col.addWidget(self.stack, 1)
        shell.addLayout(main_col, 1)

        self.toast = Toast(central)

        width, height, min_w, min_h = self._resolve_window_size()
        self.resize(width, height)
        self.setMinimumSize(min_w, min_h)

    def _build_sidebar(self) -> QFrame:
        # 导航、偏好、退出三件事只放在侧栏一处：顶栏刻意只留页标题与状态胶囊。
        # 同一动作（主题切换、退出）在两处各开一份入口，随时间必然走向两套实现。
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(theme_module.SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        brand_row = QHBoxLayout()
        self.brand_logo = QLabel("🎬")
        logo_font = QFont(self.brand_logo.font())
        logo_font.setPointSize(20)
        self.brand_logo.setFont(logo_font)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        self.brand_name = QLabel("DouyinLiveRecorder")
        brand_font = QFont(self.brand_name.font())
        brand_font.setWeight(QFont.Weight.DemiBold)
        self.brand_name.setFont(brand_font)
        self.brand_sub = QLabel(i18n.tr("直播录制 · 控制台"))
        # M-14：副标题是构建期定型的静态标签（品牌名 DouyinLiveRecorder 是专有名词、不译），
        # 登记键与构造标签同一 msgid，切语言后由 retranslate_all() 回填。
        set_text(self.brand_sub, T("直播录制 · 控制台"))
        self.brand_sub.setObjectName("muted")
        brand_text.addWidget(self.brand_name)
        brand_text.addWidget(self.brand_sub)
        brand_row.addWidget(self.brand_logo)
        brand_row.addLayout(brand_text)
        layout.addLayout(brand_row)

        # 状态胶囊：设计稿 .history-item.active 的取值（微深底 + 8px 圆角）
        pill = QFrame()
        pill.setObjectName("pill")
        pill_row = QHBoxLayout(pill)
        pill_row.setContentsMargins(12, 8, 12, 8)
        self.sidebar_dot = StatusDot(pill, base=10)
        self.sidebar_status = QLabel(i18n.tr("未运行"))
        pill_row.addWidget(self.sidebar_dot)
        pill_row.addWidget(self.sidebar_status)
        pill_row.addStretch(1)
        layout.addWidget(pill)

        layout.addSpacing(6)
        # 导航与偏好设置放进滚动区：两者合计最小高度实测 719px，而窗口最小高度允许 620px，
        # 不设滚动时 QVBoxLayout 会把品牌区与「导入字体…」按钮一起压扁（2026-10-17 截图）。
        # 滚动区自身 minimumSizeHint 很小，高度不足由它吸收；品牌区与底部按钮留在区外。
        scroll = QScrollArea()
        scroll.setObjectName("sidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        pane = QWidget()
        pane_layout = QVBoxLayout(pane)
        pane_layout.setContentsMargins(0, 0, 0, 0)
        pane_layout.setSpacing(10)
        for page_id, msgid in (
            ("dashboard", "📊  控制台"),
            ("quality", "🎯  画质监控"),
            ("danmaku", "💬  弹幕监控"),
            ("config", "📝  URL 配置"),
            ("logs", "📋  运行日志"),
        ):
            btn = nav_button(i18n.tr(msgid))
            # M-14：导航按钮是构建期定型的静态标签，此前只在建时 tr() 一次，切语言后停在旧语言。
            # 登记键与构造标签同一 msgid（构造值就是 T(msgid) 的当前语言渲染），两处不漂移；
            # 顶栏页标题按这里的 text() 派生，重定向登记后由 _repopulate_static_texts 重取。
            set_text(btn, T(msgid))
            btn.clicked.connect(lambda _checked=False, pid=page_id: self.show_page(pid))
            pane_layout.addWidget(btn)
            self._nav_buttons[page_id] = btn

        # 弹性空白留在滚动区内：窗口够高时导航仍贴顶、设置在下方；
        # 高度不足时它先被压成 0，滚动条接手，而不是压缩控件本身。
        pane_layout.addStretch(1)
        pane_layout.addLayout(self._build_sidebar_settings())
        scroll.setWidget(pane)
        layout.addWidget(scroll, 1)

        # 构造标签与 T() 必须用同一个 msgid：set_text 在建立后立刻回填，两处写法不一致时
        # 启动期与每次 retranslate_all() 都会把构造期的带 emoji 标签覆盖成 T() 的裸文本（emoji 丢失）。
        # 三空格形态是与 Tk 遗留实现共用的既有目录键，不新增条目。
        self.minimize_btn = action_button("📥   最小化到托盘")
        set_text(self.minimize_btn, T("📥   最小化到托盘"))
        self.quit_btn = action_button("❌   彻底退出", "danger")
        set_text(self.quit_btn, T("❌   彻底退出"))
        connect_click(self.minimize_btn, self.minimize_to_tray)
        connect_click(self.quit_btn, self.quit_application)
        layout.addWidget(self.minimize_btn)
        layout.addWidget(self.quit_btn)
        return sidebar

    # 侧栏底部的偏好设置：主题 / 缩放 / 语言 / 字体（2 列分文本+控件，与上版本同信息密度）。
    def _build_sidebar_settings(self) -> QVBoxLayout:
        grid = QVBoxLayout()
        grid.setSpacing(6)

        def add_setting(caption: str, combo: QComboBox) -> None:
            # M-14：说明标签是构建期定型的静态标签——caption 收**源 msgid**（调用点不再预 tr），
            # 由 set_text 建时查表 + 登记重译；下拉里的选项文本属哨兵/动态面，
            # 由 _repopulate_static_texts 按当前语言重建（那里有注释说明为什么不进登记表）。
            label = QLabel()
            set_text(label, T(caption))
            label.setObjectName("dim")
            font = QFont(label.font())
            font.setPointSize(9)
            label.setFont(font)
            # 下拉最小宽度必须与「最长选项文本」解耦：「简体中文 (Simplified Chinese)」会把
            # minimumSizeHint 撑到 302px，滚动区 setWidgetResizable 时整块内容被撑宽、右侧
            # 54px 被水平裁掉。固定按 8 个字符算，超长项由 QComboBox 自己省略显示。
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            # 组间 4px 呼吸：grid.setSpacing(6) 对「说明→下拉」和「下拉→下一组说明」
            # 是同一个值，四组连排时看不清归属（截图里 caption 像贴在上一个下拉底边）。
            grid.addSpacing(4)
            grid.addWidget(label)
            grid.addWidget(combo)

        self.theme_combo = ArrowComboBox()
        self.theme_combo.addItem(i18n.tr("跟随系统"), FOLLOW_SYSTEM_ID)
        for theme_id in THEME_IDS:
            self.theme_combo.addItem(i18n.tr(THEME_LABELS[theme_id]), theme_id)
        self.theme_combo.currentIndexChanged.connect(lambda: self.on_theme_change())
        add_setting("界面主题", self.theme_combo)

        self.scale_combo = ArrowComboBox()
        self.scale_combo.addItem(i18n.tr("自动"), AUTO_SCALE_ID)
        for percent in SCALE_PRESETS:
            self.scale_combo.addItem(i18n.tr("{percent}%", percent=percent), str(percent))
        self.scale_combo.currentIndexChanged.connect(lambda: self.on_scale_change())
        add_setting("界面缩放", self.scale_combo)

        self.language_combo = ArrowComboBox()
        self._language_names = i18n.unique_display_names()
        for code, name in self._language_names.items():
            self.language_combo.addItem(name, code)
        self.language_combo.currentIndexChanged.connect(lambda: self.on_language_change())
        add_setting("语言 Language", self.language_combo)

        self.font_combo = ArrowComboBox()
        self.font_combo.currentTextChanged.connect(lambda text: self.on_font_change(text))
        add_setting("界面字体", self.font_combo)
        self.import_font_btn = action_button(i18n.tr("导入字体…"))
        # M-14：按钮文案是构建期定型的静态标签，登记键与构造标签同一 msgid。
        set_text(self.import_font_btn, T("导入字体…"))
        connect_click(self.import_font_btn, self.on_import_font)
        grid.addWidget(self.import_font_btn)
        self._refresh_font_menu_values()
        # 图标导入与字体导入同构（选文件 → 校验 → 落盘副本 → 写配置 → 即时生效），
        # 故按钮紧跟在字体按钮之后，共用同一组样式与登记口径。
        self.import_icon_btn = action_button(i18n.tr("导入图标…"))
        set_text(self.import_icon_btn, T("导入图标…"))
        connect_click(self.import_icon_btn, self.on_import_icon)
        grid.addWidget(self.import_icon_btn)
        return grid

    def _build_topbar(self) -> QFrame:
        # 顶栏状态胶囊与侧栏胶囊是同一份运行态的两个投影，都由 _set_running_ui 驱动；
        # 各自去读录制状态就会出现「托盘说在录、按钮说待机」的错位。
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(theme_module.TOPBAR_HEIGHT)
        row = QHBoxLayout(topbar)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(8)
        self.sidebar_toggle = action_button("☰")
        connect_click(self.sidebar_toggle, self.toggle_sidebar)
        row.addWidget(self.sidebar_toggle)
        self.page_title = QLabel(i18n.tr("控制台"))
        self.page_title.setObjectName("muted")
        row.addWidget(self.page_title)
        row.addStretch(1)
        self.status_chip = QLabel(i18n.tr("未运行"))
        self.status_chip.setObjectName("muted")
        row.addWidget(self.status_chip)
        self.theme_toggle = action_button("🌓")
        connect_click(self.theme_toggle, self.toggle_theme)
        row.addWidget(self.theme_toggle)
        return topbar

    def _build_pages(self) -> None:
        # 页面构造顺序 = 侧栏导航顺序；QStackedWidget 的 index 就是它的加入顺序。
        self.dashboard = DashboardPage(self)
        self.quality_page = QualityPage(self.quality, self)
        self.danmaku_page = DanmakuPage(self.danmaku, self)
        self.config_page = ConfigPage(self)
        self.logs_page = LogsPage(self)
        for page_id, page in (
            ("dashboard", self.dashboard),
            ("quality", self.quality_page),
            ("danmaku", self.danmaku_page),
            ("config", self.config_page),
            ("logs", self.logs_page),
        ):
            self.stack.addWidget(page)
            self._pages[page_id] = page

        self.dashboard.bind_actions(
            self.start_recording, self.stop_recording, self.open_downloads_folder, self.open_advanced_settings
        )
        self.quality_page.bind_actions(lambda: self.quality_page.refresh())
        self.danmaku_page.bind_actions(self.danmaku.clear)
        self.config_page.bind_actions(lambda: self.load_url_config(), self.save_url_config)
        self.logs_page.bind_actions(self.logs_page.clear)
        self.show_page("dashboard")

    # ─── 页面切换 ───

    def show_page(self, page_id: str) -> None:
        # 切页只做 setCurrentWidget，不重建实例：QStackedWidget 复用同一批页面对象，
        # 于是日志缓冲、编辑器未保存内容、表格滚动位置都不会因切页丢失。
        page = self._pages.get(page_id)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)
        self.page_title.setText(self._nav_buttons[page_id].text().split("  ")[-1])

    def toggle_sidebar(self) -> None:
        # 用 setVisible 而不是从布局里增删：后者会重建侧栏内的下拉，
        # 把用户当前选中的主题/缩放/语言一并丢回默认值。
        self.sidebar.setVisible(not self.sidebar.isVisible())

    # ─── 主题 / 缩放 / 语言 / 字体 ───

    def _resolve_initial_theme_and_scale(self) -> None:
        # 必须在 _build_ui 之前跑：palette 的 scale 直接决定侧栏固定宽与窗口最小尺寸，
        # 先建控件再换 palette 会按 1.0 算错一版再修正，视觉上是一次可察觉的抖动。
        saved_theme = load_theme_preference(self.main_config_file)
        # 「跟随系统」= 无显式偏好：显式选过才覆盖系统明暗。
        self._theme_follow_system = saved_theme == ""
        resolved = detect_system_appearance() if saved_theme == "" else saved_theme
        saved_scale = load_scale_preference(self.main_config_file)
        self._scale_follow_system = saved_scale in ("", AUTO_SCALE_ID)
        percent = self._auto_percent() if self._scale_follow_system else int(saved_scale)
        # M-80（2026-10-21）：把最终生效的档位留给启动回填用。这里只算不写回下拉——
        # 本方法必须先于 _build_ui 跑（palette 的 scale 决定侧栏定宽与窗口最小尺寸），
        # 下拉那时还不存在，旧实现在此之后再也没有第二处对齐点，见 _sync_pref_combo_positions。
        self._initial_scale_percent = percent
        self._palette = palette(resolved, percent / 100.0)
        self._font_file_pref = load_font_file_preference(self.main_config_file)
        self._selected_font_family = load_font_preference(self.main_config_file)
        self._icon_file_pref = load_icon_preference(self.main_config_file, GUI_SECTION, GUI_ICON_KEY)

    def _auto_percent(self) -> int:
        # 取 availableSize 而非 size：任务栏/停靠栏占掉的那一部分不算可用高度，
        # 按物理高度算会让笔记本上自动选到偏大的档位。
        screen = self.screen()
        if screen is None:
            return 100
        size = screen.availableSize()
        return auto_scale_for_screen(size.width(), size.height())

    def _sync_pref_combo_positions(self) -> None:
        # M-80（2026-10-21）：_resolve_initial_theme_and_scale 读了配置、算出 palette，却从不
        # 回填侧栏下拉——下拉初值恒是 index 0（「跟随系统」/「自动」）。显式选过 dark/115 的
        # 用户重启后得到「窗口是深色、下拉却指着跟随系统」的自相矛盾现场：toggle_theme 按
        # palette 翻转、下拉按 currentData 落盘，两处对「当前主题」的判断从此不一致，用户要
        # 先拨一次下拉才能把自己的既有选择「同步」回来。定稿 = 与 _refresh_font_menu_values()
        # 同一回填形态：findData 为唯一判据、blockSignals 防回填被当成用户选择写回 config；
        # 跟随系统/自动形态下目标就是 index 0，统一走 findData 比较而不是特判「只在显式偏好
        # 时回填」（少一层分支）。目录里没有的取值（未来档位增删的过渡态）保持原位不硬设。
        targets: tuple[tuple[QComboBox, str], ...] = (
            (self.theme_combo, FOLLOW_SYSTEM_ID if self._theme_follow_system else self._palette.theme_id),
            (self.scale_combo, AUTO_SCALE_ID if self._scale_follow_system else str(self._initial_scale_percent)),
        )
        for combo, want in targets:
            index = combo.findData(want)
            if index >= 0 and index != combo.currentIndex():
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)

    def apply_palette(self) -> None:
        # 主题/缩放切换的唯一出口：QSS 由 palette 现算后整窗重设。
        # 不做逐控件 setStyle，是因为那样每加一个控件都要记得同步一次，迟早漏。
        app = self.application()
        if app is not None:
            app.setStyleSheet(theme_module.build_stylesheet(self._palette))
        self.dashboard.apply_palette(self._palette, running=self.recorder.is_running())
        self.quality_page.apply_palette(self._palette)
        self.danmaku_page.apply_palette(self._palette)
        self.logs_page.apply_palette(self._palette)
        self.config_page.apply_palette(self._palette)
        if self.recorder.is_running():
            self.sidebar_dot.set_color(self._palette.token("success"), True)
        else:
            self.sidebar_dot.set_color(self._palette.token("danger"), False)
        # M-81（2026-10-21）：托盘是运行态与主题的第五处投影，漏进本出口就会与侧栏分色
        # （图标色是 TrayIcon 构造时拿的 palette.tokens 快照，旧实现此后从不刷新）。
        # 托盘不可用时为 None，按存在性接线（离屏/无 Session 环境恒 None，不得硬调）。
        if self.tray is not None:
            self.tray.apply_palette(self._palette.tokens)

    def application(self) -> QApplication | None:
        # 取 QApplication 单例（instance() 的静态类型是 QCoreApplication，故显式 cast）。
        return cast(QApplication | None, QApplication.instance())

    def on_theme_change(self) -> None:
        # 配置写回失败时不回滚界面：用户已经看到切换结果，把配置侧的问题留在日志里
        # 比让界面跳回原样更容易诊断（回滚会让「到底切没切成功」变得不可判定）。
        data = self.theme_combo.currentData()
        selected = str(data) if data is not None else FOLLOW_SYSTEM_ID
        self._theme_follow_system = selected == FOLLOW_SYSTEM_ID
        resolved = detect_system_appearance() if self._theme_follow_system else selected
        self._palette = palette(resolved, self._palette.scale)
        self.apply_palette()
        try:
            saved = save_theme_preference(self.main_config_file, "" if self._theme_follow_system else resolved)
        except Exception as e:
            self._queue_log(i18n.tr("界面主题已切换，但配置写回失败: {err}", err=e), "warn")
            return
        if not saved:
            self._queue_log(i18n.tr("界面主题已切换，但配置写回失败"), "warn")

    def toggle_theme(self) -> None:
        # 快捷按钮：在浅色/深色之间直接翻转（不改变「跟随系统」的持久化语义时会解除跟随）。
        target = (
            theme_module.THEME_DARK if self._palette.theme_id != theme_module.THEME_DARK else theme_module.THEME_LIGHT
        )
        index = self.theme_combo.findData(target)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)

    def on_scale_change(self) -> None:
        # 缩放只改 palette 的 scale（圆角/间距/字号随之缩放），控件树不重建，
        # 因此可以在录制运行中直接调，不中断任何进行中的动作。
        data = self.scale_combo.currentData()
        raw = str(data) if data is not None else AUTO_SCALE_ID
        self._scale_follow_system = raw == AUTO_SCALE_ID
        percent = self._auto_percent() if self._scale_follow_system else int(raw)
        self._palette = palette(self._palette.theme_id, percent / 100.0)
        self.apply_palette()
        try:
            saved = save_scale_preference(
                self.main_config_file, AUTO_SCALE_ID if self._scale_follow_system else str(percent)
            )
        except Exception as e:
            self._queue_log(i18n.tr("界面缩放已调整，但配置写回失败: {err}", err=e), "warn")
            return
        if not saved:
            self._queue_log(i18n.tr("界面缩放已调整，但配置写回失败"), "warn")

    def on_language_change(self) -> None:
        data = self.language_combo.currentData()
        lang_code = str(data) if data is not None else i18n.DEFAULT_LANGUAGE
        # MID-52：取 set_language 的返回值（**实际生效**的语言码）而不是请求值——
        # 目录缺失时二者不同，写请求值会让 GUI 与录制子进程各说一种语言。
        try:
            effective = i18n.set_language(lang_code)
            retranslate_all()
            self._repopulate_static_texts()
        except Exception as e:
            self._queue_log(i18n.tr("界面重译失败（当前语言 {lang}）: {err}", lang=lang_code, err=e), "warn")
            return
        index = self.language_combo.findData(effective)
        if index >= 0 and index != self.language_combo.currentIndex():
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(index)
            self.language_combo.blockSignals(False)
        try:
            if not update_config_line(self.main_config_file, "录制设置", "language", effective):
                self._queue_log(i18n.tr("语言已切换为 {lang}，但配置写回失败", lang=effective), "warn")
            elif effective != lang_code:
                self._queue_log(
                    i18n.tr("{lang} 的翻译目录不可用，已回退为 {effective}", lang=lang_code, effective=effective),
                    "warn",
                )
            else:
                self._queue_log(i18n.tr("语言已切换: {lang}（录制子进程重启后同步生效）", lang=effective))
        except Exception as e:
            self._queue_log(i18n.tr("语言已切换，但配置写回失败: {err}", err=e), "warn")

    def _apply_language_preference(self) -> None:
        # [历史注] 本方法原注释声称「启动期与运行期两条路径都走同一个 retranslate_all()」——
        # 2026-10-21 M-78 复核证伪：旧实现从未在这里调用它，retranslate_all 全仓唯一调用点
        # 在 on_language_change。set_text() 是「建时查表 + 登记重译」两段式，而 _build_ui()
        # 跑在任何语言切换之前（建时查的还是导入默认语言的表），所以配置语言非 zh_CN 的用户
        # 启动后静态标签一直是中文，直到手动切一次语言下拉才被「顺带」修好。
        raw = self._read_config_value("language")
        effective = i18n.set_language(i18n.resolve_language(raw))
        index = self.language_combo.findData(effective)
        if index >= 0:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(index)
            self.language_combo.blockSignals(False)
        # 回填已建控件必须排在 set_language 之后、_repopulate_static_texts() 之前：
        # 后者派生顶栏页标题与运行态投影，读的必须是新语言回填完的导航按钮文本
        # （与 on_language_change 的步序逐字一致）。重译单独一段 try、与后续刷新解耦——
        # 回填半途炸掉也只损失回填，不该把哨兵下拉/托盘/状态面一并带走（同「重译与
        # config 写回必须是两段独立 try」的钩子约定）。本路径不做配置写回，写回侧问题
        # 不存在，无需再分第二段。
        try:
            retranslate_all()
        except Exception as e:
            self._queue_log(i18n.tr("界面重译失败（当前语言 {lang}）: {err}", lang=effective, err=e), "warn")
        self._repopulate_static_texts()

    def _repopulate_static_texts(self) -> None:
        # 下拉里的哨兵项（跟随系统 / 自动 / 系统默认）是**显示名**而非登记对象，
        # 语言切换后必须重建——否则下拉里混着上一语言的首项，点它却命中不了任何分支。
        self.theme_combo.setItemText(0, i18n.tr("跟随系统"))
        for offset, theme_id in enumerate(THEME_IDS, start=1):
            self.theme_combo.setItemText(offset, i18n.tr(THEME_LABELS[theme_id]))
        self.scale_combo.setItemText(0, i18n.tr("自动"))
        self._refresh_font_menu_values()
        if self.tray is not None:
            self.tray.retranslate()
        self.refresh_status()
        # ── 运行态面重驱（M-13/M-14，2026-10-18）──
        # 顶栏页标题由激活导航按钮的 text() 派生（split("  ")[-1]），**不进登记表**：
        # 登记表没有「当前页」概念，登记会让回填无条件把标题打回初值「控制台」（用户在
        # 弹幕页时也会被改）。retranslate_all() 已把导航按钮回填成新语言，这里重取即可。
        active_btn = next((btn for btn in self._nav_buttons.values() if btn.isChecked()), None)
        if active_btn is not None:
            self.page_title.setText(active_btn.text().split("  ")[-1])
        # 状态四处投影（控制台大状态点+副标题、侧栏胶囊、顶栏胶囊、托盘状态项）都是运行态
        # 文案、刻意不进登记表（登记后 retranslate_all() 会把「录制中」打回初值「待机」，
        # 即 M-13 的故障形态），切换语言后必须按当前 recorder 状态主动重调唯一出口。
        self._set_running_ui(self.recorder.is_running())
        # 两张监控表的表头/单元格状态 token 与「全部房间」哨兵都在产生点 tr()，
        # 但各自的 refresh 对行内容等值时短路返回、数据不变时旧语言原地常驻——
        # 由页面清掉上一轮缓存强制整表重画（见 pages/quality.py、pages/danmaku.py）。
        self.quality_page.retranslate_runtime()
        self.danmaku_page.retranslate_runtime()

    def _refresh_font_menu_values(self) -> None:
        # 重建期间必须 blockSignals：clear()/addItems() 会触发 currentTextChanged，
        # 不挡住就会把「系统默认」当成用户的新选择写回 config.ini。
        families = self._available_families()
        default_label = i18n.tr("系统默认")
        values = [default_label, *families]
        current = self._selected_font_family
        if current and current not in values:
            values.append(current)
        self.font_combo.blockSignals(True)
        self.font_combo.clear()
        self.font_combo.addItems(values)
        self.font_combo.setCurrentText(current if current else default_label)
        self.font_combo.blockSignals(False)

    def _available_families(self) -> list[str]:
        # 并上本会话导入的字体族：addApplicationFont 之后系统族列表不保证立刻包含它们，
        # 只信 QFontDatabase.families() 会让刚导入的字体在下拉里消失。
        families = [str(f) for f in QFontDatabase.families()]
        return sorted(set(families) | set(self._imported_font_families))

    def on_font_change(self, choice: str) -> None:
        # 空串是 clear() 过程中的中间态，不是用户选择，直接忽略即可
        if not choice:
            return
        family = "" if choice == i18n.tr("系统默认") else choice
        self._apply_font_family(family)
        self._selected_font_family = family
        try:
            saved = save_font_preference(self.main_config_file, family, self._font_file_pref)
        except Exception as e:
            self._queue_log(i18n.tr("界面字体已调整，但配置写回失败: {err}", err=e), "warn")
            return
        if not saved:
            self._queue_log(i18n.tr("界面字体已调整，但配置写回失败"), "warn")

    def _apply_font_family(self, family: str) -> None:
        # 全局字体一换即整窗重排（Qt 的字体传播是自上而下的），
        # 不需要像 Tk 那样逐控件 restyle，也不必重建控件树（不丢日志与编辑器内容）。
        app = self.application()
        if app is None or family not in self._available_families():
            return
        app.setFont(QFont(family))

    def on_import_font(self) -> None:
        # 导入的字体要落盘到 app_root 并记进 config：下次启动须能重新装载，
        # 否则「换个用户目录/清一次缓存」后界面字体就静默回退到系统默认。
        path, _ = QFileDialog.getOpenFileName(
            self,
            i18n.tr("选择字体文件"),
            "",
            i18n.tr("字体文件") + " (*" + " *".join(SUPPORTED_FONT_SUFFIXES) + ")",
        )
        if not path:
            return
        if os.path.splitext(path)[1].lower() not in SUPPORTED_FONT_SUFFIXES:
            QMessageBox.warning(
                self,
                i18n.tr("不支持的字体格式"),
                i18n.tr(
                    "仅支持 {formats} 字体文件；woff/woff2 是网页传输格式，请先转成 ttf/otf 再导入。",
                    formats="/".join(SUPPORTED_FONT_SUFFIXES),
                ),
            )
            return
        installed = install_font_file(path, self.app_root)
        if installed is None:
            QMessageBox.warning(
                self, i18n.tr("导入字体失败"), i18n.tr("无法读取或复制该字体文件，请确认文件未被占用且可读取。")
            )
            return
        font_id = QFontDatabase.addApplicationFont(str(installed))
        families = [str(f) for f in QFontDatabase.applicationFontFamilies(font_id)]
        if not families:
            QMessageBox.warning(
                self, i18n.tr("导入字体失败"), i18n.tr("系统无法加载该字体，可能是文件已损坏或系统不支持私有字体装载。")
            )
            return
        self._font_file_pref = str(installed)
        self._imported_font_families.extend(families)
        self._selected_font_family = families[0]
        self._apply_font_family(families[0])
        self._refresh_font_menu_values()
        try:
            save_font_preference(self.main_config_file, families[0], str(installed))
        except Exception as e:
            self._queue_log(i18n.tr("界面字体已调整，但配置写回失败: {err}", err=e), "warn")

    def on_import_icon(self) -> None:
        # 导入托盘 / 窗口图标（ICO）：与字体导入同一条链路——选文件 → 格式与分辨率校验 →
        # 复制进 config/icons/ → 写回 config.ini → 即时应用到托盘 + 窗口（标题栏 / 任务栏）。
        # 校验前置（而不是复制后再判）的理由：坏文件不该在 config/icons/ 里留下一份垃圾副本。
        path, _ = QFileDialog.getOpenFileName(
            self,
            i18n.tr("选择图标文件"),
            "",
            i18n.tr("图标文件") + " (*" + " *".join(SUPPORTED_ICON_SUFFIXES) + ")",
        )
        if not path:
            return
        if os.path.splitext(path)[1].lower() not in SUPPORTED_ICON_SUFFIXES:
            QMessageBox.warning(
                self,
                i18n.tr("不支持的图标格式"),
                i18n.tr(
                    "仅支持 {formats} 图标文件；ICO 需包含 16×16 分辨率（系统托盘）"
                    "，建议同时包含 256×256（应用图标与任务栏）。",
                    formats="/".join(SUPPORTED_ICON_SUFFIXES),
                ),
            )
            return
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except Exception:
            raw = b""
        check = validate_icon_bytes(raw)
        if not check.ok:
            QMessageBox.warning(self, i18n.tr("导入图标失败"), self._icon_reject_reason(check.code))
            return
        if check.code == "no_app_size":
            # 缺 256 档是「能用但发虚」（资源管理器大图标 / Alt+Tab 要放大），提示但不拦：
            # 用户手头只有 48×48 的图标时，拒绝导入等于完全用不了自定义图标。
            self._queue_log(i18n.tr("图标缺少 256×256 分辨率，应用图标会放大发虚"), "warn")
        installed = install_icon_file(path, self.app_root)
        if installed is None:
            QMessageBox.warning(
                self, i18n.tr("导入图标失败"), i18n.tr("无法读取或复制该图标文件，请确认文件未被占用且可读取。")
            )
            return
        if not self._apply_icon_path(str(installed)):
            QMessageBox.warning(
                self, i18n.tr("导入图标失败"), i18n.tr("系统无法加载该图标，可能是文件已损坏或不是有效的 ICO 文件。")
            )
            return
        self._icon_file_pref = str(installed)
        try:
            saved = save_icon_preference(self.main_config_file, GUI_SECTION, GUI_ICON_KEY, str(installed))
        except Exception as e:
            self._queue_log(i18n.tr("图标已应用，但配置写回失败: {err}", err=e), "warn")
            return
        if not saved:
            self._queue_log(i18n.tr("图标已应用，但配置写回失败"), "warn")
        self._queue_log(i18n.tr("已导入并应用图标: {name}", name=installed.name))

    def _icon_reject_reason(self, code: str) -> str:
        # 拒绝原因 → 用户能看懂的一句话。刻意不回显 code 原文（"not_ico" 对终端用户无意义）。
        if code == "too_large":
            return i18n.tr("图标文件过大（上限 {limit}KB）。", limit=MAX_ICON_BYTES // 1024)
        if code == "no_tray_size":
            return i18n.tr("图标缺少 {size} 分辨率，系统托盘会显示模糊；请用多分辨率 ICO。", size="16×16")
        return i18n.tr("系统无法加载该图标，可能是文件已损坏或不是有效的 ICO 文件。")

    def _apply_icon_preference(self) -> None:
        # 启动期加载：config.ini 记的导入图标 → 内置 assets/app.ico → 都没有就不动
        # （Qt 在 Windows 上默认取 exe 资源里的图标，打包产物因此仍显示应用图标）。
        # 整条路径静默降级：图标是装饰，加载失败只应是「图标没换」，绝不能挡住启动。
        resolved = current_icon_path(self.app_root, self._icon_file_pref)
        if resolved is None:
            return
        if not self._apply_icon_path(str(resolved)):
            self._queue_log(i18n.tr("自定义图标加载失败，回落到默认图标: {path}", path=str(resolved)), "warn")

    def _apply_icon_path(self, path: str) -> bool:
        # 应用到窗口（标题栏 / 任务栏）与托盘；返回是否真的换上了。
        # 【为什么两处必须同源】只设窗口不设托盘会出现「任务栏是导入图标、托盘还是默认圆点」，
        # 用户会当成导入没生效。托盘不可用时窗口图标照设（它决定任务栏观感）。
        icon = QIcon(path)
        if icon.isNull():
            return False
        app = self.application()
        if app is not None:
            app.setWindowIcon(icon)
        self.setWindowIcon(icon)
        if self.tray is not None:
            self.tray.set_custom_icon(path)
        return True

    # ─── 子进程接线 ───

    def _wire_recorder(self) -> None:
        # Qt 的跨线程连接（AutoConnection → Queued）保证下面几条槽只在主线程跑，
        # 取代旧版手写的 _ui_event_queue + post_ui 事件泵。
        # outputReady 取代原先从未 emit 的 linesReceived（S-01）：队列里每落一批新内容就被唤醒
        # 一次，由 _pump_recorder_queue 在主线程取空；刻意不接回带数据的信号（理由见 recorder）。
        self.recorder.outputReady.connect(self._pump_recorder_queue)
        self.recorder.logRequested.connect(self._queue_log)
        self.recorder.started.connect(self._on_recorder_started)
        self.recorder.ended.connect(self._on_recorder_ended)
        self.logQueued.connect(self._ensure_log_timer_running)
        self.shutdownFinished.connect(self._finalize_quit)

    # 读线程 → 队列 → 主线程的唯一消费口（S-01）。
    def _pump_recorder_queue(self) -> None:
        # 一次取空、成批处理，结束哨兵单独交 _on_recorder_ended 校验会话。异常只留痕不外抛：
        # 本槽由信号投递触发，抛出会中断这一轮事件派发，已 drain 出的 messages 随之丢失，
        # 界面可用优先。
        try:
            messages, ended, ended_session = self.recorder.drain()
            if messages:
                self._on_lines_received(messages)
                # _on_lines_received 直接往缓冲追加、不走 _queue_log，故这里补一次唤醒：
                # 本槽由跨线程信号投递而来、必然在主线程，直接启表安全（M-11 同一条判据）。
                self._ensure_log_timer_running()
            if ended:
                self._on_recorder_ended(ended_session)
        except Exception as e:
            self._warn_chain("recorder-output", e)

    def _on_lines_received(self, payload: object) -> None:
        if not isinstance(payload, list):
            return
        for item in payload:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                continue
            line = str(item[0])
            level = str(item[1])
            # 画质解析放在主线程（数据模型侧不再需要锁）；批次内逐行解析。
            self.quality.parse_line(line, self._queue_log, self._timestamp())
            self._pending_log_lines.append((line, level))

    def _on_recorder_started(self, _pid: int) -> None:
        # 新会话开跑：画质统计与弹幕监控都按下一次归零，
        # 否则上一轮的分辨率/帧率行会混进本轮统计里。
        self.quality.reset()
        self.danmaku.start()
        self._set_running_ui(True)

    def _on_recorder_ended(self, session_id: object) -> None:
        # 会话校验：旧会话的迟到 EOF 不得把新会话的状态打回未运行。
        session = None if session_id is None else int(str(session_id))
        if session is not None and session != self.recorder.session_id():
            return
        if self._quitting:
            # 退出收尾期间短路：UI 生命周期由 _finalize_quit 统一收尾。
            return
        if self.recorder.is_stopping():
            # 手动停止流程进行中，由其自身（_on_recorder_ended 的同源收尾）统一收尾。
            return
        # S-01：结束动作现在真的有两个来源（停止工作线程 emit 的 ended、读线程投进队列的
        # EOF 哨兵），手动停止时两条都会到达且时序取决于事件循环，不去重就是两遍
        # 「录制进程已结束」+ 两次 danmaku.stop()。按会话号去重（会话号单调递增）。
        if session is not None and self._finish_handled_session == session:
            return
        self._finish_handled_session = session
        # 自然 EOF 的句柄回收：读线程只置 _running，_process 留在这里清，
        # 否则界面回到待机后再点「开始录制」恒报 already_running。
        self.recorder.reclaim_after_natural_end(session)
        if self.recorder.output_thread_alive():
            self.recorder.note_finish_skip()
        self.danmaku.stop()
        self._set_running_ui(False)
        self._queue_log("━" * 40)
        self._queue_log(i18n.tr("录制进程已结束"))
        self._queue_log("━" * 40)

    def _set_running_ui(self, running: bool) -> None:
        # 运行态的唯一出口：侧栏胶囊 / 顶栏胶囊 / 控制台卡片 / 托盘图标四处一起切。
        # 分散到各自的刷新链里，就必然出现「托盘显示在录、按钮却可点开始」的错位。
        pid = self.recorder.pid()
        if running:
            status_text = i18n.tr("录制中")
            sub_text = i18n.tr("录制进程运行中 (PID: {pid})", pid=pid)
            sidebar_text = i18n.tr("运行中")
            self.sidebar_dot.set_color(self._palette.token("success"), True)
        else:
            status_text = i18n.tr("待机")
            sub_text = i18n.tr("录制进程未运行")
            sidebar_text = i18n.tr("未运行")
            self.sidebar_dot.set_color(self._palette.token("danger"), False)
        self.dashboard.set_status(running, self._palette, status_text, sub_text)
        self.sidebar_status.setText(sidebar_text)
        self.status_chip.setText(sidebar_text)
        if self.tray is not None:
            self.tray.set_running(running)

    # ─── 周期链 ───

    def _start_timers(self) -> None:
        # 三条链一律用 QTimer 且**自续期**（Qt 的 timer 不因回调抛错而停），但回调内部仍包
        # try/except + 限频留痕：旧版「下一次 after 因异常没注册 → 整条链永久静默」要显式消掉。
        self._log_timer = QTimer(self)
        self._log_timer.setInterval(_LOG_FLUSH_INTERVAL)
        self._log_timer.timeout.connect(self._flush_pending_lines)
        # _log_timer 刻意不在这里 start：它是「按需激活」的休眠态链，由 _ensure_log_timer_running
        # 在真有日志入队时启表。启表入口只能是主线程（M-11），故入口挂在 logQueued 信号上。
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(_STATUS_INTERVAL_IDLE)
        self._status_timer.timeout.connect(self._status_tick)
        self._status_timer.start()
        self._danmaku_timer = QTimer(self)
        self._danmaku_timer.setInterval(_DANMAKU_INTERVAL)
        self._danmaku_timer.timeout.connect(self._danmaku_tick)
        self._danmaku_timer.start()

    def _flush_pending_lines(self) -> None:
        # 成批刷入而非逐行 append：录制峰值每秒上百行，逐行走一次事件循环会把主线程拖慢到
        # 肉眼可见的卡顿。回调内包 try/except + 限频留痕是周期链的统一口径（见 _warn_chain）：
        # 不接住异常就等于这一批已出队的行随异常消失、日志页从此不再更新却无一条线索。
        if not self._pending_log_lines:
            # M-80（2026-10-21）：空缓冲时必须停表再返回。本链的契约是「按需激活」——
            # _start_timers 刻意不 start 它，启动口在 _ensure_log_timer_running（logQueued
            # 投递）。旧实现在这里直接 return，表一旦被启过就再没有停的时机：GUI 空闲时
            # 5Hz 空转直到进程退出（白耗事件循环轮次，也掩盖「唤醒链断了」这类真故障——
            # 反正定时器一直在跑，logQueued 丢没丢都看不出来）。
            self._log_timer.stop()
            return
        batch = self._pending_log_lines
        self._pending_log_lines = []
        try:
            for line, level in batch:
                if level == "error":
                    self.logs_page.terminal.append_line(f"[{self._timestamp()}] [ERROR] {line}")
                elif level == "warn":
                    self.logs_page.terminal.append_line(f"[{self._timestamp()}] [WARN] {line}")
                else:
                    self.logs_page.terminal.append_line(f"[{self._timestamp()}] {line}")
        except Exception as e:
            self._warn_chain("log-flush", e)

    def _status_tick(self) -> None:
        # 录制中收紧到 3s（要看 PID、目录、格式变化），空闲放宽到 10s 少做无用磁盘读取。
        # 间隔在 finally 里自续期，异常不会把这条链永久停掉。
        try:
            self.refresh_status()
            self.quality_page.refresh()
            self._watch_url_config()
        except Exception as e:
            self._warn_chain("status", e)
        finally:
            interval = _STATUS_INTERVAL_ACTIVE if self.recorder.is_running() else _STATUS_INTERVAL_IDLE
            self._status_timer.setInterval(interval)

    def _danmaku_tick(self) -> None:
        # 只在录制中刷新：弹幕文件由子进程写，没跑的时候轮询纯属空转。
        try:
            if self.recorder.is_running():
                self.danmaku_page.refresh()
        except Exception as e:
            self._warn_chain("danmaku", e)

    def _warn_chain(self, chain: str, error: BaseException) -> None:
        # 只留痕不重抛：周期链掉一轮不应连带杀掉整个界面；
        # 限频是因为持续故障逐次落日志会刷满日志页，而完全静默又让编程错误不可见。
        now = time.time()
        if now - self._chain_warn_at.get(chain, 0.0) < _CHAIN_WARN_INTERVAL_SECONDS:
            return
        self._chain_warn_at[chain] = now
        self._queue_log(
            i18n.tr(
                "{chain}周期任务异常（本轮已跳过、下轮继续；{seconds}s 内不重复）: {type_name}: {err}",
                chain=chain,
                seconds=int(_CHAIN_WARN_INTERVAL_SECONDS),
                type_name=type(error).__name__,
                err=error,
            ),
            "warn",
        )

    # 线程安全的日志入口（可被任意线程调用：只 append 到主线程消费的缓冲）。
    def _queue_log(self, message: str, level: str = "info") -> None:
        self._pending_log_lines.append((message, level))
        # M-11：这里**不能**直接 self._log_timer.start()。弹幕 tail 线程与画质解析链都会在
        # 非 GUI 线程调本方法，而 QTimer 只能在拥有它的线程启停——跨线程 start() 会被 Qt 拒绝
        # （stderr 打印 "Timers cannot be started from another thread"，不抛 Python 异常），
        # 那一批日志会滞留到下一次主线程入队才刷出。改经信号投递后启表必在主线程。
        self.logQueued.emit()

    # 日志刷新链的启动口（只在主线程执行：本槽由 logQueued 投递）。
    def _ensure_log_timer_running(self) -> None:
        if not self._log_timer.isActive():
            self._log_timer.start()

    @staticmethod
    def _timestamp() -> str:
        # 本地时间而非 UTC：与 logger.py 落盘行的时间戳对齐，便于两边对照排查
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ─── 状态信息 ───

    def refresh_status(self) -> None:
        # 周期调用，另外在主题/语言切换后各调一次：卡片里的文本要跟着语言重算。
        interval, output_format = self._dynamic_status_info()
        tray_status = i18n.tr("启用") if self.tray is not None and self.tray.icon.isVisible() else i18n.tr("未启动")
        self.dashboard.set_info(
            {"interval": interval, "format": output_format, "tray": tray_status, "time": self._timestamp()}
        )

    def _dynamic_status_info(self) -> tuple[str, str]:
        # 按 mtime 缓存：状态链每 3s 一次，每次都把 config.ini 读一遍是纯浪费；
        # 用 mtime 而不是内容 hash，是因为配置只会被整文件重写。
        default_interval = i18n.tr("{interval}秒", interval="120")
        output_format = "ts → mp4"
        # 先落默认值再进 try：文件存在但没有 [录制设置] 节时（用户手删/旧版本残留）走不到赋值
        # 分支，未预置会让下面的返回抛 NameError，表现为状态链每 3s 抛一次、每 30s 落一条告警。
        interval = default_interval
        if not os.path.exists(self.main_config_file):
            return default_interval, output_format
        try:
            file_mtime = os.path.getmtime(self.main_config_file)
            if self._status_cache is not None and file_mtime == self._status_cache_mtime:
                return self._status_cache
            config = tolerant_config_parser(preserve_case=True)
            config.read(self.main_config_file, encoding="utf-8-sig")
            # 重复键容错读取后必须点名（同进程内按 路径+mtime 去重，不会每 10s 刷一条）：
            # 否则该链路会把 DuplicateOptionError 打成静默降级，用户看不出配置坏在哪一行。
            warn_duplicate_options(self.main_config_file)
            if "录制设置" in config:
                raw_interval = config["录制设置"].get("循环时间(秒)", "120")
                interval = i18n.tr("{interval}秒", interval=raw_interval)
                # 与 main.py / logger.py 共用同一布尔解析口径：只比较 == "是" 会把
                # 写成 true 的配置误判为未开启 mp4 转换。
                fmt = config["录制设置"].get("录制完成后自动转为mp4格式", "否")
                if parse_config_bool(fmt, False):
                    output_format = "ts → mp4"
                else:
                    save_fmt = config["录制设置"].get("视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频", "ts")
                    output_format = f"ts → {save_fmt}"
            self._status_cache = (interval, output_format)
            self._status_cache_mtime = file_mtime
        except Exception as e:
            logger.warning(
                i18n.tr("状态栏读取 config.ini 失败，使用默认值: {type_name}: {e}", type_name=type(e).__name__, e=e)
            )
            return default_interval, output_format
        return self._status_cache

    def _read_config_value(self, key: str) -> str:
        # 只读 [录制设置] 一节：GUI 的偏好也写在这一节里，
        # 缺文件/缺节/缺键一律回落空串（调用方各自有默认值）。
        try:
            config = tolerant_config_parser()
            config.read(self.main_config_file, encoding="utf-8-sig")
        except Exception:
            return ""
        if "录制设置" in config and config.has_option("录制设置", key):
            return config["录制设置"].get(key, "")
        return ""

    # ─── URL 配置页 ───

    def load_url_config(self) -> None:
        os.makedirs(os.path.dirname(self.url_config_file), exist_ok=True)
        if not os.path.exists(self.url_config_file):
            with open(self.url_config_file, "w", encoding="utf-8-sig") as f:
                f.write("")
        try:
            with open(self.url_config_file, "r", encoding="utf-8-sig") as f:
                content = f.read()
        except Exception as e:
            self._queue_log(i18n.tr("加载配置文件失败: {err}", err=e), "error")
            return
        # 每次真正读到磁盘都刷新磁盘基线，否则保存前的冲突裁决会拿过期基线比对。
        self._url_disk_snapshot = content
        current = normalize_editor_text(self.config_page.content())
        self._url_last_mtime = os.path.getmtime(self.url_config_file)
        if normalize_editor_text(content) == current:
            return
        self.config_page.set_content(content)
        # 刚从磁盘载入 → 与磁盘一致，记为已保存基线
        self._config_baseline = normalize_editor_text(content)

    def save_url_config(self) -> None:
        editor_text = normalize_editor_text(self.config_page.content())
        disk_now, _ = read_config_snapshot(self.url_config_file)
        # MID-2252：整文件写回前必须重读磁盘并与上次读到的基线比对。录制子进程运行期
        # 确实在写 URL_config.ini（回写主播名、归一 URL、把被风控的房间整行注释掉），
        # 跨进程只剩「原子替换不半写」一条保护，丢失更新只能显式检测 + 交用户裁决。
        if config_change_verdict(self._url_disk_snapshot, disk_now, editor_text, self._config_baseline) == "conflict":
            answer = QMessageBox.question(
                self,
                i18n.tr("配置文件已变更"),
                i18n.tr(
                    "URL_config.ini 已被外部修改，但编辑器中有未保存的更改。\n\n"
                    "点击「是」放弃未保存的更改并重新加载；\n点击「否」保留当前编辑内容（稍后可手动保存）。"
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.load_url_config()
            return
        try:
            save_text_to_file(editor_text, self.url_config_file)
        except Exception as e:
            QMessageBox.critical(self, i18n.tr("错误"), i18n.tr("保存配置文件失败: {err}", err=e))
            return
        self._config_baseline = editor_text
        self._url_disk_snapshot, _ = read_config_snapshot(self.url_config_file)
        self._url_last_mtime = os.path.getmtime(self.url_config_file)
        self.toast_message(i18n.tr("URL 配置已保存"))

    def _watch_url_config(self) -> None:
        # 只认 mtime 不做内容 diff：子进程写这个文件的方式是整文件重写，
        # mtime 已经足够，且比对内容意味着状态链每秒都要读一遍配置。
        if not os.path.exists(self.url_config_file):
            return
        try:
            current_mtime = os.path.getmtime(self.url_config_file)
            if current_mtime == self._url_last_mtime:
                return
            # 有未保存编辑时先问，否则用户正在编辑的内容会被外部改动静默覆盖。
            if self._has_unsaved_config_edits():
                # M-12：本方法由 _status_tick 的定时器链驱动，而 QMessageBox.question 是**模态**
                # 的——它内部跑自己的事件循环，期间状态链照旧每 3s 触发一次本方法。
                # 顺序很关键：守卫必须排在 mtime 前置**之前**；排在之后时，询问期间若文件又变
                # 一次，那一拍的 mtime 会被就地吃掉，用户答完后这条新改动就再也问不到了。
                # 排在最前则整段挂起（既不更新 mtime、也不叠框），答完后下一拍照常再问。
                if self._url_conflict_asked:
                    return
                # 弹窗前置位：不先落 mtime，每一拍都会叠一个新的冲突框（用户视角=弹窗无限堆积）。
                self._url_last_mtime = current_mtime
                self._url_conflict_asked = True
                try:
                    answer = QMessageBox.question(
                        self,
                        i18n.tr("配置文件已变更"),
                        i18n.tr(
                            "URL_config.ini 已被外部修改，但编辑器中有未保存的更改。\n\n"
                            "点击「是」放弃未保存的更改并重新加载；\n点击「否」保留当前编辑内容（稍后可手动保存）。"
                        ),
                    )
                finally:
                    # 复位必须无条件：抛错或提前 return 都把守卫钉死，之后任何外部改动都不再询问
                    # （静默覆盖用户未保存的编辑，正是这条检测要防的事）。
                    self._url_conflict_asked = False
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self.load_url_config()
        except OSError:
            return

    def _has_unsaved_config_edits(self) -> bool:
        # 与基线比而不是与磁盘比：基线是「上次保存/载入时的内容」，
        # 于是「改了几笔又改回原样」不会再弹一次冲突框。
        return normalize_editor_text(self.config_page.content()) != self._config_baseline

    # ─── 录制控制 ───

    def has_room_config(self) -> bool:
        # 空配置下录制核心会走 input() 等待键盘输入，而 GUI 拉起的子进程带隐藏控制台、
        # stdin 永不关闭 —— 表现为「点开始录制后既无报错也无输出」。启动前自检比事后排查廉价。
        # 「这一行是不是有效房间」的唯一口径是 parse_url_config 的 enabled 字段，
        # 这里刻意不再自己实现一套（历史上两套判据漂移过：BOM 让 startswith('#') 失效）。
        try:
            if not os.path.isfile(self.url_config_file):
                return False
            rooms = parse_url_config(self.url_config_file)
        except OSError:
            return True
        return any(bool(room.get("enabled")) and str(room.get("url", "")).strip() for room in rooms)

    def start_recording(self) -> None:
        # 四道闸的顺序是刻意的：退出中 / 停止在途 / 已在运行 / 无有效房间。
        # 前两道必须排在「是否在运行」之前——停止在途时 is_running() 仍为真，
        # 先判它会给出「录制已在运行中」这个与事实相反的解释。
        if self._quitting:
            return
        if self.recorder.is_stopping():
            self._queue_log(i18n.tr("停止流程进行中，暂不可启动新录制"), "warn")
            return
        if self.recorder.is_running():
            QMessageBox.warning(self, i18n.tr("警告"), i18n.tr("录制已在运行中！"))
            return
        if not self.has_room_config():
            self._queue_log(i18n.tr("URL_config.ini 中没有直播间地址，已取消启动录制"), "warn")
            QMessageBox.warning(
                self,
                i18n.tr("警告"),
                i18n.tr("config/URL_config.ini 中没有可录制的直播间地址。\n请先在「URL 配置」中添加至少一个地址。"),
            )
            return
        ok, _pid, reason = self.recorder.start()
        if not ok:
            self._queue_log(i18n.tr("启动录制失败: {err}", err=reason), "error")
            QMessageBox.critical(self, i18n.tr("错误"), i18n.tr("启动录制失败: {err}", err=reason))
            self._set_running_ui(False)

    def stop_recording(self) -> None:
        # 停止是异步的（发 CTRL_BREAK 后还要等进程收尾），期间把两个按钮都禁用，
        # 由 _on_recorder_ended 统一恢复，避免连点触发第二次停止。
        if not self.recorder.is_running():
            # M-34：这里不只是「没什么可停」，更是**按钮禁用态的唯一自救入口**——某次停止流程
            # 没投递结束事件时两个按钮会停在禁用态且界面无出口；既然事实已判定为未运行，就把 UI
            # 收敛回待机（_set_running_ui 会重新启用开始按钮）再告知用户。
            self._set_running_ui(False)
            QMessageBox.warning(self, i18n.tr("警告"), i18n.tr("没有正在运行的录制进程！"))
            return
        self.recorder.stop_async()
        self.dashboard.start_btn.setEnabled(False)
        self.dashboard.stop_btn.setEnabled(False)

    def open_downloads_folder(self) -> None:
        # 目录不存在就先建：首次启动还没录过任何东西时点「打开目录」，
        # 报「路径不存在」对用户毫无价值。
        path = self.downloads_dir
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self._queue_log(i18n.tr("已打开下载目录: {path}", path=path))
        except Exception as e:
            self._queue_log(i18n.tr("打开目录失败: {err}", err=e), "error")

    def open_advanced_settings(self) -> None:
        # 单例化：连点会开出两个编辑器同时改同一份 config.ini，后保存者静默覆盖先保存者。
        dialog = self._advanced_dialog
        if dialog is not None and dialog.isVisible():
            dialog.set_focus()
            self._queue_log(i18n.tr("高级设置窗口已打开，已为你切换到该窗口"))
            return
        # M-35：旧实现在「旧实例不可见」时直接 new 一个覆盖引用，旧实例既无 WA_DeleteOnClose
        # 也无 deleteLater()、parent 又是主窗口 → C++ 对象与其 QPlainTextEdit（含整份 config
        # 文本）一直存活。现改为：已存在则复用（先重载磁盘内容）+ 置 WA_DeleteOnClose，
        # 引用在 destroyed 里清空，避免留下指向已析构对象的悬空属性。
        if dialog is not None:
            dialog.reload_from_disk()
            self._advanced_dialog = dialog
            dialog.show()
            dialog.set_focus()
            return
        dialog = AdvancedSettingsDialog(self, self.main_config_file, lambda msg: self._queue_log(msg))
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.destroyed.connect(self._on_advanced_dialog_destroyed)
        self._advanced_dialog = dialog
        dialog.show()

    def _on_advanced_dialog_destroyed(self) -> None:
        # M-35：destroyed 是 C++ 对象析构的最后一个信号，此时必须把 Python 侧引用清掉，
        # 否则下次 open_advanced_settings 会拿到一个已析构的包装对象（访问即 RuntimeError）。
        self._advanced_dialog = None

    # ─── 托盘 / 退出 ───

    def _setup_tray(self) -> None:
        # 托盘不可用时（部分 Linux 桌面环境、被组策略禁用）不抛错，退化为最小化到任务栏。
        # 图标在构造期就交给托盘：配置里记的路径可能已失效（用户删了文件），TrayIcon 内部
        # 「解不出就回落自绘」，故这里不必先判存在性，判了反而多一处会漂移的事实源。
        resolved = current_icon_path(self.app_root, self._icon_file_pref)
        candidate = TrayIcon(self, self._palette.tokens, str(resolved) if resolved is not None else "")
        if not candidate.is_available():
            self._queue_log(i18n.tr("系统托盘不可用，已改为最小化到任务栏"), "warn")
            # M-81（2026-10-21）：TrayIcon 在可用性判定**之前**就得先构造（is_available 是
            # 实例方法），而它的 QSystemTrayIcon 以主窗口为 parent——判定失败后直接 return
            # 会让 QSystemTrayIcon + QMenu + 5 个 QAction 永久挂在窗口对象树上（每次启动
            # 固定泄一份，且 deleteLater 是唯一能摘掉 Qt 侧父子引用的出口，Python 侧丢
            # candidate 引用并不析构 C++ 对象）。两条句柄都显式处置。
            candidate.icon.deleteLater()
            candidate.menu.deleteLater()
            return
        candidate.bind_actions(
            self.restore_from_tray,
            self.minimize_to_tray,
            self.quit_application,
            self.open_advanced_settings,
        )
        candidate.show()
        self.tray = candidate
        self._set_running_ui(self.recorder.is_running())

    def minimize_to_tray(self) -> None:
        # hide() 而非 showMinimized()：托盘模式下窗口不应继续占任务栏位置，
        # 否则「最小化到托盘」和「最小化」在用户看来没有区别。
        if self.tray is not None:
            self.hide()
            self.tray.notify(i18n.tr("程序已最小化到系统托盘，双击托盘图标可恢复窗口"))
        else:
            self.showMinimized()

    def restore_from_tray(self) -> None:
        # raise_() + activateWindow()：只调 show() 在部分窗口管理器下
        # 会让窗口出现在其它窗口后面，用户以为没恢复。
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_application(self) -> None:
        # 录制中先确认：退出会连带停掉录制并清理 ffmpeg，是不可逆的用户可见动作。
        # 清理放到后台线程，完成后经 shutdownFinished 回主线程销毁窗口，
        # 顺序反了会让清理线程随窗口一起被强杀、留下 ffmpeg 残进程。
        if self._quitting:
            return
        if self.recorder.is_running():
            answer = QMessageBox.question(self, i18n.tr("退出确认"), i18n.tr("录制正在后台进行，确定要退出吗？"))
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._quitting = True
        self._queue_log(i18n.tr("正在停止录制并清理 ffmpeg 进程，请稍候..."))
        self.recorder.shutdown_async(on_finished=lambda: self.shutdownFinished.emit())

    def _finalize_quit(self) -> None:
        # 置位必须在 close() 之前：closeEvent 见到 _quitting 才 accept，
        # 否则它会弹出「最小化 / 退出」对话框——退出路径弹出模态框等于把进程钉在这里
        # （离屏/无显示环境下更是直接卡死）。
        self._quitting = True
        self._log_timer.stop()
        self._status_timer.stop()
        self._danmaku_timer.stop()
        self.danmaku.stop()
        self.dashboard.dot.stop()
        self.sidebar_dot.stop()
        if self.tray is not None:
            self.tray.hide()
        self.close()
        # S-03（2026-10-19）：`setQuitOnLastWindowClosed(False)`（app.py 为托盘语义必须关掉）之后，
        # `close()` 只是销毁窗口、**不会**让 Qt 事件循环返回——旧实现到此结束，于是「彻底退出」
        # 只关掉界面，进程留在后台（托盘图标已 hide、任务栏无窗口，用户只能去任务管理器杀）。
        # 必须显式 quit() 才能让事件循环退出、装配函数返回。
        # 取 instance() 而不是持有 app 引用：本类在离屏测试里也实例化，未必有 QApplication。
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 的重写点必须这个名
        # 标题栏 X：给「最小化到托盘 / 完全退出」两条路径。
        if self._quitting:
            event.accept()
            return
        event.ignore()
        box = QMessageBox(self)
        box.setWindowTitle(i18n.tr("关闭选项"))
        box.setText(i18n.tr("您可以最小化到系统托盘，或完全退出程序"))
        tray_btn = box.addButton(i18n.tr("最小化到托盘"), QMessageBox.ButtonRole.AcceptRole)
        quit_btn = box.addButton(i18n.tr("完全退出"), QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is tray_btn:
            self.minimize_to_tray()
        elif clicked is quit_btn:
            self.quit_application()
        else:
            _ = cancel_btn

    def toast_message(self, message: str) -> None:
        # 位置按宿主当前尺寸实时算：窗口缩放或侧栏折叠之后 Toast 仍然贴底居中
        host = self.centralWidget()
        if host is None:
            return
        self.toast.show_message(message, host.height(), host.width())

    def _resolve_window_size(self) -> tuple[int, int, int, int]:
        # 取 94% 而不是铺满：留一点边距，避免高分屏下窗口贴边后被任务栏压住底栏
        screen = self.screen()
        if screen is None:
            return 1180, 760, 900, 620
        size = screen.availableSize()
        width = min(1180, int(size.width() * 0.94))
        height = min(760, int(size.height() * 0.94))
        return width, height, min(900, width), min(620, height)
