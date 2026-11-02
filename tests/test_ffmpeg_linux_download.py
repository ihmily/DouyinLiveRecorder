# tests/test_ffmpeg_linux_download.py —— src/ffmpeg_linux_download.py 的回归锁。
#
# 组织方式：按「删掉哪条判据就该变红」分组（分流 / URL 反解 / 真值表 / 失败不抛 / 两处副本一致性），
#   另含评审 I-1/I-3/I-4 补齐的分组：载荷形态、归档形态闸门、TOFU 基准比对（含基准读不出）、
#   归档取件布局与缺件、_download 重试与退避、安装后验证探针的三态（抛异常 / 零字节空壳）。
# 2026-10-21 评审包追加：独占落盘（M-44）、PATH 去重前置（M-47）、解包前空间预检（M-48）、
#   下载字节上限（M-49）——段末 TestExclusiveArchiveSink / TestPathInjectionAndSpacePrecheck /
#   TestDownloadByteCap 三组，判据同样全部落在「现场还剩什么」。
# 全部离线：requests / subprocess / 落盘目录三面被打桩或收敛到 tmp_path，
#   绝不真下 ~110MB 产物，也不写程序目录（AGENTS.md「测试产物一律走 tmp_path」）。
# 替身口径：stdlib 与第三方模块一律走**被测模块命名空间的 shim**
#   （types.SimpleNamespace(**vars(真身)) 浅拷贝后只覆盖所需属性，再 monkeypatch.setattr(fld, ...)）；
#   直接 monkeypatch.setattr(fld.platform, "machine", ...) 改的是全进程 platform 本体，
#   窗口内其它模块（loguru / 后台线程）的 machine() 调用一并被换——AGENTS.md M-27 明令禁止该形态。

import hashlib
import io
import json
import os
import platform
import stat
import subprocess
import tarfile
import time
import types
from pathlib import Path
from typing import Any

import pytest
import requests

import src.ffmpeg_linux_download as fld
from build_exe import _FFMPEG_DOWNLOAD_URLS as BUILD_EXE_FFMPEG_URLS

# 两条 URL 一律从被测模块的表里取，**不在本文件复述字面量**：分流/反解用例的锚点必须是「表本身」，
# 否则改表不改测试就会造出一条假绿的平行副本。URL 与发布链的一致性另有专门一条锁
# （TestUrlParityWithBuildExe），它反过来钉的是「两份物理副本不得漂移」。
LINUX64_URL = fld._LINUX_FFMPEG_URLS["linux64"]
LINUXARM64_URL = fld._LINUX_FFMPEG_URLS["linuxarm64"]


def _platform_shim(machine: str) -> Any:
    # 浅拷贝 platform 本体后只换 machine()：其余属性（python_version 等）仍是真身，
    # 用例窗口内别的模块调用它们拿到的还是真实值。
    shim = types.SimpleNamespace(**vars(platform))
    shim.machine = lambda: machine
    return shim


class TestArchSelection:
    @pytest.mark.parametrize(
        ("machine", "expected"),
        [
            ("aarch64", "linuxarm64"),
            ("arm64", "linuxarm64"),
            ("x86_64", "linux64"),
            ("AMD64", "linux64"),
            ("", "linux64"),
            ("riscv64", "linux64"),
        ],
    )
    def test_unknown_arch_falls_back_to_linux64(
        self, monkeypatch: pytest.MonkeyPatch, machine: str, expected: str
    ) -> None:
        # 六格矩阵的来源：arm64/aarch64 两个真 ARM 形态、x86_64/AMD64 两个真 x64 形态（Linux 与
        # Windows 各自的大小写习惯）、空串（machine() 取不到值）与 riscv64（本模块没打算支持的架构）。
        # 后两格判成 linux64 是**刻意的保守回落**：架构信息不可信时宁可装大概率能跑的那份。
        monkeypatch.setattr(fld, "platform", _platform_shim(machine))
        assert fld._linux_arch() == expected

    def test_asset_url_is_registered_for_both_arches(self) -> None:
        assert fld._asset_url("linuxarm64") == LINUXARM64_URL
        assert fld._asset_url("linux64") == LINUX64_URL
        # 陌生 arch 必须抛而不是回落：静默回落 = 给 aarch64 机器装 x86_64 二进制还不吭声。
        with pytest.raises(KeyError):
            fld._asset_url("s390x")


class TestApiUrlDerivation:
    def test_api_url_is_derived_from_asset_url(self) -> None:
        api = fld._api_release_url(LINUXARM64_URL)
        assert api == "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27"
        assert fld._asset_name(LINUXARM64_URL) == "ffmpeg-n9.0.1-11-ge47273f4d9-linuxarm64-gpl-9.0.tar.xz"

    def test_unparsable_url_yields_empty_api(self) -> None:
        # 含 http（非 https）与陌生域：绝不带着猜想的 API URL 出站。
        for bad in ("", "https://example.com/x.tar.xz", "http://github.com/a/b/releases/download/t/n.tar.xz"):
            assert fld._api_release_url(bad) == ""


def _tar_xz(members: dict[str, bytes], *, mode: int = 0o755) -> bytes:
    # 必须是真 tar.xz：fld 走 tarfile.is_tarfile + extractall(filter="data")，多层 mock 锁不住实现换法。
    # mode 可配（评审 I-1②/⑤）：既要造 0o755 的正常件，也要造 0o644 的件——后者才能钉住
    # 「执行位由实现补回」这条判据（默认 0o755 与既有五格载荷保持逐字同形，不改动已绿用例）。
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = mode
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _digest_resp(digest: str | None) -> Any:
    # digest=None → 模拟 API 不可达（403 限流是本模块降级分支最常见的真实成因）。
    payload = {"assets": [{"name": fld._asset_name(LINUXARM64_URL), "digest": f"sha256:{digest}"}]}

    class _Resp:
        status_code = 200 if digest is not None else 403
        encoding = "utf-8"

        @staticmethod
        def json() -> dict[str, Any]:
            # asset 名必须经 fld._asset_name 现取、不得手写常量：被测实现拿 URL basename 比对 name，
            # 测试里另抄一份名字就会变成「名字对不上 → 恒回 ""」的同源假绿。
            return payload

        @staticmethod
        def iter_content(chunk_size: int) -> Any:
            # M-12：生产读取改走「限长分块」（_read_small_document_capped），替身同步提供分块形态：
            # 单块交出全部字节（≤ 上限的常规形态；超限形态由 TestApiDocCap 另钉）。
            return iter([json.dumps(payload).encode("utf-8")])

    return _Resp()


class _FakeDownload:
    # 真身替身只覆盖 fld 模块自己的 requests 名字（绝不动 stdlib/第三方本体），
    # 且按 URL 前缀分流：api.github.com → digest 响应；github.com → 产物字节流。
    # 两个可选实参把「HTTP 错误」与「写盘/读取中途 OSError」注入到真实下载链里（评审 I-3 补的覆盖面），
    # 默认 None 时与既有五格真值表逐字同形。
    def __init__(
        self,
        body: bytes,
        *,
        raise_on_status: Exception | None = None,
        raise_while_streaming: Exception | None = None,
    ) -> None:
        self._body = body
        self._raise_on_status = raise_on_status
        self._raise_while_streaming = raise_while_streaming
        self.status_code = 200

    def raise_for_status(self) -> None:
        if self._raise_on_status is not None:
            raise self._raise_on_status
        return None

    def iter_content(self, chunk_size: int = 1) -> Any:
        # 必须真按 chunk_size 切片：被测实现用 64KB 分块写盘，一次吐出整块就锁不住
        # 「分块写出 + 空块跳过」那条内存恒定的形态。
        remaining = self._body
        while remaining:
            chunk, remaining = remaining[:chunk_size], remaining[chunk_size:]
            yield chunk
            if self._raise_while_streaming is not None:
                # 在**已经写出至少一块之后**才抛：这样被测实现才会看到「归档已存在但是半截的」，
                # 从而真正走到 except (RequestException, OSError) 里的 archive.unlink() 一支。
                raise self._raise_while_streaming

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *a: Any) -> None:
        return None


def _requests_shim(get_fn: Any) -> Any:
    # 评审 I-3：requests 替身必须是**真身浅拷贝 shim**，不得手写只挂 exceptions/RequestException/get
    # 的类。手写类缺 HTTPError，被测 _download 在解析 `except requests.HTTPError` 这一步就抛
    # AttributeError，于是重试循环、退避、半截归档 unlink、(RequestException, OSError) 分支
    # 整段 37 行一次都没执行过（覆盖率 282-318 全 miss 就是这么来的）。
    # shim 保留真身的 exceptions/RequestException/HTTPError 等全部属性，只覆盖 get。
    shim = types.SimpleNamespace(**vars(requests))
    shim.get = get_fn
    return shim


def _json_resp(status_code: int, payload: Any) -> Any:
    # 可配「状态码 + 任意 JSON 载荷」的 API 响应替身：payload 给非 dict 就是在钉 _payload_assets
    # 的形态归一，给 dict 就是常规 digest 通道；两条都走真实判定链，不伪造返回值。
    payload_json = json.dumps(payload).encode("utf-8")

    class _Resp:
        encoding = "utf-8"

        def __init__(self) -> None:
            # status_code 必须在 __init__（普通闭包函数体）里赋值：类体内的 LOAD_NAME 看不到外层形参
            self.status_code = status_code

        def json(self) -> Any:
            return payload

        def iter_content(self, chunk_size: int) -> Any:
            # M-12：生产读取改走限长分块，替身同步提供分块形态（单块交出全部字节）。
            return iter([payload_json])

    return _Resp()


def _stub_backoff(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    # fld 的重试退避用模块级 `import time`，sleep 走的是它自己的 time 名字。桩必须落在
    # fld.time 的 shim 上（AGENTS M-27：setattr(fld.time, "sleep", ...) 换的是全进程 time 本体，
    # 窗口内 loguru/后台线程的 sleep 一并被换）。返回记录到的秒数列表，供「重试次数 ↔ 退避次数」判据。
    sleeps: list[float] = []
    shim = types.SimpleNamespace(**vars(time))
    shim.sleep = lambda seconds: sleeps.append(seconds)
    monkeypatch.setattr(fld, "time", shim)
    return sleeps


def _exec_bits_observable(dest: Path) -> bool:
    # 判据不写 os.name/sys.platform，而是就地探一次宿主文件系统：Windows 的 chmod 只表达只读位，
    # 置上的 S_IXUSR 不会在 st_mode 里回报；POSIX（含 Linux CI）会。写死平台名会让「本机不测」
    # 变成长期事实，探一次至少保证 CI 侧这一格真的在跑。
    probe_dir = dest / "_exec_probe"
    probe_dir.mkdir(exist_ok=True)
    probe = probe_dir / "probe.bin"
    probe.write_bytes(b"x")
    probe.chmod(0o644 | stat.S_IXUSR)
    return bool(probe.stat().st_mode & stat.S_IXUSR)


def _stub_egress(
    monkeypatch: pytest.MonkeyPatch,
    dest_dir: str,
    *,
    digest: str | None,
    payload: bytes,
    rc: int = 0,
    run_raises: Exception | None = None,
) -> None:
    # 出站三面（API、产物下载、安装后 -version 探针）一次性收敛：digest 走真实判定链、
    # 产物走真实落盘+解包链，只有「网络响应」与「子进程结果」是替身——判序、真值表、基准记账
    # 全部跑生产实现（AGENTS.md「测试不得自实现被测逻辑」）。
    def _get(url: str, **kw: Any) -> Any:
        if url.startswith("https://api.github.com"):
            return _digest_resp(digest)
        return _FakeDownload(payload)

    monkeypatch.setattr(fld, "requests", _requests_shim(_get))

    def _run(*args: Any, **kwargs: Any) -> Any:
        if run_raises is not None:
            # 评审 I-1：安装后验证探针的**第三态**（既不是 0 也不是非零，而是子进程调用本身抛异常）。
            # 默认 None 时与既有全部用例逐字同形，只有新格子显式传入才生效——判据面不因本参数而变宽。
            raise run_raises
        return types.SimpleNamespace(returncode=rc, stdout=b"", stderr=b"")

    proc = types.SimpleNamespace(**vars(subprocess))
    proc.run = _run
    monkeypatch.setattr(fld, "subprocess", proc)
    # 产品代码安装成功后会就地改写 os.environ["PATH"]；不收敛就会污染同会话后续用例，
    # 而 monkeypatch.setenv 的还原由 fixture 兜底（本仓禁 patch.dict(os.environ)）。
    monkeypatch.setenv("PATH", dest_dir)


class TestIntegrityTruthTable:
    # 规格 4.1 真值表四格逐格锁死（外加一格「装了但跑不起来」）：
    #   取到且匹配 → 安装｜取到但不符 → 拒装且删包（**开关取真也不得放行**）｜
    #   取不到 + 开关假 → 拒装且不留基准｜取不到 + 开关真 → TOFU 首次记账并安装。
    # 判序（形态→哈希→解压）由 mismatch 那格间接钉住：官方哈希不符却仍落盘，就一定是判序漏了。
    def test_digest_matches_installs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 第一格：官方 digest 与实算哈希相等 → 装，且产物真落到 dest_dir/ffmpeg/ 下。
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(monkeypatch, str(tmp_path), digest=hashlib.sha256(payload).hexdigest(), payload=payload)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is True
        assert (tmp_path / "ffmpeg" / "ffmpeg").is_file()

    def test_installed_binary_must_actually_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 「装了但 -version 非零」必须算失败：返回值是整条链唯一的成功信号，不能被落盘动作本身满足。
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(monkeypatch, str(tmp_path), digest=hashlib.sha256(payload).hexdigest(), payload=payload, rc=1)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is False

    def test_digest_mismatch_refuses_and_deletes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 第二格：官方 digest 取到了却不符 → 拒装 + 半截归档必须删净。master_allowed=True 是**故意给的**：
        # 官方值已到手就不该再给 TOFU 面子，否则「不符」会被降级路径悄悄吞掉（本仓 SEV 级形态）。
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b""})
        _stub_egress(monkeypatch, str(tmp_path), digest="a" * 64, payload=payload)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is False
        assert list(tmp_path.glob("*ffmpeg_linux_native_temp*")) == []
        assert not (tmp_path / "ffmpeg" / "ffmpeg").exists()

    def test_no_digest_and_switch_off_refuses(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 第三格：取不到官方值 + 开关默认关 → 拒装。
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b""})
        _stub_egress(monkeypatch, str(tmp_path), digest=None, payload=payload)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is False
        # 默认关时**不得留下基准**：留了就等于偷偷启用了 TOFU。
        assert list(tmp_path.glob("_ffmpeg_linux*")) == []

    def test_no_digest_and_switch_on_records_tofu(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 第四格：取不到官方值 + 开关显式开 → TOFU 首次记账并装成功。
        # 「恰好一份」同样是判据：留下多份陈旧基准，下次校验挑到哪份全凭 glob 顺序。
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b""})
        _stub_egress(monkeypatch, str(tmp_path), digest=None, payload=payload)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is True
        baselines = list(tmp_path.glob("_ffmpeg_linux*.tar.xz.sha256"))
        assert len(baselines) == 1, f"首次记账必须留且只留一份基准：{baselines}"


class TestFailureIsNeverAnException:
    # MIN-2266⑤ 同族：顶层入口的承诺是「失败一律 False、绝不抛出」——安装器由启动期 check_ffmpeg()
    # 调用，一条穿出的异常会把整个录制进程带走，而不是只让这条兜底路径失败。
    # 两种 boom 分别代表「写盘/权限类 OSError」与「实现内部逻辑错」，都必须被归一成 False。
    # [评审 I-3 修的是这一格的成色] 此前 requests 替身是手写类、缺 HTTPError，OSError 那格实际
    # 撞到的是「入口层兜住 AttributeError」，压根没进 _download 的 (RequestException, OSError) 分支；
    # 改成 shim 后 OSError 真的走下载链的重试支，退避也必须收敛（否则三秒级 sleep 拖慢整个会话）。
    @pytest.mark.parametrize("boom", [OSError("disk full"), RuntimeError("unexpected")])
    def test_download_errors_return_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boom: Exception
    ) -> None:
        def _raise(*args: Any, **kwargs: Any) -> Any:
            raise boom

        monkeypatch.setattr(fld, "requests", _requests_shim(_raise))
        _stub_backoff(monkeypatch)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is False

    # [评审 I-1 补的两格] 上面那条只证明过「**装之前**的环节抛异常会被归一」；安装后验证那段独立 try
    # 此前一次都没执行过（实测把整个 except 摘掉后 46 条用例仍全绿）。
    # 后果不是「少一条 error 日志」：TimeoutExpired / OSError(ENOEXEC) 会穿出 install_ffmpeg_linux_native
    # → install_ffmpeg_linux（无 try）→ install_ffmpeg → check_ffmpeg → main.py 启动路径，
    # 正是本组头注承诺「绝不抛出」要防的那件事。
    def test_post_install_probe_timeout_is_never_an_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 探针带 timeout=30，超时是**第三种结局**（既非 rc=0 也非 rc≠0），不是 rc≠0 的子集：
        # 残缺安装、杀软拦截扫描都会让 `ffmpeg -version` 卡在子进程调用本身而不是退出。
        # 校验与落位一律走真实链路（digest 与实算哈希相等），只有子进程结果是替身。
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(
            monkeypatch,
            str(tmp_path),
            digest=hashlib.sha256(payload).hexdigest(),
            payload=payload,
            run_raises=subprocess.TimeoutExpired(["ffmpeg", "-version"], 30),
        )
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is False

    def test_zero_byte_landed_binary_is_not_a_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 完整性校验、解包定位、落位、补执行位**全部通过**——_install_binaries 只按 `p.is_file()` 取件、
        # 不看尺寸，所以「装回来一个零字节空壳」这件事只有安装后验证这一关能抓住（真机上零字节件的
        # exec 表现为 OSError(ENOEXEC)，走上面那格的 except 支；本格取 shell 侧同义取值 rc=126
        # 「找到了但无法执行」，钉的是 `probe.returncode != 0` 那一支）。
        # 与既有 test_installed_binary_must_actually_run 的分工：那条的产物**非零字节**，抓的是
        # 「装好了但拒绝执行」；本条抓的是「装的是空壳」，故必须见证件确实以 0 字节落位——
        # 否则本格会因实现改成「定位时判尺寸」而悄悄退化成一条什么都不验的空锁。
        payload = _tar_xz({"pkg/bin/ffmpeg": b"", "pkg/bin/ffprobe": b""})
        _stub_egress(monkeypatch, str(tmp_path), digest=hashlib.sha256(payload).hexdigest(), payload=payload, rc=126)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is False
        landed = tmp_path / "ffmpeg" / "ffmpeg"
        assert landed.is_file(), "零字节件应已被判为有效件并落位（本格验的是验证关，不是取件关）"
        assert landed.stat().st_size == 0, "反向见证：件必须真以 0 字节落位，否则本锁验的不是这条输入"


class TestUrlParityWithBuildExe:
    def test_linux_urls_are_identical_to_the_release_table(self) -> None:
        # 两份物理副本：build_exe（发布期）与本模块（运行期）。冻结 exe 里 import 不到根目录 build 脚本，
        # 所以副本不可避免，那就不让它漂移——换标签必须同批改两处，本条锁就是那只手。
        assert fld._LINUX_FFMPEG_URLS["linux64"] == BUILD_EXE_FFMPEG_URLS["linux-x64"]
        assert fld._LINUX_FFMPEG_URLS["linuxarm64"] == BUILD_EXE_FFMPEG_URLS["linux-arm64"]

    def test_runtime_digest_channel_agrees_with_the_release_pin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 离线复现「API digest 通道 == 发布期人工核过的钉定值」这一实测结论：
        # 桩掉 requests 返回 build_exe 的 linuxarm64 钉定值，走真实 _fetch_asset_digest 判定链。
        import build_exe

        pinned = build_exe._PINNED_RUNTIME_SHA256["linux-arm64"]["ffmpeg"]

        class _Resp:
            status_code = 200
            encoding = "utf-8"

            @staticmethod
            def json() -> dict[str, Any]:
                return {"assets": [{"name": fld._asset_name(LINUXARM64_URL), "digest": f"sha256:{pinned}"}]}

            @staticmethod
            def iter_content(chunk_size: int) -> Any:
                return iter(
                    [
                        json.dumps(
                            {"assets": [{"name": fld._asset_name(LINUXARM64_URL), "digest": f"sha256:{pinned}"}]}
                        ).encode("utf-8")
                    ]
                )

        monkeypatch.setattr(fld, "requests", _requests_shim(lambda *a, **kw: _Resp()))
        assert fld._fetch_asset_digest(LINUXARM64_URL) == pinned

    def test_malformed_digest_shape_is_rejected(self) -> None:
        # 形状关（同 build_exe._is_pinned）：截断/前缀残留/大写一律算「取不到」，不得放行。
        want = fld._asset_name(LINUXARM64_URL)
        for bad in ("", "e2dd447c", "sha256:" + "e" * 63, "E" * 64, "x" * 64):
            assert fld._digest_from_assets([{"name": want, "digest": bad}], want) == ""
        assert fld._digest_from_assets([{"name": "other.tar.xz", "digest": "e" * 64}], want) == ""
        assert fld._digest_from_assets([{"name": want, "digest": "sha256:" + "e" * 64}], want) == "e" * 64


class TestDigestPayloadShape:
    # 评审 I-2：规格 4.2 的「恒不抛」此前是可证伪的——payload.get("assets") 落在 try **之外**，
    # API（或前置网关）以 200 回数组载荷时 AttributeError 穿出 _fetch_asset_digest，被入口 catch-all
    # 归成「直下安装异常」，于是「取不到官方哈希 → 降级」被偷换成 fatal：连 master_allowed=True
    # 都装不上，用户也看不到 FFMPEG_MASTER_ALLOWED 指引。三格分别钉归一、钉返回值、钉端到端降级可达。
    @pytest.mark.parametrize(
        "payload",
        [
            [],
            [{"name": "ffmpeg.tar.xz", "digest": "sha256:" + "e" * 64}],
            None,
            "not-a-dict",
            0,
            {},
            {"assets": None},
            {"assets": {"name": "ffmpeg.tar.xz"}},
            {"assets": "sha256"},
        ],
    )
    def test_non_dict_payload_yields_no_assets(self, payload: Any) -> None:
        # 归一必须是**返回值**（空列表 = 取不到），不得靠调用点的 try 兜异常：
        # 异常形态进了 catch-all 就丢掉整条降级分支（见本组头注）。
        assert fld._payload_assets(payload) == []

    def test_dict_payload_passes_the_asset_list_through(self) -> None:
        # 反向见证：上面那格若把「一律 []」写死也会全绿，这条钉的是合法 dict 载荷原样交出。
        assets = [{"name": "ffmpeg.tar.xz", "digest": "sha256:" + "e" * 64}]
        assert fld._payload_assets({"assets": assets}) is assets

    def test_array_payload_digest_is_empty_not_raised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        want = fld._asset_name(LINUXARM64_URL)
        for payload in ([], [{"name": want, "digest": "sha256:" + "b" * 64}]):
            get_fn = (lambda p: (lambda *a, **kw: _json_resp(200, p)))(payload)
            monkeypatch.setattr(fld, "requests", _requests_shim(get_fn))
            # 第二条是「数组里就带着形状合法的 digest」的畸形应答：一旦形态判定被摘，
            # 它会立刻被当作官方期望值采信，所以判据是空串而不是「异常」。
            assert fld._fetch_asset_digest(LINUXARM64_URL) == ""

    def test_array_payload_still_takes_the_fallback_install_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        want = fld._asset_name(LINUXARM64_URL)
        api_body: list[Any] = [{"name": want, "digest": "sha256:" + "b" * 64}]

        def _get(url: str, **kw: Any) -> Any:
            if url.startswith("https://api.github.com"):
                return _json_resp(200, api_body)
            return _FakeDownload(payload)

        monkeypatch.setattr(fld, "requests", _requests_shim(_get))
        proc = types.SimpleNamespace(**vars(subprocess))
        proc.run = lambda *a, **kw: types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        monkeypatch.setattr(fld, "subprocess", proc)
        monkeypatch.setenv("PATH", str(tmp_path))
        # 端到端那一侧：数组载荷必须落到 TOFU 降级档（开关显式开）并装成功。
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is True
        assert (tmp_path / "ffmpeg" / "ffmpeg").is_file()
        baseline = fld._baseline_path(tmp_path, LINUXARM64_URL)
        assert baseline.is_file()
        # 基准记的必须是**实算**哈希；响应里那条 b*64 若被当成期望值或基准，下一轮就自证合法了。
        assert baseline.read_text(encoding="ascii") == hashlib.sha256(payload).hexdigest()


class TestApiDocCap:
    # M-12（2026-10-30）：GitHub API 应答必须按字节限长读取（判据复用 node_install 的单点函数）——
    # 被投毒的超大应答不得整份物化。超限必须落「取不到官方哈希」既有降级口径（回 ""），而不是
    # 把异常穿出入口（那会被入口 catch-all 偷换成 fatal）。
    def test_over_limit_response_degrades_to_empty_digest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fld, "_OFFICIAL_DOC_MAX_BYTES", 16)
        body = {"assets": [{"name": fld._asset_name(LINUXARM64_URL), "digest": "sha256:" + "d" * 64}]}
        monkeypatch.setattr(fld, "requests", _requests_shim(lambda *a, **kw: _json_resp(200, body)))
        assert fld._fetch_asset_digest(LINUXARM64_URL) == ""


class TestApiStatusGate:
    def test_non_200_status_never_trusts_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 评审 I-1③：status_code != 200 的闸门此前零锁（整段摘掉后 19 条全绿）。
        # 201/204/403/404/500 都可能带着一份「看起来合法」的 assets/digest（网关、缓存层、错误页模板），
        # 一律不得采信——「期望值只来自 200」这条判据在本模块只有这一处落点。
        want = fld._asset_name(LINUXARM64_URL)
        body = {"assets": [{"name": want, "digest": "sha256:" + "c" * 64}]}
        for status in (201, 204, 403, 404, 500):
            monkeypatch.setattr(
                fld, "requests", _requests_shim((lambda s: (lambda *a, **kw: _json_resp(s, body)))(status))
            )
            assert fld._fetch_asset_digest(LINUXARM64_URL) == "", f"status={status} 的载荷不得被采信"
        # 反向见证：同一份载荷在 200 下必须被采信，否则上面那条循环是恒真的空锁。
        monkeypatch.setattr(fld, "requests", _requests_shim(lambda *a, **kw: _json_resp(200, body)))
        assert fld._fetch_asset_digest(LINUXARM64_URL) == "c" * 64


class TestArchiveShapeGate:
    def test_non_tar_archive_refuses_before_hashing(self, tmp_path: Path) -> None:
        # 评审 I-1①：is_tarfile 闸门此前零锁（改成恒真后 19 条全绿）。直调 _verify_archive，
        # 并额外断言「基准文件不存在」——闸门被摘时实现会先算哈希、把 200+HTML 错误页的哈希
        # 当可信基准写下去（正是 ffmpeg_install.py 记录过的真实污染形态），只判返回值抓不住它。
        archive = tmp_path / "archive.tar.xz"
        archive.write_bytes(b"<!DOCTYPE html><html><body>502 Bad Gateway</body></html>")
        dest = tmp_path / "dest"
        dest.mkdir()
        assert fld._verify_archive(archive, "", dest, LINUXARM64_URL, True) is False
        assert not fld._baseline_path(dest, LINUXARM64_URL).exists()

    def test_non_tar_archive_end_to_end_refuses(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 同一判据的端到端形态：取不到官方值 + 开关开 + 产物不是 tar → 拒装、不留基准、不落产物。
        _stub_egress(monkeypatch, str(tmp_path), digest=None, payload=b"<!DOCTYPE html><html><body>502</body></html>")
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is False
        assert list(tmp_path.glob("_ffmpeg_linux*")) == []
        assert not (tmp_path / "ffmpeg").exists()


class TestTofuBaselineCompare:
    # 评审 I-1④ + I-4：TOFU 的「第二次及以后运行」整段此前从未执行（覆盖率 220-244 全 miss），
    # 而它恰是「上游换构建 / CDN 被替换」时唯一还活着的防线。
    # 三条直调 _verify_archive 分别钉「匹配 → 放行」「不符 → 拒且基准不被改写」「读不出 → 拒且不抛」，
    # 再补一条端到端两跑格（首跑记账 → 换字节重跑必须拒）。
    def _prepare(self, tmp_path: Path) -> tuple[Path, Path, str]:
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        archive = tmp_path / "archive.tar.xz"
        archive.write_bytes(payload)
        dest = tmp_path / "dest"
        dest.mkdir()
        return archive, dest, hashlib.sha256(payload).hexdigest()

    def test_matching_baseline_accepts(self, tmp_path: Path) -> None:
        archive, dest, current = self._prepare(tmp_path)
        fld._baseline_path(dest, LINUXARM64_URL).write_text(current, encoding="ascii")
        assert fld._verify_archive(archive, "", dest, LINUXARM64_URL, True) is True

    def test_mismatched_baseline_refuses_and_is_not_rewritten(self, tmp_path: Path) -> None:
        archive, dest, _current = self._prepare(tmp_path)
        baseline = fld._baseline_path(dest, LINUXARM64_URL)
        baseline.write_text("f" * 64, encoding="ascii")
        assert fld._verify_archive(archive, "", dest, LINUXARM64_URL, True) is False
        # 基准被拒装轮改写 = 下一次运行拿「篡改产物的哈希」判它合法，整条 TOFU 链自废。
        assert baseline.read_text(encoding="ascii") == "f" * 64

    def test_non_ascii_baseline_refuses_without_raising(self, tmp_path: Path) -> None:
        # 评审 I-4：基准被写成非 ASCII 字节时 read_text(encoding="ascii") 抛 UnicodeDecodeError
        # （ValueError 子类，**不是** OSError），此前只捕 OSError 接不住 → 异常穿出 _verify_archive
        # → 入口归成泛化的「直下安装异常」，那条唯一带「请人工核对或删除 {file} 后重试」指引的
        # error 日志永不打印。断言只看「回 False 且不抛」，不匹配日志文本。
        archive, dest, _current = self._prepare(tmp_path)
        fld._baseline_path(dest, LINUXARM64_URL).write_bytes("这不是十六进制哈希".encode("utf-8"))
        assert fld._verify_archive(archive, "", dest, LINUXARM64_URL, True) is False

    def test_second_run_with_different_bytes_refuses(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        first = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(monkeypatch, str(tmp_path), digest=None, payload=first)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is True
        baseline = fld._baseline_path(tmp_path, LINUXARM64_URL)
        recorded = baseline.read_text(encoding="ascii")
        assert recorded == hashlib.sha256(first).hexdigest()
        # 把首跑产物标成哨兵：第二跑若真去解包落位就会覆盖它（比删目录温和，也不碰 safe-delete 护栏）。
        sentinel = b"SENTINEL-FROM-FIRST-RUN"
        (tmp_path / "ffmpeg" / "ffmpeg").write_bytes(sentinel)
        second = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\necho tampered\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(monkeypatch, str(tmp_path), digest=None, payload=second)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is False
        assert baseline.read_text(encoding="ascii") == recorded, "拒装轮不得把篡改产物的哈希写成新基准"
        assert (tmp_path / "ffmpeg" / "ffmpeg").read_bytes() == sentinel, "拒装轮不得解包落位"
        assert list(tmp_path.glob("*ffmpeg_linux_native_temp*")) == []


class TestBinaryLayoutDiscovery:
    # 评审 I-1②/⑤：取件逻辑此前只证明过「pkg/bin/ 这一层能取到」——实现改成写死 pkg/bin/<binary>
    # 后 19 条全绿。这里用两种真实存在的布局各造一支**真**归档（平铺 <top>/<binary>、深层 a/b/bin/），
    # 并补「缺 ffprobe」一格：缺一件必须整次作废，且 dest 侧不得留下半截安装。
    def _install(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, members: dict[str, bytes], **kw: Any) -> bool:
        payload = _tar_xz(members, **kw)
        _stub_egress(monkeypatch, str(tmp_path), digest=hashlib.sha256(payload).hexdigest(), payload=payload)
        return fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False)

    def test_flat_layout_installs_both_binaries(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 平铺（无 bin 层）：BtbN 的部分构建与几乎所有自建归档都是这个形态。
        top = "ffmpeg-master-latest-linuxarm64-gpl"
        assert (
            self._install(tmp_path, monkeypatch, {f"{top}/ffmpeg": b"#!/bin/sh\n", f"{top}/ffprobe": b"#!/bin/sh\n"})
            is True
        )
        assert (tmp_path / "ffmpeg" / "ffmpeg").read_bytes() == b"#!/bin/sh\n"
        assert (tmp_path / "ffmpeg" / "ffprobe").is_file()

    def test_deep_bin_layout_installs_both_binaries(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        assert (
            self._install(tmp_path, monkeypatch, {"a/b/bin/ffmpeg": b"#!/bin/sh\n", "a/b/bin/ffprobe": b"#!/bin/sh\n"})
            is True
        )
        assert (tmp_path / "ffmpeg" / "ffmpeg").is_file()
        assert (tmp_path / "ffmpeg" / "ffprobe").is_file()

    def test_missing_companion_leaves_no_half_install(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 归档里只有 ffmpeg、没有 ffprobe。
        assert self._install(tmp_path, monkeypatch, {"pkg/bin/ffmpeg": b"#!/bin/sh\n"}) is False
        # 缺一件 = 整次作废：dest/ffmpeg/ 连目录都不许出现。原实现边找边拷，ffmpeg 已落位、
        # 只剩 ffprobe 缺席，那个半截目录会一直留到下一次运行（且是「装过了」的假证据）。
        assert not (tmp_path / "ffmpeg").exists()
        assert list(tmp_path.glob("*ffmpeg_linux_native_temp*")) == []

    def test_exec_bit_is_restored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 成员 mode 刻意给 0o644（归档外属性在部分构建里的真实形态）：只有实现补回执行位才谈得上能跑。
        assert (
            self._install(
                tmp_path,
                monkeypatch,
                {"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"},
                mode=0o644,
            )
            is True
        )
        if _exec_bits_observable(tmp_path):
            # POSIX（含 Linux CI）：owner 执行位必须真被置上，否则真机上 -version 探针必然 PermissionError。
            for binary in ("ffmpeg", "ffprobe"):
                mode = (tmp_path / "ffmpeg" / binary).stat().st_mode
                assert mode & stat.S_IXUSR, f"{binary} 缺 owner 执行位：mode={oct(mode)}"
        else:
            # Windows 宿主的 chmod 只表达只读位、执行位不可观测（生产两侧的 chmod 调用是同一条，
            # 差异只在文件系统语义）。这一格由 Linux CI 承载，见 _exec_bits_observable 头注。
            assert (tmp_path / "ffmpeg" / "ffprobe").is_file()


class TestDownloadRetryPolicy:
    # 评审 I-3：_download 的整段重试/退避/半截归档清理此前一次都没执行过（requests 替身缺 HTTPError，
    # 任何下载期异常都在 except 类型解析阶段炸成 AttributeError）。四格全部**直调 _download**，
    # 判据落在「尝试次数 / 退避次数 / 归档是否留半截 / 异常是否穿出」，不匹配日志文本。
    def test_connection_error_retries_to_max_then_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        archive = tmp_path / "archive.tar.xz"
        calls: list[str] = []
        sleeps = _stub_backoff(monkeypatch)

        def _get(url: str, **kw: Any) -> Any:
            calls.append(url)
            raise requests.ConnectionError("connection reset by peer")

        monkeypatch.setattr(fld, "requests", _requests_shim(_get))
        assert fld._download(LINUXARM64_URL, archive) is False
        assert len(calls) == fld._MAX_RETRIES, f"连接级失败必须重试到上限：实际 {len(calls)} 次"
        assert len(sleeps) == fld._MAX_RETRIES - 1, "退避比尝试少一次（最后一轮失败后不再白等）"
        assert not archive.exists()

    def test_transient_failure_then_success_writes_whole_payload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        archive = tmp_path / "archive.tar.xz"
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        state = {"n": 0}
        sleeps = _stub_backoff(monkeypatch)

        def _get(url: str, **kw: Any) -> Any:
            state["n"] += 1
            if state["n"] < 3:
                raise requests.ConnectionError("transient")
            return _FakeDownload(payload)

        monkeypatch.setattr(fld, "requests", _requests_shim(_get))
        assert fld._download(LINUXARM64_URL, archive) is True
        assert state["n"] == 3, "第三次成功后不得继续重试"
        assert len(sleeps) == 2
        assert archive.read_bytes() == payload, "重试成功那一轮必须完整落盘"

    def test_http_error_is_not_retried(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        archive = tmp_path / "archive.tar.xz"
        calls: list[str] = []
        sleeps = _stub_backoff(monkeypatch)

        def _get(url: str, **kw: Any) -> Any:
            calls.append(url)
            return _FakeDownload(b"<html>404</html>", raise_on_status=requests.HTTPError("404 Client Error"))

        monkeypatch.setattr(fld, "requests", _requests_shim(_get))
        assert fld._download(LINUXARM64_URL, archive) is False
        assert len(calls) == 1, f"4xx/5xx 重试不会把 404 变成 200：{len(calls)} 次"
        assert sleeps == []
        # raise_for_status 在 open(archive,"wb") **之前**，故这一支根本不产生文件——
        # 与 OSError 支「当场删半截归档」形成可区分的两侧判据。
        assert not archive.exists()

    def test_write_oserror_does_not_escape_download(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # MIN-2266⑤ 的原始现场就是「open(...,"wb") 的 OSError 穿出到启动期 check_ffmpeg()」。
        # 评审实测：把 _download 的 except (RequestException, OSError) 整段删掉，此前 19 条全绿
        # ——即这条回归锁对它要防的回归零敏感。本格直调 _download，钉「回 False 且不抛 + 半截归档删净」。
        archive = tmp_path / "archive.tar.xz"
        calls: list[str] = []
        sleeps = _stub_backoff(monkeypatch)

        def _get(url: str, **kw: Any) -> Any:
            calls.append(url)
            return _FakeDownload(b"PARTIAL-DOWNLOAD" * 64, raise_while_streaming=OSError("disk full"))

        monkeypatch.setattr(fld, "requests", _requests_shim(_get))
        assert fld._download(LINUXARM64_URL, archive) is False
        assert len(calls) == fld._MAX_RETRIES
        assert len(sleeps) == fld._MAX_RETRIES - 1
        assert not archive.exists(), "写盘中途失败的半截归档必须当场删掉，不得留给下一轮续写"


# ==========================================================================
# 2026-10-21 评审包 M-44 / M-47 / M-48 / M-49（Linux 直下侧）。
# 上面 TestDownloadRetryPolicy 已经锁住「重试 / 退避 / 半截归档 / 异常不穿出」这四格；本段补的是
# 同一批下载动作里**落盘纪律**的那一半：名字不可预测、独占创建、目录锁、PATH 去重、解包前空间预检、
# 以及此前完全缺失的字节上限。判据一律落在「现场还剩什么」而不是「日志写了什么」。


class TestExclusiveArchiveSink:
    # M-44：归档名从固定 `ffmpeg_linux_native_temp.tar.xz` 改为「可识别前缀 + 随机后缀」，
    # 写入走 fld.open_exclusive（O_CREAT|O_EXCL|O_NOFOLLOW）。
    def test_archive_name_is_unpredictable_yet_still_findable(self, tmp_path: Path) -> None:
        first = fld.unique_path(tmp_path, fld._TEMP_ARCHIVE_PREFIX, fld._TEMP_ARCHIVE_SUFFIX)
        second = fld.unique_path(tmp_path, fld._TEMP_ARCHIVE_PREFIX, fld._TEMP_ARCHIVE_SUFFIX)
        assert first != second, "可预测名 = 可被预置占位，两实例也会互相覆盖"
        # 前缀必须保住：TestIntegrityTruthTable 等多条既有断言靠 *ffmpeg_linux_native_temp* 找产物。
        assert first.name.startswith(fld._TEMP_ARCHIVE_PREFIX)
        assert first.name.endswith(fld._TEMP_ARCHIVE_SUFFIX)

    def test_foreign_archive_at_the_pinned_legacy_name_is_never_touched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 把命名钉回改动前的固定名，复现「本地主体/另一实例先占住那个路径」的形态：
        # 本轮必须失败、且**不得**把对方的文件当成自己的半截归档删掉（M-44 登记的互删形态）。
        victim = tmp_path / "ffmpeg_linux_native_temp.tar.xz"
        victim.write_bytes(b"NOT-OURS-DO-NOT-DELETE")
        monkeypatch.setattr(fld, "unique_path", lambda directory, prefix, suffix: Path(directory) / victim.name)
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(monkeypatch, str(tmp_path), digest=hashlib.sha256(payload).hexdigest(), payload=payload)
        _stub_backoff(monkeypatch)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is False
        assert victim.read_bytes() == b"NOT-OURS-DO-NOT-DELETE"
        assert not (tmp_path / "ffmpeg").exists()

    def test_download_uses_an_unpredictable_sink_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 本类另两条用例把 unique_path **钉成固定名**来复现「占位者」形态；那种改法对「调用点是否真的走
        # unique_path」零敏感（钉进去的名字恰好等于实现用的名字）。故这里判**行为**：spy 记录真正交给
        # open_exclusive 的路径，必须是「前缀 + 随机后缀」而不是改动前的 ffmpeg_linux_native_temp.tar.xz。
        recorded: list[Path] = []
        real_open_exclusive = fld.open_exclusive

        def spy_open(path: Path) -> Any:
            recorded.append(Path(str(path)))
            return real_open_exclusive(path)

        monkeypatch.setattr(fld, "open_exclusive", spy_open)
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(monkeypatch, str(tmp_path), digest=hashlib.sha256(payload).hexdigest(), payload=payload)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is True
        assert recorded, "下载段没有走独占创建，M-44 的判据已失效"
        assert recorded[0].name != "ffmpeg_linux_native_temp.tar.xz", "调用点仍在用改动前的固定可预测名"
        assert recorded[0].name.startswith(fld._TEMP_ARCHIVE_PREFIX), "可识别前缀不得丢"

    def test_directory_lock_blocks_a_concurrent_installer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 锁文件由「别人」持着（mtime 新鲜）：本轮必须一次请求都不发就放弃，且不删别人的锁。
        lock = tmp_path / fld._LOCK_FILE_NAME
        lock.write_text("pid=999999", encoding="ascii")
        monkeypatch.setattr(fld, "requests", _requests_shim(lambda *a, **kw: pytest.fail("持锁期间不得出站")))
        proc = types.SimpleNamespace(**vars(subprocess))
        proc.run = lambda *a, **kw: pytest.fail("持锁期间不得跑安装后探针")
        monkeypatch.setattr(fld, "subprocess", proc)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is False
        assert lock.is_file(), "不得删除别人持有的锁"


class TestPathInjectionAndSpacePrecheck:
    def test_two_installs_leave_the_same_prefix_once_in_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # M-47：旧形态是 `str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH")`，无去重——
        # 每次自动安装都把同一个目录再叠一层，PATH 单调变长（main.py 侧同样有这条守卫）。
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(monkeypatch, str(tmp_path), digest=hashlib.sha256(payload).hexdigest(), payload=payload)
        target = str(tmp_path / "ffmpeg")
        for _round in range(2):
            assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is True
        parts = os.environ["PATH"].split(os.pathsep)
        assert parts[0] == target, "注入的必须是本次真正落成的目录"
        assert parts.count(target) == 1, f"同一前缀被反复叠加：{parts[:5]}"

    def test_space_precheck_refuses_before_unpacking(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # M-48：本模块的解包目录一直落在应用目录内（不是 %TEMP%），所以这条预检是新增的那一半——
        # 预检必须在解包**之前**拦下：不留半截 ffmpeg 目录，也把自己创建的归档收干净。
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(monkeypatch, str(tmp_path), digest=hashlib.sha256(payload).hexdigest(), payload=payload)
        monkeypatch.setattr(fld, "has_room_for_unpack", lambda *a, **kw: False)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is False
        assert not (tmp_path / "ffmpeg").exists()
        assert list(tmp_path.glob("*ffmpeg_linux_native_temp*")) == []


class TestDownloadByteCap:
    def test_byte_cap_stops_the_stream_and_removes_the_partial(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # M-49 的量这一半：本模块此前有重试、无上限。上限判定必须排在 sink.write **之前**，
        # 否则「先写进磁盘再判超限」只是把无上限流改成了「略多一点的」无上限流。
        archive = tmp_path / "capped.tar.xz"
        monkeypatch.setattr(fld, "_MAX_ARCHIVE_BYTES", 8)
        calls: list[str] = []

        def _get(url: str, **kw: Any) -> Any:
            calls.append(url)
            return _FakeDownload(b"X" * 4096)

        monkeypatch.setattr(fld, "requests", _requests_shim(_get))
        sleeps = _stub_backoff(monkeypatch)
        assert fld._download(LINUXARM64_URL, archive) is False
        assert len(calls) == 1, "超限不是「网络抖了一下」，不得进入重试循环"
        assert sleeps == []
        assert not archive.exists(), "超限的半截归档必须当场删掉"
