# 黄金样本测试：在（start_record 五条 ffmpeg 命令构造路径统一）重构之前，
# 先把当前「逐分支内联构造」产出的 ffmpeg 命令行逐字节冻结成基准快照。
#
# 设计要点：
# - 不改动 main.py 任何命令构造逻辑；本测试只「驱动」start_record 并捕获其产出的 ffmpeg_command。
# - 所有模块级配置全局量（在 main() 中赋值，import 时并不存在）由本 harness 显式钉死。
# - 网络/IO（_resolve_platform_stream / select_source_url / get_record_headers /
#   get_record_user_agent / check_subprocess / direct_download_stream / danmaku hub）
#   全部 mock，避免任何真实请求与磁盘/子进程副作用。
# - 时间冻结：datetime.today()/now() 与 time.strftime/localtime/sleep 全部替换为固定值，
#   使文件名中的时间戳确定，从而命令可逐字节比对。
# - 捕获点在 check_subprocess（5 条 ffmpeg 路径）与 direct_download_stream（直下 FLV 路径）。
# - 用例清单见 _build_cases()：5 条保存类型路径（TS / FLV / MKV / MP4 / 音频 MP3+M4A）的分段与
#   非分段组合，另加 m3u8 丢 -reconnect_at_eof、请求头注入、代理注入、海外超时 + https 关校验、
#   FLV h265→强制 TS、shopee 直下；共 20 条（2026-09-23 实测：_build_cases() 与基准 JSON 键数
#   均为 20，二者一致性由 test_golden_snapshot_shape_is_sane 机检，改清单以收集结果为准）。
#
# 用法：
#   GOLDEN_REGEN=1 python -m pytest tests/test_start_record_command_golden.py -q   # 重新生成基准
#   python -m pytest tests/test_start_record_command_golden.py -q                  # 比对基准（重构后回归）
#
# 重构该后，重跑普通模式，若任一命令与基准不符即说明行为被改动——必须回到「等价重构」。

import copy
import datetime
import json
import os
import sys
import threading
import time
import traceback
import types
from collections.abc import Generator
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "start_record_commands.json"


def _regen_enabled(raw: str | None) -> bool:
    # 原写法 `bool(os.environ.get("GOLDEN_REGEN"))` 把**非空字符串**
    # 一律当真——环境里留着 `GOLDEN_REGEN=0` / `=false` 时，20 条比对全部走 `return` 判通过，
    # 并在 session 结束时**用当前实现覆盖基准 JSON**。此后任何命令行错位（例如 `-segment_format`
    # 两值再被互换，正是 09-04 的 P0 形态）都会被固化成「新基准」，黄金快照从此自证。
    # 布尔口径一律复用 src/config_bool（AGENTS.md「布尔配置项统一解析口径」第 9 条），
    # 不在测试里另造第二套真值集合；未设置/空串/无法识别 → False（即「默认比对、不生成」）。
    from src.config_bool import parse_config_bool

    return parse_config_bool(raw if raw is not None else "", False)


_REGEN = _regen_enabled(os.environ.get("GOLDEN_REGEN"))

# 冻结时间：所有时间戳统一为这一刻（真实 strftime 保证确定性，且各分支格式差异被如实保留）。
_FIXED = datetime.datetime(2026, 9, 13, 12, 0, 0)

# select_source_url 字典字面量里引用的全部 Cookie 全局量（main() 中赋值，import 时不存在）。
_COOKIE_GLOBALS = [
    "dy_cookie",
    "tiktok_cookie",
    "ks_cookie",
    "hy_cookie",
    "douyu_cookie",
    "yy_cookie",
    "bili_cookie",
    "xhs_cookie",
    "bigo_cookie",
    "blued_cookie",
    "sooplive_cookie",
    "netease_cookie",
    "qiandurebo_cookie",
    "pandatv_cookie",
    "maoerfm_cookie",
    "winktv_cookie",
    "flextv_cookie",
    "look_cookie",
    "twitcasting_cookie",
    "baidu_cookie",
    "weibo_cookie",
    "kugou_cookie",
    "liveme_cookie",
]


@pytest.fixture(scope="module")
def main_mod() -> ModuleType:
    # 与 test_main_fixes 一致：导入前把 sys.argv[0] 钉到 main.py，否则 _app_root 解析错路径。
    old_argv = sys.argv[:]
    sys.argv = [str(_REPO_ROOT / "main.py")]
    try:
        import main

        return main
    finally:
        sys.argv = old_argv


# 收集 start_record 在某次调用中产出的 ffmpeg 命令 / 直下下载参数
#   [历史注] 这段原是类 docstring，与「注释统一 # 行注释、禁三引号 docstring」冲突
#   （scripts/check_annotations.py 判违规），改为行注释、语义不变。
class _Cap:
    def __init__(self) -> None:
        # 命令快照必须连带记录 check_subprocess 收到的 platform / danmaku_args。
        # 原先只 append 命令列表，于是「保存类型分支漏传弹幕参数」不改变任何快照内容，
        # 弹幕链路（get_danmaku_collector(platform, args, ...)）的接线断一条都没人能拦。
        self.commands: list[dict[str, Any]] = []
        self.downloads: list[dict] = []
        # start_record 的 except 分支会吞掉真实异常：日志收进本用例内对象、失败时随断言消息输出，
        # 不落盘到仓库（来龙去脉见 _setup_case 里 _capture 的注释）
        self.errors: list[str] = []


def _module_shim(module: ModuleType) -> types.SimpleNamespace:
    # 把 stdlib 模块浅拷贝成替身，只替换 main 命名空间里的全局名。
    # 直接 setattr(main.time, ...) / setattr(main.os, ...) 改的是全进程唯一的模块本体：
    # 同进程的 loguru 线程、harness 守护线程、coverage 会一起吃到假 time.time/假 makedirs。
    # 同 tests/test_record_failure_feedback.py 里 subprocess 替身（_make_subprocess_shim）的
    # 写法同源，也是 AGENTS.md「测试编写强制约定」规定的模式。
    return types.SimpleNamespace(**vars(module))


# 用例默认值：20 个用例里大多数字段相同，用「默认 + 覆盖」构造，避免 20 份复制粘贴的
# 字面量（也顺带满足 black 的行宽/换行规则，无需把每个字典逐键展开）。
# 新增用例只需列出与默认值不同的字段；默认值本身不得随意改动——改动等于改动基准语义。
#
# danmaku_args 刻意取**非空**且与真实抖音分支同形（room_id/user_id/cookie 三键，见 main.py
# 抖音解析）：该要求快照记录 check_subprocess 收到的 platform / danmaku_args，
# 而「所有用例都传 None」会把这条锁变成空锁——漏传关键字参数的分支只会把一个 None
# 换成另一个 None，快照毫无变化。无弹幕的平台（TikTok / 猫耳FM / shopee 直下）显式覆盖为 None。
_DOUYIN_DANMAKU_ARGS = {
    "room_id": "7412345678901234567",
    "user_id": "123456789012",
    "cookie": "",
}

_CASE_DEFAULTS = {
    "anchor_name": "测试主播",
    "quality": "原画",
    "platform": "抖音直播",
    "record_url": "https://live.douyin.com/123",
    "real_url": "http://pull.douyin.com/123.flv",
    "flv_url": "http://other.flv",
    "save_type": "TS",
    "split": False,
    "danmaku_args": _DOUYIN_DANMAKU_ARGS,
}


def _case(case_id: str, **overrides: Any) -> dict[str, Any]:
    # 构造一条用例：defaults 覆盖顺序在后，case_id 作为黄金基准的键名。
    # 用 deepcopy 而不是 dict()：defaults 里的 danmaku_args 是嵌套 dict，浅拷贝会让 20 条
    # 用例共用同一份对象——main.py 若在某条路径上就地改它，跨用例污染会以「快照串味」
    # 的形式出现，且只在部分用例被单跑时才显现。
    case = copy.deepcopy(_CASE_DEFAULTS)
    case.update(overrides)
    case["id"] = case_id
    return case


def _build_cases() -> list[dict[str, Any]]:
    # 用例清单按「分支」分组，组间空行 + 注释标明该组要锁住的行为不变量
    cases = [
        # —— TS（else 分支）：非分段 / 分段 / m3u8（删 -reconnect_at_eof）——
        _case("ts_plain"),
        _case("ts_seg", split=True),
        _case("ts_m3u8", real_url="http://pull.douyin.com/123.m3u8"),
        _case("ts_m3u8_seg", real_url="http://pull.douyin.com/123.m3u8", split=True),
        # —— 海外 + https + 关闭证书校验：超时时长放大 + -tls_verify 0 ——
        _case(
            "ts_overseas_https",
            platform="TikTok直播",
            record_url="https://www.tiktok.com/@user/live",
            real_url="https://pull.tiktok.com/stream.m3u8",
            overseas=["tiktok.com"],
            ssl_off=True,
            danmaku_args=None,  # TikTok 无弹幕采集器
        ),
        # —— FLV（ffmpeg 分支，非直下）：非分段 / 分段 ——
        _case("flv_ffmpeg", save_type="FLV"),
        _case("flv_ffmpeg_seg", save_type="FLV", split=True),
        # —— MKV ——
        _case("mkv", save_type="MKV"),
        _case("mkv_seg", save_type="MKV", split=True),
        # —— MP4 ——
        _case("mp4", save_type="MP4"),
        _case("mp4_seg", save_type="MP4", split=True),
        # —— 音频：MP3（保存类型含 MP3）/ M4A ——
        _case("mp3", save_type="MP3"),
        _case("mp3_seg", save_type="MP3", split=True),
        _case("m4a", save_type="M4A"),
        _case("m4a_seg", save_type="M4A", split=True),
        # —— 纯音频平台（猫耳FM）：only_audio_record=True，保存类型为 TS → 走音频分支 .m4a ——
        _case(
            "audio_only_platform",
            platform="猫耳FM直播",
            record_url="https://fm.missevan.com/live/1",
            real_url="http://pull.missevan.com/1.flv",
            danmaku_args=None,  # 纯音频平台不采集弹幕
        ),
        # —— 代理：注入 -http_proxy ——
        _case(
            "proxy",
            record_url="https://live.douyin.com/123?plat=抖音直播",
            proxy="http://127.0.0.1:8888",
        ),
        # —— 请求头：注入 -headers ——
        _case("headers", save_type="MP4", headers=True),
        # —— FLV h265 → 强制 TS（P0 事故区：段容器必须为 mpegts 而非 ipod）——
        _case(
            "h265_flv_to_ts",
            real_url="http://pull.douyin.com/123.flv?codec=h265",
            flv_url="http://pull.douyin.com/123.flv?codec=h265",
            save_type="FLV",
        ),
        # —— 直下 FLV（shopee/花椒）：不经 check_subprocess，捕获下载参数 ——
        _case(
            "direct_flv_download",
            platform="shopee",
            record_url="https://shopee.com/live/1",
            real_url="http://pull.shopee.com/1.flv",
            flv_url="http://pull.shopee.com/1.flv",
            save_type="FLV",
            danmaku_args=None,  # 直下路径不经 check_subprocess，弹幕参数恒为 None
        ),
    ]
    return cases


_CASES = _build_cases()
_GOLDEN_IDS = [c["id"] for c in _CASES]


def _setup_case(main: ModuleType, monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]) -> _Cap:
    cap = _Cap()

    # —— 钉死所有录制状态 / 配置全局量 ——
    plain = {
        "exit_recording": False,
        "recording_enabled": True,
        "recording": set(),
        "recording_time_list": {},
        "record_state_lock": threading.Lock(),
        "need_update_line_list": [],
        "not_record_list": [],
        "error_window": [],
        "url_comments": set(),
        "scheduler": None,
        "auto_update_anchor_name": False,
        "show_url": False,
        "live_status_push": False,
        "begin_show_push": False,
        "over_show_push": False,
        "over_push_message_text": "",
        "begin_push_message_text": "",
        "disable_record": False,
        "push_check_seconds": 0,
        "create_time_file": False,
        "converts_to_mp4": False,
        "delete_origin_file": False,
        "custom_script": "",
        "video_save_path": "",
        "folder_by_author": False,
        "folder_by_time": False,
        "folder_by_title": False,
        "filename_by_title": False,
        "default_path": "/recordings",
        "enable_https_recording": False,
        "loop_time": False,
        "delay_default": 0,
        "video_save_type": case["save_type"],
        "split_video_by_time": case["split"],
        "split_time": "600",
        "proxy_addr": case.get("proxy", ""),
        "proxy_addr_bak": "",
        "enable_proxy_platform_list": ["douyin"] if case.get("proxy") else [],
        "extra_enable_proxy_platform_list": [],
        "OVERSEAS_PLATFORM_HOST": case.get("overseas", []),
        "color_obj": MagicMock(),
    }
    for name, value in plain.items():
        monkeypatch.setattr(main, name, value, raising=False)

    for ck in _COOKIE_GLOBALS:
        monkeypatch.setattr(main, ck, "", raising=False)

    # ssl 校验裁决：main.py 仅当 get_effective_ssl_verify 返回 False（校验关闭）时才插入
    # -tls_verify 0，故 ssl_off=True 要让该接口返回 False。
    # 这条 setattr 必须留在上面的 for 循环**之外**：挂进循环体时 monkeypatch 只记最后一次还原点
    # （看着能跑只是因为反复覆盖同一函数的同一属性），且一旦 _COOKIE_GLOBALS 变空（新增平台忘了
    # 补 cookie 全局量）裁决就静默消失，ts_overseas_https 会以「没有 -tls_verify 0」的形态与基准
    # 不符而看不出成因。
    #   [历史注] 该附带修正前正是那种循环内写法。
    monkeypatch.setattr(
        main._http_config,
        "get_effective_ssl_verify",
        lambda platform: not bool(case.get("ssl_off", False)),
    )

    # —— 冻结时间 ——
    # 注意：真实 datetime.strftime 内部会回调 time.strftime；若把 time.strftime 直接转发给
    # _FIXED.strftime 会形成「_FIXED.strftime → time.strftime → _FIXED.strftime」无限递归
    # （实测 Stack overflow）。故此处捕获「原始」time.strftime，并以固定 timetuple 喂入，
    # 既保证确定性（格式相关，各分支真实时间戳差异被如实保留），又切断递归。
    import time as _time

    _orig_strftime = _time.strftime  # 必须在 Patch 之前捕获原始实现
    _fixed_tt = _FIXED.timetuple()
    # 以下四项全部经浅拷贝替身挂到 main 命名空间，不再触碰 stdlib time 本体
    _time_shim = _module_shim(_time)
    _time_shim.strftime = lambda fmt, t=None: _orig_strftime(fmt, _fixed_tt)
    _time_shim.localtime = lambda t=None: _fixed_tt
    _time_shim.sleep = lambda *a, **k: None
    _time_shim.time = lambda: 1_000_000.0
    monkeypatch.setattr(main, "time", _time_shim)

    class _FrozenDateTime(datetime.datetime):
        # 返回类型标 Any：typeshed 中 datetime.now/today 返回 Self，标具体类型会触发
        # override 不兼容告警（测试内冻结类，无需精确覆写签名）
        @classmethod
        def today(cls) -> Any:
            return _FIXED

        @classmethod
        def now(cls, tz: datetime.tzinfo | None = None) -> Any:
            return _FIXED

    # datetime.datetime 是 C 类型，不能 setattr 类方法；替换 main 命名空间里的 datetime 模块引用。
    # 原写法 setattr(main.datetime, "datetime", ...) 会把**真** datetime 模块的类换掉，
    # 同进程任何线程（loguru 记录时间戳、coverage）此刻都在用冻结子类。
    _datetime_shim = _module_shim(datetime)
    _datetime_shim.datetime = _FrozenDateTime
    monkeypatch.setattr(main, "datetime", _datetime_shim)

    # 所有文件系统副作用：makedirs 变 no-op，full_path 仅为确定字符串
    # 同上，os 走替身（其余 os.* 属性全部转发真实实现）
    _os_shim = _module_shim(os)
    _os_shim.makedirs = lambda *a, **k: None
    monkeypatch.setattr(main, "os", _os_shim)

    # —— mock 网络 / IO ——
    port_info = {
        "is_live": True,
        "anchor_name": case["anchor_name"],
        "title": "",
        "m3u8_url": case["real_url"],
        "flv_url": case["flv_url"],
        "actual_quality": None,
    }

    # 返回四元组 (platform, port_info, record_danmaku_args, new_record_url)（见 main.py 的
    # _resolve_platform_stream）。第 3 项以前恒为 None，此后改为按用例取值，
    # 这样「保存类型分支漏传 danmaku_args」才会体现在快照里。
    monkeypatch.setattr(
        main,
        "_resolve_platform_stream",
        lambda *a, **k: (case["platform"], port_info, case["danmaku_args"], ""),
    )
    monkeypatch.setattr(
        main,
        "select_source_url",
        lambda *a, **k: case["real_url"],
    )
    monkeypatch.setattr(
        main,
        "get_record_headers",
        lambda *a, **k: ({"Referer": "http://example.com", "Cookie": "a=b"} if case.get("headers") else None),
    )
    # 返回 None → 走默认移动端 UA（确定性）
    monkeypatch.setattr(main, "get_record_user_agent", lambda *a, **k: None)

    def _check(
        record_name: str,
        record_url: str,
        ffmpeg_command: list[str],
        record_save_type: str,
        custom_script: str,
        platform: str | None = None,
        danmaku_args: dict[str, Any] | None = None,
    ) -> bool:
        cap.commands.append(
            {
                "command": list(ffmpeg_command),
                "platform": platform,
                "danmaku_args": danmaku_args,
            }
        )
        return True  # comment_end=True → 触发 if comment_end: return，干净退出

    monkeypatch.setattr(main, "check_subprocess", _check)
    monkeypatch.setattr(main, "record_success", lambda *a, **k: None)
    monkeypatch.setattr(main, "record_error", lambda *a, **k: None)

    def _dl(
        flv_url: str,
        save_file_path: str,
        record_name: str,
        record_url: str,
        platform: str,
        cookies: str | None = None,
    ) -> bool:
        cap.downloads.append(
            {
                "flv_url": flv_url,
                "save_file_path": save_file_path,
                "record_name": record_name,
                "record_url": record_url,
                "platform": platform,
            }
        )
        # 用 setattr 而非 main.exit_recording = ...：main 已标注为 ModuleType，
        # 直接属性赋值会被 mypy 判 attr-defined（该全局量在 main() 中才绑定）
        setattr(main, "exit_recording", True)  # 直下路径无 check_subprocess，靠退出标志干净退出
        return True

    monkeypatch.setattr(main, "direct_download_stream", _dl)
    # TS 非分段分支会无条件起一个非 daemon 线程跑 converts_mp4（真实函数会卡在假路径上），
    # 这里直接 no-op，避免 pytest 等待该线程导致挂死。
    monkeypatch.setattr(main, "converts_mp4", lambda *a, **k: None)

    # 退出时房间清理：hub 调用 no-op
    import src.danmaku_monitor as _dm

    monkeypatch.setattr(_dm, "get_hub", lambda: MagicMock())
    # conftest 已把 _hub 设为 hermetic；此处再兜底，防止 finally 真连
    if hasattr(_dm, "_hub"):
        monkeypatch.setattr(_dm, "_hub", MagicMock(), raising=False)

    # start_record 的 except 会吞掉真实异常、loguru 队列在测试进程里又会卡死，故把
    # logger.error/warning 改为收进 _Cap.errors，断言失败时随消息一并输出。
    #   [历史注] 此前落盘到 tests/_exc.log：路径写死盘符、CI/Linux 失效，
    #   且在仓库里留一次性产物（现由 tests/test_test_hygiene.py 的 R4 规则拦住 *.log 残留）。
    def _capture(level: str, msg: object) -> None:
        cap.errors.append(f"[{level}] {msg}\n{traceback.format_exc()}")

    monkeypatch.setattr(main.logger, "error", lambda msg, *a, **k: _capture("ERROR", msg))
    monkeypatch.setattr(main.logger, "warning", lambda msg, *a, **k: _capture("WARNING", msg))
    # 真实异常会被 start_record 内部 except 吞掉并无限循环；让 record_error 触发退出标志，使循环
    # 在首个异常后干净退出，异常本身留在 _Cap.errors 里可读。本行**覆盖**上面 record_error 的
    # no-op 桩（顺序敏感：换到那行之前就会被 no-op 抢走，异常轮次重新变成无限循环）。
    monkeypatch.setattr(main, "record_error", lambda *a, **k: setattr(main, "exit_recording", True))

    return cap


def _actual_of(case: dict[str, Any], cap: _Cap) -> dict[str, Any]:
    if case["platform"] in ("shopee", "花椒直播"):
        return {"download": cap.downloads[0]} if cap.downloads else {"download": None}
    if not cap.commands:
        # 三个键一起给 None：快照条目形状恒定，缺命令时也不会让基准比对退化成「键都不在」
        return {"command": None, "platform": None, "danmaku_args": None}
    return dict(cap.commands[0])


# GOLDEN_REGEN=1 与 `-k` / 单条 node id / `--lf` 组合时只跑部分用例，
# 而 _REGEN_DICT 装的正是「本轮跑到的那几条」——旧实现无条件整份覆写基准 JSON，于是 20 条的黄金
# 基准当场退化成「一条命令的快照」：此后其余 19 条比对全绿却什么都不证明（黄金快照自证失效，
# 与该「基准被当前实现覆盖后一切错位都成新基准」同一失效面）。
# 判据抽成纯函数是为了让「拒绝部分覆盖」本身有用例可跑（见 test_regen_coverage_guard_*），
# 而不是只在人工变异验证里有效。
def _regen_write_block(recorded: dict[str, Any], cases: list[dict[str, Any]]) -> str | None:
    # 返回 None = 覆盖度足够、允许写盘；否则返回拒绝原因（不落盘、让会话以失败收尾）。
    # 期望集直接取 _CASES 的 id 全集——它与参数化 ids 同源，故新增用例天然进判据，不建第二份清单。
    expected = {str(case["id"]) for case in cases}
    if len(expected) != len(cases):
        # id 重复会让「覆盖 20 条」这类计数判据虚高（少跑一条也凑够数），先钉住清单本身
        return f"用例 id 存在重复（{len(cases)} 条用例只有 {len(expected)} 个唯一 id），拒绝写盘"
    got = set(recorded)
    missing = sorted(expected - got)
    unexpected = sorted(got - expected)
    if missing or unexpected:
        return (
            f"GOLDEN_REGEN 拒绝覆写基准：本轮只记录到 {len(got)}/{len(expected)} 条快照。"
            + (f" 缺失用例 {missing}；" if missing else "")
            + (f" 清单外 id {unexpected}；" if unexpected else "")
            + "多为 `-k` / 单条 node id / `--lf` 只跑了子集所致——"
            f"请整文件重跑：GOLDEN_REGEN=1 python -m pytest {Path(__file__).name} -q（基准 {_GOLDEN_PATH} 保持原样）"
        )
    return None


@pytest.fixture(scope="session", autouse=True)
def _write_golden(request: pytest.FixtureRequest) -> Generator[None]:
    yield
    if _REGEN:
        # 写盘前唯一的一道闸：覆盖度不足即拒绝（见 _regen_write_block 说明）
        reason = _regen_write_block(_REGEN_DICT, _CASES)
        if reason is not None:
            pytest.fail(reason)
        _GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GOLDEN_PATH.write_text(json.dumps(_REGEN_DICT, ensure_ascii=False, indent=2), encoding="utf-8")


_REGEN_DICT: dict = {}


def test_regen_coverage_guard_refuses_partial_and_accepts_full() -> None:
    # 行为锁（三条各判一个方向，缺任一条都留下盲区）：少一条必拒、全量放行、清单外 id 必拒
    partial: dict[str, Any] = {str(case["id"]): {} for case in _CASES[:-1]}
    reason = _regen_write_block(partial, _CASES)
    assert reason is not None, "少一条用例仍允许写盘 = 黄金基准会被部分快照覆写（LT-13 复现）"
    assert str(_CASES[-1]["id"]) in reason, f"拒绝原因未点名缺失的那条用例: {reason}"
    assert _regen_write_block({str(case["id"]): {} for case in _CASES}, _CASES) is None, "全量覆盖被误拒"
    extra: dict[str, Any] = {str(case["id"]): {} for case in _CASES}
    extra["__not_a_case__"] = {}
    assert _regen_write_block(extra, _CASES) is not None, "清单外 id 会让写出的基准立刻与用例集不一致"
    # 反向见证：判据不能对空 recorded 放行（-k 一条没跑中也会走到这里）
    empty_reason = _regen_write_block({}, _CASES)
    assert empty_reason is not None and f"{len(_CASES)}" in empty_reason, f"空快照未被拒绝: {empty_reason}"


def test_regen_coverage_guard_refuses_duplicated_case_ids() -> None:
    # 计数判据的前提是 id 唯一：重复 id 会让「覆盖数够了」虚高（少跑一条也凑够 20），
    # 故清单本身不自洽时必须拒绝写盘，而不是按 id 集合放行
    duplicated = _CASES + [_CASES[0]]
    reason = _regen_write_block({str(case["id"]): {} for case in _CASES}, duplicated)
    assert reason is not None, "用例 id 重复时判据不得放行"


@pytest.mark.parametrize("case", _CASES, ids=_GOLDEN_IDS)
def test_start_record_command_golden(
    main_mod: ModuleType, monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]
) -> None:
    cap = _setup_case(main_mod, monkeypatch, case)
    main_mod.start_record((case["quality"], case["record_url"], case["anchor_name"]))
    actual = _actual_of(case, cap)

    if _REGEN:
        _REGEN_DICT[case["id"]] = actual
        return

    if not _GOLDEN_PATH.exists():
        pytest.fail(f"黄金基准文件缺失：{_GOLDEN_PATH}（先以 GOLDEN_REGEN=1 生成）")
    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    expected = golden.get(case["id"])
    if expected is None:
        pytest.fail(f"黄金基准缺少用例 {case['id']}（重新 GOLDEN_REGEN=1 生成）")
    if case["platform"] in ("shopee", "花椒直播"):
        assert set(expected) == {"download"}, f"直下条目键形状异常（用例 {case['id']}）: {sorted(expected)}"
    else:
        # 基准条目必须真的带 platform / danmaku_args。缺键说明这份 JSON 是
        # 旧格式（手改过、或用被该污染的 _REGEN 语义重生成过），那时弹幕接线
        # 不在比对范围内——快照会「全绿但什么都没看」。
        assert {"command", "platform", "danmaku_args"} <= set(
            expected
        ), f"基准条目 {case['id']} 缺键，实际键: {sorted(expected)}（请 GOLDEN_REGEN=1 重生成）"
    # start_record 的 except 会吞掉真实异常并只打日志；命令为 None 时把捕获到的
    # ERROR/WARNING 一并抛出，否则失败信息只剩「None != [...]」，无从定位。
    assert actual == expected, (
        f"命令与黄金基准不符（用例 {case['id']}）。\n"
        f"  期望: {expected}\n  实际: {actual}\n"
        + (f"  期间日志:\n    " + "\n    ".join(cap.errors) + "\n" if cap.errors else "")
        + "若属预期重构，请先 GOLDEN_REGEN=1 重新生成基准。"
    )


# 快照自身的质量锁
#
# 黄金比对有个天然失效面：基准 JSON 一旦被「当前实现」覆盖，之后所有错位都成为新基准，
# 20 条用例会全绿地什么都不证明。下面两条把「基准是否还是一份有意义的快照」变成断言。


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, False),
        ("", False),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("1", True),
        ("true", True),
        ("YES", True),
        (" 是 ", True),
    ],
)
def test_golden_regen_switch_uses_the_shared_boolean_vocabulary(raw: str | None, expected: bool) -> None:
    # 直判锁：`GOLDEN_REGEN=0` / `=false` 绝不能再被当成「开启重生成」。
    # 口径复用 src/config_bool.parse_config_bool（AGENTS.md 关键约定第 9 条），
    # 本用例同时证明「没有第二套真值集合」——改回 bool(str) 时 "0"/"false" 两格立刻变红。
    assert _regen_enabled(raw) is expected


def test_golden_regen_is_off_in_normal_runs() -> None:
    # 会话级前提见证：普通跑法（含 CI）下 _REGEN 必须为 False。
    # 若某处把 GOLDEN_REGEN 设成了非空字符串，上面 20 条比对会在 return 里全部跳过，
    # 并在 session 末覆盖基准——这条把该前提显式化，而不是依赖「环境里恰好没有」。
    # 真的需要重生成时，用 `GOLDEN_REGEN=1 pytest ...`——那一轮本条不适用（skip 而非失败，
    # 否则重生成命令自身总是红的，会被误当成缺陷「顺手改掉」）。
    if _REGEN:
        pytest.skip("GOLDEN_REGEN=1：本条锁的是「比对模式」的前提，重生成轮次不适用")
    assert _REGEN is False, "当前会话处于「重生成基准」模式，比对用例不会执行（详见 _regen_enabled）"


def test_golden_snapshot_shape_is_sane() -> None:
    # 结构锁：条数 == 用例数、每条命令非空且含 -i、弹幕两键齐备。
    # 有人只删不改（把基准清成 {}、或把 command 写成 []）时，比对仍可能「逐条 None != None」
    # 地全绿——这条就是那类自证失效的兜底。
    assert _GOLDEN_PATH.exists(), f"黄金基准文件缺失: {_GOLDEN_PATH}"
    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    assert set(golden) == set(_GOLDEN_IDS), (
        f"基准条目与用例集不一致（基准 {len(golden)} 条 / 用例 {len(_GOLDEN_IDS)} 条）："
        f" 仅基准有 {sorted(set(golden) - set(_GOLDEN_IDS))}，仅用例有 {sorted(set(_GOLDEN_IDS) - set(golden))}"
    )
    for case in _CASES:
        entry = golden[case["id"]]
        if case["platform"] in ("shopee", "花椒直播"):
            download = entry["download"]
            assert isinstance(download, dict) and download.get("flv_url"), f"{case['id']} 的直下参数为空"
            assert download.get("platform") == case["platform"], f"{case['id']} 的直下 platform 与用例不符"
            continue
        command = entry["command"]
        assert isinstance(command, list) and len(command) > 5, f"{case['id']} 的命令为空或过短: {command}"
        assert "-i" in command, f"{case['id']} 的命令缺 -i 输入锚点（F-01 的输入侧参数全靠它定位）"
        assert str(command[command.index("-i") + 1]).startswith(
            ("http://", "https://", "rtmp://")
        ), f"{case['id']} 的 -i 后面不是拉流地址: {command[command.index('-i') + 1]!r}"
        assert entry["platform"] == case["platform"], f"{case['id']} 快照里的 platform 与用例不符"
        assert "danmaku_args" in entry, f"{case['id']} 快照缺 danmaku_args 键（SEV-2224 的接线未被记录）"
