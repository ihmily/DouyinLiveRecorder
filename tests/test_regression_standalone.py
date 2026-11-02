# -*- coding: utf-8 -*-
# CODE_REVIEW_2026-09-22.md 第十章「孪生副本」语义漂移 + §5.1 副本侧条目的回归锁。
#
# 被测对象是 scripts/douyin_live_recorder_standalone.py —— 它按设计**不 import src/**，是
# src/scheduler.py 并发实现与 src/spider.py 部分平台解析的独立副本，因此必须有一份自己的用例。
# 本文件不推断 src/ 侧「应该是什么」，只把副本自身应满足的不变量钉住：
#   PlatformBreaker 的 half-open 回报须经 _probing/_probe_owner 门控——非探针线程 /
#             租约重授予后的陈旧探针只能入窗口、不得驱动状态迁移；样本窗口须为 deque(maxlen) +
#             挤出时增量扣减（副本旧实现用 list.pop(0)，持锁 O(n)）；
#   validate_stream_url 的 .m3u8 判定大小写不敏感，且「判走 HLS 分支」的证据是探针
#             序列（HEAD 后紧跟 Range GET），不是返回值；
#   副本的字母房间号反查须剥引号，非数字/尾斜杠形态不得把坏 roomid 发给接口。
# 另有 --selftest 子进程锁：自检是副本唯一的离线自检入口，新增判据必须真在它里面变绿。
#
# 原则：只打桩网络层（_fetch_html/_fetch_json/http_probe）与探针限速，熔断状态机、正则、
# 地址拼接一律走副本真实代码。

import ast
import copy
import importlib.util
import subprocess
import sys
import threading
import types
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_STANDALONE_PATH = _ROOT / "scripts" / "douyin_live_recorder_standalone.py"


def _load_standalone() -> Any:
    # 以模块形式加载单文件副本：顶层除常量/定义外只有 stdout/stderr 的 UTF-8 流重配
    # （真网络请求只发生在 main() 里），故可直接驱动内部函数而不走 CLI。
    spec = importlib.util.spec_from_file_location("dlr_standalone_under_test", _STANDALONE_PATH)
    assert spec and spec.loader, "无法为单文件副本构造 importlib spec"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SA = _load_standalone()


# ────────────────────────────────────────────────────────────
# PlatformBreaker 的 half-open 探针门控
# ────────────────────────────────────────────────────────────


def _open_breaker() -> Any:
    # 阈值与 src/scheduler.py 默认值同形：window=10 / fail_rate=0.5 / MIN_SAMPLES=8
    # → 连打 8 条失败样本必进入 open；cooldown=0 让冷却窗口不干扰用例节奏。
    breaker = SA.PlatformBreaker("t", window=10, fail_rate=0.5, cooldown=0.0)
    for _ in range(8):
        breaker.record(False)
    return breaker


def _report_from_other_thread(breaker: Any, success: bool) -> None:
    # 用真线程制造「另一线程的回报」——归属判据就是线程身份，用 monkeypatch 假造
    # current_thread() 等于把被测逻辑搬进测试自实现，故这里走真实线程。
    worker = threading.Thread(target=lambda: breaker.record(success))
    worker.start()
    # 审查 7.11：裸 join() 会在 record() 卡在锁上时永久挂死整轮 pytest；带上限后
    # 这条 is_alive 断言才是「回报确实已落进窗口」的凭据（join 超时时样本可能尚未 append）。
    worker.join(timeout=10)
    assert not worker.is_alive(), "回报线程未在 10s 内退出：breaker.record() 挂死，不得判绿"


class TestStandaloneBreakerProbeGate:
    def test_open_state_grants_probe_on_caller_thread(self) -> None:
        breaker = _open_breaker()
        assert breaker.state == "open", breaker.state
        assert breaker.allow() is True
        assert breaker.state == "half-open", breaker.state

    def test_in_flight_report_from_other_thread_does_not_close(self) -> None:
        # 失效形态（回灌前）：熔断转 half-open 后，一条在熔断前就已放行、此刻才收尾的普通轮次
        # record_success 被当成探针结果 → clear() 窗口 + 置 closed → 坏 CDN 立刻重新拿到全部流量。
        breaker = _open_breaker()
        assert breaker.allow() is True  # 本线程持有探针
        _report_from_other_thread(breaker, True)
        assert breaker.state == "half-open", "非探针线程的回报驱动了 half-open→closed 迁移"
        # 样本仍照常入窗口（供 closed 态复用阈值判定），只是不得改状态
        assert len(breaker._samples) == 9, breaker._samples

    def test_stale_probe_report_after_regrant_does_not_close(self) -> None:
        # 租约重授予后的**陈旧探针**同样不得替新探针关熔断：先让另一线程重获得探针，
        # 再由第 1 代持有线程回报——此刻它已不是 _probe_owner。
        breaker = _open_breaker()
        breaker.allow()  # 主线程 = 第 1 代持有者
        breaker._granted_at -= SA.PlatformBreaker.LEASE_SECONDS + 1.0  # 免真等 60 秒
        regrant: dict[str, object] = {}
        new_holder = threading.Thread(target=lambda: regrant.__setitem__("granted", breaker.allow()))
        new_holder.start()
        # 审查 7.11（同上一条口径）：join(timeout=10) 返回不等于线程已退出。线程挂在 allow() 里时
        # regrant 尚未写入，下一条断言只会以「键缺失」报错，看不出是死锁；这条 is_alive 直接钉住
        # 「第二线程确实跑完并重授予」这一前提。
        new_holder.join(timeout=10)
        assert not new_holder.is_alive(), "重授予线程未在 10s 内退出：breaker.allow() 挂死，不得判绿"
        assert regrant.get("granted") is True, regrant
        assert breaker.state == "half-open", breaker.state
        breaker.record(True)  # 第 1 代持有者（本线程）的陈旧回报
        assert breaker.state == "half-open", "陈旧探针的回报关掉了新探针的熔断"

    def test_owner_thread_report_closes_breaker(self) -> None:
        # 反向防线：门控不得把**合法**探针回报也挡掉，否则该 host 永久熔断直到进程重启。
        breaker = _open_breaker()
        assert breaker.allow() is True
        breaker.record(True)
        assert breaker.state == "closed", breaker.state
        assert len(breaker._samples) == 0, breaker._samples

    def test_failed_probe_reopens_breaker(self) -> None:
        # 反向防线：门控不得顺手废掉「探针失败 → 重新熔断」这一步（回灌后 half-open 分支
        # 若整体早退，坏 CDN 会被当成「探针没回报」而永远停在 half-open）。
        breaker = _open_breaker()
        assert breaker.allow() is True
        breaker.record(False)
        assert breaker.state == "open", breaker.state
        assert breaker.allow() is True  # cooldown=0 → 立即可再授予
        assert breaker.state == "half-open", breaker.state
        assert breaker.allow() is False, "half-open 期间必须只放一个探针"

    def test_probe_seq_advances_on_regrant(self) -> None:
        breaker = _open_breaker()
        breaker.allow()
        first = breaker._probe_seq
        breaker._granted_at -= SA.PlatformBreaker.LEASE_SECONDS + 1.0
        breaker.allow()
        assert breaker._probe_seq == first + 1, "重授予未递增探针代数，两代探针无从区分"

    def test_window_is_bounded_deque_with_incremental_count(self) -> None:
        # 副本 _push 此前是 list + pop(0)：满员时在**持锁下**做一次 O(n) 元素搬移，
        # 而 src 早已改成 deque(maxlen) + 增量扣减。这里同时锁容器形态与计数一致性。
        breaker = SA.PlatformBreaker("t", window=5, fail_rate=0.5, cooldown=0.0)
        for i in range(9):
            breaker._push(i % 2)
        assert isinstance(breaker._samples, deque), type(breaker._samples).__name__
        assert breaker._samples.maxlen == 5, breaker._samples.maxlen
        assert len(breaker._samples) == 5
        assert breaker._fail_count == sum(breaker._samples), "挤出样本时未扣减增量计数"


# ────────────────────────────────────────────────────────────
# validate_stream_url 的容器判定大小写


class TestStandaloneM3u8CaseInsensitive:
    def _probe_with(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
        # 采集**探针调用序列**：判走 HLS 分支的证据不是返回值（HEAD=200 时两条分支都会 True），
        # 而是 HEAD 之后有没有紧跟一次带 Range 的 GET。
        calls: list[tuple[str, str]] = []

        def fake_probe(
            url: str,
            *,
            method: str = "HEAD",
            headers: dict[str, str] | None = None,
            timeout: float = 8.0,
            proxy: str | None = None,
        ) -> Any:
            calls.append((method, (headers or {}).get("Range", "")))
            if method == "HEAD":
                # 多家 CDN 对 m3u8 的 HEAD 恒回 4xx（斗鱼 hw 即 405 + text/html）
                return SA.ProbeResult(405, {"content-type": "text/html"})
            return SA.ProbeResult(206, {"content-type": "application/vnd.apple.mpegurl"})

        monkeypatch.setattr(SA, "http_probe", fake_probe)
        monkeypatch.setattr(SA, "_throttle_probe", lambda url: None)
        monkeypatch.setattr(SA, "_probe_reject_until", {})
        return calls

    @pytest.mark.parametrize("suffix", [".m3u8", ".M3U8", ".M3u8"])
    def test_hls_suffix_reaches_range_get_probe(self, monkeypatch: pytest.MonkeyPatch, suffix: str) -> None:
        # 大写形态此前落进「非 m3u8」分支：content-type 启发式判 text/html → 非末位候选
        # 直接判不可达（探针误杀可用源），整轮回退或放弃录制。
        calls = self._probe_with(monkeypatch)
        ok = SA.validate_stream_url(f"https://cdn.example/live/a{suffix}", platform="斗鱼直播")
        assert ok is True, calls
        assert [m for m, _ in calls] == ["HEAD", "GET"], calls
        assert calls[1][1] == "bytes=0-0", calls

    def test_flv_suffix_does_not_fall_into_hls_branch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向防线：统一 lower() 不得把 FLV 也拖进 HLS 分支——HEAD=405 时 FLV 属「非流媒体
        # content-type」，应直接定罪而不是补一次 Range GET。
        calls = self._probe_with(monkeypatch)
        ok = SA.validate_stream_url("https://cdn.example/live/a.flv", platform="斗鱼直播")
        assert ok is False, calls
        assert [m for m, _ in calls] == ["HEAD"], calls

    def test_every_function_that_tests_m3u8_also_lowercases(self) -> None:
        # 同文件三处容器判定（校验 1 处 + 两处命令构造）必须同口径。判据按**函数**取：只要求「该
        # 函数里出现过 .lower()」，既允许就地 lower()，也允许 validate 那种「小写化一次、多处复用」。
        # 走 AST 而非扫文本：注释里也提到 .m3u8，文本比对会把它们数进来。
        tree = ast.parse(_STANDALONE_PATH.read_text(encoding="utf-8"))
        offenders: list[str] = []
        checked = 0
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            body = ast.unparse(fn)
            tests_hls = any(
                isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.In) and ".m3u8" in ast.unparse(node)
                for node in ast.walk(fn)
            )
            if not tests_hls:
                continue
            checked += 1
            if ".lower()" not in body:
                offenders.append(fn.name)
        assert checked >= 3, f".m3u8 判定所在函数少于三处（结构变了须同步本用例）: {checked}"
        assert offenders == [], f"这些函数在大小写敏感的 URL 上判容器: {offenders}"


# ────────────────────────────────────────────────────────────
# （副本侧）：字母房间号反查

_HUYA_OFF = {"data": {"profileInfo": {"nick": "虎牙主播"}, "realLiveStatus": "OFF"}}


class TestStandaloneHuyaLetterRoom:
    def _resolve(
        self,
        monkeypatch: pytest.MonkeyPatch,
        url: str,
        html: str,
    ) -> tuple[Any, list[str]]:
        seen: list[str] = []
        monkeypatch.setattr(SA, "_fetch_html", lambda target, **kw: html)

        def fake_json(api: str, **kw: object) -> dict[str, Any]:
            # 每次返回新副本：resolve_huya 只读，但共享同一 dict 会让某次用例的意外写入
            # 泄漏到后续用例（表现为「单跑绿、全量红」）。
            seen.append(api)
            return copy.deepcopy(_HUYA_OFF)

        monkeypatch.setattr(SA, "_fetch_json", fake_json)
        return SA.resolve_huya(url), seen

    def test_quoted_profile_room_strips_quotes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 页面内联 "ProfileRoom":"6030242"（字符串形态）时非贪婪捕获连引号一起收下，
        # 不剥引号则恒判非数字、白丢微信小程序兜底接口。
        quoted_page = 'x = {"ProfileRoom":"6030242","sPrivateHost":true};'
        info, seen = self._resolve(monkeypatch, "https://www.huya.com/abcroom", quoted_page)
        assert seen, f"未取得数字房间号即放弃兜底: {info.error}"
        assert "roomid=6030242" in seen[0], seen[0]
        assert "%22" not in seen[0], f"引号被当成房间号的一部分发出去了: {seen[0]}"

    def test_trailing_slash_numeric_room_still_requests(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # rstrip("/") 的行为锁：带尾斜杠的数字房间号与不带的必须走同一个 roomid。
        _info, seen = self._resolve(monkeypatch, "https://www.huya.com/6030242/", "")
        assert seen and "roomid=6030242" in seen[0], seen

    def test_regex_miss_does_not_hit_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 页面改版取不到 ProfileRoom：不得把字母号原样发给小程序接口，且须留 error 说明。
        info, seen = self._resolve(monkeypatch, "https://www.huya.com/abcroom", "no profile field here")
        assert seen == [], seen
        assert info.error, "未取得数字房间号须有可诊断的 error"


# ────────────────────────────────────────────────────────────
# --selftest：副本唯一的离线自检入口


def _run_selftest() -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(_STANDALONE_PATH), "--selftest"],
        capture_output=True,
        timeout=180,
    )


class TestStandaloneSelftest:
    def test_selftest_passes(self) -> None:
        # 按字节比较，不让解码参与判定（AGENTS「探测子进程输出一律按字节比较」）：
        # 中文 Windows 下让 text=True 读子进程输出曾直接抛 UnicodeDecodeError。
        proc = _run_selftest()
        out = proc.stdout or b""
        assert b"[FAIL]" not in out, out.decode("utf-8", errors="replace")[-2000:]
        assert b"[PASS]" in out, out[-500:]
        assert proc.returncode == 0, out.decode("utf-8", errors="replace")[-2000:]

    def test_selftest_covers_the_backfilled_invariants(self) -> None:
        # 自检脚本不得退化成「只跑老用例」：本轮新增的三条判据必须出现在自检输出里，否则说明有人
        # 把 --selftest 用例删掉而 pytest 这边察觉不到。
        out = _run_selftest().stdout or b""
        decoded = out.decode("utf-8", errors="replace")
        for needle in ("非探针线程回报不得关熔断", "陈旧探针回报不得关熔断", "大写 .M3U8"):
            assert needle in decoded, f"selftest 缺少判据 {needle!r}"


# ────────────────────────────────────────────────────────────
# 探针/录制链防线与命令日志脱敏


class TestUntrustedStreamTargetGuard:
    # ②：平台 API 候选属不可信输入面（恶意/被劫持代理、接口投毒、MITM 都可能改写）——
    # 协议白名单 + 本机/内网/云元数据目标必须在探针与 ffmpeg 之前被拒。判据是「守卫给得出拒绝
    # 理由」与「候选真的进不了探针」，不是「调用了守卫」。

    @pytest.mark.parametrize(
        "url",
        [
            "file:///C:/Users/x/secret.mp4",
            "ftp://cdn.example/a.flv",
            "data:text/plain,hello",
            "http://127.0.0.1:6379/x.flv",
            "http://169.254.169.254/latest/meta-data/",
            "http://2130706433/x.flv",
            "http://0x7f000001/x.flv",
            "http://0177.0.0.1/x.flv",
            "http://127.1/x.flv",
            "http://[::ffff:127.0.0.1]/x.flv",
            "http://100.64.0.1/x.flv",
            "http://metadata.tencentyun.com/latest/meta-data/",
            "http://box.local/x.flv",
        ],
    )
    def test_untrusted_targets_get_a_reason(self, url: str) -> None:
        # 中间五种 IP 形态正是主线该前缀黑名单的绕过载荷（离线即可判定，无 DNS）
        assert SA._untrusted_stream_target_reason(url) is not None, url

    @pytest.mark.parametrize(
        "url",
        [
            "https://cdn.example/live/a.flv?wsAuth=x",
            "https://example.com/a.m3u8",
            "https://live.douyin.com/746171898479",
        ],
    )
    def test_public_targets_pass(self, url: str) -> None:
        assert SA._untrusted_stream_target_reason(url) is None, url

    def test_select_source_url_drops_untrusted_without_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 行为锁：全部候选不可信时返回 None，且探针一次都不发（守卫在探针之前）
        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("不可信候选不允许到达探针")

        monkeypatch.setattr(SA, "http_probe", _boom)
        stream = SA.StreamInfo(platform="斗鱼直播", is_live=True, flv_urls=["file:///x/a.flv"])
        assert SA.select_source_url(stream) is None

    def test_validate_stream_url_hard_rejects_even_last_resort(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 「末位候选仅告警放行」的对象是 CDN 拒绝类误杀，不是本地文件/内网目标——
        # 不可信目标即便 last_resort=True 也必须硬拒（不吃放行语义）
        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("不可信目标不允许探针")

        monkeypatch.setattr(SA, "http_probe", _boom)
        assert SA.validate_stream_url("file:///x/a.flv", last_resort=True) is False


class TestWhitelistOpener:
    # ①：build_opener 的默认 Handler 集合不受显式 ProxyHandler 影响——file/ftp/data 三类
    # 协议都会被本地读出 200。行为锁：白名单 opener 对 file:// 给出「白名单外协议」的统一失败形态
    # （转成 RuntimeError），响应体一步都不读。

    def test_file_scheme_is_never_read_by_request_and_probe(self) -> None:
        with pytest.raises(RuntimeError):
            SA.http_request("file:///C:/Windows/win.ini")
        with pytest.raises(RuntimeError):
            SA.http_probe("file:///etc/passwd")


class TestHttpRequestBodyCapAndMaskedErrors:
    # M-14/M-13：① http_request 响应体读取必须有上限（对齐主线 8MiB）——异常/被劫持
    # 源不得把长跑进程内存打爆；② 网络层异常文本内嵌的 url 必须 strip_query——RuntimeError 会被
    # 上层原样写进日志，完整 URL 含 wsSecret 等签名 token，明文落盘违反「写入日志前必须脱敏」红线。

    class _FakeResp:
        status = 200
        headers = {"Content-Type": "text/plain"}

        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        # read(amt) 刻意忽略 amt 一次性全量返回：模拟「对端给多少就读多少」的旧形态，
        # 上限读取必须靠长度判定拦下，而不是靠分块。
        def read(self, amt: int = -1) -> bytes:
            return self._payload

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    def test_response_body_over_limit_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        big = b"x" * (SA._MAX_RESPONSE_BYTES + 1)
        monkeypatch.setattr(
            SA,
            "_build_opener",
            lambda proxy=None: types.SimpleNamespace(open=lambda req, timeout=0.0: self._FakeResp(big)),
        )
        with pytest.raises(RuntimeError, match="响应体超过"):
            SA.http_request("https://cdn.example/live.flv?wsSecret=SECRET")

    def test_error_and_probe_texts_do_not_leak_url_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(req: Any, timeout: float = 0.0) -> Any:
            raise OSError("connection reset")

        monkeypatch.setattr(SA, "_build_opener", lambda proxy=None: types.SimpleNamespace(open=_boom))
        with pytest.raises(RuntimeError) as req_err:
            SA.http_request("https://cdn.example/live.flv?wsSecret=SECRET&wsTime=1")
        assert "wsSecret" not in str(req_err.value)
        assert "url=https://cdn.example/live.flv" in str(req_err.value)
        with pytest.raises(RuntimeError) as probe_err:
            SA.http_probe("https://cdn.example/live.flv?wsSecret=SECRET")
        assert "wsSecret" not in str(probe_err.value)
        assert "url=https://cdn.example/live.flv" in str(probe_err.value)


class TestRedirectHopGuard:
    # SR-02：探针 opener 不得自动跟随重定向且每跳不复检——公网候选 302 到内网/
    # 云元数据时，旧裸 HTTPRedirectHandler 会把跳转请求真的发出去，末位候选的告警放行再把地址
    # 交给 ffmpeg。主线同层防线是探针客户端挂 src/async_http.build_sync_hop_guard；副本在
    # urllib 的重定向单点 redirect_request() 复刻同判据（复用 _untrusted_stream_target_reason）。

    @pytest.mark.parametrize("code", [301, 302, 303, 307])
    def test_redirect_to_internal_target_is_refused(self, code: int) -> None:
        handler = SA._HopGuardRedirectHandler()
        req = urllib.request.Request("https://cdn.example/live/a.flv")
        for target in (
            "http://127.0.0.1:6379/x.flv",
            "http://169.254.169.254/latest/meta-data/",
            "file:///C:/Windows/win.ini",
        ):
            with pytest.raises(urllib.error.URLError, match="重定向目标不可信"):
                handler.redirect_request(req, None, code, "Found", {}, target)

    def test_redirect_to_public_target_still_follows(self) -> None:
        # 判据只拒不可信目标，公网跳转不得被误杀（虎牙/斗鱼等 CDN 302 归一是常态）
        handler = SA._HopGuardRedirectHandler()
        req = urllib.request.Request("https://cdn.example/live/a.flv")
        new = handler.redirect_request(req, None, 302, "Found", {}, "https://cdn.example/live/b.flv")
        assert new is not None
        assert new.full_url == "https://cdn.example/live/b.flv"

    def test_opener_installs_guarded_redirect_handler(self) -> None:
        # 结构锁：opener 必须挂的是守卫子类，裸 HTTPRedirectHandler 不得再次出现——
        # 回退成裸版时本条与上面两条行为锁同红
        opener = SA._build_opener(None)
        assert any(isinstance(h, SA._HopGuardRedirectHandler) for h in opener.handlers)
        assert not any(type(h) is urllib.request.HTTPRedirectHandler for h in opener.handlers)


class TestHlsSegmentProbeLite:
    # HLS「播放列表 200」≠ 可录制——分片级探测回灌。判定原则与主线
    # _probe_hls_segment 一致（保守优先）：分片明确 4xx/5xx 判假绿；解析不出分片/异常维持列表
    # 可达；派生地址过不可信目标闸（SR-01 同判据）。

    def test_segment_404_rejects_playlist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 斗鱼 hw 事故形态：列表恒 200（CDN 动态合成），分片 404 —— 必须判假绿回退
        def _fake_request(url: str, **kwargs: Any) -> Any:
            return types.SimpleNamespace(status=200, text="#EXTM3U\n#EXTINF:4.0,\nhttps://edge.example.com/x.ts\n")

        seen: dict[str, int] = {}

        def _fake_probe(url: str, **kwargs: Any) -> Any:
            seen["seg"] = seen.get("seg", 0) + 1
            return types.SimpleNamespace(status=404)

        monkeypatch.setattr(SA, "http_request", _fake_request)
        monkeypatch.setattr(SA, "http_probe", _fake_probe)
        assert SA._probe_hls_segment_lite("https://cdn.example/a.m3u8", {}, None) is False
        assert seen.get("seg") == 1, "分片探测必须真的发出 Range GET"

    def test_internal_segment_target_rejects_without_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # SR-01 同判据：正文派生的分片指向内网时判不可达，且分片请求一个都不发
        def _fake_request(url: str, **kwargs: Any) -> Any:
            return types.SimpleNamespace(status=200, text="#EXTM3U\n#EXTINF:4.0,\nhttp://127.0.0.1:6379/x.ts\n")

        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("内网分片地址不允许发出请求")

        monkeypatch.setattr(SA, "http_request", _fake_request)
        monkeypatch.setattr(SA, "http_probe", _boom)
        assert SA._probe_hls_segment_lite("https://cdn.example/a.m3u8", {}, None) is False

    def test_unparseable_playlist_stays_reachable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 保守兜底：解析不出分片（空列表）时维持「列表可达」，交由 ffmpeg 定夺
        monkeypatch.setattr(SA, "http_request", lambda url, **k: types.SimpleNamespace(status=200, text="#EXTM3U\n"))
        assert SA._probe_hls_segment_lite("https://cdn.example/a.m3u8", {}, None) is True


class TestFfmpegCommandHardening:
    # ③：-protocol_whitelist 与主线 main.py:_build_ffmpeg_input_args 逐字同值，
    # 两处命令定义点（build_ffmpeg_cmd 规范列表 + run_ffmpeg 内联列表）同位（-i 之前）。

    def test_build_ffmpeg_cmd_carries_whitelist_before_input(self) -> None:
        cmd = SA.build_ffmpeg_cmd("ffmpeg", "http://x/y.flv", "o.flv", "B站直播", "", 0)
        wl = cmd.index("-protocol_whitelist")
        assert cmd[wl + 1] == "rtmp,crypto,http,https,tcp,tls,udp,rtp,httpproxy"
        assert wl < cmd.index("-i"), "白名单必须位于 -i 之前（输入级选项）"

    def test_both_command_definition_sites_are_in_sync(self) -> None:
        # run_ffmpeg 的内联列表无法直接调用，按源码断言两处白名单字面量逐字同值——与
        # tests/test_ffmpeg_reconnect_args.py 对同文件两处定义点的结构锁同口径。
        source = _STANDALONE_PATH.read_text(encoding="utf-8")
        literal = '"rtmp,crypto,http,https,tcp,tls,udp,rtp,httpproxy"'
        assert source.count(literal) == 2, f"白名单字面量出现 {source.count(literal)} 处（应为 2 处定义点）"


class TestFfmpegCommandLogMasking:
    # logs/ffmpeg.log 的命令原文必须脱敏——完整命令含 -headers 里的平台 Cookie 与
    # -i 的带 token 流地址，该日志 append 无轮转，明文落盘等于凭据长期泄漏。

    def test_mask_helper_replaces_headers_and_input_query(self) -> None:
        cmd = SA.build_ffmpeg_cmd(
            "ffmpeg",
            "http://x/y.flv?wsAuth=SECRETTOKEN&wsTime=1",
            "o.flv",
            "斗鱼直播",
            "DedeUserID=1; sessionid=COOKIESECRET",
            0,
        )
        masked = SA._mask_ffmpeg_cmd_for_log(cmd)
        assert "SECRETTOKEN" not in masked, "带 token 的流地址未脱敏"
        assert "COOKIESECRET" not in masked, "平台 Cookie 未脱敏"
        assert "<headers:" in masked, "headers 占位符缺失（排障形状保留判据）"
        assert "http://x/y.flv" in masked, "路径须保留以便归因"

    def test_run_ffmpeg_writes_masked_log(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 替身 Popen 走被测模块命名空间 shim（AGENTS：禁改进程级 subprocess 本体）
        class _FakePopen:
            def __class_getitem__(cls, item: Any) -> type["_FakePopen"]:
                return cls

            def __init__(self, args: list[str], **kwargs: Any) -> None:
                self.args = args
                self.pid = 4242

            def wait(self, timeout: float | None = None) -> int:
                return 0

            def poll(self) -> int:
                return 0

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.Popen = _FakePopen
        monkeypatch.setattr(SA, "subprocess", shim)
        log = tmp_path / "ffmpeg.log"
        rc, err = SA.run_ffmpeg(
            "ffmpeg",
            "http://cdn.example/live/a.flv?wsAuth=SECRETTOKEN&wsTime=1",
            str(tmp_path / "out.flv"),
            "斗鱼直播",
            "DedeUserID=1; sessionid=COOKIESECRET",
            0,
            "flv",
            str(log),
        )
        assert rc == 0, err
        text = log.read_text(encoding="utf-8")
        assert "SECRETTOKEN" not in text, "带 token 的流地址明文落盘"
        assert "COOKIESECRET" not in text, "平台 Cookie 明文落盘"
        assert "<headers:" in text, "headers 占位符缺失"
        assert "http://cdn.example/live/a.flv" in text, "路径须保留以便归因"


class TestStandaloneGracefulQuitChain:
    # （审查修复）：run_ffmpeg 的 Popen 原带 text=True，stdin 是 TextIOWrapper，
    # 而 terminate_all_ffmpeg 按主线 src/ffmpeg_proc.py 口径写 b"q"——必抛 TypeError 被写 q 处的
    # except 吞没，「写 q 优雅收尾补 moov」一级恒失效（Windows 下退化为硬杀，可产出缺 moov 的坏文件）。
    # 行为锁走真实链路：run_ffmpeg 建进程 → 登记表 → terminate_all_ffmpeg 写 q；替身只仿真「管道
    # 类型严格性」，终止链本身不在测试里重写。

    def test_terminate_writes_b_q_into_run_ffmpeg_binary_stdin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: dict[str, Any] = {}

        class _FakeStdin:
            def __init__(self, text_mode: bool) -> None:
                self.text_mode = text_mode
                self.writes: list[Any] = []

            def write(self, data: Any) -> None:
                # 复刻真实管道语义：TextIOWrapper.write(bytes) 抛 TypeError，
                # 二进制 BufferedWriter.write(str) 同样抛 TypeError。
                if self.text_mode != isinstance(data, str):
                    raise TypeError("write() argument must be " + ("str" if self.text_mode else "bytes-like object"))
                self.writes.append(data)

            def flush(self) -> None:
                pass

            def close(self) -> None:
                events["stdin_closed"] = True

        class _FakePopen:
            def __class_getitem__(cls, item: Any) -> type["_FakePopen"]:
                return cls

            def __init__(self, args: list[str], **kwargs: Any) -> None:
                self.args = args
                self.pid = 4242
                self.returncode: int | None = None
                # 按真实 subprocess 的 text/universal_newlines 口径决定 stdin 类型严格性
                self.stdin = _FakeStdin(bool(kwargs.get("text") or kwargs.get("universal_newlines")))
                events["proc"] = self

            def poll(self) -> int | None:
                return self.returncode

            def wait(self, timeout: float | None = None) -> int:
                # 无 timeout 的首次 wait 来自 run_ffmpeg 主循环：此刻进程已在登记表内，借这个时机
                # 驱动真实的 terminate_all_ffmpeg；带 timeout 的 wait 是终止链自己的宽限回收。
                if timeout is None and "killed" not in events:
                    events["killed"] = SA.terminate_all_ffmpeg()
                return 0

            def terminate(self) -> None:
                self.returncode = -15

            def kill(self) -> None:
                self.returncode = -9

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.Popen = _FakePopen
        monkeypatch.setattr(SA, "subprocess", shim)
        rc, err = SA.run_ffmpeg(
            "ffmpeg",
            "https://cdn.example/live/a.flv",
            str(tmp_path / "out.flv"),
            "斗鱼直播",
            "",
            0,
            "flv",
            str(tmp_path / "ffmpeg.log"),
        )
        assert rc == 0, err
        assert events.get("killed") == 1, f"登记表未命中在途进程: {events}"
        stdin_obj = events["proc"].stdin
        assert stdin_obj.writes == [b"q"], f"写 q 一级未真正落进 stdin（类型不匹配会被吞没）: {stdin_obj.writes}"
        # 钉死口径方向：修复必须落在「二进制管道 + 写 b"q"」侧（与主线一致），
        # 不得反向改成 text 管道 + 写 "q"——那是另一种可行实现，但不是本副本与主线的共同口径。
        assert stdin_obj.text_mode is False, "run_ffmpeg 的 stdin 必须是二进制管道（主线 ffmpeg_proc.py 同口径）"
        assert events.get("stdin_closed") is True, "写完 q（无论成败）必须关闭 stdin：部分构建要读到 EOF 才处理 q"
