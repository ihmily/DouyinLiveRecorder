# -*- coding: utf-8 -*-
# src/config_read.py — config.ini 读取侧：容错解析器与「重复键」点名。
#
# 为什么单独成模块：这条判据必须同时被录制引擎（main.py 的模块级裸读）与 GUI/Web 进程
# （ui_theme / ui_scale / ui_fonts、src/gui_qt/main_window）复用，而
# src/config_io.py 在导入期就 `import main`（会把录制引擎的 file_update_lock 体系带进 GUI 进程，
# AGENTS.md「GUI 主题层」明令禁止），src/web_config.py 又自居不落日志的纯函数模块。
# 故这里只依赖 stdlib + i18n + logger，并复用 web_config 的 TEXT_ENCODING 取值。
#
# 职责边界：只管「读」与「把重复项告诉用户」；写回（缺键补写、行级替换）仍在
# config_io / web_config，不得由此处代劳。

import configparser
import os
from pathlib import Path
from typing import Final

import i18n
from src.logger import logger
from src.web_config import TEXT_ENCODING

# 「同一份文件形态只点名一次」的记忆集：状态链每 10s 读一次 config.ini，不去重会把同一条
# 告警刷满日志。键取 (绝对路径, mtime)，配置一改写就重新点名一次。
# GUI 线程与录制线程都会进来，GIL 下 add/clear 竞争最多让同一条多报一次、不会漏报，
# 因此刻意不加锁；封顶 _DUP_WARN_CACHE_MAX 项后整体清空，陈旧项的代价只是「可能再报一次」。
_DUP_WARNED: set[tuple[str, float]] = set()
_DUP_WARN_CACHE_MAX: Final[int] = 32


# 构造「同一节内落出两行同名键时，仍能读出全部其它配置」的解析器。
# [为什么必须 strict=False] configparser 各解析类的默认 strict=True 把重复键判成
# DuplicateOptionError，后果是**整份 config.ini 一个键都读不出来**：main.py 的模块级裸读
# 因此让录制核心 import 即崩（现场只剩 logs/gui.log、没有 streamget.log），GUI 侧则每轮静默
# 回落默认值。用一行重复换整份配置失效并不成比例。
# strict=False 的取值语义是「后写覆盖前写」（与 configparser 自身的 dict 内存态一致），
# 重复项因此**不得静默**——由 warn_duplicate_options 点名到 节/键/行号。
def tolerant_config_parser(preserve_case: bool = False) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    if preserve_case:
        # GUI 侧历史形态：中文节/键名原样保留（optionxform 恒等）。mypy 不接受直接给
        # optionxform 赋一个签名不同的函数，沿用调用点既有的 setattr 口径。
        def _identity_optionxform(optionstr: str) -> str:
            return optionstr

        setattr(parser, "optionxform", _identity_optionxform)
    return parser


# 枚举「同一节内出现两次以上的键」：返回 [(节名, 键名, (行号, ...))]，行号自 1 起、按出现顺序。
# 判据复刻 configparser 的读取口径——# / ; 起始的整行算注释、[节名] 换节、键取首个 = 或 :
# 之前并 strip。键名一律 casefold 比较：optionxform 的默认行为就是转小写，忽略大小写才等于
# 解析器实际看到的键集合（本仓键多为中文，这条只对 language / gui_* 这类 ASCII 键有意义）。
# 无节头的裸键归到空节名下——那种文件 configparser 自己会先抛 MissingSectionHeaderError，
# 本函数只是归因辅助，不重复做格式裁判。
# 整行没有 = 也没有 : 的一律不算键：configparser 把这种行当**续行**并入上一条键的值（多行值形态，
# L-17，2026-10-19），旧实现把缩进 strip 掉后当独立键统计，于是每份带多行值的配置都被误报成重复，
# 虚假告警会把 warn_duplicate_options 的「同一形态只报一次」额度耗尽、真重复反被淹没。
# 放过它不会漏报：allow_no_value 在本仓从未开启（tolerant_config_parser 用默认值），无分隔符的
# 行根本不会被解析成键，因此**不可能**成为重复键的一方。
def find_duplicate_options(text: str) -> list[tuple[str, str, tuple[int, ...]]]:
    buckets: dict[tuple[str, str], list[tuple[int, str]]] = {}
    section = ""
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line[0] in "#;":
            continue
        # M-54（2026-10-21）：以空白起始的行**一律先跳过**。上一条分隔符判据只放过了「整行不含
        # = 也不含 :」的续行，于是 `cookie = v1` 之后跟着两行缩进续值 `   token=abc` / `   token=def`
        # 时，这两行会被 strip 后当成两个同名键 → 误报「存在重复配置项」。后果不止于噪声：
        # warn_duplicate_options 的「同一文件形态只点名一次」额度只有 _DUP_WARN_CACHE_MAX(32) 项，
        # 被假告警吃掉后**真重复反而不再被点名**，正是本函数要防的形态。
        # 依据：configparser 3.14 的 _handle_continuation_line 把「当前行缩进 > 上一条键的缩进」的
        # 行折进上一条键的值（本仓配置键一律顶格写，故任何缩进行的缩进都大于 0），因此缩进行不是键。
        # 已知边界（两处可接受的漏报/窄化方向，实测口径来自 3.14 configparser 本体）：
        # ① 整节每行同缩进且同名重复（`[s]\n   k = v1\n   k = v2`）——configparser 确实把它当两个键，
        #    本函数会跳过；② 节头本身被缩进且该节前已有键时，configparser 会把它折进上一条键的值，
        #    本函数跳过后节名归属沿用上一节。两者都不是本仓任何写入方（configparser.write 顶格输出）
        #    能产出的形态，且与本次要消灭的误报相比是次要面；若要彻底收口，正解是改用
        #    parser.read_string 统计而不是继续手抄判据。
        if raw_line[:1] in (" ", "\t"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        # 与 configparser 的默认 delimiters ('=', ':') 同集合，故这里也写字面两个字符；
        # 判据必须是「整行里有没有分隔符」，不能用 split 后的 head 是否为空——无分隔符的行
        # split 出来 head == line（非空），会被当成键名继续统计。
        if not any(delimiter in line for delimiter in ("=", ":")):
            continue
        head = line.split("=", 1)[0].split(":", 1)[0].strip()
        if not head:
            continue
        buckets.setdefault((section, head.casefold()), []).append((lineno, head))
    return [
        (section, items[0][1], tuple(lineno for lineno, _ in items))
        for (section, _lower), items in buckets.items()
        if len(items) > 1
    ]


# 读取 config.ini 并把重复键落一条 warning；返回重复键的条数（0 = 文件干净，或读不出内容）。
# 读不出内容时**不**在这里告警：文件缺失/不可读/编码错由调用方的解析路径给出结论，本函数的
# 职责只是「已决定按容错方式读时，顺带说明哪几处被折叠」，两处都报会让同一次故障有两条口径。
def warn_duplicate_options(config_file: str | Path, encoding: str = TEXT_ENCODING) -> int:
    try:
        mtime = os.stat(config_file).st_mtime
        with open(config_file, encoding=encoding, newline="") as fp:
            text = fp.read()
    except OSError, UnicodeDecodeError:
        return 0
    duplicates = find_duplicate_options(text)
    if not duplicates:
        return 0
    marker = (os.path.abspath(str(config_file)), mtime)
    if marker not in _DUP_WARNED:
        if len(_DUP_WARNED) >= _DUP_WARN_CACHE_MAX:
            _DUP_WARNED.clear()
        _DUP_WARNED.add(marker)
        detail = "; ".join(
            f"[{section}] {option} @ {', '.join(str(lineno) for lineno in lines)}"
            for section, option, lines in duplicates
        )
        logger.warning(i18n.tr("config.ini 存在重复配置项，已按最后一次取值读取: {detail}", detail=detail))
    return len(duplicates)
