# src/node_install.py 的行为锁。
#
# 安装分支（Windows 下载→校验→解压→改名→PATH 注入→node -v 复核、Linux yum/apt、macOS brew）
# 只在「真缺 node 的机器首次启动」时才跑，属典型的「平时代码不发版、一发版就没人验证」路径。
# 补测的意义不是覆盖率本身，而是固化两条已被踩过的坑：
#   1) ：残缺 zip 缓存必须删除重下，否则错误哈希会被固化成基线 → 永久失败且不自愈；
#   2) ：SHA256 基准不一致必须硬拒绝，且拒绝时要清掉坏包（否则下次仍读到它）。
#
# Mock 口径（与 tests/test_ffmpeg_install.py 一致）：
#   - 只替换模块全局引用（requests / subprocess / distro / tqdm / execute_dir），绝不改 stdlib
#     本体（subprocess 用 types.SimpleNamespace 浅拷贝做 shim）；
#   - zip 用真 zipfile 生成，让 is_valid_zip / unzip_file 走真实实现，顺带锁住「node_install 与
#     utils.unzip_file 的落点约定」（解压目录名 = zip 去扩展名）。

import ast
import hashlib
import inspect
import io
import os
import shutil
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


# partial（CODE_REVIEW_2026-10-21）：生产侧三处 node 调用改为「先经 shutil.which 解析、
# 按解析结果调用」。测试进程不得受「本机恰好装了 node」影响——which 会解析到本机绝对路径，
# 使 cmd 断言（"node -v"）非自洽。默认桩原样返回裸名（与改动前实参形态一致）；
# 「解析结果确实被采用」由 TestNodeBinaryResolution 单独覆盖。替身按 AGENTS 约定挂
# **被测模块命名空间**（shim 浅拷贝），不动 stdlib shutil 本体。
@pytest.fixture(autouse=True)
def _hermetic_node_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    shim = types.SimpleNamespace(**vars(shutil))
    shim.which = lambda name, *args, **kwargs: name
    monkeypatch.setattr(node_install, "shutil", shim)


# 三个模块级常量的作用域差异，是本文件能「只测映射、不测上游」的前提：PAGE_HTML_OK 只负责被
# 上游正则抠中（即进入下载分支），本身不参与断言；NODE_ZIP_BASE 同时是「zip 文件名」与
# 「解压后目录名」，改名分支因此无需额外 mock；ZIP_A 只用其字节摘要，当「任意非 zip 内容」用。


# 每个失败点各有独立用例（页面/结构变动/下载/校验/解压改名/复核），避免一个用例兼管多分支而
# 定位不明；新增分支必须补对应用例。全部失败路径的共同契约是「返 False 不抛异常」——调用方
# check_node() 据此提示用户手动安装，抛出去会直接中断主程序启动。
#
# Linux / macOS 安装器：只验证「命令序列与退出码 → 返回值」的映射；包管理器本身是否可用不在
# 本仓职责内（yum 失败短路、apt 直装、brew 两类异常各自分叉）。
#
# install_nodejs / check_node：平台分发与「已装则不重复安装」的短路。未支持平台必须返回 False
# 而不是抛异常，否则打包产物在非三大平台上启动即崩。
#
# 权威哈希（nodejs.org 的 SHASUMS256.txt）优先、TOFU 降级为兜底后，锁住四条不变量：
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
        # ②：生产代码改为按 iter_content 限长读取文档（不再用 response.text 整份物化），
        # 替身必须同形——真实 requests.Response 恒有 encoding，且 text 与 iter_content 同源。
        self.encoding = "utf-8"

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        # 返回 None 与 False 同为 falsy（不抑制异常）；恒 False 的 __exit__ 用 bool 标注会被 mypy [exit-return] 拒绝。
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int = 1024) -> Any:
        # ②：只给了 text= 的替身（版本页/摘要文档用例）按 UTF-8 编码后分块产出，
        # 使「按 iter_content 限长读取」与「text 形态」在替身侧等价（真实 Response 亦然）。
        body = self._content if self._content else self.text.encode("utf-8")
        for i in range(0, len(body), chunk_size):
            yield body[i : i + chunk_size]


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
    # 把安装落点收敛到 tmp_path。[2026-10-31 L-11] 生产侧 PATH 注入已改为现读现拼
    # （导入期快照 current_env_path 已删除），用例内 install 分支真改 os.environ 时
    # monkeypatch 注册后会在用例结束整体还原，不会污染同进程后续用例。
    monkeypatch.setattr(node_install, "execute_dir", str(tmp_path))
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    # 安装链路用例不涉及信任策略（官方清单在这些用例里本来就取不到），统一显式开 TOFU 开关，
    # 使被测对象保持在「安装流程」而非「策略判定」；策略本身由 TestSkipOfficialDocPolicy 钉。
    monkeypatch.setenv(node_install._NODE_ALLOW_TOFU_ENV, "1")
    state: dict[str, Any] = {"calls": [], "tmp": tmp_path}
    return state


class TestCheckOrRecordZipSha256:
    # trust-on-first-use 基准文件的四种形态：首次记录 / 重复比对 / 内容漂移 / 基准不可读。
    # 边界不可混：「基准存在且不一致」与「基准存在但读不出来」（M-11，2026-10-30 收紧，
    # 与 ffmpeg 三链同分支裁决对齐）都硬拒；缺基准默认拒装（TestSkipOfficialDocPolicy 单独钉）、
    # 写不进基准不阻断安装。
    # 2026-10-21：TOFU 降级不再是默认行为——官方清单不可达且无历史基准时默认
    # **拒绝安装**，必须显式设 DLR_NODE_ALLOW_TOFU=1。本类测的是 TOFU 机制本身，故统一开该开关。
    @pytest.fixture(autouse=True)
    def _allow_tofu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(node_install._NODE_ALLOW_TOFU_ENV, "1")

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

    # 第二次进来走「比对分支」而非重复记录——实现若退化成无条件覆写基准，篡改检测形同虚设。
    def test_content_drift_is_refused(self, tmp_path: Path) -> None:
        # 与 ffmpeg 侧「同一构建标识下内容变了」同构：node 的基准不按构建轮转，
        # 因此任何不一致都按篡改处理，必须 False（调用方据此删包）。
        zip_path = tmp_path / "node.zip"
        zip_path.write_bytes(ZIP_A)
        assert node_install._check_or_record_zip_sha256(zip_path) is True
        zip_path.write_bytes(b"different")
        assert node_install._check_or_record_zip_sha256(zip_path) is False

    # M-11（2026-10-30）：基准**存在**却读不出来必须 fail-closed（删包 + 拒装）。旧实现 warning 后
    # return True 放行（「装得上优先于校得严」的旧取舍），与 ffmpeg 三链的 fail-closed 裁决相悖。
    # 基准文件被同名目录占住 → read_text 抛 OSError（IsADirectoryError）。
    def test_unreadable_baseline_refuses_and_unlinks(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "node.zip"
        zip_path.write_bytes(ZIP_A)
        Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).mkdir()
        assert node_install._check_or_record_zip_sha256(zip_path) is False
        assert not zip_path.exists(), "fail-closed 分支必须删包（与 ffmpeg 侧同口径）"

    # ascii 解码失败（基准被非 ASCII 字节污染）旧实现穿到外层 catch-all 被归成泛化「安装失败」，
    # fail-closed 分支整个被跳过；并捕 UnicodeDecodeError 后必须走同一条删包拒装路径。
    def test_non_ascii_baseline_refuses_and_unlinks(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "node.zip"
        zip_path.write_bytes(ZIP_A)
        Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).write_bytes(b"\xff\xfe\xfd")
        assert node_install._check_or_record_zip_sha256(zip_path) is False
        assert not zip_path.exists()

    # 基准文件写不进（记录侧失败）不阻断本次安装：只影响「下一次能否比对」。
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
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": str(len(_make_node_zip()))})
        responses = {"nodejs.cn/download/": page, "npmmirror.com": dl}
        monkeypatch.setattr(node_install, "requests", _requests_stub(responses, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({("node", "-v"): node_rc}, proc_calls))
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
                return _FakeResponse(content=_make_node_zip(), headers={"Content-Length": str(len(_make_node_zip()))})
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
                return _FakeResponse(
                    content=b"not-a-zip-but-unzip-not-reached",
                    headers={"Content-Length": str(len(b"not-a-zip-but-unzip-not-reached"))},
                )
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
        # 有效缓存（is_valid_zip 通过）命中即跳过下载，只取页面与复核
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
        # 残缺缓存必须删掉重下，并把「新内容的哈希」而不是残缺内容的哈希记进基准。
        tmp_path: Path = env["tmp"]
        cached = tmp_path / f"{NODE_ZIP_BASE}.zip"
        cached.write_bytes(b"\x50\x4b truncated")  # 有 zip 魔数但无 EOCD → is_valid_zip False
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": str(len(_make_node_zip()))})
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
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": str(len(_make_node_zip()))})
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page, "npmmirror": dl}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, proc_calls))
        # 删除失败不阻断：随后 open(zip, "wb") 覆盖写，安装仍应成功
        assert node_install.install_nodejs_windows() is True

    def test_sha_mismatch_unlinks_zip_and_returns_false(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 基准预置为全 0（必然与产物不符）：断言删包 + 返 False，避免下次直接复用被篡改内容
        tmp_path: Path = env["tmp"]
        zip_path = tmp_path / f"{NODE_ZIP_BASE}.zip"
        zip_path.write_bytes(_make_node_zip())
        Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).write_text("0" * 64, encoding="ascii")
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": str(len(_make_node_zip()))})
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
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": str(len(_make_node_zip()))})
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
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": str(len(_make_node_zip()))})
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
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": str(len(_make_node_zip()))})
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
        dl = _FakeResponse(content=_make_node_zip(), headers={"Content-Length": str(len(_make_node_zip()))})
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page, "npmmirror": dl}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, proc_calls))
        assert node_install.install_nodejs_windows() is False

    def test_unexpected_exception_is_swallowed_to_false(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 顶层兜底：未预期异常不得外溢（否则首次启动即崩，用户也看不到安装失败的提示）
        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("network down")

        monkeypatch.setattr(node_install, "requests", types.SimpleNamespace(get=boom))
        assert node_install.install_nodejs_windows() is False


class TestInstallNodejsLinux:
    # Linux 两条分支：yum（先 epel-release，失败短路）与 apt 直装；包管理器缺失
    # （FileNotFoundError/OSError）一律返 False 不抛。
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
    # macOS 只有 brew 一条路径：非零退出码、CalledProcessError 与其它意外异常三种失败形态
    # 都必须返 False（不能抛给启动流程）。
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
    # distro.id 白名单 → 包管理器族（RHS=yum 系 / DBS=apt 系）；未列入白名单的发行版不得被
    # 静默当成 DBS。
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
    # SHASUMS256.txt 只认「64 位十六进制 + 两个空格 + 文件名」的行，且文件名字段逐字相等；
    # 大小写摘要归一，其它文件条目与非规范行一律返回空串。
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
        # ③：TOFU 现在必须显式开启（默认拒绝安装）。开启后仍须留痕，且降级事件升为 error 级。
        monkeypatch.setenv(node_install._NODE_ALLOW_TOFU_ENV, "1")
        captured: list[str] = []
        monkeypatch.setattr(node_install.logger, "error", lambda msg, *a, **k: captured.append(str(msg)))
        zip_path = tmp_path / ZIP_NAME
        zip_path.write_bytes(ZIP_A)
        assert node_install._check_or_record_zip_sha256(zip_path, "") is True
        joined = "\n".join(captured)
        assert "TOFU" in joined or "首次信任" in joined, "降级必须写进日志（不得静默）"
        assert Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).is_file()

    def test_no_official_hash_without_baseline_is_refused_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ③ 正面判据：官方文档不可达 + 无历史基准（首次安装）→ 默认**拒绝安装**。
        # 原行为是「记录本次哈希为基线并返回 True」，等于把校验归零；攻击者只需让那 15s 探测失败。
        monkeypatch.delenv(node_install._NODE_ALLOW_TOFU_ENV, raising=False)
        zip_path = tmp_path / ZIP_NAME
        zip_path.write_bytes(ZIP_A)
        assert node_install._check_or_record_zip_sha256(zip_path, "") is False
        assert not Path(str(zip_path) + node_install._NODE_HASH_SUFFIX).exists(), "拒绝安装时不得写入信任基准"

    def test_tofu_refusal_still_applies_without_official_hash(self, tmp_path: Path) -> None:
        monkeypatch_env = node_install._NODE_ALLOW_TOFU_ENV
        zip_path = tmp_path / ZIP_NAME
        zip_path.write_bytes(ZIP_A)
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv(monkeypatch_env, "1")
            assert node_install._check_or_record_zip_sha256(zip_path, "") is True
        zip_path.write_bytes(b"drifted")
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv(monkeypatch_env, "1")
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
        dl = _FakeResponse(content=zip_payload, headers={"Content-Length": str(len(zip_payload))})
        doc = _FakeResponse(status_code=200 if doc_sha else 404, text=_shasums_body(doc_sha) if doc_sha else "")
        responses = {"nodejs.cn/download/": page, "npmmirror.com": dl, "nodejs.org/dist": doc}
        monkeypatch.setattr(node_install, "requests", _requests_stub(responses, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        proc_calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({("node", "-v"): node_rc}, proc_calls))
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

    def test_unreachable_doc_with_opt_in_installs_via_tofu(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ③：显式设 DLR_NODE_ALLOW_TOFU=1 才允许「官方文档不可达 → TOFU 安装」。
        # 这条路径必须仍可用：境外网络受限时 nodejs.org 常不可达，用户显式放行后应能装成功。
        tmp_path: Path = env["tmp"]
        payload = _make_node_zip()
        monkeypatch.setenv(node_install._NODE_ALLOW_TOFU_ENV, "1")
        _calls, proc_calls = self._wire(monkeypatch, tmp_path, doc_sha=None, zip_payload=payload)
        captured: list[str] = []
        monkeypatch.setattr(node_install.logger, "error", lambda msg, *a, **k: captured.append(str(msg)))
        assert node_install.install_nodejs_windows() is True
        assert proc_calls == ["node -v"]
        assert any("TOFU" in m or "首次信任" in m for m in captured)

    def test_unreachable_doc_without_opt_in_refuses_install(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ③ 的正面判据：默认拒绝。攻击模型是「让那 15s 探测失败」即可把校验降级归零，
        # 故「不可达」必须是拒绝安装而不是静默降级；想装的人显式设开关（上一条用例覆盖）。
        tmp_path: Path = env["tmp"]
        payload = _make_node_zip()
        monkeypatch.delenv(node_install._NODE_ALLOW_TOFU_ENV, raising=False)
        _calls, proc_calls = self._wire(monkeypatch, tmp_path, doc_sha=None, zip_payload=payload)
        assert node_install.install_nodejs_windows() is False
        assert proc_calls == [], "拒绝安装时不得执行 node -v 或解压"


# ==========================================================================
# 残余（CODE_REVIEW_2026-10-21）：文档限长读覆盖版本页 + 半份 zip 清理归位
# ==========================================================================
class TestSmallDocumentReadCap:
    # 原 2MB 上限判据只接在 SHA256 文档一侧，npmmirror 版本页仍走 response.text 整份物化。
    # 修复后两条读取链共用 _read_small_document_capped（判据单点）；超限口径：摘要文档记既有
    # error 并返回 ""，版本页按「页面取不到」既有文案拒绝（不新增 msgid，镜像 zip 一发不出）。

    def test_official_doc_over_limit_returns_empty_with_error_log(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[str] = []
        monkeypatch.setattr(node_install.logger, "error", lambda msg, *a, **k: captured.append(str(msg)))
        monkeypatch.setattr(node_install, "_NODE_VERSION_PAGE_MAX_BYTES", 32)
        resp = _FakeResponse(text="x" * 200)
        monkeypatch.setattr(node_install, "requests", types.SimpleNamespace(get=lambda *a, **k: resp))
        assert node_install._fetch_official_sha256("v22.11.0", ZIP_NAME) == ""
        assert any("上限" in m for m in captured), "超限拒绝必须留 error 痕迹"

    def test_version_page_over_limit_is_refused_before_any_zip_request(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # env 夹具的 TOFU/落点设置与本用例无关，但它保证「不会真下载」的隔离前提成立。
        calls: list[str] = []
        page = _FakeResponse(content=b"<html>" + b"x" * 200)
        monkeypatch.setattr(node_install, "_NODE_VERSION_PAGE_MAX_BYTES", 32)
        monkeypatch.setattr(node_install, "requests", _requests_stub({"download": page}, calls))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        assert node_install.install_nodejs_windows() is False
        assert not any(u.endswith(".zip") for u in calls), "超限版本页不得进入镜像下载分支"

    def test_read_cap_helper_is_the_single_source_of_the_two_reads(self) -> None:
        # 结构锁：两条文档读取链（摘要文档 / 版本页）都必须经由同一个 _read_small_document_capped，
        # 防止「又在一处内联一份 iter_content 计数」或「版本页退回整份物化」的双份判据形态。
        # 「不得退回 .text」按 **AST** 判（属性访问集合），不能按源码子串判——本函数自己的
        # 历史注里就写着 response.text，子串判据会被承重注释永久打红。
        fetch_src = inspect.getsource(node_install._fetch_official_sha256)
        win_func = node_install.install_nodejs_windows
        win_src = inspect.getsource(win_func)
        assert "_read_small_document_capped" in fetch_src
        assert "_read_small_document_capped" in win_src
        tree = ast.parse(win_src)
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert "text" not in attrs, "版本页不得退回整份物化形态（S-12 残余本体）"


class TestWindowsPartialZipCleanup:
    # 残余：承诺的「不完整 zip 必须删掉」原先落在 install_nodejs_centos 的
    # locals().get("zip_file_path")（yum 路径无此变量、恒 None 的死代码），而真正写 zip 的
    # install_nodejs_windows 的 except 只记日志。清理归位后：超限中断与半途断流两种形态都
    # 不得把半份文件留在 execute_dir 等下次被 is_valid_zip 当缓存复用（该同型）。

    def test_centos_handler_no_longer_carries_the_dead_zip_cleanup(self) -> None:
        # 反向见证：centos 分支里不得再出现 locals() 死代码——「清理只有一处、且在写 zip 的那侧」。
        tree = ast.parse(inspect.getsource(node_install.install_nodejs_centos))
        call_names = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "locals" not in call_names

    def test_over_limit_download_deletes_partial_zip(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp_path: Path = env["tmp"]
        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        payload = b"x" * 512
        dl = _FakeResponse(content=payload, headers={"Content-Length": str(len(payload))})
        monkeypatch.setattr(node_install, "_NODE_DOWNLOAD_MAX_BYTES", 64)
        monkeypatch.setattr(
            node_install, "requests", _requests_stub({"nodejs.cn/download/": page, "npmmirror.com": dl}, calls)
        )
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        assert node_install.install_nodejs_windows() is False
        assert not (tmp_path / ZIP_NAME).exists(), "超限半份 zip 必须被 except 清理，不得留作下次缓存"

    def test_stream_error_mid_download_deletes_partial_zip(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp_path: Path = env["tmp"]

        class _BoomStream:
            # zip 流式分支的最小替身面：首块真实落盘，第二块抛「半途断流」。
            status_code = 200
            headers = {"Content-Length": "100"}

            def __enter__(self) -> "_BoomStream":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def raise_for_status(self) -> None:
                return None

            def iter_content(self, chunk_size: int = 1024) -> Any:
                yield b"x" * 10
                raise RuntimeError("connection reset mid-download")

        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        boom = _BoomStream()

        def fake_get(url: str, *args: Any, **kwargs: Any) -> Any:
            calls.append(url)
            if url.endswith(".zip"):
                return boom
            if "nodejs.org/dist" in url:
                return _FakeResponse(status_code=404)
            return page

        # unlink 加记：删之前把被删文件的字节记录下来——「半份文件确实写下、且被清走」两侧都是
        # 行为证据，不必事后去读一个必然已不存在的文件自证。
        unlinked: list[bytes] = []
        real_unlink = Path.unlink

        def record_then_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
            if self.name.endswith(".zip"):
                unlinked.append(self.read_bytes())
            real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", record_then_unlink)
        monkeypatch.setattr(node_install, "requests", types.SimpleNamespace(get=fake_get))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        assert node_install.install_nodejs_windows() is False
        assert unlinked == [b"x" * 10], "半途断流留下的半份 zip 必须被 except 清理"
        assert not (tmp_path / ZIP_NAME).exists()

    def test_unlinkable_partial_zip_still_returns_false(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 清理是尽力而为：删不掉（占用/权限）只 warning，不得让清理异常顶掉真实失败原因；
        # 同时覆盖「zip_file_path 尚未绑定就炸」的形态——except 里的 locals() 必须跳过清理而非
        # NameError（页面阶段 requests 直接抛即此形态）。
        tmp_path: Path = env["tmp"]

        class _BoomStream:
            status_code = 200
            headers = {"Content-Length": "100"}

            def __enter__(self) -> "_BoomStream":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def raise_for_status(self) -> None:
                return None

            def iter_content(self, chunk_size: int = 1024) -> Any:
                yield b"x" * 10
                raise RuntimeError("connection reset mid-download")

        real_unlink = Path.unlink

        def deny(self: Path, *args: Any, **kwargs: Any) -> None:
            if self.name.endswith(".zip"):
                raise OSError("locked by another process")
            real_unlink(self, *args, **kwargs)

        calls: list[str] = []
        page = _FakeResponse(text=PAGE_HTML_OK)
        boom_stream = _BoomStream()

        def fake_get(url: str, *args: Any, **kwargs: Any) -> Any:
            calls.append(url)
            if url.endswith(".zip"):
                return boom_stream
            if "nodejs.org/dist" in url:
                return _FakeResponse(status_code=404)
            return page

        captured: list[str] = []
        monkeypatch.setattr(node_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))
        monkeypatch.setattr(Path, "unlink", deny)
        monkeypatch.setattr(node_install, "requests", types.SimpleNamespace(get=fake_get))
        monkeypatch.setattr(node_install, "tqdm", _DummyTqdm)
        assert node_install.install_nodejs_windows() is False
        assert any("清理未完成的 Node.js 下载失败" in m for m in captured), "删不掉必须留 warning 痕迹"
        assert (tmp_path / ZIP_NAME).exists(), "删失败不得伪装成已清理（返回值仍是 False 即可）"

        # zip_file_path 未绑定形态：requests 在页面阶段就抛 → except 里 locals() 无键、跳过清理。
        def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("network down before any download started")

        monkeypatch.setattr(node_install, "requests", types.SimpleNamespace(get=boom))
        assert node_install.install_nodejs_windows() is False


# ==========================================================================
# partial（CODE_REVIEW_2026-10-21）：node 复核调用必须先解析绝对路径
# ==========================================================================
# execute_dir\node 是用户可写目录，裸名 "node" 依赖 PATH 的延迟解析。本轮只做有界的一半：
# 三处调用（改名分支复核 / 已有目录复核 / check_nodejs_installed）一律先 shutil.which 解析一次、
# 按解析结果调用。**未做** ACL/属主校验（需平台层，已登记后续）——本组用例钉的是「解析结果被
# 采用」，不是「目录可信」。
class TestNodeBinaryResolution:
    @staticmethod
    def _absolute_which(monkeypatch: pytest.MonkeyPatch, resolved: str | None) -> None:
        shim = types.SimpleNamespace(**vars(shutil))
        shim.which = lambda name, *args, **kwargs: (resolved if name == "node" else None)
        monkeypatch.setattr(node_install, "shutil", shim)

    def test_rename_branch_invokes_the_resolved_absolute_path(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp_path: Path = env["tmp"]
        resolved = str(tmp_path / "node" / "node.exe")
        proc_calls = TestInstallNodejsWindows._wire(monkeypatch, tmp_path, node_rc=0)
        self._absolute_which(monkeypatch, resolved)
        assert node_install.install_nodejs_windows() is True
        assert proc_calls == [f"{resolved} -v"], "前置 PATH 后的复核必须按 which 解析结果调用，不得仍走裸名"

    def test_existing_node_dir_branch_invokes_the_resolved_absolute_path(
        self, env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tmp_path: Path = env["tmp"]
        (tmp_path / "node").mkdir()
        monkeypatch.setattr(node_install, "unzip_file", lambda *_a, **_k: None)
        proc_calls = TestInstallNodejsWindows._wire(monkeypatch, tmp_path, node_rc=0)
        resolved = str(tmp_path / "node" / "node.exe")
        self._absolute_which(monkeypatch, resolved)
        assert node_install.install_nodejs_windows() is True
        assert proc_calls == [f"{resolved} -v"]

    def test_check_nodejs_installed_invokes_the_resolved_absolute_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(node_install, "subprocess", _subprocess_stub({}, calls))
        resolved = "C:\\Program Files\\nodejs\\node.exe"
        self._absolute_which(monkeypatch, resolved)
        assert node_install.check_nodejs_installed() is True
        assert calls == [f"{resolved} -v"]

    def test_unresolvable_node_falls_back_to_bare_name_and_reports_not_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # which 解析不到（PATH 里根本没有 node）时保留裸名实参，让既有 FileNotFoundError 分支
        # 继续走「未安装→触发自动安装」的既有语义——本条是「不得改成静默 True/抛穿」的反向锁。
        calls: list[str] = []

        def boom(cmd: list[str], *args: object, **kwargs: object) -> None:
            calls.append(" ".join(cmd))
            raise FileNotFoundError("node")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(node_install, "subprocess", shim)
        self._absolute_which(monkeypatch, None)
        assert node_install.check_nodejs_installed() is False
        assert calls == ["node -v"]

    def test_all_three_call_sites_resolve_before_running(self) -> None:
        # 结构锁：三处 subprocess.run 的 node 调用实参必须是 which 的解析结果，防止第四处漏接
        # 或既有点退回裸名形态。
        for func_name in ("install_nodejs_windows", "check_nodejs_installed"):
            tree = ast.parse(inspect.getsource(getattr(node_install, func_name)))
            run_cmds = [
                node.args[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run"
            ]
            assert run_cmds, f"{func_name} 找不到 subprocess.run 调用点，判据失效"
            for cmd in run_cmds:
                assert isinstance(cmd, ast.List) and len(cmd.elts) == 2
                head = cmd.elts[0]
                assert (
                    isinstance(head, ast.Name) and head.id == "_node_bin"
                ), f"{func_name}: node 调用实参不是 which 解析结果（裸名字面量 = M-29 回归形态）"
        win_src = inspect.getsource(node_install.install_nodejs_windows)
        assert win_src.count('_node_bin = shutil.which("node") or "node"') == 2
