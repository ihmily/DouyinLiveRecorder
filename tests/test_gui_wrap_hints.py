# tests/test_gui_wrap_hints.py — 长提示文案自适应折行回归锁。
#
# 根因：长文案标签的请求宽超出父容器分配宽时，Tk pack 按默认 anchor=center **两侧对称裁切**
# （150% DPI 下控制台提示与弹幕占位提示两侧各缺半个字；定宽 wraplength=1000 在窄窗口
# 下同样右缘裁切）。
# 修复（gui.py）：_compute_wraplength 纯函数 + _bind_adaptive_wraplength（防抖 + 迟滞地把
# wraplength 绑到标签自身窗口宽，要求 fill/sticky 拉伸）+ 占位文案收敛到两个工厂。
# 平台事实：ttk 的 wraplength 是原始设备像素、不随 tk scaling 缩放（Tk 9.0 探针实测），
# 故换算不除缩放率；历史锚点 1584@1.5→1050 与新锚点 1584→1576 在 150% DPI 下视觉等价。
#
# 三层锁：纯函数单测与 AST 源码锁无头可跑（Linux CI 全量执行）；真窗用例需要显示器，
# 无显示环境 skip——与 tests/test_ui_theme.py 的 TestApplyTtk 同一口径。

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUI_SOURCE = (ROOT / "gui.py").read_text(encoding="utf-8")
GUI_TREE = ast.parse(GUI_SOURCE)

_MARKER = "\n@@WRAP@@ "

# 子进程驱动真实 gui 代码（不在 pytest 进程 import gui：DLR_GUI_PARENT 会跨用例污染 src.logger）。
# compute/should_apply：纯函数；window：真窗验证 fill=X 标签窄容器自动折行、加宽后 wraplength 增长。
_SCRIPT = r"""
import json
import sys
import time

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

out = {"skipped": None, "ok": False}
try:
    import gui
    import i18n as i18n_module

    # 语言钉定：gui 静态标签经 ui_i18n.T 建时查表（2026-10-04 起），译文形态取决于
    # config.ini 的 language 与宿主 locale（本探针子进程不经过 conftest 的恒等映射）。
    # stress 分支按简中源文前缀匹配 4 个绑定标签，故这里固定 zh_CN，让断言与宿主语言解耦。
    i18n_module.set_language("zh_CN")

    req = json.loads(sys.stdin.read())
    if req["call"] == "compute":
        out["result"] = gui._compute_wraplength(req["width"], req.get("margin", 8))
        out["ok"] = True
    elif req["call"] == "should_apply":
        out["result"] = gui._wrap_should_apply(req["current"], req["new"])
        out["ok"] = True
    elif req["call"] == "window":
        # [阶段5] CTk 摘除后生产面即 ttk/tk：真窗用例改用原生控件 + tkfont 点值字体
        # （与 gui.Fonts 同款），折行机制判据不变。
        root = tk.Tk()
        root.geometry("1120x300")
        body = ttk.Frame(root)
        body.pack(fill=tk.X, padx=18)
        b1 = ttk.Button(body, text="start", padding=(20, 8))
        b1.pack(side=tk.LEFT, padx=(0, 12))
        b2 = ttk.Button(body, text="stop", padding=(20, 8))
        b2.pack(side=tk.LEFT)
        label = ttk.Label(
            body, text=req["text"], font=tkfont.Font(family="Microsoft YaHei UI", size=-9),
            anchor="w", justify="left",
        )
        label.pack(side=tk.LEFT, padx=20, fill=tk.X, expand=True)
        gui._bind_adaptive_wraplength(label)
        root.update_idletasks()
        root.update()
        # 2026-09-29 卡死修复后写入是防抖的（风暴安静 120ms 才结算），读数前等防抖落地
        time.sleep(0.4)
        root.update()
        narrow_wrap = int(label.cget("wraplength"))
        narrow_req = int(label.winfo_reqwidth())
        narrow_win = int(label.winfo_width())
        root.geometry("1600x300")
        root.update_idletasks()
        root.update()
        time.sleep(0.4)
        root.update()
        wide_wrap = int(label.cget("wraplength"))
        out.update(
            narrow_wrap=narrow_wrap,
            narrow_req=narrow_req,
            narrow_win=narrow_win,
            wide_wrap=wide_wrap,
            clipped_narrow=narrow_req > narrow_win + 1,
            ok=True,
        )
        root.destroy()
    elif req["call"] == "stress":
        # 2026-09-29 卡死回归锁：DPI 反复翻转（用户跨屏拖拽的真实路径）。修复前绑定追逐
        # 每次瞬时宽度写 wraplength，几何失效排进 idle 队列使其永不排空（120s 泵不完 =
        # 卡死）；修复后防抖 + 迟滞，必须能排空。[阶段5] 风暴源改为 `tk scaling` 翻转——
        # 点值字体随 scaling 重排触发全窗几何失效，等价模拟跨 DPI 拖拽（CTk 的
        # set_widget_scaling 随依赖摘除退役）。
        root = tk.Tk()
        app = gui.LiveRecorderGUI(root)
        # gui 构造期会按 config.ini/宿主 locale 重设语言（_build_sidebar 的 set_language），
        # 本探针宿主解析为 en_US、静态标签因此是英文；下面按简中源文前缀匹配绑定标签，
        # 故构造后统一切回 zh_CN 并重译静态标签（与用户在语言菜单切回简中同一条路径）。
        from src import ui_i18n

        i18n_module.set_language("zh_CN")
        ui_i18n.retranslate_all()
        root.geometry("1120x740")
        root.update_idletasks()
        root.update()

        def find_labels(widget, acc):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Label):
                    acc.append(child)
                find_labels(child, acc)
            return acc

        targets = {}
        for lb in find_labels(root, []):
            t = str(lb.cget("text"))
            for prefix in ("启动后将调用", "暂无弹幕监控数据", "暂无录制中的直播间", "「切换画质」"):
                if t.startswith(prefix):
                    targets[prefix] = lb

        changes = {k: 0 for k in targets}
        last = {k: 0 for k in targets}

        def make_cb(key, widget):
            def cb(event=None):
                cur = int(widget.cget("wraplength"))
                if cur != last[key]:
                    changes[key] += 1
                    last[key] = cur

            return cb

        for k, lb in targets.items():
            lb.bind("<Configure>", make_cb(k, lb), add="+")

        base = float(root.tk.call("tk", "scaling"))
        for s in (base, base * 1.5, base, base * 1.5, base, base * 1.5, base, base * 1.5):
            root.tk.call("tk", "scaling", s)
            end = time.time() + 0.15
            while time.time() < end:
                root.update()
                time.sleep(0.004)
        out.update(changes=changes, ok=True)
        root.destroy()
    else:
        raise SystemExit("unknown call: " + req["call"])
except tk.TclError as e:
    # 无显示环境（Linux CI 无 X server）：真窗用例跳过；compute 调用不建窗，不受影响
    out["skipped"] = f"{type(e).__name__}: {e}"
except Exception as e:  # noqa: BLE001 - 把异常带回主进程断言
    out["error"] = f"{type(e).__name__}: {e}"
sys.stdout.write("\n@@WRAP@@ " + json.dumps(out, ensure_ascii=True))
"""


def _wrap_call(call: str, **kwargs: Any) -> dict[str, Any]:
    # 结果用带前缀的单行 JSON 回传：GUI 可能向 stdout 混出杂散行，前缀标记让解析与杂散
    # 输出解耦；回传侧 ensure_ascii=True 免受控制台码页影响。
    payload = json.dumps({"call": call, **kwargs}, ensure_ascii=False)
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"gui subprocess failed: {proc.stderr[-2000:]}"
    assert _MARKER in proc.stdout, f"no result marker in: {proc.stdout[-500:]}"
    result: dict[str, Any] = json.loads(proc.stdout.split(_MARKER, 1)[1])
    return result


def _compute(width: int, margin: int = 8) -> int:
    # 经子进程驱动 gui._compute_wraplength 本体（非本地复刻）——测试自实现被测逻辑是假绿
    out = _wrap_call("compute", width=width, margin=margin)
    assert out["ok"], out.get("error")
    return int(out["result"])


class TestComputeWraplength:
    # 锚点：设备像素 - 边距 取整，下限 120。ttk wraplength = 原始设备像素（不随 tk scaling
    # 缩放），旧 CTk 换算 (width-margin)/scale 已退役——历史锚点 1584@1.5→1050 与
    # 新锚点 1584→1576 在 150% DPI 下视觉等价（1050×1.5≈1576）。
    def test_device_pixel_conversion(self) -> None:
        assert _compute(1584) == 1576
        assert _compute(2008) == 2000
        assert _compute(3008) == 3000

    def test_floor_at_120(self) -> None:
        # 极窄容器逐字折行也好过 wraplength→0（0 = 不折行 = 回到两侧裁切）
        assert _compute(50) == 120
        assert _compute(0) == 120

    def test_monotonic_in_width(self) -> None:
        values = [_compute(w) for w in (200, 400, 800, 1600)]
        assert values == sorted(values)


def _should_apply(current: int, new: int) -> bool:
    out = _wrap_call("should_apply", current=current, new=new)
    assert out["ok"], out.get("error")
    return bool(out["result"])


class TestWrapShouldApply:
    # 迟滞判据（2026-09-29 卡死修复的纯函数面）：滚动条出现/消失使容器宽 ±~11 逻辑像素，
    # 无迟滞时「折行变高→滚动条翻转→宽度变→再折行」在阈值边界无限互振。

    def test_first_apply_always(self) -> None:
        assert _should_apply(0, 300) is True

    def test_small_delta_suppressed(self) -> None:
        assert _should_apply(780, 772) is False  # 8 ≤ max(12, 15)
        assert _should_apply(300, 292) is False  # 8 ≤ 12

    def test_significant_delta_applies(self) -> None:
        assert _should_apply(780, 760) is True  # 20 > 15
        assert _should_apply(300, 287) is True  # 13 > 12

    def test_threshold_is_relative_to_value(self) -> None:
        # 大值用 2%（更宽容），小值用 12px 下限——保证同一像素噪声在不同字号下都被吸收
        assert _should_apply(1500, 1490) is False  # 10 ≤ 30
        assert _should_apply(1500, 1460) is True  # 40 > 30


class TestSourceLocks:
    def test_bind_helper_defined_once_and_wired_to_five_sites(self) -> None:
        defs = [
            n for n in ast.walk(GUI_TREE) if isinstance(n, ast.FunctionDef) and n.name == "_bind_adaptive_wraplength"
        ]
        assert len(defs) == 1
        calls = [
            n
            for n in ast.walk(GUI_TREE)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_bind_adaptive_wraplength"
        ]
        # 5 个接线点：控制台按钮行提示、画质说明、画质占位工厂、弹幕占位工厂、
        # URL 配置页底部提示（右边框裁切修复时补接——原单行全文计入窗口 reqwidth）。
        assert len(calls) == 5, f"_bind_adaptive_wraplength 接线点应为 5，实际 {len(calls)}"

    def test_binding_is_debounced_hysteresis_and_guarded(self) -> None:
        # 卡死修复锁：绑定必须 ① 防抖（Configure 风暴期零写入——同步追写会喂进重缩放的
        # 递归 idle 泵，队列永不排空）② 迟滞判据 ③ 销毁竞态 TclError 守卫
        fn = next(
            n for n in ast.walk(GUI_TREE) if isinstance(n, ast.FunctionDef) and n.name == "_bind_adaptive_wraplength"
        )
        src = ast.get_source_segment(GUI_SOURCE, fn)
        assert src, "_bind_adaptive_wraplength 源码段提取失败"
        assert "after_cancel" in src and ".after(" in src, "缺防抖（after_cancel + after）"
        assert "_wrap_should_apply" in src, "缺迟滞判据"
        assert src.count("TclError") >= 2, "缺销毁竞态 TclError 守卫"

    def test_wrap_should_apply_defined_once(self) -> None:
        defs = [n for n in ast.walk(GUI_TREE) if isinstance(n, ast.FunctionDef) and n.name == "_wrap_should_apply"]
        assert len(defs) == 1

    def test_placeholder_text_defined_once_each(self) -> None:
        # 占位文案收敛进唯一工厂：刷新路径重建占位时必须复用工厂，禁止再写一份（曾经 4 处重复）
        for needle in ("暂无录制中的直播间", "暂无弹幕监控数据"):
            assert GUI_SOURCE.count(needle) == 1, f"{needle} 文案须只出现一次（工厂内）"

    def test_no_constant_wraplength_kwargs(self) -> None:
        # 定宽 wraplength（原 wraplength=1000）在窄窗口下重新引入右缘裁切；
        # gui.py 所有 wraplength 赋值必须流经 _bind_adaptive_wraplength 的动态值
        offenders = [
            node
            for node in ast.walk(GUI_TREE)
            if isinstance(node, ast.Call)
            for kw in node.keywords
            if kw.arg == "wraplength" and isinstance(kw.value, ast.Constant)
        ]
        assert not offenders, f"发现定宽 wraplength 调用点: {len(offenders)} 处"

    def test_placeholder_factories_use_stretch_and_bind(self) -> None:
        # 占位改 grid 叠放（sticky="ew"）：工厂丢掉拉伸或绑定会让折行静默失效
        for fn_name in ("_make_quality_placeholder", "_make_danmaku_placeholder"):
            fn = next(n for n in ast.walk(GUI_TREE) if isinstance(n, ast.FunctionDef) and n.name == fn_name)
            src = ast.get_source_segment(GUI_SOURCE, fn)
            assert src, f"{fn_name} 源码段提取失败"
            assert 'sticky="ew"' in src, f"{fn_name} 缺 sticky=ew（自适应折行前提）"
            assert "_bind_adaptive_wraplength" in src, f"{fn_name} 缺自适应绑定"

    def test_placeholder_single_instance_toggled_by_refresh(self) -> None:
        # 占位收敛为单实例：构建路径经工厂创建一次；刷新路径不再重建占位，改为
        # grid_remove/grid 切换可见性——锁两件事：① 工厂只被构建页调用；② 刷新路径必须经
        # _show_*_placeholder 切换（直接 tree.grid() 而漏掉占位会让空态文案残留）。
        pairs = {
            "_make_quality_placeholder": ("_build_quality_page", "_show_quality_placeholder"),
            "_make_danmaku_placeholder": ("_build_danmaku_page", "_show_danmaku_placeholder"),
        }
        for factory, (builder, toggler) in pairs.items():
            build_fn = next(n for n in ast.walk(GUI_TREE) if isinstance(n, ast.FunctionDef) and n.name == builder)
            build_src = ast.get_source_segment(GUI_SOURCE, build_fn)
            assert build_src and f"self.{factory}(" in build_src, f"{builder} 未复用 {factory}"
            # 刷新路径只允许经 toggle 触碰占位/表格可见性
            refresh_fn = next(n for n in ast.walk(GUI_TREE) if isinstance(n, ast.FunctionDef) and n.name == toggler)
            refresh_src = ast.get_source_segment(GUI_SOURCE, refresh_fn)
            assert refresh_src and "grid_remove" in refresh_src and ".grid()" in refresh_src
            update_fn_name = "_update_quality_display" if "quality" in factory else "_update_danmaku_display"
            update_fn = next(
                n for n in ast.walk(GUI_TREE) if isinstance(n, ast.FunctionDef) and n.name == update_fn_name
            )
            update_src = ast.get_source_segment(GUI_SOURCE, update_fn)
            assert update_src and f"self.{toggler}(" in update_src, f"{update_fn_name} 未经 {toggler} 切换空态"


class TestRealWindowWrap:
    def test_narrow_wraps_without_clipping_and_widens(self) -> None:
        result = _wrap_call(
            "window",
            text="启动后将调用 main.py 循环监测 URL 配置中的直播间并自动录制",
        )
        if result.get("skipped"):
            pytest.skip(f"无显示环境，跳过真窗用例: {result['skipped']}")
        assert result["ok"], result.get("error")
        assert not result[
            "clipped_narrow"
        ], f"窄容器下标签仍溢出（会两侧裁切）: reqwidth={result['narrow_req']} winfo_width={result['narrow_win']}"
        assert result["narrow_wrap"] >= 120
        # 加宽后 wraplength 必须跟随增长：绑在 <Configure> 上持续自适应，不是一次性初值
        assert (
            result["wide_wrap"] > result["narrow_wrap"]
        ), f"加宽后 wraplength 未增长: narrow={result['narrow_wrap']} wide={result['wide_wrap']}"

    def test_dpi_flip_stress_drains_event_loop_with_bounded_writes(self) -> None:
        # 卡死回归锁：DPI 反复翻转（用户跨屏拖拽走 check_dpi_scaling 同一回调链）下，
        # 事件循环必须能排空（修复前绑定追逐每次瞬时宽度写 wraplength，几何失效喂进
        # 递归 idle 泵，update() 永不返回，子进程直接超时）；且 wraplength 写入有界。
        result = _wrap_call("stress")
        if result.get("skipped"):
            pytest.skip(f"无显示环境，跳过真窗用例: {result['skipped']}")
        assert result["ok"], result.get("error")
        changes: dict[str, int] = result["changes"]
        # 防抖 + 迟滞下每次翻转至多结算一次；放宽到 24 防计时抖动，无界互振会远超此界
        assert all(v <= 24 for v in changes.values()), f"wraplength 写入无界（互振回归）: {changes}"
        # 防抖必须在位：四个绑定标签都被压力路径真实触达过
        assert len(changes) == 4, f"压力路径未触达全部绑定标签: {sorted(changes)}"
