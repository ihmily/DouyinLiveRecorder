# -*- coding: utf-8 -*-
# M-02：GUI 两条配置保存路径共用的 _save_text_to_file 必须委托 src.utils.atomic_write_text
# （全仓唯一加固实现：flush+fsync + replace 前保留目标文件 mode）。
# 旧实现是本地弱化副本（有 tmp+replace、缺 fsync、不保留 mode），POSIX 下每次保存把 0600
# 还原成 umask 权限——含全部平台口令/Cookie 的配置变为同机任意本地用户可读。
#
# 经子进程驱动真实实现：gui.py 模块级写 os.environ["DLR_GUI_PARENT"]="1"（必须先于任何
# src 导入），同进程导入会把后续用例的 src.logger 判成 GUI 父进程、不再建录制日志。
# 理由与骨架同 tests/test_gui_monitor.py；结果以带前缀的单行 JSON 回传。

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = r"""
import gui
import json
import os
import pathlib
import stat
import sys
import tempfile

req = json.loads(sys.stdin.read())
out = {}

d = tempfile.mkdtemp()
# 目标文件取自 mkstemp 的返回值；首写经 fdopen（用例里不出现 open(变量路径, "w") 形态）
fd, target = tempfile.mkstemp(suffix=".ini", dir=d)
with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
    f.write("old")

# 判据一：委托真实加固实现（经 gui 命名空间的 atomic_write_text 转发）
calls = []
real = gui.atomic_write_text
def spy(path, text, encoding="utf-8-sig", errors=None):
    calls.append((str(path), text, encoding))
    return real(path, text, encoding=encoding, errors=errors)
gui.atomic_write_text = spy
gui._save_text_to_file("a=1", target)
out["delegated"] = len(calls) == 1 and calls[0][0] == target and calls[0][2] == "utf-8-sig"
out["content"] = pathlib.Path(target).read_text(encoding="utf-8-sig").replace("\ufeff", "")

# 判据二：POSIX 下 0600 权限在保存后保持（M-02 的核心缺口；Windows chmod 仅只读位，跳过）
if sys.platform != "win32":
    os.chmod(target, 0o600)
    gui._save_text_to_file("a=2", target)
    out["mode_preserved"] = stat.S_IMODE(os.stat(target).st_mode) == 0o600

# 判据三：失败必须上抛 OSError（两处保存按钮靠异常弹错误框；atomic_write_text 失败只
# 返回 False，委托层必须转换，不得静默吞掉）。失败形态用「目标本身是上面已存在的
# 目录」：os.replace 落到目录上必抛 OSError，无需再构造任何别的路径。
try:
    gui._save_text_to_file("a=3", d)
    out["raises_on_failure"] = False
except OSError:
    out["raises_on_failure"] = True

# 判据四：原子写不残留 .tmp（C7；失败分支的临时文件由 atomic_write_text 自行清理）
out["no_tmp_left"] = [n for n in os.listdir(d) if n.endswith(".tmp")] == []

sys.stdout.write("\n@@GUI@@ " + json.dumps(out, ensure_ascii=False))
"""

_MARKER = "\n@@GUI@@ ".encode("utf-8")


def _child_env() -> dict[str, str]:
    # 显式给子进程钉死 UTF-8（中文 Windows ACP=936 下否则 stdout 走 GBK）；
    # 只读基底、不写回本进程。
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_child() -> dict[str, Any]:
    # 按字节找 marker（探测子进程输出一律按字节比较），rfind 取最后一次：万一日志恰好
    # 打出同形文本，真实载荷仍在最后一条里。180s 覆盖子进程完整 import gui。
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        input=b"{}",
        capture_output=True,
        timeout=180,
        cwd=str(ROOT),
        env=_child_env(),
    )
    idx = proc.stdout.rfind(_MARKER)
    assert idx >= 0, f"子进程未回传结果标记: {proc.stderr.decode('utf-8', errors='replace')[-400:]}"
    payload = json.loads(proc.stdout[idx + len(_MARKER) :].decode("utf-8"))
    assert isinstance(payload, dict), f"子进程载荷不是 dict: {payload!r}"
    return cast("dict[str, Any]", payload)


def test_save_text_to_file_delegates_to_hardened_atomic_write() -> None:
    # 单用例四判据全部经同一子进程回传：delegation 发生、补末尾换行、失败上抛、无 .tmp
    # 残留；POSIX 额外断言 0600 保持（Windows 上 chmod 只影响只读位，该断言仅 ubuntu 生效）。
    out = _run_child()
    assert out["delegated"], f"未委托 atomic_write_text: {out}"
    assert out["content"] == "a=1\n", f"补末尾换行语义丢失: {out['content']!r}"
    assert out["no_tmp_left"], f"原子写残留 .tmp: {out}"
    assert out["raises_on_failure"], f"失败未上抛: {out}"
    if sys.platform != "win32":
        assert out["mode_preserved"], f"POSIX 下 0600 权限未保留: {out}"
