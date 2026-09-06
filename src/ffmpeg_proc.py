# -*- coding: utf-8 -*-
# FFmpeg 进程生命周期管理（独立模块，不依赖 main 的全局状态）
#
# 负责：
# - 全局登记/注销正在运行的 ffmpeg 子进程
# - 分级（q/SIGINT → terminate → kill）安全终止 ffmpeg 进程
# - 并行清理全部 ffmpeg 进程
# - 从异常 traceback 提取最内层出错行号
#
# 本模块自持 _ffmpeg_processes / _processes_lock，不引用 main 的任何全局变量，
# 可被 main / web_api / gui 等任意入口安全复用。

import os
import signal
import subprocess
import threading
import types
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger

# 全局跟踪所有 ffmpeg 进程（用于安全退出时清理）
_ffmpeg_processes: list[subprocess.Popen[bytes]] = []
_processes_lock: threading.Lock = threading.Lock()


# 把 process（新启动的 ffmpeg 子进程）登记到全局列表，供退出时统一清理；无返回值
def register_ffmpeg_process(process: subprocess.Popen[bytes]) -> None:
    # 注册新启动的 ffmpeg 进程
    with _processes_lock:
        _ffmpeg_processes.append(process)


# 从全局列表中移除已结束的 process；列表中不存在时静默跳过，无返回值
def unregister_ffmpeg_process(process: subprocess.Popen[bytes]) -> None:
    # 取消注册已结束的 ffmpeg 进程
    with _processes_lock:
        if process in _ffmpeg_processes:
            _ffmpeg_processes.remove(process)


# 分级终止 ffmpeg 子进程 proc（写 q / SIGINT → terminate → kill），timeout 为总等待秒数（按三段均分）；返回进程是否已退出
def _terminate_ffmpeg_process(proc: subprocess.Popen[bytes], timeout: int = 30) -> bool:
    # 安全地终止 ffmpeg 进程，包含多层级 fallback 机制（被多处复用，避免逻辑漂移）
    # 返回 True 表示进程已退出
    if proc.poll() is not None:
        return True
    try:
        # 第一步：尝试正常退出（发送 q 命令或 SIGINT）
        if os.name == "nt":
            if proc.stdin:
                try:
                    _ = proc.stdin.write(b"q")
                    proc.stdin.flush()
                    proc.stdin.close()
                except Exception:
                    pass
        else:
            try:
                proc.send_signal(signal.SIGINT)
            except Exception:
                pass

        # 等待进程正常退出
        try:
            _ = proc.wait(timeout=timeout // 3)
            if proc.poll() is not None:
                return True
        except Exception:
            pass

        # 第二步：尝试终止进程
        try:
            proc.terminate()
            _ = proc.wait(timeout=timeout // 3)
            if proc.poll() is not None:
                return True
        except Exception:
            pass

        # 第三步：强制杀死进程
        try:
            proc.kill()
            _ = proc.wait(timeout=timeout // 3)
            if proc.poll() is not None:
                return True
        except Exception:
            pass

        # 最后手段：尝试清理资源
        try:
            if proc.stdout:
                proc.stdout.close()
        except Exception:
            pass

        return proc.poll() is not None
    except Exception as e:
        logger.error(f"终止 ffmpeg 进程时出错: {e}")
        return False


# 清理单个 ffmpeg 进程 proc 并打印日志，供线程池并行调用；异常内部吞掉，无返回值
def _cleanup_single_ffmpeg_process(proc: subprocess.Popen[bytes]) -> None:
    # 清理单个 ffmpeg 进程（在并行线程中调用），复用公共终止逻辑
    try:
        if proc.poll() is None:
            logger.info(f"尝试终止 ffmpeg 进程 (PID: {proc.pid})")
            _ = _terminate_ffmpeg_process(proc)
        logger.info(f"ffmpeg 进程 (PID: {proc.pid}) 已清理")
    except Exception as e:
        logger.error(f"清理 ffmpeg 进程时出错: {e}")


# 用线程池并行清理全部已注册的 ffmpeg 进程并清空注册表；无入参，无返回值
def cleanup_all_ffmpeg_processes() -> None:
    # 清理所有注册的 ffmpeg 进程（并行执行）
    logger.info("正在清理所有 ffmpeg 进程...")
    with _processes_lock:
        processes_to_clean = list(_ffmpeg_processes)

    if processes_to_clean:
        with ThreadPoolExecutor(max_workers=min(len(processes_to_clean), 8)) as executor:
            futures = [executor.submit(_cleanup_single_ffmpeg_process, proc) for proc in processes_to_clean]
            for f in as_completed(futures):
                try:
                    f.result(timeout=10)
                except Exception as e:
                    logger.debug(f"清理 ffmpeg 进程异常: {e}")

    with _processes_lock:
        _ffmpeg_processes.clear()
    logger.info("所有 ffmpeg 进程清理完成")


# 从异常 e 的 traceback 最内层取真正出错的行号；返回行号字符串（无 traceback 时返回 "unknown"）
def _get_error_line(e: BaseException) -> str:
    # 从异常对象获取真正出错的行号（取 traceback 最内层帧，而非最外层）
    tb = e.__traceback__
    if not tb:
        return "unknown"
    # 遍历到 traceback 最内层，获取真正出错的行
    while tb.tb_next is not None:
        tb = tb.tb_next
    return str(tb.tb_lineno)
