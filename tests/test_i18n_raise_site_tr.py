# 盲区锁：raise 位的中文文案必须在「产生点」接 tr()，且四语目录齐全。
#
# 为什么必须锁在产生点：这些消息大多作为 `{reason}` 实参插进一条已经 tr() 过的日志模板
# （main._resolve_hy_fan / _resolve_b23_tv、src/utils._make_trace_error_guard 的 str(e) 分支），
# 模板查了表、**消息本身从没被查过**——只在目录里登记原文只会造出永不生效的死条目
# （2026-10-17 逐条顺消费链实测）。
#
# 白名单用「集合相等」而非计数上限：上限只拦新增，消解掉一处却不收回白名单同样会让
# 「这条已不需要照顾」的判断长期失真（与 test_i18n_catalog_coverage 的 ⑤-B 同口径）。

import ast
import pathlib
import re
from typing import Iterator

from tests.test_i18n_catalog_coverage import _cached_catalog_key_sets

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN_FILES = ("main.py", "src/spider.py", "src/web_models.py")
_HAS_CN = re.compile(r"[一-鿿]")

# 刻意不接 tr() 的站点，键为「相对路径|消息里第一个中文常量」；每条须写明「为什么不接、谁在管」。
ALLOWED_UNTRANSLATED_RAISES = {
    # XhsUrlError 携带稳定 code（format/scheme/userinfo/port/host/short_path/room_id/non_live_path），
    # 消费点（src/spider.py 的 except XhsUrlError 两处与 main._resolve_xhslink_com）一律只读 e.code，
    # message 从不显示——登记它等于往四目录塞死条目。
    "src/spider.py|小红书链接为空",
    "src/spider.py|小红书链接格式非法",
    "src/spider.py|小红书链接协议不受支持（只接受 http/https）",
    "src/spider.py|小红书链接不允许携带用户信息（userinfo）",
    "src/spider.py|小红书链接不允许指定非默认端口",
    "src/spider.py|小红书链接域名不受支持: ",
    "src/spider.py|小红书短链路径必须是 /o/<短码>",
    "src/spider.py|小红书直播链接的房间 ID 缺失或非数字",
    "src/spider.py|小红书链接不是直播间或作者主页地址",
    # 整条以英文撰写，只有括号里的「原」是汉字；把它「译」一遍等于把英文再写成英文。
    "src/spider.py|TTingLive(原Flextv) login failed",
}

# 反向见证锚点：解析整体失效（返回空）时「0 缺失」就是假绿。
# 按名传入的 tr() 不在本文件范围内，这里只钉字面量形态的既有站点。
ANCHOR_MSGIDS = frozenset(
    {
        "URL 无法解析",
        "跳转地址不是虎牙直播间",
        "字段 {field} 必须是布尔值",
        "无法从链接中解析 TwitCasting 主播 ID: {masked_url}",
    }
)


def _cn(value: object) -> bool:
    return isinstance(value, str) and bool(_HAS_CN.search(value))


def _tr_calls(node: ast.AST) -> Iterator[ast.Call]:
    # 认 tr() 与 T() 两种标记：前者是运行期查表，后者是静态标签登记（都算「接了」）。
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        name = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
        if (
            name in ("tr", "T")
            and sub.args
            and _cn(sub.args[0].value if isinstance(sub.args[0], ast.Constant) else None)
        ):
            yield sub


def collect_raise_sites(rel_paths: tuple[str, ...] = SCAN_FILES) -> tuple[set[str], set[str]]:
    # 返回 (未接 tr() 的站点键集合, 已接 tr() 的 msgid 集合)。
    untranslated: set[str] = set()
    translated: set[str] = set()
    for rel in rel_paths:
        path = ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            # isinstance(s.value, str) 不可省：mypy 无法经 _cn() 收窄，缺了它下面的 f-string
            # 会因元素类型是 object（可能是 bytes）报 str-bytes-safe。
            cn_consts = [
                s.value
                for s in ast.walk(node.exc)
                if isinstance(s, ast.Constant) and isinstance(s.value, str) and _HAS_CN.search(s.value)
            ]
            if not cn_consts:
                continue
            hits = list(_tr_calls(node.exc))
            if hits:
                for call in hits:
                    first = call.args[0]
                    assert isinstance(first, ast.Constant)
                    translated.add(str(first.value))
            else:
                untranslated.add(f"{rel}|{cn_consts[0]}")
    return untranslated, translated


def test_untranslated_chinese_raise_sites_match_allowlist() -> None:
    untranslated, _translated = collect_raise_sites()
    extra = sorted(untranslated - ALLOWED_UNTRANSLATED_RAISES)
    stale = sorted(ALLOWED_UNTRANSLATED_RAISES - untranslated)
    assert not extra, (
        "新增未接 tr() 的中文 raise 文案：" + "；".join(extra) + " —— 在产生点包 i18n.tr()（消息被当 {reason} "
        "插值时从不查表，接了才有目录意义），或确证「该消息永远不显示」后写进白名单并注明消费点"
    )
    assert not stale, (
        "白名单里有已不存在的站点（多为文案改写或站点删除）：" + "；".join(stale) + " —— 收回本项，勿留空壳"
    )


def test_tr_wrapped_raise_msgids_are_covered_by_all_catalogs() -> None:
    # 「接了 tr() 但忘登记」：运行时静默回退原文、四语界面看不出问题，只有这里能判红。
    _untranslated, translated = collect_raise_sites()
    assert ANCHOR_MSGIDS <= translated, f"解析结果为空或漏站点，判据失效（缺锚点 {sorted(ANCHOR_MSGIDS - translated)}）"
    key_sets = _cached_catalog_key_sets()
    missing = sorted(m for m in translated if any(m not in keys for keys in key_sets.values()))
    assert not missing, "raise 位 tr() 的 msgid 未登记进全部目录：" + "；".join(repr(m) for m in missing)
