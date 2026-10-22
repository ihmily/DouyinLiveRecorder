# 常驻门禁：出站链路上的异常文本进日志前必须过 mask_credentials（CODE_REVIEW_2026-10-18 §7.11 第②条）。
#
# 立规理由：异常文本里常内嵌**带签名/凭据的完整 URL**（httpx 的 ConnectError/HTTPError 会把请求 URL
# 打进 str(e)），而 logs/ 按大小轮转保留多份 ⇒ 凭据等于长期落盘。AGENTS.md 的凭据红线写的是「写入
# 日志前必须脱敏」，但只靠人眼 grep 时同族缺陷在一轮里就报了 3 处（M-05 / L-08 / L-21）。
#
# 为什么不做成「全仓一律必须脱敏」：实测同口径扫描在**出站函数**里就命中 23 个函数 / 34 个实参，
# 全仓 except 分支的异常文本实参更多（数百）。零容忍会把门禁写成一张永久红榜，红榜没人看，
# 保护力反而归零（与其让断言恒真，不如让它判一个可收缩的量）。
# 因此本门禁取**只降不升的棘轮**（同 tests/test_spider_hardening.py::BARE_JSON_LOADS_CEILING 口径）：
#   ① 现存违例按 (文件, 函数) 登记进 `_SANCTIONED_UNMASKED`，逐条给归类；
#   ② 出现表外新违例 ⇒ 立即红（新代码必须脱敏，这是立规的目的）；
#   ③ 表内条目被整改后若不同步删行 ⇒ 也红（防止表与代码脱钩、变成装饰性清单）；
#   ④ 反向见证：扫描面必须同时看到「已脱敏」与「未脱敏」两类实参，否则判据可能整体失明。
#
# 扫描口径说明（为什么只看「函数体里有出站动作」的函数）：脱敏的必要性来自「异常里可能带 URL/凭据」，
# 而这正是出站调用的属性；把纯本地解析（json 解码、正则、文件读）也拉进来，只会造出大批无需整改的
# 噪声条目，淹没真正带凭据的站点。markers 集合刻意保守（async_req / sync_req / httpx 客户端构造 /
# urlopen / build_opener / requests. / websockets / .connect(），宁可漏报也不误报——漏报的代价由
# AGENTS.md「凭据与敏感配置脱敏」条 + code review 承担。
import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "node",
    "ffmpeg",
    "build",
    "dist",
    "__pycache__",
    ".workbuddy",
    ".qoder",
    ".qoder-credits",
    "node_modules",
    "typings",
    "downloads",
    "logs",
    "backup_config",
    ".agents",
    ".superpowers",
    # tests/ 与 scripts/ 不参与：用例里的替身异常文本是本文件自己的构造值，
    # 维护脚本只在开发机跑、不落运行期日志，纳进来会把判据稀释成「也管测试代码」。
    "tests",
    "scripts",
}
# 出站动作标记（出现在函数体源码里即认为该函数会发起带 URL 的请求）。
_OUTBOUND_MARK = re.compile(
    r"(async_req\(|sync_req\(|httpx\.AsyncClient\(|httpx\.Client\(|urlopen\(|build_opener\(|requests\.|websockets|\.connect\()"
)
# 承载「异常文本」的关键字实参名（本仓日志模板的既有 kwarg 命名集合）。
_EXC_TEXT_KWARGS = frozenset({"e", "err", "error", "exc", "message", "msg", "reason", "detail", "errmsg"})
# 值里出现这些名字才算「把异常对象塞进了日志」。
_EXC_NAME_RE = re.compile(r"\b(e|err|exc|error)\b")
# 棘轮登记表：键 = (仓库相对路径, 函数名)，值 = (未脱敏实参条数, 归类)。
# 归类只说明「为什么它排在后面」，**不是**「为什么可以永远不脱敏」——全部待整改。
# 凭据型 = URL/异常文本可能带 Cookie/token/签名参数；下载源型 = 取数指向公共 CDN，泄漏面是路径而非凭据。
_SANCTIONED_UNMASKED: dict[tuple[str, str], tuple[int, str]] = {
    ("main.py", "direct_download_stream"): (1, "下载源型"),
    ("src/ffmpeg_install.py", "_fetch_official_sha256"): (1, "下载源型"),
    ("src/ffmpeg_install.py", "download_ffmpeg_official"): (2, "下载源型"),
    ("src/ffmpeg_linux_download.py", "_download"): (2, "下载源型"),
    ("src/ffmpeg_linux_download.py", "_fetch_asset_digest"): (1, "下载源型"),
    ("src/ffmpeg_master_download.py", "_probe"): (1, "下载源型"),
    ("src/ffmpeg_master_download.py", "_stream_download"): (1, "下载源型"),
    ("src/node_install.py", "_fetch_official_sha256"): (1, "下载源型"),
    ("src/node_install.py", "install_nodejs_windows"): (2, "下载源型"),
    ("src/platforms/douyin.py", "start"): (1, "凭据型：弹幕握手链路，异常文本可含带签名参数的 ws/流地址"),
    ("src/spider.py", "_fetch_buvid"): (3, "凭据型：B 站 buvid 获取链"),
    ("src/spider.py", "get_bilibili_danmaku_info"): (6, "凭据型：B 站直播信息，Cookie 参与请求"),
    ("src/spider.py", "get_bilibili_room_info"): (1, "凭据型：同上"),
    ("src/spider.py", "get_douyin_app_stream_data"): (1, "凭据型：签名参数在 URL 上"),
    ("src/spider.py", "get_douyin_web_stream_data"): (1, "凭据型：同上"),
    ("src/spider.py", "get_huajiao_sn"): (2, "凭据型：接口返回体参与拼接"),
    ("src/spider.py", "get_kuaishou_stream_data"): (1, "凭据型：did/凭据参与查询串"),
    ("src/spider.py", "get_kuaishou_stream_data2"): (1, "凭据型：同上"),
    ("src/spider.py", "get_token_js"): (1, "凭据型：斗鱼 token 签名链"),
    ("src/ws_client.py", "connect"): (1, "凭据型：WS 握手 URL 带鉴权参数"),
}


def _iter_scan_files() -> list[Path]:
    files: list[Path] = []
    for path in _REPO_ROOT.rglob("*.py"):
        if path.name == "build_exe.py":
            # 发布链脚本：取数指向官方 CDN，且只在 CI 构建机跑、不写运行期日志。
            continue
        if set(path.parts) & _EXCLUDED_PARTS:
            continue
        files.append(path)
    return files


def _collect_sites(files: list[Path]) -> tuple[dict[tuple[str, str], int], int]:
    # 返回 (未脱敏实参按 {(文件, 函数): 条数}, 已脱敏实参条数)；后者只供反向见证用。
    unmasked: dict[tuple[str, str], int] = {}
    masked_count = 0
    for path in files:
        rel = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise AssertionError(f"{rel} 解析失败，判据无法自证覆盖: {type(exc).__name__}: {exc}") from exc
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            seg = ast.get_source_segment(text, func) or ""
            if not _OUTBOUND_MARK.search(seg):
                continue
            for handler in ast.walk(func):
                if not isinstance(handler, ast.ExceptHandler):
                    continue
                for call in ast.walk(handler):
                    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
                        continue
                    base = call.func.value
                    if getattr(base, "id", getattr(base, "attr", "")) not in ("logger", "log"):
                        continue
                    # 本仓日志一律写成 logger.warning(i18n.tr(模板, **kw))——kwarg 挂在**内层** tr 调用上，
                    # 只查 logger 自己的 keywords 会一条也看不见（M-05 排查期实测踩到的第一版假绿）。
                    for sub in ast.walk(call):
                        if not isinstance(sub, ast.Call):
                            continue
                        for kw in sub.keywords:
                            if kw.arg not in _EXC_TEXT_KWARGS:
                                continue
                            value = ast.unparse(kw.value)
                            if not _EXC_NAME_RE.search(value):
                                continue
                            if "mask_credentials" in value:
                                masked_count += 1
                                continue
                            unmasked[(rel, func.name)] = unmasked.get((rel, func.name), 0) + 1
    return unmasked, masked_count


def test_exception_text_sites_match_the_ratchet_ledger() -> None:
    # 判据②③：表外新违例即红；表内条目消失（已整改）却不同步缩表也即红。
    unmasked, _masked = _collect_sites(_iter_scan_files())
    new_sites = sorted(set(unmasked) - set(_SANCTIONED_UNMASKED))
    stale = sorted(set(_SANCTIONED_UNMASKED) - set(unmasked))
    assert not new_sites, (
        f"出站链路上出现未过 mask_credentials 的异常文本实参（凭据会随轮转日志长期落盘，"
        f"AGENTS.md 凭据红线）: {new_sites}"
    )
    assert not stale, f"以下站点已整改但棘轮表未同步收窄: {stale}"


def test_ratchet_count_only_shrinks() -> None:
    unmasked, _masked = _collect_sites(_iter_scan_files())
    total = sum(unmasked.values())
    baseline = sum(count for count, _kind in _SANCTIONED_UNMASKED.values())
    assert total <= baseline, f"未脱敏实参总数由 {baseline} 涨到 {total}——棘轮只允许下降"


def test_scanner_sees_both_masked_and_unmasked_sites() -> None:
    # 判据④：反向见证。若扫描只产出违例、一条「已脱敏」都看不见，说明脱敏判定失明
    # （常见成因：kwarg 挂载层找错、或关键字集合与模板命名不一致），此时前两条锁会给假绿。
    unmasked, masked = _collect_sites(_iter_scan_files())
    assert unmasked, "扫描面一个违例都没找到：要么全仓已整改（请同步删除本文件与棘轮表），要么判据已失效"
    assert masked >= 1, "扫描面一个「已脱敏」实参都没找到，脱敏判定很可能失效（见上条注释）"


def test_detector_flags_unmasked_and_passes_masked_samples() -> None:
    # 自检（防空转）：同一段代码的两种写法必须被判成两类结果。
    bad = (
        "from src import logger, utils\n"
        "import src.async_http as ah\n"
        "async def fetch(url):\n"
        "    try:\n"
        "        return await ah.async_req(url)\n"
        "    except Exception as e:\n"
        "        logger.warning('请求失败: {e}', e=e)\n"
    )
    good = bad.replace("e=e)", "e=utils.mask_credentials(str(e)))")
    for text, expect_flag in ((bad, True), (good, False)):
        tree = ast.parse(text)
        func = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        hits = 0
        for handler in ast.walk(func):
            if not isinstance(handler, ast.ExceptHandler):
                continue
            for call in ast.walk(handler):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
                    continue
                for sub in ast.walk(call):
                    if not isinstance(sub, ast.Call):
                        continue
                    for kw in sub.keywords:
                        if kw.arg not in _EXC_TEXT_KWARGS:
                            continue
                        value = ast.unparse(kw.value)
                        if _EXC_NAME_RE.search(value) and "mask_credentials" not in value:
                            hits += 1
        assert (hits > 0) is expect_flag, f"自检失效：{expect_flag=} 却得到 hits={hits}"
