# tests/test_node_install.py - src/node_install.py 的行为锁。
#
# 该模块此前只有 15% 覆盖：全部安装分支（Windows 下载→校验→解压→改名→PATH 注入→
# node -v 复核、Linux yum/apt、macOS brew）都只在「真缺 node 的机器首次启动」时才跑，
# 属于典型的「平时代码不发版、一发版就没人验证」的路径。补测的意义不是覆盖率本身，
# 而是把两条已被踩过一次的坑固化下来：
#   1) CR-11：残缺 zip 缓存必须删除重下，否则错误哈希会被固化成基线 → 永久失败且不自愈；
#   2) H-1：SHA256 基准不一致必须硬拒绝，且拒绝时要清掉坏包（否则下次仍读到它）。
#
# Mock 口径（与 tests/test_ffmpeg_install.py 一致）：
#   - 只替换模块全局引用（requests / subprocess / distro / tqdm / execute_dir），
#     绝不改 stdlib 本体（subprocess 用 types.SimpleNamespace 浅拷贝做 shim）；
#   - zip 用真 zipfile 生成，让 is_valid_zip / unzip_file 走真实实现，
#     顺带锁住「node_install 与 utils.unzip_file 的落点约定」（解压目录名 = zip 去扩展名）。

import hashlib
import io
import os
import subprocess
import types
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

import src.node_install as node_install

ZIP_A = b"fake-node-build-A"
PAGE_HTML_OK = "<html>download https://npmmirror.com/mirrors/node/v22.11.0/" "node-v22.11.0-x64.msi</html>"
NODE_ZIP_BASE = "node-v22.11.0-win-x64"

# 三个模块级常量的作用域差异，是本文件能「只测映射、不测上游」的前提：
# PAGE_HTML_OK 只负责能被上游那条正则抠中（抠中即进入下载分支），本身不参与断言；
# NODE_ZIP_BASE 同时担任「zip 文件名」与「解压后目录名」两个角色，所以改名分支
# 不需要额外 mock 就能跑到；ZIP_A 只用它的字节摘要，当「任意非 zip 内容」用。


# 分支 → 用例 对照表（供后续改动人快速判断「新分支是否要补测」，也防止用例
# 被误删后无人发现。左列是被测行为，右列是承担该贵任的用例名）。
#
# _check_or_record_zip_sha256（基准文件的四种形态，缺一即退化成「无校验」或「误拒」）：
#   首次下载无基准 → 记录并放行 .............. test_first_download_records_baseline
#   已有基准且一致 → 比对通过 ................ test_second_run_with_same_content_passes
#   已有基准但不一致 → 硬拒（篡改形态）...... test_content_drift_is_refused
#   基准不可读（同名目录）→ 降级放行 ........ test_unreadable_sidecar_degrades_to_pass
#   基准不可写（只读盘）→ 不阻断安装 ........ test_unwritable_sidecar_does_not_fail_install
#
# install_nodejs_windows（按失败点逐条拆分，避免一个用例兼管十行分支而定位不明）：
#   下载页非 200 ................................. test_page_fetch_failure_returns_false
#   HTML 结构变动、抠不到直链 ................. test_version_not_found_in_html_returns_false
#   下载→校验→解压→改名→node -v 全链路 .. test_full_install_renames_and_verifies
#   改名后复核失败（装了但跑不起来）...... test_install_fails_when_node_not_runnable
#   Windows on ARM 误判为 x64（架构识别修复） test_arm_machine_selects_arm64_artifact
#   32 位机器 .................................... test_32bit_machine_selects_x86_artifact
#   有效缓存命中（不重下）...................... test_valid_cached_zip_skips_download
#   残缺缓存删除重下（CR-11 回归锁）.......... test_corrupt_cached_zip_is_deleted_and_redownloaded
#   删不掉残缺包也不能停摆 .................... test_unlink_failure_on_corrupt_cache_is_swallowed
#   哈希不一致 → 删包 + 拒装 .................. test_sha_mismatch_unlinks_zip_and_returns_false
#   删不掉时仍须返回 False（不掩盖真实原因） test_sha_mismatch_survives_unlinkable_zip
#   已有 node/ 只复核不重复改名 ................ test_existing_node_dir_is_verified_without_rename
#   已有 node/ 但不可用 .......................... test_existing_node_dir_but_broken_returns_false
#   解压产物目录名不符合预期 .................. test_rename_branch_when_no_extracted_dir_returns_false
#   任何意外异常不得外溢（中断启动）.......... test_unexpected_exception_is_swallowed_to_false
#
# Linux / macOS 安装器：只验证「命令序列与退出码 → 返回值」的映射；包管理器
# 本身是否可用不在本仓职责内（yum 失败短路、apt 直装、brew 两类异常各自分叉）。
#
# install_nodejs / check_node：平台分发与「已装则不重复安装」的短路。未支持平台
# 必须返回 False 而不是抛异常，否则打包产物在非三大平台上启动即崩。
#
# [2026-09-22 P-1 追加] 权威哈希（nodejs.org 的 SHASUMS256.txt）优先、TOFU 降级为兜底后，
# 新增下面三段用例（TestNodeVersionNormalization / TestNodeShasumsParsing /
# TestNodeOfficialAuthorityWiring 等），锁住四条不变量：
#   ① 期望值取自 nodejs.org 而不是 npmmirror（否则镜像可自证，校验归零）；
#   ② 「有官方期望值且不符」= 硬拒 + 删包 + 不执行，且绝不降级去记新基准；
#   ③ 官方校验通过时旁路基准不得否决它（否则版本轮转仍能造成永久拒装）；
#   ④ 取不到官方清单才走 TOFU，并留下可发现的降级告警。


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _FakeResponse:
    # 覆盖 requests.Response 在本模块被用到的最小面：状态码 / text / 流式内容 / 头。
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._content = content
        self.headers = headers or {}

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        # 返回 None 与 False 同为 falsy（不抑制异常）；恒 False 的 __exit__ 用 bool 标注会被 mypy [exit-return] 拒绝。
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int = 1024) -> Any:
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]


class _DummyTqdm:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def __enter__(self) -> "_DummyTqdm":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def update(self, _n: int) -> None:
        return None


def _make_node_zip() -> bytes:
    # 真 zip：顶层目录名与 zip 去扩展名后的目录名一致（install_nodejs_windows 的改名前提）
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{NODE_ZIP_BASE}/node.exe", "pretend-binary")
        zf.writestr(f"{NODE_ZIP_BASE}/lib/node.js", "pretend-lib")
    return buf.getvalue()


def _requests_stub(responses: dict[str, _FakeResponse], calls: list[str]) -> types.SimpleNamespace:
    # 权威哈希文档（P-1 新增的请求点）的缺省响应：404 = 「取不到官方清单」→ 调用方按
    # 原 TOFU 路径降级，语义与本文件改动前逐字一致。因此**不关心**权威校验的用例不必逐个
    # 登记这个 URL；真正测权威分支的用例显式覆盖该键（见 TestNodeOfficialAuthorityWiring）。
    # 缺省项放在最前且不覆盖调用方同名键，保证「未登记的 URL 一律 AssertionError」这条
    # 严格性仍然成立——多出一个计划外请求不会静默通过。
    merged: dict[str, _FakeResponse] = {"nodejs.org/dist": _FakeResponse(status_code=404)}
    merged.update(responses)

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        calls.append(url)
        for key, resp in merged.items():
            if key in url:
                return resp
        raise AssertionError(f"未预期的请求 URL: {url}")

    return types.SimpleNamespace(get=fake_get)


class _ProcResult:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout = b"v22.11.0"
        self.stderr = b""


def _subprocess_stub(codes: dict[tuple[str, ...], int], calls: list[str]) -> types.SimpleNamespace:
    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> _ProcResult:
        calls.append(" ".join(cmd))
        return _ProcResult(codes.get(tuple(cmd), codes.get(("__default__",), 0)))

    shim = types.SimpleNamespace(**vars(subprocess))
    shim.run = fake_run
    return cast(types.SimpleNamespace, shim)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    # 把安装落点收敛到 tmp_path，并冻结 PATH 快照（用例内 install 分支会真改 os.environ）。
    monkeypatch.setattr(node_install, "execute_dir", str(tmp_path))
    monkeypatch.setattr(node_install, "current_env_path", "C:\\fakebin")
    # monkeypatch 注册后会在用例结束整体还原，避免污染同进程后续用例。
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    state: dict[str, Any] = {"calls": [], "tmp": tmp_path}
    return state


class TestCheckOrRecordZipSha256:
    # trust-on-first-use 基准文件的四种形态：首次记录 / 重复比对 / 内容漂移 / 基准不可读。
    # 本类的价值在于「拒绝条」与「放行条」的边界不能被混为一谈：
    # 只有「基准存在且不一致」才硬拒，其余（缺基准/读不动/写不进）一律不阻断安装。
    def test_first_download_records_baseline(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "node.zip"
        zip_path.write_bytes(ZIP_A)
        assert node_install._check_or_record_zip_sha256(zip_path) is True
        sidecar = Path(str(zip_path) + node_install._NODE_HASH_SUFFIX)
        assert sidecar.read_text(encoding="ascii").strip() == _sha256(ZIP_A)

    # 首次下载：只记录不比对，故返回值必为 True（否则首启就装不上）。
    def test_second_run_with_same_content_passes(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "node.zip"
        zip_path.write_bytes(ZIP_A)
        assert node_install._check_or_record_zip_sha256(zip_path) is True
        assert node_install._check_or_record_zip_sha256(zip_path) is True

    # 第二次进来走的是「比对分支」而不是重复记录——若实现退化成无条件覆写基准，
    # 篡改检测形同虚设，故此处必须让两条路径在行为上可区分。
    def test_content_drift_is_refused(self, tmp_path: Path) -> None:
        # 与 ffmpeg 侧「同一构建标识下内容变了」同构：node 的基准不按构建轮转，
        # 因此任何不一致都按篡改处理，必须 False（调用方据此删包）。
        zip_path = tmp_path / "node.zip"
        zip_path.write_bytes(ZIP_A)
        assert node_install._check_or_record_zip_sha256(zip_path) is True
        zip_path.write_bytes(b"different")
        assert node_install._check_or_record_zip_sha256(zip_path) is False

    # node 侧基准不按构建轮转（与 ffmpeg 的 _build_identity 不同），因此任何不一致
    # 都按篡改处理。把这一条写成独立用例：放宽成「不一致只告警」会在此变红。
    def test_unreadable_sidecar_degrades_to_pass(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "node.zip"
        zip_path.write_bytes(ZIP_A)
        Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).mkdir()
        assert node_install._check_or_record_zip_sha256(zip_path) is True

    # 基准文件被同名目录占住 → read_text 抛 OSError：按「跳过校验」放行。
    # 取舍是「装得上」优先于「校得严」，与 ffmpeg 侧同一口径。
    def test_unwritable_sidecar_does_not_fail_install(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        zip_path = tmp_path / "node.zip"
        zip_path.write_bytes(ZIP_A)
        real_write_text = Path.write_text

        def deny(self: Path, *args: Any, **kwargs: Any) -> int:
            if str(self).endswith(node_install._NODE_HASH_SUFFIX):
                raise OSError("read-only dir")
            return cast(int, real_write_text(self, *args, **kwargs))

        monkeypatch.setattr(Path, "write_text", deny)
        assert node_install._check_or_record_zip_sha256(zip_path) is True
        # （写不进基准只影响「下一次能否比对」，不该让本次安装失败；
        #   这里用窄化的 write_text 桩：仅对 .sha256 旁路文件抛错，其余走真实实现。）


class TestInstallNodejsWindows:
    # Windows 安装链路的六个出口：页面取不到版本 / HTML 结构变动 / 下载 / 校验 /
    # 解压改名 / `node -v` 复核。全部失败路径都必须「返 False 不抛异常」——
    # 调用方 check_node() 据此提示用户手动安装，抛出去会直接中断主程序启动。

    def test_page_fetch_failure_returns_false(self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        # 页面 5xx：直接放弃（不做镜像兜底是刻意的——上游页面结构变动就无从猜直链）。
        calls: list[str] = []
        monkeypatch.setattr(
            node_install,
            "requests",
            _requests_stub({"download": _FakeResponse(status_code=503)}, calls),
        )
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        assert node_install.install_nodejs_windows() is False

    def test_version_not_found_in_html_returns_false(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            node_install, "requests", _requests_stub({"download": _FakeResponse(text="<html>no link</html>")}, calls)
        )
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        assert node_install.install_nodejs_windows() is False

    @staticmethod
    def _wire(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, node_rc: int = 0) -> list[str]:
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": "120"})
        responses = {"nodejs.cn/download/": page, "npmmirror.com": dl}
        monkeypatch.setattr(node_install, "requests", _requests_stub(responses, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({("node", "-v"): node_rc}, proc_calls))
        monkeypatch.setattr(node_install, "current_env_path", str(tmp_path))
        return proc_calls

    def test_full_install_renames_and_verifies(self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        tmp_path: Path = env["tmp"]
        proc_calls = self._wire(monkeypatch, tmp_path, node_rc=0)
        assert node_install.install_nodejs_windows() is True
        assert proc_calls == ["node -v"]
        # 解压产物被改名为固定目录 node/，且已前置注入 PATH（供同进程后续调用命中）
        assert (tmp_path / "node" / "node.exe").is_file()
        assert os.environ["PATH"].startswith(str(tmp_path / "node"))
        # 首次下载的哈希基准已落盘，供下次运行比对
        assert (tmp_path / f"{NODE_ZIP_BASE}.zip{node_install._NODE_HASH_SUFFIX}").is_file()

    def test_install_fails_when_node_not_runnable(self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        tmp_path: Path = env["tmp"]
        self._wire(monkeypatch, tmp_path, node_rc=1)
        assert node_install.install_nodejs_windows() is False

    def test_arm_machine_selects_arm64_artifact(self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        tmp_path: Path = env["tmp"]
        seen: dict[str, str] = {}
        calls: list[str] = []

        page = _FakeResponse(text=PAGE_HTML_OK)

        def fake_get(url: str, *args: object, **kwargs: object) -> _FakeResponse:
            calls.append(url)
            if "npmmirror" in url and url.endswith(".zip"):
                seen["zip"] = url
                return _FakeResponse(content=_make_node_zip(), headers={"Content-Length": "120"})
            return page

        monkeypatch.setattr(node_install, "requests", types.SimpleNamespace(get=fake_get))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        monkeypatch.setattr(node_install.platform, "machine", lambda: "ARM64")
        # 解压桩掉：本用例只断言「架构 → 产物名」的映射，不关心解压后的目录改名
        monkeypatch.setattr(node_install, "unzip_file", lambda *_a, **_k: None)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, proc_calls))
        _ = node_install.install_nodejs_windows()
        assert "win-arm64.zip" in seen["zip"]

    def test_32bit_machine_selects_x86_artifact(self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        seen: dict[str, str] = {}
        page = _FakeResponse(text=PAGE_HTML_OK)

        def fake_get(url: str, *args: object, **kwargs: object) -> _FakeResponse:
            calls.append(url)
            if url.endswith(".zip"):
                seen["zip"] = url
                return _FakeResponse(content=b"not-a-zip-but-unzip-not-reached", headers={"Content-Length": "1"})
            return page

        monkeypatch.setattr(node_install, "requests", types.SimpleNamespace(get=fake_get))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        monkeypatch.setattr(node_install.platform, "machine", lambda: "x86")
        # 让解压直接成功，隔离「架构判定」这一条断言
        monkeypatch.setattr(node_install, "unzip_file", lambda *_a, **_k: None)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, proc_calls))
        _ = node_install.install_nodejs_windows()
        assert "win-x86.zip" in seen["zip"]

    def test_valid_cached_zip_skips_download(self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        tmp_path: Path = env["tmp"]
        cached = tmp_path / f"{NODE_ZIP_BASE}.zip"
        cached.write_bytes(_make_node_zip())
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, proc_calls))
        assert node_install.install_nodejs_windows() is True
        assert not any(u.endswith(".zip") for u in calls), "已有有效缓存不应重新下载"

    def test_corrupt_cached_zip_is_deleted_and_redownloaded(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # CR-11 回归锁：残缺缓存必须删掉重下，并把「新内容的哈希」而不是残缺内容的哈希记进基准。
        tmp_path: Path = env["tmp"]
        cached = tmp_path / f"{NODE_ZIP_BASE}.zip"
        cached.write_bytes(b"\x50\x4b truncated")  # 有 zip 魔数但无 EOCD → is_valid_zip False
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": "120"})
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page, "npmmirror": dl}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, proc_calls))
        assert node_install.install_nodejs_windows() is True
        assert any(u.endswith(".zip") for u in calls), "残缺缓存后必须重下"

    def test_unlink_failure_on_corrupt_cache_is_swallowed(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp_path: Path = env["tmp"]
        cached = tmp_path / f"{NODE_ZIP_BASE}.zip"
        cached.write_bytes(b"\x50\x4b truncated")
        real_unlink = Path.unlink

        def deny(self: Path, *args: Any, **kwargs: Any) -> None:
            if self.name.endswith(".zip"):
                raise OSError("locked")
            real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", deny)
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": "120"})
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page, "npmmirror": dl}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, proc_calls))
        # 删除失败不阻断：随后 open(zip, "wb") 覆盖写，安装仍应成功
        assert node_install.install_nodejs_windows() is True

    def test_sha_mismatch_unlinks_zip_and_returns_false(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp_path: Path = env["tmp"]
        zip_path = tmp_path / f"{NODE_ZIP_BASE}.zip"
        zip_path.write_bytes(_make_node_zip())
        Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).write_text("0" * 64, encoding="ascii")
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": "120"})
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page, "npmmirror": dl}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        assert node_install.install_nodejs_windows() is False
        assert not zip_path.exists()

    def test_sha_mismatch_survives_unlinkable_zip(self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        # 校验不通过时删坏包只是「尽力而为」：删不掉（占用/权限）也必须返回 False，
        # 不能让 OSError 逃出成「安装异常」——那会把真实原因（哈希不一致）盖掉。
        tmp_path: Path = env["tmp"]
        zip_path = tmp_path / f"{NODE_ZIP_BASE}.zip"
        zip_path.write_bytes(_make_node_zip())
        Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).write_text("0" * 64, encoding="ascii")
        real_unlink = Path.unlink

        def deny(self: Path, *args: Any, **kwargs: Any) -> None:
            if self.name.endswith(".zip"):
                raise OSError("locked by another process")
            real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", deny)
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": "120"})
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page, "npmmirror": dl}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        assert node_install.install_nodejs_windows() is False

    def test_existing_node_dir_is_verified_without_rename(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp_path: Path = env["tmp"]
        (tmp_path / "node").mkdir()
        monkeypatch.setattr(node_install, "unzip_file", lambda *_a, **_k: None)
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": "120"})
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page, "npmmirror": dl}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({("node", "-v"): 0}, proc_calls))
        assert node_install.install_nodejs_windows() is True

    def test_existing_node_dir_but_broken_returns_false(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp_path: Path = env["tmp"]
        (tmp_path / "node").mkdir()
        monkeypatch.setattr(node_install, "unzip_file", lambda *_a, **_k: None)
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": "120"})
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page, "npmmirror": dl}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({("node", "-v"): 3}, proc_calls))
        assert node_install.install_nodejs_windows() is False

    def test_rename_branch_when_no_extracted_dir_returns_false(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 解压出来既不是预期目录名、也没有 node/ ——两条分支都不命中，落到末尾 return False
        tmp_path: Path = env["tmp"]
        monkeypatch.setattr(node_install, "unzip_file", lambda *_a, **_k: None)
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": "120"})
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page, "npmmirror": dl}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, proc_calls))
        assert node_install.install_nodejs_windows() is False

    def test_unexpected_exception_is_swallowed_to_false(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("network down")

        monkeypatch.setattr(node_install, "requests", types.SimpleNamespace(get=boom))
        assert node_install.install_nodejs_windows() is False


class TestInstallNodejsLinux:
    def test_centos_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, calls))
        assert node_install.install_nodejs_centos() is True
        assert calls == ["yum install -y epel-release", "yum install -y nodejs"]

    def test_centos_epel_failure_short_circuits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            node_install, "subprocess", _subprocess_stub({("yum", "install", "-y", "epel-release"): 1}, calls)
        )
        assert node_install.install_nodejs_centos() is False
        assert calls == ["yum install -y epel-release"]

    def test_centos_nodejs_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            node_install, "subprocess", _subprocess_stub({("yum", "install", "-y", "nodejs"): 1}, calls)
        )
        assert node_install.install_nodejs_centos() is False

    def test_centos_missing_yum_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            raise FileNotFoundError("yum")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(node_install, "subprocess", shim)
        assert node_install.install_nodejs_centos() is False

    def test_ubuntu_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, calls))
        assert node_install.install_nodejs_ubuntu() is True
        assert calls == ["apt install -y nodejs"]

    def test_ubuntu_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            node_install, "subprocess", _subprocess_stub({("apt", "install", "-y", "nodejs"): 1}, calls)
        )
        assert node_install.install_nodejs_ubuntu() is False

    def test_ubuntu_missing_apt_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            raise OSError("apt")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(node_install, "subprocess", shim)
        assert node_install.install_nodejs_ubuntu() is False


class TestInstallNodejsMac:
    def test_brew_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, calls))
        assert node_install.install_nodejs_mac() is True
        assert calls == ["brew install node"]

    def test_brew_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({("brew", "install", "node"): 127}, calls))
        assert node_install.install_nodejs_mac() is False

    def test_called_process_error_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            raise subprocess.CalledProcessError(1, ["brew"])

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(node_install, "subprocess", shim)
        assert node_install.install_nodejs_mac() is False

    def test_unexpected_error_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            raise ValueError("unexpected")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(node_install, "subprocess", shim)
        assert node_install.install_nodejs_mac() is False


class TestPackageManagerDispatch:
    @pytest.mark.parametrize(
        "dist_id,expected",
        [
            ("centos", "RHS"),
            ("rhel", "RHS"),
            ("alinux", "RHS"),
            ("ubuntu", "DBS"),
            ("debian", "DBS"),
            ("alpine", "DBS"),
        ],
    )
    def test_whitelist(self, monkeypatch: pytest.MonkeyPatch, dist_id: str, expected: str) -> None:
        monkeypatch.setattr(node_install.distro, "id", lambda: dist_id)
        assert node_install.get_package_manager() == expected

    def test_install_nodejs_dispatch_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(node_install, "current_platform", "Windows")
        monkeypatch.setattr(node_install, "install_nodejs_windows", lambda: True)
        assert node_install.install_nodejs() is True

    def test_install_nodejs_dispatch_linux_rhs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(node_install, "current_platform", "Linux")
        monkeypatch.setattr(node_install, "get_package_manager", lambda: "RHS")
        monkeypatch.setattr(node_install, "install_nodejs_centos", lambda: True)
        assert node_install.install_nodejs() is True

    def test_install_nodejs_dispatch_linux_dbs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(node_install, "current_platform", "Linux")
        monkeypatch.setattr(node_install, "get_package_manager", lambda: "DBS")
        monkeypatch.setattr(node_install, "install_nodejs_ubuntu", lambda: False)
        assert node_install.install_nodejs() is False

    def test_install_nodejs_dispatch_darwin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(node_install, "current_platform", "Darwin")
        monkeypatch.setattr(node_install, "install_nodejs_mac", lambda: True)
        assert node_install.install_nodejs() is True

    def test_install_nodejs_unsupported_platform(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(node_install, "current_platform", "FreeBSD")
        assert node_install.install_nodejs() is False


class TestCheckNode:
    # 入口短路的四种输入：已装（不重装）/ rc=0 但 stdout 空 / rc≠0 / 根本没有二进制。
    # 第二种是容易写错的：只判 returncode 会把「跑了但没输出版本号」误判为已装，
    # 而 check_node 因此永不触发自动安装（症状：长期 0 弹幕但面板显示一切正常）。
    def test_installed_returns_true_without_install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, calls))
        monkeypatch.setattr(node_install, "install_nodejs", lambda: False)
        assert node_install.check_nodejs_installed() is True
        assert node_install.check_node() is True

    def test_zero_rc_but_empty_stdout_is_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Empty:
            returncode = 0
            stdout = b"   "

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = lambda *a, **k: _Empty()
        monkeypatch.setattr(node_install, "subprocess", shim)
        assert node_install.check_nodejs_installed() is False

    def test_nonzero_rc_is_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({("node", "-v"): 1}, calls))
        assert node_install.check_nodejs_installed() is False

    def test_missing_binary_triggers_install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            raise FileNotFoundError("node")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(node_install, "subprocess", shim)
        monkeypatch.setattr(node_install, "install_nodejs", lambda: True)
        assert node_install.check_nodejs_installed() is False
        assert node_install.check_node() is True


# ==========================================================================
# 2026-09-22 P-1：nodejs.org 权威哈希优先校验（npmmirror 降级为纯加速镜像）
# ==========================================================================

# 公开可核对的标准值：sha256("") —— 用来把「解析器」本身钉死在字面摘要上。
# 刻意不写成 hashlib.sha256(b"") 现场算：那样等于用被测逻辑的等价实现验证被测逻辑，
# 任何「把整行原样返回」的错误实现都照样绿（本仓「测试不得自实现被测逻辑」口径）。
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
DOC_URL = f"{node_install._NODE_DIST_BASE}v22.11.0/{node_install._NODE_SHASUMS_NAME}"
ZIP_NAME = f"{NODE_ZIP_BASE}.zip"


def _shasums_body(sha: str, name: str = ZIP_NAME) -> str:
    # 真实文档形态：`<64 位十六进制>  <文件名>`（两个空格），末尾带换行。
    return f"{sha}  {name}\n"


class TestNodeVersionNormalization:
    # 版本形态必须能同时拼出镜像 URL 与 nodejs.org 的 dist 路径；裸版本号会让两条一起 404，
    # 而报错落在「取不到官方哈希」上，极易误判成上游故障。
    @pytest.mark.parametrize(
        "raw,expected", [("v22.11.0", "v22.11.0"), ("22.11.0", "v22.11.0"), ("  v24.0.0 ", "v24.0.0")]
    )
    def test_prefix_is_normalized(self, raw: str, expected: str) -> None:
        assert node_install._normalize_node_version(raw) == expected

    def test_empty_stays_empty(self) -> None:
        # 空值不得被拼成 "v"（那会打偏到 https://nodejs.org/dist/v/SHASUMS256.txt）
        assert node_install._normalize_node_version("   ") == ""


class TestNodeShasumsParsing:
    def test_known_hash_shasums_line_is_parsed_verbatim(self) -> None:
        assert node_install._parse_shasums256(_shasums_body(EMPTY_SHA256), ZIP_NAME) == EMPTY_SHA256

    def test_uppercase_digest_is_normalized(self) -> None:
        assert node_install._parse_shasums256(_shasums_body(EMPTY_SHA256.upper()), ZIP_NAME) == EMPTY_SHA256

    def test_other_files_in_the_same_listing_are_ignored(self) -> None:
        # 一份清单上百行：必须只取目标文件名那条，且行序无关。
        body = (
            _shasums_body("1" * 64, "node-v22.11.0-headers.tar.gz")
            + _shasums_body("2" * 64, "node-v22.11.0-win-arm64.zip")
            + _shasums_body(EMPTY_SHA256, ZIP_NAME)
        )
        assert node_install._parse_shasums256(body, ZIP_NAME) == EMPTY_SHA256

    def test_extension_prefix_collision_does_not_mis_match(self) -> None:
        # 判定按「文件名字段逐字相等」，两个方向都必须挡住：
        #   ① 目标比清单条目长（.7z 之于 .zip）——拿不到条目，返回 "";
        #   ② 清单条目以目标为前缀（同名的 .asc/.sig 签名条目，PGP 风格清单里确有这种行）——
        #      若实现退化成 `file_name in fields[1]` 的子串匹配，就会把**签名文件的哈希**
        #      当成 zip 的期望值，于是合法的 zip 被判定为篡改（校验反过来变成拒装源）。
        assert node_install._parse_shasums256(_shasums_body("a" * 64, "node-v22.11.0-win-x64.7z"), ZIP_NAME) == ""
        assert node_install._parse_shasums256(_shasums_body("b" * 64, f"{ZIP_NAME}.asc"), ZIP_NAME) == ""
        assert node_install._parse_shasums256(_shasums_body("c" * 64, f"{ZIP_NAME}.sig"), ZIP_NAME) == ""

    @pytest.mark.parametrize(
        "body",
        [
            "",
            "not a shasums file",
            "<html>403 Forbidden</html>",
            f"{'z' * 64}  {ZIP_NAME}",  # 长度合法但非十六进制
            f"{EMPTY_SHA256[:63]}  {ZIP_NAME}",  # 摘要被截断
            f"{EMPTY_SHA256}",  # 只有摘要、丢了文件名字段
        ],
    )
    def test_non_conforming_lines_return_empty(self, body: str) -> None:
        assert node_install._parse_shasums256(body, ZIP_NAME) == ""


class TestNodeFetchOfficialSha256:
    def test_network_error_degrades_to_empty_with_masked_typed_log(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[str] = []
        monkeypatch.setattr(node_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))

        def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("")  # Windows 下 socket.timeout 的 str() 为空：只能靠 type_name

        monkeypatch.setattr(node_install, "requests", types.SimpleNamespace(get=boom))
        assert node_install._fetch_official_sha256("v22.11.0", ZIP_NAME) == ""
        joined = "\n".join(captured)
        assert "RuntimeError" in joined, "异常日志必须带 type_name（str(e) 可能为空）"
        assert "nodejs.org" in joined, "降级日志必须点名是哪个 URL 没取到"

    def test_missing_entry_logs_which_file_was_expected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[str] = []
        monkeypatch.setattr(node_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))
        resp = _FakeResponse(text=_shasums_body("1" * 64, "node-v9.9.9-linux-x64.tar.xz"))
        monkeypatch.setattr(node_install, "requests", types.SimpleNamespace(get=lambda *a, **k: resp))
        assert node_install._fetch_official_sha256("v22.11.0", ZIP_NAME) == ""
        assert any(ZIP_NAME in m for m in captured)

    def test_doc_url_is_nodejs_org_not_the_mirror(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 镜像自证等于没有校验：文档宿主必须是 nodejs.org 本体。
        calls: list[str] = []
        resp = _FakeResponse(text=_shasums_body(EMPTY_SHA256))

        def _fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
            # 不写「lambda url, *a, **k: (calls.append(url), resp)[1]」形态——list.append 无返回值，
            # mypy [func-returns-value] 拒绝把它放进取值表达式。
            calls.append(url)
            return resp

        monkeypatch.setattr(
            node_install,
            "requests",
            types.SimpleNamespace(get=_fake_get),
        )
        assert node_install._fetch_official_sha256("v22.11.0", ZIP_NAME) == EMPTY_SHA256
        assert calls == [DOC_URL]


class TestNodeAuthorityVsTofu:
    def test_authoritative_match_passes_even_against_stale_sidecar(self, tmp_path: Path) -> None:
        zip_path = tmp_path / ZIP_NAME
        zip_path.write_bytes(ZIP_A)
        Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).write_text("0" * 64, encoding="ascii")
        assert node_install._check_or_record_zip_sha256(zip_path, _sha256(ZIP_A)) is True

    def test_authoritative_mismatch_refuses_and_does_not_record_new_baseline(self, tmp_path: Path) -> None:
        # 降级到 TOFU 会把被篡改的内容记成新基准（一次「文档与产物不一致」即完成洗白），
        # 故不符必须硬拒且**不写**旁路文件。
        zip_path = tmp_path / ZIP_NAME
        zip_path.write_bytes(ZIP_A)
        assert node_install._check_or_record_zip_sha256(zip_path, "f" * 64) is False
        assert not Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).exists()

    def test_no_official_hash_keeps_tofu_and_warns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[str] = []
        monkeypatch.setattr(node_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))
        zip_path = tmp_path / ZIP_NAME
        zip_path.write_bytes(ZIP_A)
        assert node_install._check_or_record_zip_sha256(zip_path, "") is True
        joined = "\n".join(captured)
        assert "TOFU" in joined or "首次信任" in joined, "降级必须写进日志（不得静默）"
        assert Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).is_file()

    def test_tofu_refusal_still_applies_without_official_hash(self, tmp_path: Path) -> None:
        zip_path = tmp_path / ZIP_NAME
        zip_path.write_bytes(ZIP_A)
        assert node_install._check_or_record_zip_sha256(zip_path, "") is True
        zip_path.write_bytes(b"drifted")
        assert node_install._check_or_record_zip_sha256(zip_path, "") is False

    def test_authoritative_pass_still_records_sidecar(self, tmp_path: Path) -> None:
        # 权威通过时顺带记基准：下次官方文档不可达时手上才有可比对的东西。
        zip_path = tmp_path / ZIP_NAME
        zip_path.write_bytes(ZIP_A)
        assert node_install._check_or_record_zip_sha256(zip_path, _sha256(ZIP_A), source_url="https://x/y.zip") is True
        sidecar = Path(str(zip_path) + node_install._NODE_HASH_SUFFIX)
        assert sidecar.read_text(encoding="ascii").strip() == _sha256(ZIP_A)


class TestNodeOfficialAuthorityWiring:
    # 整链验证：期望值确实来自 nodejs.org 的清单，而不是「单元里传了个参数」。
    def _wire(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        *,
        doc_sha: str | None,
        zip_payload: bytes,
        node_rc: int = 0,
    ) -> tuple[list[str], list[str]]:
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=zip_payload, headers={"Content-Length": "120"})
        doc = _FakeResponse(status_code=200 if doc_sha else 404, text=_shasums_body(doc_sha) if doc_sha else "")
        responses = {"nodejs.cn/download/": page, "npmmirror.com": dl, "nodejs.org/dist": doc}
        monkeypatch.setattr(node_install, "requests", _requests_stub(responses, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({("node", "-v"): node_rc}, proc_calls))
        monkeypatch.setattr(node_install, "current_env_path", str(tmp_path))
        return calls, proc_calls

    def test_genuine_artifact_installs_and_doc_is_fetched_first(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp_path: Path = env["tmp"]
        payload = _make_node_zip()
        calls, proc_calls = self._wire(monkeypatch, tmp_path, doc_sha=_sha256(payload), zip_payload=payload)
        assert node_install.install_nodejs_windows() is True
        assert proc_calls == ["node -v"]
        # 文档请求发往 nodejs.org 的对应版本目录，且带 v 前缀
        assert DOC_URL in calls
        assert (tmp_path / "node" / "node.exe").is_file()

    def test_mirror_swapped_payload_is_refused_and_never_executed(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 攻击模型：镜像把 zip 换成后门，官方清单仍是真值 → 必拒、删包、不跑 node -v。
        tmp_path: Path = env["tmp"]
        calls, proc_calls = self._wire(monkeypatch, tmp_path, doc_sha="c" * 64, zip_payload=_make_node_zip())
        assert node_install.install_nodejs_windows() is False
        assert not (tmp_path / ZIP_NAME).exists()
        assert proc_calls == [], "校验不通过的二进制不得被执行"
        assert not (tmp_path / "node").exists()
        assert not Path(str(tmp_path / ZIP_NAME) + node_install._NODE_HASH_SUFFIX).exists()
        assert any(u.endswith("SHASUMS256.txt") for u in calls)

    def test_cached_zip_is_also_checked_against_the_official_doc(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 缓存命中路径同样要过权威校验：旧实现只在本地比对旁路基准，
        # 而基准与产物同目录（强度等同目录权限），官方清单是唯一独立期望值来源。
        tmp_path: Path = env["tmp"]
        payload = _make_node_zip()
        (tmp_path / ZIP_NAME).write_bytes(payload)
        Path(str(tmp_path / ZIP_NAME) + node_install._NODE_HASH_SUFFIX).write_text(_sha256(payload), encoding="ascii")
        _calls, proc_calls = self._wire(monkeypatch, tmp_path, doc_sha="d" * 64, zip_payload=payload)
        assert node_install.install_nodejs_windows() is False
        assert proc_calls == []

    def test_unreachable_doc_degrades_to_tofu_but_still_installs(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # nodejs.org 不可达（境外网络受限时很常见）不得把安装打成失败：
        # 那等于用一个可选加固换掉原本能成功的自动安装（MID-59 的反面形态）。
        tmp_path: Path = env["tmp"]
        payload = _make_node_zip()
        _calls, proc_calls = self._wire(monkeypatch, tmp_path, doc_sha=None, zip_payload=payload)
        captured: list[str] = []
        monkeypatch.setattr(node_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))
        assert node_install.install_nodejs_windows() is True
        assert proc_calls == ["node -v"]
        assert any("TOFU" in m or "首次信任" in m for m in captured)
