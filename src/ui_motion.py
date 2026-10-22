# src/ui_motion.py
# GUI 动效层：动效等级 + 插值原语 + 系统「关闭动画」感知。
#
# 设计约束（延续 ui_theme/ui_kit 的分层约定）：
#   · 只有三档且默认克制：full/subtle/off。Tk 没有 GPU 合成，每帧都是 Tcl 层重绘，
#     after 链越密、控件越多占用越明显，故除档位外还设硬性帧数上限（MAX_FRAMES）。
#   · 降级优先于禁用：off 不是「什么都不做」，而是直接落到终态（位移归零、状态点停呼吸），
#     不留半途状态——半途状态就是用户看到控件卡在中间位置。
#   · 系统级无障碍优先于用户档位：Windows「在 Windows 中显示动画」关闭
#     （SPI_GETCLIENTAREAANIMATION = 0）与 Linux GNOME「减少动画」等价，一律压到 off。
#   · import 期零 Tk 对象：探测函数只在调用时读系统，纯插值函数可无头测。
# Tk 的硬限制：ttk 控件没有 alpha 通道、没有圆角与阴影，故「淡入」只能做不透明度等效的
# 位移+尺寸插值，卡片圆角只能落在 Canvas 自绘件上；不为「看起来有」堆无效代码。
from __future__ import annotations

import configparser
import subprocess
import sys
import tkinter as tk
from collections.abc import Callable
from typing import Final, final

from src.config_read import tolerant_config_parser
from src.web_config import update_or_append_config_line

# 动效等级（持久化值即 id 原文，必须是安全的配置值：无空格无分隔符）。
MOTION_IDS: Final[tuple[str, ...]] = ("off", "subtle", "full")

# 「跟随系统」哨兵 id（刻意不在 MOTION_IDS 内）：走 detect_system_animations()
# 探测的结果，且不写显式偏好。与 ui_theme 的 _FOLLOW_SYSTEM_ID 同一约定。
FOLLOW_SYSTEM_MOTION_ID: Final[str] = "_follow_system_"

# 各档的时长与帧数。full 才允许较长的滑入；subtle 是「能感到但不抢注意」；
# off 的帧数 1 意味着「一帧后即终态」。
_MOTION_TABLE: Final[dict[str, tuple[int, int]]] = {
    # id: (单段时长毫秒, 帧数)
    "off": (0, 1),
    "subtle": (110, 4),
    "full": (190, 10),
}

# 硬性帧数上限：即便调用方传了离谱的 duration/frames，落库时也按此收敛。
# 这是"流畅克制"的可机检形态——帧数上限与等级无关，避免低性能设备上
# 用户选 full 就把主线程占满。
MAX_FRAMES: Final[int] = 12
MIN_FRAME_MS: Final[int] = 8

# 页面滑入的位移量（逻辑像素 @100%，随 ScaleProfile 缩放）。8px 足够读出
# "新页面进来了"，再大就变成幻灯片切换、与"克制"矛盾。
PAGE_SLIDE_PX: Final[int] = 8
# 弹窗缩放起始比例：从 0.96 放大到 1.0。用缩放而非位移，因为弹窗没有"从哪来"的
# 方向语义；0.96 的幅度小到不像"弹出动画"、只像"落位时稳了一下"。
DIALOG_START_SCALE: Final[float] = 0.96
# 列表更新高亮的衰减步数与总时长。
ROW_HIGHLIGHT_FRAMES: Final[int] = 5
ROW_HIGHLIGHT_MS: Final[int] = 420

# 持久化落点：config.ini [GUI] gui_motion（与 gui_theme / gui_scale 同节）。
GUI_SECTION: Final[str] = "GUI"
MOTION_KEY: Final[str] = "gui_motion"


def is_valid_motion(value: str) -> bool:
    return value in MOTION_IDS


def detect_system_animations() -> bool:
    # 探测系统是否开了动画。False 表示系统侧已关闭（应降级为 off）。
    #   Windows：SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION=0x1042)，它已是「在 Windows
    #     中显示动画」的权威取值，不再叠加高对比度等开关。
    #   macOS：`defaults read -g reduceMotion` 为 1 / true 时判为关闭。
    #   其余平台（Linux/Wayland 等）无统一口径，一律返回 True——猜错的方向是「关掉用户要的
    #     动效」，宁可不动也不误关。
    # 任何异常都回 True：探测失败不得让界面失去反馈。
    if sys.platform == "win32":
        try:
            import ctypes

            enabled = ctypes.c_int(0)
            # SPI_GETCLIENTAREAANIMATION 的 pvParam 指向 BOOL；不声明 argtypes 时 ctypes 按
            # 默认 int 传值，恰好与 BOOL 同宽。返回值 0 = 取值失败，此时 enabled 仍是初值 0，
            # 会被误判成「动画已关」——故失败按 True 处理。
            ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
            return True if not ok else bool(enabled.value)
        except Exception:
            return True
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "reduceMotion"],
                capture_output=True,
                timeout=2,
            )
            return result.returncode != 0
        except OSError, subprocess.TimeoutExpired:
            return True
    return True


def effective_motion(motion_id: str, *, system_animations: bool | None = None) -> str:
    # 归一化「用户选择 + 系统开关」→ 实际生效等级。
    # 系统关闭动画时一律 off（优先于用户选择）；否则按用户选择归一化，非法值回落到
    # subtle 而非 off——默认要「有」只是「克制」，把非法配置解释成「全关」会让升级用户
    # 莫名失去全部反馈。
    enabled = detect_system_animations() if system_animations is None else system_animations
    if not enabled:
        return "off"
    if not is_valid_motion(motion_id):
        return "subtle"
    return motion_id


def load_motion_preference(config_file: str) -> str:
    # 读取 [GUI] gui_motion。返回 "" 表示未设置（节/键缺失、空值、非法值），
    # 调用方按 FOLLOW_SYSTEM_MOTION_ID 处理。
    parser = tolerant_config_parser()
    try:
        parser.read(config_file, encoding="utf-8-sig")
    except OSError, configparser.Error:
        return ""
    if not parser.has_section(GUI_SECTION):
        return ""
    raw = parser.get(GUI_SECTION, MOTION_KEY, fallback="").strip()
    return raw if is_valid_motion(raw) else ""


def save_motion_preference(config_file: str, motion_id: str) -> bool:
    # 持久化动效偏好。FOLLOW_SYSTEM_MOTION_ID 写空值（= 下次启动继续跟随系统）；
    # 其余必须是非空合法 id。通道与 gui_theme / gui_scale 一致。
    if motion_id == FOLLOW_SYSTEM_MOTION_ID:
        value = ""
    elif is_valid_motion(motion_id):
        value = motion_id
    else:
        raise ValueError(f"未知动效 id: {motion_id!r}（合法值: {MOTION_IDS}）")
    return update_or_append_config_line(config_file, GUI_SECTION, MOTION_KEY, value)


def ease_out(t: float) -> float:
    # 缓出（cubic ease-out）：起步快、收尾慢。这是页面滑入唯一该用的曲线——
    # 起步慢会让"点击后界面没反应"的错觉窗口变长。
    # 输入 t ∈ [0,1]，输出 ∈ [0,1]（1 - (1-t)^3）。纯函数，供无头测试。
    clamped = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - clamped) ** 3


def frame_plan(motion_id: str, duration_ms: int, frames: int) -> list[float]:
    # 由「等级 + 期望时长/帧数」算出逐帧进度序列（0.0 起、不含 1.0 终帧）。
    # 终帧不入返回：调用方在最后一帧后统一落终态，使「降级到 off」与「正常跑完」走同一条
    # 落地路径，不会出现停在 95% 的控件。off 档返回空列表，调用方据「空」直接落终态。
    if not is_valid_motion(motion_id):
        motion_id = "subtle"
    _base_ms, base_frames = _MOTION_TABLE[motion_id]
    if motion_id == "off" or duration_ms <= 0 or frames <= 0:
        return []
    total = min(frames, base_frames, MAX_FRAMES)
    if total <= 1:
        return []
    per_frame = max(MIN_FRAME_MS, duration_ms // total)
    return [ease_out((index + 1) / total) for index in range(total - 1)]


def lerp(start: float, end: float, t: float) -> float:
    # 线性插值。单独成函数是为了让"终值 = end 在 t=1 时精确成立"成为机检事实
    # （逐步累加会漂移，落在 Canvas 坐标上是肉眼可见的半像素错位）。
    return start + (end - start) * t


def _noop() -> None:
    # run_frames 的 on_done 缺省实现。命名成函数而非 `lambda: None` 是为了让
    # mypy 把它认成 Callable[[], None]（lambda 在该位置会被推成更宽的签名）。
    return None


@final
class MotionController:
    # 动效运行时状态：有效等级 + 已登记的 after 句柄。
    #
    # 为什么自己管句柄：Tk 的 after 回调在窗口销毁后仍会触发一次，而动效回调里要写
    # Canvas 坐标/place 位置，对象已死就是 TclError。故每条链的句柄登记在册，
    # cancel()/cancel_all() 统一撤销（含对 Tcl 的 after_cancel），
    # 且回调入口先按链令牌核对自己的 job 是否仍然有效。
    # [历史注] 本段原文引用了一个从未存在的 disable() 方法（2026-10-21 M-82 复核证伪，
    # 真实撤销出口只有 cancel/cancel_all 两处）；且旧实现的 cancel 只清 Python 侧字典、
    # 从不 after_cancel，被「撤销」的链仍会被 Tcl 事件队列唤醒写完剩余帧。
    def __init__(self, motion_id: str = "subtle") -> None:
        self._motion_id: str = motion_id if is_valid_motion(motion_id) else "subtle"
        # 登记项 = (排帧用的 root, 最新 after 句柄, 链令牌)。root 与令牌都是 M-82 补的：
        # after_cancel 要 root 才打得出去；令牌让 _step 入口能分辨「这条链还是不是我」。
        # root 为 None 表示「裸句柄登记」（诊断/测试形态），cancel 时只清册不调 after_cancel。
        self._jobs: dict[str, tuple[tk.Misc | None, str, int]] = {}
        self._next_token: int = 0

    @property
    def motion_id(self) -> str:
        return self._motion_id

    @property
    def enabled(self) -> bool:
        # 「是否产生任何 after 链」。off 档恒 False，调用方可用它跳过整段动效代码
        # （省掉的不只是动画，还有每帧的 Canvas 重绘开销）。
        return self._motion_id != "off"

    def set_motion(self, motion_id: str) -> str:
        # 切换等级。切到 off 时立即撤销全部在途链（否则关掉动效后仍有旧链在跑）。
        if not is_valid_motion(motion_id):
            motion_id = "subtle"
        if motion_id == self._motion_id:
            return self._motion_id
        self._motion_id = motion_id
        if motion_id == "off":
            self.cancel_all()
        return self._motion_id

    def cancel(self, job_key: str) -> None:
        # 撤销一条链（按 key，不是按句柄——调用方不该关心句柄值）。
        # M-82：旧实现只 pop 字典——已排进 Tcl 事件队列的下一帧回调仍会被唤醒并继续写
        # place/几何，正是「关掉动效后控件还在抖、页面切完旧控件被拽回中途位置」的形态。
        # 定稿 = 先摘册再对该句柄 after_cancel；已经在执行当帧的迟到回调由 _step 入口的
        # 令牌守卫兜住（摘册即失效）。after_cancel 传空串/已触发句柄是 no-op，不额外判。
        entry = self._jobs.pop(job_key, None)
        if entry is None:
            return
        root, after_id, _token = entry
        if root is not None and after_id:
            try:
                root.after_cancel(after_id)
            except tk.TclError:
                # 窗口已销毁：Tcl 层没有待取消项可撤，属正常收尾，不得把退出路径上的
                # 清理动作连带打断。
                pass

    def cancel_all(self) -> None:
        # 撤销全部在途链。逐条走 cancel：句柄既要从册上摘掉，也要真的 after_cancel
        # （M-82 前只 clear 字典，被「撤销」的链照跑不误）。
        for job_key in list(self._jobs):
            self.cancel(job_key)

    def track(self, job_key: str, after_id: str, root: tk.Misc | None = None, token: int = -1) -> None:
        # 登记一条链的句柄。key 重复时旧的已失效，不再单独 cancel（_step 入口的令牌
        # 守卫会认出「登记已被本 key 的新链替换」并让旧链静默终止；[历史注] 原注释引用
        # 的 call_with_tracking 并不存在，守卫实现在 run_frames 的闭包里，2026-10-21 M-82
        # 按真实形态改正）。
        self._jobs[job_key] = (root, after_id, token)

    def run_frames(
        self,
        root: tk.Misc,
        job_key: str,
        apply: Callable[[float], None],
        *,
        duration_ms: int,
        frames: int,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        # 跑一条插值链：逐帧调 apply(progress)，最后一帧之后调 on_done。
        # off 档 / 参数非法时**同步**落终态并调 on_done——不排 after、不留半途状态。
        # 这是「降级优先于禁用」在代码里的唯一落点，其余调用点不必各自判 enabled。
        self.cancel(job_key)
        # on_done 是可选形参，但「落终态」是本方法的契约：缺省补一个空实现，
        # 好过在每个分支写 `if on_done is not None`（漏一处就静默停在半途）。
        finish: Callable[[], None] = on_done if on_done is not None else _noop
        plan = frame_plan(self._motion_id, duration_ms, frames)
        if not plan:
            finish()
            return
        per_frame = max(MIN_FRAME_MS, duration_ms // (len(plan) + 1))
        # 链令牌：本条 run_frames 调用的唯一标识。cancel/cancel_all 摘册、同 key 换新链
        # 都会让它对不上号，_step 据此在入口终止已失效的链（M-82）。
        self._next_token += 1
        token = self._next_token

        def _step() -> None:
            # 守卫①（M-82）：链是否仍然有效——登记缺失（被 cancel/cancel_all 撤销，含
            # 切 off 的收尾）或令牌更替（同 key 已被新链接管）时，本次唤醒属于「已撤销
            # 排程的迟到回调」：既不写几何，也不代落终态（终态由撤销方负责，落它反而
            # 把用户/调用方新设的状态打回旧链的半途）。
            entry = self._jobs.get(job_key)
            if entry is None or entry[2] != token:
                return
            # 守卫②：窗口已销毁时 Tk 仍会调回调一次，写坐标即 TclError。这里统一兜住并直接
            # 收尾，不把异常抛进 mainloop。
            try:
                progress = plan.pop(0)
                apply(progress)
            except tk.TclError:
                self.cancel(job_key)
                finish()
                return
            if plan:
                self.track(job_key, cast_after(root.after(per_frame, _step)), root, token)
            else:
                self.cancel(job_key)
                finish()

        apply(plan[0])
        plan.pop(0)
        if plan:
            self.track(job_key, cast_after(root.after(per_frame, _step)), root, token)
        else:
            finish()


def cast_after(value: str) -> str:
    # root.after 返回 Tk 的 after id（存根是 str|None）。运行期不会是 None，但类型上需要
    # 收敛；这里显式给一个可复核的落点而不是散落 cast。None 只在 Tk 内部异常时出现，用空串
    # 占位即可（track 存空串不影响正确性，cancel 只是删 key），比塞一个假 id 更好排查。
    return value if isinstance(value, str) else ""
