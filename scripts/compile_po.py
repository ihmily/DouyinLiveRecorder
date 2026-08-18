# -*- coding: utf-8 -*-
# gettext 翻译编译脚本：i18n/zh_CN/LC_MESSAGES/zh_CN.po -> 同目录 zh_CN.mo
#
# 背景：gettext 运行时只读取编译后的 .mo 文件，.po 仅是维护用的源文本。
# 本仓库按 .gitignore 约定将 .mo 随源分发（Docker / 发布 zip / 源码运行均依赖），
# 因此修改 .po 后必须重新编译并提交 .mo，否则翻译改动不会生效。
# Windows 开发机通常没有 gettext 工具链（msgfmt），故此处内置纯 Python 实现，
# 输出与 GNU msgfmt 兼容的最小 .mo（按 msgid 排序、无哈希表）。
#
# 用法：
#   python scripts/compile_po.py            # 编译生成 .mo
#   python scripts/compile_po.py --check    # 校验已提交的 .mo 与 .po 是否同步（CI 用）

import io
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
    # 解析 .po 文件为 {msgid: msgstr} 映射；重复 msgid 以最后一次为准并告警。
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


def write_mo(entries: dict[str, str], path: Path) -> bytes:
    # 按 GNU mo 格式写出：排序后的 (msgid, msgstr) 表 + NUL 结尾字符串区。
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

    path.write_bytes(output)
    return output


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            # sys.stdout/stderr 标准解释器下为 TextIOWrapper（含 reconfigure）；
            # typeshed 将其声明为 TextIO | Any，TextIO 抽象基无该方法，故收窄到真实类型。
            cast("io.TextIOWrapper", sys.stdout).reconfigure(encoding="utf-8")
            cast("io.TextIOWrapper", sys.stderr).reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    if not PO_PATH.exists():
        print(f"ERROR: 未找到 {PO_PATH}", file=sys.stderr)
        return 2
    entries = parse_po(PO_PATH)
    fresh = write_mo(entries, MO_PATH)  # --check 模式也需要产出以做字节比对

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

    print(f"OK: 已生成 {MO_PATH}（{len(entries)} 条，{len(fresh)} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
