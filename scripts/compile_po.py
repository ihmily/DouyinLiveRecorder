# -*- coding: utf-8 -*-
# gettext 翻译编译脚本：i18n/zh_CN/LC_MESSAGES/zh_CN.po -> 同目录 zh_CN.mo
#
# 背景：gettext 运行时只读编译后的 .mo，.po 仅是维护用源文本；本仓按 .gitignore 约定将 .mo
# 随源分发（Docker / 发布 zip / 源码运行均依赖），故改完 .po 必须重编译并提交 .mo。Windows
# 开发机通常没有 gettext 工具链（msgfmt），故此处内置纯 Python 实现，输出与 GNU msgfmt 兼容
# 的最小 .mo（按 msgid 排序、无哈希表）。
#
# 「.po 改了但 .mo 忘了重编译」由两处同源把守（都是字节级比对，不是抽样）：
#   CI / 本地门禁块里的 `python scripts/compile_po.py --check`，以及
#   tests/test_i18n.py::TestMoCatalog::test_po_and_mo_in_sync（直接 import 本模块重算一遍）。
#
# 用法：
#   python scripts/compile_po.py            # 编译生成 .mo
#   python scripts/compile_po.py --check    # 校验已提交的 .mo 与 .po 是否同步（CI 用，零副作用不写盘）

import io
import os
import struct
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent
PO_PATH = ROOT / "i18n" / "zh_CN" / "LC_MESSAGES" / "zh_CN.po"
MO_PATH = PO_PATH.with_suffix(".mo")

# GNU .mo 文件魔数与格式版本
MO_MAGIC = 0x950412DE

# .po 字符串转义还原（与 GNU gettext 规则一致）
_UNESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def _unescape(text: str) -> str:
    # 还原 po 文件中的转义序列。
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            out.append(_UNESCAPES.get(text[i + 1], text[i + 1]))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_po(path: Path) -> dict[str, str]:
    # 解析 .po 为 {msgid: msgstr} 映射；重复 msgid 以最后一次为准并告警。
    # 返回的字典**含** gettext 的头部空 msgid ""（元信息条目），故 len() 等于 .mo 头部 N，
    # 比 JSON/YAML 目录的键数恰好多 1——往文档写条数时必须先说明用的是哪一种口径。
    entries: dict[str, str] = {}
    cur_id: list[str] | None = None
    cur_str: list[str] | None = None

    def flush() -> None:
        nonlocal cur_id, cur_str
        if cur_id is not None and cur_str is not None:
            key = "".join(cur_id)
            if key in entries:
                print(f"WARNING: 重复 msgid（以最后一次为准）: {key[:60]!r}", file=sys.stderr)
            entries[key] = "".join(cur_str)
        cur_id = None
        cur_str = None

    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            # '#~' 过时条目与其余注释行均跳过；条目边界处结束上一组
            if cur_str is not None:
                flush()
            continue
        if line.startswith("msgid "):
            if cur_str is not None:
                flush()
            cur_id = [_unescape(line[6:].strip().strip('"'))]
            cur_str = None
        elif line.startswith("msgstr "):
            cur_str = [_unescape(line[7:].strip().strip('"'))]
        elif line.startswith('"') and line.endswith('"'):
            # 续行：归属当前正在累积的字段
            piece = _unescape(line[1:-1])
            if cur_str is not None:
                cur_str.append(piece)
            elif cur_id is not None:
                cur_id.append(piece)
    flush()

    if "" not in entries:
        print("ERROR: .po 缺少空 msgid 的头部条目", file=sys.stderr)
        sys.exit(2)
    return entries


def write_mo(entries: dict[str, str]) -> bytes:
    # 按 GNU mo 格式构建字节流；不落盘——是否写入由调用方决定（--check 必须零副作用）。
    keys = sorted(entries.keys())
    ids = bytearray()
    strs = bytearray()
    offsets: list[tuple[int, int, int, int]] = []  # (id偏移, id长度, str偏移, str长度)
    for key in keys:
        value = entries[key]
        kb = key.encode("utf-8")
        vb = value.encode("utf-8")
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\x00"
        strs += vb + b"\x00"

    n = len(keys)
    keystart = 7 * 4 + 16 * n  # 头部 7 字段 + 每条目 2×(长度,偏移) 的原/译文表
    valuestart = keystart + len(ids)
    koffsets: list[int] = []
    voffsets: list[int] = []
    for id_off, id_len, str_off, str_len in offsets:
        koffsets += [id_len, id_off + keystart]
        voffsets += [str_len, str_off + valuestart]

    output = struct.pack("<Iiiiiii", MO_MAGIC, 0, n, 7 * 4, 7 * 4 + n * 8, 0, 0)
    output += struct.pack(f"<{2 * n}i", *koffsets)
    output += struct.pack(f"<{2 * n}i", *voffsets)
    output += bytes(ids) + bytes(strs)
    return output


def main() -> int:
    # .po 的 msgid/msgstr 全是中文，把条目打到控制台时若沿用 cp936 输出码页就会
    # UnicodeEncodeError（i18n 三件套必须在 UTF-8 下跑，与 MID-63 同源）。
    # 只在本进程内 reconfigure，不改环境变量——那会污染同一次调用里的其它子进程。
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            # sys.stdout/stderr 标准解释器下为 TextIOWrapper（含 reconfigure）；
            # typeshed 将其声明为 TextIO | Any，TextIO 抽象基无该方法，故收窄到真实类型。
            # errors="replace" 与同仓 8 处同类站点同口径（AGENTS「任何 reconfigure 显式给 errors」）：
            # 缺省会重置为 strict，中文 Windows 下一条 emoji/中文行即可让门禁崩掉进程。
            cast("io.TextIOWrapper", sys.stdout).reconfigure(encoding="utf-8", errors="replace")
            cast("io.TextIOWrapper", sys.stderr).reconfigure(encoding="utf-8", errors="replace")
        except AttributeError, OSError:
            pass

    if not PO_PATH.exists():
        print(f"ERROR: 未找到 {PO_PATH}", file=sys.stderr)
        return 2
    entries = parse_po(PO_PATH)
    # 下面打印的「条数」含头部空 msgid，即 .mo 头部的 N，比 en_US.json / zh_TW.yaml 的键数
    # 恰大 1；往文档写目录条数时必须注明用的是哪种口径（两种不得互换，见 AGENTS.md）。
    # 先在纯内存里产出编译结果：--check 分支绝不触碰磁盘上的 .mo，否则读回自己刚写的文件
    # 必然相等，校验恒真、门禁形同虚设。
    # [历史注] parse_po/write_mo 遇坏 .po 旧实现以未捕获异常裸栈收场（rc=1），现收敛为
    # rc=2 + 明确错误行（契约见下方退出码分级，2 = 门禁本身没数据可判）。
    try:
        fresh = write_mo(entries)
    except Exception as e:
        print(
            f"ERROR: .po 编译失败（门禁无数据可判，按契约回 rc=2）: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return 2

    # 退出码：0 已同步；1 .mo 与 .po 不同步；2 门禁本身没数据可判（找不到 .po，
    # 或 .po 连头部空 msgid 条目都没有——见 parse_po 的 sys.exit(2)，与 MIN-19 口径同族）。
    # --check 比的是**完整字节流**而不是抽样：任何 .po 改动忘记重编译都会在这里变红。
    if "--check" in sys.argv:
        committed = MO_PATH.read_bytes() if MO_PATH.exists() else b""
        if committed != fresh:
            print(
                f"ERROR: {MO_PATH.name} 与 {PO_PATH.name} 不同步，请运行 python scripts/compile_po.py 后提交",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {MO_PATH.name} 与 .po 同步（{len(entries)} 条）")
        return 0

    # 写入原子化：直接覆盖时中途失败会留下截断的 .mo，gettext 静默回落到原文，
    # 而 --check 门禁不再报警。先写同目录临时文件再 os.replace，保证要么旧要么新。
    tmp_path = MO_PATH.with_name(MO_PATH.name + ".tmp")
    _ = tmp_path.write_bytes(fresh)
    os.replace(tmp_path, MO_PATH)
    print(f"OK: 已生成 {MO_PATH}（{len(entries)} 条，{len(fresh)} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
