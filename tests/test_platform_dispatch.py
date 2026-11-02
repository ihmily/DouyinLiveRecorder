# 本文件锁定三条契约，防止后续「加平台 / 调顺序」时静默改变平台判定优先级：
#   1. 分发表非空、无重复处理函数、顺序即优先级（头部若干项与主平台白名单一致）；
#   2. 每个代表 URL 经分派后得到预期平台名，且走的是预期解析入口（记录 spider/stream 调用）；
#   3. 无法识别的地址返回 None；自定义流地址按**路径扩展名**判定，大小写不敏感。
#
# 所有 spider / stream 调用均替换为记录型异步桩，用例不发任何真实网络请求。

import ast
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def main_mod() -> Any:
    # 与 test_start_record_command_golden 一致：导入前把 sys.argv[0] 钉到 main.py，
    # 否则 _app_root() 解析出的路径不对（配置/日志目录会落到别处）。
    old_argv = sys.argv[:]
    sys.argv = [str(_REPO_ROOT / "main.py")]
    try:
        import main

        return main
    finally:
        sys.argv = old_argv


class _RecordingShim:
    # 记录型异步桩：任何属性访问都返回一个「记录调用名与入参、返回空 dict」的协程函数，
    # 既避免真实请求，又能让用例断言「这条 URL 走了哪个解析入口」。
    def __init__(self, tag: str, sink: list) -> None:
        self._tag = tag
        self._sink = sink

    def __getattr__(self, name: str) -> object:
        async def _fake(*args: object, **kwargs: object) -> object:
            self._sink.append((self._tag, name))
            return {}

        return _fake


@pytest.fixture
def dispatch_env(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(main_mod, "spider", _RecordingShim("spider", calls), raising=False)
    monkeypatch.setattr(main_mod, "stream", _RecordingShim("stream", calls), raising=False)
    # main() 运行期才赋值的全局量：import 期不存在，需补齐否则 NameError
    for name in (
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
        "global_proxy",
    ):
        if not hasattr(main_mod, name):
            monkeypatch.setattr(main_mod, name, "", raising=False)
    if not hasattr(main_mod, "semaphore"):
        monkeypatch.setattr(main_mod, "semaphore", threading.Semaphore(8), raising=False)
    return main_mod, calls


def test_resolver_table_is_wellformed(main_mod: Any) -> None:
    table = main_mod._PLATFORM_RESOLVERS
    # 空表意味着分派链整体丢失（所有地址都会落到「无法识别」）
    assert table, "平台分发表不应为空"
    handlers = [handler for _, handler in table]
    # 处理函数不可重复：重复意味着某个平台分支被登记两次，后一半永远不可达
    assert len(handlers) == len(set(handlers)), "分发表存在重复处理函数"
    # 两个可调用对象缺一即会在分派循环里抛 TypeError
    assert all(callable(matcher) and callable(handler) for matcher, handler in table)


def test_resolver_table_priority_head(main_mod: Any) -> None:
    # 前六项 = 迁移前 elif 链的前五平台（抖音 / TikTok / 快手 / 虎牙 / 斗鱼）+ 虎牙移动端短链
    # hy.fan（2026-10-03 插入虎牙之后、斗鱼之前，白名单同批登记）。顺序即优先级：抖音短链
    # v.douyin.com 等形态必须最先判定，不能被更宽松的片段抢走；插入新表项会挪动其后所有下标，
    # 所以这里显式列出顺序，改顺序必须同步改本锁并说明理由。
    names = [handler.__name__ for _, handler in main_mod._PLATFORM_RESOLVERS[:6]]
    assert names == [
        "_resolve_douyin_com",
        "_resolve_tiktok_com",
        "_resolve_live_kuaishou_com",
        "_resolve_huya_com",
        "_resolve_hy_fan",
        "_resolve_douyu_com",
    ]
    # 自定义流地址必须垫底：它只按扩展名匹配，放前面会截获平台地址
    assert main_mod._PLATFORM_RESOLVERS[-1][1].__name__ == "_resolve_custom_stream"


# （URL, 预期平台名, 预期命中的解析入口）：入口名用于确认「走的是哪条分支」，
# 只断言平台名会漏掉「匹配到了但处理函数被换错」这类错误。
_DISPATCH_CASES = [
    ("https://live.douyin.com/123", "抖音直播", "get_douyin_web_stream_data"),
    ("https://v.douyin.com/abc/", "抖音直播", "get_douyin_app_stream_data"),
    ("https://www.tiktok.com/@u/live", "TikTok直播", "get_tiktok_stream_data"),
    ("https://live.kuaishou.com/u/x", "快手直播", "get_kuaishou_stream_data"),
    ("https://www.huya.com/660002", "虎牙直播", "get_huya_stream_data"),
    ("https://www.douyu.com/9999", "斗鱼直播", "get_douyu_info_data"),
    # 斗鱼移动端域名：与 www 共用 _resolve_douyu_com，必须落到同一个解析入口
    ("https://m.douyu.com/9999", "斗鱼直播", "get_douyu_info_data"),
    ("http://m.douyu.com/9999/", "斗鱼直播", "get_douyu_info_data"),
    ("https://live.bilibili.com/1", "B站直播", "get_bilibili_room_info"),
    # B站移动端分享短链纯数字形态：归一后复用 _resolve_live_bilibili_com（短码形态
    # 依赖跳转解析，整体替换为桩后的专项覆盖见 test_b23_tv_dispatch.py）
    ("https://b23.tv/22747736", "B站直播", "get_bilibili_room_info"),
    ("https://www.picarto.tv/x", "Picarto", "get_picarto_stream_url"),
]


@pytest.mark.parametrize("url,expected_platform,expected_entry", _DISPATCH_CASES)
def test_resolve_platform_stream_dispatches(
    dispatch_env: tuple, url: str, expected_platform: str, expected_entry: str
) -> None:
    main_mod, calls = dispatch_env
    # 代理非空才会走 TikTok / LiveMe 等「需要代理」的分支，此处统一带代理避免空转
    result = main_mod._resolve_platform_stream(url, "http://127.0.0.1:1", "原画")
    assert result is not None, f"{url} 应被识别，实际返回 None"
    platform, _port_info, _danmaku, _new_url = result
    assert platform == expected_platform
    assert expected_entry in [name for _tag, name in calls]


def test_resolve_platform_stream_unknown_returns_none(dispatch_env: tuple) -> None:
    main_mod, _calls = dispatch_env
    assert main_mod._resolve_platform_stream("https://example.com/nothing", None, "原画") is None


# 自定义流地址分支：扩展名大小写两种形态都要落到「自定义录制直播」，
# 且按扩展名写入对应的流地址键（flv_url / m3u8_url）。
_CUSTOM_STREAM_CASES = [
    ("https://cdn.example.com/live/1.m3u8", "m3u8_url"),
    # 大写扩展名同样要识别：历史上 find(".m3u8") 大小写敏感导致自定义地址被判「未知链接」
    ("https://cdn.example.com/live/1.M3U8", "m3u8_url"),
    ("http://cdn.example.com/live/1.flv", "flv_url"),
    ("http://cdn.example.com/live/1.FLV", "flv_url"),
]


@pytest.mark.parametrize("url,expected_key", _CUSTOM_STREAM_CASES)
def test_custom_stream_suffix_is_case_insensitive(dispatch_env: tuple, url: str, expected_key: str) -> None:
    main_mod, _calls = dispatch_env
    result = main_mod._resolve_platform_stream(url, None, "原画")
    assert result is not None
    platform, port_info, _danmaku, _new_url = result
    assert platform == "自定义录制直播"
    assert expected_key in port_info


def test_new_platform_entry_can_be_registered(main_mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # 「新平台接入成本」是该核心诉求：追加一个处理函数 + 一条表项即可，不必进 600 行链里
    # 插分支。此处用一个临时表项验证该扩展点确实可用。
    seen: list[str] = []

    def _fake_handler(ctx: Any) -> None:
        seen.append(ctx.record_url)
        ctx.platform = "测试平台"

    monkeypatch.setattr(
        main_mod,
        "_PLATFORM_RESOLVERS",
        ((main_mod._match_host("https://probe.example/"), _fake_handler),),
    )
    result = main_mod._resolve_platform_stream("https://probe.example/room", None, "原画")
    assert result is not None
    assert result[0] == "测试平台"
    assert seen == ["https://probe.example/room"]


# --------------------------------------------------------------------------------------
# 白名单 host 与分发表必须一一对应
#
# 准入按 `url_host in PLATFORM_HOST` **精确 host**，分派按**子串**匹配。白名单里有、没有任何表项
# 命中的 host 会让房间线程每轮走 _resolve_unrecognized：一条 error → sleep → 无限空转，永不录制、
# 也**不记 record_error**（熔断/背压统计完全看不到），白占监控位并持续污染日志。
def test_every_platform_host_has_a_resolver(main_mod: Any) -> None:
    matchers = [matcher for matcher, _handler in main_mod._PLATFORM_RESOLVERS]

    def _covered(host: str) -> bool:
        # 用两种协议各试一次：白名单只写裸 host，用户粘贴的地址两种形态都合法
        return any(matcher(f"{scheme}://{host}/123456") for scheme in ("https", "http") for matcher in matchers)

    uncovered = [host for host in main_mod.PLATFORM_HOST if not _covered(host)]
    assert not uncovered, f"PLATFORM_HOST 中以下 host 没有任何 resolver 命中: {uncovered}"


def test_platform_host_entries_that_were_fixed_on_2026_09_20(main_mod: Any) -> None:
    # www.redelight.cn：全仓（spider / stream / JS 签名脚本 / 平台清单）零引用，
    # 留在白名单里只会让用户配一个永不录制的地址 → 已按该摘除。
    assert "www.redelight.cn" not in main_mod.PLATFORM_HOST
    # huodong.m.taobao.com：淘宝直播分享页 host（get_taobao_stream_url 的 Referer 即该域名），
    # 此前白名单有、表项没有 → 现已接入 _resolve_tb_cn。
    assert main_mod._match_host("tb.cn", "tbzb.taobao.com", "huodong.m.taobao.com")("https://huodong.m.taobao.com/x")


def test_douyu_mobile_host_is_admitted_and_dispatched(main_mod: Any) -> None:
    # 斗鱼移动端 host 必须在准入白名单（精确匹配）且分派表命中：缺前者时
    # https://m.douyu.com/8751648 在读取 URL 配置阶段就被判「未知链接」注释掉；缺后者则会落入
    # _resolve_unrecognized 无限空转（该同型：永不录制、不记 record_error）。
    assert "m.douyu.com" in main_mod.PLATFORM_HOST
    matcher = main_mod._match_host("www.douyu.com/", "m.douyu.com/")
    assert matcher("https://m.douyu.com/8751648")
    assert matcher("http://m.douyu.com/8751648/")
    assert matcher("https://www.douyu.com/8751648")
    # 反例：路径里出现域名词不得被路由进斗鱼（该同口径）
    assert not matcher("https://example.com/m.douyu.com/8751648")


# --------------------------------------------------------------------------------------
# 录制链里的「平台名字面量」必须等于 resolver 回写值
#
# 这些列表参与运行期判定（是否强制 http、是否强制直下 FLV、是否纯音频、源地址日志走哪个字段），
# 比对对象是 _resolve_* 回写的 `platform`。写成 host 片段（曾经的 "migu"）就是死项：不报错、
# 只是永不生效。此处用 AST 交叉校验两侧，防止再次漂移。
# 需要与 resolver 回写平台名比对的主循环内列表/元组（变量名 → main.py）
_PLATFORM_NAME_LITERALS = (
    "http_record_list",
    "only_flv_platform_list",
    "only_audio_platform_list",
    "re_plat",
)


def _resolver_platform_names(tree: "ast.Module") -> set[str]:
    # 收集所有 _resolve_* 处理函数里对 `platform` 的字面量赋值（含 if/else 分支内的）
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("_resolve_"):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Assign) and isinstance(inner.value, ast.Constant):
                if isinstance(inner.value.value, str) and any(
                    isinstance(t, ast.Name) and t.id == "platform" for t in inner.targets
                ):
                    names.add(inner.value.value)
    return names


def _literal_sequences_by_name(tree: "ast.Module") -> dict[str, list[str]]:
    # 收集 `name = ["a", "b"]` / `name = ("a", "b")` 形式的字符串序列赋值
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        targets: list[str] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value = node.value
        if value is None or not targets:
            continue
        if not isinstance(value, (ast.List, ast.Tuple)):
            continue
        items = [v.value for v in value.elts if isinstance(v, ast.Constant) and isinstance(v.value, str)]
        if len(items) == len(value.elts):
            for target in targets:
                found[target] = items
    return found


def _platform_cookie_map_entries(tree: "ast.Module") -> dict[str, str]:
    # 取 `platform_cookie = {...}.get(platform, "")` 里的字面量映射：{平台名字面量: 值表达式名}。
    # 值一律取「表达式里的名字」（如 shopee_cookie），字面量兜底（"" 等）原样回字符串——
    # 调用方据此区分「键加上了但没接到配置变量」这一形态。
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not any(
            isinstance(t, ast.Name) and t.id == "platform_cookie" for t in node.targets
        ):
            continue
        dict_node: ast.Dict | None = None
        value = node.value
        # 形态一：`{...}.get(platform, "")`；形态二：直接 `{...}` 赋值。只认这两种字面量映射。
        if isinstance(value, ast.Dict):
            dict_node = value
        elif (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "get"
            and isinstance(value.func.value, ast.Dict)
        ):
            dict_node = value.func.value
        if dict_node is None:
            continue
        entries: dict[str, str] = {}
        for key, val in zip(dict_node.keys, dict_node.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if isinstance(val, ast.Name):
                    entries[key.value] = val.id
                elif isinstance(val, ast.Constant):
                    entries[key.value] = repr(val.value)
        if entries:
            return entries
    return {}


def test_platform_name_literals_match_resolver_writeback(main_mod: Any) -> None:
    tree = ast.parse((_REPO_ROOT / "main.py").read_text(encoding="utf-8"))
    resolver_names = _resolver_platform_names(tree)
    assert resolver_names, "AST 未能取到任何 resolver 回写的平台名（扫描口径失效即假绿）"
    sequences = _literal_sequences_by_name(tree)

    unknown: list[str] = []
    for var in _PLATFORM_NAME_LITERALS:
        items = sequences.get(var)
        assert items, f"main.py 中找不到列表 {var}（被改名或删除，本回归锁随之失效）"
        for item in items:
            if item not in resolver_names:
                unknown.append(f"{var}: {item}")
    assert not unknown, f"以下平台名字面量在任何 resolver 的回写值里都不存在（死项）: {unknown}"


def test_migu_is_not_a_dead_http_record_entry(main_mod: Any) -> None:
    # 回归具体缺陷：http_record_list 曾写 "migu"，而咪咕 resolver 回写 "咪咕直播" → 死项
    tree = ast.parse((_REPO_ROOT / "main.py").read_text(encoding="utf-8"))
    sequences = _literal_sequences_by_name(tree)
    assert "migu" not in sequences["http_record_list"]
    assert "咪咕直播" in sequences["http_record_list"]


# --------------------------------------------------------------------------------------
# 自定义流判定必须按**路径扩展名**，不能整串子串包含
#
# 旧实现 `".flv" in url.lower()` 让任意地址只要在 query 里塞 `?a=.flv` 就命中自定义流分支，
# 于是面板写入的 http://127.0.0.1:8000/x?a=.flv 会被原样送进 ffmpeg 的 -i（ SSRF 旁路）。
# 反向要求：path 以 .m3u8/.flv 结尾、带任意 query/fragment 的合法形态必须照常命中（大小写不敏感）。
_LEGITIMATE_STREAM_URLS = [
    "https://cdn.example.com/live/1.m3u8",
    "https://cdn.example.com/live/1.M3U8",
    # 带签名 query 的真实形态（斗鱼/虎牙 HLS、FLV）
    "https://cdn.example.com/live/1.m3u8?wsSecret=abc&wsTime=1",
    "http://cdn.example.com/live/1.flv?txSecret=abc&txTime=1",
    "http://cdn.example.com/live/1.FLV",
]

_SUFFIX_BYPASS_URLS = [
    # query / fragment 里的扩展名不算数
    "http://127.0.0.1:8000/x?a=.flv",
    "http://169.254.169.254/latest/meta-data/?x=.m3u8",
    "https://example.com/room/123#frag.flv",
    "https://example.com/room/123?path=/a/b.m3u8",
    # 无扩展名 / 其它扩展名
    "https://example.com/nothing",
    "https://example.com/index.html",
]


@pytest.mark.parametrize("url", _LEGITIMATE_STREAM_URLS)
def test_custom_stream_still_matches_real_stream_paths(dispatch_env: tuple, url: str) -> None:
    main_mod, _calls = dispatch_env
    result = main_mod._resolve_platform_stream(url, None, "原画")
    assert result is not None
    platform, port_info, _danmaku, _new_url = result
    assert platform == "自定义录制直播"


@pytest.mark.parametrize("url", _SUFFIX_BYPASS_URLS)
def test_query_or_fragment_suffix_cannot_reach_custom_stream_branch(dispatch_env: tuple, url: str) -> None:
    main_mod, _calls = dispatch_env
    assert main_mod._resolve_platform_stream(url, None, "原画") is None, f"{url} 不应命中自定义流分支"
    assert main_mod._match_stream_suffix(".m3u8", ".flv")(url) is False


def test_stream_path_suffix_ignores_query_and_fragment(main_mod: Any) -> None:
    assert main_mod._stream_path_suffix("https://h/a.m3u8?x=1") == ".m3u8"
    assert main_mod._stream_path_suffix("https://h/a.FLV#z") == ".flv"
    assert main_mod._stream_path_suffix("https://h/a?x=.flv") == ""
    assert main_mod._stream_path_suffix("https://h") == ""
    # 畸形入参（urlsplit 抛 ValueError）按「无扩展名」处理，不得抛出
    assert main_mod._stream_path_suffix("http://[::1:notaport]/a.flv") in ("", ".flv")


def test_custom_stream_keys_follow_path_extension(dispatch_env: tuple) -> None:
    # flv_url / m3u8_url 的归属必须与匹配器同一判据（路径扩展名）：
    # 旧实现按整串子串选键，于是 `.m3u8?....flv` 的 HLS 清单被写进 flv_url（当成 FLV 直下）
    main_mod, _calls = dispatch_env
    result = main_mod._resolve_platform_stream("https://cdn.example.com/a.m3u8?f=.flv", None, "原画")
    assert result is not None
    platform, port_info, _danmaku, _new_url = result
    assert platform == "自定义录制直播"
    assert "m3u8_url" in port_info and "flv_url" not in port_info

    result2 = main_mod._resolve_platform_stream("https://cdn.example.com/a.flv?f=.m3u8", None, "原画")
    assert result2 is not None
    port_info2 = result2[1]
    assert "flv_url" in port_info2 and "m3u8_url" not in port_info2


def test_forced_direct_download_platforms_carry_cookie(main_mod: Any) -> None:
    # 不变量锁：两个「强制直下」平台必须在 platform_cookie 映射
    # 里有条目且绑定到配置项变量（*_cookie），而不是空串字面量。成因：[Cookie] shopee_cookie /
    # huajiao_cookie 已有读取点并透传给解析函数，却不在映射里，于是同一份 Cookie 在「解析」与
    # 「探针 / ffmpeg 录制头 / 直下」两条路口径不一——直下路径按游客态取流，CDN 可 403 或钳到最低档。
    # 判据：删掉任一键、或把值写成 "" 字面量即变红；映射整体丢失时开头的非空见证变红。
    tree = ast.parse((_REPO_ROOT / "main.py").read_text(encoding="utf-8"))
    entries = _platform_cookie_map_entries(tree)
    assert entries, "AST 未能取到 platform_cookie 字面量映射（扫描口径失效即假绿）"
    only_flv = _literal_sequences_by_name(tree).get("only_flv_platform_list")
    assert only_flv, "main.py 中找不到 only_flv_platform_list（被改名或删除，本回归锁随之失效）"
    for platform in only_flv:
        assert platform in entries, f"强制直下平台 {platform} 未向探针/录制头/直下转发 Cookie（L-04 回归）"
        assert entries[platform].endswith("_cookie"), f"{platform} 未绑定配置项变量: {entries[platform]}"
