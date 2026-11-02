# tests/test_ffmpeg_master_download.py — src/ffmpeg_master_download.py 的回归锁。
#
# 该模块被 src/ffmpeg_install.py 模块级 import 并进主链（install_ffmpeg_windows →
#   FFMPEG_MASTER_ALLOWED 显式开关 → download_ffmpeg_master），模块自身的选源顺序、探针判据、
#   TOFU 记账与「失败不抛」契约由本文件直接锁住。用例按「删掉哪条判据就该变红」组织，
#   全部离线：requests / subprocess / 落盘目录三面被打桩或收敛到 tmp_path，绝不真下 ~190MB 产物。
#
# 锁住的行为：
#   A) 候选源顺序即优先级——BtbN 权威上游必须排在 fyhub 镜像之前
#      （镜像既能替换产物就能替换它自己的元数据，权威性严格弱于上游，只配当兜底项）；
#   B) TOFU 基准存在却读不出来一律拒装（本模块 TOFU 是唯一一道完整性检查，
#      没有「降级后仍可安装」的余量）；
#   C) 首次记账必须落 warning（不得降成 debug），并修剪同前缀陈旧基准
#      （master-latest 是滚动别名，不修剪即让程序目录无界增长）；
#   D) 非压缩包产物（镜像站 200 + text/html 的人机验证页）必须先于
#      哈希记账被拒，且不进入解压、不执行刚下载的二进制；
#   E) _looks_like_html 的读失败判「内容不可信」（True），不得当「不是 HTML」放行；
#   F) OSError（写盘失败 / 磁盘满 / 路径失效）不得穿出「失败一律返回 False、不抛」契约。
#
# Mock 口径：只替换「模块自己的 requests 名字」与 subprocess 的模块全局引用
#   （types.SimpleNamespace(**vars(...)) 浅拷贝，绝不动 stdlib 本体），
#   判定分支（顺序、探针三态、形态守卫、TOFU 记账/比对、异常归一）一律走真实实现。

import ast
import hashlib
import io
import os
import subprocess
import types
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal, cast

import pytest
import requests

import src.ffmpeg_master_download as md

GITHUB_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
FYHUB_URL = "https://fyhub.cn/FFmpeg/latest/ffmpeg-master-latest-win64-gpl.zip"

# 镜像站挑战页的真实形态（2026-09-22 实测）：200 + text/html、引用 PoW 脚本的人机验证页。
HTML_CHALLENGE = (
    b'\n<!doctype html>\n<html lang="zh-CN"><head><title>download</title></head>'
    b"<body><script src=/static/public/vdf-worker.js></script></body></html>"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_with_bin(members: tuple[str, ...] = ("bin/ffmpeg.exe", "bin/ffprobe.exe")) -> bytes:
    # 必须是真 zip：is_valid_zip 走 zipfile.is_zipfile（读尾部 EOCD），unzip_file 还要真的解压。
    # 用真压缩包而不是多层 mock，才能让「换实现（去掉 bin/ 层、改成 glob）」在这里立刻变红。
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in members:
            zf.writestr(f"ffmpeg-master/bin/{name}", "pretend-binary")
    return buf.getvalue()


class _Bar:
    # tqdm 替身：进度条不是被测对象，但它的迭代体就是那段「读流 + 写盘」的下载循环，
    # 必须能正常进出——直接拿掉会让下载分支的每一行都跑不到。
    def __init__(self, *_a: object, **_k: object) -> None:
        pass

    def __enter__(self) -> "_Bar":
        return self

    def __exit__(self, *args: object) -> Literal[False]:
        return False

    def update(self, _n: int) -> None:
        return None


class _Resp:
    # requests.Response 在被测代码里用到的最小面：状态码 / 头 / 流式内容 / close / 上下文协议。
    # iter_content 刻意可被配成「抛异常」，用来锁该读失败分支。
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        content: bytes = b"",
        stream_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._content = content
        self._stream_error = stream_error
        self.closed = False

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *args: object) -> Literal[False]:
        return False

    def close(self) -> None:
        self.closed = True

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int = 1024) -> Iterator[bytes]:
        if self._stream_error is not None:
            raise self._stream_error
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]


def _as_response(resp: _Resp) -> requests.Response:
    # _looks_like_html 的形参注解是 requests.Response，而本替身只实现它真正调用的那几个成员
    # （headers.get / iter_content）。用 cast 显式收窄，不为了「类型更诚实」去继承 Response
    # （继承会让 iter_content 覆写的签名不兼容，反而引入新的类型噪音）。
    return cast(requests.Response, resp)


class _FakeHttp:
    # 按 (url, 请求形态) 派发的出站替身；**未登记的组合直接 AssertionError**。
    # 形态用「是否带 Range 头」区分：_probe 发 Range 探针、_stream_download 发完整 GET，
    # 于是「探针 ok 但整包 404」「探针拿到 zip 首字节但整包回 HTML」这些互不等价的真实形态
    # 能分别构造——只用一个响应对象就把两条路径混成一条，会同时丢掉这两条锁。
    PROBE = "probe"
    DOWNLOAD = "download"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.routes: dict[tuple[str, str], _Resp] = {}
        # 被测代码把下面两个名字用于 except 元组（不发请求），故必须留真身。
        self.RequestException = requests.RequestException
        self.HTTPError = requests.HTTPError

    def add(self, url: str, kind: str, resp: _Resp) -> None:
        self.routes[(url, kind)] = resp

    def get(self, url: str, *args: Any, **kwargs: Any) -> _Resp:
        headers = kwargs.get("headers") or {}
        kind = self.PROBE if "Range" in headers else self.DOWNLOAD
        self.calls.append((kind, url))
        resp = self.routes.get((url, kind))
        if resp is None:
            raise AssertionError(f"测试桩未登记的出站请求：{kind} {url}")
        return resp

    def post(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("本模块不使用 POST，出现即说明有新增出站面未登记")

    def urls_of(self, kind: str) -> list[str]:
        return [url for k, url in self.calls if k == kind]


@pytest.fixture(autouse=True)
def no_egress(monkeypatch: pytest.MonkeyPatch) -> _FakeHttp:
    # 兜底哨兵：先用「未登记即红」的 requests 换掉模块全局名，用例再往这个实例里登记路由。
    # 为什么必须 autouse 而不是每条用例自己记得：download_ffmpeg_master 的全部出站都走
    # md.requests（模块级名字查找），漏桩一次就是真去 github.com 拉 ~190MB
    # （与 test_ffmpeg_install 同一族事故）。
    http = _FakeHttp()
    monkeypatch.setattr(md, "requests", http)
    # 安装成功分支会真改 os.environ["PATH"]（把 bin 目录前置注入）；不还原会污染同进程
    # 后续用例的子进程查找路径。按仓内约定用 setenv 快照（禁 patch.dict(os.environ)）。
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    monkeypatch.setattr(md, "tqdm", _Bar)
    return http


def _proc_shim(codes: dict[tuple[str, ...], int], calls: list[str]) -> types.SimpleNamespace:
    # 按命令元组查退出码，查不到取 0（成功）；calls 记录顺序——「有没有执行刚下载的二进制」
    # 本身就是 B/D 两条锁的断言对象，所以必须是可观测的调用列表而不是静默替身。
    class _R:
        def __init__(self, code: int) -> None:
            self.returncode = code
            self.stdout = b"ffmpeg version n7.1"
            self.stderr = b""

    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> _R:
        calls.append(" ".join(cmd))
        return _R(codes.get(tuple(cmd), 0))

    shim = types.SimpleNamespace(**vars(subprocess))
    shim.run = fake_run
    return cast(types.SimpleNamespace, shim)


def _serve_file_source(
    http: _FakeHttp, url: str, payload: bytes, *, download_headers: dict[str, str] | None = None
) -> None:
    # 「探针与整包都给同一份合法产物」的正常源。download_headers 默认留空 →
    # _build_identity 返回 "" → 基准文件退回无构建标识的旧命名，
    # 需要按名字预置基准的用例（构造「基准存在但读不出来」）依赖这个稳定名字。
    http.add(url, _FakeHttp.PROBE, _Resp(content=payload))
    http.add(url, _FakeHttp.DOWNLOAD, _Resp(content=payload, headers=download_headers or {}))


def _logs(monkeypatch: pytest.MonkeyPatch, level: str) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(md.logger, level, lambda msg, *a, **k: captured.append(str(msg)))
    return captured


# ---------------------------------------------------------------------------
# A) 候选源顺序


class TestCandidateSourceOrder:
    def test_authority_upstream_precedes_mirror_for_every_arch(self) -> None:
        # 断言**整张列表逐字相等**，而不是「包含两个 URL」：后者对调顺序仍然通过，
        # 而「镜像排在权威上游之前」正是本项要消灭的形态。
        for arch in ("win64", "winarm64"):
            base = f"ffmpeg-master-latest-{arch}-gpl.zip"
            assert md._candidate_urls(arch) == [
                f"https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/{base}",
                f"https://fyhub.cn/FFmpeg/latest/{base}",
            ], f"{arch} 的候选顺序/取值漂移"

    def test_mirror_is_probed_only_after_the_authority_fails(
        self, no_egress: _FakeHttp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 顺序不只是「列表里谁在前」，而是运行期的实际行为：权威上游先被探、并被选中；
        # 镜像只在它**不可达**时才被探测使用。有人把 for 循环改成 reversed(urls) 时，
        # 逐字相等那条断言会红，而这条从运行期顺序上再兜一层。
        # 整包 GET 刻意回 404：raise_for_status 先于 open(wb)，既走完整链路又不落任何文件。
        no_egress.add(GITHUB_URL, _FakeHttp.PROBE, _Resp(status_code=503))
        no_egress.add(FYHUB_URL, _FakeHttp.PROBE, _Resp(content=_zip_with_bin()))
        no_egress.add(FYHUB_URL, _FakeHttp.DOWNLOAD, _Resp(status_code=404))
        monkeypatch.setattr(md, "subprocess", _proc_shim({}, []))

        assert md.download_ffmpeg_master(str(tmp_path), arch="win64") is False
        assert no_egress.urls_of(_FakeHttp.PROBE) == [GITHUB_URL, FYHUB_URL], "候选探测顺序须上游在前、镜像在后"
        assert no_egress.urls_of(_FakeHttp.DOWNLOAD) == [FYHUB_URL], "上游不可达时才允许落到镜像，且只发一次完整 GET"

    @pytest.mark.parametrize(
        "machine,expected",
        [("ARM64", "winarm64"), ("aarch64", "winarm64"), ("AMD64", "win64"), ("x86_64", "win64"), ("", "win64")],
    )
    def test_arch_detection_falls_back_to_win64(
        self, monkeypatch: pytest.MonkeyPatch, machine: str, expected: str
    ) -> None:
        # platform 是 stdlib 模块本体，改它会波及同进程其它代码 → 浅拷贝换单属性。
        # 未知/空架构一律默认 x86_64：宁可装能跑的 x86_64，也不在架构信息不可信时误装 arm64 原生包。
        shim = types.SimpleNamespace(**vars(md.platform))
        shim.machine = lambda: machine
        monkeypatch.setattr(md, "platform", shim)
        assert md._windows_arch() == expected


# ---------------------------------------------------------------------------
# B) 基准存在但读不出来 → 一律拒装


class TestUnreadableBaselineRefusesInstall:
    def test_unreadable_baseline_raises_integrity_and_discards_zip(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "ffmpeg_master_win64_temp.zip"
        zip_path.write_bytes(_zip_with_bin())
        # 用「目录当文件读」天然复现 OSError（IsADirectoryError / Windows PermissionError），
        # 不必 patch stdlib 的 Path.read_text；exists() 仍为真，正是「基准在但读不出」的形态。
        hash_file = tmp_path / "_ffmpeg_master.win64.zip.sha256"
        hash_file.mkdir()

        with pytest.raises(md.IntegrityError):
            md._tofu_verify_or_record(zip_path, hash_file, GITHUB_URL)
        assert not zip_path.exists(), "读不出基准时留下的产物会在下次运行被当成「已下载」"

    def test_entrypoint_refuses_and_never_executes_the_binary(
        self, no_egress: _FakeHttp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = _zip_with_bin()
        _serve_file_source(no_egress, GITHUB_URL, payload)
        (tmp_path / "_ffmpeg_master.win64.zip.sha256").mkdir()
        proc_calls: list[str] = []
        monkeypatch.setattr(md, "subprocess", _proc_shim({}, proc_calls))
        errors = _logs(monkeypatch, "error")

        assert md.download_ffmpeg_master(str(tmp_path), arch="win64") is False
        assert not (tmp_path / "ffmpeg_master_win64_temp.zip").exists()
        assert not (tmp_path / "ffmpeg").exists(), "拒装路径上却落了产物 = 校验形同未做"
        assert proc_calls == [], "绝不得执行刚下载的二进制"
        assert any("SHA256" in m or "完整性" in m for m in errors)

    def test_readable_matching_baseline_still_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 对照组（防「B 的拒装退化成一律拒装」）：基准可读且相符时必须放行。
        payload = _zip_with_bin()
        zip_path = tmp_path / "a.zip"
        zip_path.write_bytes(payload)
        hash_file = tmp_path / "_ffmpeg_master.win64.zip.sha256"
        hash_file.write_text(_sha256(payload), encoding="ascii")
        debugs = _logs(monkeypatch, "debug")

        md._tofu_verify_or_record(zip_path, hash_file, GITHUB_URL)

        assert zip_path.exists()
        assert any("TOFU 基准校验" in m for m in debugs)


# ---------------------------------------------------------------------------
# C) 首次 TOFU 记账：warning + 修剪陈旧基准


class TestTofuFirstRecording:
    def test_first_record_logs_warning_not_debug(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 这一条是「本次安装没有任何可比对的期望值」的唯一书面证据；降成 debug 等于静默
        # （与本仓「降级必须显式 warning」的一贯口径同源）。
        payload = _zip_with_bin()
        zip_path = tmp_path / "a.zip"
        zip_path.write_bytes(payload)
        hash_file = tmp_path / "_ffmpeg_master.win64.zip.sha256"
        warnings = _logs(monkeypatch, "warning")
        debugs = _logs(monkeypatch, "debug")

        md._tofu_verify_or_record(zip_path, hash_file, GITHUB_URL)

        assert hash_file.read_text(encoding="ascii").strip() == _sha256(payload)
        assert any("首次记录" in m and "TOFU" in m for m in warnings), "首次记账必须落 warning"
        assert not any("首次记录" in m for m in debugs), "warning 被降成 debug = 未校验安装被藏进日志"

    def test_prune_removes_every_stale_baseline_with_the_same_prefix(self, tmp_path: Path) -> None:
        # master-latest 是滚动别名：每发一次新构建就多一个基准文件且再不参与校验，
        # 不修剪即程序目录无界增长 + 排查时一堆陈旧基准混在里面。
        stale_names = ["_ffmpeg_master.win64.aaaa1111bbbb.zip.sha256", "_ffmpeg_master.winarm64.zip.sha256"]
        for stale in stale_names:
            (tmp_path / stale).write_text("0" * 64, encoding="ascii")
        keep = tmp_path / "_ffmpeg_master.win64.cccc2222dddd.zip.sha256"
        keep.write_text("1" * 64, encoding="ascii")

        removed = md._prune_stale_master_baselines(tmp_path, keep)

        assert sorted(removed) == sorted(stale_names)
        assert keep.is_file(), "keep 自己不得被剪掉（它正是本次校验要读的那一份）"

    def test_record_path_prunes_so_only_one_baseline_survives(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 端到端一侧：写新基准后同前缀旧基准必须已被清掉。只测修剪函数测不到
        # 「函数在、调用点没了」这种半截实现形态。
        (tmp_path / "_ffmpeg_master.win64.aaaa1111bbbb.zip.sha256").write_text("0" * 64, encoding="ascii")
        zip_path = tmp_path / "a.zip"
        zip_path.write_bytes(_zip_with_bin())
        keep = tmp_path / "_ffmpeg_master.win64.zip.sha256"
        warnings = _logs(monkeypatch, "warning")

        md._tofu_verify_or_record(zip_path, keep, GITHUB_URL)

        left = sorted(p.name for p in tmp_path.glob(f"{md._HASH_PREFIX}*{md._HASH_SUFFIX}"))
        assert left == [keep.name], f"陈旧基准未被修剪：{left}"
        assert any("aaaa1111bbbb" in m for m in warnings), "修剪了也要点名删了哪些，便于事后核对"


# ---------------------------------------------------------------------------
# D) 非压缩包产物拒装（镜像站 200 + text/html 的人机验证页）


class TestNonArchivePayloadRefused:
    def test_html_payload_is_refused_without_recording_baseline(
        self, no_egress: _FakeHttp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 探针漏判 HTML 的形态（Range 请求拿到首字节是 zip、完整 GET 却被换成验证页）：
        # 形态守卫必须独立生效。若守卫缺席，TOFU 分支会把这段 HTML 的哈希当成可信基准写盘，
        # 失败要等到解压才暴露，而基准已被污染——下次拿到真包反倒可能被判成篡改。
        no_egress.add(GITHUB_URL, _FakeHttp.PROBE, _Resp(content=_zip_with_bin()[:512]))
        no_egress.add(GITHUB_URL, _FakeHttp.DOWNLOAD, _Resp(content=HTML_CHALLENGE))
        proc_calls: list[str] = []
        monkeypatch.setattr(md, "subprocess", _proc_shim({}, proc_calls))
        errors = _logs(monkeypatch, "error")

        assert md.download_ffmpeg_master(str(tmp_path), arch="win64") is False
        assert not (tmp_path / "ffmpeg_master_win64_temp.zip").exists()
        assert list(tmp_path.glob(f"{md._HASH_PREFIX}*")) == [], "中毒点：非压缩包不得进哈希记账"
        assert not (tmp_path / "ffmpeg").exists(), "拒装却仍解压 = 守卫只在解压前一刻"
        assert proc_calls == []
        assert any("不是有效 zip" in m for m in errors)

    def test_guard_is_ordered_before_hash_recording(self) -> None:
        # AST 顺序锁：把形态判定挪到「解压之前」在文本上等价（都拦住坏包），但基准已被污染。
        source = Path(md.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "download_ffmpeg_master")
        order = {
            node.func.id: node.lineno
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "_tofu_verify_or_record" in order and "is_valid_zip" in order, "形态守卫或哈希记账调用缺失"
        assert order["is_valid_zip"] < order["_tofu_verify_or_record"], "形态判定必须先于哈希记账"


# ---------------------------------------------------------------------------
# 探针三态与换源（挑战页识别）


class TestProbeClassification:
    def test_ok_challenge_and_http_error_are_three_distinct_verdicts(self, no_egress: _FakeHttp) -> None:
        # 三态被压成两态（例如把 challenge 归进 http-error）会让「跳过镜像」这条告警消失，
        # 用户以为源可用却拿不到文件；三者必须分别可观测。
        arm_url = md._candidate_urls("winarm64")[1]
        no_egress.add(GITHUB_URL, _FakeHttp.PROBE, _Resp(content=_zip_with_bin()))
        no_egress.add(FYHUB_URL, _FakeHttp.PROBE, _Resp(content=HTML_CHALLENGE, headers={"Content-Type": "text/html"}))
        no_egress.add(arm_url, _FakeHttp.PROBE, _Resp(status_code=403))

        assert md._probe(GITHUB_URL)[0] == "ok"
        assert md._probe(FYHUB_URL) == ("challenge", None)
        assert md._probe(arm_url) == ("http-error", None)

    def test_challenge_candidate_is_skipped_and_next_one_used(
        self, no_egress: _FakeHttp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 首个候选被探成挑战页时必须自动换源（而不是放弃整条兜底路径），并留下可读证据。
        payload = _zip_with_bin()
        no_egress.add(GITHUB_URL, _FakeHttp.PROBE, _Resp(content=HTML_CHALLENGE, headers={"Content-Type": "text/html"}))
        _serve_file_source(no_egress, FYHUB_URL, payload)
        monkeypatch.setattr(md, "subprocess", _proc_shim({}, []))
        warnings = _logs(monkeypatch, "warning")

        assert md.download_ffmpeg_master(str(tmp_path), arch="win64") is True
        assert no_egress.urls_of(_FakeHttp.DOWNLOAD) == [FYHUB_URL]
        assert any("人机验证页" in m and "github.com" in m for m in warnings), "跳过挑战页必须落告警并点名是哪个源"

    def test_all_candidates_unusable_returns_false_without_any_download(
        self, no_egress: _FakeHttp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for url in (GITHUB_URL, FYHUB_URL):
            no_egress.add(url, _FakeHttp.PROBE, _Resp(content=HTML_CHALLENGE, headers={"Content-Type": "text/html"}))
        errors = _logs(monkeypatch, "error")

        assert md.download_ffmpeg_master(str(tmp_path), arch="win64") is False
        assert no_egress.urls_of(_FakeHttp.DOWNLOAD) == [], "全源不可用时不得再发完整 GET"
        assert any("BtbN/FFmpeg-Builds" in m for m in errors), "必须给出手动下载指引，不能只说「失败」"


# ---------------------------------------------------------------------------
# E) _looks_like_html 的读失败判「不可信」


class TestLooksLikeHtml:
    def test_stream_read_failure_is_treated_as_untrusted(self) -> None:
        # 读失败必须判「内容不可信」：返回 False 等于「不是 HTML，放行」，流一断就误报探针 ok，
        # 本可换源的候选被当成唯一可用源。
        resp = _Resp(
            headers={"Content-Type": "application/octet-stream"}, stream_error=requests.ConnectionError("reset")
        )
        assert md._looks_like_html(_as_response(resp)) is True

    @pytest.mark.parametrize(
        "headers,body,expected",
        [
            ({"Content-Type": "text/html; charset=utf-8"}, b"", True),
            ({}, b"\n\n<!DOCTYPE html>\n<html>", True),
            ({}, b"   <HTML lang=en>", True),
            ({}, b"PK\x03\x04binaryzip", False),
        ],
    )
    def test_content_type_and_magic_bytes(self, headers: dict[str, str], body: bytes, expected: bool) -> None:
        # 只看 Content-Type 不够（某些 CDN 把挑战页误标 octet-stream），首字节标签才是主判据；
        # 但真 zip 首字节不得被误判——否则合法上游也会被跳过。
        assert md._looks_like_html(_as_response(_Resp(headers=headers, content=body))) is expected


# ---------------------------------------------------------------------------
# F) 「失败一律返回 False、不抛」的契约


class TestNoRaiseContract:
    def test_open_failure_is_normalized_to_false(self, no_egress: _FakeHttp, tmp_path: Path) -> None:
        # 探针已通过、真正失败的是 open(zip_path, "wb")：落点目录不存在（路径失效/被清理）。
        # 抛的是 FileNotFoundError（OSError 子类），既不是 FfmpegDownloadError 也不是 requests 系，
        # 故必须由 OSError 兜底，否则一路穿出到 install_ffmpeg_windows → 启动期 check_ffmpeg()。
        _serve_file_source(no_egress, GITHUB_URL, _zip_with_bin())
        assert md.download_ffmpeg_master(str(tmp_path / "no-such-dir"), arch="win64") is False

    def test_http_error_during_download_is_normalized_to_false(
        self, no_egress: _FakeHttp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 「探针 ok 但整包 4xx」= 验证页漏判或源中途 404：4xx 不是重试能解决的，直接失败，
        # 且不得留下产物、不得执行刚下载的二进制。
        payload = _zip_with_bin()
        no_egress.add(GITHUB_URL, _FakeHttp.PROBE, _Resp(content=payload))
        no_egress.add(GITHUB_URL, _FakeHttp.DOWNLOAD, _Resp(status_code=404))
        errors = _logs(monkeypatch, "error")

        assert md.download_ffmpeg_master(str(tmp_path), arch="win64") is False
        assert not (tmp_path / "ffmpeg_master_win64_temp.zip").exists()
        assert any("下载失败" in m for m in errors)


# ---------------------------------------------------------------------------
# 对照组：以上守卫不得退化成「永远拒绝」


def test_happy_path_installs_records_baseline_and_prepends_path(
    no_egress: _FakeHttp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _zip_with_bin()
    _serve_file_source(no_egress, GITHUB_URL, payload, download_headers={"Content-Length": str(len(payload))})
    proc_calls: list[str] = []
    monkeypatch.setattr(md, "subprocess", _proc_shim({("ffmpeg", "-version"): 0}, proc_calls))

    assert md.download_ffmpeg_master(str(tmp_path), arch="win64") is True
    assert (tmp_path / "ffmpeg" / "ffmpeg.exe").is_file()
    assert not (tmp_path / "ffmpeg_master_win64_temp.zip").exists(), "临时 zip 必须删净（否则下次被当「已下载」）"
    baselines = sorted(tmp_path.glob(f"{md._HASH_PREFIX}*{md._HASH_SUFFIX}"))
    assert len(baselines) == 1
    assert baselines[0].read_text(encoding="ascii").strip() == _sha256(payload)
    # 基准按构建标识分文件（Content-Length 参与标识推导），不得静默落回无标识旧命名
    assert baselines[0].name != f"{md._HASH_PREFIX}.win64{md._HASH_SUFFIX}"
    assert proc_calls == ["ffmpeg -version"]
    # PATH 前置的是**安装落点**，不是临时 zip 所在目录
    assert os.environ["PATH"].startswith(str(tmp_path / "ffmpeg") + os.pathsep)
