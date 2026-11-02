# -*- coding: utf-8 -*-
import datetime
import os
import re
import subprocess
import sys
import time

from loguru import logger

import i18n
import main
from src import utils

# 视频后处理（独立模块）：FFmpeg 分段 / 转封装 / 转码 / 时间字幕生成
#
# - 大部分函数仅依赖文件级参数与 ffmpeg 命令，不触碰 main 全局状态；
# - 仅 converts_mp4 / generate_subtitles 需要读 main 的少量配置全局变量（converts_to_h264 /
#   color_obj / text_encoding / recording / record_state_lock），经 `import main` 在运行时
#   惰性读取，避开循环导入与 __main__ 二次执行问题。
#
# 线程归属：本模块的函数不跑在调用它的主线程里——generate_subtitles 由 main.py 的
# _subtitle_thread_target / _subtitle_thread_target_direct 起 daemon 线程，converts_* 与
# segment_video 由 _submit_postprocess 投进后处理线程池。而全仓 threading.excepthook 只在 gui.py
# 装过（且只覆盖 GUI 父进程），录制子进程里线程内的未捕获异常默认没有 hook：traceback 只落
# stderr，随即被 display_info 的 "\033[2J" 清屏刷掉，房间状态照旧显示「正在录制」——即静默死亡。
# 故本模块的循环体/写盘路径必须就地捕获，不能指望全局兜底；也不在本模块另装 hook（跨进程归属
# 决策留给主会话，再补一个只会形成第二份 hook）。
# [2026-10-30 L-07 更正] 上段「segment_video 由 _submit_postprocess 投进后处理线程池」已失实：
# segment_video 现为 main.py:148-149 注释登记的刻意死代码（无调用方），并未进线程池；converts_*
# 仍由 _submit_postprocess 投递。原句保留作历史口径，以本注为准。

# 转码超时按源文件体积线性放大（秒/MB）。固定 600s 对「1800s 分段 + libx264 veryfast
# 重编码」在中低端机上根本不够：一段 1800s/4Mbps 的 1080p 分段约 900 MB，40~80 fps 的机器要
# 675~1350s。取 1.5 s/MB（≈0.67 MB/s，对应偏慢的那一档）作放大系数。超时被 kill 的重编码产物
# 没有 -movflags +faststart、moov 尚未落盘 → 完全不可播，却会与仍在的源文件一起留下。
_REENCODE_SECONDS_PER_MB = 1.5
# 转封装（-c copy）只受 IO 限制，按 25 MB/s 估
_REMUX_SECONDS_PER_MB = 0.04
# 放大后的上限（秒）：避免超大文件算出荒谬值，超过即按上限放弃等待
_MAX_CONVERT_TIMEOUT = 3600
_MB = 1024 * 1024


# 按源文件体积推算本次转码的超时上限；显式传入的 timeout 优先（调用方可强制）。
def _convert_timeout(source_path: str, re_encoding: bool, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    try:
        size_mb = os.path.getsize(source_path) / _MB
    except OSError:
        # 退化即正确：体积读不到（文件刚被移走 / 权限）时按 0 处理，落到下面的 600s 下限，
        # 行为与修复前的固定超时完全一致；此处告警只会制造与转码失败重复的噪音
        size_mb = 0.0
    rate = _REENCODE_SECONDS_PER_MB if re_encoding else _REMUX_SECONDS_PER_MB
    return int(min(_MAX_CONVERT_TIMEOUT, max(600.0, size_mb * rate)))


# 删除**本次调用**生成的不完整产物。返回是否真的删掉了。
# 判据刻意保守：调用前同名文件已存在时不删——那可能是上一次的成功产物，本次只是覆盖
# 失败，删掉反而把可用产物一起毁掉。
def _discard_partial_output(out_path: str, pre_existed: bool, source_path: str) -> bool:
    if not out_path or pre_existed or not os.path.exists(out_path):
        return False
    try:
        os.remove(out_path)
    except OSError as e:
        logger.warning(
            i18n.tr(
                "[后处理]删除本次生成的不完整产物失败: {out_path} - {type_name}: {e}",
                out_path=out_path,
                type_name=type(e).__name__,
                e=e,
            )
        )
        return False
    logger.warning(
        i18n.tr(
            "[后处理]已删除本次生成的不完整产物，源文件已保留: {out_path} / {source_path}",
            out_path=out_path,
            source_path=source_path,
        )
    )
    return True


# 「失败即清理」由三个 ffmpeg 后处理入口共用；清理下沉到 _run_postprocess_command 的两个好处：
# ① 三条入口共享一份「本次新建」快照判据；
# ② 覆盖面从 except Exception 扩到 BaseException——取消、KeyboardInterrupt、MemoryError 这类
# 不走 except Exception 的退出路径同样不再留半成品。
# 段模板（.../主播_时间_%03d.ts）的产物名在调用前不可知，故清理以「模板展开后能匹配到的
# 文件名」为准做集合差，只删本次新增的那些（快照里已存在的一律不动）。
_SEGMENT_TEMPLATE_RE = re.compile(r"%0(\d+)d")


# 把 ffmpeg 的输出参数（单文件路径或含 %0Nd 占位符的分段模板）转成匹配**文件名**的正则。
def _output_matcher(file_pattern: str) -> re.Pattern[str]:
    # 字面部分整体 re.escape：产物目录名/文件名来自 clean_name，可能含 [ ] 这类 glob 元字符，
    # 用 glob 匹配会错配（同一目录下别人的文件被当成本次半成品）。
    parts: list[str] = []
    pos = 0
    for m in _SEGMENT_TEMPLATE_RE.finditer(file_pattern):
        parts.append(re.escape(file_pattern[pos : m.start()]))
        digits = int(m.group(1))
        # %0Nd 只保证**下限**：段数超过 999 时 ffmpeg 会输出 4 位（main.py 的转码分支已按此
        # 兼容），故按「至少 N 位数字」匹配。恰好 N 位会让第 1000 片的半成品删不掉。
        parts.append(r"\d{" + str(digits) + ",}")
        pos = m.end()
    parts.append(re.escape(file_pattern[pos:]))
    return re.compile("".join(parts))


# 列出磁盘上所有匹配 out_spec（模板已展开为真实序号）的产物完整路径；目录不可读时抛 OSError。
def _match_outputs(out_spec: str) -> list[str]:
    directory, file_pattern = os.path.split(out_spec)
    matcher = _output_matcher(file_pattern)
    # directory 为空（裸文件名）时按当前目录列，与 ffmpeg 的落盘位置一致。
    # 匹配 entry.name、再显式 join 回 directory：os.scandir(".") 给出的 entry.path 是
    # "./x.ts"，与 out_spec 不同形，直接用会让快照与后一次列表对不上。
    return [
        os.path.join(directory, entry.name) for entry in os.scandir(directory or ".") if matcher.fullmatch(entry.name)
    ]


# 为**本次调用**建立产物快照；返回 None 表示快照不可得（目录列不出来）。
def _snapshot_outputs(out_spec: str) -> set[str] | None:
    try:
        return set(_match_outputs(out_spec))
    except OSError as e:
        # 这里必须区分「原先没有文件」与「看不见目录」：后者若返回空集，随后一次成功的目录
        # 扫描会把上一次录制留下的**有效分段**全当成「本次新建」删掉。宁可不清理（顶多留一份
        # 半成品，用户还能自行判断），也不能删错可用产物。
        logger.warning(
            i18n.tr(
                "[后处理]无法读取产物目录，本次跳过半成品清理: {out_path} - {type_name}: {e}",
                out_path=utils.mask_credentials(os.path.dirname(out_spec) or "."),
                type_name=type(e).__name__,
                e=e,
            )
        )
        return None


# 删除 out_spec 匹配到的、本次调用新增的产物（快照之后才出现的文件）。
def _discard_new_outputs(out_spec: str, pre_existed: set[str], source_path: str) -> None:
    try:
        current = _match_outputs(out_spec)
    except OSError as e:
        logger.warning(
            i18n.tr(
                "[后处理]失败后无法读取产物目录，半成品未清理: {out_path} - {type_name}: {e}",
                out_path=utils.mask_credentials(os.path.dirname(out_spec) or "."),
                type_name=type(e).__name__,
                e=e,
            )
        )
        return
    for path in current:
        if path in pre_existed:
            continue
        # pre_existed 已过滤，故这里恒传 False：确属本次新建，交给 _discard_partial_output 落日志
        _discard_partial_output(path, False, source_path)


# 执行一条后处理 ffmpeg 命令；任何非正常退出（失败/超时/取消）后清理本次新增的半成品产物。
def _run_postprocess_command(command: list[str], out_spec: str, source_path: str, timeout: int = 600) -> None:
    # 「本次创建」的判据必须在启动 ffmpeg **之前**取，不能事后用 mtime 猜（该同一口径）。
    pre_existed = _snapshot_outputs(out_spec)
    try:
        _run_ffmpeg_checked(command, timeout=timeout)
    except BaseException:
        if pre_existed is not None:
            _discard_new_outputs(out_spec, pre_existed, source_path)
        # 原样抛出：分类日志仍由各入口的 except 分支负责（超时/转换失败/未知错误三种语义
        # 必须区分，见 tests/test_video_postprocess_paths.py 的异常分类用例）
        raise


# Windows 下 subprocess.STARTUPINFO 仅存在于 Windows typeshed，Linux/macOS 上 mypy 无法解析该名字。
# 返回值用 object 而非具体 STARTUPINFO：该符号在非 Windows typeshed 中不存在，无法作为跨平台
# 类型引用；调用方仅透传给 subprocess 的 startupinfo 参数，object | None 不损失实际类型安全。
def get_startup_info(system_type: str) -> object | None:
    # 按 system_type（os.name 取值）返回子进程启动参数：只在 Windows（"nt"）构造隐藏窗口的
    # STARTUPINFO，其余平台恒返 None；mypy 依 sys.platform 字面量分支跳过非当前平台代码。
    if system_type != "nt":
        return None
    if sys.platform == "win32":
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startup_info
    return None


# 同步执行 ffmpeg 命令 command（超过 timeout 秒则杀掉子进程并抛 TimeoutExpired，避免转码卡死
# 永久挂住后处理线程池的工作线程）；返回合并后的输出文本，返回码非 0 时抛 CalledProcessError
def _run_ffmpeg_checked(command: list[str], timeout: int = 600) -> str:
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=get_startup_info(main.os_type)
    ) as process:
        try:
            out, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            # 第二次 communicate 必须带超时（对齐 notify.py 该同款防线）——
            # kill() 只杀直接子进程，孙进程握着管道写端时无超时的读取会永久挂住后处理线程；
            # 超时后抛 TimeoutExpired 交上层兜底，输出取「已读到的部分」。
            try:
                out, _ = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                out = b""
                raise
            raise
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command, output=out)
        return out.decode("utf-8", errors="replace")


# 用 ffmpeg 把 converts_file_path 按 segment_time 秒切分为 segment_format 容器，
# 输出到 segment_save_file_path（含编号占位符的模板）；is_original_delete=True 时删除源文件，无返回值
def segment_video(
    converts_file_path: str,
    segment_save_file_path: str,
    segment_format: str,
    segment_time: str,
    is_original_delete: bool = True,
) -> None:
    try:
        if os.path.exists(converts_file_path) and os.path.getsize(converts_file_path) > 0:
            ffmpeg_command = [
                "ffmpeg",
                "-i",
                converts_file_path,
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-map",
                "0",
                "-f",
                "segment",
                "-segment_time",
                segment_time,
                "-segment_format",
                segment_format,
                "-reset_timestamps",
                "1",
                "-movflags",
                "+frag_keyframe+empty_moov",
                # 补 `-n`（输出已存在时立即退出、不询问），与 converts_m4a / converts_mp4 对齐：
                # 目标名与磁盘已有文件撞车时 ffmpeg 会打印 "Overwrite? [y/N]"，而本命令由
                # _run_ffmpeg_checked 以管道启动、子进程没有可用 stdin → read 直接 EOF（等同选 N），
                # 于是走满 600s 超时才把进程 kill 掉。
                # 生效范围：覆盖询问发生在解析输出文件参数时，故字面文件名时必需；模板名必然不存在，
                # `-n` 属无害的对称写法。与 `-y` 相反：撞名说明已有上一次的成功分段，立即失败 + 只删
                # 本次新增才是安全语义。
                "-n",
                segment_save_file_path,
            ]
            _run_postprocess_command(ffmpeg_command, segment_save_file_path, converts_file_path)
            if is_original_delete:
                time.sleep(1)
                if os.path.exists(converts_file_path):
                    os.remove(converts_file_path)
    except subprocess.TimeoutExpired as e:
        # 与「转码失败」「未知失败」区分：超时表明 ffmpeg 卡死，须告警用户主动排查，
        # 不能并进 except Exception 兜底成「unknown error」丢失语义。
        logger.error(i18n.tr("ffmpeg 转封装/转码超时（{type_name}）: {e}", type_name=type(e).__name__, e=e))
    except subprocess.CalledProcessError as e:
        logger.error(i18n.tr("Error occurred during conversion: {e}", e=e))
    except Exception as e:
        logger.error(i18n.tr("An unknown error occurred: {e}", e=e))


# 把 converts_file_path 转封装为同名 .mp4（全局 converts_to_h264 开启时重编码为 h264）；
# is_original_delete=True 时删除源文件；timeout 为总等待秒数，None 表示按源文件体积自动放大
# 。失败/超时会清理本次生成的半成品 .mp4 并保留源文件，无返回值
def converts_mp4(converts_file_path: str, is_original_delete: bool = True, timeout: int | None = None) -> None:
    # out_path 在 try 外预置：except 分支与基于它的清理出口要能判定「本次是否已生成过输出」，
    # 否则 basedpyright 判 possibly unbound、且早期异常（如体积读取）会误删无关文件。
    # 「调用前已存在的产物集合」快照已收敛到 _run_postprocess_command，三入口共用。
    out_path = ""
    try:
        if os.path.exists(converts_file_path) and os.path.getsize(converts_file_path) > 0:
            out_path = converts_file_path.rsplit(".", maxsplit=1)[0] + ".mp4"
            re_encoding = bool(main.converts_to_h264)
            if re_encoding:
                main.color_obj.print_colored("正在转码为MP4格式并重新编码为h264\n", main.color_obj.YELLOW)
                # 补 `-n`（覆盖同名 .mp4 时不询问；无 stdin → read EOF 等同选 N，会走满 600s 超时
                # 才被回收）。开弹幕 + 分段 + 转码的组合下**每个分段**都触发一次 600s 挂死。
                ffmpeg_command = [
                    "ffmpeg",
                    "-i",
                    converts_file_path,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-vf",
                    "format=yuv420p",
                    "-c:a",
                    "copy",
                    "-f",
                    "mp4",
                    "-n",
                    out_path,
                ]
            else:
                main.color_obj.print_colored("正在转码为MP4格式\n", main.color_obj.YELLOW)
                ffmpeg_command = [
                    "ffmpeg",
                    "-i",
                    converts_file_path,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "copy",
                    "-f",
                    "mp4",
                    "-n",
                    out_path,
                ]
            _run_postprocess_command(
                ffmpeg_command,
                out_path,
                converts_file_path,
                timeout=_convert_timeout(converts_file_path, re_encoding, timeout),
            )
            if is_original_delete:
                time.sleep(1)
                if os.path.exists(converts_file_path):
                    os.remove(converts_file_path)
    except subprocess.TimeoutExpired as e:
        # 与下两类错误区分：ffmpeg 卡死须告警（与「格式不对」语义不同），否则被 except Exception
        # 兜底为 unknown error 丢失语义。半成品清理已在 _run_postprocess_command 统一执行。
        logger.error(i18n.tr("ffmpeg 转 MP4 超时（{type_name}）: {e}", type_name=type(e).__name__, e=e))
        # [历史注] 清理已上移到 _run_postprocess_command 的出口统做：超时分支原先 kill 完就 raise，
        # 会留下写到一半的 .mp4（无 -movflags +faststart，moov 未落盘 → 完全不可播）。
        # 三条路径共用同一清理点，这里只保留各自分类的日志。
    except subprocess.CalledProcessError as e:
        logger.error(i18n.tr("Error occurred during conversion: {e}", e=e))
    except Exception as e:
        logger.error(i18n.tr("An unknown error occurred: {e}", e=e))


# 把 converts_file_path 抽取音轨转为同名 320k .m4a；is_original_delete=True 时删除源文件，无返回值
def converts_m4a(converts_file_path: str, is_original_delete: bool = True) -> None:
    # out_path 预置在 try 外：与 converts_mp4 同一理由（早期异常时 except 分支不得去删无关文件）
    out_path = ""
    try:
        if os.path.exists(converts_file_path) and os.path.getsize(converts_file_path) > 0:
            out_path = converts_file_path.rsplit(".", maxsplit=1)[0] + ".m4a"
            m4a_command = [
                "ffmpeg",
                "-i",
                converts_file_path,
                "-n",
                "-vn",
                "-c:a",
                "aac",
                "-bsf:a",
                "aac_adtstoasc",
                "-ab",
                "320k",
                out_path,
            ]
            # ⑤：本函数的调用已接入统一清理——超时/CalledProcessError 后不会再留下
            # 半截 .m4a（AAC 帧头已写、尾部截断，播放器只认得到开头几秒）。
            _run_postprocess_command(m4a_command, out_path, converts_file_path)
            if is_original_delete:
                time.sleep(1)
                if os.path.exists(converts_file_path):
                    os.remove(converts_file_path)
    except subprocess.TimeoutExpired as e:
        logger.error(i18n.tr("ffmpeg 抽音频超时（{type_name}）: {e}", type_name=type(e).__name__, e=e))
    except subprocess.CalledProcessError as e:
        logger.error(i18n.tr("Error occurred during conversion: {e}", e=e))
    except Exception as e:
        logger.error(i18n.tr("An unknown error occurred: {e}", e=e))


# 时间字幕写盘失败时的告警聚合窗口与重开退避（单位＝循环秒，见 generate_subtitles 内注释）。
# 60s 与 src/collector.py 的 _SRT_WARN_INTERVAL、src/srt_writer.py 的 WD-03 口径一致：
# 逐条告警会在磁盘满时把 logs/streamget.log 刷爆（本线程每秒一条 → 每分钟 60 条 warning），
# 反而淹掉真正的排查线索；完全不告警则是「房间显示正常、字幕再也不长」的静默丢数据。
_SUB_WRITE_WARN_WINDOW = 60
# 10s 重开退避仿 src/srt_writer.py 的 _OPEN_RETRY_INTERVAL：故障期间无需每秒再发起一次
# open()（网络盘/USB 掉线时 open 本身就能拖住线程），到点试一次即可自愈。
_SUB_WRITE_RETRY_INTERVAL = 10


# 后台逐秒追加写"时间字幕"：record_name 用于判断该房间是否仍在录制（不在则结束），
# ass_filename 为不含扩展名的输出路径前缀，sub_format 为字幕扩展名；无返回值
def generate_subtitles(record_name: str, ass_filename: str, sub_format: str = "srt") -> None:
    index_time = 0
    today = datetime.datetime.now()
    re_datetime = today.strftime("%Y-%m-%d %H:%M:%S")
    # 扩展名/前缀与循环无关，提到循环外：一是长时间录制下少拼上千次同样的字符串，二是让下面失败日志里的
    # 路径与真正写入的路径**必然是同一个值**（各处分别拼接时改一处即产生「日志说 A 坏、实际坏的是 B」）
    sub_out_path = f"{ass_filename}.{sub_format.lower()}"

    # 写盘守卫的状态。计时基准一律用 index_time（循环自身的秒计数，每轮 sleep(1) 恰好
    # 推进 1 秒），**不**引入 time.monotonic()：
    #   ① 本线程的节奏定义就是「一轮一秒」，用循环计数与「实际丢了多久」严格一致，不受线程被调度
    #      推迟（GIL 争抢、池内排队）影响——被推迟时真实时钟会走完退避窗口，而这一轮其实一条都没写，
    #      用 monotonic 会误判成「已恢复」；
    #   ② 用例可确定性推进计数（现有用例把 time.sleep 换成 shim，真实时钟会让退避断言随时序抖动）。
    sub_next_warn_at = 0  # 初值 0 → 首次失败立刻可见，之后每 _SUB_WRITE_WARN_WINDOW 秒一条
    sub_next_retry_at = 0  # index_time < 该值时跳过 open()（退避中）
    sub_window_failures = 0  # 距上次告警以来丢弃的条数
    sub_total_failures = 0  # 本线程生命周期内丢弃的总条数，恢复时一并告知后归零

    # 内部工具：把 seconds 秒转为 "HH:MM:SS" 形式的字符串
    def transform_int_to_time(seconds: int) -> str:
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    while True:
        index_time += 1
        txt = (
            str(index_time)
            + "\n"
            + transform_int_to_time(index_time)
            + ",000 --> "
            + transform_int_to_time(index_time + 1)
            + ",000"
            + "\n"
            + re_datetime
            + "\n\n"
        )

        if index_time < sub_next_retry_at:
            # 退避窗口内：本次条目计丢，不发起 open()
            sub_window_failures += 1
            sub_total_failures += 1
        else:
            try:
                # 该线程跑在录制子进程里，而 threading.excepthook 全仓只有 gui.py 装过（见文件头）
                # ——磁盘满(ENOSPC) / 目录被
                # rename_anchor_directory 改名(ENOENT) / 路径过长(ENAMETOOLONG) / 权限(EACCES) 任一
                # 发生，线程就静默死掉，字幕从此不再增长且无线索。
                # 只捕 OSError 而不是 except Exception：上述四类都是 OSError 子类，其余异常（如
                # main.text_encoding 配成非法编码名的 LookupError）属真 bug，吞了会让「字幕永远
                # 不生成」再次变成无解释的现象。
                with open(sub_out_path, "a", encoding=main.text_encoding) as f:
                    _ = f.write(txt)
            except OSError as e:
                sub_window_failures += 1
                sub_total_failures += 1
                sub_next_retry_at = index_time + _SUB_WRITE_RETRY_INTERVAL
                if index_time >= sub_next_warn_at:
                    logger.warning(
                        i18n.tr(
                            "[时间字幕]写入失败，{retry}s 后重试打开；本窗口丢失 {lost} 条、累计 {total} 条: {out_path} - {type_name}: {e}",
                            retry=_SUB_WRITE_RETRY_INTERVAL,
                            lost=sub_window_failures,
                            total=sub_total_failures,
                            out_path=utils.mask_credentials(sub_out_path),
                            type_name=type(e).__name__,
                            e=e,
                        )
                    )
                    sub_next_warn_at = index_time + _SUB_WRITE_WARN_WINDOW
                    sub_window_failures = 0
            else:
                if sub_total_failures:
                    # 恢复只报一次并清零累计：否则后续每轮成功都要判一次，
                    # 且「累计」会一直保留着旧故障的数字反复出现
                    logger.warning(
                        i18n.tr(
                            "[时间字幕]写入已恢复，故障期间共丢失 {total} 条: {out_path}",
                            total=sub_total_failures,
                            out_path=utils.mask_credentials(sub_out_path),
                        )
                    )
                    sub_total_failures = 0
                    sub_window_failures = 0
                    sub_next_warn_at = 0
                    sub_next_retry_at = 0

        with main.record_state_lock:
            still_recording = record_name in main.recording
        if not still_recording:
            return
        time.sleep(1)
        today = datetime.datetime.now()
        re_datetime = today.strftime("%Y-%m-%d %H:%M:%S")
