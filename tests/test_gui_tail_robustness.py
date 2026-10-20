# tests/test_gui_tail_robustness.py — tail 线程逐事件防护与 after 链无条件续期（M-15 / M-17）。
#
# 两条同族故障：M-17 tail 线程里 json.loads 有防护而 _danmaku_dispatch 的数值转换没有，
# 一条脏事件（如 ts 为 null）冒到最外层时 offset 已推进过整个 chunk，同批后续完好事件
# 全部丢失且零日志；M-15 弹幕刷新/状态刷新/日志 flush/UI 事件泵四条 after 自续期链把
# 「下一次 after」写在回调尾部，回调一抛未捕获异常就整页永久停止刷新（tail 首读还会回放
# 旧 JSONL 末尾 64KB 的历史脏记录，触发概率真实存在）。
#
# 两者必须同批断言：修 M-17 的逐事件 try 会把 M-15 的 float(None) 崩溃降级成静默丢一条；
# 加了 _as_float/_as_int 容错后逐事件防护的缺失又难以触发——单独看都能掩盖对方。
#
# 判据经**子进程**驱动真实实现（同 test_gui_monitor.py：pytest 进程 import gui 会注入
# DLR_GUI_PARENT）。桩只补状态字段与假控件，不重新实现判定逻辑。
#
# 桩的边界：
#   * FakeRoot.after 只记账、不起 Tk：锁「有没有续期」，「续期后真跑到」属真窗范畴；
#   * FakeText 的 boom 按方法名触发（一律抛会把渲染失败与取队列失败混成一个结论）；
#   * _danmaku_dispatch 的投毒只废 room==BAD 那一条，其余事件仍进真实实现；
#   * 桩实例走 object.__new__ 跳过 Tk 构造：被测方法读到的字段必须在 base_stub() 补齐，
#     缺一个即 AttributeError，不会静默通过。

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUI_SOURCE = (ROOT / "gui.py").read_text(encoding="utf-8")
# 结果载荷与杂散 stdout 的分隔锚点：Tk 初始化期会往 stdout 写非受控行，整段 parse 必
# JSONDecodeError。约定「marker 之后才是载荷」，父侧只按字节 find 锚点，其余输出一律忽略。
_MARKER = "\n@@WP_E_TAIL@@ "

# 子进程脚本整体是**一个字符串字面量**（不是本模块的作用域）：里面的名字全部取自真实 gui
# 与 stdlib，改脚本时不要在父侧再写一份。各场景在同一子进程里顺序跑完，隔离靠：
# ① 每个场景重建 base_stub()；② 对 gui 模块级对象的临时替换包在 try/finally 里还原；
# ③ out[...] 键名互不重复。
_SCRIPT = r"""
import json
import os
import queue
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import gui

out = {}


class FakeRoot:
    # 只记「排了什么延迟 / 排了哪个回调」，不真跑 Tk。
    def __init__(self):
        self.calls = []

    def after(self, delay, callback):
        self.calls.append((int(delay), getattr(callback, "__name__", repr(callback))))
        return "job-%d" % len(self.calls)


class FakeText:
    # tk.Text 的最小替身：记录插入内容、可在指定调用上抛错。
    def __init__(self, boom=None):
        self.inserted = []
        self.state = None
        self.seen_end = False
        self._boom = boom

    def _maybe_boom(self, name):
        if self._boom == name:
            raise RuntimeError("boom@" + name)

    def config(self, **kwargs):
        self._maybe_boom("config")
        self.state = kwargs.get("state", self.state)

    def delete(self, *args):
        self._maybe_boom("delete")

    def insert(self, index, text, tag=None):
        self._maybe_boom("insert")
        self.inserted.append(str(text))

    def see(self, *args):
        self._maybe_boom("see")

    def yview(self):
        return (0.0, 1.0)

    def index(self, *args):
        return "100.0"


class FakeLabel:
    def __init__(self, value="全部房间"):
        self.value = value

    def configure(self, **kwargs):
        if "values" in kwargs:
            self.value = kwargs["values"]

    def get(self):
        return self.value


class FakeTable:
    # [阶段4] DataTable 替身：记录 sync 的行级增量调用，供链路断言与异常注入。
    def __init__(self):
        self.synced = []

    def sync(self, keys, values, tags):
        self.synced.append((list(keys), dict(values), dict(tags)))


def base_stub(extra_boom=None):
    # object.__new__ 跳过 Tk 初始化：只挂被测方法用到的状态字段与假控件。
    stub = object.__new__(gui.LiveRecorderGUI)
    stub._danmaku_lock = threading.Lock()
    stub._danmaku_rooms = {}
    stub._danmaku_msgs = __import__("collections").deque(maxlen=300)
    stub._danmaku_stats_dirty = True
    stub._danmaku_stream_dirty = True
    stub._danmaku_last_stats = None
    stub._danmaku_filter = "全部房间"
    stub._dm_table = FakeTable()
    stub._dm_stat_rooms = FakeLabel()
    stub._dm_stat_connected = FakeLabel()
    stub._dm_stat_msgs = FakeLabel()
    stub._dm_filter_menu = FakeLabel()
    stub.danmaku_text = FakeText(extra_boom)
    stub._show_danmaku_placeholder = lambda visible: None
    stub.log_text = FakeText(extra_boom)
    stub.root = FakeRoot()
    stub._log_lines = []
    stub._log = lambda message, level="info": stub._log_lines.append([message, level])
    stub._chain_warn_at = {}
    stub._CHAIN_WARN_INTERVAL_SECONDS = 0.0
    stub._log_queue = queue.Queue()
    stub._log_queue_lock = threading.Lock()
    stub._log_queue_has_data = True
    stub._log_flush_job_id = None
    # _pump_ui_events 的桩字段（M-15 第四支链）。缺任一即以 AttributeError 暴露，
    # 不会退化成「静默通过」——这是本文件桩契约的一部分。
    stub._pump_active = True
    stub._ui_event_queue = queue.Queue()
    stub._ui_pump_job_id = None
    stub._refresh_job_id = None
    stub._danmaku_refresh_job_id = None
    stub._process_lock = threading.Lock()
    stub._process = None
    stub._process_pid = None
    stub._running = True
    stub._session_id = 1
    stub._process_ended = lambda session_id=None: None
    stub._update_status_bar = lambda: None
    stub._update_quality_display = lambda: None
    stub._watch_url_config = lambda: None
    stub._get_timestamp = lambda: "2026-09-29 12:00:00"
    return stub


G = gui.LiveRecorderGUI


# ─── M-15 / M-17：数值容错（_as_float / _as_int） ─────────────
out["as_float"] = [gui._as_float(None), gui._as_float("abc"), gui._as_float("12.5"), gui._as_float(3)]
out["as_int"] = [
    gui._as_int(None),
    gui._as_int("x"),
    gui._as_int("7"),
    gui._as_int(2.9),
    gui._as_int(float("inf"), -1),
    gui._as_int(True, -1),
]

# ─── M-15：脏 ts 的 conn/stats 事件不再炸、回落默认值 ─────────
stub = base_stub()
G._danmaku_dispatch(stub, {"ev": "conn", "room": "房间A", "platform": "抖音直播", "state": "started", "ts": None})
G._danmaku_dispatch(
    stub, {"ev": "stats", "room": "房间A", "connected": True, "msg_total": None, "msg_rate": "12", "online": [1]}
)
out["dispatch_null_safe"] = {
    "started_at": stub._danmaku_rooms["房间A"]["started_at"],
    "msg_total": stub._danmaku_rooms["房间A"]["msg_total"],
    "msg_rate": stub._danmaku_rooms["房间A"]["msg_rate"],
    "online": stub._danmaku_rooms["房间A"]["online"],
}

# ─── M-15：弹幕刷新链——ts 为 null 的展示消息渲染不炸且续期 ───
stub = base_stub()
stub._danmaku_msgs.append({"ev": "msg", "room": "房间A", "type": "chat", "user": "u", "text": "hi", "ts": None})
G._schedule_danmaku_refresh(stub)
out["render_after_null_ts"] = {
    "jobs": stub.root.calls,
    "text": "".join(stub.danmaku_text.inserted),
    "warns": [line for line in stub._log_lines if line[1] == "warn"],
}

# ─── M-15：渲染真抛错时链必须续期 + 留痕 ──────────────────────
stub = base_stub(extra_boom="insert")
stub._danmaku_msgs.append({"ev": "msg", "room": "房间A", "type": "chat", "user": "u", "text": "hi", "ts": 1.0})
G._schedule_danmaku_refresh(stub)
out["danmaku_chain_rearm"] = {
    "jobs": stub.root.calls,
    "warns": [line for line in stub._log_lines if line[1] == "warn"],
}

stub = base_stub()


def _raise_later():
    raise ValueError("simulated status bar failure")


stub._update_quality_display = _raise_later
G._schedule_status_refresh(stub)
out["status_chain_rearm"] = {
    "jobs": stub.root.calls,
    "warns": [line for line in stub._log_lines if line[1] == "warn"],
}

stub = base_stub(extra_boom="insert")
stub._log_queue.put([["一行日志", "info"]])
G._schedule_log_flush(stub)
out["flush_chain_rearm"] = {
    "jobs": stub.root.calls,
    "warns": [line for line in stub._log_lines if line[1] == "warn"],
    "still_has_data": stub._log_queue_has_data,
}

# ─── M-15 第四支链：UI 事件泵本体抛错也必须续期 ───────────────
stub = base_stub()
# 注入点选「激活刷新链那一段整体抛错」（把锁换成 None → with 语句抛 TypeError），
# 而不是替换 _after_retry 本身：替换被测机制会让红点无法归因（分不清是 finally 没生效
# 还是重排被拆）。这里要证的正是「前面那段炸了，后面的续期照样跑」。
# 异常必须在本场景内接住并记账：本文件的 results fixture 断言子进程 rc==0，
# 让它穿透会连坐整个文件（那是 fixture 的刻意设计，不是本用例的判据）。
stub._log_queue_lock = None
raised = ""
try:
    G._pump_ui_events(stub)
except Exception as exc:
    raised = type(exc).__name__
out["pump_rearm_when_body_raises"] = {
    "jobs": stub.root.calls,
    "pump_still_armed": stub._ui_pump_job_id is not None,
    "flush_job_id": stub._log_flush_job_id,
    # raised 非空是**注入生效的证明**：它为空说明前面那段根本没抛，
    # 于是「finally 续期」这一判据退化成什么都测不到。
    "raised": raised,
}

# ─── M-17：一条坏事件不得带走同批后续事件 ─────────────────────
with tempfile.TemporaryDirectory() as tmp:
    logs = Path(tmp) / "logs"
    logs.mkdir()
    sidecar = logs / "danmaku_monitor.jsonl"
    events = [
        {"ev": "conn", "room": "房间Z", "platform": "B站直播", "state": "started", "ts": 1.0},
        {"ev": "msg", "room": "BAD", "type": "chat", "user": "u", "text": "坏条", "ts": 1.0},
        {"ev": "msg", "room": "房间Z", "type": "chat", "user": "v", "text": "后一条", "ts": 2.0},
        {"ev": "msg", "room": "房间Z", "type": "chat", "user": "w", "text": "再后一条", "ts": 3.0},
    ]
    sidecar.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8")

    original_dispatch = G._danmaku_dispatch

    def poisoned(self, event):
        # 只负责「注入一次 dispatch 失败」，去重/状态写入仍走真实实现。
        if event.get("room") == "BAD":
            raise TypeError("simulated dirty event")
        return original_dispatch(self, event)

    G._danmaku_dispatch = poisoned
    try:
        stub = base_stub()
        stub.app_root = str(tmp)
        stop = threading.Event()
        t = threading.Thread(target=G._danmaku_tail_loop, args=(stub, stop), daemon=True)
        t.start()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with stub._danmaku_lock:
                if len(stub._danmaku_msgs) >= 2:
                    break
            time.sleep(0.05)
        # set 传入的那只 Event（M-24 同口径）
        stop.set()
        t.join(timeout=3.0)
        out["tail_batch_survives"] = {
            "msgs": [str(m.get("text")) for m in stub._danmaku_msgs],
            "rooms": sorted(stub._danmaku_rooms),
            "warns": [line for line in stub._log_lines if line[1] == "warn"],
            "thread_dead": not t.is_alive(),
        }
    finally:
        G._danmaku_dispatch = original_dispatch

# ─── M-17：最外层异常必须留痕（此前完全静默） ────────────────
with tempfile.TemporaryDirectory() as tmp:
    logs = Path(tmp) / "logs"
    logs.mkdir()
    (logs / "danmaku_monitor.jsonl").write_text(
        json.dumps({"ev": "msg", "room": "房间Q", "type": "chat", "user": "u", "text": "x", "ts": 1.0}) + "\n",
        encoding="utf-8",
    )
    real_path = os.path

    def _boom(path):
        raise RuntimeError("simulated non-OSError failure")

    # gui.os 换成浅拷贝替身：改 stdlib 模块本体的属性会波及全进程（AGENTS 明令）。
    shim_os = types.SimpleNamespace(
        path=types.SimpleNamespace(exists=real_path.exists, getsize=_boom, join=real_path.join)
    )
    original_os = gui.os
    gui.os = shim_os
    try:
        stub = base_stub()
        stub.app_root = str(tmp)
        stop = threading.Event()
        t = threading.Thread(target=G._danmaku_tail_loop, args=(stub, stop), daemon=True)
        t.start()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not stub._log_lines:
            time.sleep(0.05)
        stop.set()
        t.join(timeout=3.0)
        out["tail_outer_warn"] = {
            "lines": stub._log_lines,
            "thread_dead": not t.is_alive(),
        }
    finally:
        gui.os = original_os

sys.stdout.write("\n@@WP_E_TAIL@@ " + json.dumps(out, ensure_ascii=False))
"""


def _child_env() -> dict[str, str]:
    # 显式钉死 UTF-8：无 PYTHONUTF8 的中文 Windows（ACP=936）下子进程 stdout 走 GBK，
    # 而 JSON 带中文房间名 → 父进程按 utf-8 解码即 UnicodeDecodeError。
    # 只读 os.environ 取基底，不写回本进程（环境变量一律用 monkeypatch）。
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@pytest.fixture(scope="module")
def results() -> dict[str, Any]:
    # module 作用域：一次子进程跑完全部场景（import gui 约数秒，两个 tail 场景还要等
    # deadline/join）。按用例各起一支会把墙钟时间放大到分钟级。任何场景抛错都会让本文件
    # 全部用例一起失败——这是**期望行为**，子进程内的场景本就是同一批证据。
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        # 脚本不读 stdin，但仍显式给一支空管道：不传则子进程继承父控制台句柄，
        # 在 GUI/无头宿主下继承到的可能是不可用句柄，表现为随机尽早退出。
        input=b"{}",
        capture_output=True,
        # 300s：两个 tail 场景内含 5s/3s deadline 轮询与 3s join 预算，正常远用不到；
        # 但不能无限——tail 循环不再响应 stop_event 时必须以 TimeoutExpired 失败，
        # 而不是挂死整个 pytest 会话（守护线程会跟着子进程一起没）。
        timeout=300,
        cwd=str(ROOT),
        env=_child_env(),
    )
    marker = _MARKER.encode("utf-8")
    assert proc.returncode == 0, (
        "tail robustness subprocess failed: " + proc.stderr.decode("utf-8", errors="replace")[-4000:]
    )
    # 判定一律按字节（不传 text/encoding）：码页与子进程控制台语言都与结论解耦；
    # 判定通过后才把载荷按 utf-8 解出（编码由注入的 PYTHONIOENCODING 保证）。
    assert marker in proc.stdout, "no result marker in: " + proc.stdout.decode("utf-8", errors="replace")[-1000:]
    # 收窄口径同 test_gui_status_pattern_i18n._case_result：json.loads 返回 Any，原样 return
    # 会让 results[...] 取值脱离类型检查（mypy 在定义处报 no-any-return）。只加声明、不改
    # 运行时；不用行内 type: ignore（Linux 必要 / Windows 多余 → basedpyright 报错）。
    return cast(dict[str, Any], json.loads(proc.stdout.split(marker, 1)[1].decode("utf-8")))


def test_as_float_and_as_int_tolerate_dirty_values(results: dict[str, Any]) -> None:
    # 单一容错口径（M-15/M-17 共用同一 helper，不得出现第二份）：None/垃圾串回落默认值，
    # 合法数值原样取，Infinity 不得把 int() 炸穿。两个列表按「位置即语义」写：as_float 依次
    # 是 None/垃圾串/合法小数/合法整数（须转成 float，下游格式化才不会少小数位）；as_int
    # 最后两项用 -1 哨兵证明 default 真的被透传（恒回 0 的实现能把前四项全蒙对）。
    # True→1 也在列：JSON 的 true 落进数值字段是边车脏数据的真实形态之一。
    assert results["as_float"] == [0.0, 0.0, 12.5, 3.0]
    assert results["as_int"] == [0, 0, 7, 2, -1, 1]


def test_dispatch_survives_null_and_typed_fields(results: dict[str, Any]) -> None:
    # ts=null、msg_total=null、online 给了数组：一条都不许抛，取不到的回落默认值。
    # 断言取的是**桩里那份真实 _danmaku_rooms**，所以同时见证 conn/stats 事件正常入库——
    # 只断言不抛异常的话，把 dispatch 整体 try/except 吞掉也能过（假绿）。
    # msg_rate 取到 12 而 msg_total 取到 0：证明「带外类型只废单个字段，不废整条事件」。
    info = results["dispatch_null_safe"]
    assert info["started_at"] == 0.0
    assert info["msg_total"] == 0
    assert info["msg_rate"] == 12
    assert info["online"] == 0


def test_danmaku_render_of_null_ts_still_rearms(results: dict[str, Any]) -> None:
    # _render_danmaku_stream 里 float(ts) 的确切事故点（文件头 2026-09-12 审查 6.2）。
    # 现在必须：① 渲染出该条（时间显示 --:--:--）② 无条件续期 ③ 不误报异常。
    case = results["render_after_null_ts"]
    assert "--:--:--" in case["text"], case["text"]
    assert "hi" in case["text"]
    # JSON 把元组落成数组：按 [延迟, 回调名] 逐字比对续期节拍
    # 延迟值 1000 是被锁死的：本链的节拍就是「弹幕页 1s 一刷」。改成 lambda/偏函数包装
    # 会让回调名变成 <lambda>，这里即以字符串不等而红——防止「续期还在、但续的是别的 callable」。
    assert case["jobs"] == [[1000, "_schedule_danmaku_refresh"]]
    # 反向半边：正常轮次不得留痕。限频器若写成「无条件 warn」，日志页会被每秒一条刷满、
    # 真实线索被淹掉，所以「不该响的时候不许响」必须同锁。
    assert case["warns"] == [], f"无异常却留痕 = 判据漂移：{case['warns']}"


def test_danmaku_chain_rearms_and_warns_when_render_raises(results: dict[str, Any]) -> None:
    # M-15：渲染抛错时链不能断——续期在 finally，且必须留一条 warn（限频由
    # _CHAIN_WARN_INTERVAL_SECONDS 控制，桩里压成 0）。
    # 本场景只断言「回调名」不比对延迟：抛错轮次的延迟与正常轮次同值，比了也不增判据强度，
    # 反而会把「间隔调整」这类无关改动误报成 M-15 回归。
    case = results["danmaku_chain_rearm"]
    assert [job[1] for job in case["jobs"]] == ["_schedule_danmaku_refresh"]
    assert case["warns"], "刷新链异常未留痕（旧形态全静默）"


def test_status_chain_rearms_when_render_raises(results: dict[str, Any]) -> None:
    # 三条链各自单独锁：本链的抛错源是 _update_quality_display（换成会抛的替身），而非
    # 渲染弹幕那条路径。三链共用 finally 形态但接线点独立，只锁一条时另外两条被改回
    # 「尾部续期」不会被发现。
    case = results["status_chain_rearm"]
    assert [job[1] for job in case["jobs"]] == ["_schedule_status_refresh"]
    assert case["warns"], "状态刷新链异常未留痕"


def test_log_flush_chain_rearms_when_render_raises(results: dict[str, Any]) -> None:
    # 日志刷新链断掉后 _log_flush_job_id 会留着旧 id、_pump_ui_events 便不再激活 ——
    # 这正是旧实现「整页停止刷新」的机制，续期必须落 finally。
    case = results["flush_chain_rearm"]
    assert [job[1] for job in case["jobs"]] == ["_schedule_log_flush"]
    # 这条是 M-15 里最容易被「顺手优化」掉的语义：has_data 为真时 finally 才重排，
    # 渲染失败不等于队列已清空。若实现改成「抛错就把 has_data 置 False」，链会以
    # 「休眠态」形式静默停下——表面看仍是有条件的、实则永不会被人唤醒（唤醒点在 _log）。
    assert case["still_has_data"] is True, "渲染失败时不得把 has_data 误判成已清空"
    assert case["warns"], "日志刷新链异常未留痕"


def test_ui_pump_rearms_when_activation_raises(results: dict[str, Any]) -> None:
    # M-15 第四支链（_pump_ui_events 本体）。旧形态把续期写在函数最后一句，前面的
    # 「激活日志刷新链」一抛（窗口销毁竞态里的 TclError 即此形）就跳过续期 → UI 事件泵
    # 永久停摆，post_ui 排队的 _on_recording_stopped / _finalize_quit 不再执行（关不掉窗口）。
    # jobs 只应有一项：泵自己的重排；刷新链激活那一项在抛错行之前就被打断了。
    case = results["pump_rearm_when_body_raises"]
    assert [job[1] for job in case["jobs"]] == ["_pump_ui_events"], case["jobs"]
    assert case["jobs"][0][0] == 100, f"泵的重排节拍被改动：{case['jobs']}"
    assert case["pump_still_armed"] is True, "UI 事件泵在激活段抛错后没有续期"
    # flush_job_id 保持 None 是刻意的语义：激活失败不得记成「已排队」，
    # 否则下一轮的 `is None` 守卫永不为真，刷新链再无人唤醒。
    assert case["flush_job_id"] is None, case
    # 注入生效的证明：前段确实抛了 TypeError（锁被换成 None → `with None:` 在 3.12+ 报
    # 'NoneType' does not define __enter__ and __exit__）。它为空说明本轮什么都没注入，
    # 上面三条断言即刻失去意义。
    assert case["raised"] == "TypeError", case


def test_tail_batch_keeps_good_events_after_a_bad_one(results: dict[str, Any]) -> None:
    # M-17 本体：坏条只废自己，同 chunk 后续完好事件必须照常入库，并留一条汇总 warn。
    # 顺序是判据的一半：坏条排在两条好条之前、四条同一 chunk 一次读入——「整批丢失」
    # 只可能表现为 msgs 少掉后两条。thread_dead 必须显式锁：否则「异常穿透打死 tail 线程」
    # 与「防护有效」能留下相同的两帧缓冲（首轮已入库）。
    case = results["tail_batch_survives"]
    assert case["thread_dead"] is True
    # rooms 只允许有房间Z：BAD 那条废在自己的 dispatch 上，不得留下半个房间条目
    # （连接状态已写、消息没写 = 表格里出现空房间行，用户视角同样是脏数据外溢）。
    assert case["rooms"] == ["房间Z"], case["rooms"]
    assert case["msgs"] == ["后一条", "再后一条"], f"坏条之后的完好事件被整批丢弃：{case['msgs']}"
    # 汇总条数走**一条** warn（bad_events 计数 + 首个异常详情），逐条 warn 会让刷屏
    # 淹掉真实线索；这里用 any(子串) 而不是全等，避免把「措辞」钉成契约。
    assert any("弹幕事件处理失败" in line[0] for line in case["warns"]), case["warns"]


def test_tail_outer_failure_is_logged_not_silent(results: dict[str, Any]) -> None:
    # M-17：最外层 except 从「静默 sleep(1.0)」变成「限频 warning 留痕」。
    # 注入点是 os.path.getsize（非 OSError 的 RuntimeError），刻意避开 OSError 分支——
    # 那条是 MID-2250 认定的良性路径（日志归档改名），应当继续静默重试。
    case = results["tail_outer_warn"]
    assert case["thread_dead"] is True
    assert any("弹幕 tail 线程本轮异常" in line[0] for line in case["lines"]), case["lines"]


# ─── 结构锁：续期注册必须在 finally，且不得留在函数尾部 ────────

# 键=链名、值=该链**必须使用**的重排 helper（不是列表：四链都走 _after_retry，
# 一旦某条改回裸 self.root.after(...)，绕过的是 _after_retry 内部的 TclError 容错，
# 结构锁会立刻点名是哪一条链跑偏）。
# _pump_ui_events 是审查时漏计的第 4 支：它续自己的泵，同时负责按需激活日志刷新链，
# 断了等于整窗收尾回调停摆，与另外三支同族同判据。
_CHAINS = {
    "_schedule_danmaku_refresh": "_after_retry",
    "_schedule_status_refresh": "_after_retry",
    "_schedule_log_flush": "_after_retry",
    "_pump_ui_events": "_after_retry",
}


def test_rearm_lives_in_finally_for_every_chain() -> None:
    # 行为锁之上的第二道防线：把「重排落在 finally 里」钉成结构约束，否则一次「顺手把
    # finally 拆回顺序语句」的重构就会让三页重新有停摆风险。
    # 为什么行为锁不够：上面的 chain_rearm 用例各喂**一种**抛错注入点，拆掉 finally 后
    # 若那条路径恰好不再抛，行为锁会一起变绿；AST 锁与「本轮是否真的出错」完全解耦。
    tree = ast.parse(GUI_SOURCE)
    for name, helper in _CHAINS.items():
        fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), None)
        assert fn is not None, f"gui.py 缺少 {name}"
        arms = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == helper
        ]
        assert arms, f"{name} 未用 {helper}() 重排"
        # 判据是「arm 出现在某个带 finalbody 的 Try 的子树里」，而不是「Try 的 body 里」：
        # 写在 try 体内等于回到旧形态（抛错即跳过），只有 finalbody 才无条件执行。
        in_finally = any(
            isinstance(node, ast.Try) and node.finalbody and any(arm in ast.walk(node) for arm in arms)
            for node in ast.walk(fn)
        )
        assert in_finally, f"{name} 的续期注册不在 finally 里（M-15 回归形态）"


def test_tail_loop_guards_every_event() -> None:
    # 结构锁：tail 的 try/except 必须**在 for 循环体内**（逐事件），
    # 只包整个循环等于回到「一条坏事件带走整批」的旧形态。
    tree = ast.parse(GUI_SOURCE)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_danmaku_tail_loop")

    def _dispatch_calls(node: ast.AST) -> list[ast.Call]:
        found: list[ast.Call] = []
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "_danmaku_dispatch"
            ):
                found.append(sub)
        return found

    guarded = False
    for loop in (node for node in ast.walk(fn) if isinstance(node, ast.For)):
        for try_node in (n for n in ast.walk(loop) if isinstance(n, ast.Try)):
            # 必须是被 try 体**直接包住**的 dispatch 调用：前半句排除「try 体内根本没有
            # dispatch」的无关 Try（如 json.loads 那一圈）；后半句要求 try 体的每一条语句
            # 都含 dispatch。只写前半句会把「包整条 for 的外层大 try」也算成有效防护——
            # 那正是 M-17 要消灭的形态。
            if _dispatch_calls(try_node) and all(_dispatch_calls(stmt) for stmt in try_node.body):
                guarded = True
    assert guarded, "_danmaku_dispatch 的逐事件防护缺失（M-17 回归形态）"
