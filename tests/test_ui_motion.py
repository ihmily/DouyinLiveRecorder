# tests/test_ui_motion.py — src/ui_motion.py 的回归锁（阶段6 GUI 动效层）。
#
# 覆盖四条不变量：
#   1) 帧计划：off 档返回空列表（调用方据此同步落终态）、非off 档产出**不含终帧**的
#      严格递增序列（终帧由 on_done 统一落地，避免「停在 95%」的半途状态）；
#   2) 帧数上限：无论调用方传多大的frames，落库时都按等级与 MAX_FRAMES 收敛
#      （低性能设备上的硬保护）；
#   3) 无障碍优先：系统关闭动画时一律返回 off，优先于用户在设置里选的档位；
#   4) 持久化：[GUI] gui_motion 缺失/非法回退「未设置」，合法值经 update_or_append
#      行级写回且不破坏既有节与注释。
#
# 全部用例无头（不建 Tk 窗口）——Linux CI 全量执行。
# MotionController.run_frames 需要真实 Tk 事件循环，只用假 root 验证「off 档同步
# 落终态、不排 after」这条可无头判定的分支（这是本模块最容易被改坏的一条）。

import configparser
from pathlib import Path
from typing import Any

import pytest

from src.ui_motion import (
    DIALOG_START_SCALE,
    FOLLOW_SYSTEM_MOTION_ID,
    GUI_SECTION,
    MAX_FRAMES,
    MIN_FRAME_MS,
    MOTION_IDS,
    MOTION_KEY,
    MotionController,
    detect_system_animations,
    ease_out,
    effective_motion,
    frame_plan,
    is_valid_motion,
    lerp,
    load_motion_preference,
    save_motion_preference,
)


class FakeRoot:
    # 复刻 run_frames 用到的 after/after_cancel 协议，并记录调用与待触回调。
    # [历史注] 旧版刻意「不模拟取消语义」——M-82 定稿后 cancel 必须真的打 after_cancel，
    # 替身没有 after_cancel 一面的话新判据就无从取证；pending 表用来手动引爆炸掉的旧链
    # （模拟 Tcl 队列里已排好的迟到回调）。

    def __init__(self) -> None:
        self.after_calls: list[int] = []
        self.cancel_calls: list[str] = []
        self.pending: dict[str, Any] = {}

    def after(self, ms: int, callback: Any) -> str:
        self.after_calls.append(ms)
        job = f"after#{len(self.after_calls)}"
        self.pending[job] = callback
        return job

    def after_cancel(self, job: str) -> None:
        self.cancel_calls.append(job)
        self.pending.pop(job, None)


def _make_config(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "config.ini"
    cfg.write_text(body, encoding="utf-8-sig")
    return cfg


class TestMotionIds:
    def test_ids_are_stable(self) -> None:
        # 持久化值即 id 原文，改名会让既有用户的 config.ini 里的值全部失效
        assert MOTION_IDS == ("off", "subtle", "full")

    def test_is_valid(self) -> None:
        assert is_valid_motion("subtle") is True
        assert is_valid_motion("OFF") is False
        assert is_valid_motion("") is False
        # 「跟随系统」哨兵刻意不在 MOTION_IDS 内（它映射为空值而非某个等级）
        assert is_valid_motion(FOLLOW_SYSTEM_MOTION_ID) is False


class TestEaseOut:
    # 缓动曲线本体：页面滑入唯一该用的曲线（起步慢会让「点击后没反应」的错觉窗口变长）
    def test_endpoints(self) -> None:
        assert ease_out(0.0) == pytest.approx(0.0)
        assert ease_out(1.0) == pytest.approx(1.0)

    def test_clamped_out_of_range(self) -> None:
        assert ease_out(-0.5) == pytest.approx(0.0)
        assert ease_out(1.5) == pytest.approx(1.0)

    def test_starts_fast(self) -> None:
        # 起步快：t=0.25 时已走完全程的一半以上（线性只有 0.25）
        assert ease_out(0.25) > 0.5

    def test_monotonic(self) -> None:
        values = [ease_out(i / 20) for i in range(21)]
        assert values == sorted(values)


class TestLerp:
    def test_endpoints_exact(self) -> None:
        # 终值必须在 t=1 时**精确**等于 end：Canvas 坐标上差0.5px 就是肉眼可见的错位
        assert lerp(0, 100, 1.0) == 100
        assert lerp(0, 100, 0.0) == 0

    def test_midpoint(self) -> None:
        assert lerp(0, 100, 0.5) == pytest.approx(50)


class TestFramePlan:
    def test_off_returns_empty(self) -> None:
        # 空列表是「同步落终态」的信号：调用方不排 after、直接 on_done
        assert frame_plan("off", 190, 10) == []

    def test_plan_excludes_final_frame(self) -> None:
        # 终帧不在列表里：最后一帧之后统一走 on_done，正常跑完与降级到 off
        # 因此落在**同一条**落地路径上
        plan = frame_plan("full", 190, 10)
        assert plan
        assert max(plan) < 1.0, "帧序列不得含终帧"

    def test_plan_is_increasing(self) -> None:
        plan = frame_plan("full", 190, 10)
        assert plan == sorted(plan)
        assert len(set(plan)) == len(plan)

    def test_frames_capped_by_max(self) -> None:
        # 低性能设备的硬保护：即便调用方传 frames=1000，落库仍按 MAX_FRAMES 收敛
        plan = frame_plan("full", 10000, 1000)
        assert len(plan) <= MAX_FRAMES - 1

    def test_subtle_is_shorter_than_full(self) -> None:
        # 「流畅克制」的可机检形态：subtle 的帧数必须显著少于 full
        assert len(frame_plan("subtle", 190, 10)) < len(frame_plan("full", 190, 10))

    def test_nonpositive_duration_is_empty(self) -> None:
        assert frame_plan("full", 0, 10) == []
        assert frame_plan("full", 190, 0) == []

    def test_invalid_id_falls_back_to_subtle(self) -> None:
        # 非法 id 不得当成 off（那会让升级用户莫名失去全部反馈）
        assert frame_plan("nonsense", 190, 10) == frame_plan("subtle", 190, 10)


class TestEffectiveMotion:
    def test_system_off_overrides_user_choice(self) -> None:
        # 无障碍优先：系统关了动画，用户在设置里选 full 也不生效
        assert effective_motion("full", system_animations=False) == "off"
        assert effective_motion("subtle", system_animations=False) == "off"

    def test_system_on_keeps_user_choice(self) -> None:
        assert effective_motion("full", system_animations=True) == "full"
        assert effective_motion("off", system_animations=True) == "off"

    def test_invalid_id_falls_back_to_subtle(self) -> None:
        assert effective_motion("garbage", system_animations=True) == "subtle"

    def test_empty_id_means_follow_system(self) -> None:
        # 未设置偏好按 subtle 起评（而不是 off）——默认要有反馈，只是克制
        assert effective_motion("", system_animations=True) == "subtle"

    def test_detect_returns_bool(self) -> None:
        # 探测函数在任意平台都不得抛：它决定界面能不能起得来
        assert isinstance(detect_system_animations(), bool)


class TestMotionController:
    def test_defaults_to_subtle(self) -> None:
        assert MotionController().motion_id == "subtle"
        assert MotionController("nonsense").motion_id == "subtle"

    def test_enabled_reflects_motion_id(self) -> None:
        assert MotionController("off").enabled is False
        assert MotionController("subtle").enabled is True
        assert MotionController("full").enabled is True

    def test_set_motion_is_idempotent(self) -> None:
        mc = MotionController("subtle")
        assert mc.set_motion("subtle") == "subtle"
        assert mc.motion_id == "subtle"

    def test_switching_to_off_cancels_inflight(self) -> None:
        # 关掉动效必须立刻停掉在途的链，否则用户关了它圆点还在跳
        mc = MotionController("full")
        mc.track("rows:1", "after#1")
        mc.set_motion("off")
        assert mc.motion_id == "off"
        assert mc.enabled is False

    def test_off_runs_terminal_state_synchronously(self) -> None:
        # 本模块最关键的一条：off 档**不排 after**、同步调 on_done。
        # 若改成排 after，关闭动效就会在控件销毁后才落终态 → TclError 风暴。
        root = FakeRoot()
        mc = MotionController("off")
        seen: list[float] = []
        done: list[bool] = []
        mc.run_frames(
            root,  # type: ignore[arg-type]
            "k",
            seen.append,
            duration_ms=190,
            frames=10,
            on_done=lambda: done.append(True),
        )
        assert root.after_calls == [], "off 档不得排 after"
        assert done == [True], "off 档必须同步落终态"

    def test_enabled_motion_schedules_frames(self) -> None:
        root = FakeRoot()
        mc = MotionController("full")
        seen: list[float] = []
        mc.run_frames(root, "k", seen.append, duration_ms=190, frames=10)  # type: ignore[arg-type]
        # 第一帧同步应用，其余排 after；每帧间隔不得低于 MIN_FRAME_MS
        assert len(seen) == 1
        assert root.after_calls
        assert all(ms >= MIN_FRAME_MS for ms in root.after_calls)

    def test_cancel_is_idempotent(self) -> None:
        mc = MotionController("full")
        mc.track("k", "after#1")
        mc.cancel("k")
        mc.cancel("k")  # 再取消一次不得抛
        mc.cancel("never-registered")

    def test_cancel_issues_after_cancel(self) -> None:
        # M-82 行为锁①：cancel 必须对登记句柄真的调 after_cancel——只摘 Python 侧册子，
        # Tcl 事件队列里已排好的下一帧仍会被唤醒并继续写 place/几何（「关了动效控件还在抖」
        # 的确切成因；全文件此前零个 after_cancel 调用点）。
        root = FakeRoot()
        mc = MotionController("full")
        mc.run_frames(root, "page", lambda _p: None, duration_ms=80, frames=3)  # type: ignore[arg-type]
        assert root.after_calls and list(root.pending) == ["after#1"]
        mc.cancel("page")
        assert root.cancel_calls == ["after#1"], "撤销链必须撤掉 Tcl 侧排程，不只是清字典"

    def test_stale_chain_write_stops_after_cancel(self) -> None:
        # M-82 行为锁②：_step 入口必须核对「这条链还是不是我」。模拟 Tcl 队列不受控
        # （窗口销毁后被强调、或 cancel 与回调同轮竞态）把已撤销链的回调再唤起一次：
        # 既不写几何，也不代落终态——终态归撤销方，旧链补 finish() 反而把新状态打回半途。
        root = FakeRoot()
        mc = MotionController("full")
        seen: list[float] = []
        done: list[bool] = []
        mc.run_frames(
            root,  # type: ignore[arg-type]
            "page",
            seen.append,
            duration_ms=80,
            frames=3,
            on_done=lambda: done.append(True),
        )
        stale_cb = root.pending["after#1"]
        mc.cancel("page")
        stale_cb()
        assert len(seen) == 1, "被撤销链的迟到回调不得再写一帧几何"
        assert done == [], "迟到回调不得代落终态（终态由撤销方/新链负责）"

    def test_same_key_new_chain_invalidates_old_callback(self) -> None:
        # M-82 行为锁③：链令牌同族判据——同 key 重跑 run_frames 后，旧链已排回调被
        # 「新链接管」，旧回调醒来必须静默终止（否则两轮动效互写同一控件、互相拽回）。
        root = FakeRoot()
        mc = MotionController("full")
        writes: list[tuple[str, float]] = []
        mc.run_frames(root, "k", lambda p: writes.append(("old", p)), duration_ms=80, frames=3)  # type: ignore[arg-type]
        old_cb = root.pending["after#1"]
        mc.run_frames(root, "k", lambda p: writes.append(("new", p)), duration_ms=80, frames=3)  # type: ignore[arg-type]
        baseline = list(writes)  # 旧链被接管前的同步首帧是合法写入，判据只看接管之后
        old_cb()
        assert writes == baseline, "旧链迟到回调越界写入（令牌守卫失效）"

    def test_set_motion_off_after_cancels_pending(self) -> None:
        # 「切到 off 立即撤销全部在途链」这句既有契约，从 M-82 起才算真的可兑现：
        # 旧 set_motion('off') 只清册不 after_cancel，关动画后圆点照呼吸就是这条。
        root = FakeRoot()
        mc = MotionController("full")
        mc.run_frames(root, "rows:1", lambda _p: None, duration_ms=80, frames=3)  # type: ignore[arg-type]
        mc.set_motion("off")
        assert root.cancel_calls == ["after#1"]
        assert mc.enabled is False


class TestBlend:
    # blend 在 ui_kit（表格高亮衰减用），此处只锁「终点精确归位」——
    # 不精确归位会在表格行上留一层永久色偏。
    def test_endpoints_exact(self) -> None:
        from src.ui_kit import blend

        assert blend("#112233", "#445566", 0.0) == "#112233"
        assert blend("#112233", "#445566", 1.0) == "#445566"

    def test_midpoint(self) -> None:
        from src.ui_kit import blend

        assert blend("#000000", "#FFFFFF", 0.5) == "#808080"

    def test_out_of_range_ratio_is_clamped_to_endpoints(self) -> None:
        # M-83：ratio 越界（>1 / <0 / NaN）旧实现不校验——round(负权重通道) 拼出带负号或
        # 8+ 位的畸形「颜色串」，喂给 tag_configure 是**静默失败**（高亮衰减整段不可见、
        # 不留日志）。定稿一律钳回 [0,1]，越界退化为取端点，出口恒为合法 7 位串。
        from src.ui_kit import blend

        assert blend("#112233", "#445566", 1.5) == "#445566"
        assert blend("#112233", "#445566", -0.5) == "#112233"
        assert blend("#112233", "#445566", float("nan")) in ("#112233", "#445566")

    def test_invalid_color_input_returns_valid_hex(self) -> None:
        # M-83 另一半：颜色形状不合法（命名色 / 位数不对 / 非十六进制）时旧实现在
        # int(x, 16) 处当场 ValueError，打断调用方的每帧回调。定稿复用 src.ui_theme.is_valid_hex
        # 判形状（全仓唯一的 #RRGGBB 口径），非法输入回合法一侧、两侧都非法回中性黑。
        from src.ui_kit import blend
        from src.ui_theme import is_valid_hex

        assert blend("red", "#445566", 0.5) == "#445566"
        assert blend("#112233", "#12G456", 0.5) == "#112233"
        assert blend("red", "blue", 0.5) == "#000000"
        nasty = ("#11", "xyz", "#11223344", "", "not-a-color")
        assert all(
            is_valid_hex(blend(a, b, r))
            for a in nasty
            for b in (*nasty, "#112233")
            for r in (-1.0, 2.0, float("nan"), 0.5)
        ), "非法入参的出口不得是 tag_configure 吃不下 yet 不报错的畸形串"


class TestDialogConstants:
    def test_start_scale_is_near_one(self) -> None:
        # 弹窗从 0.96 放大到 1.0：幅度小到不像「弹出动画」、只像「落位时稳了一下」
        assert 0.9 <= DIALOG_START_SCALE < 1.0


class TestPersistence:
    def test_missing_section_is_unset(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[other]\nkey = value\n")
        assert load_motion_preference(str(cfg)) == ""

    def test_missing_key_is_unset(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[GUI]\ngui_theme = light\n")
        assert load_motion_preference(str(cfg)) == ""

    def test_valid_value_round_trips(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[GUI]\n")
        assert save_motion_preference(str(cfg), "full") is True
        assert load_motion_preference(str(cfg)) == "full"

    def test_follow_system_writes_empty(self, tmp_path: Path) -> None:
        # 「跟随系统」写空值 = 下次启动继续跟随系统（与 gui_theme 的「写空=跟随」同约定）
        cfg = _make_config(tmp_path, "[GUI]\n")
        assert save_motion_preference(str(cfg), FOLLOW_SYSTEM_MOTION_ID) is True
        assert load_motion_preference(str(cfg)) == ""

    def test_illegal_id_raises(self, tmp_path: Path) -> None:
        # 非法 id 静默写下去会让下次启动读到不可渲染的等级
        cfg = _make_config(tmp_path, "[GUI]\n")
        with pytest.raises(ValueError):
            save_motion_preference(str(cfg), "wild")

    def test_illegal_value_on_disk_is_unset(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[GUI]\ngui_motion = wild\n")
        assert load_motion_preference(str(cfg)) == ""

    def test_write_preserves_other_keys_and_comments(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[GUI]\n# 保留我\ngui_scale = 130\n")
        assert save_motion_preference(str(cfg), "off") is True
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(cfg, encoding="utf-8-sig")
        assert parser.get(GUI_SECTION, "gui_scale") == "130"
        assert parser.get(GUI_SECTION, MOTION_KEY) == "off"
        assert "# 保留我" in cfg.read_text(encoding="utf-8-sig")

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        assert save_motion_preference(str(tmp_path / "nope.ini"), "off") is False
