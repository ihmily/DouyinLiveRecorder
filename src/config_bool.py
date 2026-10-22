# 布尔配置值解析（全仓统一口径，零依赖模块）。
#
# 背景：规范写法是「是/否」（config.ini 模板、README 配置块、Web 面板提示均按此文档化），但落盘值来自
# 多个写入方（Web 面板文本框 / GUI / 用户手改 / 外部编辑器 / 配置迁移脚本），故 true/false（大小写不一）、
# 1/0、yes/no、on/off 都会出现。此前各模块各写一套判据且口径互不相同（main.py 字典查表、
# logger.py `!= "否"`、web/app.js `== "是"`），同一份 config.ini 因而含义各异；2026-09-17 实测把
# 「是/否」批量改成 true/false 后 8 项配置生效值全部漂移（其中「是否跳过代理检测」漂移导致
# 9 个海外平台的解析分支直接走 else，100% 无法录制）。
#
# 本模块只做「字符串 → bool」的纯解析：无 I/O、不 import 任何本仓模块，好让加载极早的 logger.py 可直接引用
# 而不构成循环导入（logger 早于 main 执行、且 src.utils → src.logger 已有依赖链，故不能放进 utils / config_io）。
# 「读取 + 缺键补写」见 config_io.read_config_bool。

from __future__ import annotations

__all__ = ["TRUE_TOKENS", "FALSE_TOKENS", "parse_config_bool", "format_config_bool"]

# 真 / 假 值 token：比较前统一 strip + lower，故大小写与首尾空白不敏感。
# 「是/否」为本仓规范写法，其余为各写入方与外部工具的实际产出。
# 前端 web/app.js 的 CONFIG_TRUE_TOKENS/CONFIG_FALSE_TOKENS 必须与本表保持同一集合
# （改任一侧须同步另一侧；tests/frontend/test_quality_ui.mjs 从两端源码抠集合逐一比对）。
TRUE_TOKENS: frozenset[str] = frozenset({"是", "true", "t", "yes", "y", "on", "1"})
FALSE_TOKENS: frozenset[str] = frozenset({"否", "false", "f", "no", "n", "off", "0"})


# 把配置值解析为布尔。识别集合以上方 TRUE/FALSE_TOKENS 为准（strip + lower 后比较，
# 不在此复述以免漂移）；空值与无法识别的值一律返回 default。调用方必须传该配置项
# 的文档默认值，而不要传「上一次的取值」——否则非法输入会静默沿用旧值而不报警。
def parse_config_bool(raw: str | bool | int | None, default: bool) -> bool:
    # bool 短路返回：调用方可能混入 API/测试传入的 bool，走 str() 分支会得到 "True"
    # （小写后仍命中 token，但属无谓转换）。
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    token = str(raw).strip().lower()
    if token in TRUE_TOKENS:
        return True
    if token in FALSE_TOKENS:
        return False
    return default


# 把布尔值序列化为本仓配置的规范写法「是」/「否」。
# 仅用于「键缺失时补写默认值」这一处；存量值不被改写（避免对用户文件产生无谓 diff，
# 且 true/false 与 是/否 经 parse_config_bool 等价，无需迁移）。
def format_config_bool(value: bool) -> str:
    return "是" if value else "否"
