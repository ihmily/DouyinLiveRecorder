# tests/test_gui_monitor.py - 守护 gui.py 中不依赖 Tk 主循环的判定逻辑。
#
# 覆盖五类 GUI 缺陷（ID 为审查编号，便于回溯）：MID-51 URL 配置有效性判据（带 BOM 的
# 「全部注释」配置必须拦住启动，不能误判成有配置）；MID-53 语言下拉显示名唯一
# （en_US/en_GB 不得同名）；MID-54 画质降级标志按时间序复位（不得一次瞬时降级永久钉住）；
# MID-55 高级设置保存前必须先裁决外部改动（不得用打开时快照覆盖录制进程的新写入）；
# MID-56 _stopping 必须在 finally 复位（否则「开始录制」永久失效）。
#
# 不在本进程 `import gui`：gui.py 模块级写 os.environ["DLR_GUI_PARENT"]="1"（必须先于
# 任何 src 导入），同进程导入会让后续用例的 src.logger 都被判成 GUI 父进程、不再建录制日志。
# 故行为判据经**子进程**驱动真实实现，结构性约束以 AST/文本静态锁读取源码。
#
# 子进程输出显式钉 UTF-8（PYTHONUTF8/PYTHONIOENCODING）并按字节比较：无该环境变量的中文
# Windows（ACP=936）下 stdout 走 GBK，父进程按 utf-8 解码即抛 UnicodeDecodeError。

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUI_SOURCE = (ROOT / "gui.py").read_text(encoding="utf-8")

# 子进程内驱动真实 gui 逻辑；结果以带前缀的单行 JSON 回传（便于与 customtkinter 的
# 任何杂散输出分离）。
_SCRIPT = """
import gui
import json
import sys
import types

req = json.loads(sys.stdin.read())
call = req["call"]
out = {}

if call == "has_room":
    fake = types.SimpleNamespace(url_config_file=req["path"])
    out["result"] = bool(gui.LiveRecorderGUI._has_room_config(fake))
elif call == "alert_expired":
    out["result"] = bool(gui._quality_alert_expired(req["info"], req["now"]))
elif call == "verdict":
    out["result"] = gui._config_change_verdict(
        req["disk_baseline"], req["disk_now"], req["editor_text"], req["editor_baseline"]
    )
elif call == "snapshot":
    content, mtime = gui._read_config_snapshot(req["path"])
    out["result"] = [content, mtime]
elif call == "normalize":
    out["result"] = gui._normalize_editor_text(req["text"])
elif call == "display_names":
    out["result"] = gui.i18n_module.unique_display_names()
elif call == "ttl":
    out["result"] = float(gui._QUALITY_ALERT_TTL_SECONDS)
else:
    raise SystemExit("unknown call: " + call)

sys.stdout.write("\\n@@GUI@@ " + json.dumps(out, ensure_ascii=False))
"""

_MARKER = "\n@@GUI@@ "
# 纯逻辑调用无需子进程：把函数体复制进沙箱太脆，改为首次需要时一次性拉取常量，
# 其余走 _gui_call 的真实调用路径。
_TTL_CACHE: dict[str, float] = {}


def _subprocess_env() -> dict[str, str]:
    # 显式钉死 UTF-8：无 PYTHONUTF8 的中文 Windows（ACP=936）下子进程 stdout 走 GBK，
    # 而 JSON 带中文房间名/主播名 → 父进程按 utf-8 解码即抛 UnicodeDecodeError。
    # 只读 os.environ 取基底，绝不写回本进程（环境变量一律用 monkeypatch）。
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _decode_loosely(raw: bytes) -> str:
    # 仅用于**失败时的诊断文本**：不参与任何判定（判定一律按字节，见 _gui_call），
    # 因此 errors="replace" 兜底即可，绝不让解码影响用例结论。
    return raw.decode("utf-8", errors="replace")


def _gui_call(call: str, **kwargs: Any) -> Any:
    payload = json.dumps({"call": call, **kwargs}, ensure_ascii=False)
    # 按字节比较：不传 text/encoding/errors，marker 判定与宿主码页、子进程控制台语言
    # 完全解耦；判定通过后才把 marker 之后的载荷按 utf-8 解出（编码由注入的
    # PYTHONIOENCODING 保证）。
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=180,
        cwd=str(ROOT),
        env=_subprocess_env(),
    )
    marker = _MARKER.encode("utf-8")
    assert proc.returncode == 0, "gui subprocess failed: " + _decode_loosely(proc.stderr)[-2000:]
    assert marker in proc.stdout, "no result marker in: " + _decode_loosely(proc.stdout)[-500:]
    return json.loads(proc.stdout.split(marker, 1)[1].decode("utf-8"))["result"]


def _ttl_seconds() -> float:
    if "ttl" not in _TTL_CACHE:
        _TTL_CACHE["ttl"] = float(_gui_call("ttl"))
    return _TTL_CACHE["ttl"]


# ─── MID-51：URL 配置有效性判据 ─────────────────────────────
class TestHasRoomConfig:
    def test_bom_and_all_commented_lines_block_start(self, tmp_path: Path) -> None:
        # 全仓写入方一律 utf-8-sig（文件必带 BOM），而「全部房间注释掉」是暂停录制的常规做法：
        # 旧实现裸 utf-8 + startswith('#') 会把首行读成 '\ufeff#…' 而误判成有配置。
        target = tmp_path / "URL_config.ini"
        _ = target.write_text(
            "#https://live.douyin.com/123456\n#原画,https://live.douyin.com/654321,主播: 甲\n\n",
            encoding="utf-8-sig",
        )
        assert _gui_call("has_room", path=str(target)) is False

    def test_bom_with_active_room_passes(self, tmp_path: Path) -> None:
        # 反向护栏：判据不能收紧成「一律拦住」，否则正常配置也起不来
        target = tmp_path / "URL_config.ini"
        _ = target.write_text("#注释掉的房间\n原画,https://live.douyin.com/123456,主播: 甲\n", encoding="utf-8-sig")
        assert _gui_call("has_room", path=str(target)) is True

    def test_missing_file_blocks_start(self, tmp_path: Path) -> None:
        assert _gui_call("has_room", path=str(tmp_path / "nope.ini")) is False

    def test_no_bare_utf8_read_left_in_guard(self) -> None:
        # 静态锁：守卫不得自带编码/行解析（漂移回旧形态即红），必须复用
        # src/web_config.py::parse_url_config 的 enabled 判据。
        tree = ast.parse(GUI_SOURCE)
        fn = next(
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_has_room_config"
        )
        dumped = ast.dump(fn)
        assert "parse_url_config" in dumped, "守卫必须复用 web_config.parse_url_config 的判据"
        assert "utf-8" not in dumped, "守卫内不得自带一套读取编码"


# ─── MID-53：语言菜单显示名唯一 ─────────────────────────────
class TestLanguageMenuNames:
    def test_display_names_unique_per_code(self) -> None:
        names = _gui_call("display_names")
        assert len(set(names.values())) == len(names) == 4
        assert names["en_US"] != names["en_GB"]

    def test_gui_no_longer_strips_parenthetical(self) -> None:
        # 静态锁（走 AST，避免被解释性注释里引用的旧写法字符串误命中）：
        # _language_names 必须整体来自 i18n.unique_display_names()，不得再有本地裁剪——
        # 正是那一次 split(" (") 让 en_US 与 en_GB 折成同名。
        tree = ast.parse(GUI_SOURCE)
        # 赋值带类型注解（self._language_names: dict[str, str] = ...）→ AnnAssign 而非 Assign
        assigns = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AnnAssign | ast.Assign)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "_language_names"
                for t in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets)
            )
        ]
        assert len(assigns) == 1, f"_language_names 应只在一处赋值，实际 {len(assigns)}"
        value = assigns[0].value
        assert isinstance(value, ast.Call)
        assert getattr(value.func, "attr", "") == "unique_display_names"
        assert "split" not in ast.dump(value), "赋值表达式里不得再有显示名裁剪"


# ─── MID-54：降级告警的时间序复位 ───────────────────────────
class TestQualityAlertExpiry:
    def test_fresh_alert_is_kept(self) -> None:
        info = {"downgraded": True, "alert_at": 1000.0, "set_quality": "蓝光"}
        assert _gui_call("alert_expired", info=info, now=1001.0) is False

    def test_alert_expires_after_one_cycle(self) -> None:
        ttl = _ttl_seconds()
        info = {"downgraded": True, "alert_at": 1000.0, "set_quality": "蓝光"}
        assert _gui_call("alert_expired", info=info, now=1000.0 + ttl + 1.0) is True
        # TTL 必须不短于两个主循环周期（默认 delay_default=120s）：告警在每轮录制启动时
        # 重打，窗口短于周期会把「仍在降级、只是本轮告警还没到」误清成正常
        assert ttl >= 240.0

    def test_no_alert_never_expires(self) -> None:
        assert _gui_call("alert_expired", info={"downgraded": False, "alert_at": 0.0}, now=1e9) is False

    def test_garbage_alert_at_is_recoverable(self) -> None:
        # alert_at 被污染成非数值时不得永久钉住房间（旧故障形态）
        assert _gui_call("alert_expired", info={"downgraded": True, "alert_at": "n/a"}, now=1e9) is True

    def test_alert_at_is_excluded_from_display_compare(self) -> None:
        # alert_at 是纯内部时序字段；若参与「数据未变则跳过重建」的整表比较，会让画质页
        # 每轮 destroy+重建（闪烁 + 点击落空）。
        tree = ast.parse(GUI_SOURCE)
        keys: set[str] = set()
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "_QUALITY_NON_DISPLAY_FIELDS" for t in node.targets):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Set):
                    keys.update(e.value for e in sub.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
        assert "alert_at" in keys, f"_QUALITY_NON_DISPLAY_FIELDS 未包含 alert_at（实际 {sorted(keys)}）"


# ─── MID-55：config.ini 的外部改动裁决 ───────────────────────
class TestConfigSnapshotConflict:
    def test_unchanged_disk_allows_plain_save(self) -> None:
        verdict = _gui_call("verdict", disk_baseline="A\n", disk_now="A\n", editor_text="A", editor_baseline="A")
        assert verdict == "unchanged"

    def test_external_change_without_local_edits_reloads(self) -> None:
        assert (
            _gui_call("verdict", disk_baseline="A\n", disk_now="A\nB=1\n", editor_text="A", editor_baseline="A")
            == "reload"
        )

    def test_external_change_with_local_edits_is_conflict(self) -> None:
        assert (
            _gui_call(
                "verdict",
                disk_baseline="A\n",
                disk_now="A\nB=1\n",
                editor_text="A edited",
                editor_baseline="A",
            )
            == "conflict"
        )

    def test_unreadable_baseline_is_conflict(self) -> None:
        # 打开窗口时读失败（None）而保存时读到了内容：编辑器基线不可信，
        # 即使「看起来没有改动」也必须交用户裁决，不能静默整文件覆盖
        assert (
            _gui_call("verdict", disk_baseline=None, disk_now="A\n", editor_text="A", editor_baseline="A") == "conflict"
        )

    def test_both_missing_is_unchanged(self) -> None:
        assert (
            _gui_call("verdict", disk_baseline=None, disk_now=None, editor_text="A", editor_baseline="A") == "unchanged"
        )

    def test_unmodified_editor_is_not_reported_dirty(self) -> None:
        # Tk 的 get("1.0", END) 末尾恒多一个换行：编辑器文本与文件原文必须经
        # _normalize_editor_text 同一口径归一，否则「一行未改」也会走 conflict，
        # 静默跟随外部改动的 reload 路径形同不存在。
        disk = "[录制设置]\nlanguage = \n"
        editor_as_tk = _gui_call("normalize", text=disk + "\n")
        baseline = _gui_call("normalize", text=disk)
        assert editor_as_tk == baseline
        assert (
            _gui_call(
                "verdict",
                disk_baseline=disk,
                disk_now=disk + "B=1\n",
                editor_text=editor_as_tk,
                editor_baseline=baseline,
            )
            == "reload"
        )

    def test_snapshot_read_drops_bom(self, tmp_path: Path) -> None:
        target = tmp_path / "config.ini"
        _ = target.write_text("[录制设置]\nlanguage = \n", encoding="utf-8-sig")
        content, mtime = _gui_call("snapshot", path=str(target))
        assert content is not None and not content.startswith("\ufeff")
        assert isinstance(mtime, float)

    def test_snapshot_read_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert _gui_call("snapshot", path=str(tmp_path / "absent.ini")) == [None, None]

    def test_save_config_checks_conflict_before_writing(self) -> None:
        # 静态锁：save_config 必须先重读磁盘并走裁决，否则整文件写回会回滚录制进程
        # 刚写入的 sooplive/flextv/popkontv 凭据与缺键补写（跨进程无锁可用）。
        tree = ast.parse(GUI_SOURCE)
        cls = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AdvancedSettingsWindow"
        )
        save = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "save_config")
        names = {n.func.id for n in ast.walk(save) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "_read_config_snapshot" in names and "_config_change_verdict" in names
        assert "askyesno" in ast.dump(save), "冲突时必须交用户裁决"
        watcher = next(
            node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_watch_config_file"
        )
        assert "_schedule_config_watch" in ast.dump(watcher), "窗口打开期间须持续核对磁盘基线"


# ─── MID-56：_stopping 复位必须无条件 ────────────────────────
class TestStoppingFlagReset:
    def test_reset_sits_in_finally(self) -> None:
        # 收尾主体（含 _send_stop_signal_and_wait 里的 ctypes 调用）一旦抛异常逃出线程，
        # 写在函数末尾的复位永不执行 →「开始录制」此后只回一句 warn、永久失效。
        tree = ast.parse(GUI_SOURCE)
        stop = next(
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "stop_recording"
        )
        waiter = next(n for n in ast.walk(stop) if isinstance(n, ast.FunctionDef) and n.name == "_wait_and_update_ui")
        tries = [b for b in ast.walk(waiter) if isinstance(b, ast.Try) and b.finalbody]
        assert tries, "_wait_and_update_ui 需有 finally"
        reset_in_finally = any(
            isinstance(stmt, ast.Assign)
            and any(isinstance(t, ast.Attribute) and t.attr == "_stopping" for t in stmt.targets)
            for blk in tries
            for stmt in blk.finalbody
        )
        assert reset_in_finally, "finally 内必须复位 _stopping"

    def test_gate_still_blocks_while_stopping(self) -> None:
        # 闸门本身不得被顺手删掉（停止窗口内重复启动是另一种竞态）
        assert "if self._stopping:" in GUI_SOURCE
