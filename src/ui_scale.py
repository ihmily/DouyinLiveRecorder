# src/ui_scale.py
# GUI 度量层：语义字号 token + 间距 token + 全局缩放档位 + 偏好持久化。
#
# 设计约束（延续「一切走语义槽位」铁律；颜色那一半在 src/ui_theme.py，本模块管尺寸）：
#   · 字体只用**负数点值**（-N pt）：正数是屏幕像素、不随 `tk scaling` 跨 DPI 缩放，
#     高 DPI 屏上整窗偏小；点值由 Tk 按 scaling 换算，DPI 适配天然成立。pt() 是唯一
#     允许产出字号的入口，正数字号在本仓视为 bug。
#   · 缩放只改字号与间距，不改控件数量与信息密度——行高、padding、圆角随档位线性放大，
#     但表格列数、卡片结构、导航项全部不变，否则「放大界面」会退化成「重排信息架构」。
#   · DPI 与缩放是两件事：`tk scaling` 解决「同一物理大小在不同 DPI 下看起来一样大」，
#     缩放解决「用户主动要更大/更小」。本模块只管后者，但会读 `tk scaling` 参与小屏
#     降档判断（见 auto_scale_for_screen）。
#   · 持久化落 config.ini [GUI] gui_scale，通道与 ui_theme 的 gui_theme 一致
#     （update_or_append_config_line：行级替换 + 缺节补建 + 原子写），刻意不用
#     config_io.read_config_value——它写回时持 main.file_update_lock，GUI 进程不应
#     把 [GUI] 键的补写混进录制引擎的锁体系。
#   · import 期零 Tk 对象（本模块甚至不 import tkinter）：无头 Linux CI 可安全 import，
#     `import gui` 链路不受影响；一切 Tk 相关只在调用方传入 root 后发生。
from __future__ import annotations

import configparser
import math
from typing import Final, final

from src.config_read import tolerant_config_parser
from src.web_config import update_or_append_config_line

# ─── 字号体系（100% 档位下的目标点值 pt） ───────────────────────────────
#
# 取值依据：相邻档位至少差 1.5pt、辅助文字不得小于 10pt。原先 12/13 两档只差 1px，侧栏
# 状态文字与导航项糊成一档；表格/列表另立 label 档（原先复用 body，表格数字与正文同重、
# 扫读时没有锚点）。
#
# 单位是点值而非像素：Tk 的 1pt = 1.333px @96dpi，换算已含在 Tk 内部。
TYPE_SCALE: Final[dict[str, int]] = {
    # 辅助文字：卡片副标题、列标签、状态说明、时间戳、提示条
    "caption": 10,
    # 正文：按钮文字、导航项、输入框内容、占位文案
    "body": 12,
    # 表格/列表：Treeview 行与统计项标签（比正文轻一档，让数值更跳）
    "label": 11,
    # 表格数值：统计卡片的数字（比 label 重，与 label 成对使用）
    "stat": 16,
    # 小节标题：卡片标题、弹窗标题
    "heading": 14,
    # 页面/品牌标题
    "title": 19,
    # 大状态文字：控制台的「待 机 / 录制中」
    "display": 28,
    # 等宽：日志终端、URL 编辑器
    "mono": 11,
}

# 等宽字体单独一档：日志/配置是等宽语义，不能跟着比例字体一起放大到读不动。取 11pt
# 与 label 同档，缩放时按 0.9 系数跟随（等宽字符宽，放大后一行能装的列数骤减、行内
# 信息密度损失比比例字体大）。
MONO_SCALE_FACTOR: Final[float] = 0.9

# 字体族。比例字体沿用微软雅黑 UI（Windows 观感最稳），等宽沿用 Cascadia Code；
# 缺字族时 Tk 静默回退系统默认（Linux CI 无显示，不会走到）。
FONT_FAMILY: Final[str] = "Microsoft YaHei UI"
MONO_FAMILY: Final[str] = "Cascadia Code"

# ─── 间距体系（逻辑像素，100% 档位） ─────────────────────────────────────
#
# 4px 基准栅格。ttk 的 padding、Treeview 的 rowheight、页面内边距全部取自这里，
# 禁止在调用点写裸数字——否则「统一间距」无从机检，视觉一致性只能靠肉眼。
SPACING: Final[dict[str, int]] = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
}

# 控件体量的两档基线（ttk 靠 padding 撑起控件高度，没有像素级 height）。
CONTROL_PADDING: Final[tuple[int, int]] = (12, 7)  # 常规按钮
CONTROL_PADDING_COMPACT: Final[tuple[int, int]] = (10, 5)  # 紧凑按钮（工具栏/表格浮层）
CONTROL_PADDING_NAV: Final[tuple[int, int]] = (14, 10)  # 侧栏导航（体量最大，触控友好）
CONTROL_PADDING_ROW: Final[tuple[int, int]] = (6, 6)  # 表格行内浮层编辑器

# 表格行高（像素）：基准 32，缩放后不得低于 TREE_ROW_HEIGHT_MIN（30）——再低单行
# 文字上下缘贴边，长表格滚动时行与行之间没有分隔感。
TREE_ROW_HEIGHT: Final[int] = 32
TREE_ROW_HEIGHT_MIN: Final[int] = 30

# 根窗口与最小尺寸（逻辑像素 @100%）。缩放时按系数放大后必须再 clamp 到屏幕可用区，
# 否则 150% 档在 1366x768 上开出来就溢出屏幕（低分辨率屏的核心诉求）。
WINDOW_WIDTH: Final[int] = 1120
WINDOW_HEIGHT: Final[int] = 740
WINDOW_MIN_WIDTH: Final[int] = 920
WINDOW_MIN_HEIGHT: Final[int] = 620
# 侧栏宽度（逻辑像素 @100%）。导航项文字 + 左侧留白，超出即折行。
SIDEBAR_WIDTH: Final[int] = 230
# 缩放后窗口尺寸占屏幕可用区的上限比例：留出任务栏与窗口标题栏的位置，
# 免得「放大到 150%」的结果是窗口大到拖不动边角。
SCREEN_FILL_CEILING: Final[float] = 0.94
# 小屏降档阈值（屏幕可用宽/高的逻辑像素）。低于此值说明屏幕装不下 100% 档的
# 完整布局（如 1366x768 装 1120x740 虽够，但浏览器/任务栏吃掉一部分后很紧），
# 自动降一档。降档只做一次，不递归——避免在临界屏上反复横跳。
SMALL_SCREEN_WIDTH: Final[int] = 1400
SMALL_SCREEN_HEIGHT: Final[int] = 800

# ─── 缩放档位 ────────────────────────────────────────────────────────────

# 用户可选档位（百分比）。下限 85 是可读性地板：再小 sidebar 导航（10 字）与
# 状态胶囊（4 字）会撞行；上限 150 是布局天花板：再大侧栏两列信息网格会挤成两行。
SCALE_PRESETS: Final[tuple[int, ...]] = (85, 100, 115, 130, 150)

# 「自动」哨兵 id（刻意不在 SCALE_PRESETS 内）：选中即清空显式偏好、按屏幕可用区
# 现算档位，下次启动继续跟随（与 _FOLLOW_SYSTEM_ID 同一套「写空值 = 跟随」的约定）。
AUTO_SCALE_ID: Final[str] = "_auto_scale_"

# 持久化落点：config.ini [GUI] gui_scale（键名无 configparser 分隔符 = :）。
GUI_SECTION: Final[str] = "GUI"
SCALE_KEY: Final[str] = "gui_scale"

# 自动档在「小屏」与「正常屏」之间取的那一档。取 85（可读性地板）而不是 100：
# 小屏上真正的问题是放不下，降一档比让用户自己发现「界面被裁掉了」更省事。
AUTO_SCALE_SMALL: Final[int] = 85
AUTO_SCALE_NORMAL: Final[int] = 100


def clamp_scale(value: int) -> int:
    # 把任意整数夹到合法缩放区间。持久化值来自用户手改的 config.ini，可能是
    # 40 或 900；不夹会得到不可读的界面或撑爆布局（下限 70 / 上限 200 超出
    # SCALE_PRESETS 的设计区间但仍是「可读」的应急值，菜单里不暴露这两个值）。
    return max(70, min(200, value))


def is_valid_scale(value: int) -> bool:
    # 菜单展示用：只认 SCALE_PRESETS 里的档位；70/200 这些应急夹取区间仍可用于渲染，
    # 但不会出现在下拉里，避免用户面对一串没意义的百分比。
    return value in SCALE_PRESETS


def parse_scale(raw: str) -> str:
    # 归一化持久化/配置里的原始值。返回 SCALE_PRESETS 的百分比字符串、
    # AUTO_SCALE_ID、或 ""（未设置/非法 → 调用方按「自动」处理）。
    # 与 ui_theme.load_theme_preference 同一容错口径：配置损坏绝不能让 GUI 起不来。
    text = raw.strip()
    if not text:
        return ""
    if text == AUTO_SCALE_ID or text == "auto":
        return AUTO_SCALE_ID
    try:
        value = int(float(text))
    except ValueError:
        # "115%" 这类带百分号的写法在用户手改配置时很常见，静默按「自动」兜底
        return ""
    return str(value) if is_valid_scale(value) else ""


def auto_scale_for_screen(screen_width: int, screen_height: int) -> int:
    # 自动档的纯函数形态（供无头测试与 gui 复用）：按屏幕可用区给小屏降一档。
    # 两个维度取「更严格」的一方（or）：1366x900 与 1920x700 都属于任一维度装不下，
    # 只看宽会让竖屏小窗口用户拿到 100% 而横向溢出。
    if screen_width < SMALL_SCREEN_WIDTH or screen_height < SMALL_SCREEN_HEIGHT:
        return AUTO_SCALE_SMALL
    return AUTO_SCALE_NORMAL


def load_scale_preference(config_file: str) -> str:
    # 读取 [GUI] gui_scale。返回 "" 表示「未设置」（节/键缺失、值为空、值非法），
    # 调用方按「自动」处理——用户没选过时保持按屏幕现算，而不是钉死某个百分数
    # （换台分辨率不同的机器就再也不对了）。
    parser = tolerant_config_parser()
    try:
        parser.read(config_file, encoding="utf-8-sig")
    except OSError, configparser.Error:
        return ""
    if not parser.has_section(GUI_SECTION):
        return ""
    return parse_scale(parser.get(GUI_SECTION, SCALE_KEY, fallback=""))


def save_scale_preference(config_file: str, scale: str) -> bool:
    # 持久化缩放偏好。scale 取 parse_scale 的归一化形态（百分比串或 AUTO_SCALE_ID）或 ""
    # （清空显式偏好 = 回到自动）。False = 文件不存在等不可写情形，调用方告警但不阻断
    # 内存态切换（与 gui_theme 同一容错口径）。
    normalized = scale if scale == AUTO_SCALE_ID else parse_scale(scale)
    return update_or_append_config_line(config_file, GUI_SECTION, SCALE_KEY, normalized)


@final
class ScaleProfile:
    # 一次解析出来的「当前缩放上下文」：档位 + 由此派生的字号/间距/尺寸。
    #
    # 为什么是对象而不是散落的模块级全局：Fonts（gui.py）、ui_theme、ui_kit 三处都要读
    # 同一份缩放态，散落全局必然出现「改了一半忘了另一处」的中间态，而在 ttk 上表现为
    # 部分控件字号错乱——比全错更难查。对象让「读同一份」成为类型层面的事实。
    #
    # 不可变：所有派生值在构造期一次算完；运行中改档位一律新建 profile 整体替换（字体缓存
    # 随 profile 一起换 key），不做「就地改字段」。
    def __init__(self, percent: int) -> None:
        # percent 是百分比（100 = 基准）。夹取在这里做，构造出的对象永远合法，
        # 下游的 pt()/px() 不必各自防守。
        self.percent: int = clamp_scale(percent)
        # 缩放系数：像素量用它，点值用 pt_scale（点值不按比例放大，见 pt 的注释）。
        self.factor: float = self.percent / 100.0

    def __eq__(self, other: object) -> bool:
        # 显式实现：dataclass 会在字段增加时静默改变相等语义（新增派生字段被算进
        # __eq__ 后，字体缓存键会随无关字段抖动）；这里只认 percent 这一个真值源。
        if not isinstance(other, ScaleProfile):
            return NotImplemented
        return self.percent == other.percent

    def __hash__(self) -> int:
        return hash(self.percent)

    def __repr__(self) -> str:
        return f"ScaleProfile(percent={self.percent})"

    def px(self, base: int) -> int:
        # 逻辑像素量按系数缩放（至少 1px，避免 4px * 0.85 舍入成 3 时栅格错位）。
        return max(1, round(base * self.factor))

    def pt(self, token: str) -> int:
        # 字号档位 → tk 字号（**负数点值**）。点值不随 factor 线性放大：点本身已是与 DPI
        # 无关的物理量，再乘一次用户系数会让 150% 档的正文达到 18pt（约 24px @96dpi），
        # 行高与卡片全部撑爆——这不是「更清晰」，是布局失效。折中是乘 sqrt 级别的温和
        # 系数，见 _pt_gain。
        if token not in TYPE_SCALE:
            raise KeyError(f"未知字号 token: {token!r}（合法值: {tuple(TYPE_SCALE)}）")
        return -max(7, round(TYPE_SCALE[token] * self._pt_gain))

    def mono_pt(self) -> int:
        # 等宽字号：与比例字体同档起算，但按 MONO_SCALE_FACTOR 收敛，避免等宽字符
        # 随放大变宽导致一行能装的列数骤减（日志/URL 编辑器是逐行阅读场景）。
        return -max(7, round(TYPE_SCALE["mono"] * self._pt_gain * MONO_SCALE_FACTOR))

    def spacing(self, token: str) -> int:
        if token not in SPACING:
            raise KeyError(f"未知间距 token: {token!r}（合法值: {tuple(SPACING)}）")
        return self.px(SPACING[token])

    def padding(self, base: tuple[int, int]) -> tuple[int, int]:
        # ttk padding 二元组（水平, 垂直）按系数缩放。
        return (self.px(base[0]), self.px(base[1]))

    def row_height(self) -> int:
        # Treeview 行高：缩放后不得低于 TREE_ROW_HEIGHT_MIN（下限存在的原因是
        # 85% 档下 32*0.85=27px，单行文字上下缘贴边、行间无分隔感）。
        return max(TREE_ROW_HEIGHT_MIN, self.px(TREE_ROW_HEIGHT))

    def window_size(self, screen_width: int, screen_height: int) -> tuple[int, int, int, int]:
        # 由缩放档位 + 屏幕可用区推出 (宽, 高, 最小宽, 最小高)，四值全部 clamp 到屏幕内。
        # clamp 的必要性：150% 档的 1680x1110 在 1366x768 上根本开不出来，
        # Tk 会让窗口超出屏幕右/下沿，用户连边角都拖不到。SCREEN_FILL_CEILING
        # 再留 6% 余量给标题栏与任务栏。
        if screen_width <= 0 or screen_height <= 0:
            # 拿不到屏幕尺寸（无头/异常环境）时不做 clamp，只按系数给尺寸——
            # 宁可能开大一点，也不要因为屏幕尺寸读不到就把窗口压成默认大小。
            return (
                self.px(WINDOW_WIDTH),
                self.px(WINDOW_HEIGHT),
                self.px(WINDOW_MIN_WIDTH),
                self.px(WINDOW_MIN_HEIGHT),
            )
        cap_w = int(screen_width * SCREEN_FILL_CEILING)
        cap_h = int(screen_height * SCREEN_FILL_CEILING)
        width = min(self.px(WINDOW_WIDTH), cap_w)
        height = min(self.px(WINDOW_HEIGHT), cap_h)
        # 最小宽高同样受屏幕约束，但不能大于目标宽高（否则 minsize > geometry 时
        # Tk 会把窗口撑到 minsize，用户第一眼看到的尺寸就不是我们算的那个）。
        min_width = min(self.px(WINDOW_MIN_WIDTH), width)
        min_height = min(self.px(WINDOW_MIN_HEIGHT), height)
        return (width, height, min_width, min_height)

    def sidebar_width(self) -> int:
        return self.px(SIDEBAR_WIDTH)

    # 字号档位相对 100% 的温和增益：点值是物理量，直接乘 factor 太激进，用 (factor)^0.6
    # 让 150% 档得 1.30 倍、85% 档得 0.90 倍——用户能明确感到「变大了/变小了」，但布局
    # （行高/卡片）不会被撑坏。
    @property
    def _pt_gain(self) -> float:
        # 用 math.pow 而非 `factor ** 0.6`：typeshed 对 float.__pow__ 的重载在「指数为
        # float」时不覆盖、返回推成 Any（no-any-return 报错）；math.pow 的返回类型明确，
        # 不依赖运算符重载的推断。
        return math.pow(self.factor, 0.6)
