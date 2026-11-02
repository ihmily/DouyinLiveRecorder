# -*- coding: utf-8 -*-
# FFmpeg 进程生命周期管理（独立模块，不依赖 main 的全局状态）
#
# 负责：全局登记/注销正在运行的 ffmpeg 子进程；分级（q/SIGINT → terminate → kill）安全终止；
# 并行清理全部 ffmpeg 进程；从异常 traceback 提取最内层出错行号。
#
# 本模块自持 _ffmpeg_processes / _processes_lock，不引用 main 的任何全局变量，
# 可被 main / web_api / gui 等任意入口安全复用。

import os
import signal
import subprocess
import threading
import time

from loguru import logger

import i18n

# 全局登记/注销正在运行的 ffmpeg 子进程
_ffmpeg_processes: list[subprocess.Popen[bytes]] = []
_processes_lock: threading.Lock = threading.Lock()

# 单进程三级终止的默认超时（秒）——与 _terminate_ffmpeg_process 的 timeout 默认值同源，
# 清理总预算按它配平，两处必须一起改。
_TERMINATE_TIMEOUT_SECONDS = 30.0
# 一次最多并行的清理工作线程数（与旧 ThreadPoolExecutor(max_workers=min(n, 8)) 同量级）
_CLEANUP_MAX_WORKERS = 8
# 总预算在「最忙分组串行长度 × 单进程超时」之外额外留出的余量（秒）：
# 覆盖事件置位、日志写入与线程调度抖动。
_CLEANUP_BUDGET_MARGIN_SECONDS = 5.0
# 并行清理总预算的**上限**（秒），None = 按 _cleanup_wait_budget() 配平。语义是上限而非固定值，
# 保留它作为显式收窄开关（测试 / 紧急退出用）。
# [历史注] 旧实现固定 45.0，而清理线程「组内串行、组间并行」：最忙那组串行长度达 2（>8 个
# 进程）时需 2×30=60s > 45s，「正在被慢速终止」的进程必然被误报成「未能终止」。
_CLEANUP_WAIT_SECONDS: float | None = None
# 单段等待的最小秒数，理由见 _stage_budget。
_MIN_STAGE_WAIT_SECONDS = 1.0

# 三级终止的第一级（「优雅退出」）两平台走**不可互换**的路径：
#   · Windows：向 stdin 写 'q' 再关闭——ffmpeg 在 Windows 上没有可用的控制台信号语义，写完
#     必须 close（部分构建要读到 EOF 才处理 'q'，见 _terminate_ffmpeg_process 内注释）；
#   · POSIX：直接发 SIGINT，ffmpeg 自行 flush 并收尾——这条路径**绝不碰 stdin**：ffmpeg 卡死
#     且不读管道时，写满的缓冲会让 stdin.write **永久阻塞**（进程内无法给管道写加超时），
#     一个进程就能把整条退出清理链路挂死。
# 抽成模块级常量而非内联 `os.name == "nt"`：CI 跑在 ubuntu（POSIX），内联的话
# tests/test_ffmpeg_proc.py 那两条「写失败也要关 stdin」的回归锁进不了分支、断言恒为假——
# 它们锁的正是「旧实现把 close() 与 write/flush 放同一个 try，写失败即跳过 close」。
# 测试侧 monkeypatch 置 True 覆盖 Windows 路径。
_QUIT_VIA_STDIN = os.name == "nt"


# 本轮清理的状态载体：在「worker 已处理完」事件之上多带一个「已确认进程终止」结果位。
# 为何多这一位：「未确认」告警读 event、注册表复核读 p.poll() is None 曾是**两套互斥的事实**
# ——worker 仍在三级终止时 poll() 恒为 None，「正在终止」被谎报成「未能终止」，而该进程稍后
# 真的退出了也没人注销它，死对象永久留在注册表里。现在两处判定读同一处事实（terminated）。
# 仍继承 threading.Event 是为了保持 _cleanup_single_ffmpeg_process(proc, finished) 的既有签名。
class _CleanupSignal(threading.Event):
    def __init__(self) -> None:
        super().__init__()
        # 只有「本轮处理完且进程确已退出」才置位；三级终止失败 / 异常均保持 False
        self.terminated = False


# 清理总等待预算（秒）：组内串行、组间并行 ⇒ 墙钟下界 = 最忙那一组的串行长度 × 单进程超时。
# process_count / worker_count 必须与 cleanup_all_ffmpeg_processes() 里的分组口径一致。
def _cleanup_wait_budget(process_count: int, worker_count: int) -> float:
    serial_depth = -(-max(process_count, 0) // max(worker_count, 1))  # 向上取整
    budget = serial_depth * _TERMINATE_TIMEOUT_SECONDS + _CLEANUP_BUDGET_MARGIN_SECONDS
    cap = _CLEANUP_WAIT_SECONDS
    if cap is not None:
        return min(budget, float(cap))
    return budget


# 把 process（新启动的 ffmpeg 子进程）登记到全局列表，供退出时统一清理；无返回值
def register_ffmpeg_process(process: subprocess.Popen[bytes]) -> None:
    with _processes_lock:
        _ffmpeg_processes.append(process)


# 从全局列表中移除已结束的 process；列表中不存在时静默跳过，无返回值
def unregister_ffmpeg_process(process: subprocess.Popen[bytes]) -> None:
    with _processes_lock:
        if process in _ffmpeg_processes:
            _ffmpeg_processes.remove(process)
    # 释放 stdin 写端（S-06）：优雅退出只在 _terminate_ffmpeg_process 里写 q 并 close，而**自然
    # 退出**的录制根本不会进终止函数（poll 非空即早退），录制期 PIPE 若无人 close 会把句柄留到
    # 解释器收尾。只 close、绝不 write：写才可能在缓冲满时永久阻塞。
    try:
        if process.stdin:
            process.stdin.close()
    except Exception:
        # 吞没即正确：句柄随进程/解释器回收，此处失败已无可恢复动作
        pass


# 按剩余预算给下一段等待分配秒数：三段均分「剩余时间」并保底 _MIN_STAGE_WAIT_SECONDS。
# [历史注] 旧实现写死 timeout//3，timeout<3 时算出 0 —— 而 proc.wait(0) 立即抛 TimeoutExpired，
# 等于**整段跳过优雅退出**（q / SIGINT）直接 terminate/kill，正在写的 MP4 因此丢 moov、产物不可播。
def _stage_budget(deadline: float, stages_left: int) -> float:
    remaining = deadline - time.monotonic()
    return max(_MIN_STAGE_WAIT_SECONDS, remaining / max(stages_left, 1))


# 分级终止 ffmpeg 子进程 proc（写 q / SIGINT → terminate → kill），timeout 为总等待秒数
# （三段按剩余预算分摊）；返回进程是否已退出。多处复用，故收敛成一处避免逻辑漂移。
# 默认值与 _TERMINATE_TIMEOUT_SECONDS 同源（清理总预算按它配平，见 _cleanup_wait_budget）。
def _terminate_ffmpeg_process(proc: subprocess.Popen[bytes], timeout: int = int(_TERMINATE_TIMEOUT_SECONDS)) -> bool:
    if proc.poll() is not None:
        return True
    deadline = time.monotonic() + max(float(timeout), _MIN_STAGE_WAIT_SECONDS * 3)
    try:
        # 第一步：尝试正常退出（Windows 写 q 到 stdin，POSIX 发 SIGINT）
        if _QUIT_VIA_STDIN:
            if proc.stdin:
                try:
                    _ = proc.stdin.write(b"q")
                    proc.stdin.flush()
                except Exception:
                    # 吞没即正确：ffmpeg 已卡死且不读 stdin 时，管道缓冲满会让 write/flush
                    # **永久阻塞**（进程内无法给管道写加超时），唯一出路就是下面的 wait → terminate
                    # → kill 三级兜底；重抛只会让清理线程提前放弃该进程。
                    pass
                finally:
                    # 写完必须关闭 stdin（旧实现只在 write 与 flush 都成功时才 close）。
                    # 不关闭则部分 ffmpeg 构建要读到 EOF 才处理 'q'；同时不假定有任何回音。
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass
        else:
            try:
                proc.send_signal(signal.SIGINT)
            except Exception:
                # 吞没即正确：进程可能已自行退出（对僵尸发信号会抛错），后续 wait 才是判据
                pass

        # 下面三段的 except Exception: pass 是刻意的：proc.wait 抛出的 TimeoutExpired 含义是
        # 「该级没等到」，正是进入下一级的条件；真正的错误由最后的 poll() 复核参与判定，
        # 在此重抛会让一个仍可杀掉的进程直接被放弃。
        try:
            _ = proc.wait(timeout=_stage_budget(deadline, 3))
            if proc.poll() is not None:
                return True
        except Exception:
            pass

        # 第二步：尝试终止进程
        try:
            proc.terminate()
            _ = proc.wait(timeout=_stage_budget(deadline, 2))
            if proc.poll() is not None:
                return True
        except Exception:
            pass

        # 第三步：强制杀死进程
        try:
            proc.kill()
            _ = proc.wait(timeout=_stage_budget(deadline, 1))
            if proc.poll() is not None:
                return True
        except Exception:
            pass

        # 最后手段：关掉仍握着的管道句柄
        # 兜底必须覆盖三支管道，不能只关 stdout。走到这里意味着三级终止
        # 全部没等到进程退出（ffmpeg 卡在不可中断IO / 孙进程握着管道写端），此时 stderr（ffmpeg 的
        # 进度与错误输出，7×24 多房间下每条录制都开着一支）与 stdin 若不关，只能等解释器收尾回收；
        # 反复启停会让清理线程一路攒 fd，且 Windows 上这些句柄还会让日志/媒体文件的归档改名撞
        # WinError 32。逐支独立 best-effort：任一支 close 抛错不得阻止后面两支。
        # 只做 close、**绝不 write**：写才会在缓冲满时永久阻塞（见上方 _QUIT_VIA_STDIN 注释里
        # POSIX 路径「绝不碰 stdin」的由来），关闭写端本身不阻塞、POSIX 侧同样安全。
        for pipe in (proc.stdout, proc.stderr, proc.stdin):
            try:
                if pipe:
                    pipe.close()
            except Exception:
                pass

        return proc.poll() is not None
    except Exception as e:
        logger.error(i18n.tr("终止 ffmpeg 进程时出错: {type_name}: {err}", type_name=type(e).__name__, err=e))
        return False


# 清理单个 ffmpeg 进程并打印日志，供清理线程串行调用；异常内部吞掉，无返回值。
# finished 为可选的「本进程已处理完」事件（成功、失败或未终止都要置位），由
# cleanup_all_ffmpeg_processes 用来实现「总预算 + 未确认即放弃等待」；传 _CleanupSignal 时
# 另置 terminated 位，使注册表复核与「未确认」告警共用同一处事实。
def _cleanup_single_ffmpeg_process(
    proc: subprocess.Popen[bytes], finished: _CleanupSignal | threading.Event | None = None
) -> None:
    try:
        if proc.poll() is None:
            logger.info(i18n.tr("尝试终止 ffmpeg 进程 (PID: {pid})", pid=proc.pid))
            # 终止返回值必须参与判定：原实现忽略返回值直接打印「已清理」，
            # 杀不掉的孤儿 ffmpeg 会继续拉流写盘，而注册表随后被清空、再也追踪不到。
            if not _terminate_ffmpeg_process(proc):
                logger.warning(
                    i18n.tr(
                        "ffmpeg 进程 (PID: {pid}) 未能完全终止，请手动检查",
                        pid=proc.pid,
                    )
                )
                return
        logger.info(i18n.tr("ffmpeg 进程 (PID: {pid}) 已清理", pid=proc.pid))
        # 成功路径才登记「已确认终止」，且必须在 finally 置位 finished **之前**
        # 写入——否则主线程被唤醒后可能读到尚未落定的结果位，等于又引入了两套事实。
        # isinstance 判定不可省：既有调用方与用例允许传裸 threading.Event。
        if isinstance(finished, _CleanupSignal):
            finished.terminated = True
    except Exception as e:
        logger.error(i18n.tr("清理 ffmpeg 进程时出错: {type_name}: {err}", type_name=type(e).__name__, err=e))
    finally:
        # 置位必须在 finally：worker 抛错时若漏置，总预算等待方只能干等到超时，
        # 把一次「已处理完」误报成「未确认清理」。
        if finished is not None:
            finished.set()


# 用守护线程分组并行清理全部已注册的 ffmpeg 进程并清空注册表；无入参，无返回值
def cleanup_all_ffmpeg_processes() -> None:
    logger.info("正在清理所有 ffmpeg 进程...")
    with _processes_lock:
        processes_to_clean = list(_ffmpeg_processes)

    # 注册表复核（函数末尾）无条件读它，故必须在 if 之前先声明为空列表：
    # 本轮快照为空时，若清理期间另有线程 register 了进程，注册表会有残留项需要归类。
    tracked: list[tuple[subprocess.Popen[bytes], _CleanupSignal]] = []
    if processes_to_clean:
        # 之一：旧写法 `for f in as_completed(futures)` 不给 as_completed 传 timeout，
        # 它本身「直到有 future 完成才返回」，能进循环体的 future 必然已完成——循环体里的
        # f.result(timeout=10) 是**死代码**，于是单个卡死的 worker 就能永久挂住整条退出链路
        # （本函数由 atexit 与 Web「停止录制」两处调用）。现改为「总预算 + 逐个等事件」。
        #
        # 之二：不再用 ThreadPoolExecutor——其 worker 是**非守护**线程，
        # concurrent.futures 在解释器收尾时 join 全部 worker，而本函数正跑在 atexit 链路上，一个
        # 卡在 stdin 写上的 worker 依旧能把进程永久钉住（`with` 退出即 shutdown(wait=True)，是第二个
        # 无界点）。故改用显式分组守护线程（组数 ≤ _CLEANUP_MAX_WORKERS，与旧 max_workers 同量级）：
        # 组内串行、组间并行，只等总预算、等不到就先返回。
        worker_count = min(len(processes_to_clean), _CLEANUP_MAX_WORKERS)
        groups: list[list[tuple[subprocess.Popen[bytes], _CleanupSignal]]] = [[] for _ in range(worker_count)]
        for index, proc in enumerate(processes_to_clean):
            entry = (proc, _CleanupSignal())
            groups[index % worker_count].append(entry)
            tracked.append(entry)

        def _run_group(members: list[tuple[subprocess.Popen[bytes], _CleanupSignal]]) -> None:
            for member_proc, member_event in members:
                _cleanup_single_ffmpeg_process(member_proc, member_event)

        for group_index, group in enumerate(groups):
            if not group:
                continue
            thread = threading.Thread(
                target=_run_group, args=(group,), name=f"ffmpeg_cleanup_{group_index}", daemon=True
            )
            thread.start()

        # 预算按「最忙分组串行长度 × 单进程超时」配平（为什么不能是固定 45s，见
        # _CLEANUP_WAIT_SECONDS 的历史注）
        budget = _cleanup_wait_budget(len(processes_to_clean), worker_count)
        deadline = time.monotonic() + budget
        pending_pids: list[str] = []
        for proc, finished in tracked:
            remaining = deadline - time.monotonic()
            if not finished.wait(timeout=max(0.0, remaining)):
                pending_pids.append(str(proc.pid))
        if pending_pids:
            # 计数与 PID 一并给出：未确认 ≠ 未终止（worker 可能仍在跑三级终止），
            # 但调用方（atexit / 面板停止）必须知道退出链路已被放弃。
            logger.warning(
                i18n.tr(
                    "ffmpeg 进程清理未在 {seconds} 秒总预算内全部确认，已放弃等待（未确认 {count} 个: {pids}）",
                    seconds=f"{budget:.0f}",
                    count=len(pending_pids),
                    pids=",".join(pending_pids),
                )
            )

    with _processes_lock:
        # 只移除「本轮已确认处理完且进程确已退出」的条目（两个事实都取自 _CleanupSignal，判据与
        # 误报形态见该类说明）。未确认与确认杀不掉的都留下，便于下次重新尝试清理与诊断。
        # 局部变量刻意避开 signal 这个名字：模块顶层 import 的 signal 会被推导式遮蔽。
        confirmed_terminated = {id(proc) for proc, tracker in tracked if tracker.is_set() and tracker.terminated}
        still_running = [p for p in _ffmpeg_processes if id(p) not in confirmed_terminated]
        _ffmpeg_processes.clear()
        _ffmpeg_processes.extend(still_running)
    if still_running:
        # 两类保留原因分开说：混成一句「未能终止」就是本轮修掉的误报。
        # 「确认未能终止」= worker 跑完三级终止仍在（真孤儿）；其余一律计入「未确认」——
        # 含本轮之后才注册进来的新进程，它们的终止状态本轮无从得知。
        confirmed_failed = sum(1 for _proc, tracker in tracked if tracker.is_set() and not tracker.terminated)
        unconfirmed = max(0, len(still_running) - confirmed_failed)
        logger.warning(
            i18n.tr(
                "{count} 个 ffmpeg 进程已保留在注册表中待下次清理（确认未能终止 {failed_count} 个、未确认 {unconfirmed_count} 个）",
                count=len(still_running),
                failed_count=confirmed_failed,
                unconfirmed_count=unconfirmed,
            )
        )
    logger.info("所有 ffmpeg 进程清理完成")


# 从异常 e 的 traceback 最内层取真正出错的行号；返回行号字符串（无 traceback 时返回 "unknown"）
def _get_error_line(e: BaseException) -> str:
    tb = e.__traceback__
    if not tb:
        return "unknown"
    # 取最内层帧而非最外层：调用链的最后一跳才是真正出错的位置
    while tb.tb_next is not None:
        tb = tb.tb_next
    return str(tb.tb_lineno)
