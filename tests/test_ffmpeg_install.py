# tests/test_ffmpeg_install.py - 守护 ffmpeg 自动安装器的两条硬行为：
#   1) SHA256 旁路基准**按构建标识命名**（MID-59）：gyan.dev 的
#      ffmpeg-release-essentials.zip 是滚动 URL，上游出新构建后旧命名会让校验永久不等，
#      官方源拒绝 → 用户被永久卡在「请手动安装 ffmpeg」。同一构建标识下内容变化仍必须硬拒绝。
#   2) Linux 的 yum → apt 回退链路真正成立（MIN-24④）：「yum 在位但安装失败」
#      （RHEL 系未启用 EPEL 的常态）必须继续尝试 apt，而不是直接放弃。
#
# [2026-09-22 P-1/P-1b] 完整性模型从「纯 TOFU」升级为「官方公布哈希优先、TOFU 仅作显式降级兜底」。
# 锁住的不变量：
#   ① 「有官方期望值且不符」绝不降级为未校验安装；② 官方校验通过时旁路基准不得否决它
#   （否则 MID-59 的永久死路在文档可达时仍复现）；③ 降级必须留下可读的 warning。
#
# [2026-09-22 同日追加] 两条同源、更晚补上的锁：
#   ④ 下载产物必须是**真压缩包**才允许进入哈希记账（详见 TestDownloadedPayloadMustBeArchive 类头）——
#      一句话：非压缩包先记账 = 把镜像站的人机验证页哈希当成可信基准写进旁路文件。
#   ⑤ Windows 只有 gyan.dev 一条**默认**自动路径（TestWindowsInstallSingleSource）——蓝奏云兜底
#      连同 FFMPEG_LANZOU_* 三个环境变量已整体删除，锁的目的是防止「顺手加回第二条源」。
#      [历史注] 原 P-1b 的开关用例（TestLanzouSwitch / TestLanzouLink / TestLanzouInstall /
#      TestWindowsFallbackOrder / TestWindowsFallbackSwitch）随被删实现一并移除，
#      其「默认拒绝、拒绝日志必须可操作」的语义由 ⑤ 的第二条用例接续。
#
# [2026-09-23 SEV-2218 决策落地] 第二条 Windows 源（BtbN master，见
# src/ffmpeg_master_download.py）改为由环境变量 FFMPEG_MASTER_ALLOWED 显式门控、**默认关闭**；
# 「开启」与「因未开启而跳过」两种情形都必须落 warning。TestMasterSourceGate 锁住这四条，
# 并把 ⑤ 的「不要再长出第二条源」从「单文件 AST 扫 URL」升级为「src/ 全量下载常量白名单
# 反查」（DOWNLOAD_SOURCES，逐源登记完整性方式 ∈ {官方哈希, 官方签名, 第4类, TOFU}）。
#
# Mock 设计：只打桩网络响应头、文件系统与 subprocess（按仓内约定用
# types.SimpleNamespace(**vars(subprocess)) 浅拷贝替换模块全局引用，绝不改 stdlib 本体）。
# 测试内一律不发真实网络请求：自 2026-09-23 起该约定由 **autouse 的 _no_real_egress** 机检
# （SEV-2220）——所有下载模块的出站层被预置成「一调用即 AssertionError」的哨兵，用例需要
# 网络响应时再自行覆盖成按 URL 派发的替身；过去它只是文件头的一句口头约定，而
# install_ffmpeg_windows 会经 src.ffmpeg_master_download **自己**的 requests 真的去探测下载。
#
# [2026-09-21 覆盖率专项扩容] 把本模块从 36% 提到 95%+：补齐 download_ffmpeg_official 全部分支、
# macOS brew 路径、install_ffmpeg 的平台分发，以及 check_ffmpeg_installed 的四类异常形态
# （FileNotFoundError / TimeoutExpired / OSError / 其它）——后者决定「PATH 里残留损坏 ffmpeg」时
# 启动流程会不会被挂死，是真实用户故障的第一现场。追加段沿用同一 Mock 口径，分支地图见
# TestOfficialDownload 上方的「追加段的分支 → 用例」清单。

import ast
import hashlib
import importlib
import io
import os
import subprocess
import types
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import pytest
import requests

import src.ffmpeg_install as ffmpeg_install

# 一份与真实构建无关的假 zip 内容：只用其字节摘要
ZIP_A = b"fake-ffmpeg-build-A"
ZIP_B = b"fake-ffmpeg-build-B-different-content"


# --------------------------------------------------------------------------
# hermetic 出站层（SEV-2220）：本文件任何用例都不得真的发出网络请求。
#
# 为什么桩在「各下载模块自己的模块级 requests 名字」这一层，而不是 socket / urllib：
#   ① 覆盖面正确——src/ffmpeg_install、src/ffmpeg_master_download、src/node_install 全部
#      经 `requests.get(...)`（模块全局名查找）发起出站，替换模块属性即拦住所有调用点；
#      而旧写法只 patch 了 ffmpeg_install 一处，install_ffmpeg_windows 转手调
#      download_ffmpeg_master，用的是 **master 模块自己的** requests → 拦不住（实测：
#      本用例在有外网的机器上会真探到 github.com 并可能开始下载 ~190MB）。
#   ② 不改 stdlib 本体——socket/urlopen 是全进程共享的，替换它会波及同进程里 harness 的
#      守护线程与其它库（AGENTS.md「patch subprocess 必须替换模块全局引用、不能改 stdlib
#      模块本体」同一族理由），且一旦某线程正在用旧引用还会产生跨用例噪声。
# 注册表与「src/ 全量下载常量白名单反查」共用一份事实源（见 _assert_download_sources_registered）。
DOWNLOAD_MODULES: tuple[str, ...] = (
    "src.ffmpeg_install",
    "src.ffmpeg_master_download",
    "src.ffmpeg_linux_download",
    "src.node_install",
)


def _download_module_files() -> set[str]:
    # 点分模块名 → 文件名（_src_http_literals 以文件名为键，两者必须能对上）。
    return {name.rsplit(".", 1)[-1] + ".py" for name in DOWNLOAD_MODULES}


# win_env 里 ffmpeg_install.download_ffmpeg_master 替身的调用记录。
# 由 _no_real_egress 逐用例清空（跨用例串味会让「有没有走第二条源」的断言失真）。
MASTER_CALLS: list[Any] = []


class _EgressTripwire:
    # 哨兵：任何一次未被子替换覆盖的出站调用都立刻 AssertionError（而不是静默走网络）。
    # exceptions / RequestException 保持真身——被测代码只拿它们做 except 元组，不发请求。
    def __init__(self, module_name: str) -> None:
        self._module_name = module_name
        self.exceptions = requests.exceptions
        self.RequestException = requests.RequestException

    def _boom(self, kind: str, *args: Any, **kwargs: Any) -> None:
        raise AssertionError(f"测试内不得发起真实网络请求：{self._module_name}.requests.{kind}({args[:1]!r})")

    def get(self, *args: Any, **kwargs: Any) -> Any:
        self._boom("get", *args, **kwargs)

    def post(self, *args: Any, **kwargs: Any) -> None:
        self._boom("post", *args, **kwargs)

    def request(self, *args: Any, **kwargs: Any) -> None:
        self._boom("request", *args, **kwargs)


@pytest.fixture(autouse=True)
def _no_real_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    # 先把每个下载模块的出站层换成哨兵，再保证「第二条源默认关」不被宿主环境翻牌：
    # FFMPEG_MASTER_ALLOWED 若在本机 shell 里被设成 是/1，全部默认分支用例都会走错路，
    # 故逐用例显式 delenv（仓内约定：环境变量一律 monkeypatch.setenv/delenv，禁 patch.dict）。
    monkeypatch.delenv(ffmpeg_install._FFMPEG_MASTER_ENV, raising=False)
    for name in DOWNLOAD_MODULES:
        module = importlib.import_module(name)
        monkeypatch.setattr(module, "requests", _EgressTripwire(name))
    # 2026-10-02 接线之后（install_ffmpeg_linux 末尾多了「官方月末构建直下」兜底），本文件所有
    # 「两条包管理器都没装上 → 返回 False」的既有用例都会**真走进** src.ffmpeg_linux_download，
    # 执行一整条它们并不想测的下载链（取官方哈希 → 下载 → 解包 → 前置 os.environ["PATH"]）。
    # 实测该链路在哨兵下恰好也返 False，于是既有用例「测的是包管理器结论」这件事失去全部可见证据
    # —— 属 AGENTS.md 禁止的「绿着但没在测」形态。统一在此钉成 False，使既有用例的语义逐字保持
    # 「包管理器结果」；确需测兜底的 TestInstallFfmpegLinuxNativeFallback 各用例在自己的函数体里
    # 再 setattr 覆盖本桩（fixture 先于用例执行，覆盖必然生效），两条「兜底被触达」的判据仍由它们真锁。
    # 出站哨兵本身的强度不因这一桩降低：DOWNLOAD_MODULES 每个模块的 requests 仍然逐个装着。
    monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_linux_native", lambda *args, **kwargs: False)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_zip(tmp_path: Path, data: bytes) -> Path:
    zip_path = tmp_path / "ffmpeg_official_temp.zip"
    zip_path.write_bytes(data)
    return zip_path


# 让旁路文件落在 tmp_path 而不是 execute_dir：_check_or_record_zip_sha256 用的是
# zip_path.parent，故把 zip 写到 tmp_path 即天然隔离。
class TestBuildIdentityKeying:
    def test_identity_differs_per_build_and_stable_within_build(self) -> None:
        headers_old = {"Last-Modified": "Mon, 01 Jun 2026 10:00:00 GMT", "Content-Length": "90000000"}
        headers_new = {"Last-Modified": "Tue, 01 Sep 2026 10:00:00 GMT", "Content-Length": "91000000"}
        id_old = ffmpeg_install._build_identity(headers_old)
        assert id_old == ffmpeg_install._build_identity(headers_old)
        assert id_old != ffmpeg_install._build_identity(headers_new)
        # 文件名安全：不含冒号 / 空格 / 逗号（Last-Modified 原样拼进文件名在 Windows 上非法）
        assert all(ch not in id_old for ch in ': ,|/"\\')

    def test_identity_empty_without_usable_headers(self) -> None:
        # 无头 / 全空头 → ""，此时退回旧命名（保持「有校验」而不是静默放行）
        assert ffmpeg_install._build_identity(None) == ""
        assert ffmpeg_install._build_identity({}) == ""
        assert ffmpeg_install._build_identity({"Server": "nginx"}) == ""
        assert ffmpeg_install._hash_file_name("") == ffmpeg_install._FFMPEG_HASH_FILE

    def test_hash_file_name_is_keyed_by_build(self) -> None:
        name = ffmpeg_install._hash_file_name("abc123def456")
        assert name == "_ffmpeg_official.abc123def456.zip.sha256"
        assert name != ffmpeg_install._FFMPEG_HASH_FILE

    def test_first_download_records_baseline(self, tmp_path: Path) -> None:
        zip_path = _write_zip(tmp_path, ZIP_A)
        build_id = ffmpeg_install._build_identity({"Content-Length": str(len(ZIP_A))})
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, build_id) is True
        sidecar = zip_path.parent / ffmpeg_install._hash_file_name(build_id)
        assert sidecar.read_text(encoding="ascii").strip() == _sha256(ZIP_A)

    def test_same_build_same_content_passes(self, tmp_path: Path) -> None:
        zip_path = _write_zip(tmp_path, ZIP_A)
        build_id = ffmpeg_install._build_identity({"Content-Length": str(len(ZIP_A))})
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, build_id) is True
        # 第二次（同标识、同内容）走比对分支而非重复记录
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, build_id) is True

    def test_corrupt_baseline_file_refuses_instead_of_skipping(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # L-44（2026-10-02，对齐 SEV-2222 口径）：基准**存在**但读取失败（磁盘异常/杀软占用）
        # 时必须拒装（fail-closed），不得 warning 后 return True 放行未校验的二进制——
        # 官方文档不可达时 TOFU 就是最后一道完整性检查。zip 一并被删除（不执行的路径）。
        zip_path = _write_zip(tmp_path, ZIP_A)
        build_id = ffmpeg_install._build_identity({"Content-Length": str(len(ZIP_A))})
        hash_file = tmp_path / ffmpeg_install._hash_file_name(build_id)
        hash_file.write_text("0" * 64, encoding="ascii")

        real_read_text = Path.read_text

        def _deny_sidecar_read(self: Path, *args: Any, **kwargs: Any) -> str:
            # 只拦基准文件本身，其余读不受影响（替身必须收窄到目标路径）
            if self.name == hash_file.name:
                raise PermissionError(13, "模拟杀软占用基准文件")
            return real_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", _deny_sidecar_read)
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, build_id) is False
        # 拒装路径必须删包：未校验的二进制不得留在待解压位置
        assert not zip_path.exists()

    # MID-59 的核心回归：上游换构建（标识变化、内容随之变化）不得判成篡改。
    # 把 _check_or_record_zip_sha256 的 hash_file 改回固定 _FFMPEG_HASH_FILE 即在此变红。
    def test_new_build_records_new_baseline_instead_of_refusing(self, tmp_path: Path) -> None:
        first_id = ffmpeg_install._build_identity({"Last-Modified": "Mon, 01 Jun 2026 10:00:00 GMT"})
        assert ffmpeg_install._check_or_record_zip_sha256(_write_zip(tmp_path, ZIP_A), first_id) is True
        second_id = ffmpeg_install._build_identity({"Last-Modified": "Tue, 01 Sep 2026 10:00:00 GMT"})
        assert ffmpeg_install._check_or_record_zip_sha256(_write_zip(tmp_path, ZIP_B), second_id) is True
        # 旧基准保留（供用户比对两版哈希），但不再参与本轮校验
        assert (tmp_path / ffmpeg_install._hash_file_name(first_id)).is_file()

    def test_legacy_sidecar_does_not_block_new_build(self, tmp_path: Path) -> None:
        # 老用户手上已有旧命名（不随构建轮转）的基准文件：必须能自愈，
        # 否则本次修复对他们毫无意义。
        (tmp_path / ffmpeg_install._FFMPEG_HASH_FILE).write_text("0" * 64, encoding="ascii")
        zip_path = _write_zip(tmp_path, ZIP_A)
        build_id = ffmpeg_install._build_identity({"ETag": '"deadbeef"'})
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, build_id) is True
        assert (tmp_path / ffmpeg_install._hash_file_name(build_id)).is_file()

    # 同一构建标识下内容被换 = 篡改形态，仍须硬拒绝（修复不得顺手放松真防线）。
    def test_same_build_different_content_still_refused(self, tmp_path: Path) -> None:
        build_id = ffmpeg_install._build_identity({"ETag": '"v1"', "Content-Length": "90000000"})
        assert ffmpeg_install._check_or_record_zip_sha256(_write_zip(tmp_path, ZIP_A), build_id) is True
        assert ffmpeg_install._check_or_record_zip_sha256(_write_zip(tmp_path, ZIP_B), build_id) is False

    def test_corrupt_sidecar_read_failure_refuses_install(self, tmp_path: Path) -> None:
        # [历史注] 旧名 test_corrupt_sidecar_read_failure_degrades_to_pass，锁定旧 fail-open
        # 行为（读取失败 → 跳过校验放行）。L-44（2026-10-02）对齐 ffmpeg_master_download 的
        # SEV-2222 口径：官方文档不可达时 TOFU 就是最后一道完整性检查，基准存在却读不出来
        # = 可信基准处于不可信状态，必须拒装（fail-closed）并删包。
        zip_path = _write_zip(tmp_path, ZIP_A)
        sidecar = tmp_path / ffmpeg_install._hash_file_name("x" * 12)
        # 目录当文件读 → OSError（PermissionError）
        sidecar.mkdir()
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, "x" * 12) is False
        assert not zip_path.exists()

    def test_sidecar_path_occupied_by_directory_refuses_install(self, tmp_path: Path) -> None:
        # [历史注] 旧名 test_unwritable_sidecar_does_not_fail_install，注释称走 write_text
        # 分支——实测（含旧实现）读侧先触发：sidecar 是目录时 hash_file.exists() 为 True、
        # read_text 抛 PermissionError，与上一条同走「基准读取失败」路径。L-44 收紧后同样拒装。
        zip_path = _write_zip(tmp_path, ZIP_A)
        (tmp_path / ffmpeg_install._hash_file_name("y" * 12)).mkdir()
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, "y" * 12) is False
        assert not zip_path.exists()


class TestOfficialFailureHint:
    # 官方源失败（默认配置下它是 Windows 唯一一条自动路径）时必须给出「删掉过期基准」这一可执行
    # 指引（MID-59 的排查线索），否则用户只剩一句无指向性的「请手动安装」。
    def test_hint_points_at_sidecar_glob(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[str] = []
        monkeypatch.setattr(
            ffmpeg_install.logger,
            "warning",
            lambda msg, *a, **k: captured.append(str(msg)),
        )
        monkeypatch.setattr(ffmpeg_install.logger, "error", lambda msg, *a, **k: None)
        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_official_windows", lambda: False)
        assert ffmpeg_install.install_ffmpeg_windows() is False
        joined = "".join(captured)
        lowered = joined.lower()
        # 断言按「这条提示必须点名的四件事」写：两个基准前缀（官方源 _ffmpeg_official* /
        # master 源 _ffmpeg_master*）、SHA256 这个词、以及基准所在目录 execute_dir。
        # [2026-09-23 SEV-2220] 旧断言里的 ".sha256" 是**顺带**从别处来的：当时
        # install_ffmpeg_windows 会真的调 download_ffmpeg_master 走外网，日志里混进了带
        # .zip.sha256 字样的行；本文件加了 _no_real_egress 哨兵 + master 源默认关闭之后，
        # 那句话不再出现。提示语本身现在就写 "_ffmpeg_official*" / "_ffmpeg_master*"，
        # 故这里改为直接点名提示应含的内容（顺带把 master 源的基准前缀也纳入 —— 它的
        # 拒装自救路径与 SEV-2222 同源，不该只剩官方源那半句指引）。
        assert "_ffmpeg_official" in lowered, "提示必须点名官方源的旁路基准前缀"
        assert "_ffmpeg_master" in lowered, "提示必须点名 master 源的 TOFU 基准前缀"
        assert "sha256" in lowered
        assert str(ffmpeg_install.execute_dir) in joined


# Linux 分支：yum 与 apt 的先后与回退（MIN-24④）。
class TestLinuxPackageFallback:
    def _fake_subprocess(self, results: dict[tuple[str, ...], int]) -> tuple[types.SimpleNamespace, list[str]]:
        calls: list[str] = []

        class _Result:
            def __init__(self, code: int) -> None:
                self.returncode = code
                self.stderr = b""

        def fake_run(cmd: list[str], *args: object, **kwargs: object) -> _Result:
            key = tuple(cmd[:2])
            calls.append(" ".join(cmd))
            return _Result(results.get(key, 1))

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = fake_run
        # subprocess.CalledProcessError / TimeoutExpired 仍走 vars() 带过来的真身
        return shim, calls

    def test_yum_present_but_failing_still_tries_apt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        shim, calls = self._fake_subprocess({("yum", "install"): 1, ("apt", "update"): 1, ("apt", "install"): 1})
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.install_ffmpeg_linux() is False
        assert any(c.startswith("yum install") for c in calls)
        assert any(c.startswith("apt") for c in calls), "yum 失败后必须继续尝试 apt（MIN-24④）"

    def test_yum_missing_falls_back_to_apt_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        class _Result:
            returncode = 0
            stderr = b""

        def fake_run(cmd: list[str], *args: object, **kwargs: object) -> _Result:
            calls.append(" ".join(cmd))
            if cmd[0] == "yum":
                raise FileNotFoundError("yum")
            return _Result()

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = fake_run
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.install_ffmpeg_linux() is True
        # yum 探测本身先被调用（随即抛 FileNotFoundError），随后 apt 两步成功
        assert calls == ["yum install -y ffmpeg", "apt update", "apt install -y ffmpeg"]

    def test_yum_success_does_not_touch_apt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        shim, calls = self._fake_subprocess({("yum", "install"): 0})
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.install_ffmpeg_linux() is True
        assert not any(c.startswith("apt") for c in calls)


# 旁路文件与产物同目录（防护强度等同目录权限）——这条边界必须留在源码注释里，
# 静态锁避免后续「顺手搬走 / 改成写死单文件」。
def test_sidecar_directory_caveat_documented() -> None:
    source = (Path(__file__).resolve().parents[1] / "src" / "ffmpeg_install.py").read_text(encoding="utf-8")
    assert "等同" in source and "目录权限" in source
    assert "_build_identity" in source and "_hash_file_name(build_id)" in source


# 交叉一致性：download_ffmpeg_official 必须把「由响应头推导的构建标识」**和**「官方公布的
# 期望哈希」一起传进校验函数，否则旁路文件仍按固定名生成（MID-59 的修复形同未做）、
# 或权威校验形同未接入（P-1 的修复形同未做，退化成纯 TOFU）。
# AST 锁比 mock 整条下载链更廉价，也与本仓 ffmpeg 参数类用例（tests/test_ffmpeg_reconnect_args.py）同一手法。
def test_official_download_wires_build_identity() -> None:
    source = (Path(__file__).resolve().parents[1] / "src" / "ffmpeg_install.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "download_ffmpeg_official"
    )
    calls = [node for node in ast.walk(fn) if isinstance(node, ast.Call)]

    def called_name(call: ast.Call) -> str:
        # 不用三参 getattr（返回 Any，会静默放宽后续检查）——显式按节点类型取名字
        target = call.func
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Attribute):
            return target.attr
        return ""

    checker = next((c for c in calls if called_name(c) == "_check_or_record_zip_sha256"), None)
    assert checker is not None, "download_ffmpeg_official 不再调用 _check_or_record_zip_sha256"
    assert len(checker.args) == 3, "校验调用必须把构建标识（第 2 位）与官方期望哈希（第 3 位）一并传入"
    assert isinstance(checker.args[1], ast.Name) and checker.args[1].id == "build_id"
    assert isinstance(checker.args[2], ast.Name) and checker.args[2].id == "official_hash"
    assert any(called_name(c) == "_build_identity" for c in calls), "缺少由响应头推导构建标识的调用"
    # 标识必须在读响应头的作用域内求值（response.headers 是它的唯一来源）
    assert any(called_name(c) == "_build_identity" and c.args and "headers" in ast.dump(c.args[0]) for c in calls)
    # P-1：官方哈希必须由 _fetch_official_sha256 取得，且取的是「zip URL + .sha256」这一文档地址
    # （不是把常量钉进代码，也不是取本地旁路文件的别名路径）。
    fetches = [c for c in calls if called_name(c) == "_fetch_official_sha256"]
    assert len(fetches) == 1, "官方哈希文档必须且只能取一次"
    dumped = ast.dump(fetches[0])
    assert "_OFFICIAL_DOC_SUFFIX" in dumped and "url" in dumped, "官方哈希文档地址必须由被下载的 url 派生"


# ==========================================================================
# 以下为 2026-09-21 覆盖率专项追加段：把「装不上 ffmpeg」的主路径
# （官方源下载 / 平台分发）逐分支锁住。
# ==========================================================================

# 追加段的「分支 → 用例」地图（上方原有段已逐条说明 MID-59 / MIN-24④）。
#
# 为什么要给安装器写这么多用例：它们只在「系统没有 ffmpeg 的机器首次启动」时才跑，
# 属于「平时不发版验证、一发版就没人验证」的路径，失败形态是用户只能手动安装。
#
# download_ffmpeg_official（官方源 gyan.dev）：
#   全链路（下载→形态判定→哈希校验→拣 bin/→copytree→注入 PATH→-version 复核）..
#       test_happy_path_installs_and_verifies
#   产物里没有 bin/ffmpeg.exe（拉错包不能当成功）.............. test_missing_binary_in_package_returns_false
#   基准不一致 → 删掉坏包且不执行它 ................................ test_sha_baseline_mismatch_refuses_and_unlinks
#   装了但复核不过（PATH 命中了损坏产物）........................ test_verification_failure_returns_false
#   旧产物目录整体替换（不留上一次的残留文件）.................. test_pre_existing_ffmpeg_dir_is_replaced
#   网络错与其他异常的分类上报（两条不同日志文案）.............. test_network_error_* / test_unexpected_error_*
#
# 下载产物的形态守卫（TestDownloadedPayloadMustBeArchive，2026-09-22）：三条锁 = 拒装且产物被删 /
#   不产生任何旁路基准 / 判序在哈希记账之前（AST 锁，防「把守卫挪到解压前」这种看似等价的改法）。
#
# install_ffmpeg_windows（TestWindowsInstallSingleSource + TestMasterSourceGate +
#   TestDownloadSourceWhitelist）：Windows 默认只有 gyan.dev 一条自动路径，后来接入的 BtbN master
#   兜底因不满足「官方公布哈希」判据，2026-09-23 起由 FFMPEG_MASTER_ALLOWED 显式门控、默认关闭
#   （删除与门控的缘由见文件头 ④⑤ 两段，不在此重述）。锁三件事：
#   ① 官方源失败即最终失败（默认配置下），且告警点名「删哪个旁路文件」（MID-59）；
#   ② 第二条源必须默认关闭、开启/跳过都落 warning、取值走 config_bool 同一套布尔口径；
#   ③ 全仓下载常量必须落进 DOWNLOAD_SOURCES 白名单并登记模块（防「加回某个国内镜像」）。
#
# check_ffmpeg_installed：四类异常（无文件 / 超时 / OSError / 其它）都得返回 False。
#   超时那条是 2026-09-12 补的：旧实现无 timeout，PATH 里残留卡住的 ffmpeg（损坏产物、
#   网络文件系统、杀软拦截）会把整个启动流程挂死，而版本探测本是毫秒级操作。


class _Resp:
    # requests.Response 在本模块被用到的最小面：状态码 / text / 流式内容 / 头。
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

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *args: object) -> None:
        # 返回 None 与 False 同为 falsy（不抑制异常）；恒 False 的 __exit__ 用 bool 标注会被 mypy [exit-return] 拒绝。
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int = 1024) -> Iterator[bytes]:
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]


class _Bar:
    # tqdm 替身：只保留上下文管理器协议与 update()。进度条本身不是被测对象，
    # 但它的迭代体里就是那段「读流 + 写盘」的下载循环，所以必须能正常进出，
    # 不能直接拿掉——否则下载分支的每一行都跑不到。
    def __init__(self, *_a: object, **_k: object) -> None:
        pass

    def __enter__(self) -> "_Bar":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def update(self, _n: int) -> None:
        return None


def _zip_with_bin(members: tuple[str, ...] = ("bin/ffmpeg.exe", "bin/ffprobe.exe")) -> bytes:
    # 官方源产物的形状：<顶层目录>/bin/ffmpeg.exe。download_ffmpeg_official 靠 os.walk
    # 找 basename=="bin" 且含 ffmpeg.exe 的目录，用真 zip 比多层 mock 更能锁住这条约定：
    # 换实现（比如改成 glob、或去掉 bin 层）会直接在这里变红，而不是退化成「跑得通但装错了」。
    # members 参数化是为了单独跑「有 bin/ 但没有 ffmpeg.exe」那条失败分支。
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in members:
            zf.writestr(f"ffmpeg-n7.1/{name}", "pretend-binary")
    return buf.getvalue()


def _proc_shim(codes: dict[tuple[str, ...], int], calls: list[str]) -> types.SimpleNamespace:
    # 按「完整命令元组」查退出码，查不到则取 __default__（缺省为 0，即成功）：
    # 大多数用例只关心某一步失败，不想为了跑到底而枚举所有命令。
    # calls 是故意外传的：同一轮里 yum / apt / ffmpeg 复核会追加到同一个列表，
    # 而「顺序」本身就是 MIN-24④（yum 失败后仍须试 apt）的断言对象。
    # stdout/stderr 都给真字节：linux 分支会直接对 stderr 做 decode，给 None 会
    # 把「安装失败」测成「AttributeError」，错到另一个根因上去。
    class _R:
        def __init__(self, code: int) -> None:
            self.returncode = code
            self.stdout = b"ffmpeg version n7.1"
            self.stderr = b"boom"

    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> _R:
        calls.append(" ".join(cmd))
        return _R(codes.get(tuple(cmd), codes.get(("__default__",), 0)))

    shim = types.SimpleNamespace(**vars(subprocess))
    shim.run = fake_run
    return cast(types.SimpleNamespace, shim)


@pytest.fixture
def win_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # 安装落点收敛到 tmp_path：三个 execute_dir / ffmpeg_path / current_env_path 都是
    # 模块级常量，不换掉就会往仓库目录（本机即 _internal/）写几百 MB 产物与旁路文件。
    # PATH 快照冻结后由 monkeypatch 在用例结束整体还原：安装分支会真改 os.environ["PATH"]，
    # 残留会污染同进程后续用例的 subprocess 查找路径。
    monkeypatch.setattr(ffmpeg_install, "execute_dir", str(tmp_path))
    monkeypatch.setattr(ffmpeg_install, "ffmpeg_path", str(tmp_path / "ffmpeg"))
    monkeypatch.setattr(ffmpeg_install, "current_env_path", "C:\\fakebin")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    monkeypatch.setattr(ffmpeg_install, "tqdm", _Bar)

    # SEV-2220 的「哨兵被覆盖即红」用例需要走真 master 代码，但 master 会经 ffmpeg_install
    # 模块级的这个名字调用（不是 master 模块自己的 requests），故覆盖点在这里。
    # 默认实现：记一次名字 + 返回 False（等价于「兜底失败」），绝不真下载。
    def _record_master_call(*args: Any, **kwargs: Any) -> bool:
        # 不写「lambda: LIST.append(x) or False」形态——list.append 无返回值，mypy [func-returns-value] 拒绝。
        MASTER_CALLS.append(args or kwargs)
        return False

    monkeypatch.setattr(ffmpeg_install, "download_ffmpeg_master", _record_master_call)
    return tmp_path


class TestThinWrappers:
    # CR-11 把实现下沉到 src.utils，本模块只留薄封装：薄封装必须在（调用点/测试仍引用），
    # 且必须真的委托到 utils，否则「两份实现重新分叉」的老问题会复发。
    def test_is_valid_zip_delegates_to_utils(self, tmp_path: Path) -> None:
        good = tmp_path / "good.zip"
        good.write_bytes(_zip_with_bin())
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not-a-zip-at-all")
        assert ffmpeg_install._is_valid_zip(good) is True
        assert ffmpeg_install._is_valid_zip(bad) is False
        assert ffmpeg_install._is_valid_zip(tmp_path / "nope.zip") is False

    def test_sha256_wrapper_matches_hashlib(self, tmp_path: Path) -> None:
        p = tmp_path / "x.bin"
        p.write_bytes(ZIP_A)
        assert ffmpeg_install._sha256_of_file(p) == _sha256(ZIP_A)


class TestBuildIdentityGuard:
    def test_non_mapping_headers_returns_empty(self) -> None:
        # 非 Mapping 形态的 headers 不得把安装流程带崩，退化为旧命名即可。
        assert ffmpeg_install._build_identity(cast(Any, 123)) == ""


class TestStaleSidecarWarning:
    def test_new_build_lists_superseded_baseline(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 目录里已有旧基准时，为新构建记录基准要顺带点名被取代的文件（MID-59 的排查线索）。
        zip_path = _write_zip(tmp_path, ZIP_A)
        (tmp_path / "_ffmpeg_official.aaaa1111bbbb.zip.sha256").write_text("0" * 64, encoding="ascii")
        captured: list[str] = []
        monkeypatch.setattr(ffmpeg_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, "cccc2222dddd") is True
        assert any("aaaa1111bbbb" in m for m in captured)


class TestOfficialDownload:
    # 官方源是首选路径，70+ 平台的录制都依赖它。本类的重点不是「能装上」，而是
    # 五种「不能装上」彼此不混淆：拉错包 / 基准不一致 / 复核不过 / 旧产物残留 /
    # 网络错与未知错。其中前三种都必须保证不执行刚下载的二进制（否则完整性
    # 校验只是自欺），第四种必须保证替换而非叠加（否则旧 ffmpeg.exe 仍在 PATH 里）。
    def _requests(self, get_impl: Any) -> types.SimpleNamespace:
        return types.SimpleNamespace(get=get_impl, RequestException=requests.RequestException)

    def test_happy_path_installs_and_verifies(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _zip_with_bin()
        calls: list[str] = []
        monkeypatch.setattr(
            ffmpeg_install,
            "requests",
            self._requests(lambda *a, **k: _Resp(content=payload, headers={"Content-Length": str(len(payload))})),
        )
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({("ffmpeg", "-version"): 0}, calls))
        assert ffmpeg_install.download_ffmpeg_official("https://x/ffmpeg.zip", str(win_env)) is True
        assert (win_env / "ffmpeg" / "ffmpeg.exe").is_file()
        assert not (win_env / "ffmpeg_official_temp.zip").exists()
        assert calls == ["ffmpeg -version"]
        assert os.environ["PATH"].startswith(str(win_env / "ffmpeg"))

    def test_missing_binary_in_package_returns_false(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _zip_with_bin(members=("bin/ffprobe.exe",))
        calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "requests", self._requests(lambda *a, **k: _Resp(content=payload)))
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({}, calls))
        assert ffmpeg_install.download_ffmpeg_official("https://x/ffmpeg.zip", str(win_env)) is False
        assert calls == []

    def test_sha_baseline_mismatch_refuses_and_unlinks(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _zip_with_bin()
        (win_env / ffmpeg_install._FFMPEG_HASH_FILE).write_text("0" * 64, encoding="ascii")
        calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "requests", self._requests(lambda *a, **k: _Resp(content=payload)))
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({}, calls))
        assert ffmpeg_install.download_ffmpeg_official("https://x/ffmpeg.zip", str(win_env)) is False
        assert not (win_env / "ffmpeg_official_temp.zip").exists()

    def test_verification_failure_returns_false(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _zip_with_bin()
        calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "requests", self._requests(lambda *a, **k: _Resp(content=payload)))
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({("ffmpeg", "-version"): 1}, calls))
        assert ffmpeg_install.download_ffmpeg_official("https://x/ffmpeg.zip", str(win_env)) is False

    def test_pre_existing_ffmpeg_dir_is_replaced(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        stale = win_env / "ffmpeg"
        stale.mkdir()
        (stale / "obsolete.txt").write_text("x", encoding="utf-8")
        payload = _zip_with_bin()
        calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "requests", self._requests(lambda *a, **k: _Resp(content=payload)))
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({}, calls))
        assert ffmpeg_install.download_ffmpeg_official("https://x/ffmpeg.zip", str(win_env)) is True
        assert not (stale / "obsolete.txt").exists()

    def test_network_error_is_reported_as_failure(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*a: object, **k: object) -> None:
            raise requests.RequestException("connection reset")

        monkeypatch.setattr(ffmpeg_install, "requests", self._requests(boom))
        assert ffmpeg_install.download_ffmpeg_official("https://x/ffmpeg.zip", str(win_env)) is False

    def test_unexpected_error_is_reported_as_failure(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 载荷必须本身是合法 zip：形态守卫上线后，再拿 b"not-a-zip" 当载荷会在守卫处就返回，
        # 本用例想锁的 except Exception 分支（「安装失败不得打断主程序启动」）反而没被覆盖。
        payload = _zip_with_bin()
        monkeypatch.setattr(ffmpeg_install, "requests", self._requests(lambda *a, **k: _Resp(content=payload)))

        def explode(*a: object, **k: object) -> None:
            raise RuntimeError("zip exploded")

        monkeypatch.setattr(ffmpeg_install, "unzip_file", explode)
        assert ffmpeg_install.download_ffmpeg_official("https://x/ffmpeg.zip", str(win_env)) is False

    def test_official_windows_entrypoint_uses_gyan_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, str] = {}
        monkeypatch.setattr(
            ffmpeg_install,
            "download_ffmpeg_official",
            lambda url, dest: seen.update(url=url) or True,
        )
        assert ffmpeg_install.install_ffmpeg_official_windows() is True
        assert "gyan.dev" in seen["url"]


class TestDownloadedPayloadMustBeArchive:
    # 形态守卫（2026-09-22）：下载产物必须先是**真压缩包**，才允许进哈希校验/记账。
    # 这条不是理论演练——有镜像站在被直接 GET 时回 200 + text/html 的人机验证（PoW）页，
    # 正文约 10KB、且不带 Content-Length / ETag / Last-Modified。三个头全缺时
    # _build_identity 返回 ""，旁路基准落到旧文件名 _ffmpeg_official.zip.sha256；
    # 没有这道守卫，TOFU 分支会把那段 HTML 的哈希当成「可信基准」写盘，
    # 而失败要等到 unzip_file 才暴露——基准已被污染，下次拿到真包反倒可能被判成篡改。
    HTML_CHALLENGE = (
        b'\n<!doctype html>\n<html lang="zh-CN"><head><title>download</title></head>'
        b"<body><script src=/static/public/download-pow.js></script></body></html>"
    )

    def _requests(self, payload: bytes, *, doc_text: str = "") -> types.SimpleNamespace:
        # 按 URL 后缀派发：官方哈希文档取 doc_text（默认空 = 取不到 → 走 TOFU 降级分支），
        # 其余即被下载的 zip 地址。默认让文档不可达，正是为了把「只有 TOFU 会记账」
        # 这条最容易中毒的路径摆在台面上。
        def fake_get(url: str, *a: Any, **k: Any) -> _Resp:
            if url.endswith(".sha256"):
                return _Resp(text=doc_text)
            return _Resp(content=payload)

        return types.SimpleNamespace(get=fake_get, RequestException=requests.RequestException)

    def test_html_challenge_is_refused_without_recording_baseline(
        self, win_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "requests", self._requests(self.HTML_CHALLENGE))
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({}, calls))
        captured: list[str] = []
        monkeypatch.setattr(ffmpeg_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))

        assert ffmpeg_install.download_ffmpeg_official("https://mirror/ffmpeg.zip", str(win_env)) is False
        # ① 产物被删：残缺/非压缩包不得留在目录里被后续运行当成「已下载」
        assert not (win_env / "ffmpeg_official_temp.zip").exists()
        # ② 一个基准文件都没写——这正是中毒点
        assert list(win_env.glob("_ffmpeg_official*")) == []
        # ③ 从未执行刚下载的二进制
        assert calls == []
        # ④ 没走到哈希环节，故不该出现 TOFU 降级告警（出现了就说明判序被改动了）
        assert not any("TOFU" in m for m in captured)

    def test_truncated_zip_is_refused_before_hashing(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 半截 zip（进程被杀 / 磁盘满 / 网络中断）没有中央目录，is_zipfile 判 False；
        # 旧实现会把它一路带到解压才炸，且中途可能已把残缺内容的哈希记成基准。
        monkeypatch.setattr(ffmpeg_install, "requests", self._requests(_zip_with_bin()[:80]))
        assert ffmpeg_install.download_ffmpeg_official("https://x/ffmpeg.zip", str(win_env)) is False
        assert list(win_env.glob("_ffmpeg_official*")) == []

    def test_valid_zip_still_records_baseline(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 对照组：守卫必须是「只拦非压缩包」，不得退化成永远拒绝——合法载荷 + 取不到官方文档
        # 时，仍应照 MID-59 的记录路径写下基准并装成功。
        payload = _zip_with_bin()
        calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "requests", self._requests(payload))
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({("ffmpeg", "-version"): 0}, calls))
        assert ffmpeg_install.download_ffmpeg_official("https://x/ffmpeg.zip", str(win_env)) is True
        assert list(win_env.glob("_ffmpeg_official*.sha256"))
        assert calls == ["ffmpeg -version"]

    def test_guard_is_ordered_before_hash_recording(self) -> None:
        # AST 顺序锁：把守卫挪到「解压之前」在文本上等价（都拦住坏包），但基准已被污染，
        # 这条正是那种改法的回归锁——形态判定必须紧接在下载之后、哈希记账之前。
        source = (Path(__file__).resolve().parents[1] / "src" / "ffmpeg_install.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "download_ffmpeg_official"
        )
        order = [
            (node.lineno, name)
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"_is_valid_zip", "_check_or_record_zip_sha256"}
            for name in [node.func.id]
        ]
        form = [ln for ln, name in order if name == "_is_valid_zip"]
        hashc = [ln for ln, name in order if name == "_check_or_record_zip_sha256"]
        assert form and hashc, "守卫或哈希记账调用缺失"
        assert max(form) < min(hashc), "_is_valid_zip 必须先于 _check_or_record_zip_sha256"


class TestWindowsInstallSingleSource:
    # 现状：蓝奏云兜底已删除（2026-09-22）、BtbN master 改为**默认关闭**（2026-09-23，SEV-2218），
    # 于是「Windows 只有 gyan.dev 一条默认自动路径」重新成立；本类锁「不要再长出**默认**第二条源」。
    # [历史注] 本类旧注释自称「按 URL 常量集合而非 lanzou 字样判定，换成任意别的镜像名也拦得住」，
    # 与实现相反：那条锁只 ast.parse 了 src/ffmpeg_install.py 一个文件，而真正的第二条源在
    # src/ffmpeg_master_download.py 里，故它恒绿。判定范围现已扩成「遍历 src/ 全部模块的
    # http(s) 字面量 + 反查 DOWNLOAD_SOURCES 白名单」，见 TestDownloadSourceWhitelist（SEV-2220）。
    def test_official_failure_is_final(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 默认（未开启 FFMPEG_MASTER_ALLOWED）：官方源失败即最终失败，不得再有第二条下载尝试。
        # download_ffmpeg_master 这里刻意也换成替身并记录调用：一是让「没走到第二条源」可断言，
        # 二是即便宿主环境把开关打开也不会真去下载（哨兵只拦 requests，不拦这条函数）。
        calls: list[str] = []

        def _fake_official() -> bool:
            calls.append("official")
            return False

        def _fake_master(*args: Any, **kwargs: Any) -> bool:
            calls.append("master")
            return False

        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_official_windows", _fake_official)
        monkeypatch.setattr(ffmpeg_install, "download_ffmpeg_master", _fake_master)
        assert ffmpeg_install.install_ffmpeg_windows() is False
        assert calls == ["official"], "官方源失败后不得再有第二条下载尝试"

    def test_no_lanzou_env_or_entry_point_remains(self) -> None:
        # 只看 AST：模块头里保留了一条说明「为何删除」的历史注释，含 FFMPEG_LANZOU_* 字面量，
        # 那是刻意留下的（注释「只增不改」约定），所以文本 grep 会误报，必须按代码结构判。
        source = (Path(__file__).resolve().parents[1] / "src" / "ffmpeg_install.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        assert not {
            n for n in names if "lanzou" in n.lower()
        }, f"仍残留蓝奏云入口：{sorted(n for n in names if 'lanzou' in n.lower())}"
        env_reads = {
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        assert not {e for e in env_reads if "LANZOU" in e.upper()}, f"仍在读取镜像开关环境变量：{sorted(env_reads)}"


# ==========================================================================
# 2026-09-23 SEV-2218：第二条 Windows 运行期 ffmpeg 源的显式开关（默认关闭）
# ==========================================================================


def _platform_shim(machine: str) -> types.SimpleNamespace:
    # platform 是 stdlib 模块本体，不能 monkeypatch.setattr(ffmpeg_install.platform, ...)
    # ——那会波及同进程其它代码（与 patch subprocess 同一族约定）。浅拷贝换单属性。
    shim = types.SimpleNamespace(**vars(ffmpeg_install.platform))
    shim.machine = lambda: machine
    return cast(types.SimpleNamespace, shim)


class TestMasterSourceGate:
    # 四条锁：① 默认关闭时根本不进 master 路径；② 显式开启时才进；③ 两种情形都落 warning
    # （不得静默）；④ 取值口径复用 src/config_bool 的同一识别集合，不得再造第三套布尔判定。
    def _record(
        self, monkeypatch: pytest.MonkeyPatch, *, official_result: bool, master_result: bool, machine: str
    ) -> list[tuple[str, dict[str, Any]]]:
        seen: list[tuple[str, dict[str, Any]]] = []

        def official() -> bool:
            seen.append(("official", {}))
            return official_result

        def master(_dest: str, **kw: Any) -> bool:
            seen.append(("master", kw))
            return master_result

        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_official_windows", official)
        monkeypatch.setattr(ffmpeg_install, "download_ffmpeg_master", master)
        monkeypatch.setattr(ffmpeg_install, "platform", _platform_shim(machine))
        return seen

    def _warnings(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        captured: list[str] = []
        monkeypatch.setattr(ffmpeg_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))
        return captured

    def test_default_off_skips_master_on_x86_64(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ffmpeg_install._FFMPEG_MASTER_ENV, raising=False)
        seen = self._record(monkeypatch, official_result=False, master_result=True, machine="AMD64")
        assert ffmpeg_install.install_ffmpeg_windows() is False
        assert [name for name, _kw in seen] == ["official"], "未开启开关时不得尝试 master 源"

    def test_default_off_skips_master_on_arm64(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # ARM64 是 master 源存在的主要理由（gyan.dev 只发 x86_64），但它同样**不默认**开启：
        # 未开启时直接用官方 x86_64 构建经模拟运行，至少可用。
        monkeypatch.delenv(ffmpeg_install._FFMPEG_MASTER_ENV, raising=False)
        seen = self._record(monkeypatch, official_result=True, master_result=True, machine="ARM64")
        assert ffmpeg_install.install_ffmpeg_windows() is True
        assert [name for name, _kw in seen] == ["official"]

    def test_enabled_tries_master_after_official_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ffmpeg_install._FFMPEG_MASTER_ENV, "是")
        seen = self._record(monkeypatch, official_result=False, master_result=True, machine="AMD64")
        assert ffmpeg_install.install_ffmpeg_windows() is True
        assert [name for name, _kw in seen] == ["official", "master"]
        assert seen[1][1].get("arch") == "win64"

    def test_enabled_arm64_tries_native_master_first_then_official(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 开启后 arm64 才走原生构建；原生失败仍退回官方 x86_64 保底（顺序即既有契约）。
        monkeypatch.setenv(ffmpeg_install._FFMPEG_MASTER_ENV, "true")
        seen = self._record(monkeypatch, official_result=True, master_result=False, machine="aarch64")
        assert ffmpeg_install.install_ffmpeg_windows() is True
        assert [name for name, _kw in seen] == ["master", "official"]
        assert seen[0][1].get("arch") == "winarm64"

    def test_both_gate_outcomes_log_a_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 「开启 = 本次用的是未校验 TOFU 源」「未开启 = 因开关而未兜底」两种情形都必须落盘，
        # 静默会把这条弱校验路径藏进日志里（本仓对降级的一贯口径：见 ffmpeg_install 的
        # 「未取得官方 SHA256 → 显式 warning」）。
        warnings_off = self._warnings(monkeypatch)
        monkeypatch.delenv(ffmpeg_install._FFMPEG_MASTER_ENV, raising=False)
        self._record(monkeypatch, official_result=False, master_result=True, machine="AMD64")
        assert ffmpeg_install.install_ffmpeg_windows() is False
        joined_off = "".join(warnings_off)
        assert ffmpeg_install._FFMPEG_MASTER_ENV in joined_off, "跳过兜底也要点名是哪个开关"
        assert "跳过" in joined_off

        warnings_on: list[str] = []
        monkeypatch.setattr(ffmpeg_install.logger, "warning", lambda msg, *a, **k: warnings_on.append(str(msg)))
        monkeypatch.setenv(ffmpeg_install._FFMPEG_MASTER_ENV, "on")
        self._record(monkeypatch, official_result=False, master_result=False, machine="AMD64")
        assert ffmpeg_install.install_ffmpeg_windows() is False
        joined_on = "".join(warnings_on)
        assert ffmpeg_install._FFMPEG_MASTER_ENV in joined_on
        assert "TOFU" in joined_on or "未校验" in joined_on, "开启弱校验源时必须写清强度回落了"

    @pytest.mark.parametrize(
        "raw",
        ["是", "true", "TRUE", " t ", "yes", "y", "on", "1"],
    )
    def test_true_tokens_all_enable(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv(ffmpeg_install._FFMPEG_MASTER_ENV, raw)
        assert ffmpeg_install._master_source_allowed() is True

    @pytest.mark.parametrize("raw", ["否", "false", "f", "no", "n", "off", "0", "", "   ", "随便写的值"])
    def test_false_and_unknown_tokens_keep_it_off(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        # 无法识别 → 返回 default=False（宁可少一条弱校验路径，也不因用户手误写出
        # "ture" 这种拼错就默认放行的形态）。
        monkeypatch.setenv(ffmpeg_install._FFMPEG_MASTER_ENV, raw)
        assert ffmpeg_install._master_source_allowed() is False

    def test_missing_env_keeps_it_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ffmpeg_install._FFMPEG_MASTER_ENV, raising=False)
        assert ffmpeg_install._master_source_allowed() is False

    def test_boolean_vocabularies_are_not_duplicated(self) -> None:
        # 「同一份配置在不同模块语义不同」是本仓已付过学费的坑（AGENTS.md 第 9 条）。
        # 这里锁两件事：① 开关解析必须经 parse_config_bool（不允许现场写 == "1" / in ("true",…)）；
        # ② 判定用的是 src/config_bool 的真值集合本身，而不是测试里另抄一份。
        source = (Path(__file__).resolve().parents[1] / "src" / "ffmpeg_install.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_master_source_allowed")
        called = {
            node.func.id for node in ast.walk(fn) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "parse_config_bool" in called, f"开关解析未走统一入口，实际调用：{sorted(called)}"
        from src.config_bool import TRUE_TOKENS

        assert "是" in TRUE_TOKENS and "1" in TRUE_TOKENS  # 与上面参数化所用集合同源


# ==========================================================================
# 2026-09-23 SEV-2220 ②：下载源白名单（反查 src/ 全量 http(s) 常量，而非单文件）
# ==========================================================================

# 完整性方式取值域：与 AGENTS.md「三类钉定/校验」+ build_exe 的第 4 类同一套词表。
INTEGRITY_METHODS: frozenset[str] = frozenset({"官方哈希", "官方签名", "第4类", "TOFU"})

# 运行期可下载二进制/脚本的宿主白名单。键 = hostname（小写），值 = (完整性方式, 说明)。
# 新增一条出站下载源必须同时改三处：源码里的 URL 常量、本表、以及（若来自新模块）
# DOWNLOAD_MODULES 注册表 —— 否则本节的锁直接变红。
DOWNLOAD_SOURCES: dict[str, tuple[str, str]] = {
    "www.gyan.dev": (
        "官方哈希",
        "Windows 运行期 ffmpeg 默认且唯一自动路径；<zip>.sha256 与产物同主机同通道，"
        "属同源一致性校验而非来源认证（MIN-2258）",
    ),
    "github.com": (
        "TOFU",
        "BtbN/FFmpeg-Builds 的 master-latest 滚动构建：权威上游，但不公布 latest 的 SHA256；"
        "需 FFMPEG_MASTER_ALLOWED 显式开启，候选顺序必须排在任何镜像之前（SEV-2218）",
    ),
    # 与上一条同主机族但**异服务**：github.com 那条记的是「产物下载域」（master-latest 无公布哈希 →
    # TOFU），本条记的是「release asset 的 digest 字段」（月末 autobuild 标签不可变 → 官方哈希）。
    # 两条不得合并成一条，否则要么把已校验的 Linux 直下错标成 TOFU、要么把 master 那条 TOFU 洗白。
    "api.github.com": (
        "官方哈希",
        "Linux 运行期直下的期望值来源（release asset 的 digest 字段，与产物下载域异服务）；"
        "URL 里的月末 autobuild 标签不可变，故期望值不随上游重发漂移",
    ),
    "fyhub.cn": (
        "TOFU",
        "BtbN master 的个人镜像：直链实测回人机验证页、.sha256 文档 404；只作镜像兜底项",
    ),
    "nodejs.org": (
        "官方哈希",
        "node 运行期安装的期望值来源（dist/<version>/SHASUMS256.txt，与产物异源）",
    ),
    "npmmirror.com": (
        "官方哈希",
        "node zip 的加速镜像；哈希一律以 nodejs.org 官方清单为准，镜像不自证",
    ),
    "nodejs.cn": (
        "官方哈希",
        "仅用于抓「当前推荐版本号」的页面本身，不提供完整性凭据；期望值仍走 nodejs.org",
    ),
}


def _src_http_literals() -> dict[str, set[str]]:
    # 返回 {模块文件名: 该模块内出现的 http(s) 字面量集合}。f-string 的常量段
    # （如 f"https://fyhub.cn/FFmpeg/latest/{base}"）在 AST 里就是 ast.Constant，一并收进来。
    root = Path(__file__).resolve().parents[1] / "src"
    found: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        urls = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and (node.value.startswith("http://") or node.value.startswith("https://"))
        }
        if urls:
            found[path.name] = urls
    return found


def _host_of(url: str) -> str | None:
    return urlsplit(url).hostname


def _modules_holding_whitelisted_hosts(literals: dict[str, set[str]]) -> set[str]:
    hosts = set(DOWNLOAD_SOURCES)
    return {
        module for module, urls in literals.items() if any((host := _host_of(url)) and host in hosts for url in urls)
    }


class TestDownloadSourceWhitelist:
    def test_scan_actually_sees_the_sources_it_claims(self) -> None:
        # 反向见证（防空扫描）：本锁的全部威力建立在「真的扫到了这些常量」上。
        # 扫描根为空 / 只扫到一个文件，都会让它「绿着什么都没查」——AGENTS.md MID-68 同族形态。
        literals = _src_http_literals()
        assert (
            _modules_holding_whitelisted_hosts(literals) == _download_module_files()
        ), f"下载源注册表与实际持有下载 URL 的模块不一致：{sorted(literals)}"
        assert ZIP_URL in literals["ffmpeg_install.py"], "扫描没看到官方源 URL（锁将形同虚设）"
        assert any("fyhub.cn" in u for urls in literals.values() for u in urls), "扫描漏了镜像源，锁即失效"

    def test_every_url_in_a_download_module_is_whitelisted(self) -> None:
        offenders: dict[str, list[str]] = {}
        for module, urls in _src_http_literals().items():
            if module not in _download_module_files():
                continue
            bad = sorted(u for u in urls if (_host_of(u) or "") not in DOWNLOAD_SOURCES)
            if bad:
                offenders[module] = bad
        assert not offenders, f"下载模块里出现未登记进 DOWNLOAD_SOURCES 的出站常量：{offenders}"

    def test_no_other_module_reaches_a_download_host(self) -> None:
        # 「新增一条源」无法只改一处：任何未注册模块只要引用了下载宿主（含复制粘贴一条 URL）
        # 即在此变红，逼作者把它登记进 DOWNLOAD_MODULES + 走一遍哨兵。
        offenders = sorted(_modules_holding_whitelisted_hosts(_src_http_literals()) - _download_module_files())
        assert not offenders, f"未注册模块持有下载源 URL：{offenders}"

    def test_each_source_declares_a_known_integrity_method(self) -> None:
        for host, (method, note) in DOWNLOAD_SOURCES.items():
            assert method in INTEGRITY_METHODS, f"{host} 的完整性方式 {method!r} 不在取值域内"
            assert note.strip(), f"{host} 缺说明：白名单要写清「为什么这一档可接受」"

    def test_tofu_sources_are_all_gated_off_by_default(self) -> None:
        # 白名单不是记账本：凡完整性方式为 TOFU 的源，都必须有默认关闭的开关兜着
        # （AGENTS.md ②：把 TOFU 当默认路径等于最危险的首次安装没有任何校验）。
        source = (Path(__file__).resolve().parents[1] / "src" / "ffmpeg_install.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_master_source_allowed")
        # 开关名在实现里是**模块常量引用**（`os.environ.get(_FFMPEG_MASTER_ENV)`）而非字面量，
        # 故按 Name 判定；再单独断言该常量的值，两侧合起来才等价于「读取点与登记的开关名不脱节」。
        assert any(
            isinstance(node, ast.Name) and node.id == "_FFMPEG_MASTER_ENV" for node in ast.walk(fn)
        ), "开关名与 env 读取点脱节"
        assert ffmpeg_install._FFMPEG_MASTER_ENV == "FFMPEG_MASTER_ALLOWED", "对外承诺的开关变量名不得改动"
        parse_call = next(
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "parse_config_bool"
        )
        # 第二个实参 = 「未设置时的默认值」，必须是字面 False；写成 True 即把红线放开。
        assert isinstance(parse_call.args[1], ast.Constant) and parse_call.args[1].value is False
        tofu_hosts = {h for h, (m, _n) in DOWNLOAD_SOURCES.items() if m == "TOFU"}
        assert tofu_hosts == {
            "github.com",
            "fyhub.cn",
        }, f"TOFU 源集合变化，须复核默认关闭的开关是否覆盖：{sorted(tofu_hosts)}"

    def test_api_github_com_is_registered_as_official_hash(self) -> None:
        assert DOWNLOAD_SOURCES["api.github.com"][0] == "官方哈希"
        assert DOWNLOAD_SOURCES["api.github.com"][1].strip(), "白名单要写清「为什么这一档可接受」"
        assert "src.ffmpeg_linux_download" in DOWNLOAD_MODULES
        # TOFU 源集合不得因本次改动扩大或缩小：github.com 的 master-latest 路径仍是默认关闭的 TOFU。
        assert {h for h, (m, _n) in DOWNLOAD_SOURCES.items() if m == "TOFU"} == {"github.com", "fyhub.cn"}


class TestInstallFfmpegMac:
    def test_brew_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({}, calls))
        assert ffmpeg_install.install_ffmpeg_mac() is True
        assert calls == ["brew install ffmpeg"]

    def test_brew_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({("brew", "install", "ffmpeg"): 1}, calls))
        assert ffmpeg_install.install_ffmpeg_mac() is False

    def test_called_process_error_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*a: object, **k: object) -> None:
            raise subprocess.CalledProcessError(1, ["brew"])

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.install_ffmpeg_mac() is False

    def test_unexpected_error_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*a: object, **k: object) -> None:
            raise ValueError("nope")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.install_ffmpeg_mac() is False


class TestLinuxExtraBranches:
    # 上方原有类 TestLinuxPackageFallback 已锁住「yum 失败仍试 apt」；本类补它没走到
    # 的四条旁支：yum 探测抛非 FileNotFoundError、apt update 失败、apt 不存在、
    # apt 安装本身失败。这四条共同决成「请手动安装」的文案，走错一条就是直接放弃。
    def test_yum_probe_crash_keeps_rhs_semantics(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # yum 探测抛非 FileNotFoundError 时 is_RHS 保持 True（不再试 apt）——既有语义，
        # 用例钉住它，避免后续「顺手改成回退」造成行为漂移。
        state: dict[str, int] = {"n": 0}

        def fake_run(cmd: list[str], *a: object, **k: object) -> Any:
            state["n"] += 1
            if cmd[0] == "yum":
                raise ValueError("yum blew up")
            return types.SimpleNamespace(returncode=0, stderr=b"")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = fake_run
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.install_ffmpeg_linux() is False
        assert state["n"] == 1

    def test_apt_update_failure_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        shim = _proc_shim({("yum", "install", "-y", "ffmpeg"): 1, ("apt", "update"): 1}, calls)
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.install_ffmpeg_linux() is False
        assert calls == ["yum install -y ffmpeg", "apt update"]

    def test_apt_missing_binary_reports_manual_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def fake_run(cmd: list[str], *a: object, **k: object) -> Any:
            calls.append(" ".join(cmd))
            if cmd[0] == "apt":
                raise FileNotFoundError("apt")
            return types.SimpleNamespace(returncode=1, stderr=b"")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = fake_run
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.install_ffmpeg_linux() is False
        assert calls == ["yum install -y ffmpeg", "apt update"]

    def test_apt_probe_crash_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def fake_run(cmd: list[str], *a: object, **k: object) -> Any:
            calls.append(" ".join(cmd))
            if cmd[0] == "apt":
                raise ValueError("apt blew up")
            return types.SimpleNamespace(returncode=1, stderr=b"")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = fake_run
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.install_ffmpeg_linux() is False

    def test_apt_install_failure_logs_stderr_and_gives_up(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        shim = _proc_shim({("yum", "install", "-y", "ffmpeg"): 1, ("apt", "install", "-y", "ffmpeg"): 1}, calls)
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.install_ffmpeg_linux() is False
        assert calls == ["yum install -y ffmpeg", "apt update", "apt install -y ffmpeg"]


# 直下兜底的接线锁（2026-10-02 Linux arm64 支持，Task 4 Step 1；fix round 2 补到六条）：
# install_ffmpeg_linux() 在「yum、apt 两条包管理器路径都试过且都没装上」之后、给出「请手动安装」
# 提示之前，必须触达官方月末构建直下（src.ffmpeg_linux_download.install_ffmpeg_linux_native）。
# 逐条判据（不得笼统读成「四条都要恰好一次」——① 要求的恰恰是 0 次触达）：
#   ① test_package_manager_success_skips_native_download：包管理器已成功 → 触达即回归（优先级锁）。
#   ② test_both_package_managers_missing_falls_back_exactly_once：两条都不存在 → 恰好一次 + 实参逐项。
#   ③ test_native_failure_still_ends_with_manual_hint：apt update 失败 + 兜底返假 → 恰好一次 + 有手动提示。
#   ④ test_native_reached_when_apt_install_fails_reports_false：apt install 失败 + 兜底返假 → 恰好一次。
#   ⑤ test_master_switch_on_is_passed_to_native_fallback：开关取真 → master_allowed=True 传到兜底。
#   ⑥ test_apt_update_failure_fallback_success_skips_manual_hint：update 失败 + 兜底返真 → 恰好一次、
#      整体 True、且**不得**打印手动安装提示。
# 按 M-26 一律写「谁被调用、传了什么」的行为锁：顺序判据取 calls 记录的真实调用次序，
# 不用正则扫源码字面量（契约一改名，文本锁就静默空洞成立）。
# [历史注] 本类初版（Unit B 首轮）只有四条，其中 ③ 按 brief 的实参形态（apt update 非零）
# 对「接线存在与否」零敏感——当时实现里该分支在 apt 块内就 `return False` 早退、根本到不了兜底。
# 2026-10-02 R-11 删除该早退后：③ 改判据成真锁，并新增 ⑤（开关传递）与 ⑥（update 失败支的成功侧）。
class TestInstallFfmpegLinuxNativeFallback:
    def test_package_manager_success_skips_native_download(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # apt/yum 天然给原生 arch 且带发行版自己的签名链，直下只是「拿不到包管理器」时的兜底，
        # 优先级不得颠倒：包管理器已成功时触达直下即视为回归。
        calls: list[str] = []
        # yum 一步返回 0 → _proc_shim 默认码即 0，无需枚举；断言看的是「有没有第二次调用」。
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({}, calls))
        monkeypatch.setattr(
            ffmpeg_install,
            "install_ffmpeg_linux_native",
            lambda *args, **kwargs: pytest.fail("包管理器已成功，不得触达直下路径"),
        )
        assert ffmpeg_install.install_ffmpeg_linux() is True
        assert calls == ["yum install -y ffmpeg"]

    def test_both_package_managers_missing_falls_back_exactly_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[dict[str, Any]] = []
        calls: list[str] = []

        def _native(dest_dir: str, arch: str | None = None, *, master_allowed: bool = False) -> bool:
            seen.append({"dest_dir": dest_dir, "arch": arch, "master_allowed": master_allowed})
            return True

        def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> Any:
            calls.append(" ".join(cmd))
            # 既无 yum 也无 apt（轻量发行版/容器的真实形态）：两条包管理器路径都以 FileNotFoundError 收场。
            raise FileNotFoundError(cmd[0])

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = fake_run
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_linux_native", _native)
        monkeypatch.delenv("FFMPEG_MASTER_ALLOWED", raising=False)
        assert ffmpeg_install.install_ffmpeg_linux() is True
        assert calls == ["yum install -y ffmpeg", "apt update"]
        assert len(seen) == 1, f"直下兜底必须恰好触达一次：{seen}"
        assert seen[0]["dest_dir"] == ffmpeg_install.execute_dir
        # arch 一律不传：分流由新模块自己的 _linux_arch()（platform.machine()）负责，调用方传死 arch
        # （如 linux64）会把 aarch64 机器钉在 x86_64 构建上，故「没传」本身要有锁。
        assert seen[0]["arch"] is None
        # 开关默认关：master_allowed 必须原样是 False，而不是新模块自己去读环境变量。
        assert seen[0]["master_allowed"] is False

    def test_native_failure_still_ends_with_manual_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 实参形态＝「yum 非零 + apt update 非零」（无 root 的 Debian/Ubuntu 常态：update 要写
        # /var/lib/apt/lists）。R-11 前本条只断 `is False`，对「接线存在与否」零敏感（当时该分支
        # 在 apt 块内就 return False 早退，压根到不了兜底）；早退删除后本条改判据成真锁：
        # 兜底恰好触达一次 + 兜底返假时手动安装提示确实打印出来。
        # [历史注] brief 原文那句「apt update 也要给非零，否则永远走不到兜底」与当时的实现正好相反
        # （非零正是走不到的原因），2026-10-02 按「被证伪的事实陈述改正原文」口径移除。
        seen: list[str] = []
        calls: list[str] = []
        errors: list[str] = []

        def _native(dest_dir: str, arch: str | None = None, *, master_allowed: bool = False) -> bool:
            seen.append(dest_dir)
            return False

        shim = _proc_shim({("yum", "install", "-y", "ffmpeg"): 1, ("apt", "update"): 1}, calls)
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_linux_native", _native)
        monkeypatch.setattr(ffmpeg_install.logger, "error", lambda msg, *a, **k: errors.append(str(msg)))
        assert ffmpeg_install.install_ffmpeg_linux() is False
        # update 失败后不白跑 apt install（既有取舍保留），但必须落到函数末尾的统一出口。
        assert calls == ["yum install -y ffmpeg", "apt update"]
        assert len(seen) == 1, f"apt update 失败时兜底须恰好触达一次：{seen}"
        hint = " ".join(errors)
        assert "Manual installation of ffmpeg is required" in hint, f"兜底返假后必须给出手动安装提示：{hint}"

    def test_native_reached_when_apt_install_fails_reports_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 与上一条同族但失败点后移一格：apt update 成功、apt install 装不上（发行版仓库里没有
        # ffmpeg 的常态）。两支各自独立抵达统一出口，缺任何一支都会让「apt 这条路白跑」重新出现。
        seen: list[dict[str, Any]] = []
        calls: list[str] = []

        def _native(dest_dir: str, arch: str | None = None, *, master_allowed: bool = False) -> bool:
            seen.append({"dest_dir": dest_dir, "arch": arch, "master_allowed": master_allowed})
            return False

        shim = _proc_shim({("yum", "install", "-y", "ffmpeg"): 1, ("apt", "install", "-y", "ffmpeg"): 1}, calls)
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_linux_native", _native)
        assert ffmpeg_install.install_ffmpeg_linux() is False
        assert calls == ["yum install -y ffmpeg", "apt update", "apt install -y ffmpeg"]
        assert len(seen) == 1, f"apt 装不上时兜底须恰好触达一次：{seen}"
        # 收集了就断言：只断 len(seen) 会让「传错实参」这一半无人看守。
        assert seen[0]["dest_dir"] == ffmpeg_install.execute_dir
        assert seen[0]["arch"] is None
        assert seen[0]["master_allowed"] is False

    def test_master_switch_on_is_passed_to_native_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 开关传递锁（Linux 接线面与 Windows 侧 TestMasterSourceGate 的 setenv 锁同等待遇）：
        # FFMPEG_MASTER_ALLOWED 取真时调用方必须把 master_allowed=True 原样传下去。把接线调用点的
        # `master_allowed=_master_source_allowed()` 写成字面 False 或漏传该关键字，本条即红——否则
        # 「取不到官方哈希 → TOFU 降级」那一档在 Linux 上永久不可达，开关形同虚设且零可见证据
        # （也顺带证明开关真读到了环境，不是「读不到但静默当 False」）。
        seen: list[bool] = []
        calls: list[str] = []

        def _native(dest_dir: str, arch: str | None = None, *, master_allowed: bool = False) -> bool:
            seen.append(master_allowed)
            return False

        shim = _proc_shim({("yum", "install", "-y", "ffmpeg"): 1, ("apt", "install", "-y", "ffmpeg"): 1}, calls)
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_linux_native", _native)
        monkeypatch.setenv(ffmpeg_install._FFMPEG_MASTER_ENV, "1")
        assert ffmpeg_install.install_ffmpeg_linux() is False
        assert len(seen) == 1, f"兜底须恰好触达一次：{seen}"
        assert seen[0] is True, f"{ffmpeg_install._FFMPEG_MASTER_ENV} 取真时 master_allowed 必须传成 True"

    def test_apt_update_failure_fallback_success_skips_manual_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # ③ 的另一侧（同一实参形态、只在兜底返回值上分叉）：apt update 失败 → 兜底恰触达一次 →
        # 兜底成功即整体 True，且**不得**再打印手动安装提示（否则「装了却又叫用户自己装」）。
        # 这一支正是 R-11 闭合的目标人群：非 root 的 Debian/Ubuntu arm64 上 update 失败是常态。
        seen: list[dict[str, Any]] = []
        calls: list[str] = []
        errors: list[str] = []

        def _native(dest_dir: str, arch: str | None = None, *, master_allowed: bool = False) -> bool:
            seen.append({"dest_dir": dest_dir, "arch": arch, "master_allowed": master_allowed})
            return True

        shim = _proc_shim({("yum", "install", "-y", "ffmpeg"): 1, ("apt", "update"): 1}, calls)
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_linux_native", _native)
        monkeypatch.setattr(ffmpeg_install.logger, "error", lambda msg, *a, **k: errors.append(str(msg)))
        assert ffmpeg_install.install_ffmpeg_linux() is True
        assert len(seen) == 1, f"apt update 失败时兜底须恰好触达一次：{seen}"
        assert seen[0]["dest_dir"] == ffmpeg_install.execute_dir
        hint = " ".join(errors)
        assert "Manual installation of ffmpeg is required" not in hint, f"兜底成功不得再给手动提示：{hint}"


class TestPlatformDispatch:
    @pytest.mark.parametrize(
        "platform_name,attr,expected",
        [
            ("Windows", "install_ffmpeg_windows", True),
            ("Linux", "install_ffmpeg_linux", False),
            ("Darwin", "install_ffmpeg_mac", True),
        ],
    )
    def test_routes_to_platform_installer(
        self, monkeypatch: pytest.MonkeyPatch, platform_name: str, attr: str, expected: bool
    ) -> None:
        monkeypatch.setattr(ffmpeg_install, "current_platform", platform_name)
        monkeypatch.setattr(ffmpeg_install, attr, lambda: expected)
        assert ffmpeg_install.install_ffmpeg() is expected

    def test_unknown_platform_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ffmpeg_install, "current_platform", "FreeBSD")
        assert ffmpeg_install.install_ffmpeg() is False


class TestCheckFfmpegInstalled:
    def test_ok_when_rc_zero_and_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({}, calls))
        assert ffmpeg_install.check_ffmpeg_installed() is True

    def test_rc_zero_with_empty_stdout_is_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Empty:
            returncode = 0
            stdout = b"  "

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = lambda *a, **k: _Empty()
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.check_ffmpeg_installed() is False

    def test_nonzero_rc_is_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({("ffmpeg", "-version"): 1}, calls))
        assert ffmpeg_install.check_ffmpeg_installed() is False

    def test_missing_binary_silently_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*a: object, **k: object) -> None:
            raise FileNotFoundError("ffmpeg")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.check_ffmpeg_installed() is False

    def test_timeout_is_treated_as_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*a: object, **k: object) -> None:
            raise subprocess.TimeoutExpired(["ffmpeg", "-version"], 15)

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.check_ffmpeg_installed() is False

    def test_oserror_prompts_delete_and_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*a: object, **k: object) -> None:
            raise OSError("bad exe")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.check_ffmpeg_installed() is False

    def test_unexpected_exception_is_logged_and_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*a: object, **k: object) -> None:
            raise ValueError("weird")

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = boom
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        assert ffmpeg_install.check_ffmpeg_installed() is False


class TestCheckFfmpegEntry:
    def test_already_installed_short_circuits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ffmpeg_install, "check_ffmpeg_installed", lambda: True)
        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg", lambda: False)
        assert ffmpeg_install.check_ffmpeg() is True

    def test_not_installed_triggers_install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ffmpeg_install, "check_ffmpeg_installed", lambda: False)
        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg", lambda: True)
        assert ffmpeg_install.check_ffmpeg() is True


# ==========================================================================
# 2026-09-22 P-1：官方公布哈希优先校验（TOFU 降级为兜底）
# ==========================================================================

# 官方文档正文（gyan.dev 的 ffmpeg-release-essentials.zip.sha256 实测形态：裸 64 位小写十六进制）。
# 取值刻意写成模块级字面量而不是现场 hashlib.sha256(...) 算出来：否则「解析器把任意输入
# 当成合法摘要」这类缺陷会被自实现的等价计算掩盖（本仓「测试不得自实现被测逻辑」口径）。
OFFICIAL_SHA = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"
# 与上面同一形态、但内容不同的第二个值：用于构造「官方期望值 ≠ 本地实算值」的篡改分支。
OFFICIAL_SHA_OTHER = "a" * 63 + "b"
ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DOC_URL = ZIP_URL + ".sha256"


def _doc_and_zip_requests(
    *, doc_text: str | None = None, doc_status: int = 200, payload: bytes = b""
) -> tuple[Any, list[str]]:
    # 按 URL 派发的 requests 替身：官方哈希文档与 zip 各回各的响应，
    # 未登记的 URL 一律抛错——这样「多发了一个请求 / 发错宿主」都会立刻显形，
    # 而不是静默走通（真实网络在测试里必须完全不可达）。
    calls: list[str] = []

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _Resp:
        calls.append(url)
        if url == DOC_URL:
            return _Resp(status_code=doc_status, text=doc_text if doc_text is not None else "")
        if url == ZIP_URL:
            return _Resp(content=payload, headers={"Content-Length": str(len(payload))})
        raise AssertionError(f"测试桩未登记的请求 URL: {url}")

    return types.SimpleNamespace(get=fake_get, RequestException=requests.RequestException), calls


class TestOfficialSha256DocParsing:
    # 解析判据必须严格：gyan.dev 前置 WAF/代理会回 200 + HTML，宽松判定会把挑战页
    # 当成期望哈希，从而把**正常**构建判成篡改（比无校验更糟——它拒绝安装）。
    def test_known_hash_official_doc_body_is_parsed_verbatim(self) -> None:
        assert ffmpeg_install._parse_official_sha256(OFFICIAL_SHA) == OFFICIAL_SHA

    @pytest.mark.parametrize("wrapping", ["  \n", "\r\n", "\t"])
    def test_surrounding_whitespace_is_tolerated(self, wrapping: str) -> None:
        # 只有首尾空白可容忍：文档实际带尾换行，剥掉它才比得上
        assert ffmpeg_install._parse_official_sha256(wrapping + OFFICIAL_SHA + wrapping) == OFFICIAL_SHA

    def test_uppercase_is_normalized(self) -> None:
        assert ffmpeg_install._parse_official_sha256(OFFICIAL_SHA.upper()) == OFFICIAL_SHA

    @pytest.mark.parametrize(
        "body",
        [
            "",
            "not-a-hash",
            "<html><body>Just a moment...</body></html>",
            OFFICIAL_SHA[:63],  # 截断
            OFFICIAL_SHA + "  ffmpeg-release-essentials.zip",  # 带文件名（那是 node 侧形态）
            "g" * 64,  # 合法长度但非十六进制
        ],
    )
    def test_non_conforming_bodies_return_empty(self, body: str) -> None:
        assert ffmpeg_install._parse_official_sha256(body) == ""


class TestFetchOfficialSha256:
    def test_get_is_used_and_redirects_are_not_disabled(self) -> None:
        # 2026-09-22 实测：<zip>.sha256 回 **303** 跳到 /builds/packages/ffmpeg-<ver>-essentials_build.zip.sha256，
        # 跟着跳才有 200 + 裸摘要。改成 requests.head、或显式 allow_redirects=False，
        # 都会拿到空正文 → 永久静默降级成 TOFU，且日志只说「未取得文档」，极易误判成上游故障。
        source = (Path(__file__).resolve().parents[1] / "src" / "ffmpeg_install.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_fetch_official_sha256"
        )
        # 逐个显式 isinstance 收窄，而不是在推导式里过滤后再取 .attr：
        # 推导式的过滤器不把类型传播到下一个推导式（ast.Call.func 的声明类型是 expr），
        # 换成 filter 写法会被 basedpyright 打成 reportAttributeAccessIssue。
        http_calls: list[tuple[str, set[str | None]]] = []
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"get", "head", "request"}:
                continue
            http_calls.append((node.func.attr, {kw.arg for kw in node.keywords}))
        assert http_calls, "_fetch_official_sha256 不再发起 HTTP 请求"
        assert all(name == "get" for name, _kw in http_calls), "取文档必须用 GET（HEAD 拿不到正文）"
        for _name, kwargs in http_calls:
            assert "allow_redirects" not in kwargs, "不得改动重定向策略：官方文档经 303 跳转才到 200"

    def test_network_error_returns_empty_and_logs_masked_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 「取不到」必须是返回值层面的信号（空串），绝不向上抛——一次可选加固不得打断安装。
        captured: list[str] = []
        monkeypatch.setattr(ffmpeg_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))

        def boom(*args: Any, **kwargs: Any) -> None:
            raise requests.ConnectionError("dns fail")

        monkeypatch.setattr(
            ffmpeg_install, "requests", types.SimpleNamespace(get=boom, RequestException=requests.RequestException)
        )
        assert ffmpeg_install._fetch_official_sha256("https://user:pw@www.gyan.dev/x.zip.sha256") == ""
        joined = "\n".join(captured)
        # AGENTS.md 硬要求：异常日志带 type_name，且 URL 必须脱敏（凭据不得进日志）
        assert "ConnectionError" in joined
        assert "user:pw" not in joined and "pw@" not in joined

    def test_non_200_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            ffmpeg_install,
            "requests",
            types.SimpleNamespace(
                get=lambda *a, **k: _Resp(status_code=404, text=""), RequestException=requests.RequestException
            ),
        )
        assert ffmpeg_install._fetch_official_sha256(DOC_URL) == ""

    def test_html_body_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            ffmpeg_install,
            "requests",
            types.SimpleNamespace(
                get=lambda *a, **k: _Resp(text="<html>challenge</html>"), RequestException=requests.RequestException
            ),
        )
        assert ffmpeg_install._fetch_official_sha256(DOC_URL) == ""


class TestAuthoritativeVsTofu:
    # 权威分支与 TOFU 分支的优先级：这是 P-1 的核心，也是最容易被「顺手写成 or」弱化的地方。
    def test_authoritative_match_passes_even_against_stale_sidecar(self, tmp_path: Path) -> None:
        # 旧旁路基准记着上一个构建的哈希：官方文档已确认本次构建 → 必须放行。
        # 若实现让旁路基准拥有否决权，MID-59 的「版本轮转即永久拒装」在此复现。
        zip_path = _write_zip(tmp_path, ZIP_A)
        sidecar = zip_path.parent / ffmpeg_install._hash_file_name("b" * 12)
        sidecar.write_text("0" * 64, encoding="ascii")
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, "b" * 12, _sha256(ZIP_A)) is True

    def test_authoritative_mismatch_refuses_without_falling_back_to_tofu(self, tmp_path: Path) -> None:
        # 「拿到官方期望值且不符」= 硬拒。降级到 TOFU（首次信任）会把这次篡改记成新基准，
        # 于是攻击者只要制造一次「官方文档与产物不一致」就自动完成洗白——绝不允许。
        zip_path = _write_zip(tmp_path, ZIP_A)
        build_id = "d" * 12
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, build_id, OFFICIAL_SHA_OTHER) is False
        assert not (zip_path.parent / ffmpeg_install._hash_file_name(build_id)).exists()

    def test_missing_official_hash_keeps_tofu_and_warns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 取不到官方文档 → 保留原 TOFU 行为，但必须留下可发现的降级告警。
        captured: list[str] = []
        monkeypatch.setattr(ffmpeg_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))
        zip_path = _write_zip(tmp_path, ZIP_A)
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, "e" * 12, "") is True
        joined = "\n".join(captured)
        assert "TOFU" in joined or "首次信任" in joined
        assert (zip_path.parent / ffmpeg_install._hash_file_name("e" * 12)).is_file()

    def test_tofu_refusal_still_works_when_official_doc_unavailable(self, tmp_path: Path) -> None:
        # 降级不等于放松：同一构建标识下内容漂移仍须硬拒（原有 MID-59 防线不得回退）。
        zip_path = _write_zip(tmp_path, ZIP_A)
        build_id = "f" * 12
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, build_id, "") is True
        zip_path.write_bytes(ZIP_B)
        assert ffmpeg_install._check_or_record_zip_sha256(zip_path, build_id, "") is False


class TestOfficialDownloadAuthorityWiring:
    # 从 download_ffmpeg_official 整链验证「期望值来自上游文档」这一事实，
    # 而不只是单元级传参——防的是「取了文档但没参与判定」这类半截实现。
    def test_doc_url_is_zip_url_plus_suffix(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _zip_with_bin()
        stub, calls = _doc_and_zip_requests(doc_text=_sha256(payload), payload=payload)
        monkeypatch.setattr(ffmpeg_install, "requests", stub)
        proc_calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({("ffmpeg", "-version"): 0}, proc_calls))
        assert ffmpeg_install.download_ffmpeg_official(ZIP_URL, str(win_env)) is True
        # 官方哈希文档必须真的被请求，且宿主仍是 gyan.dev（不是第三方镜像自证）
        assert calls[0] == DOC_URL
        assert calls[1] == ZIP_URL

    def test_tampered_payload_is_refused_and_deleted(self, win_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _zip_with_bin()
        stub, _calls = _doc_and_zip_requests(doc_text=OFFICIAL_SHA_OTHER, payload=payload)
        monkeypatch.setattr(ffmpeg_install, "requests", stub)
        proc_calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({}, proc_calls))
        assert ffmpeg_install.download_ffmpeg_official(ZIP_URL, str(win_env)) is False
        # 拒绝的三条硬要求：坏包删掉、不执行、不把被篡改的哈希写成基准
        assert not (win_env / "ffmpeg_official_temp.zip").exists()
        assert proc_calls == []
        assert not list(win_env.glob(f"_ffmpeg_official*{ffmpeg_install._HASH_SUFFIX}"))

    def test_unreachable_doc_degrades_to_tofu_but_still_installs(
        self, win_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 上游文档 404（离线 / 站点故障）时安装仍须成功——否则 P-1 就把 MID-59
        # 从「永久死路」改成了「文档一挂就全挂」，比不改更糟。
        payload = _zip_with_bin()
        stub, _calls = _doc_and_zip_requests(doc_status=404, payload=payload)
        monkeypatch.setattr(ffmpeg_install, "requests", stub)
        captured: list[str] = []
        monkeypatch.setattr(ffmpeg_install.logger, "warning", lambda msg, *a, **k: captured.append(str(msg)))
        proc_calls: list[str] = []
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({("ffmpeg", "-version"): 0}, proc_calls))
        assert ffmpeg_install.download_ffmpeg_official(ZIP_URL, str(win_env)) is True
        assert any("TOFU" in m or "首次信任" in m for m in captured), "降级必须写进日志（不得静默）"
