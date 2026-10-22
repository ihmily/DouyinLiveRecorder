# 常驻门禁：出站响应体读取必须落在「已登记且带上限」的函数里（CODE_REVIEW_2026-10-18 §7.11 第①条）。
#
# 立规背景：该轮审查一次性报出三条同形态缺陷——M-03（sync_http 的 400 分支全量 `e.read()`）、
# M-04（async_http 主请求路径非流式全量读 + httpx 自动解压无上限，压缩炸弹可直接打爆内存）、
# L-11（探针非流式读响应体，不遵守 Range 的节点可回任意大 body）。单点修完并不阻止第四个读取点
# 被写出来：出站代码分散在 async_http / sync_http / stream_select / main 直下载 / 推送通道五处。
#
# 为什么只做 AST、不跑网络：判据是「谁在读响应体、读的时候有没有上限」，这是纯源码结构事实；
# 运行时用例只能证明**某一条路径**被限制住，无法证明没有第二条未限制路径。本文件不 import 被测
# 模块，只读源码文本 + ast.parse，自身零副作用、秒级完成。
#
# 三条判据（互不重叠，各挡一种回归）：
#   ① httpx 流式/异步读取点集合（`aread` / `aiter_bytes` / `aiter_raw` / `iter_bytes` / `iter_raw` /
#      `iter_lines`）必须与登记表**双向相等**——新读点即红，删读点不缩表也即红。收这套方法名是因为
#      它们是 httpx Response 独有，**零误报**；而 `.read()` / `.text` / `.json()` 在文件对象上同名，
#      纳进来会把「读配置文件」也算成出站读取（实测全仓 `.read` 位点 53 处，绝大多数是文件读）。
#   ② 两个受管上限函数（async_http._bounded_response_read、stream_select._bounded_probe_get）
#      体内必须**真的引用**上限常量或限量实参——防「函数名还在、上限被摘掉」这种只改体的回归。
#   ③ 同步侧 sync_http 里所有 `.read(...)` 必须落在 `_read_capped` / `_gunzip_capped` 之内，且 HTTP
#      400 分支必须经 `_read_capped`（M-03 本体）——同步侧读的是 http.client/HTTPError，方法名与
#      文件读同形，只能按「模块内封闭」判定。
#
# 已知取舍：①③ 不追数据流（不证明 response 真的来自网络），构造样本仍可绕过，但真实新增一个未限量
# 读取点跑不掉。上限取值本身的跨模块同值由
# tests/test_async_http.py::test_caps_match_the_sync_side_baseline 钉，本文件不再维护第二份数值断言。
import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
# 与 scripts/check_annotations.py / pyproject 的排除面同源：运行时二进制目录与工具产物不参与扫描。
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
}
# httpx Response 独有的流式/异步读取方法名（文件对象没有这些属性 ⇒ 零误报的一档）。
_HTTPX_READ_METHODS = frozenset(
    {"aread", "aiter_bytes", "aiter_raw", "aiter_lines", "iter_bytes", "iter_raw", "iter_lines"}
)
# 登记表：键 = (仓库相对路径, 函数名)，值 = (上限形态, 为什么这样可接受)。
# 形态与 tests/test_ffmpeg_install.py::DOWNLOAD_SOURCES 同构：**缺一即锁红、多一即锁红**，
# 新增出站读取点必须先在此说明「量从哪儿来、为什么不会把内存打满」。
_HTTPX_READERS: dict[tuple[str, str], tuple[str, str]] = {
    (
        "src/async_http.py",
        "_bounded_response_read",
    ): (
        "分块累加 + 压缩/未压缩双上限，超限即抛",
        "异步主请求路径（全平台解析实际在用）的唯一受管读点：aiter_bytes 走 httpx 自带解码管线，"
        "读完回填 response._content 让后续 aread() 短路，故调用面与返回契约不变（M-04 定稿形态）。",
    ),
    (
        "src/stream_select.py",
        "_bounded_probe_get",
    ): (
        "只读首块即限量（read_body=False 时根本不读体）",
        "探针语义是「可达性判定」，不需要完整 body；限量读不改判定结论（L-11 定稿形态）。",
    ),
    (
        "main.py",
        "direct_download_stream",
    ): (
        "边下边写盘，内存里只过一块",
        "直下载的目标就是把整个流落成文件，把上限加在这里等于把功能砍掉；风险面是磁盘占用而非内存放大，"
        "由分段与磁盘清理策略承担。刻意登记为「无上限但合法」，不得据此推及任何新读点。",
    ),
}
# 判据②的配对：这两个函数必须真的引用上限常量/限量实参（摘掉上限即红）。
_CAP_BOUND_FUNCS = {
    ("src/async_http.py", "_bounded_response_read"): ("_MAX_RESPONSE_BYTES", "_MAX_DECOMPRESSED_BYTES"),
    ("src/stream_select.py", "_bounded_probe_get"): ("_PROBE_READ_BYTES", "read_body", "max_bytes"),
}


def _scan_roots() -> list[Path]:
    files: list[Path] = []
    for path in _REPO_ROOT.rglob("*.py"):
        if set(path.parts) & _EXCLUDED_PARTS:
            continue
        files.append(path)
    return files


def _rel(path: Path) -> str:
    return str(path.relative_to(_REPO_ROOT)).replace("\\", "/")


def _func_bodies(tree: ast.AST) -> list[tuple[str, ast.AST]]:
    out: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((node.name, node))
    return out


@pytest.mark.parametrize(
    "files",
    [_scan_roots()],
    ids=["repo-py"],
)
def test_httpx_read_sites_match_the_registered_ledger(files: list[Path]) -> None:
    # 判据①：双向差集都必须为空。
    found: set[tuple[str, str]] = set()
    for path in files:
        rel = _rel(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise AssertionError(f"{rel} 解析失败，判据无法自证覆盖: {type(exc).__name__}: {exc}") from exc
        for name, body in _func_bodies(tree):
            for node in ast.walk(body):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _HTTPX_READ_METHODS
                ):
                    found.add((rel, name))
    missing = sorted(found - set(_HTTPX_READERS))
    stale = sorted(set(_HTTPX_READERS) - found)
    assert not missing, f"出现未登记的出站响应体读取点（必须先说明上限形态与可接受理由）: {missing}"
    assert not stale, f"登记表里的读取点已不存在，必须同步缩表（否则表会退化成一堵谁都能跨的墙）: {stale}"


def test_ledger_is_not_a_vacuous_empty_table() -> None:
    # 反向见证：扫描面必须真的看到 async_http 与 stream_select 两个受管读点，
    # 否则「集合相等」在两边都空时也成立——那正是本门禁最坏的失效形态。
    rels = {key[0] for key in _HTTPX_READERS}
    assert {"src/async_http.py", "src/stream_select.py"} <= rels, f"登记表把受管读点弄丢了: {rels}"
    assert len(_HTTPX_READERS) >= 3, f"登记表条目异常收缩: {len(_HTTPX_READERS)}"


def test_cap_functions_still_reference_their_limits() -> None:
    # 判据②：函数名还在但上限被摘掉，是最典型的「只改体」回归（MID-2264 同族：外壳保留、内里失效）。
    for (rel, func), markers in _CAP_BOUND_FUNCS.items():
        tree = ast.parse((_REPO_ROOT / rel).read_text(encoding="utf-8"))
        body = next((b for n, b in _func_bodies(tree) if n == func), None)
        assert body is not None, f"{rel} 里找不到 {func}()，判据②失去附着点"
        names = {node.id for node in ast.walk(body) if isinstance(node, ast.Name)}
        attrs = {node.attr for node in ast.walk(body) if isinstance(node, ast.Attribute)}
        kwargs = {kw.arg for call in ast.walk(body) if isinstance(call, ast.Call) for kw in call.keywords}
        seen = names | attrs | kwargs
        hit = [m for m in markers if m in seen or m in ast.unparse(body)]
        assert hit, f"{rel}::{func}() 不再引用任何上限常量/限量实参 {markers}——限量读取已被摘除"


def test_sync_http_reads_stay_inside_the_capped_helpers() -> None:
    # 判据③：同步侧 `.read` 与文件读同形，故按「模块内封闭」收口——只允许出现在两个受管函数里。
    rel = "src/sync_http.py"
    tree = ast.parse((_REPO_ROOT / rel).read_text(encoding="utf-8"))
    offenders: list[tuple[str, int, str]] = []
    allowed = {"_read_capped", "_gunzip_capped"}
    for name, body in _func_bodies(tree):
        if name in allowed:
            continue
        for node in ast.walk(body):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "read" or node.args:
                continue
            receiver = getattr(node.func.value, "id", "") or getattr(node.func.value, "attr", "")
            # 只认响应/错误对象形态的接收者（resp/response/e/err/r），避免把其它同名方法也算进来。
            if receiver in {"resp", "response", "rs", "e", "err", "r", "http_response"}:
                offenders.append((name, node.lineno, receiver))
    assert not offenders, f"{rel} 出现未经 _read_capped 的响应体全量读取（M-03 同形态回归）: {offenders}"
    # 400 分支必须经 _read_capped：这是 M-03 的修复本体，单独点名，避免被上一条「不出现 read」间接盖住。
    src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "_read_capped(e" in src.replace(" ", ""), f"{rel} 的 400 错误体不再走 _read_capped: M-03 回归"


def test_detector_flags_a_new_unregistered_read_site() -> None:
    # 自检（防空转）：合成一段「新增未登记读点」的源码，判据①的枚举逻辑必须抓到它。
    sample = (
        "import httpx\n"
        "async def fetch(client):\n"
        "    resp = await client.send(client.build_request('GET', 'https://example.com'))\n"
        "    return await resp.aread()\n"
    )
    tree = ast.parse(sample)
    found = {
        (name, node.func.attr)
        for name, body in _func_bodies(tree)
        for node in ast.walk(body)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _HTTPX_READ_METHODS
    }
    assert ("fetch", "aread") in found, f"自检失效：新增读点未被枚举到 {found}"
