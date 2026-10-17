# tests/test_gui_right_edge_fit.py — 右侧边框裁切回归锁（2026-10-17 修复）。
#
# 根因（两层）：
#   ① 源头：三条长提示标签初始 wraplength=0（不折行，按单行全文计入需求宽，单行 ~725-820px）
#      与 ui_kit 两处 tk.Text 默认 width=80 字符，把 root reqwidth 撑到 1248 > geometry 1120；
#   ② 机制：Tk grid 对「需求宽 > 分配宽」的 slave 是**裁切**而非收缩——页面右缘（卡片右边框
#      + 20px 右边距）被整段切掉，表现为用户截图里的「右边框显示不全」。
# 修复：gui.py 三标签初始 wraplength=scale_profile.px(320) + config 页提示补接
# _bind_adaptive_wraplength；ui_kit.EditorText/terminal_text 的 tk.Text 加 width=1；
# gui._raise_width_to_fit_content 把窗口宽与 minsize 宽抬到实测需求宽（clamp 屏幕可用区）。
#
# 锁两层：源码锁（无头可跑）钉住三处修复点不回退；真窗用例断言「整窗需求宽 ≤ 实际宽」
# 且每张卡片右缘都在页面实宽内——后者需要显示器，无显示环境 skip（与 test_ui_theme 同口径）。

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUI_SOURCE = (ROOT / "gui.py").read_text(encoding="utf-8")
GUI_TREE = ast.parse(GUI_SOURCE)
UI_KIT_SOURCE = (ROOT / "src" / "ui_kit.py").read_text(encoding="utf-8")

_MARKER = "\n@@FIT@@ "

# 子进程驱动真实 gui（不在 pytest 进程 import gui：DLR_GUI_PARENT 会跨用例污染 src.logger，
# 与 test_gui_wrap_hints 同一口径）。
_SCRIPT = r"""
import json
import sys
import tkinter as tk

out = {"skipped": None, "ok": False}
try:
    import gui

    root = tk.Tk()
    app = gui.LiveRecorderGUI(root)
    root.update_idletasks()
    root.update()
    out["root_req_w"] = int(root.winfo_reqwidth())
    out["root_w"] = int(root.winfo_width())
    pages = {}
    for name, page in app._pages.items():
        pages[name] = {
            "req_w": int(page.winfo_reqwidth()),
            "w": int(page.winfo_width()),
            # 卡片右缘（相对页面的 x + 宽）必须落在页面实宽内，留 1px 容差
            "cards_over": [
                int(c.winfo_x() + c.winfo_width()) - int(page.winfo_width())
                for c in page.winfo_children()
                if int(c.winfo_x() + c.winfo_width()) > int(page.winfo_width()) + 1
            ],
        }
    out["pages"] = pages
    out["ok"] = True
    root.destroy()
except tk.TclError as e:
    # 无显示环境（Linux CI 无 X server）：真窗用例跳过
    out["skipped"] = f"{type(e).__name__}: {e}"
except Exception as e:  # noqa: BLE001 - 把异常带回主进程断言
    out["error"] = f"{type(e).__name__}: {e}"
sys.stdout.write("\n@@FIT@@ " + json.dumps(out, ensure_ascii=True))
"""


def _fit_probe() -> dict[str, Any]:
    # 结果用带前缀的单行 JSON 回传（gui 启动日志会混出杂散行；ensure_ascii 防控制台码页）。
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"gui subprocess failed: {proc.stderr[-2000:]}"
    assert _MARKER in proc.stdout, f"no result marker in: {proc.stdout[-500:]}"
    # json.loads 返回 Any，显式收成 dict 以满足 no-any-return（看测试数据本身允许 Any）
    return cast("dict[str, Any]", json.loads(proc.stdout.split(_MARKER, 1)[1]))


class TestSourceLocks:
    def test_text_widgets_request_minimal_width(self) -> None:
        # tk.Text 默认宽 80 字符是撑爆 root reqwidth 的源头之一；两处工厂都必须显式 width=1
        # （实际宽度由 pack fill+expand 分配，1 只是请求值地板）。
        # EditorText 走 super().__init__、terminal_text 走 tk.Text(...)，统一按关键字实参判定。
        tree = ast.parse(UI_KIT_SOURCE)
        hits = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and any(
                kw.arg == "width" and isinstance(kw.value, ast.Constant) and kw.value.value == 1 for kw in n.keywords
            )
        ]
        assert len(hits) >= 2, f"ui_kit 的 tk.Text 工厂须有 width=1（EditorText/terminal_text），实际 {len(hits)} 处"

    def test_root_width_raised_to_fit_content(self) -> None:
        # _raise_width_to_fit_content 必须存在且在 _setup_ui 与 _apply_scale 两条路径都被调用——
        # 缺后者会在升档后字号变大、reqwidth 反超 geometry 时复发裁切
        defs = [
            n for n in ast.walk(GUI_TREE) if isinstance(n, ast.FunctionDef) and n.name == "_raise_width_to_fit_content"
        ]
        assert len(defs) == 1, "_raise_width_to_fit_content 须定义且唯一"

        # 两个类都有 _setup_ui（高级设置对话框 + LiveRecorderGUI 主窗），必须取主窗那个——
        # 对话框布局不参与整窗需求宽计算，锁错对象等于锁了空气。
        def _method_source(class_name: str, method: str) -> str:
            cls = next(n for n in ast.walk(GUI_TREE) if isinstance(n, ast.ClassDef) and n.name == class_name)
            fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method)
            src = ast.get_source_segment(GUI_SOURCE, fn)
            assert src, f"{class_name}.{method} 源码段提取失败"
            return src

        assert "_raise_width_to_fit_content" in _method_source("LiveRecorderGUI", "_setup_ui")
        assert "_raise_width_to_fit_content" in _method_source("LiveRecorderGUI", "_apply_scale")

    def test_hint_labels_have_initial_wraplength(self) -> None:
        # 三条长提示标签的构造调用必须带非零初始 wraplength（缺省 0 = 单行全文计入 reqwidth）。
        # 判定按文案前缀定位构造点，不依赖变量名。
        for needle in ("启动后将调用", "「切换画质」", "每行一个直播链接"):
            node = next(
                (
                    n
                    for n in ast.walk(GUI_TREE)
                    if isinstance(n, ast.Call)
                    and any(
                        isinstance(kw.value, ast.Call)
                        and any(isinstance(a, ast.Constant) and str(a.value).startswith(needle) for a in kw.value.args)
                        for kw in n.keywords
                        if kw.arg == "text"
                    )
                ),
                None,
            )
            assert node is not None, f"未找到提示标签构造点: {needle}"
            assert any(kw.arg == "wraplength" for kw in node.keywords), f"{needle} 标签缺初始 wraplength"


class TestRealWindowFit:
    def test_content_fits_window_without_right_clipping(self) -> None:
        result = _fit_probe()
        if result.get("skipped"):
            pytest.skip(f"无显示环境，跳过真窗用例: {result['skipped']}")
        assert result["ok"], result.get("error")
        # 双保险落地后：整窗需求宽不得超过实际宽（超过即 Tk grid 裁切右缘）
        assert (
            result["root_req_w"] <= result["root_w"]
        ), f"root reqwidth={result['root_req_w']} > width={result['root_w']}（右缘会被裁切）"
        for name, page in result["pages"].items():
            assert not page["cards_over"], f"{name} 页有卡片右缘超出页面实宽: {page}"
