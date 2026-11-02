#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# DouyinLiveRecorder 核心包：初始化运行时环境（PATH / Node.js）并导出弹幕录制公共 API。

# Author: Hmily
# GitHub: https://github.com/ihmily
# Date: 2023-2025

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, cast

from .node_install import check_node

current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
JS_SCRIPT_PATH = current_dir / "javascript"  # JavaScript 脚本目录（用于签名算法）

# execute_dir 需指向项目根目录（主脚本所在目录），Node.js 装在根目录下的 node/。
# 冻结后资源统一在 _internal/，故统一取 src.logger.script_path（= _app_root() 的结果），
# 复用 logger 已导出的公开符号，避免跨模块引用私有符号 _app_root。
from .logger import script_path

execute_dir = script_path
node_execute_dir = Path(execute_dir) / "node"  # Node.js 可执行文件目录
current_env_path = os.environ.get("PATH", "")
# 仅在目录存在且未添加时更新 PATH，避免污染或重复追加
node_dir_str = str(node_execute_dir)
if node_execute_dir.is_dir() and node_dir_str not in current_env_path.split(os.pathsep):
    os.environ["PATH"] = node_dir_str + os.pathsep + current_env_path

# 导入期运行时检查开关：测试/CI/静态工具导入 src 包时不应触发 node 子进程检查与自动安装
# 副作用（受限环境下子进程管道偶发失败还会导致导入崩溃）；生产运行不设置该变量，行为不变。
if os.environ.get("DOUYIN_SKIP_RUNTIME_CHECK", "").strip().lower() not in ("1", "true", "yes"):
    # 初始化检查 Node.js 环境（仅为副作用：缺失则自动安装，返回值此处无需处理）
    _ = check_node()


# ---------------------------------------------------------------------------
# 弹幕录制公共 API：平台名 → 弹幕类注册表 + 两个工厂函数
# ---------------------------------------------------------------------------
# 移植自 dart_simple_live，为录制工具提供与录像同步、按半小时分片的 SRT 弹幕录制能力。

from src.base import DanmakuBase

if TYPE_CHECKING:
    from src.collector import DanmakuCollector


# 平台名与 main.py 中的 platform 标识一致。注册表在函数内惰性构建，避免 `import src`
# 即拉起 websockets / protobuf 等重依赖。
def get_danmaku_class(platform: str) -> Optional[type[DanmakuBase]]:
    from src.platforms.bilibili import BilibiliDanmaku
    from src.platforms.douyin import DouyinDanmaku
    from src.platforms.douyu import DouyuDanmaku
    from src.platforms.huya import HuyaDanmaku
    from src.platforms.twitch import TwitchDanmaku

    _DANMAKU_REGISTRY = {
        "斗鱼直播": DouyuDanmaku,
        "B站直播": BilibiliDanmaku,
        "虎牙直播": HuyaDanmaku,
        "抖音直播": DouyinDanmaku,
        "TwitchTV": TwitchDanmaku,
    }
    return cast(Optional[type[DanmakuBase]], _DANMAKU_REGISTRY.get(platform))


# 工厂函数：平台不支持或 danmaku_args 为空时返回 None（导入放在函数内，避免循环依赖）。
def get_danmaku_collector(
    platform: str,
    danmaku_args: Any,
    base_filename: str,
    segment_seconds: Optional[float] = 1800.0,
    # 默认 None 而非 True——True 会顶掉平台类自己刻意设的默认值（斗鱼为 False），
    # 让该平台的普通弹幕被静默丢弃且无日志；None 表示调用方未指定、不覆盖平台默认。
    only_fans: Optional[bool] = None,
    room_name: Optional[str] = None,
    write_srt: bool = True,
) -> Optional["DanmakuCollector"]:
    from src.collector import DanmakuCollector

    cls = get_danmaku_class(platform)
    if cls is None:
        return None
    if not danmaku_args:
        return None
    return DanmakuCollector(
        danmaku_cls=cls,
        danmaku_args=danmaku_args,
        base_filename=base_filename,
        segment_seconds=segment_seconds,
        only_fans=only_fans,
        room_name=room_name,
        platform_name=platform,
        write_srt=write_srt,
    )
