# -*- coding: utf-8 -*-
# 组 C（src/utils.py + src/web_config.py + src/config_io.py + msg_push.py）回归锁。
#
# 判据一律落在「失效形态本身」，而不是「调用了某个函数」：
#   SEV-2210  mask_credentials() 对 camelCase / 全小写复合凭据键必须让**原值消失**，并给出变异判据；
#   SEV-2211  面板配置写入必须与 src.utils.atomic_write_text 是**同一份实现**，且整文件重写保留原
#             mode（Windows 条件跳过）；
#   SEV-2212  send_email 的 SSL 与 STARTTLS 两条路径都必须收到「校验证书」的 context；
#   SEV-2209  run_js_async 必须有超时预算——运行时侧 timeout= 与外层 asyncio.wait_for 双保险
#             （to_thread 的工作线程不可取消，只靠运行时侧会永久挂住 await）；
#   MIN-2244  remove_duplicate_lines 不得改写 CRLF 行尾、不得因 strip() 误删仅差空格的行、
#             编码回退分支不得使用宿主 locale。
#
# 全部离线：SMTP 用记录型假类替换（不发真实连接）；JS 运行时用桩上下文替换（不启动 node）。

import asyncio
import builtins
import inspect
import smtplib
import ssl
import stat
import sys
import threading
import time
import types
from pathlib import Path
from typing import IO, Any, cast

import pytest

import i18n  # noqa: F401  与 conftest 的恒等翻译 fixture 同源，确保断言与语言配置解耦
import msg_push
import src.utils as utils_module
from src import web_config as web_config_module
from src.utils import _SECRET_KEYS, mask_credentials

# ────────────────────────────────────────────────────────────
# SEV-2210：camelCase / 全小写复合凭据键的掩码覆盖

# (原文, 必须消失的凭据值)。每条都对应一个曾经的漏抹路径：
#   · 驼峰复合键（accessToken / wsAuth / msToken / verifyFp / idToken / refreshToken / tk）
#     —— 裸名 token/auth 的右半截前一位是字母，被左顾 (?<![A-Za-z0-9]) 整体排除；
#   · 全小写「不透明前缀 + token/key」（mytoken / apitoken）—— 既非独立参数也无大写转折；
#   · 未登记的新驼峰键（newCamelKey）—— 只能靠词内驼峰边界分支兜住。
_CAMEL_LEAK_CASES: list[tuple[str, str]] = [
    ("https://p.example/a.flv?accessToken=LEAKACCESS&t=1", "LEAKACCESS"),
    ("https://p.example/a.flv?access_token=PLAINACCESS&t=1", "PLAINACCESS"),
    ("https://p.example/a.flv?refreshToken=LEAKREFRESH", "LEAKREFRESH"),
    ("https://p.example/a.flv?idToken=LEAKIDTOKEN", "LEAKIDTOKEN"),
    ("https://p.example/a.flv?msToken=LEAKMSTOKEN", "LEAKMSTOKEN"),
    ("https://p.example/a.flv?wsAuth=LEAKWSAUTH&wsTime=6F2A", "LEAKWSAUTH"),
    ("https://p.example/a.flv?txAuth=LEAKTXAUTH", "LEAKTXAUTH"),
    ("https://p.example/a.flv?verifyFp=LEAKVERIFYFP", "LEAKVERIFYFP"),
    ("https://p.example/a.flv?tk=LEAKTK&t=1", "LEAKTK"),
    ("https://p.example/a.flv?mytoken=LEAKMYTOKEN&t=1", "LEAKMYTOKEN"),
    ("https://p.example/a.flv?apitoken=LEAKAPITOKEN&t=1", "LEAKAPITOKEN"),
    ("https://p.example/a.flv?newCamelKey=LEAKNEWCAMEL&t=1", "LEAKNEWCAMEL"),
    ("https://p.example/a.flv?csrfToken=LEAKCSRF&t=1", "LEAKCSRF"),
    # 请求头形态的驼峰键（Authorization 已覆盖，这里锁 wsAuth 的 header 写法）
    ("wsAuth: LEAKHEADERWSAUTH", "LEAKHEADERWSAUTH"),
    # header 形态、整段键名不在 _SECRET_KEYS 黑名单：只能靠驼峰边界分支命中的复合键；修复后值必须消失。
    # [历史注] 修复前 _SECRET_HEADER_RE 的 guard 错挂在驼峰分支上（与 (?<=[a-z]) 同位置互斥、分支恒死），三条曾明文落日志。
    ("myToken: LEAKHEADERMYTOK", "LEAKHEADERMYTOK"),
    ("sessionKey: LEAKSESSKEY", "LEAKSESSKEY"),
    ("newCamelKey: LEAKNEWCAMELHDR", "LEAKNEWCAMELHDR"),
    # 配套边界：shell 命令串里的带引号 header——键名前恰是引号，独立参数分支不得加 quote 排除（排除即此形态重新漏抹，tests/test_notify_script_guard.py 全组同证）
    ('--header "Authorization: Bearer LEAKQUOTEDBEARER"', "LEAKQUOTEDBEARER"),
    # JSON 体形态的驼峰键：键名整体被引号包裹、边界由闭合引号给出（(?i) 下 "accessToken" 与
    # "accesstoken" 同形）——与下面 _PUBLIC_UNTOUCHED 的反向棘轮分属两条判据，改任一侧须两边同看。
    ('{"accessToken": "LEAKJSONCAMEL", "expires_in": 7200}', "LEAKJSONCAMEL"),
    ('{"msToken":"LEAKJSONMS","keep":"ok"}', "LEAKJSONMS"),
]

# 「不得误伤」的公开形态：驼峰边界分支与 (?i) 分离若做错，design/presigned 会被当驼峰转折抹掉。
_PUBLIC_UNTOUCHED: list[str] = [
    "https://example.com/path?quality=10000&codec=h265&origin=1&design=2",
    "https://example.com/path?presigned=1&ts=1699",
    "https://live.douyin.com/746171898479",
    "https://www.huya.com/880214",
    "https://devlivepull.douyucdn.cn/live/1234567890.flv",
    "rtmp://push.example.com/app/streamid",
    "sender_name@qq.com 发件人邮箱",
    "wss://webcast100-ws-web-lf.douyin.com/webcast/im/push/v2/?room_id=1",
]


class TestCamelCaseCredentialLeak:
    @pytest.mark.parametrize(("raw", "secret"), _CAMEL_LEAK_CASES)
    def test_compound_keys_value_disappears(self, raw: str, secret: str) -> None:
        # 判据是「原值确实消失」——不是「调用了掩码」。旧测试只断言形状，故整表全绿而漏抹仍在。
        masked = mask_credentials(raw)
        assert secret not in masked
        assert "***" in masked

    @pytest.mark.parametrize("raw", _PUBLIC_UNTOUCHED)
    def test_public_urls_stay_intact(self, raw: str) -> None:
        # 反向棘轮：边界断言必须大小写敏感，否则 design 的 s|i 被折行成驼峰转折而误抹。
        assert mask_credentials(raw) == raw

    def test_all_masked_values_are_gone_from_a_combined_log_line(self) -> None:
        # 一条真实形态的选源日志里同时出现驼峰查询串 + 头形态 + JSON 体，三处都要消失
        line = (
            "https://p.example/a.flv?wsAuth=COMBOAUTH&msToken=COMBOMS "
            'header wsAuth: COMBOHEADER body {"accessToken":"COMBOJSON"}'
        )
        masked = mask_credentials(line)
        for secret in ("COMBOAUTH", "COMBOMS", "COMBOHEADER", "COMBOJSON"):
            assert secret not in masked

    def test_registered_camel_keys_are_in_the_blocklist(self) -> None:
        # 第二层修复（整段小写形式入表）必须真的落表；只靠边界分支兜不住 tk 这类无转折的短键。
        lowered = {k.lower() for k in _SECRET_KEYS}
        for key in ("accesstoken", "refreshtoken", "idtoken", "mstoken", "wsauth", "verifyfp", "tk"):
            assert key in lowered, f"{key} 未登记进 _SECRET_KEYS"

    def test_short_key_does_not_truncate_long_key(self) -> None:
        # 长名优先排序不得因新增短键（tk）被破坏：access_token 须整体成键，不得被切成 token。
        # 位置断言不可靠（短名 tk 天生排末位），故直接断言匹配语义：值必须整体消失、不残留半截。
        masked = mask_credentials("https://p.example/a.flv?access_token=LONGSECRETVALUE&t=1")
        assert "LONGSECRETVALUE" not in masked
        assert "***" in masked
        # 短键 tk 也不得漏抹（若长名优先被破坏，tk 会先被 token 的尾段消费掉）
        assert "SHORTTKVALUE" not in mask_credentials("https://p.example/a.flv?tk=SHORTTKVALUE")

    def test_camel_boundary_branch_exists_for_mutation_check(self) -> None:
        # 变异判据（可复核）：删掉 _SECRET_CAMEL_BOUNDARY 在两个 pattern 里的拼接后，
        # test_compound_keys_value_disappears 的 newCamelKey / wsAuth 等用例必须变红。
        assert utils_module._SECRET_CAMEL_BOUNDARY == r"(?<=[a-z])(?=[A-Z])"
        source = inspect.getsource(utils_module)
        assert source.count("_SECRET_CAMEL_BOUNDARY") >= 3  # 定义 + 查询串 + 请求头各一处
        assert "_SECRET_LOWER_COMPOUND_BOUNDARY" in source


# ────────────────────────────────────────────────────────────
# SEV-2211：面板配置写入必须是 utils.atomic_write_text 的薄封装


class TestWebConfigDelegatesToUtilsAtomicWrite:
    def test_web_config_write_is_the_same_implementation(self) -> None:
        # 失效形态：web_config 曾持有「第二份独立实现」（自造 tmp + open("w")），没有 mode 回填 /
        # fsync / 唯一临时名 / 失败清理四项加固。判据是**实现同一性**：用 monkeypatch 换掉 utils
        # 的符号，web_config 的写入必须跟着换（证明它真的在调用）。
        import src.web_config as wc

        called: list[tuple[str, str, str]] = []

        def _spy(file_path: str, text: str, encoding: str = "utf-8-sig") -> bool:
            called.append((file_path, text, encoding))
            return True

        original = wc.atomic_write_text
        wc.atomic_write_text = _spy  # type: ignore[assignment]
        try:
            # 只验证「调用被转发」：用不存在的路径，spy 返回 True 且真实实现不会被触达，故本用例不落任何文件（旧写法用 src/ 固定名会污染工作区）。
            target = Path("__never_written_by_regression_test__.ini")
            assert wc._atomic_write_text(target, "payload") is True
        finally:
            wc.atomic_write_text = original  # type: ignore[assignment]
        assert called == [(str(target), "payload", wc.TEXT_ENCODING)]
        # 且 web_config 内不得再有第二份 mkstemp 实体：只看可执行调用点（AST 摘 attr 名），
        # 文本匹配会命中文档性注释里的旧实现字样而假红。
        import ast

        tree = ast.parse(inspect.getsource(wc))
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    called_names.add(func.attr)
        assert "mkstemp" not in called_names

    def test_web_config_and_utils_are_the_same_object(self) -> None:
        # 更强的同一性见证：模块属性直接取自 utils（薄封装不得复制签名/默认值）
        assert web_config_module.atomic_write_text is utils_module.atomic_write_text

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows 的 os.chmod 仅影响只读位，无法断言权限位")
    def test_whole_file_rewrite_preserves_mode_via_web_config(self, tmp_path: Path) -> None:
        # 失效形态本体：旧弱化副本 os.replace 后目标继承 tmp 的 umask 0644，
        # 把 utils.update_config 对 config.ini 的 os.chmod(0o600) 收紧静默退回。
        target = tmp_path / "config.ini"
        _ = target.write_text("[A]\nk = v\n", encoding="utf-8")
        for mode in (0o600, 0o644):
            target.chmod(mode)
            assert web_config_module._atomic_write_text(target, "[A]\nk = new\n") is True
            assert stat.S_IMODE(target.stat().st_mode) == mode
            assert target.read_text(encoding="utf-8-sig") == "[A]\nk = new\n"

    def test_no_second_mkstemp_implementation_across_owned_files(self) -> None:
        # 报告要求的可复核判据（grep -rn "mkstemp" src/ 仅 utils 命中）以 AST 形式锁死——文本匹配
        # 会命中文档性注释（SEV-2211 的修复注释本身就提到旧实现），故只看可执行调用点。
        # 注意：main 必须先导入——直接 `import src.config_io` 会在其 `import main` 处触发循环导入。
        import ast

        import main  # noqa: F401  先完整初始化 main，打破 config_io<->main 的循环导入
        import src.config_io as config_io

        for module in (web_config_module, config_io):
            tree = ast.parse(inspect.getsource(module))
            called_names: set[str] = {
                node.func.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            }
            assert "mkstemp" not in called_names, f"{module.__name__} 仍持有第二份原子写实现"

    def test_write_is_atomic_across_threads(self, tmp_path: Path) -> None:
        # 旧实现的临时名只含 pid → 同进程两线程写同一目标共用同一 tmp，open("w") 互相截断。
        # 这里直接驱动真实实现（不桩网络/时间之外的任何东西），只验证「不留半写文件」。
        target = tmp_path / "cfg.ini"
        _ = target.write_text("", encoding="utf-8")
        payloads = [f"p{i}-" + ("x" * 8000) for i in range(4)]
        threads = [threading.Thread(target=web_config_module._atomic_write_text, args=(target, p)) for p in payloads]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        # join(timeout=10) 超时是静默返回的，此时目标文件可能恰好还留着
        # 上一轮的完整内容，下一条「读回来 in payloads」照样通过——挂死的写线程根本不会被发现。
        alive = [t.name for t in threads if t.is_alive()]
        assert not alive, f"原子写线程未在 10s 内退出（疑似 os.replace/mkstemp 链挂死）：{alive}"
        assert target.read_text(encoding="utf-8-sig") in payloads


# ────────────────────────────────────────────────────────────
# SEV-2212：send_email 两条 TLS 路径都必须收到校验证书的 context


class _FakeSMTPSSL:
    # 记录构造时收到的 context（真实 smtplib.SMTP_SSL 用不到网络：全部方法被桩掉）
    def __init__(self, host: str, port: int, timeout: float | None = None, context: ssl.SSLContext | None = None):
        _SSL_CALLS.append(context)

    def ehlo(self) -> tuple[int, bytes]:
        return (250, b"ok")

    def login(self, *args: object, **kwargs: object) -> tuple[int, bytes]:
        return (235, b"ok")

    def sendmail(self, *args: object, **kwargs: object) -> dict[str, object]:
        return {}

    def quit(self) -> tuple[int, bytes]:
        return (221, b"bye")


class _FakeSMTP:
    def __init__(self, host: str, port: int, timeout: float | None = None):
        pass

    def ehlo(self) -> tuple[int, bytes]:
        return (250, b"ok")

    def starttls(self, context: ssl.SSLContext | None = None) -> tuple[int, bytes]:
        _STARTTLS_CALLS.append(context)
        return (220, b"ok")

    def login(self, *args: object, **kwargs: object) -> tuple[int, bytes]:
        return (235, b"ok")

    def sendmail(self, *args: object, **kwargs: object) -> dict[str, object]:
        return {}

    def quit(self) -> tuple[int, bytes]:
        return (221, b"bye")


_SSL_CALLS: list[ssl.SSLContext | None] = []
_STARTTLS_CALLS: list[ssl.SSLContext | None] = []
# 反向见证基准：在**任何替身窗口之前**（模块导入期）记下 stdlib 本体里这两个建连类的原对象。
# [历史注] 旧写法（容器为 msg_push.smtplib 即本体）会把它们就地换掉——只比「当前引用位上是什么」看不见本体侧的漂移。
_REAL_SMTP_CLS = smtplib.SMTP
_REAL_SMTP_SSL_CLS = smtplib.SMTP_SSL


def _smtplib_shim(**overrides: Any) -> types.SimpleNamespace:
    # [历史注] MT-10：msg_push.py 顶层 `import smtplib`，`msg_push.smtplib` 即全进程唯一的 stdlib 模块
    # 本体——旧写法改的正是本体，替身窗口内同会话其它线程/库（loguru 边车、别的推送渠道）拿到的
    # SMTP/SMTP_SSL 会被一并换掉。shim 口径：浅拷贝命名空间（其余符号按**原对象**复制，故
    # `except smtplib.SMTPException` 异常类同一性不变）、只覆盖建连两个类，替身绑到 msg_push 自己的引用上。
    shim = types.SimpleNamespace(**vars(smtplib))
    for name, value in overrides.items():
        setattr(shim, name, value)
    return shim


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    # 本文件的推送用例一律离线：万一某条用例漏桩 SMTP/opener，错误消息必须点名是网络越界，
    # 而不是让 CI 在某台能连外网的机器上静默发出真实推送。
    def _deny(*args: object, **kwargs: object) -> object:
        raise AssertionError("测试不得发起真实网络请求")

    monkeypatch.setattr(msg_push.opener, "open", _deny)
    monkeypatch.setattr(msg_push, "smtplib", _smtplib_shim(SMTP_SSL=_deny, SMTP=_deny))
    # 反向见证（窗口**内**才有判定力）：stdlib 本体的两个建连类必须仍是导入期记下的原对象。
    assert smtplib.SMTP is _REAL_SMTP_CLS, "smtplib.SMTP 本体被替换：shim 形态失效，泄漏面回到全进程"
    assert smtplib.SMTP_SSL is _REAL_SMTP_SSL_CLS, "smtplib.SMTP_SSL 本体被替换：本体侧泄漏"


def _send(monkeypatch: pytest.MonkeyPatch, *, open_ssl: bool, port: str) -> None:
    _SSL_CALLS.clear()
    _STARTTLS_CALLS.clear()
    # 只替换 msg_push 模块内的 smtplib 引用（不碰 stdlib 模块对象本身）。[历史注] 2026-10-18 前两处 setattr 的容器是 msg_push.smtplib（即 stdlib 本体）。
    monkeypatch.setattr(msg_push, "smtplib", _smtplib_shim(SMTP_SSL=_FakeSMTPSSL, SMTP=_FakeSMTP))
    # 反向见证：打桩只落在 msg_push 的引用位上——stdlib 本体必须逐字仍是导入期记下的那两个原类。
    # 判据取「与导入期原对象同一」而不是「不是本次的替身」：后者看不见本体被别处换过（变异实测）。
    assert smtplib.SMTP is _REAL_SMTP_CLS, "smtplib.SMTP 本体被替换：shim 形态失效，泄漏面回到全进程"
    assert smtplib.SMTP_SSL is _REAL_SMTP_SSL_CLS, "smtplib.SMTP_SSL 本体被替换：本体侧泄漏"
    _ = msg_push.send_email(
        email_host="smtp.example.com",
        login_email="a@example.com",
        email_pass="secret",
        sender_email="a@example.com",
        sender_name="tester",
        to_email="b@example.com",
        title="t",
        content="c",
        smtp_port=port,
        open_ssl=open_ssl,
    )


class TestSmtpBothPathsVerifyCertificates:
    def test_ssl_path_gets_verifying_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 失效形态：不传 context → smtplib 回落 ssl._create_stdlib_context()（即 _create_unverified_context），
        # verify_mode=0 / check_hostname=False，中间人呈递自签证书即可取走邮箱授权码。
        _send(monkeypatch, open_ssl=True, port="465")
        assert len(_SSL_CALLS) == 1
        ctx = _SSL_CALLS[0]
        assert ctx is not None, "SMTP_SSL 未收到 context，将回落不校验的 stdlib context"
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_starttls_path_gets_verifying_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 只改 SSL 分支、漏改 starttls 即出现口径分叉（本仓 F-12 记载的形态）——两条都要锁。
        _send(monkeypatch, open_ssl=False, port="587")
        assert len(_STARTTLS_CALLS) == 1
        ctx = _STARTTLS_CALLS[0]
        assert ctx is not None, "starttls 未收到 context，STARTTLS 升级成「已加密但未认证」"
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_both_paths_share_one_context_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 两条路径必须传**同一个** ctx（报告原文：两条都要改，传同一 ctx）
        _send(monkeypatch, open_ssl=True, port="465")
        ssl_ctx = _SSL_CALLS[0]
        _send(monkeypatch, open_ssl=False, port="587")
        tls_ctx = _STARTTLS_CALLS[0]
        assert ssl_ctx is not None and tls_ctx is not None
        assert ssl_ctx.verify_mode == tls_ctx.verify_mode == ssl.CERT_REQUIRED

    def test_no_unverified_context_is_constructed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 变异判据（可复核）：把 ctx 换成 ssl._create_unverified_context() → 上面三条全红。
        # 只看可执行调用点（修复注释里必然会提到 _create_unverified_context，文本匹配会假红）。
        import ast

        tree = ast.parse(inspect.getsource(msg_push.send_email))
        called_names: set[str] = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "create_default_context" in called_names
        assert "_create_unverified_context" not in called_names
        assert "_create_stdlib_context" not in called_names


# ────────────────────────────────────────────────────────────
# MID-2251 / MID-2252 / MIN-2251：同文件内同族的历史缺陷（本轮一并锁死）


class TestMsgPushMaskingAndCleanup:
    def test_ntfy_failure_log_masks_last_segment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # MIN-2251：ntfy 的 topic 在路径末段，`https://ntfy.sh/<topic>` 的 topic 即频道口令
        # （拿到即可收通知/抢先发假消息）。钉钉/Bark/微信三处已传 mask_last_segment=True，ntfy 漏了。
        # 判据落在「**最终进日志的整条文本**」而非 kwarg 形态或脱敏函数返回值：只有把 logger.warning
        # 收到的那一行拿来看，才真正等价于「用户求助时上传的日志里有没有 topic」。
        logged: list[str] = []
        monkeypatch.setattr(msg_push.logger, "warning", lambda msg, *a, **k: logged.append(str(msg)))

        def _boom(*args: object, **kwargs: object) -> object:
            raise OSError("network down")

        monkeypatch.setattr(msg_push.opener, "open", _boom)
        _ = msg_push.ntfy("https://ntfy.sh/mytopic", title="t", content="c")
        assert logged, "ntfy 失败路径未产生任何日志"
        joined = "\n".join(logged)
        assert "mytopic" not in joined, f"ntfy 未按末段敏感渠道遮蔽，topic 明文进日志:\n{joined}"
        assert "ntfy.sh" in joined  # 主机名保留，便于定位是哪个服务失败

    def test_ntfy_real_mask_hides_topic_but_keeps_host(self) -> None:
        # 对照：直接对真实实现下判据，确认 mask_last_segment 关掉时 topic 才会漏（变异基准）。
        assert "mytopic" not in msg_push._mask_url("https://ntfy.sh/mytopic", mask_last_segment=True)
        assert "ntfy.sh" in msg_push._mask_url("https://ntfy.sh/mytopic", mask_last_segment=True)
        assert "mytopic" in msg_push._mask_url("https://ntfy.sh/mytopic", mask_last_segment=False)

    def test_send_email_quit_timeout_does_not_replace_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # finally 只吞 SMTPException，而 quit() 等 221 响应超时抛 socket.timeout（OSError
        # 子类）→ 在 finally 里抛出会替换掉已算好的成功返回值，用户重复收到同一封通知。
        class _QuitTimeoutSSL(_FakeSMTPSSL):
            def quit(self) -> tuple[int, bytes]:
                raise TimeoutError("timed out waiting for 221")

        monkeypatch.setattr(msg_push, "smtplib", _smtplib_shim(SMTP_SSL=_QuitTimeoutSSL, SMTP=_FakeSMTP))
        result = msg_push.send_email(
            email_host="smtp.example.com",
            login_email="a@example.com",
            email_pass="secret",
            sender_email="a@example.com",
            sender_name="tester",
            to_email="b@example.com",
            title="t",
            content="c",
            smtp_port="465",
            open_ssl=True,
        )
        assert result == {"success": ["b@example.com"], "error": []}

    def test_crlf_injection_is_still_rejected(self) -> None:
        # 反向棘轮：SEV-2212 的 ctx 改动不得削弱既有的头注入防线
        result = msg_push.send_email(
            email_host="smtp.example.com",
            login_email="a@example.com",
            email_pass="secret",
            sender_email="a@example.com",
            sender_name="tester",
            to_email="b@example.com",
            title="hello\r\nBcc: victim@example.com",
            content="c",
            smtp_port="465",
            open_ssl=True,
        )
        assert result == {"success": [], "error": ["b@example.com"]}


# ────────────────────────────────────────────────────────────
# SEV-2209：run_js_async 的超时预算（运行时侧 + await 侧双保险）


class _JsCtxAcceptingTimeout:
    # 桩 exejs（requirements 首选）与新版 PyExecJS 的运行时上下文：前者签名是
    # call(key, *args, timeout=None)，后者是 call(*args, **kwargs)，两者都会把 timeout 透传给子进程。
    def __init__(self, delay: float = 0.0, raise_after: float = 0.0) -> None:
        self.kwargs: dict[str, Any] = {}
        self._delay = delay
        self._raise_after = raise_after

    def call(self, key: str, *args: object, timeout: float | None = None) -> str:
        # 只记录「运行时侧真正收到的 kwargs」——判据②的落点，不是「有没有调用 call」
        self.kwargs = {"timeout": timeout}
        if self._delay:
            # 忽略 timeout 的桩：模拟「运行时侧不生效」的形态（正是回退分支的 PyExecJS 1.5.1），
            # 用来证明外层 asyncio.wait_for 是独立的第二道闸，而不是同一条闸的重复。
            time.sleep(self._delay)
        if self._raise_after:
            # 模拟「外层先超时、被放弃的工作线程随后才失败」：execjs 自己的 timeout 略晚于
            # 外层预算时，异常落在一支已无人等待的 future 上。
            time.sleep(self._raise_after)
            raise RuntimeError("late runtime-side timeout")
        return f"{key}:{args}"


class _JsCtxLegacyPyExecJS:
    # 桩「PyExecJS 1.5.1」形态：AbstractRuntimeContext.call(self, name, *args) 不接受任何关键字参数。
    # utils 顶部 `except ImportError` 回退分支拿到的就是这份签名——无条件透传 timeout 会让该环境下
    # 全部 JS 签名平台（抖音 xbogus / LiveMe / 嗨秀）以 TypeError 全废。
    def __init__(self) -> None:
        self.args: tuple[object, ...] = ()

    def call(self, name: str, *args: object) -> str:
        self.args = (name, *args)
        return "legacy-ok"


class TestRunJsAsyncTimeoutBudget:
    def test_signature_exposes_a_positive_timeout(self) -> None:
        # 判据①：预算存在、可关键字覆盖、默认值为正（与姊妹函数 run_node_script_async 同口径）
        param = inspect.signature(utils_module.run_js_async).parameters["timeout"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert isinstance(param.default, (int, float))
        assert cast("float", param.default) > 0

    @pytest.mark.asyncio
    async def test_timeout_is_forwarded_to_the_runtime_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 判据②：kwargs 里确实带 timeout。旧缺陷形态是「call(func_name, *args)」——运行时侧
        # 收到的 timeout 恒为 None，即子进程永不超时（node 卡住即整轮挂死）。
        ctx = _JsCtxAcceptingTimeout()
        monkeypatch.setattr(utils_module, "get_compiled_js", lambda _js_path: ctx)
        result = await utils_module.run_js_async("x.js", "sign", "query", "ua")
        assert result == "sign:('query', 'ua')"
        assert ctx.kwargs == {"timeout": 30.0}, "默认预算未透传"
        _ = await utils_module.run_js_async("x.js", "sign", "query", timeout=5.5)
        assert ctx.kwargs == {"timeout": 5.5}, "显式预算未透传"

    @pytest.mark.asyncio
    async def test_hanging_runtime_is_still_bounded_by_wait_for(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 判据③：运行时侧完全不生效（桩忽略 timeout）时，await 侧仍必须在预算内脱身。这里刻意让桩
        # 睡到 delay（> 预算）：少了 wait_for 就是「睡满 delay 后正常返回」，多了则在预算处抛 TimeoutError。
        ctx = _JsCtxAcceptingTimeout(delay=1.0)
        monkeypatch.setattr(utils_module, "get_compiled_js", lambda _js_path: ctx)
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            _ = await utils_module.run_js_async("x.js", "sign", "query", timeout=0.2)
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, f"未在预算内脱身（耗时 {elapsed:.2f}s）——to_thread 线程不可取消，必须靠 wait_for"
        # 被放弃的工作线程仍在睡：等它收尾，避免它的残余 sleep 跨到事件循环销毁之后
        await asyncio.sleep(1.0)

    @pytest.mark.asyncio
    async def test_abandoned_thread_failing_later_does_not_leak_a_loop_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 外层预算先到位、execjs 侧稍后才失败（两条 timeout 竞态的常见形态）时，异常落在一支已无人
        # 等待的 future 上。不主动取用的话，asyncio 会在该 future 被 GC 时向事件循环报 "Future
        # exception was never retrieved"——污染「pytest 0 警告」门禁与用户日志，且真正归因被埋掉。
        ctx = _JsCtxAcceptingTimeout(raise_after=0.4)
        monkeypatch.setattr(utils_module, "get_compiled_js", lambda _js_path: ctx)
        loop = asyncio.get_running_loop()
        reported: list[dict[str, Any]] = []
        loop.set_exception_handler(lambda _loop, context: reported.append(dict(context)))
        try:
            with pytest.raises(TimeoutError):
                _ = await utils_module.run_js_async("x.js", "sign", "query", timeout=0.1)
            # 给被放弃的工作线程时间把异常抛出来并触达 done 回调
            await asyncio.sleep(0.6)
        finally:
            loop.set_exception_handler(None)
        messages = " | ".join(str(ctx_item.get("message")) for ctx_item in reported)
        assert not reported, f"事件循环收到无人认领的异常: {messages}"

    @pytest.mark.asyncio
    async def test_legacy_runtime_without_timeout_kwarg_is_not_broken(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 兼容闸的反向锁：旧版 PyExecJS 的 call() 不收 timeout，透传即 TypeError → 该环境下所有 JS 签名平台瞬间全废。此处必须正常返回、且不带多余关键字。
        ctx = _JsCtxLegacyPyExecJS()
        monkeypatch.setattr(utils_module, "get_compiled_js", lambda _js_path: ctx)
        assert await utils_module.run_js_async("x.js", "sign", "query") == "legacy-ok"
        assert ctx.args == ("sign", "query")

    def test_runtime_capability_probe_matches_all_three_backend_shapes(self) -> None:
        def _with_kw(key: str, *args: object, timeout: float | None = None) -> str:
            return f"{key}{args}{timeout}"

        def _with_var_kw(*args: object, **kwargs: object) -> str:
            return f"{args}{kwargs}"

        def _without_kw(name: str, *args: object) -> str:
            return f"{name}{args}"

        assert utils_module._js_runtime_accepts_timeout(_with_kw) is True
        assert utils_module._js_runtime_accepts_timeout(_with_var_kw) is True
        assert utils_module._js_runtime_accepts_timeout(_without_kw) is False

    def test_await_side_has_its_own_deadline_and_does_not_swallow(self) -> None:
        # 变异判据（可复核）：
        #   · 去掉外层 asyncio.wait_for(...) → "wait_for" 不在调用点里 → 本用例红；
        #   · 在本函数里 try/except 把超时吞成返回值 → 出现 ast.Try 节点 → 同一条红。
        #     超时必须上抛，交调用方的 trace_error_decorator 兜底并计入按 host 的失败样本。
        import ast

        tree = ast.parse(inspect.getsource(utils_module.run_js_async))
        attrs = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        # 阻塞段不再走 asyncio.to_thread 的**默认**线程池——默认池由 asyncio
        # 自己管，asyncio.run 收尾会 shutdown_default_executor() 并给 300 秒 join 超时，内层超时
        # 失效时房间线程整整停摆 5 分钟。改为自有 _js_executor() + run_in_executor。
        assert {"wait_for", "run_in_executor"} <= attrs, "超时双保险被拆成单层"
        assert not any(isinstance(node, ast.Try) for node in ast.walk(tree)), "run_js_async 不得自行吞异常"


# ────────────────────────────────────────────────────────────
# MIN-2244：remove_duplicate_lines 的行尾 / 原始行 / 编码保真


class TestRemoveDuplicateLinesByteFidelity:
    # MIN-2244①②③ 一次锁死。失效面之严重：只要 URL_config.ini 存在，main() 启动期就会调用本函数
    # 一次（用户设置无法关闭），于是三处失真会在每个 Windows 用户开机那一刻静默写进真实配置——
    # 整表行尾 CRLF→LF、仅差一个空格的房间行被判重复删掉、行首缩进丢失。
    def test_crlf_indent_and_whitespace_twin_survive(self, tmp_path: Path) -> None:
        target = tmp_path / "URL_config.ini"
        payload = (
            b"\xef\xbb\xbfhttps://a.example/1\r\n"
            b"https://a.example/1 \r\n"  # 仅差一个尾随空格：旧实现按 strip() 判重会静默删掉
            b"    https://indented.example/3\r\n"  # 行首缩进：旧实现回写的是 strip 过的行
            b"https://b.example/2\r\n"
            b"https://b.example/2\r\n"  # 真重复：必须仍然被去掉
        )
        _ = target.write_bytes(payload)
        utils_module.remove_duplicate_lines(target)
        out = target.read_bytes()
        # 整体字节判据（①②③ + BOM 一次锁死）
        assert out == (
            b"\xef\xbb\xbfhttps://a.example/1\r\n"
            b"https://a.example/1 \r\n"
            b"    https://indented.example/3\r\n"
            b"https://b.example/2\r\n"
        )
        # ① 行尾未被改写：存活的 4 行仍全部以 \r\n 结束（\n 数 == \r\n 数即无裸 LF 混入）
        assert out.count(b"\r\n") == 4
        assert out.count(b"\n") == out.count(b"\r\n")
        # ② 仅差空格的行没被误删、缩进原样保留
        assert b"https://a.example/1 \r\n" in out
        assert b"    https://indented.example/3\r\n" in out
        # ③ 真重复仍去掉；BOM 读时剥一枚、写时补一枚 → 仍然只有一枚
        assert out.count(b"https://b.example/2\r\n") == 1
        assert out.count(b"\xef\xbb\xbf") == 1

    def test_terminator_shape_difference_dedupes_to_first_raw_line(self, tmp_path: Path) -> None:
        # \r\n 与 \n 结尾的同一行仍算同一行，且保留的是**首次出现**那一行的原文
        # （setdefault 而非赋值：赋值会把行尾换成后到者的形态，等于悄悄改写文件）。
        target = tmp_path / "URL_config.ini"
        _ = target.write_bytes(b"\xef\xbb\xbfa\r\na\nb\n")
        utils_module.remove_duplicate_lines(target)
        assert target.read_bytes() == b"\xef\xbb\xbfa\r\nb\n"

    def test_final_line_without_terminator_gets_one(self, tmp_path: Path) -> None:
        # 与 replace_url 同口径：末行原本无行尾时补 \n，否则后续按行追加/删除的实现
        # 会把新行拼到末行尾巴上（config_io 的行级写入按整行比较）。
        target = tmp_path / "URL_config.ini"
        _ = target.write_bytes(b"\xef\xbb\xbfa\r\nb")
        utils_module.remove_duplicate_lines(target)
        assert target.read_bytes() == b"\xef\xbb\xbfa\r\nb\n"

    def test_non_utf8_bytes_round_trip_unchanged(self, tmp_path: Path) -> None:
        # 真实非 UTF-8 字节（GBK 的「测试」= b2 e2 ca d4，在 UTF-8 下非法 → 必走回退轮）。
        # [历史注] 旧回退轮按宿主 locale 读、按 utf-8-sig 写 = 一次静默转码；现走 surrogateescape，内容字节原样落盘，不依赖宿主 locale，跨平台稳定。
        target = tmp_path / "URL_config.ini"
        _ = target.write_bytes(b"https://x.example/1\n\xb2\xe2\xca\xd4\n\xb2\xe2\xca\xd4\n")
        utils_module.remove_duplicate_lines(target)
        assert target.read_bytes() == b"\xef\xbb\xbfhttps://x.example/1\n\xb2\xe2\xca\xd4\n"

    def test_both_reads_are_explicitly_encoded_and_untranslated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 直接盯两次 open 的 kwargs：encoding 必须显式为 utf-8-sig（None 即宿主 locale）、
        # newline 必须为 ""（否则 universal newlines 翻译行尾）、回退轮必须带 surrogateescape。
        real_open = builtins.open
        reads: list[dict[str, Any]] = []

        def spy_open(file: Any, mode: str = "r", **kwargs: Any) -> IO[Any]:
            if "r" in mode:
                reads.append(dict(kwargs))
                if kwargs.get("errors") is None:
                    raise UnicodeDecodeError("utf-8-sig", b"\xff", 0, 1, "force the fallback pass")
            return real_open(file, mode, **kwargs)

        monkeypatch.setattr(builtins, "open", spy_open)
        target = tmp_path / "URL_config.ini"
        _ = target.write_bytes(b"a\nb\n")
        utils_module.remove_duplicate_lines(target)
        assert len(reads) == 2, f"回退轮未走到（或多了读轮）: {reads}"
        for kwargs in reads:
            assert kwargs.get("encoding") == "utf-8-sig", kwargs
            assert kwargs.get("newline") == "", kwargs
        assert reads[1].get("errors") == "surrogateescape", reads[1]
        assert target.read_bytes() == b"\xef\xbb\xbfa\nb\n"

    def test_every_open_call_carries_encoding_and_empty_newline(self) -> None:
        # AST 判据：以后往本函数加第三处 open 时不得漏参数（文本匹配会命中修复注释，
        # 故只看可执行调用点——与本文件 SEV-2211/MID-2252 同一手法）。
        import ast

        tree = ast.parse(inspect.getsource(utils_module.remove_duplicate_lines))
        opens = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"
        ]
        assert len(opens) >= 2, opens
        for call in opens:
            keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
            assert "encoding" in keywords, "读侧未显式指定编码"
            encoding_node = keywords["encoding"]
            assert not (
                isinstance(encoding_node, ast.Constant) and encoding_node.value is None
            ), "encoding=None 即宿主 locale"
            newline_node = keywords.get("newline")
            assert (
                isinstance(newline_node, ast.Constant) and newline_node.value == ""
            ), '缺少 newline=""（行尾会被改写）'
