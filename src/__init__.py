#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# DouyinLiveRecorder 核心包初始化 - 负责直播录制的核心功能

# Author: Hmily
# GitHub: https://github.com/ihmily
# Date: 2023-2025

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, cast

from .node_install import check_node

# 包路径配置
current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
JS_SCRIPT_PATH = current_dir / "javascript"  # JavaScript 脚本目录（用于签名算法）

# Node.js 环境配置
# execute_dir 需指向项目根目录（主脚本所在目录），Node.js 安装在根目录下的 node/ 文件夹
# 冻结后资源统一在 _internal/，故用 src.logger.script_path（即 _app_root() 的结果）统一收敛，
# 复用 logger 已导出的公开符号，避免跨模块引用私有符号 _app_root
from .logger import script_path

execute_dir = script_path
node_execute_dir = Path(execute_dir) / "node"  # Node.js 可执行文件目录
current_env_path = os.environ.get("PATH", "")
# 仅在目录存在且未添加时更新 PATH，避免污染或重复追加
node_dir_str = str(node_execute_dir)
if node_execute_dir.is_dir() and node_dir_str not in current_env_path.split(os.pathsep):
    os.environ["PATH"] = node_dir_str + os.pathsep + current_env_path

# 导入期运行时检查开关：测试/CI/静态工具导入 src 包时不应触发 node 子进程检查
# 或自动安装副作用（受限环境下子进程管道偶发失败还会导致导入崩溃）。
# 生产运行不设置该变量，行为不变。
if os.environ.get("DOUYIN_SKIP_RUNTIME_CHECK", "").strip().lower() not in ("1", "true", "yes"):
    # 初始化检查 Node.js 环境（仅为副作用：缺失则自动安装，返回值此处无需处理）
    _ = check_node()


# ---------------------------------------------------------------------------
# 弹幕录制公共 API（原 src/danmaku/__init__.py，随目录扁平化迁移至此处）
# ---------------------------------------------------------------------------
# 弹幕模块从 dart_simple_live 移植，为录制工具提供与录像同步、按半小时分片的
# SRT 弹幕录制能力。下方注册「平台名 -> 弹幕类」映射表，并对外提供
# get_danmaku_class() 与 get_danmaku_collector() 两个工厂函数。

from src.base import DanmakuBase

if TYPE_CHECKING:
    from src.collector import DanmakuCollector


# 平台名 -> 弹幕类。平台名与 main.py 中的 platform 标识一致。
# 注册表按需惰性构建，避免 `import src` 时即拉起 websockets/protobuf 等重依赖。
def get_danmaku_class(platform: str) -> Optional[type[DanmakuBase]]:
    # 返回该平台对应的弹幕类，不支持则返回 None。
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


# 工厂函数：按 platform 取弹幕类并用 danmaku_args、base_filename、segment_seconds、only_fans
# 构造 DanmakuCollector 返回；room_name / write_srt 透传给采集器（监控显示名与是否落 SRT）；
# 平台不支持或 danmaku_args 为空时返回 None（延迟导入避免循环依赖）。
def get_danmaku_collector(
    platform: str,
    danmaku_args: Any,
    base_filename: str,
    segment_seconds: Optional[float] = 1800.0,
    only_fans: bool = True,
    room_name: Optional[str] = None,
    write_srt: bool = True,
) -> Optional["DanmakuCollector"]:
    # 构造该平台的 DanmakuCollector，不支持该平台或缺少参数时返回 None。
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
