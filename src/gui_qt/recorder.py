# -*- coding: utf-8 -*-
# 录制子进程生命周期控制器（不触碰任何 Qt 控件）。
#
# 为什么和窗口分离：录制的启停**必然跨线程**（发信号后要 wait 最长 15s + taskkill 5s）。
# 控制器只操作进程与状态标志、经 Signal 向主线程投消息，因此可以在 pytest 的离屏模式
# （QT_QPA_PLATFORM=offscreen）里直接实例化并驱动。
#
# 竞态处理：
#   · session_id —— 「停止 → 立即启动」时旧会话的迟到回调会把新会话 UI 打回未运行；
#   · _stopping  —— 停止窗口内禁止再次启动；复位必须放 finally 且早于会话校验（MI-08）；
#   · 单飞闸门   —— attach 控制台是**进程全局**状态，两条路径（停止录制 / 彻底退出）
#                  并发时 CTRL_BREAK 会错投或丢失，退化成 taskkill 硬杀。
from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading
import time
from typing import Callable, Final

from PySide6.QtCore import QObject, Signal

# 子进程环境构造：src/logger.py 的 child_process_env（剔除 GUI 父进程标记）。
from src.logger import child_process_env

from .shared import ANSI_ESCAPE_PATTERN, STOP_REUSE_JOIN_SECONDS, cleanup_process_tree, send_ctrl_break_to_child

# 读线程的批次大小：10 行一批入队再做一次跨线程投递。ffmpeg 报错时单行突发很密（实测一串
# 能连绵 200+ 行警告），逐行 emit 会让主线程事件队列积压；批量后 UI 侧每 200ms 只做一次
# 光标定位而不是 200 次。
_READ_BATCH_SIZE: Final[int] = 10
# 读线程「空行 + 进程仍活」形态的短轮询间隔与累计上限（M-79，2026-10-21）：readline()
# 返回空串只意味着管道当前无数据（写端还被孙进程握着等），不代表进程已退出；旧实现按
# 0.05s 无限忙轮询，没有任何退出条件。定稿 = 累计空等超过上限后退化为**阻塞** proc.wait()
# （唤醒点是进程真实终止），既终结空转，也不引入新的定时器。
_READ_POLL_INTERVAL_SECONDS: Final[float] = 0.05
_READ_IDLE_LIMIT_SECONDS: Final[float] = 5.0


class RecorderController(QObject):
    # 向主线程投递的信号；Qt 的跨线程自动队列（AutoConnection）使这几条天然线程安全，
    # 取代旧版的 _ui_event_queue + post_ui 事件泵。
    # outputReady 刻意不携带数据本体（S-01）：批次只在 _read_queue 存一份、由主线程 drain()
    # 取空。信号带批次会让同一批日志被消费两遍，只发信号又会让节流批次失去落点。
    outputReady = Signal()  # 队列里有了新内容（日志批次或结束哨兵），请主线程来 drain()
    ended = Signal(object)  # session_id（自然 EOF / 读取异常）
    logRequested = Signal(str, str)  # message, level
    started = Signal(int)  # pid

    def __init__(self, urls_file: str, app_root: str, script_dir: str) -> None:
        super().__init__()
        self.urls_file = urls_file
        self.app_root = app_root
        self.script_dir = script_dir

        self._process: subprocess.Popen[str] | None = None
        self._process_pid: int | None = None
        # M-79（2026-10-21）：最近一次录制子进程的 PID，**专供退出收尾的进程树清理**。
        # 与 _process/_process_pid 不同，它不随 _clear_process 归零——停止路径抢先把句柄
        # 清掉后，shutdown 侧再读 proc.pid 只会拿到 None，cleanup_process_tree(None) 直接
        # 早退，「子进程没死利索、ffmpeg 树还挂着」的现场就被静默跳过了（孤儿录制器）。
        # 生命周期只允许 start() 覆写、停止收尾**确认进程已终止**时清零，两处之外的写法
        # 都会把这个兜底重新挖空。
        self._cleanup_target_pid: int | None = None
        self._running = False
        self._stopping = False
        self._stopping_requested = False
        self._session_id = 0

        self._process_lock = threading.Lock()
        self._stop_inflight: threading.Thread | None = None
        self._stop_inflight_lock = threading.Lock()
        # 层次各一的第二把锁：_console_stop_lock 是「停止子进程」临界区的串行化闸门，
        # **只由 _stop_child_once 在其 with 块内持锁**，被它调用的 _send_stop_signal_and_wait
        # 一律不得自己再加锁、也不得被别处直接调用（改完请 grep 调用点）。
        self._console_stop_lock = threading.Lock()

        self._output_thread: threading.Thread | None = None
        self._read_queue: queue.Queue[object] = queue.Queue()
        self._read_queue_lock = threading.Lock()
        self._read_has_data = False

    # ─── 只读状态（无需持锁：bool/int 读取在 CPython 下是原子的，状态抖动不产生错误行为） ───

    def pid(self) -> int | None:
        return self._process_pid

    def session_id(self) -> int:
        return self._session_id

    def is_running(self) -> bool:
        return self._running

    def is_stopping(self) -> bool:
        return self._stopping

    def has_queue_data(self) -> bool:
        with self._read_queue_lock:
            return self._read_has_data or not self._read_queue.empty()

    # 取出当前积累的全部日志批次与“进程结束”标记（主线程调用）。
    # 生产调用方是 main_window._pump_recorder_queue（由 outputReady 唤醒），不是轮询定时器。
    def drain(self) -> tuple[list[tuple[str, str]], bool, int | None]:
        messages: list[tuple[str, str]] = []
        ended = False
        ended_session: int | None = None
        while True:
            try:
                item = self._read_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, list):
                messages.extend(item)  # type: ignore[arg-type]
            else:
                ended = True
                ended_session = int(item[0]) if item[0] is not None else None  # type: ignore[index]
        with self._read_queue_lock:
            self._read_has_data = False
        return messages, ended, ended_session

    # 自然 EOF（子进程自己退出，不是用户点停止）的进程句柄回收，由主线程消费结束哨兵后调用。
    # 不由读线程顺手清：_process 同时是 start() 的 already_running 闸门与 stop_async() 取进程
    # 对象的依据，句柄清理只允许两处出口（停止收尾 + 本方法）。不清则界面回到待机后再点
    # 「开始录制」恒报 already_running（S-01 影响 ③）。
    def reclaim_after_natural_end(self, session_id: int | None) -> None:
        if session_id is not None and session_id != self._session_id:
            return  # 旧会话的迟到哨兵不得清掉新会话刚建立的句柄（与 _stop_worker_body 同判据）
        self._clear_process()

    # ─── 启动 ───

    # 构造录制命令：冻结包是直接调同目录 CLI exe，源码运行是 python main.py。
    def build_record_command(self) -> list[str]:
        # [为什么冻结/源码两套] PyInstaller 之后 sys.executable 指向 GUI exe 自身，
        # 继续用 [sys.executable, main.py] 会递归拉起 GUI。
        if getattr(sys, "frozen", False):
            cli_name = "DouyinLiveRecorder.exe" if sys.platform == "win32" else "DouyinLiveRecorder"
            base_dir = self.script_dir
            if os.path.basename(os.path.normpath(base_dir)) == "_internal":
                base_dir = os.path.dirname(base_dir)
            cli_exe = os.path.join(base_dir, cli_name)
            if not os.path.isfile(cli_exe):
                raise FileNotFoundError(f"未找到录制核心程序: {cli_exe}")
            return [cli_exe]
        main_py = os.path.join(self.script_dir, "main.py")
        exe = sys.executable
        if sys.platform == "win32" and os.path.basename(exe).lower().startswith("pythonw"):
            # pythonw.exe 是无控制台的 GUI 子系统进程，CREATE_NEW_CONSOLE 对它无效 →
            # 子进程永远收不到 CTRL_BREAK，优雅停止（safe_exit 清理 ffmpeg）结构性失效。
            console_exe = os.path.join(os.path.dirname(exe), "python.exe")
            if os.path.isfile(console_exe):
                exe = console_exe
            else:
                self._log(f"未找到 console 解释器 {console_exe}，优雅停止将不可用", "warn")
        return [exe, main_py]

    def start(self) -> tuple[bool, int | None, str]:
        # 返回 (是否成功, pid, 失败原因)。失败原因为空串表示成功。
        if self._stopping:
            return False, None, "stopping"
        if self._process is not None:
            return False, None, "already_running"
        try:
            record_cmd = self.build_record_command()
        except Exception as e:
            return False, None, f"{e}"

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        creation_flags = 0
        if sys.platform == "win32":
            # CREATE_NEW_CONSOLE + SW_HIDE：给子进程一个隐藏控制台（无控制台则 CTRL_BREAK
            # 永远送不到、main.py 的 safe_exit 触发不了）；CREATE_NEW_PROCESS_GROUP 使
            # CTRL_BREAK 只投递给子进程组，不影响 GUI 自身。
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE

        try:
            proc = subprocess.Popen(
                record_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=self.script_dir,
                # 经 child_process_env() 剔除 GUI 父进程标记，否则子进程也被判为 GUI、
                # 不写录制日志文件（见 src/logger.py）。
                env=child_process_env(),
                startupinfo=startupinfo,
                creationflags=creation_flags,
            )
        except Exception as e:
            return False, None, f"{type(e).__name__}: {e}"

        with self._process_lock:
            self._process = proc
            self._process_pid = proc.pid
            # M-79：清理目标在**启动时刻**就钉住，之后句柄怎么被清都不影响退出收尾找得到
            # 那棵进程树（见 __init__ 中 _cleanup_target_pid 的注释）。
            self._cleanup_target_pid = proc.pid
            self._running = True
            self._session_id += 1
            session = self._session_id

        self._log("━" * 40)
        self._log(f"录制进程已启动 (PID: {proc.pid})")
        self._log(f"执行程序: {record_cmd[0]}")
        self._log(f"工作目录: {self.script_dir}")
        self._log("━" * 40)

        # 看门狗线程：读 stdout 并以「批次 + 结束哨兵」两种形态投给主线程；
        # 哨兵必须带会话代号（见 drain 的解析处），否则「停止后立即启动」的旧会话
        # 迟到 EOF 会把新会话的状态打回未运行。
        self._output_thread = threading.Thread(
            target=self._read_output, args=(proc, session), name="recorder-output", daemon=True
        )
        self._output_thread.start()
        self.started.emit(int(proc.pid))
        return True, proc.pid, ""

    # ─── 停止（两条路径共用的单飞入口） ───

    def _register_stop_worker(self, worker: threading.Thread) -> None:
        # 已有**在途**（alive）停止线程时不覆盖登记：否则后来者会在 _stop_child_once 里把自己
        # 认成「在途的那条」，丢掉「复用在途停止线程」这条语义。
        with self._stop_inflight_lock:
            current = self._stop_inflight
            if current is not None and current is not worker and current.is_alive():
                return
            self._stop_inflight = worker

    def _finish_stop_worker(self) -> None:
        with self._stop_inflight_lock:
            if self._stop_inflight is threading.current_thread():
                self._stop_inflight = None

    def _current_stop_worker(self) -> threading.Thread | None:
        with self._stop_inflight_lock:
            worker = self._stop_inflight
        # is_alive 在锁外判：退出路径要 join 它，绝不能带着这把锁 join（会与登记方形成锁序交叉）。
        return worker if worker is not None and worker.is_alive() else None

    # 停止子进程的唯一入口——「停止录制」与「彻底退出」两条路径都必须走这里。
    def _stop_child_once(self, proc: subprocess.Popen[str]) -> None:
        worker = self._current_stop_worker()
        if worker is not None and worker is not threading.current_thread():
            self._log("已有停止流程在途，等待其完成后再收尾（避免并发操作同一子进程控制台）")
            worker.join(timeout=STOP_REUSE_JOIN_SECONDS)
        with self._console_stop_lock:
            # 拿锁后必须复核进程状态：在途那轮（或另一条路径）可能已经把子进程终止，
            # 此时再发一遍 CTRL_BREAK 只是把日志刷脏。
            if proc.poll() is not None:
                return
            self._send_stop_signal_and_wait(proc)

    # 优雅停止核心：发信号 → 等待退出 → 超时整树强杀。返回是否走了优雅信号路径。
    # 本方法**只允许由 _stop_child_once 调用**，自身一律不加锁。
    def _send_stop_signal_and_wait(self, proc: subprocess.Popen[str]) -> bool:
        graceful_signal_sent = False
        if sys.platform == "win32":
            self._log("正在发送 CTRL_BREAK 信号（触发子进程 safe_exit 清理 ffmpeg）...")
            graceful_signal_sent = send_ctrl_break_to_child(proc.pid)
            if not graceful_signal_sent:
                # 不能只 proc.terminate()：TerminateProcess 硬杀不触发 safe_exit，
                # 其下 ffmpeg 会孤儿化继续录制，且 wait() 立即成功会绕过 taskkill /T 兜底。
                self._log("发送 CTRL_BREAK 失败，整树强制终止（避免 ffmpeg 孤儿化）", "warn")
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=5)
                except Exception as e:
                    self._log(f"taskkill 整树终止失败，回退 terminate: {e}")
                    proc.terminate()
        else:
            self._log("正在发送 SIGINT 信号...")
            try:
                os.kill(proc.pid, signal.SIGINT)
            except Exception as e:
                self._log(f"发送 SIGINT 失败，回退 terminate: {e}")
                proc.terminate()

        terminated = False
        try:
            proc.wait(timeout=15)
            terminated = True
            if graceful_signal_sent:
                self._log("进程已优雅退出（ffmpeg 已由子进程清理）")
            else:
                # 硬杀路径不能宣称「ffmpeg 已由子进程清理」
                self._log("进程已终止（硬杀路径，ffmpeg 已随进程树终止）")
        except subprocess.TimeoutExpired:
            self._log("进程未能及时退出，整树强制终止...")
        except Exception as e:
            self._log(f"等待子进程退出异常: {e}")

        if not terminated and proc.poll() is None:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=5)
                else:
                    proc.kill()
                    subprocess.run(["pkill", "-P", str(proc.pid), "-x", "ffmpeg"], capture_output=True, timeout=5)
                proc.wait(timeout=5)
                self._log("进程已强制终止")
            except subprocess.TimeoutExpired:
                self._log("警告：进程可能仍在运行！", "warn")
            except Exception as e:
                self._log(f"强制终止失败: {e}")
        return graceful_signal_sent

    # 用户点「停止录制」：只负责置位与拉起后台线程，不做任何阻塞操作（界面必须立刻回弹）。
    def stop_async(self) -> bool:
        if self._process is None:
            return False
        self._stopping = True
        self._log("━" * 40)
        self._log("正在停止录制...")
        worker = threading.Thread(target=self._stop_worker_body, name="gui-stop", daemon=True)
        self._register_stop_worker(worker)
        worker.start()
        return True

    # 退出路径：后台停止子进程（走同一个单飞入口）+ 清理 ffmpeg，完成后通知主线程收尾。
    def shutdown_async(self, on_finished: Callable[[], None] | None = None) -> None:
        worker = threading.Thread(target=self._shutdown_worker_body, name="gui-quit", daemon=True)
        self._register_stop_worker(worker)
        self._shutdown_callback = on_finished
        worker.start()

    def _stop_worker_body(self) -> None:
        proc = self._process
        session = self._session_id
        if proc is None:
            self._stopping = False
            # M-79（2026-10-21）：这是「UI 已按下停止、两个按钮按约定由 _on_recorder_ended
            # 统一恢复，而句柄被自然 EOF 的 reclaim 抢先清掉」的竞态窗口——旧实现在这里
            # 只复位 _stopping 就 return，不 emit ended，按钮永久禁用直到重启。与 M-33 对
            # 异常路径的要求同形：出口必须走统一恢复点。会话号取当前值，迟到的结束事件
            # 由 main_window._on_recorder_ended 按 _finish_handled_session 去重，不会打双遍
            # 结束日志。
            self.ended.emit(session)
            return
        try:
            self._stop_child_once(proc)
            # _stopping 复位必须在会话校验**之前**（MI-08）：它表示「停止流程进行中」，
            # 而 start() 以它为闸门拒绝启动；若放到校验之后，未来的异常分支会把 UI 永久挡住。
            self._stopping = False
            if proc.poll() is not None:
                # M-79：进程确认已终止，停止链已把整树收干净——清掉启动期钉住的清理目标，
                # 免得之后的退出收尾再对一个已回收的号码补一发 taskkill（Windows 的 PID
                # 进程退出即进复用池，命中新主人比多打一行日志严重得多）。
                self._cleanup_target_pid = None
            if session != self._session_id:
                self._log("检测到新录制会话，跳过旧会话的停止收尾")
                return
            self._clear_process()
            self.ended.emit(session)
        except Exception as e:
            self._stopping = False
            self._log(f"停止流程收尾异常: {type(e).__name__}: {e}", "error")
            # M-33：异常路径必须走与成功路径相同的出口——main_window.stop_recording 在发起停止时
            # 就禁用了两个按钮并约定「由 _on_recorder_ended 统一恢复」，不 emit ended 会让按钮
            # 永久禁用、只能重启 GUI；不清进程句柄则 is_running() 仍为真、start() 的闸门继续拦。
            # 会话号同样要带上：新会话已起时这次迟到事件必须被 _on_recorder_ended 丢弃。
            self._clear_process()
            self.ended.emit(session)

    def _shutdown_worker_body(self) -> None:
        proc = self._process
        # M-79（2026-10-21）：把 _cleanup_target_pid 的消费关系补上——旧实现只在末尾写它、
        # 全程无人读，而 child_pid 只取 self._process：停止路径（或自然 EOF 的 reclaim）已
        # 把句柄清空时 child_pid 恒为 None，cleanup_process_tree(None) 记一行就直接返回，
        # 「子进程没死利索、ffmpeg 还在录」的退出现场被静默跳过整树清理。定稿取数次序 =
        # 本次 shutdown 的 proc.pid 优先，回落启动期钉住的 PID，两者都空才是真的没得清。
        child_pid = proc.pid if proc is not None else self._cleanup_target_pid
        try:
            if proc is not None:
                self._stop_child_once(proc)
                self._clear_process()
            cleanup_process_tree(child_pid, lambda msg, level="info": self._log(msg, level))
        except Exception as e:
            self._log(f"退出清理流程异常: {e}", "warn")
        finally:
            self._finish_stop_worker()
        callback = getattr(self, "_shutdown_callback", None)
        if callback is not None:
            callback()
        self._shutdown_callback = None

    def _clear_process(self) -> None:
        with self._process_lock:
            self._process = None
            self._process_pid = None
            self._running = False

    # ─── stdout 读取线程 ───

    def _read_output(self, proc: subprocess.Popen[str], session_id: int | None) -> None:
        batch: list[tuple[str, str]] = []

        def flush_batch() -> None:
            nonlocal batch
            if batch:
                self._push(batch)
                batch = []

        if proc.stdout is None:
            self._push((session_id,))
            return

        idle_wait = 0.0
        while True:
            try:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        flush_batch()
                        self._mark_session_stopped(session_id)
                        self._push((session_id,))
                        break
                    # M-79：空行 + 进程仍在 = 管道瞬时无数据（典型：孙进程握着写端），旧实现
                    # 只有 0.05s 忙轮询、没有任何退出条件——写端一直不关这条线程就永远每秒
                    # 空转 20 次。定稿给累计上限：空等超过 _READ_IDLE_LIMIT_SECONDS 后退化为
                    # 阻塞 proc.wait()（唤醒点是进程真实终止），随后走与 EOF+已退出同一条
                    # 收尾出口，结束哨兵照投，UI 不会失去唯一的结束信号。
                    idle_wait += _READ_POLL_INTERVAL_SECONDS
                    if idle_wait >= _READ_IDLE_LIMIT_SECONDS:
                        proc.wait()
                        flush_batch()
                        self._mark_session_stopped(session_id)
                        self._push((session_id,))
                        break
                    time.sleep(_READ_POLL_INTERVAL_SECONDS)
                    continue
                idle_wait = 0.0
                clean_line = ANSI_ESCAPE_PATTERN.sub("", line.rstrip())
                batch.append((clean_line, "info"))
                if len(batch) >= _READ_BATCH_SIZE:
                    flush_batch()
            except (ValueError, OSError) as e:
                flush_batch()
                self._mark_session_stopped(session_id)
                self._push([(f"输出流已关闭: {e}", "error")])
                self._push((session_id,))
                break
            except Exception as e:
                flush_batch()
                self._mark_session_stopped(session_id)
                self._push([(f"读取输出错误: {e}", "error")])
                self._push((session_id,))
                break
        flush_batch()

    # 仅在会话未更替时把 running 置 False（WD-21：三条收尾统一口径）。
    def _mark_session_stopped(self, session_id: int | None) -> None:
        if session_id is None or session_id == self._session_id:
            self._running = False

    # 跨线程投递的唯一入口：列表 = 日志批次，元组 = 进程结束哨兵。
    def _push(self, payload: object) -> None:
        self._read_queue.put(payload)
        with self._read_queue_lock:
            self._read_has_data = True
        # 顺序必须是「先入队、后发唤醒」：反过来就存在「主线程被叫醒时这条数据还没进队列，
        # 于是 drain() 取到空、而它此后再也没有第二次唤醒」的丢单窗口（S-01 的修复点）。
        # emit 本身线程安全：接收方（主窗口）线程亲和性在主线程，Qt 自动降级为 Queued。
        self.outputReady.emit()

    def _log(self, message: str, level: str = "info") -> None:
        # 全部诊断一律以 Signal 投给 UI 的日志页：控制器不知道「该不该写文件」，
        # 那条策略属于窗口层（本项目 GUI 不落自己的日志文件）。
        self.logRequested.emit(message, level)

    def output_thread_alive(self) -> bool:
        thread = self._output_thread
        return thread is not None and thread.is_alive()

    def note_finish_skip(self) -> None:
        # UI 线程不 join 输出线程（WD-21：join 会冻结界面），因此这里只 emit 一条日志。
        self._log("录制进程已结束但输出线程仍在收尾，直接重置 UI（不阻塞主线程）")
