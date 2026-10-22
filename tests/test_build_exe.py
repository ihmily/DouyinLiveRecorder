# build_exe.py 发布链「运行时二进制来源」的回归用例。
#
# 被测面：_FFMPEG_DOWNLOAD_URLS / _ffmpeg_source_url 与 _PINNED_RUNTIME_SHA256 的**键同构**，
# 以及 macOS arm64 下载点缺陷的形态锁。全程离线——不发起网络请求、不下载任何二进制，
# 故「某条 URL 当下是否 200」不进本文件（那属真机验证，读数见 CODE_WIKI 更新日志）。
#
# 为什么值得单独锁：旧 macOS arm64 分支按 `machine` 现场拼 URL（`getrelease-arm64/zip`，上游
# 根本没有这个产物），请求 404 → 被 _download_ffmpeg 外层的 `except Exception` 吞成一行 warning
# → Apple Silicon 的 full zip **静默不含 ffmpeg**，而构建流程照样报成功、`--dual` 照常出包。
# 三层叠加才让它不可见：
#   ① URL 不在任何清单里（拼出来的，静态检查看不出它指向不存在的端点）；
#   ② 失败被宽泛 except 捕获后只返回 False（组件级降级，不参与总判定）；
#   ③ 发布链没有对「full 包必须含 ffmpeg」做事后校验。
# 本文件锁 ①（URL 只能来自按运行时键分列的表）与表/钉定表的同构关系；②③ 属需审批的生产改动。

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import types
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parent.parent

# evermeet / gyan.dev / BtbN(github) 三家 + nodejs.org 官方 dist：来源清单与
# _FFMPEG_DOWNLOAD_URLS / _download_nodejs 的拼接主机一一对应。
# 退役来源（johnvansickle.com）必须同步移出清单——留在清单内等于给一条已退役的来源保留通行证；
# 真要再用必须在这里显式加回并说明理由。api.github.com 用于读 GitHub Release 的 assets[].digest
# （见 build_exe._PIN_SOURCE_TABLE），与产物下载同属 github.com 一家的两个端点，不是新引入的第三方。
_ALLOWED_HOSTS = frozenset({"www.gyan.dev", "evermeet.ca", "github.com", "api.github.com", "nodejs.org"})


def _load_build_exe() -> Any:
    # 与 scripts/check_runtime_pins.py 同一手法：根目录模块不在包路径内，按文件路径显式加载；
    # build_exe 的 import 期只有常量定义（main() 受 __name__ 守卫），故加载无副作用。
    spec = importlib.util.spec_from_file_location("_build_exe_runtime_probe", ROOT / "build_exe.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_exe = _load_build_exe()


def test_ffmpeg_source_table_covers_release_matrix_exactly() -> None:
    # 缺键 = 该平台构建时查不到来源；多键 = 表与矩阵漂移（没人再核对它）。两侧都要拦。
    keys = build_exe.RELEASE_RUNTIME_KEYS
    missing = [k for k in keys if k not in build_exe._FFMPEG_DOWNLOAD_URLS]
    assert not missing, f"ffmpeg 来源表缺运行时键 {missing}，该平台 full 包将无 ffmpeg"
    extra = [k for k in build_exe._FFMPEG_DOWNLOAD_URLS if k not in keys]
    assert not extra, f"ffmpeg 来源表含矩阵外的键 {extra}"


def test_source_table_and_pin_table_share_the_same_runtime_keys() -> None:
    # 两张表必须同键：钉定判定按运行时键取段，来源表若多出/少了一个键，
    # 就会出现「有来源没钉定」或「有钉定没来源」的静默半边。
    assert set(build_exe._FFMPEG_DOWNLOAD_URLS) == set(build_exe._PINNED_RUNTIME_SHA256)


def test_macos_arm64_resolves_to_the_same_evermeet_build_as_x64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_exe, "runtime_slot_key", lambda: "macos-arm64")
    url = build_exe._ffmpeg_source_url()
    assert url == build_exe._FFMPEG_DOWNLOAD_URLS["macos-x64"], "两架构必须共用同一份 evermeet 构建"
    assert re.fullmatch(r"https://evermeet\.ca/ffmpeg/ffmpeg-\d+\.\d+\.\d+\.zip", url), url


def test_macos_ffmpeg_urls_point_at_immutable_artifacts() -> None:
    # evermeet 的 Download API（getrelease[/…]/zip[/sig]）被上游以「exorbitant abuse」为由整体下架
    # （实测 410 + JSON {"code":410}），且它本来就是滚动别名——签名只钉得住「谁签的」，钉不住
    # 「哪个版本」。故 macOS 两支归档一律钉**版本化直链**：URL 与签名对象双双不可变，
    # 上游发新版不会自动跟进，属刻意的人工闸口。
    urls: dict[str, str] = {}
    for key in ("macos-x64", "macos-arm64"):
        for slot, url in (
            ("ffmpeg", build_exe._FFMPEG_DOWNLOAD_URLS[key]),
            ("ffprobe", build_exe._EXTRA_EXECUTABLE_URLS[key]["ffprobe"]),
        ):
            assert "getrelease" not in url, f"{key}/{slot} 仍指向上游已 410 下架的别名端点：{url}"
            assert re.fullmatch(rf"https://evermeet\.ca/ffmpeg/{slot}-(\d+\.\d+\.\d+)\.zip", url), url
            urls[slot] = url
    # 两架构逐槽相等：分头钉成两个版本等于让 x64/arm64 拉两条不同代次的 ffmpeg
    assert build_exe._FFMPEG_DOWNLOAD_URLS["macos-x64"] == build_exe._FFMPEG_DOWNLOAD_URLS["macos-arm64"]
    assert build_exe._EXTRA_EXECUTABLE_URLS["macos-x64"] == build_exe._EXTRA_EXECUTABLE_URLS["macos-arm64"]
    # 同一次抬版必须两支一起抬：只挪 ffmpeg 会让 full 包里 ffmpeg 与 ffprobe 跨代次共存
    ffmpeg_ver = re.search(r"-(\d+\.\d+\.\d+)\.zip", urls["ffmpeg"])
    ffprobe_ver = re.search(r"-(\d+\.\d+\.\d+)\.zip", urls["ffprobe"])
    assert ffmpeg_ver is not None and ffprobe_ver is not None, urls
    assert ffmpeg_ver.group(1) == ffprobe_ver.group(1), f"macOS 两支归档版本不一致：{urls}"


def test_linux_ffmpeg_urls_pin_an_immutable_release_tag() -> None:
    # 发布链曾红在「钉了会变的来源」上：BtbN 的 `releases/download/latest/...` 是滚动别名，同名资产
    # 被上游反复重传——当天取的 digest 在同日重发后即失配，构建在 SHA256 校验处 SystemExit，
    # 上传步骤报 `Pattern 'dist/*-lite.zip' does not match any files`。日更 autobuild 标签也不能钉
    # （上游只保留最近约两周，钉它等于预埋一次 404）。只有**月末 autobuild 标签**能让 URL 与
    # digest 双双不可变，钉定才成立。
    tags: set[str] = set()
    for key in ("linux-x64", "linux-arm64"):
        url = build_exe._FFMPEG_DOWNLOAD_URLS[key]
        assert "/releases/download/latest/" not in url, f"{key} 仍钉在滚动别名 latest 上：{url}"
        # 资产名带具体版本号（n9.0.1-11-g<hash>），与 latest 的 `n9.0-latest-` 形态互斥
        assert "n9.0-latest-" not in url, f"{key} 的资产名仍是 latest 别名形态：{url}"
        match = re.search(r"/releases/download/(autobuild-\d{4}-\d{2}-\d{2}-\d{2}-\d{2})/", url)
        assert match is not None, f"{key} 未指向带日期的不可变 autobuild 标签：{url}"
        tags.add(match.group(1))
    # 两架构必须同一个标签：分头钉成两个标签等于让 x64/arm64 拉两条不同代次的 ffmpeg
    assert len(tags) == 1, f"linux 两槽钉在了不同的 autobuild 标签上：{sorted(tags)}"


def test_broken_arm64_endpoint_cannot_be_resurrected() -> None:
    # 形态锁，且**只看字符串字面量与函数体**：注释里记录「这条端点不存在」是必要的文档，
    # 但它绝不能再成为取值——无论写进来源表还是在下载函数里按 machine 现场拼接。
    tree = ast.parse((ROOT / "build_exe.py").read_text(encoding="utf-8"), filename="build_exe.py")
    offenders = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "getrelease-arm64" in node.value
    ]
    assert not offenders, f"不存在的 evermeet arm64 端点重新出现在字面量里: {offenders}"
    download_src = inspect.getsource(build_exe._download_ffmpeg)
    assert "platform.machine" not in download_src, "URL 不得再由 platform.machine() 派生（走运行时键查表）"
    assert "_ffmpeg_source_url()" in download_src, "下载函数未从来源表取 URL，等于回到现场拼的旧形态"


def test_every_pinned_source_url_is_https_on_an_allowlisted_host() -> None:
    # 供应链侧的最低门槛：明文 http 或新增镜像域都必须显式改进本清单（并在评审里说明理由）。
    # 独立归档件（macOS 的 ffprobe）同属出站下载点，一并纳入，不得只查主表。
    urls = list(build_exe._FFMPEG_DOWNLOAD_URLS.values())
    urls += [url for slots in build_exe._EXTRA_EXECUTABLE_URLS.values() for url in slots.values()]
    assert len(urls) == len(build_exe.RELEASE_RUNTIME_KEYS) + len(build_exe._EXTRA_EXECUTABLE_URLS)
    for url in urls:
        assert url.startswith("https://"), f"非 TLS 来源: {url}"
        host = url.split("/", 3)[2]
        assert host in _ALLOWED_HOSTS, f"来源主机 {host} 不在允许清单内"
    # node 的 URL 是 f-string 现拼的，锁它的两个模板主机而不是具体版本
    node_source = (ROOT / "build_exe.py").read_text(encoding="utf-8")
    assert 'urllib.request.urlopen("https://nodejs.org/dist/index.json"' in node_source
    assert 'url = f"https://nodejs.org/dist/{version}/{filename}"' in node_source


def test_both_macos_ffmpeg_slots_stay_consistent() -> None:
    # 两个槽指向同一份产物 → 取值必须同为占位或同为同一个官方哈希。
    # 只在其中一个填值会让 macos-x64 有校验、arm64 无校验（或反之），而 --strict 只数「未钉定」。
    for slot in ("ffmpeg", "ffprobe"):
        x64 = build_exe._PINNED_RUNTIME_SHA256["macos-x64"][slot]
        arm = build_exe._PINNED_RUNTIME_SHA256["macos-arm64"][slot]
        assert x64 == arm, f"macOS 两槽的 {slot} 钉定值不一致：同一份构建被钉成了两个值"


def test_unlisted_arch_falls_back_to_family_x64_and_warns(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(build_exe, "runtime_slot_key", lambda: "windows-arm64")
    assert build_exe._ffmpeg_source_url() == build_exe._FFMPEG_DOWNLOAD_URLS["windows-x64"]
    assert "回落" in capsys.readouterr().out, "回落必须留痕，否则「拿不到本架构构建」会被伪装成正常"


def test_unknown_family_raises_instead_of_skipping_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    # 连同族 x64 都没有时**必须抛错**：静默返回空串会让 _download_file 拿不到 URL，
    # 失败又被外层 except 吞掉——正是本文件开头描述的三层失效。
    monkeypatch.setattr(build_exe, "runtime_slot_key", lambda: "freebsd-x64")
    with pytest.raises(KeyError):
        build_exe._ffmpeg_source_url()


def test_runtime_slots_cover_both_pinnable_components() -> None:
    # 钉定表按槽位分列；槽位集合与 runtime_slots_for() 不一致时，check_runtime_pins 会静默少查一类。
    assert set(build_exe.RUNTIME_SLOTS) == {"ffmpeg", "node"}
    for key, entry in build_exe._PINNED_RUNTIME_SHA256.items():
        assert set(entry) == set(build_exe.runtime_slots_for(key)), f"{key} 的槽位集合不完整"


def test_ffprobe_is_a_separate_download_point_only_on_macos() -> None:
    # evermeet 的 ffmpeg 归档里**只有 ffmpeg**（自检报「找不到非空的 ffprobe 可执行文件」却报
    # ffmpeg 可执行），所以 macOS 的 ffprobe 必须是一个独立槽位；而 gyan.dev / BtbN 的归档里两件
    # 同包，给它另立槽位等于凭空造一个没有公布值的假闸口。三张表的键集合必须互相推出，
    # 缺任一处都会让「有来源没钉定」或「有钉定没来源」半边静默。
    macos_keys = {k for k in build_exe.RELEASE_RUNTIME_KEYS if k.startswith("macos-")}
    assert set(build_exe._EXTRA_EXECUTABLE_URLS) == macos_keys, "独立归档件的登记面与 macOS 运行时键不同步"
    assert set(build_exe.runtime_slots_for("macos-x64")) == {"ffmpeg", "node", "ffprobe"}
    for key in build_exe.RELEASE_RUNTIME_KEYS:
        expected = {"ffprobe"} if key in macos_keys else set()
        pinned_extra = set(build_exe._PINNED_RUNTIME_SHA256[key]) - set(build_exe.RUNTIME_SLOTS)
        assert pinned_extra == expected, f"{key} 的额外钉定槽位 {pinned_extra} 与实际下载点 {expected} 不符"
        assert ("ffprobe" in build_exe.runtime_slots_for(key)) is (key in macos_keys)


def test_macos_ffprobe_signature_entry_matches_its_artifact_url() -> None:
    # 钉的是「谁签的」，登记错了签名 URL 就等于这一档从未真正管住过。两架构同一份产物 → 同值。
    for key in ("macos-x64", "macos-arm64"):
        sig_url, fingerprint = build_exe._RUNTIME_GPG_SIGNATURES[key]["ffprobe"]
        assert sig_url == f"{build_exe._EXTRA_EXECUTABLE_URLS[key]['ffprobe']}.sig", sig_url
        assert (
            fingerprint == build_exe._RUNTIME_GPG_SIGNATURES[key]["ffmpeg"][1]
        ), "ffprobe 与 ffmpeg 同页同钥，另立指纹等于引入第二把未核实的钥匙"
        # 实测：两份 .sig 的签发者都是主钥名下的同一把子钥（判据见 build_exe 侧注释）
        assert fingerprint == _PRIMARY_FPR


def test_is_pinned_shape_rule_rejects_every_placeholder_form() -> None:
    # SEV-10 的「已钉定」唯一判据是形状（64 位小写十六进制）：占位串、空串、大写、缺位、
    # 带空白一律算未钉定。形状关把不住，后面所有「缺钉定即终止构建」的语义都无从谈起。
    is_pinned = build_exe._is_pinned
    assert is_pinned("a" * 64) is True
    for bad in (
        build_exe.UNVERIFIED_PIN,
        build_exe.OFFICIAL_SIGNATURE_PIN,  # 签名档标记不得被当成「已钉定的哈希」，否则哈希分支会拿它去比 digest
        "",
        "A" * 64,
        "a" * 63,
        "z" * 64,
        "  " + "a" * 64 + " ",
    ):
        assert is_pinned(bad) is False, f"形状判定对 {bad!r} 放宽了"


# ---------------------------------------------------------------------------
# P-2：官方 GPG 签名核验（2026-09-22 批准引入 gnupg）
#
# 全部离线：gpg 与 urlopen 都被打桩。桩只替换 build_exe 的**模块全局名**（urllib / _run_gpg），
# 绝不改 stdlib 模块本体。
# ---------------------------------------------------------------------------

_PRIMARY_FPR = "20F6EA3E0CFD6B4C53447A73476C4B611A660874"
_SIGNING_SUBKEY_FPR = "31B0C6D7E8F90A1B2C3D4E5F60718293A4B5C6D7"
_UNRELATED_FPR = "99AABBCCDDEEFF00112233445566778899AABBCC"


def _colon_fpr_line(fingerprint: str) -> str:
    # gpg --with-colons 的 fpr 记录：指纹在第 10 字段（下标 9）
    fields = [""] * 10
    fields[0] = "fpr"
    fields[9] = fingerprint
    return ":".join(fields)


def _keyring_record(*fingerprints: str) -> bytes:
    lines = [f"pub:-:4096:1:1600000000:::{fingerprints[0]}:"] + [_colon_fpr_line(f) for f in fingerprints]
    return ("\n".join(lines) + "\n").encode("ascii")


class _FakeResponse:
    # 桩同时服务两种调用方：_verify_gpg_artifact 整块 read()，而 _download_file 按 read(65536)
    # 分块循环读到空字节为止，并要 headers["Content-Length"]。故这里必须**逐次排空**——
    # 每次返回同一份 payload 会让下载循环永不退出。
    headers: dict[str, str] = {}

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self, size: int = -1) -> bytes:
        take = len(self._payload) if size is None or size < 0 else min(size, len(self._payload))
        chunk, self._payload = self._payload[:take], self._payload[take:]
        return chunk

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def _install_fake_urlopen(monkeypatch: pytest.MonkeyPatch, payload: bytes | OSError) -> list[str]:
    seen: list[str] = []

    def fake_urlopen(url: str, *args: Any, **kwargs: Any) -> Any:
        seen.append(url)
        if isinstance(payload, OSError):
            raise payload
        return _FakeResponse(payload)

    monkeypatch.setattr(build_exe, "urllib", types.SimpleNamespace(request=types.SimpleNamespace(urlopen=fake_urlopen)))
    return seen


def _install_fake_gpg(
    monkeypatch: pytest.MonkeyPatch,
    *,
    keyring: bytes,
    verify_status: bytes,
    import_available: bool = True,
) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run_gpg(args: list[str], timeout: int = 180) -> Any:
        calls.append(args)
        if "--recv-keys" in args:
            if not import_available:
                return None  # None == gpg 这个工具不可用（未安装/超时/起不动）
            return types.SimpleNamespace(stdout=b"", returncode=0)
        if "--list-keys" in args:
            return types.SimpleNamespace(stdout=keyring, returncode=0)
        return types.SimpleNamespace(stdout=verify_status, returncode=0)

    monkeypatch.setattr(build_exe, "_run_gpg", fake_run_gpg)
    return calls


def _macos_release_env(monkeypatch: pytest.MonkeyPatch, *, release: bool) -> None:
    monkeypatch.setattr(build_exe, "runtime_slot_key", lambda: "macos-arm64")
    monkeypatch.setattr(build_exe, "require_pinned_hashes", lambda: release)


def _artifact_url_for_slot(key: str, slot: str) -> str:
    # 签名 URL 的同构校验要先拿到「该槽的产物 URL」。ffprobe 不在 _FFMPEG_DOWNLOAD_URLS 里，
    # 它在 _EXTRA_EXECUTABLE_URLS（依据见该表注释），查不到就该 KeyError 而不是回空串——
    # 回空串会让 `sig_url == f"{artifact}.sig"` 变成和 ".sig" 比，永远红或永远假绿。
    # build_exe 是动态加载的 Any，须显式 cast 收窄以满足 warn_return_any。
    if slot == "ffmpeg":
        return cast(str, build_exe._FFMPEG_DOWNLOAD_URLS[key])
    return cast(str, build_exe._EXTRA_EXECUTABLE_URLS[key][slot])


def test_gpg_config_shape_and_source_consistency() -> None:
    # 只登记「上游确实公布 detached 签名」的槽位；且签名 URL 必须是产物 URL + ".sig"
    # （evermeet 2026-10-18 起的形态；旧约定「产物 URL + /sig」随 Download API 一起 410 下架），
    # 否则改了产物来源却忘了改签名来源，验签会长期假失败。
    for key, slots in build_exe._RUNTIME_GPG_SIGNATURES.items():
        assert key in build_exe._FFMPEG_DOWNLOAD_URLS, f"签名配置指向了不存在的运行时键 {key}"
        for slot, (sig_url, fingerprint) in slots.items():
            assert slot in build_exe.runtime_slots_for(key)
            assert re.fullmatch(r"[0-9a-fA-F]{40}", fingerprint), f"{key}/{slot} 指纹不是 40 位十六进制"
            artifact = _artifact_url_for_slot(key, slot)
            assert sig_url == f"{artifact}.sig", f"{key}/{slot} 签名 URL 与产物 URL 脱钩: {sig_url}"


def test_gpg_verification_is_skipped_for_slots_without_official_sig(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # gyan.dev / BtbN 不公布签名：未登记的槽位必须**一次网络与进程都不碰**，
    # 而不是「试一下失败后放行」——后者会把「无物可验」伪装成「验过了」。
    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("未登记签名的槽位不得发起核验")

    monkeypatch.setattr(build_exe, "urllib", types.SimpleNamespace(request=types.SimpleNamespace(urlopen=explode)))
    monkeypatch.setattr(build_exe, "_run_gpg", explode)
    monkeypatch.setattr(build_exe, "runtime_slot_key", lambda: "windows-x64")
    build_exe._verify_official_signature(tmp_path / "a.zip", "ffmpeg", "ffmpeg (gyan.dev)")


def test_gpg_accepts_signature_made_by_pinned_keys_subkey(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # VALIDSIG 报的是**实际签名的子钥**指纹。逐字比主钥会把合法产物判失败（假红），
    # 所以判据必须是「签名钥匙属于那把钥匙的主钥/子钥集合」。
    artifact = tmp_path / "ffmpeg.zip"
    artifact.write_bytes(b"payload")
    _macos_release_env(monkeypatch, release=True)
    _install_fake_urlopen(monkeypatch, b"detached-sig")
    status = (
        b"[GNUPG:] GOODSIG 1234567890ABCDEF someone@example.org\n"
        b"[GNUPG:] VALIDSIG " + _SIGNING_SUBKEY_FPR.lower().encode("ascii") + b" 1600000000 1600000000 0 4 0 1 22 00\n"
    )
    calls = _install_fake_gpg(
        monkeypatch, keyring=_keyring_record(_PRIMARY_FPR, _SIGNING_SUBKEY_FPR), verify_status=status
    )
    build_exe._verify_official_signature(artifact, "ffmpeg", "ffmpeg (evermeet)")
    assert any("--verify" in c for c in calls), "根本没跑 gpg --verify，上一条断言成了自证"


@pytest.mark.parametrize(
    ("keyring", "verify_status"),
    [
        # 签名者不属于钉定钥匙
        (
            _keyring_record(_PRIMARY_FPR, _SIGNING_SUBKEY_FPR),
            b"[GNUPG:] GOODSIG x y\n[GNUPG:] VALIDSIG " + _UNRELATED_FPR.encode() + b" 1 1 0 4 0 1 22 00\n",
        ),
        # 明确的坏签名
        (_keyring_record(_PRIMARY_FPR), b"[GNUPG:] BADSIG 1234567890ABCDEF someone@example.org\n"),
        # 只有 GOODSIG 没有 VALIDSIG（状态行不完整）
        (_keyring_record(_PRIMARY_FPR), b"[GNUPG:] GOODSIG 1234567890ABCDEF someone@example.org\n"),
        # 钥匙环里没有钉定的那把主钥（import 拿到别的钥匙）
        (
            _keyring_record(_UNRELATED_FPR),
            b"[GNUPG:] GOODSIG x y\n[GNUPG:] VALIDSIG " + _UNRELATED_FPR.encode() + b" 1 1 0 4 0 1 22 00\n",
        ),
    ],
    ids=["signer-not-pinned", "badsig", "no-validsig", "wrong-key-in-ring"],
)
def test_gpg_rejects_every_untrustworthy_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, keyring: bytes, verify_status: bytes
) -> None:
    artifact = tmp_path / "ffmpeg.zip"
    artifact.write_bytes(b"payload")
    _macos_release_env(monkeypatch, release=True)
    _install_fake_urlopen(monkeypatch, b"detached-sig")
    _install_fake_gpg(monkeypatch, keyring=keyring, verify_status=verify_status)
    with pytest.raises(SystemExit):
        build_exe._verify_official_signature(artifact, "ffmpeg", "ffmpeg (evermeet)")


@pytest.mark.parametrize("release", [True, False], ids=["release", "local"])
def test_gpg_tool_or_sig_missing_never_passes_silently(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, release: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    # 「gpg 不可用」与「取不到签名文件」都属工具/网络缺失：发布路径必须终止，本地路径必须
    # **留一条明确的跳过日志**——两侧都不许出现「什么都没发生」的形态。
    artifact = tmp_path / "ffmpeg.zip"
    artifact.write_bytes(b"payload")
    _macos_release_env(monkeypatch, release=release)

    _install_fake_urlopen(monkeypatch, OSError("network down"))
    _install_fake_gpg(monkeypatch, keyring=_keyring_record(_PRIMARY_FPR), verify_status=b"")
    if release:
        with pytest.raises(SystemExit):
            build_exe._verify_official_signature(artifact, "ffmpeg", "ffmpeg (evermeet)")
    else:
        build_exe._verify_official_signature(artifact, "ffmpeg", "ffmpeg (evermeet)")
        assert "签名核验跳过" in capsys.readouterr().out

    _install_fake_urlopen(monkeypatch, b"detached-sig")
    _install_fake_gpg(monkeypatch, keyring=_keyring_record(_PRIMARY_FPR), verify_status=b"", import_available=False)
    if release:
        with pytest.raises(SystemExit):
            build_exe._verify_official_signature(artifact, "ffmpeg", "ffmpeg (evermeet)")
    else:
        build_exe._verify_official_signature(artifact, "ffmpeg", "ffmpeg (evermeet)")
        assert "gnupg 不可用" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# P-5：full 包产物自检
# ---------------------------------------------------------------------------


def test_verify_runtime_binaries_flags_every_missing_component(tmp_path: Path) -> None:
    problems = build_exe.verify_runtime_binaries(tmp_path)
    text = "\n".join(problems)
    assert len(problems) == 3, problems
    for name in ("ffmpeg", "ffprobe", "node"):
        assert name in text, f"未报告缺失组件 {name}: {text}"


def test_verify_runtime_binaries_accepts_nested_bin_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # node 的 tar.gz 解压后是 bin/node，ffmpeg 的 Windows 包是 bin/ffmpeg.exe：
    # 递归匹配才不会把布局差异误判成缺件（那会让 macOS/Linux 构建无端变红）。
    (tmp_path / "ffmpeg" / "bin").mkdir(parents=True)
    (tmp_path / "ffmpeg" / "bin" / "ffmpeg").write_bytes(b"x" * 10)
    (tmp_path / "ffmpeg" / "ffprobe").write_bytes(b"y" * 10)
    (tmp_path / "node" / "bin").mkdir(parents=True)
    (tmp_path / "node" / "bin" / "node").write_bytes(b"z" * 10)
    monkeypatch.setattr(build_exe, "_probe_runnable", lambda binary, component: None)
    assert build_exe.verify_runtime_binaries(tmp_path) == []


def test_zero_byte_runtime_binary_is_not_counted_as_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 下载被截断时文件存在但 0 字节；只看存在性会判「就绪」。
    (tmp_path / "ffmpeg").mkdir()
    (tmp_path / "ffmpeg" / "ffmpeg").write_bytes(b"")
    (tmp_path / "ffmpeg" / "ffprobe").write_bytes(b"ok")
    (tmp_path / "node").mkdir()
    (tmp_path / "node" / "node").write_bytes(b"ok")
    monkeypatch.setattr(build_exe, "_probe_runnable", lambda binary, component: None)
    problems = build_exe.verify_runtime_binaries(tmp_path)
    assert len(problems) == 1 and "ffmpeg" in problems[0], problems


def test_unrunnable_binary_is_reported_with_upstream_reason(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 文件在、跑不动（macOS 缺 dylib 闭包 / 无 Rosetta）必须被点名，且报错里带上游第一行原因。
    # 顺带锁「按字节读输出」：桩返回的是 stderr **bytes**。
    for rel in ("ffmpeg/ffmpeg", "ffmpeg/ffprobe", "node/node"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"binary")
    fake = types.SimpleNamespace(**vars(subprocess))
    fake.run = lambda *args, **kwargs: types.SimpleNamespace(
        returncode=1, stdout=b"", stderr=b"dyld: Library not loaded: /opt/homebrew/lib/libx265.215.dylib\n"
    )
    monkeypatch.setattr(build_exe, "subprocess", fake)
    problems = build_exe.verify_runtime_binaries(tmp_path)
    assert len(problems) == 3, problems
    assert any("libx265" in p for p in problems), problems


def test_version_probe_arg_is_per_component(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 三平台 build-release 曾同因红：探针取值对三件套共用 `-version`，而 node 的 CLI 解析器把
    # `-version` 判成非法选项（`bad option: -version` + 返回码 1），**每一支 full 包**都卡在产物自检上。
    # 反向「统一改成 --version」同样是错的（实测 `ffmpeg --version` 返回码 8，`ffmpeg -version` 返回码 0），
    # 故这里锁的是**逐件取值**：node --version 合规、node -version 非法。并成一个常量，本用例即红。
    for rel in ("ffmpeg/ffmpeg", "ffmpeg/ffprobe", "node/node"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"binary")
    argvs: list[list[str]] = []
    fake = types.SimpleNamespace(**vars(subprocess))

    def record_run(cmd: list[str], *args: Any, **kwargs: Any) -> Any:
        argvs.append([str(part) for part in cmd])
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    fake.run = record_run
    monkeypatch.setattr(build_exe, "subprocess", fake)
    assert build_exe.verify_runtime_binaries(tmp_path) == [], "真实探针把可用产物判成了缺件"
    flags = {Path(argv[0]).name: argv[1] for argv in argvs}
    assert flags == {"ffmpeg": "-version", "ffprobe": "-version", "node": "--version"}, flags
    assert len(argvs) == 3, "有组件没被探测"


@pytest.mark.parametrize("release", [True, False], ids=["release", "local"])
def test_dual_full_aborts_on_release_path_when_runtime_incomplete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, release: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    # 这一条锁的是本轮缺陷的收口：_download_ffmpeg 返回 False 不再等于「这轮构建可以出包」。
    monkeypatch.setattr(build_exe, "_download_ffmpeg", lambda target: False)
    monkeypatch.setattr(build_exe, "_download_nodejs", lambda target: False)
    monkeypatch.setattr(build_exe, "require_pinned_hashes", lambda: release)
    if release:
        with pytest.raises(SystemExit):
            build_exe.download_runtime_binaries(tmp_path)
    else:
        build_exe.download_runtime_binaries(tmp_path)
        assert "不得用于发布" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# W1（2026-09-22 批准）：第 4 类完整性口径「源码可复现构建」
# 锁的是两件事：满足条件不可被标记单独糊过去；声明第 4 类的槽位不得再走下载路径。
# ---------------------------------------------------------------------------

_MARKER = build_exe.SOURCE_BUILD_PROVENANCE
_EVIDENCE_OK = {"source_sha256": "b" * 64, "recipe_sha256": "c" * 64, "provenance_ref": "build-release.yml@abc"}


@pytest.mark.parametrize(
    ("value", "evidence", "expected"),
    [
        ("a" * 64, {}, True),  # 常规：已钉定的官方哈希
        ("", {}, False),
        (_MARKER, {}, False),  # 光有标记 = 不满足
        (_MARKER, {"source_sha256": "b" * 64, "recipe_sha256": "c" * 64, "provenance_ref": ""}, False),
        (_MARKER, {"source_sha256": "b" * 63, "recipe_sha256": "c" * 64, "provenance_ref": "w@1"}, False),
        (_MARKER, _EVIDENCE_OK, True),  # 三件证据齐备且过形状关
        ("a" * 64, _EVIDENCE_OK, True),  # 钉定哈希不受证据表影响（两条路任一成立即管住）
    ],
    ids=["pinned", "empty", "marker-only", "no-ref", "short-source", "full-evidence", "pinned-plus-evidence"],
)
def test_slot_is_gated_is_the_single_authority_predicate(
    monkeypatch: pytest.MonkeyPatch, value: str, evidence: dict[str, str], expected: bool
) -> None:
    monkeypatch.setattr(build_exe, "_SOURCE_BUILD_EVIDENCE", {"macos-arm64": {"ffmpeg": dict(evidence)}})
    assert build_exe._slot_is_gated(value, "macos-arm64", "ffmpeg") is expected


def test_table_never_declares_the_fourth_class_without_evidence() -> None:
    # 永久不变量：谁启用第 4 类，就必须同时把三件证据填进 _SOURCE_BUILD_EVIDENCE，
    # 否则「更容易填的标记」就成了绕闸通道（本用例即那条防线的静态面）。
    offenders = [
        f"{key}/{slot}"
        for key, entry in build_exe._PINNED_RUNTIME_SHA256.items()
        for slot, value in entry.items()
        if value == _MARKER and not build_exe._is_source_build_satisfied(value, key, slot)
    ]
    assert not offenders, f"以下槽位声明第 4 类但证据不齐: {offenders}"


@pytest.mark.parametrize("release", [True, False], ids=["release", "local"])
def test_declared_source_build_slot_refuses_to_download_on_both_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, release: bool
) -> None:
    # 第 4 类的产物应由构建步骤产出，不是从上游拉：走到下载就必须终止，**两侧都一样**
    # （本地路径若放行，等于「换个标记就把校验整个跳过」——这正是本类最容易被误用的地方）。
    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("第 4 类槽位不得发起下载")

    monkeypatch.setattr(build_exe, "require_pinned_hashes", lambda: release)
    monkeypatch.setattr(build_exe, "runtime_slot_key", lambda: "macos-arm64")
    monkeypatch.setattr(build_exe, "_PINNED_RUNTIME_SHA256", {"macos-arm64": {"ffmpeg": _MARKER, "node": "a" * 64}})
    monkeypatch.setattr(build_exe, "urllib", types.SimpleNamespace(request=types.SimpleNamespace(urlopen=explode)))
    with pytest.raises(SystemExit) as caught:
        build_exe._download_file(
            "https://example.invalid/x.zip", tmp_path / "x.zip", "ffmpeg (evermeet)", slot="ffmpeg"
        )
    assert "SOURCE-BUILD-PROVENANCE" in str(caught.value)


def test_env_injected_marker_also_refuses_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 标记也可能由 CI 经 DLR_RUNTIME_SHA256 注入（build-release.yml 的透传通道），
    # 拒下载判定必须看**合并环境变量后的实际取值**，而不是只看内置表。
    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("第 4 类槽位不得发起下载")

    payload = '{"macos-arm64": {"ffmpeg": "%s"}}' % _MARKER
    monkeypatch.setenv("DLR_RUNTIME_SHA256", payload)
    monkeypatch.setattr(build_exe, "runtime_slot_key", lambda: "macos-arm64")
    monkeypatch.setattr(build_exe, "require_pinned_hashes", lambda: False)
    monkeypatch.setattr(build_exe, "urllib", types.SimpleNamespace(request=types.SimpleNamespace(urlopen=explode)))
    with pytest.raises(SystemExit):
        build_exe._download_file(
            "https://example.invalid/x.zip", tmp_path / "x.zip", "ffmpeg (evermeet)", slot="ffmpeg"
        )


def test_pinned_slot_still_downloads_and_verifies_normally(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 反向防线：别把「拒下载」写成对所有槽位生效——那会让已钉定的 windows 构建悄悄拿不到 ffmpeg。
    payload = b"chunk" * 4
    digest = hashlib.sha256(payload).hexdigest()
    dest = tmp_path / "artifact.zip"
    remaining = [payload]

    class _Resp:
        headers = {"Content-Length": str(len(payload))}

        def read(self, size: int = -1) -> bytes:
            return remaining.pop(0) if remaining else b""

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

    monkeypatch.setattr(build_exe, "runtime_slot_key", lambda: "windows-x64")
    monkeypatch.setattr(build_exe, "require_pinned_hashes", lambda: True)
    monkeypatch.setattr(build_exe, "_PINNED_RUNTIME_SHA256", {"windows-x64": {"ffmpeg": digest, "node": "a" * 64}})
    monkeypatch.setattr(
        build_exe, "urllib", types.SimpleNamespace(request=types.SimpleNamespace(urlopen=lambda *a, **k: _Resp()))
    )
    seen: list[tuple] = []
    monkeypatch.setattr(build_exe, "_verify_official_signature", lambda *a: seen.append(a))
    build_exe._download_file("https://example.invalid/x.zip", dest, "ffmpeg (gyan.dev)", slot="ffmpeg")
    assert dest.read_bytes() == payload
    assert seen == [(dest, "ffmpeg", "ffmpeg (gyan.dev)")], "钉定通过后才应触发验签，且不得对未核过内容的产物验签"


# ---------------------------------------------------------------------------
# 2026-09-26 官方签名档（macOS 两槽）：上游不公布 SHA256，判据 = 官方分离 GPG 签名
# + 带外钉死的 40 位主钥指纹。下面各锁分别拦一种具体失效形态：
#   ① 「光有标记就拿免检」——标记比 64 位十六进制更容易填，缺登记 / 缺形状必须同等拦下；
#   ② SEV-2221「验签代码写在下载后、闸口卡在下载前」——若签名档槽位不在哈希分支之外也验签，
#      这一档在真实构建路径上永不可达，看着有防线其实一次都没跑过；
#   ③ 签名档**没有哈希兜底**，故发布路径上「gpg 不可用 / 验签判坏」必须终止，不得降级放行。
# 全程离线：urlopen 与 _run_gpg 一律打桩（桩替换 build_exe 的模块全局名，不改 stdlib 本体）。
# ---------------------------------------------------------------------------

_SIG_MARKER = build_exe.OFFICIAL_SIGNATURE_PIN
_GOOD_VERIFY_STATUS = (
    b"[GNUPG:] GOODSIG 1234567890ABCDEF someone@example.org\n"
    b"[GNUPG:] VALIDSIG " + _PRIMARY_FPR.lower().encode("ascii") + b" 1600000000 1600000000 0 4 0 1 22 00\n"
)


@pytest.mark.parametrize(
    ("key", "slot", "expected"),
    [
        ("macos-arm64", "ffmpeg", True),
        ("macos-x64", "ffmpeg", True),
        ("macos-arm64", "node", False),  # 同一运行时键的另一槽没登记签名 → 不许蹭同键的登记
        ("linux-x64", "ffmpeg", False),  # BtbN 不公布 detached 签名，无物可验
        ("windows-x64", "ffmpeg", False),
    ],
    ids=["arm64-ffmpeg", "x64-ffmpeg", "同键另一槽", "linux-无签名", "windows-无签名"],
)
def test_signature_mode_is_satisfied_only_by_a_registered_slot(key: str, slot: str, expected: bool) -> None:
    # 与第 4 类同一条防线：标记本身绝不构成放行，必须「该槽确有登记」且「指纹形状对」。
    assert build_exe._is_signature_satisfied(_SIG_MARKER, key, slot) is expected
    # 唯一口径必须同步认下这一档：_slot_is_gated 若漏并，--strict 会把已按签名管住的槽判成未钉定。
    assert build_exe._slot_is_gated(_SIG_MARKER, key, slot) is expected


def test_signature_mode_marker_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    # _pinned_slots() 会把内置表与 DLR_RUNTIME_SHA256 注入值统一 .strip().lower()；
    # 若标记按原样逐字比，CI 注入通道就永远认不出签名档（与 test_env_injected_marker_also_refuses_download
    # 抓出来的第 4 类同一形态）。
    assert build_exe._is_signature_satisfied(_SIG_MARKER.lower(), "macos-arm64", "ffmpeg") is True


@pytest.mark.parametrize(
    "bad_fpr",
    ["", "20F6EA3E", "z" * 40, "20F6EA3E0CFD6B4C53447A73476C4B611A66087"],
    ids=["空指纹", "过短", "非十六进制", "39位"],
)
def test_signature_mode_rejects_malformed_fingerprint(monkeypatch: pytest.MonkeyPatch, bad_fpr: str) -> None:
    # 指纹形状关把不住，「登记一把不存在的钥匙」就成了新的绕闸通道。
    monkeypatch.setitem(
        build_exe._RUNTIME_GPG_SIGNATURES, "macos-arm64", {"ffmpeg": ("https://example.invalid/sig", bad_fpr)}
    )
    assert build_exe._is_signature_satisfied(_SIG_MARKER, "macos-arm64", "ffmpeg") is False
    assert build_exe._slot_is_gated(_SIG_MARKER, "macos-arm64", "ffmpeg") is False


def test_table_never_declares_signature_mode_without_satisfaction() -> None:
    # 永久不变量（对齐 test_table_never_declares_the_fourth_class_without_evidence）：
    # 谁把某槽改成签名档，就必须同批把签名 URL 与指纹登记进 _RUNTIME_GPG_SIGNATURES。
    offenders = [
        f"{key}/{slot}"
        for key, entry in build_exe._PINNED_RUNTIME_SHA256.items()
        for slot, value in entry.items()
        if value == _SIG_MARKER and not build_exe._is_signature_satisfied(value, key, slot)
    ]
    assert not offenders, f"以下槽位声明官方签名档但未满足登记/指纹条件: {offenders}"


@pytest.mark.parametrize("release", [True, False], ids=["release", "local"])
def test_signature_mode_slot_downloads_and_actually_verifies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, release: bool
) -> None:
    # SEV-2221 的可达性锁：签名档槽位必须**真的走到验签**。把验签调用点挪回「只在哈希已过的分支里」
    # （改造前形态）→ 本用例红，因为 macOS 槽值永远过不了 _is_pinned。
    dest = tmp_path / "ffmpeg.zip"
    payload = b"evermeet-archive"
    _macos_release_env(monkeypatch, release=release)
    _install_fake_urlopen(monkeypatch, payload)
    _install_fake_gpg(monkeypatch, keyring=_keyring_record(_PRIMARY_FPR), verify_status=_GOOD_VERIFY_STATUS)
    seen: list[tuple] = []
    real_verify = build_exe._verify_official_signature

    def _spy(*args: Any) -> None:
        seen.append(args)
        real_verify(*args)

    monkeypatch.setattr(build_exe, "_verify_official_signature", _spy)
    build_exe._download_file("https://example.invalid/x.zip", dest, "ffmpeg (evermeet)", slot="ffmpeg")
    assert seen == [(dest, "ffmpeg", "ffmpeg (evermeet)")], "签名档没有触发验签：验签又落回了哈希分支"
    assert dest.read_bytes() == payload


def test_signature_mode_aborts_build_when_signature_is_bad(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 验签判坏必须终止构建：签名档是这一槽唯一的判据，这里降级就等于整槽无校验。
    dest = tmp_path / "ffmpeg.zip"
    _macos_release_env(monkeypatch, release=True)
    _install_fake_urlopen(monkeypatch, b"evermeet-archive")
    _install_fake_gpg(
        monkeypatch, keyring=_keyring_record(_PRIMARY_FPR), verify_status=b"[GNUPG:] BADSIG 1 x@example.org\n"
    )
    with pytest.raises(SystemExit):
        build_exe._download_file("https://example.invalid/x.zip", dest, "ffmpeg (evermeet)", slot="ffmpeg")


def test_signature_mode_aborts_build_when_gpg_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 「gpg 这个工具不存在」在发布路径必须终止：签名档没有哈希兜底，跳过验签=跳过校验。
    dest = tmp_path / "ffmpeg.zip"
    _macos_release_env(monkeypatch, release=True)
    _install_fake_urlopen(monkeypatch, b"evermeet-archive")
    _install_fake_gpg(monkeypatch, keyring=b"", verify_status=b"", import_available=False)
    with pytest.raises(SystemExit):
        build_exe._download_file("https://example.invalid/x.zip", dest, "ffmpeg (evermeet)", slot="ffmpeg")


def test_signature_mode_marker_without_registration_never_downloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 声明了签名档但登记不齐（例如同步改表时漏改签名表）→ 必须**在下载前**拦下，
    # 且不发起任何请求；报错文案点名「未登记/指纹形状」，别让维护者去核对一个不存在的哈希。
    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("未满足的签名档不得发起下载")

    monkeypatch.setattr(build_exe, "runtime_slot_key", lambda: "linux-x64")
    monkeypatch.setattr(build_exe, "require_pinned_hashes", lambda: True)
    monkeypatch.setattr(build_exe, "_PINNED_RUNTIME_SHA256", {"linux-x64": {"ffmpeg": _SIG_MARKER, "node": "a" * 64}})
    monkeypatch.setattr(build_exe, "urllib", types.SimpleNamespace(request=types.SimpleNamespace(urlopen=explode)))
    with pytest.raises(SystemExit) as caught:
        build_exe._download_file("https://example.invalid/x.tar.xz", tmp_path / "x.tar.xz", "ffmpeg", slot="ffmpeg")
    assert "官方签名档" in str(caught.value) and "未满足" in str(caught.value)


def _make_tar_xz(archive: Path, members: dict[str, bytes]) -> None:
    # 造一份最小 tar.xz：只用于驱动真实的 tarfile 解包与递归查名，不碰网络。
    with tarfile.open(archive, "w:xz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(data))


@pytest.mark.parametrize(
    "members",
    [
        # BtbN 实测布局（2026-09-26 取该资产归档前 4 MB 列成员所得）
        {
            "ffmpeg-n9.0-latest-linux64-gpl-9.0/bin/ffmpeg": b"ELF-ffmpeg",
            "ffmpeg-n9.0-latest-linux64-gpl-9.0/bin/ffprobe": b"ELF-ffprobe",
            "ffmpeg-n9.0-latest-linux64-gpl-9.0/doc/ffmpeg.html": b"docs",
        },
        # johnvansickle 旧布局：平铺在 ffmpeg-<ver>-<arch>-static/ 下
        {
            "ffmpeg-7.0-amd64-static/ffmpeg": b"ELF-ffmpeg",
            "ffmpeg-7.0-amd64-static/ffprobe": b"ELF-ffprobe",
        },
    ],
    ids=["BtbN-bin布局", "johnvansickle-平铺布局"],
)
def test_linux_ffmpeg_extraction_is_layout_agnostic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, members: dict[str, bytes]
) -> None:
    # 换源后归档内层级从平铺变成带 bin/：写死任一种，另一种会「解包成功但一件没拷」，
    # 而调用方要到出包前的 verify_runtime_binaries 才发现。本函数不读 sys.platform，
    # 故在 Windows 开发机与 Linux CI 上都会真实执行（AGENTS.md「平台分支不得靠 skipif 让 CI 丢锁」同源）。
    archive = tmp_path / "runtime.tar.xz"
    _make_tar_xz(archive, members)
    ffmpeg_dir = tmp_path / "ffmpeg"
    ffmpeg_dir.mkdir()
    build_exe._extract_linux_ffmpeg_binaries(archive, ffmpeg_dir)
    for binary, content in (("ffmpeg", b"ELF-ffmpeg"), ("ffprobe", b"ELF-ffprobe")):
        got = ffmpeg_dir / binary
        assert got.is_file() and got.read_bytes() == content, f"{binary} 未被取出（布局假设被写死了）"


def test_linux_ffmpeg_extraction_aborts_when_binary_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 缺件抛 SystemExit（BaseException 不被 _download_ffmpeg 外层 except Exception 吞）：
    # 否则回到「一行 warning + 出包成功」的 arm64 404 形态。
    archive = tmp_path / "runtime.tar.xz"
    _make_tar_xz(archive, {"ffmpeg-x/doc/README": b"docs only"})
    ffmpeg_dir = tmp_path / "ffmpeg"
    ffmpeg_dir.mkdir()
    with pytest.raises(SystemExit):
        build_exe._extract_linux_ffmpeg_binaries(archive, ffmpeg_dir)


# ---------------------------------------------------------------------------
# 2026-09-26 macOS full 包两处产物缺陷：zip 解包丢可执行位 + ffprobe 从未被下载。
# 前者让 ffmpeg 落盘即不可执行（自检 PermissionError [Errno 13]），后者让 macOS 的 full 包
# 结构上就缺件（evermeet 的 ffmpeg 归档里只有 ffmpeg）。
# 全程离线：归档由用例自己造，网络与 gpg 走本文件既有的桩。
# ---------------------------------------------------------------------------


def _make_zip(archive: Path, members: dict[str, tuple[bytes, int]]) -> None:
    # 造一份最小 zip：成员名 → (内容, unix mode)。必须把 mode 写进 external_attr 的高 16 位，
    # 因为本组用例锁的正是「归档里带了 0o755，解出来却没有可执行位」这一形态。
    with zipfile.ZipFile(archive, "w") as zf:
        for name, (data, mode) in members.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            zf.writestr(info, data)


def _install_chmod_spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    # 替换 build_exe 的**模块全局名 os**（浅拷贝 stdlib 全部属性，只覆盖 chmod），
    # 不污染 stdlib 本体（AGENTS.md「patch stdlib 模块属性」同源坑）。
    calls: list[tuple[str, int]] = []
    shim = types.SimpleNamespace(**vars(os))

    def spy_chmod(path: Any, mode: int, *args: Any, **kwargs: Any) -> None:
        calls.append((str(path), mode))
        return os.chmod(path, mode, *args, **kwargs)

    shim.chmod = spy_chmod
    monkeypatch.setattr(build_exe, "os", shim)
    return calls


def test_zip_install_restores_exec_bit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    archive = tmp_path / "ffmpeg.zip"
    _make_zip(archive, {"ffmpeg": (b"MachO-ffmpeg", 0o755), "LICENSE": (b"text", 0o644)})
    ffmpeg_dir = tmp_path / "ffmpeg"
    ffmpeg_dir.mkdir()
    chmod_calls = _install_chmod_spy(monkeypatch)

    build_exe._install_executables_from_zip(
        archive, ffmpeg_dir, ("ffmpeg",), require_bin_dir=False, set_exec_bit=True, required=("ffmpeg",)
    )
    got = ffmpeg_dir / "ffmpeg"
    assert got.read_bytes() == b"MachO-ffmpeg"
    assert [(os.path.basename(p), m) for p, m in chmod_calls] == [("ffmpeg", 0o755)], chmod_calls

    # 反向证据（POSIX 才有权限语义，Windows 上 chmod 只映射只读位）：
    # 同归档走 zipfile.extractall 解出来的那一份**没有**执行位——这就是 macOS runner 上的实测形态，
    # 也是「改回 extractall」会被本用例抓住的原因。
    via_extractall = tmp_path / "via_extractall"
    via_extractall.mkdir()
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(via_extractall)
    if os.name != "nt":
        assert (
            not (via_extractall / "ffmpeg").stat().st_mode & stat.S_IXUSR
        ), "extractall 竟然保留了执行位：本用例的前提（Python 不还原 unix mode）已被证伪，须重判"
        assert got.stat().st_mode & stat.S_IXUSR, "补位后仍不可执行，chmod 没落到目标文件上"


def test_zip_install_aborts_when_required_member_absent(tmp_path: Path) -> None:
    # 上游一改归档内部层级就会「解包成功但一件没拷」；缺件必须 SystemExit，
    # 与 _extract_linux_ffmpeg_binaries 同一条判据（不得降级成 warning + 出包成功）。
    archive = tmp_path / "ffmpeg.zip"
    _make_zip(archive, {"README": (b"docs only", 0o644)})
    ffmpeg_dir = tmp_path / "ffmpeg"
    ffmpeg_dir.mkdir()
    with pytest.raises(SystemExit) as caught:
        build_exe._install_executables_from_zip(
            archive, ffmpeg_dir, ("ffmpeg",), require_bin_dir=False, set_exec_bit=True, required=("ffmpeg",)
        )
    assert "ffmpeg" in str(caught.value)


def test_zip_install_never_writes_outside_dest_dir(tmp_path: Path) -> None:
    # CR-11 的取件面锁：成员名取自压缩包自述、可含 `../../` 或 `x/bin/../../y`。本函数一律先取
    # basename 再与白名单比，于是「逃逸形态的成员名」最坏只会命中同名 basename 写到 dest_dir 内，
    # 绝不会被写到外面——删掉 basename 归一（改成直接用 member 作路径）即红。
    # realpath 前缀校验是第二道闸，只在白名单里出现带目录分隔的名字时才可能触发。
    archive = tmp_path / "evil.zip"
    _make_zip(
        archive,
        {
            "../../ffmpeg": (b"payload", 0o755),
            "nested/a/bin/../../../ffprobe": (b"payload2", 0o755),
        },
    )
    ffmpeg_dir = tmp_path / "out" / "ffmpeg"
    ffmpeg_dir.mkdir(parents=True)
    build_exe._install_executables_from_zip(
        archive,
        ffmpeg_dir,
        ("ffmpeg", "ffprobe"),
        require_bin_dir=False,
        set_exec_bit=True,
        required=("ffmpeg",),
    )
    assert sorted(p.name for p in ffmpeg_dir.iterdir()) == ["ffmpeg", "ffprobe"]
    assert not (tmp_path.parent / "ffmpeg").exists() and not (tmp_path / "ffmpeg").exists(), "写到了 ffmpeg_dir 之外"


def _install_routed_urlopen(monkeypatch: pytest.MonkeyPatch, payloads: dict[str, bytes]) -> list[str]:
    # evermeet 一条链路要发 4 次请求（两支归档 + 两份签名），单 payload 的 _install_fake_urlopen
    # 会把签名内容也返回成归档，故按 URL 前缀匹配、**最长前缀优先**
    # （.../ffprobe/zip/sig 同时含 .../ffprobe/zip 与 .../zip）。
    seen: list[str] = []
    ordered = sorted(payloads, key=len, reverse=True)

    def fake_urlopen(url: str, *args: Any, **kwargs: Any) -> Any:
        seen.append(url)
        for prefix in ordered:
            if prefix in url:
                return _FakeResponse(payloads[prefix])
        raise AssertionError(f"用例没准备这个 URL 的应答: {url}")

    monkeypatch.setattr(build_exe, "urllib", types.SimpleNamespace(request=types.SimpleNamespace(urlopen=fake_urlopen)))
    return seen


def test_macos_ffmpeg_branch_fetches_both_archives_and_verifies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # darwin 分支的端到端锁，且**不靠 skipif**：IS_WIN / sys.platform / runtime_slot_key 三处
    # 一起强制，让这条只在 macOS runner 上真实执行的分支在 Windows 开发机与 Linux CI 上都跑到。
    _macos_release_env(monkeypatch, release=True)
    monkeypatch.setattr(build_exe, "IS_WIN", False)
    sys_shim = types.SimpleNamespace(**vars(sys))
    sys_shim.platform = "darwin"
    monkeypatch.setattr(build_exe, "sys", sys_shim)
    ffmpeg_zip = tmp_path / "src_ffmpeg.zip"
    _make_zip(ffmpeg_zip, {"ffmpeg": (b"MachO-ffmpeg", 0o755)})
    ffprobe_zip = tmp_path / "src_ffprobe.zip"
    _make_zip(ffprobe_zip, {"ffprobe": (b"MachO-ffprobe", 0o755)})
    # payload 键取自**生产来源表本身**而不是复写一遍 URL：这条锁要证的是「darwin 分支按表取两支归档、
    # 并对每支按其登记的签名 URL 验签」，把 URL 抄进用例就等于同时锁住了两个可能各自漂移的事实源。
    ffmpeg_url = _artifact_url_for_slot("macos-arm64", "ffmpeg")
    ffprobe_url = _artifact_url_for_slot("macos-arm64", "ffprobe")
    seen = _install_routed_urlopen(
        monkeypatch,
        {
            f"{ffprobe_url}.sig": b"sig-ffprobe",
            f"{ffmpeg_url}.sig": b"sig-ffmpeg",
            ffprobe_url: ffprobe_zip.read_bytes(),
            ffmpeg_url: ffmpeg_zip.read_bytes(),
        },
    )
    _install_fake_gpg(monkeypatch, keyring=_keyring_record(_PRIMARY_FPR), verify_status=_GOOD_VERIFY_STATUS)
    chmod_calls = _install_chmod_spy(monkeypatch)

    assert build_exe._download_ffmpeg(tmp_path) is True
    ffmpeg_dir = tmp_path / "ffmpeg"
    assert (ffmpeg_dir / "ffmpeg").read_bytes() == b"MachO-ffmpeg"
    assert (ffmpeg_dir / "ffprobe").read_bytes() == b"MachO-ffprobe", "macOS full 包又缺 ffprobe 了"
    # 两个可执行件都补了执行位（归档本身是 zip，Windows 开发机上也能按 chmod 调用记录判定）
    assert sorted(os.path.basename(p) for p, _ in chmod_calls) == ["ffmpeg", "ffprobe"], chmod_calls
    # 归档与签名都取过，且**没有**落到 target_dir（会被 make_zip 打进对外分发包）
    assert sum(1 for url in seen if url.endswith(".sig")) == 2, seen
    assert ffprobe_url in seen, seen
    # 临时归档必须解包后即删：留在 target_dir 里会被 make_zip 一起打进对外分发包
    assert not list(tmp_path.glob("_*temp.zip")), "临时归档残留在发布目录里"


# ---------------------------------------------------------------------------
# MID-2254：发布 zip 与冒烟解耦 + 「运行期产物不得进包」
# 冒烟以 cwd=RELEASE_DIR 连跑 CLI 25s / Web 90s / GUI 8s，src/logger.py 会在包内落
# streamget.log / PlayURL.log / web_console.log（含 runner 绝对路径、用户名、告警堆栈），
# 「缺键补写」还会改写包内 config.ini。旧顺序把冒烟排在 full 压缩之前，等于把这些打进对外分发的 zip。
# 下面几条分别锁：顺序、清理、实物断言。全程桩掉 PyInstaller / 下载 / 压缩 / 起进程，不执行真实打包。
# ---------------------------------------------------------------------------


def _stub_build_steps(monkeypatch: pytest.MonkeyPatch, order: list[str], tmp_path: Path) -> None:
    # 把 main() 的每个重活换成「记名字」的桩：既验证顺序，也保证不碰网络与磁盘产物。
    def _make(name: str, ret: object) -> Any:
        def _stub(*args: object, **kwargs: object) -> object:
            order.append(name)
            return ret

        return _stub

    # DIST_DIR 必须改指到 tmp：main() 出包前会真实调用 _clean_stale_release_zips() 删 dist/ 里的
    # 陈旧 zip，不重定向就会在跑测试时删掉仓库 dist/ 下用户真正的构建产物。
    monkeypatch.setattr(build_exe, "DIST_DIR", tmp_path / "dist")
    for name in ("run_pyinstaller", "copy_external_binaries", "download_runtime_binaries", "smoke_test"):
        monkeypatch.setattr(build_exe, name, _make(name, None))
    monkeypatch.setattr(build_exe, "_prepare_url_config", _make("_prepare_url_config", None))

    # make_zip 的桩必须**按 suffix 产出不同名字**并在盘上真实落件：--dual 分支现在会拿两个返回值
    # 做「互不相同且都存在」的事后校验，返回常量路径的旧桩会让三条 --dual 用例全部误红。
    def _fake_make_zip(*args: object, **kwargs: object) -> Path:
        order.append("make_zip")
        suffix = str(kwargs.get("suffix", args[1] if len(args) > 1 else "") or "")
        zip_path = cast(Path, build_exe.DIST_DIR) / f"stub{suffix}.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(b"PK\x03\x04")
        return zip_path

    monkeypatch.setattr(build_exe, "make_zip", _fake_make_zip)


def _zip_positions(order: list[str]) -> list[int]:
    return [i for i, name in enumerate(order) if name == "make_zip"]


def test_dual_build_zips_both_variants_before_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    order: list[str] = []
    _stub_build_steps(monkeypatch, order, tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_exe.py", "--dual", "--smoke"])
    build_exe.main()
    zips = _zip_positions(order)
    assert len(zips) == 2, f"--dual 应产出 lite + full 两个 zip：{order}"
    assert "smoke_test" in order, order
    smoke_at = order.index("smoke_test")
    assert all(z < smoke_at for z in zips), f"冒烟必须排在两个 zip 之后（否则日志进包）：{order}"
    # full zip 必须在运行时下载之后（否则包里没有 ffmpeg/node），且仍在冒烟之前
    assert order.index("download_runtime_binaries") < zips[-1] < smoke_at, order
    # 事后校验的输入侧证据：两个变体各自落件，名字互不相同
    produced = sorted(p.name for p in (tmp_path / "dist").glob("*.zip"))
    assert produced == ["stub-full.zip", "stub-lite.zip"], produced


def test_dual_build_prunes_stale_zips_before_first_zip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 出包前清理 dist/ 的**接线**：陈旧 zip 不清就会被 build-release.yml 的 `path: dist/*.zip`
    # 连同本轮产物一起扫进附件（僵尸附件）。删不掉本用例就红——它锁的是「main() 里真的有这次调用
    # 且排在第一次 make_zip 之前」，而不是 _clean_stale_release_zips 自身的返回值。
    dist = tmp_path / "dist"
    dist.mkdir(parents=True)
    stale_buggy = dist / "DouyinLiveRecorder-v4.3.zip"  # with_suffix 截断缺陷时期的产物名形态
    stale_old = dist / "DouyinLiveRecorder-v4.2.0-windows-amd64-full.zip"
    user_file = dist / "release-notes.txt.zip"  # 不归本构建管辖，绝不得碰
    for victim in (stale_buggy, stale_old, user_file):
        victim.write_bytes(b"PK\x03\x04")
    order: list[str] = []
    _stub_build_steps(monkeypatch, order, tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_exe.py", "--dual"])
    build_exe.main()
    assert not stale_buggy.exists(), order
    assert not stale_old.exists(), order
    assert user_file.is_file(), "清理范围越界：非本产物名的 zip 也被删了"
    assert _zip_positions(order), order


def test_no_zip_build_keeps_existing_dist_zips(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 反向：不出包就不清理。--no-zip（ci.yml 的 build-verify 形态）下把用户 dist/ 里的 zip 删掉
    # 是纯粹的副作用，必须锁住「没出包 → 一个文件都没删」。
    dist = tmp_path / "dist"
    dist.mkdir(parents=True)
    keeper = dist / "DouyinLiveRecorder-v4.2.0-windows-amd64-lite.zip"
    keeper.write_bytes(b"PK\x03\x04")
    order: list[str] = []
    _stub_build_steps(monkeypatch, order, tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_exe.py", "--smoke", "--no-zip", "--no-runtime"])
    build_exe.main()
    assert keeper.is_file(), order


def test_single_build_zips_before_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    order: list[str] = []
    _stub_build_steps(monkeypatch, order, tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_exe.py", "--smoke"])
    build_exe.main()
    zips = _zip_positions(order)
    assert len(zips) == 1, order
    assert zips[0] < order.index("smoke_test"), f"非 dual 路径同样必须先压缩后冒烟：{order}"


def test_no_zip_build_still_smokes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 反向：--no-zip（ci.yml 的 build-verify 即用此形态）不该因为「zip 在前」的新顺序
    # 而丢掉冒烟——本用例锁「冒烟仍在」，防止把解耦写成「干脆不冒烟」。
    order: list[str] = []
    _stub_build_steps(monkeypatch, order, tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_exe.py", "--smoke", "--no-zip", "--no-runtime"])
    build_exe.main()
    assert "make_zip" not in order, order
    assert "smoke_test" in order, order


def test_ensure_utf8_streams_keeps_replace_error_policy() -> None:
    # 回归锁：_ensure_utf8_streams 一旦退回裸 reconfigure(encoding="utf-8")，就会把 pytest fd 捕获
    # 包装器（EncodedFile）的 errors 从 replace 就地翻成 strict——代价不在当场，要等会话收尾
    # 读捕获时才以 UnicodeDecodeError 炸出来，且往往先嫁祸给无关用例。
    # 这里在**真实的 pytest 捕获**下调用它，要求两侧流的错误策略一字不变。
    before = (getattr(sys.stdout, "errors", None), getattr(sys.stderr, "errors", None))
    build_exe._ensure_utf8_streams()
    after = (getattr(sys.stdout, "errors", None), getattr(sys.stderr, "errors", None))
    # 前提：本用例必须跑在 pytest 的 fd 捕获之下，否则这条锁失去意义（而不是假通过）
    assert before == ("replace", "replace"), f"本用例依赖 pytest fd 捕获的 replace 策略，实测：{before}"
    assert after == before, f"_ensure_utf8_streams 改动了标准流错误策略：{before} -> {after}"


def test_ensure_utf8_streams_passes_explicit_errors_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    # 形态锁：错误策略必须**显式**写成 "replace"，不能指望「省略即兜底」——省略恰恰会被
    # TextIOWrapper.reconfigure 解释成 strict（见上一条用例的注释）。
    calls: list[dict[str, str]] = []

    class _FakeStream:
        # 模拟 Windows CI 的默认形态：非 UTF-8 编码 + 严格错误策略
        encoding = "cp1252"
        errors = "strict"

        def reconfigure(self, **kwargs: str) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(sys, "stdout", _FakeStream())
    monkeypatch.setattr(sys, "stderr", _FakeStream())
    build_exe._ensure_utf8_streams()
    assert calls == [
        {"encoding": "utf-8", "errors": "replace"},
        {"encoding": "utf-8", "errors": "replace"},
    ], f"两个标准流都必须带 errors='replace' 重配置：{calls}"


def test_release_cleaner_removes_runtime_artifacts_and_keeps_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / build_exe.APP_NAME
    for name in build_exe.RUNTIME_ARTIFACT_DIR_NAMES:
        (release / name).mkdir(parents=True)
        (release / name / "junk.txt").write_text("leak", encoding="utf-8")
    (release / "_internal" / "src" / "__pycache__").mkdir(parents=True)
    keep = release / "_internal" / "src" / "utils.py"
    keep.write_text("#\n", encoding="utf-8")
    cfg = release / "config"
    cfg.mkdir()
    (cfg / "config.ini").write_text("[录制设置]\n", encoding="utf-8")
    monkeypatch.setattr(build_exe, "RELEASE_DIR", release)

    removed = build_exe._clean_runtime_artifacts_from_release()

    for name in build_exe.RUNTIME_ARTIFACT_DIR_NAMES:
        assert not (release / name).exists(), f"{name}/ 未被剔除，会随 zip 外发"
    assert not (release / "_internal" / "src" / "__pycache__").exists(), "嵌套 __pycache__ 未剔除"
    assert keep.is_file() and (cfg / "config.ini").is_file(), "清理误伤发布载荷（源码/配置模板）"
    assert {p.replace("\\", "/") for p in removed} == {
        "logs/",
        "backup_config/",
        "downloads/",
        "_internal/src/__pycache__/",
    }, removed


@pytest.mark.parametrize(
    ("member", "expected"),
    [
        (f"{build_exe.APP_NAME}/logs/streamget.log", True),
        (f"{build_exe.APP_NAME}\\logs\\PlayURL.log", True),
        (f"{build_exe.APP_NAME}/downloads/x/1.ts", True),
        (f"{build_exe.APP_NAME}/_internal/src/__pycache__/utils.cpython-314.pyc", True),
        ("logs/web_console.log", True),
        (f"{build_exe.APP_NAME}/config/config.ini", False),
        (f"{build_exe.APP_NAME}/_internal/src/utils.py", False),
        (f"{build_exe.APP_NAME}/_internal/web/logs_note.js", False),
        (f"{build_exe.APP_NAME}/", False),
    ],
)
def test_zip_member_runtime_artifact_predicate(member: str, expected: bool) -> None:
    # `unzip -l` 那一列的判定逻辑；反斜杠形态也要认出（Windows 上手工造的 zip 会这样存）。
    assert build_exe._zip_member_is_runtime_artifact(member) is expected


def _fake_archive_with(members: list[str]) -> Any:
    # 桩掉 `_zip_release_dir`（make_zip 内部的压缩动作）而不是 shutil.make_archive：体积优化后
    # make_zip 改为自建 zipfile（为指定 compresslevel=9），压缩这一步的**唯一接缝**就是该函数。
    # 桩在这里，两条用例的「实物断言独立成立，不靠上游先删干净」语义原样保留。
    def _fake(zip_path: Path) -> None:
        with zipfile.ZipFile(zip_path, "w") as zf:
            for member in members:
                zf.writestr(member, "x")

    return _fake


def _stub_make_zip_inputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, members: list[str]) -> None:
    release = tmp_path / build_exe.APP_NAME
    release.mkdir(parents=True)
    dist = tmp_path / "dist"
    dist.mkdir()
    monkeypatch.setattr(build_exe, "RELEASE_DIR", release)
    monkeypatch.setattr(build_exe, "DIST_DIR", dist)
    monkeypatch.setattr(build_exe, "assert_no_credentials_in_release", lambda: None)
    # 把清理本身桩成 no-op：证明「实物断言」独立成立，不靠上游先删干净
    monkeypatch.setattr(build_exe, "_clean_runtime_artifacts_from_release", lambda: [])
    monkeypatch.setattr(build_exe, "_zip_release_dir", _fake_archive_with(members))


def test_make_zip_aborts_when_archive_still_contains_logs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _stub_make_zip_inputs(monkeypatch, tmp_path, [f"{build_exe.APP_NAME}/logs/streamget.log"])
    with pytest.raises(SystemExit) as caught:
        build_exe.make_zip("9.9.9")
    assert "logs/streamget.log" in str(caught.value)


def test_make_zip_accepts_clean_archive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 反向：不得把断言写成「永远红」——干净清单必须出包成功。
    _stub_make_zip_inputs(
        monkeypatch,
        tmp_path,
        [f"{build_exe.APP_NAME}/config/config.ini", f"{build_exe.APP_NAME}/_internal/a.py"],
    )
    zip_path = build_exe.make_zip("9.9.9")
    assert zip_path.is_file()


# ---------------------------------------------------------------------------
# 2026-09-27 CI 实红：zip 文件名被 Path.with_suffix(".zip") 截断。
# 版本号带点（如 4.3.0）时 with_suffix 从**最后一个点**起把尾巴整段当旧扩展名丢弃，
# DouyinLiveRecorder-v4.3.0-windows-amd64-{lite,full} 双双变成 DouyinLiveRecorder-v4.3.zip
# （架构段写 amd64：那是 platform.machine().lower() 在 Windows 上的实际取值，x64 只是
# _NODE_ARCH_MAP 归一后的运行时键名，从不出现在产物名里）。于是 full 静默覆盖 lite、dist/ 只剩
# 一个 zip，build-release.yml 的「lite+full 齐全」校验与 dist/*-lite.zip 上传通配同时落空。
# 上方两条既有 make_zip 用例对**名字**都不设判据，名称漂移对它们完全隐形——本组用例锁的
# 正是名称形态与「两个 zip 互不覆盖」。
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("suffix,tail", [("-lite", "lite"), ("-full", "full")])
def test_make_zip_name_keeps_dotted_version_and_variant_suffix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, suffix: str, tail: str
) -> None:
    _stub_make_zip_inputs(monkeypatch, tmp_path, [f"{build_exe.APP_NAME}/_internal/a.py"])
    zip_path = build_exe.make_zip("4.3.0", suffix=suffix)
    # 结构锁：完整的 v4.3.0（两个点都在）+ <os>-<arch> 段 + 变体段 + .zip 扩展名。
    pattern = rf"DouyinLiveRecorder-v4\.3\.0-(windows|macos|linux)-[a-z0-9_]+-{tail}\.zip"
    assert re.fullmatch(pattern, zip_path.name), zip_path.name


def test_dual_suffixes_do_not_collide_on_one_zip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # --dual 的真实失效形态：两次 make_zip 落到同一个路径，后一次覆盖前一次，
    # 磁盘上只剩一个 zip（内容是 full、名字什么变体都不带）。判据只数文件，不复算命名实现。
    _stub_make_zip_inputs(monkeypatch, tmp_path, [f"{build_exe.APP_NAME}/_internal/a.py"])
    lite = build_exe.make_zip("4.3.0", suffix="-lite")
    full = build_exe.make_zip("4.3.0", suffix="-full")
    assert lite != full
    produced = sorted(p.name for p in (tmp_path / "dist").glob("*.zip"))
    assert len(produced) == 2, produced
    assert lite.is_file() and full.is_file()


def test_make_zip_refuses_name_containing_path_separator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # version/suffix 含分隔符时，f-string 拼出的是**子路径**而不是文件名，成品会落到 dist/ 之外。
    # 用 '/' 而非 os.sep：Windows 的 pathlib 同样把 '/' 当分隔符，Linux 上 '\' 却是合法文件名字符，
    # 故 '/' 是唯一在两侧都真实走到拒收分支的取值（不得靠 skipif 让 CI 少跑一半）。
    # 两个入参位都要测：守卫拦的是「拼出来的路径落点」，只测 version 会让 suffix 那一半没有锁。
    _stub_make_zip_inputs(monkeypatch, tmp_path, [f"{build_exe.APP_NAME}/_internal/a.py"])
    for version, suffix in (("4.3.0/escape", ""), ("4.3.0", "-lite/escape")):
        with pytest.raises(SystemExit) as caught:
            build_exe.make_zip(version, suffix=suffix)
        assert "路径分隔符" in str(caught.value), (version, suffix)
        assert not (tmp_path / "dist" / "DouyinLiveRecorder-v4.3.0").exists(), (version, suffix)
        assert list((tmp_path / "dist").glob("*.zip")) == [], (version, suffix)
        assert list(tmp_path.glob("*.zip")) == [], (version, suffix)


def test_dual_and_no_zip_are_mutually_exclusive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # --dual 分支从不读 no_zip：旧形态下 `--dual --no-zip` 照样压出两个大 zip，用户显式写的
    # --no-zip 被静默无视。现在必须 fail-fast；断言 order 为空即锁「判定早于任何构建步骤」。
    order: list[str] = []
    _stub_build_steps(monkeypatch, order, tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_exe.py", "--dual", "--no-zip", "--smoke"])
    with pytest.raises(SystemExit) as caught:
        build_exe.main()
    assert "--dual 与 --no-zip 互斥" in str(caught.value)
    assert order == [], order
    assert list((tmp_path / "dist").glob("*.zip")) == [], "互斥判定必须早于清理，否则报错前已经删过文件"


def _stub_two_colliding_zips(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, order: list[str]) -> Path:
    # 复现 2026-09-27 的真实失效形态：两次 make_zip 返回同一个路径（名字里没有变体段），
    # 第二次以 zipfile "w" 原地截断第一次，进程退出码 0、零可见症状。
    victim = tmp_path / "dist" / "DouyinLiveRecorder-v4.3.zip"
    victim.parent.mkdir(parents=True, exist_ok=True)

    def _fake(*args: object, **kwargs: object) -> Path:
        order.append("make_zip")
        victim.write_bytes(b"PK\x03\x04")
        return victim

    monkeypatch.setattr(build_exe, "make_zip", _fake)
    return victim


def test_dual_build_aborts_when_both_variants_land_on_one_zip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 本地兜底：CI 那条 `Verify dist contains both lite & full zips` 只在 runner 上跑，
    # 本机 `--dual` 出包时同样必须抓到「两个变体撞成一个文件」，否则缺陷又要等一轮发布才现形。
    order: list[str] = []
    _stub_build_steps(monkeypatch, order, tmp_path)
    victim = _stub_two_colliding_zips(monkeypatch, tmp_path, order)
    monkeypatch.setattr(sys, "argv", ["build_exe.py", "--dual"])
    with pytest.raises(SystemExit) as caught:
        build_exe.main()
    assert "同一个文件" in str(caught.value), str(caught.value)
    assert len(_zip_positions(order)) == 2, order


def test_dual_build_aborts_when_a_variant_zip_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 事后校验的另一半：名字互异但其中一个根本没落盘（磁盘满 / 被外部删掉）同样不得放行。
    order: list[str] = []
    _stub_build_steps(monkeypatch, order, tmp_path)
    made: list[Path] = []

    def _fake(*args: object, **kwargs: object) -> Path:
        order.append("make_zip")
        suffix = str(kwargs.get("suffix", "") or "")
        zip_path = cast(Path, build_exe.DIST_DIR) / f"stub{suffix}.zip"
        if suffix != "-full":  # full 只报成功不落件
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            zip_path.write_bytes(b"PK\x03\x04")
        made.append(zip_path)
        return zip_path

    monkeypatch.setattr(build_exe, "make_zip", _fake)
    monkeypatch.setattr(sys, "argv", ["build_exe.py", "--dual"])
    with pytest.raises(SystemExit) as caught:
        build_exe.main()
    assert "不存在" in str(caught.value), str(caught.value)
    assert [p.name for p in made] == ["stub-lite.zip", "stub-full.zip"], made


def test_clean_stale_release_zips_only_touches_own_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 判据本体：按 `{APP_NAME}-v*.zip` 命中并**返回**被删名字（返回清单才可能被打印出来，
    # 静默删除与不删同样糟）。dist/ 不存在时必须是空操作而不是抛错——首次构建就是这个形态。
    dist = tmp_path / "dist"
    dist.mkdir()
    mine = [dist / "DouyinLiveRecorder-v4.3.zip", dist / "DouyinLiveRecorder-v4.2.0-linux-x86_64-full.zip"]
    keepers = [dist / "notes.zip", dist / "DouyinLiveRecorder.txt"]
    for victim in mine + keepers:
        victim.write_bytes(b"x")
    monkeypatch.setattr(build_exe, "DIST_DIR", dist)
    removed = build_exe._clean_stale_release_zips()
    assert sorted(removed) == ["DouyinLiveRecorder-v4.2.0-linux-x86_64-full.zip", "DouyinLiveRecorder-v4.3.zip"]
    assert not any(victim.exists() for victim in mine)
    assert all(victim.exists() for victim in keepers)
    # 幂等：再来一次不得报错、也不得删掉别的
    assert build_exe._clean_stale_release_zips() == []
    missing = tmp_path / "no-such-dist"
    monkeypatch.setattr(build_exe, "DIST_DIR", missing)
    assert build_exe._clean_stale_release_zips() == []


# ---------------------------------------------------------------------------
# MID-2255：.dockerignore / .gitignore 的行内 `#` 与空规则
# 两份文件都只有**行首** `#` 是注释；`pattern   # 说明` 让模式变成「带空格与中文的长串」，
# 永不匹配 —— 规则看着在、实际等于没写，而且**伪装成已排除**（比漏写更危险）。
# ---------------------------------------------------------------------------


def _ignore_patterns(name: str) -> list[str]:
    text = (ROOT / name).read_text(encoding="utf-8-sig")
    return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


@pytest.mark.parametrize("ignore_file", [".dockerignore", ".gitignore"])
def test_ignore_files_have_no_inline_comments(ignore_file: str) -> None:
    patterns = _ignore_patterns(ignore_file)
    offenders = [
        f"{ignore_file}:{no} -> {line!r}" for no, line in enumerate(patterns, 1) if " #" in line or "\t#" in line
    ]
    assert not offenders, "以下忽略规则把注释写在了行内，模式永不匹配（须移到独立行）：\n" + "\n".join(offenders)


def test_dockerignore_excludes_dev_only_artifacts_as_bare_patterns() -> None:
    patterns = _ignore_patterns(".dockerignore")
    # 这三条是本轮实测「伪装成已排除」的形态：65KB 打包脚本 / 37KB UTF-16 的 Windows 脚本 /
    # 仓库内散落的 *.jsonl（弹幕监控边车日志）都会经 COPY . ./ 进镜像。
    for must in ("build_exe.py", "StopRecording.vbs", "*.jsonl"):
        assert must in patterns, f".dockerignore 缺少裸模式 {must!r}（带行内注释的规则永不匹配）"
    # 空规则：i18n/ 下从来没有 compile_po.py（真身在 scripts/，已整目录排除），留着只会误导读者
    assert not [p for p in patterns if "compile_po" in p], "i18n/**/compile_po.py 永不匹配，属空规则"


def test_gitignore_runtime_dirs_are_bare_patterns() -> None:
    patterns = _ignore_patterns(".gitignore")
    # node/ 与 node-v*.zip 曾只有这一条规则（无其它兜底），行内注释让运行时下载的 Node.js
    # 目录几乎整体入库（node.exe 只是恰好被下面的 *.exe 拦住）；另两条一并钉住。
    for must in ("node/", "node-v*.zip", "backup_config/", "logs/", "*.jsonl"):
        assert must in patterns, f".gitignore 缺少裸模式 {must!r}"
    # 运行期产物目录**必须**保持忽略：修正规则形态不等于放开忽略意图
    assert "!node/" not in patterns and "!logs/" not in patterns and "!backup_config/" not in patterns


# ---------------------------------------------------------------------------
# MIN-2260：scripts/smoke_test.py 的「0 断言」不得算通过
# _ci_web_smoke.sh 原样透传 rc，CI 的「Web panel smoke test」步骤因此可以查了个空气还报成功。
# ---------------------------------------------------------------------------

_SMOKE_SCRIPT = ROOT / "scripts" / "smoke_test.py"


def _run_smoke_script(tmp_path: Path, content: str) -> int:
    cfg = tmp_path / "cfg.json"
    cfg.write_text(content, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(_SMOKE_SCRIPT), "-c", str(cfg)],
        capture_output=True,
        env={**os.environ, "PYTHONUTF8": "1"},
        cwd=str(ROOT),
        check=False,
    )
    rc: int = proc.returncode
    return rc


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"base_url": "http://127.0.0.1:9", "checks": []}', 2),
        ('{"base_url": "http://127.0.0.1:9"}', 2),
        ("[]", 2),
        ('[{"url": "http://127.0.0.1:9/none", "expected_status": 418, "name": "closed port"}]', 1),
    ],
    ids=["empty-checks", "missing-checks-key", "empty-top-level", "one-real-check-fails"],
)
def test_smoke_script_exit_codes_on_empty_config(tmp_path: Path, content: str, expected: int) -> None:
    # 前三条锁「空清单 = 2（配置问题）」，第四条锁「有断言时仍按结果退 1」——
    # 少了第四条，「任何配置一律退 2」的改法也会全绿（变异验证结论见本轮交付说明）。
    # 第 4 条只连 127.0.0.1 的关闭端口（连接被拒即返回），不外发任何请求。
    assert _run_smoke_script(tmp_path, content) == expected


def test_smoke_load_config_still_reads_valid_checks(tmp_path: Path) -> None:
    # 反向：加严「checks 必须存在」不得顺手把合法配置读坏。
    spec = importlib.util.spec_from_file_location("_smoke_cfg_probe", _SMOKE_SCRIPT)
    assert spec is not None and spec.loader is not None
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    cfg = tmp_path / "ok.json"
    cfg.write_text('{"base_url": "http://127.0.0.1:9", "checks": [{"url": "/health"}]}', encoding="utf-8")
    checks, base_url = smoke.load_config(str(cfg))
    assert base_url == "http://127.0.0.1:9"
    assert checks == [{"url": "/health"}]
    # 缺 checks 键：ValueError（而不是静默的 0 检查）
    bad = tmp_path / "bad.json"
    bad.write_text('{"base_url": "http://127.0.0.1:9"}', encoding="utf-8")
    with pytest.raises(ValueError):
        smoke.load_config(str(bad))


# ---------------------------------------------------------------------------
# 产物体积优化：排除清单与资源清单的回归锁
#
# 为什么值得锁：这些排除项**在源码里看不出代价**——排除一个模块在本地 Windows 上可能毫无变化
# （如 uvloop 只在 POSIX 安装），排除错了却会在某个平台/分支上以 ModuleNotFoundError 的形态在
# **冻结产物运行时**炸出来，而单测跑的是源码、覆盖不到。故锁三件事：① 清单不含「生产代码真的
# 导入了」的模块；② 三个入口都挂上清单（COLLECT 合并去重，只挂一个等于没排）；
# ③ i18n 资源不含 .po 但含运行时真正读的格式。
# ---------------------------------------------------------------------------


def _production_import_names() -> set[str]:
    # 收集生产代码（根入口 + src/）里出现过的所有导入模块名，用于判定「排除项是否可达」。
    # 用 AST 而不是正则：正则会把注释与字符串里的 import 也算进去（既漏判又误判）。
    files = [ROOT / name for name in ("main.py", "gui.py", "web.py", "i18n.py", "msg_push.py")]
    files += sorted((ROOT / "src").rglob("*.py"))
    names: set[str] = set()
    for path in files:
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
    return names


def test_bloat_excludes_never_hide_a_module_that_production_imports() -> None:
    # 正向安全阀：清单里任何一项都不得是生产代码（含其父模块）会导入的模块。
    # 「等于或以其为前缀」单向查：排除 `PIL` 会让生产导入的 `PIL.Image` 一起消失
    # （该形态必须拦）；反过来排除 `PIL._avif` 而生产只导入 `PIL` 是安全的、必须放行。
    imported = _production_import_names()
    collisions = sorted(
        name
        for excluded in build_exe.BLOAT_EXCLUDES
        for name in imported
        if name == excluded or name.startswith(excluded + ".")
    )
    assert not collisions, f"排除项与生产导入冲突（冻结后会 ModuleNotFoundError）：{collisions}"


def test_bloat_excludes_still_cover_the_measured_bloat() -> None:
    # 反向：只锁「清单不许乱加」会让「把体积项删掉」也全绿。这几项是 2026-09-24 实测
    # 进产物的死重量（基线 lite 82.77MB 中的约 11.7MB），删任一项都会让体积悄悄回弹。
    for required in (
        "pydantic.v1.mypy",  # 拖入整个 mypy 包（0.71MB / 69 文件）
        "PIL._avif",  # 7.52MB，产物内最大的单个非解释器文件
        "PIL._imagingft",  # 2.07MB
        "httptools",  # 0.17MB
        "watchfiles",  # 0.61MB
        "nodejs_wheel",  # 114MB：venv 里有、requirements.txt 没有
    ):
        assert required in build_exe.BLOAT_EXCLUDES, f"体积排除清单缺 {required!r}，产物体积将回弹"


def test_every_analysis_applies_the_bloat_excludes() -> None:
    # COLLECT 把三个 Analysis 的 binaries/datas 合并去重后落同一个 _internal/，
    # 所以「只在 CLI 上排除 PIL」等于没排（GUI 收进来、CLI 产物照样带着）。
    rendered = build_exe.SPEC_TEMPLATE.format(
        app=build_exe.APP_NAME,
        bloat_excludes=list(build_exe.BLOAT_EXCLUDES),
        i18n_datas=build_exe.i18n_datas_entries(),
        icon_datas=build_exe.icon_datas_entries(),
        icon=build_exe.icon_spec_value(),
    )
    assert rendered.count("excludes=excludes_bloat +") == 3, "三个 Analysis 必须都挂上排除清单"


def test_i18n_datas_skip_po_sources_but_keep_runtime_formats() -> None:
    # i18n.py 的加载优先级是 .mo → .json → .yaml，*.po 是翻译源文件、运行期不读；
    # 用整目录拷贝（旧写法 ('i18n','i18n')）会把它一起打进分发包。
    entries = build_exe.i18n_datas_entries()
    assert entries, "i18n 资源清单为空（i18n/ 目录缺失或过滤条件写错）"
    sources = [src for src, _dest in entries]
    assert not [s for s in sources if s.endswith(".po")], f"i18n 资源仍含 .po 源文件：{sources}"
    suffixes = {Path(s).suffix for s in sources}
    assert {".mo", ".json", ".yaml"} <= suffixes, f"运行时格式缺失（实际 {sorted(suffixes)}）"
    # 目标路径必须仍落在 i18n/ 下：i18n.py 用 __file__ 定位 _internal/i18n，改了就找不到目录
    assert all(dest == "i18n" or dest.startswith("i18n/") for _src, dest in entries)


def test_qt_bloat_files_stay_inside_the_pyside6_dir() -> None:
    # 剪除清单是「按文件名删」，一旦有人写进 `../` 或绝对形态，剪除就会落到 _internal 之外
    # （甚至仓库里）——体积门禁查不出来，只表现为「构建后某些文件神秘消失」。
    for rel in build_exe.QT_BLOAT_FILES:
        assert not rel.startswith(("/", "\\")) and ":" not in rel, f"剪除项不得为绝对路径：{rel!r}"
        parts = Path(rel).parts
        assert ".." not in parts, f"剪除项不得含路径穿越：{rel!r}"
        # 只允许「根目录 DLL」与「plugins/<类型>/<插件>」两种形态：Qt 的插件永远在这两层下，
        # 更深的路径说明清单写错了（剪不到真正的目标会在体积报告里表现为「剪了但没降」）。
        assert len(parts) in (1, 3) and (len(parts) == 1 or parts[0] == "plugins"), f"剪除项形态异常：{rel!r}"
    # 反向：最大的那一项必须在列（删掉它体积会悄悄回弹约 20MB）
    assert "opengl32sw.dll" in build_exe.QT_BLOAT_FILES


def test_prune_qt_bloat_deletes_only_listed_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 剪除是**文件删除**，比 excludes 危险一档：误删一个真在用的 Qt DLL，冻结产物只在运行时炸。
    # 故这里钉两件事——命中项必删、未命中项（含同目录其它 DLL）必留。
    qt = tmp_path / build_exe.APP_NAME / "_internal" / "PySide6"
    (qt / "plugins" / "imageformats").mkdir(parents=True)
    listed = []
    for rel in build_exe.QT_BLOAT_FILES:
        target = qt / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
        listed.append(target)
    keep = qt / "Qt6Widgets.dll"
    keep.write_text("x", encoding="utf-8")
    keep_plugin = qt / "plugins" / "imageformats" / "qjpeg.dll"
    keep_plugin.write_text("x", encoding="utf-8")
    monkeypatch.setattr(build_exe, "RELEASE_DIR", tmp_path / build_exe.APP_NAME)

    build_exe.prune_qt_bloat()

    assert not any(p.exists() for p in listed), "剪除清单里的文件必须被删掉"
    assert keep.exists() and keep_plugin.exists(), "未列入清单的文件/插件不得被误删"


def test_zip_release_dir_prefixes_members_with_app_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 压缩接缝换成自建 zipfile 后，成员名前缀必须与旧 shutil.make_archive(root_dir=DIST,
    # base_dir=APP_NAME) 同构——_assert_zip_has_no_runtime_artifacts 靠这个前缀判运行期产物，
    # 前缀丢了那条断言会永远绿（正是它存在的意义所在）。
    release = tmp_path / build_exe.APP_NAME
    (release / "config").mkdir(parents=True)
    (release / "config" / "config.ini").write_text("[录制设置]\n", encoding="utf-8")
    monkeypatch.setattr(build_exe, "RELEASE_DIR", release)
    zip_path = tmp_path / "out.zip"
    build_exe._zip_release_dir(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert f"{build_exe.APP_NAME}/config/config.ini" in names
        assert all(n.startswith(f"{build_exe.APP_NAME}/") for n in names), names
        # 必须是 deflate（体积优化的全部意义）
        info = zf.getinfo(f"{build_exe.APP_NAME}/config/config.ini")
        assert info.compress_type == zipfile.ZIP_DEFLATED


# ---------------------------------------------------------------------------
# 运行时钉定的在线来源层（**默认 off**）
#
# 被测面是「在线值在什么条件下才允许影响判据」。三条核心不变量：
#   ① off（默认）：一次网络请求都不发，_pinned_slots() 的结果与引入本层前逐字相同；
#   ② verify 档**永不写入**：在线值只用于比对，写进期望值就等于跳过「人工回填内置表」这道闸口，
#      而那道闸口同时也是「重新确认版本代次 / 体积门禁 / 冒烟」的触发点；
#   ③ adopt 只认「清单有独立认证」的槽位：advisory 档（清单与产物同源同服务器）与
#      「signed 但没钉指纹」一律拒绝采用——前者是 TOFU，后者等于没验。
# 全程离线：urlopen 与 _run_gpg 一律打桩（桩替换 build_exe 的模块全局名，不改 stdlib 本体）。
# ---------------------------------------------------------------------------

_BUILTIN_HEX = "a" * 64
_ONLINE_HEX = "b" * 64
_MANIFEST_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256"


@pytest.fixture
def _clean_pin_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    # 在线层带两个模块级状态（进程内缓存、命令行覆盖）与两个 node 解析结果，不清会串到相邻用例。
    # 缓存尤其危险：上一条用例拉到的值会被下一条当成「刚拉的」，于是「换桩后仍不生效」的假象
    # 会把真正的回归藏起来。
    monkeypatch.setattr(build_exe, "_PIN_ONLINE_CACHE", {})
    monkeypatch.setattr(build_exe, "_PIN_SOURCE_OVERRIDE", None)
    monkeypatch.setattr(build_exe, "_NODE_RESOLVED_VERSION", "")
    monkeypatch.setattr(build_exe, "_NODE_RESOLVED_FILENAME", "")


def _pin_layer_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str,
    key: str = "windows-x64",
    release: bool = False,
    table: dict[str, dict[str, dict[str, str]]],
) -> None:
    monkeypatch.setattr(build_exe, "runtime_slot_key", lambda: key)
    monkeypatch.setattr(build_exe, "require_pinned_hashes", lambda: release)
    monkeypatch.setattr(build_exe, "_PIN_SOURCE_OVERRIDE", mode)
    monkeypatch.setattr(build_exe, "_PIN_SOURCE_TABLE", table)
    monkeypatch.setattr(build_exe, "_PINNED_RUNTIME_SHA256", {key: {"ffmpeg": _BUILTIN_HEX, "node": _BUILTIN_HEX}})


def _advisory_table() -> dict[str, dict[str, dict[str, str]]]:
    return {
        "windows-x64": {
            "ffmpeg": {
                "url": _MANIFEST_URL,
                "trust": build_exe.PIN_TRUST_ADVISORY,
                "kind": build_exe._PIN_KIND_RAW,
            }
        }
    }


def _good_gpg_status() -> bytes:
    return (
        b"[GNUPG:] GOODSIG 1234567890ABCDEF someone@example.org\n"
        b"[GNUPG:] VALIDSIG " + _SIGNING_SUBKEY_FPR.lower().encode("ascii") + b" 1600000000 1600000000 0 4 0 1 22 00\n"
    )


def test_online_layer_is_off_by_default_and_never_touches_network(
    monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None
) -> None:
    # 默认姿态必须是「完全不联网」：CI 的默认路径不该因为引入本层而多出一个外部依赖点
    # （上游清单挂掉就会拖垮发布，而内置表本来是不受它影响的）。
    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("默认 off 的在线层不得发起任何网络请求")

    monkeypatch.setattr(build_exe, "urllib", types.SimpleNamespace(request=types.SimpleNamespace(urlopen=explode)))
    monkeypatch.delenv("DLR_RUNTIME_PIN_SOURCE", raising=False)
    assert build_exe.pin_source_mode() == build_exe.PIN_SOURCE_OFF
    merged = build_exe._pinned_slots()
    assert merged["ffmpeg"] == build_exe._PINNED_RUNTIME_SHA256["windows-x64"]["ffmpeg"].lower()


def test_unrecognized_pin_source_env_value_falls_back_to_off(
    monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None, capsys: pytest.CaptureFixture[str]
) -> None:
    # 拼写错误（"verfiy"）若被当成 verify，等于在维护者不知情时打开了联网路径，故必须告警后按 off。
    monkeypatch.setenv("DLR_RUNTIME_PIN_SOURCE", "verfiy")
    assert build_exe.pin_source_mode() == build_exe.PIN_SOURCE_OFF
    assert "DLR_RUNTIME_PIN_SOURCE" in capsys.readouterr().out


@pytest.mark.parametrize("release", [True, False], ids=["release", "local"])
def test_verify_mode_never_writes_the_online_value(
    monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None, release: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    # verify 的**全部意义**就是「只比对、不写入」：写进去就等于把「人工核对并回填」这道闸口
    # 换成「上游说什么就是什么」，那还不如直接用 adopt。
    _pin_layer_env(monkeypatch, mode=build_exe.PIN_SOURCE_VERIFY, release=release, table=_advisory_table())
    _install_fake_urlopen(monkeypatch, f"{_ONLINE_HEX}  ffmpeg.zip".encode("ascii"))
    if release:
        with pytest.raises(SystemExit):
            build_exe._pinned_slots()
        return
    merged = build_exe._pinned_slots()
    assert merged["ffmpeg"] == _BUILTIN_HEX, "verify 档把在线值写进了期望值，人工回填闸口被绕过"
    assert _ONLINE_HEX in capsys.readouterr().out, "不一致时没把在线值打出来，维护者无从回填"


def test_advisory_source_is_never_adopted(
    monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None, capsys: pytest.CaptureFixture[str]
) -> None:
    # advisory 档的清单与产物同源同服务器：把它当判据，「拉清单 → 当期望值 → 比对产物」三步
    # 恒等通过，钉定等于被降级成 TOFU。故 adopt 必须拒绝并沿用内置值。
    _pin_layer_env(monkeypatch, mode=build_exe.PIN_SOURCE_ADOPT, table=_advisory_table())
    _install_fake_urlopen(monkeypatch, f"{_ONLINE_HEX}  ffmpeg.zip".encode("ascii"))
    assert build_exe._pinned_slots()["ffmpeg"] == _BUILTIN_HEX
    assert build_exe.PIN_TRUST_ADVISORY in capsys.readouterr().out


def test_signed_source_without_pinned_fingerprint_is_never_adopted(
    monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None, capsys: pytest.CaptureFixture[str]
) -> None:
    # 声明 signed 却没钉指纹 = 验签这一步根本没东西可比，adopt 会退化成「清单说什么就是什么」。
    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("未登记指纹的 signed 槽位不得发起验签")

    _pin_layer_env(
        monkeypatch,
        mode=build_exe.PIN_SOURCE_ADOPT,
        table={
            "windows-x64": {
                "ffmpeg": {
                    "url": _MANIFEST_URL,
                    "sig_url": f"{_MANIFEST_URL}.asc",
                    "trust": build_exe.PIN_TRUST_SIGNED,
                    "kind": build_exe._PIN_KIND_RAW,
                    "fingerprint": "",
                }
            }
        },
    )
    _install_fake_urlopen(monkeypatch, f"{_ONLINE_HEX}  ffmpeg.zip".encode("ascii"))
    monkeypatch.setattr(build_exe, "_run_gpg", explode)
    assert build_exe._pinned_slots()["ffmpeg"] == _BUILTIN_HEX
    assert "未登记 40 位主钥指纹" in capsys.readouterr().out


def test_signed_manifest_is_adopted_only_when_its_own_signature_verifies(
    monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None
) -> None:
    # 同一份清单，验签通过才可采用；验签不过（BADSIG）时必须一个字都不改。
    table = {
        "windows-x64": {
            "ffmpeg": {
                "url": "https://nodejs.org/dist/{version}/SHASUMS256.txt",
                "sig_url": "https://nodejs.org/dist/{version}/SHASUMS256.txt.asc",
                "trust": build_exe.PIN_TRUST_SIGNED,
                "kind": build_exe._PIN_KIND_SHASUMS,
                "fingerprint": _PRIMARY_FPR,
                "asset": "ffmpeg.zip",
            }
        }
    }
    _pin_layer_env(monkeypatch, mode=build_exe.PIN_SOURCE_ADOPT, table=table)
    monkeypatch.setattr(build_exe, "_NODE_RESOLVED_VERSION", "v24.21.0")
    _install_fake_urlopen(monkeypatch, f"{_ONLINE_HEX}  ffmpeg.zip".encode("ascii"))
    _install_fake_gpg(
        monkeypatch, keyring=_keyring_record(_PRIMARY_FPR, _SIGNING_SUBKEY_FPR), verify_status=_good_gpg_status()
    )
    assert build_exe._pinned_slots()["ffmpeg"] == _ONLINE_HEX

    monkeypatch.setattr(build_exe, "_PIN_ONLINE_CACHE", {})
    _install_fake_gpg(
        monkeypatch,
        keyring=_keyring_record(_PRIMARY_FPR, _SIGNING_SUBKEY_FPR),
        verify_status=b"[GNUPG:] BADSIG 1234567890ABCDEF someone@example.org\n",
    )
    assert build_exe._pinned_slots()["ffmpeg"] == _BUILTIN_HEX


def test_manifest_needing_version_is_skipped_instead_of_building_a_broken_url(
    monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None, capsys: pytest.CaptureFixture[str]
) -> None:
    # 版本还没解析时拼出的 https://nodejs.org/dist//SHASUMS256.txt 恒 404，报错会指向「上游挂了」，
    # 把真正的原因藏起来。故必须显式跳过。
    _pin_layer_env(
        monkeypatch,
        mode=build_exe.PIN_SOURCE_ADOPT,
        table={
            "windows-x64": {
                "ffmpeg": {
                    "url": "https://nodejs.org/dist/{version}/SHASUMS256.txt",
                    "trust": build_exe.PIN_TRUST_ADVISORY,
                    "kind": build_exe._PIN_KIND_RAW,
                }
            }
        },
    )
    _install_fake_urlopen(monkeypatch, f"{_ONLINE_HEX}  ffmpeg.zip".encode("ascii"))
    assert build_exe._pinned_slots()["ffmpeg"] == _BUILTIN_HEX
    assert "尚未解析 node 版本" in capsys.readouterr().out


@pytest.mark.parametrize(
    "payload",
    [
        b"",  # 空响应体（上游 200 但没内容）
        b"<html><body>404 Not Found</body></html>",  # 错误页被当成清单
        b"deadbeef  ffmpeg.zip",  # 长度不足
        (b"z" * 64) + b"  ffmpeg.zip",  # 长度够但不是十六进制
    ],
    ids=["empty", "html-error-page", "too-short", "non-hex"],
)
def test_online_values_that_fail_the_shape_gate_are_dropped(
    monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None, payload: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    # 形状关只有 _SHA256_PATTERN 一处，与「已钉定」的判定同口径。任何不合法的在线值都必须
    # 按「没拉到」处理，绝不能流进期望值——否则「上游返回了个 HTML」会变成一条假的钉定。
    _pin_layer_env(monkeypatch, mode=build_exe.PIN_SOURCE_ADOPT, table=_advisory_table())
    _install_fake_urlopen(monkeypatch, payload)
    assert build_exe._pinned_slots()["ffmpeg"] == _BUILTIN_HEX
    assert "未解析出 64 位十六进制值" in capsys.readouterr().out


def test_online_manifest_is_fetched_only_once_per_slot(monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None) -> None:
    # _pinned_slots() 每次下载都要跑一遍，同一槽位一轮构建会被问多次；对同一份清单反复请求
    # 既慢又容易被上游限流，故成功值必须进缓存。
    _pin_layer_env(monkeypatch, mode=build_exe.PIN_SOURCE_VERIFY, table=_advisory_table())
    seen = _install_fake_urlopen(monkeypatch, f"{_ONLINE_HEX}  ffmpeg.zip".encode("ascii"))
    build_exe._pinned_slots()
    build_exe._pinned_slots()
    assert seen.count(_MANIFEST_URL) == 1, f"在线清单被重复拉取：{seen}"


def test_online_fetch_failure_never_changes_the_verdict(
    monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None, capsys: pytest.CaptureFixture[str]
) -> None:
    # 拉取失败/超时的处置是「本次不参与判定」而不是「放宽判定」：内置值原样保留，
    # 放行与否仍由 _download_file 的既有闸口决定（本层不抢它的判定）。
    _pin_layer_env(monkeypatch, mode=build_exe.PIN_SOURCE_ADOPT, table=_advisory_table())
    _install_fake_urlopen(monkeypatch, OSError("network down"))
    assert build_exe._pinned_slots()["ffmpeg"] == _BUILTIN_HEX
    assert "在线清单拉取失败" in capsys.readouterr().out


def test_online_pin_table_only_declares_slots_that_have_a_download_point() -> None:
    # 给一个没有下载点的槽位登记在线来源，等于凭空造一个永远不会被真实构建路径走到的假闸口。
    for key, slots in build_exe._PIN_SOURCE_TABLE.items():
        if key == "*":
            for slot in slots:
                assert slot in build_exe.RUNTIME_SLOTS, f"通配段声明了通用槽位之外的 {slot}"
            continue
        assert key in build_exe.RELEASE_RUNTIME_KEYS, f"在线来源表出现未登记的运行时键 {key}"
        for slot in slots:
            assert slot in build_exe.runtime_slots_for(key), f"{key}/{slot} 没有对应的下载点"


def test_every_online_pin_source_url_is_https_on_an_allowlisted_host() -> None:
    # 与产物下载同一条供应链门槛：明文 http 或新增镜像域都必须显式改进 _ALLOWED_HOSTS 并说明理由。
    for key, slots in build_exe._PIN_SOURCE_TABLE.items():
        for slot, entry in slots.items():
            for field in ("url", "sig_url"):
                url = entry.get(field, "")
                if not url:
                    continue
                assert url.startswith("https://"), f"{key}/{slot} 的 {field} 非 TLS：{url}"
                host = url.split("/", 3)[2]
                assert host in _ALLOWED_HOSTS, f"{key}/{slot} 的 {field} 主机 {host} 不在允许清单内"


def test_github_pin_asset_name_matches_the_download_url_basename() -> None:
    # GitHub 档按 assets[].name 匹配：名字若与 _FFMPEG_DOWNLOAD_URLS 里真正下载的那一份脱钩，
    # 会拉到同一 release 下**另一个资产**的 digest，恒失配（且失配看起来像「钉定填错了」）。
    checked = 0
    for key, slots in build_exe._PIN_SOURCE_TABLE.items():
        for slot, entry in slots.items():
            if entry.get("kind") != build_exe._PIN_KIND_GITHUB:
                continue
            assert key in build_exe._FFMPEG_DOWNLOAD_URLS, f"{key} 无 ffmpeg 下载点"
            expected = build_exe._FFMPEG_DOWNLOAD_URLS[key].rsplit("/", 1)[-1]
            assert entry["asset"] == expected, f"{key}/{slot} 的资产名与下载 URL 脱钩：{entry['asset']} != {expected}"
            checked += 1
    assert checked, "没有任何 github 档条目被核对——该档若被整体删掉，本用例会变成空转"


# ---------------------------------------------------------------------------
# M-99（2026-10-21 审查）三处，全部离线：urlopen / gpg 走本文件既有的桩，文件一律落 tmp_path，
# 且**绝不调用** build_exe.main()（那会真打包、真下载、真起 exe）。
#   ① 脱敏与断言只认 CREDENTIAL_FILE_NAMES 两个硬编码名字 + `not item.is_file()` 静默跳过子目录
#      → 改为「递归复制 + 全树判定」；
#   ② ffmpeg/node 的临时归档与 _node_extract/ 建在 RELEASE_DIR 内、只在成功路径清理
#      → 清理落 finally（except 只捕 Exception，SystemExit 那一路必须也覆盖）+ 压缩前实物残留断言；
#   ③ _verify_gpg_artifact 只捕 OSError，条目漏配 sig_url 时 urlopen("") 抛 ValueError 穿透，
#      以未处理异常终止整个构建（绕过 _skip_or_fail 的发布/本地分级处置）。
# ---------------------------------------------------------------------------

_M99_DESC = "ffmpeg (evermeet.ca release)"


@pytest.mark.parametrize("release", [True, False], ids=["release", "local"])
def test_gpg_empty_sig_url_never_reaches_urlopen_and_never_crashes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, release: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    # 空 URL 必须走「取不到签名」那条分级处置，而不是交给 urlopen("") 变成一句 ValueError 堆栈。
    # 桩选 explode：同时锁「零网络请求、零 gpg 进程」——漏配 sig_url 时连试都不该试。
    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("空 sig_url 不得发起网络请求或调用 gpg")

    monkeypatch.setattr(build_exe, "urllib", types.SimpleNamespace(request=types.SimpleNamespace(urlopen=explode)))
    monkeypatch.setattr(build_exe, "_run_gpg", explode)
    _macos_release_env(monkeypatch, release=release)
    artifact = tmp_path / "ffmpeg.zip"
    artifact.write_bytes(b"payload")
    if release:
        with pytest.raises(SystemExit) as caught:
            build_exe._verify_gpg_artifact(artifact, tmp_path / "a.sig", "", _PRIMARY_FPR, _M99_DESC)
        assert "缺 sig_url" in str(caught.value)
    else:
        # 本地路径：留痕 + 返回 False（「验不过」不是「没抛异常」，返回值才是判据）
        assert build_exe._verify_gpg_artifact(artifact, tmp_path / "a.sig", "", _PRIMARY_FPR, _M99_DESC) is False
        assert "缺 sig_url" in capsys.readouterr().out


def test_gpg_malformed_sig_url_is_treated_as_unavailable_not_as_a_build_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 异常面：urlopen 对畸形 URL 抛的是 ValueError（不是 OSError 子类），旧 except 元组接不住 →
    # 穿透成整条构建的未处理异常。处置必须与「网络取不到」一致。
    def raise_value_error(url: str, *args: Any, **kwargs: Any) -> Any:
        raise ValueError("unknown url type: 'not-a-url'")

    monkeypatch.setattr(
        build_exe, "urllib", types.SimpleNamespace(request=types.SimpleNamespace(urlopen=raise_value_error))
    )
    monkeypatch.setattr(build_exe, "_run_gpg", lambda *args, **kwargs: None)
    artifact = tmp_path / "ffmpeg.zip"
    artifact.write_bytes(b"payload")
    _macos_release_env(monkeypatch, release=False)
    assert build_exe._verify_gpg_artifact(artifact, tmp_path / "a.sig", "not-a-url", _PRIMARY_FPR, _M99_DESC) is False
    assert "ValueError" in capsys.readouterr().out, "本地路径必须留一条带异常类型的跳过日志，不能静默"
    _macos_release_env(monkeypatch, release=True)
    with pytest.raises(SystemExit):
        build_exe._verify_gpg_artifact(artifact, tmp_path / "a.sig", "not-a-url", _PRIMARY_FPR, _M99_DESC)


def test_adopt_layer_entry_missing_sig_url_does_not_abort_the_build(
    monkeypatch: pytest.MonkeyPatch, _clean_pin_layer: None, capsys: pytest.CaptureFixture[str]
) -> None:
    # M-99③ 的真实崩溃面在**在线来源层**：signed 条目漏配 sig_url 时 _fetch_online_pin 传 ""，
    # 旧实现里 ValueError 穿出 _verify_gpg_artifact、又不被 _fetch_online_pin 的 except 覆盖，
    # 于是 _pinned_slots()（构建开头就要调）直接崩掉整条构建——即使内置钉定表本来是完整的。
    # 判据：不抛、并且**不采用**在线值（沿用内置表）。
    _pin_layer_env(
        monkeypatch,
        mode=build_exe.PIN_SOURCE_ADOPT,
        table={
            "windows-x64": {
                "ffmpeg": {
                    "url": _MANIFEST_URL,
                    "trust": build_exe.PIN_TRUST_SIGNED,
                    "kind": build_exe._PIN_KIND_RAW,
                    "fingerprint": _PRIMARY_FPR,
                }
            }
        },
    )
    _install_fake_urlopen(monkeypatch, f"{_ONLINE_HEX}  ffmpeg.zip".encode("ascii"))
    _install_fake_gpg(monkeypatch, keyring=_keyring_record(_PRIMARY_FPR), verify_status=_good_gpg_status())
    assert build_exe._pinned_slots()["ffmpeg"] == _BUILTIN_HEX
    assert "缺 sig_url" in capsys.readouterr().out


def test_prepare_config_dir_copies_subdirectories_and_templates_nested_credential_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # M-99① 第一半：旧循环 `if item.name in known or not item.is_file(): continue` 把所有子目录
    # 静默跳过（既不进包、也不进判定面），而日志上「没进包」与「判定过所以安全」长得一模一样。
    repo = tmp_path / "repo"
    src = repo / "config"
    (src / "fonts").mkdir(parents=True)
    (src / "profiles").mkdir(parents=True)
    secret = "http://proxyuser:proxypass@10.0.0.1:8080"
    (src / "config.ini").write_text(f"[录制设置]\n代理地址 = {secret}\n", encoding="utf-8")
    (src / "fonts" / "LICENSE.txt").write_text("font licence note\n", encoding="utf-8")
    (src / "profiles" / "config.ini").write_text(f"[录制设置]\n代理地址 = {secret}\n", encoding="utf-8")
    release = tmp_path / build_exe.APP_NAME
    monkeypatch.setattr(build_exe, "PROJECT_ROOT", repo)
    monkeypatch.setattr(build_exe, "RELEASE_DIR", release)

    build_exe._prepare_config_dir()

    dst = release / "config"
    assert (dst / "fonts" / "LICENSE.txt").is_file(), "子目录仍被静默跳过（M-99① 回归）"
    nested = cast(str, (dst / "profiles" / "config.ini").read_text(encoding="utf-8"))
    assert secret not in nested, "子目录里的同名凭据文件被原样复制进发布目录"
    assert (dst / "config.ini").is_file() and (dst / "URL_config.ini").is_file()


def test_credential_assertion_scans_copied_files_whose_name_is_not_whitelisted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # M-99① 第二半：第三个文件名（不在 CREDENTIAL_FILE_NAMES 里的 cookies.json）此前从不进扫描面，
    # 带着真实凭据进对外 zip 也不会有任何红灯。「复制即判定」要求按**内容**判、不看名字。
    release = tmp_path / build_exe.APP_NAME
    cfg = release / "config"
    (cfg / "profiles").mkdir(parents=True)
    (cfg / "config.ini").write_text("[录制设置]\n代理地址 = \n", encoding="utf-8")
    (cfg / "URL_config.ini").write_text("#https://live.douyin.com/000000000000\n", encoding="utf-8")
    (cfg / "profiles" / "cookies.json").write_text(
        json.dumps({"accessToken": "ghp_" + "x" * 24, "count": 3}), encoding="utf-8"
    )
    monkeypatch.setattr(build_exe, "RELEASE_DIR", release)
    monkeypatch.setattr(build_exe, "PROJECT_ROOT", tmp_path / "nonexistent_root")

    with pytest.raises(SystemExit):
        build_exe.assert_no_credentials_in_release()


def test_credential_assertion_accepts_benign_copied_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 反向对照（放行面）：③ 不得写成「config/ 里有第三个文件就红」——那是把递归复制这条通路整体堵死，
    # 使用者会退回去掉扫描而不是去掉凭据。普通文本/无凭据形态的附属文件必须照常通过。
    release = tmp_path / build_exe.APP_NAME
    cfg = release / "config"
    (cfg / "fonts").mkdir(parents=True)
    (cfg / "config.ini").write_text("[录制设置]\n代理地址 = \n", encoding="utf-8")
    (cfg / "URL_config.ini").write_text("#https://live.douyin.com/000000000000\n", encoding="utf-8")
    (cfg / "fonts" / "LICENSE.txt").write_text("Copyright (c) 2026 Some Foundry\n", encoding="utf-8")
    (cfg / "fonts" / "note.json").write_text('{"family": "Dlr Sans", "weight": 400}\n', encoding="utf-8")
    monkeypatch.setattr(build_exe, "RELEASE_DIR", release)
    monkeypatch.setattr(build_exe, "PROJECT_ROOT", tmp_path / "nonexistent_root")

    build_exe.assert_no_credentials_in_release()  # 不抛异常即通过


def test_ffmpeg_failure_path_purges_temp_archive_from_release_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # M-99②：darwin 分支里「归档解得出但缺 ffmpeg 成员」走 SystemExit（BaseException，穿得过
    # `except Exception`），旧实现的两处 unlink 都在成功路径上，于是那支临时归档就留在
    # RELEASE_DIR 里被下一次 make_zip 整包打进对外 zip。
    _macos_release_env(monkeypatch, release=True)
    monkeypatch.setattr(build_exe, "IS_WIN", False)
    sys_shim = types.SimpleNamespace(**vars(sys))
    sys_shim.platform = "darwin"
    monkeypatch.setattr(build_exe, "sys", sys_shim)
    ffmpeg_zip = tmp_path / "src_ffmpeg.zip"
    _make_zip(ffmpeg_zip, {"README": (b"docs only", 0o644)})
    ffmpeg_url = _artifact_url_for_slot("macos-arm64", "ffmpeg")
    _install_routed_urlopen(monkeypatch, {f"{ffmpeg_url}.sig": b"sig-ffmpeg", ffmpeg_url: ffmpeg_zip.read_bytes()})
    _install_fake_gpg(monkeypatch, keyring=_keyring_record(_PRIMARY_FPR), verify_status=_GOOD_VERIFY_STATUS)

    with pytest.raises(SystemExit):
        build_exe._download_ffmpeg(tmp_path)
    assert not list(tmp_path.glob("_*temp.zip")), "失败路径把临时归档留在了发布目录里（M-99② 回归）"
    assert not list(tmp_path.glob("_*temp.*")), f"残留：{sorted(p.name for p in tmp_path.iterdir())}"


def test_nodejs_failure_path_purges_archive_and_extract_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # node 侧同族：归档已落盘、解压才失败（坏包 / 成员缺失）。_node_extract/ 是**目录**，
    # 留在发布目录里同样会被 _zip_release_dir 的 rglob 收进 zip。
    index = json.dumps([{"version": "v24.22.0", "lts": "Krypton"}]).encode("utf-8")
    _install_fake_urlopen(monkeypatch, index)

    def fake_download(url: str, dest: Path, desc: str, *, slot: str) -> None:
        dest.write_bytes(b"PK\x03\x04 this is not a real archive")

    monkeypatch.setattr(build_exe, "_download_file", fake_download)

    assert build_exe._download_nodejs(tmp_path) is False
    assert not list(tmp_path.glob("node-*")), "node 归档残留在发布目录里（M-99② 回归）"
    assert not (tmp_path / "_node_extract").exists(), "_node_extract/ 残留在发布目录里"


def test_make_zip_refuses_release_dir_with_temp_archive_leftover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 残留断言独立成立：清理是 best-effort（Windows 上 rmtree/unlink 会被句柄占用/杀软挡住），
    # 而分发出去的是 zip，所以必须**在压缩前**按实物再查一次。桩掉 _zip_release_dir 后，
    # 「上游没删干净」这一格仍然要红——否则这条断言就只是 finally 的复读。
    _stub_make_zip_inputs(monkeypatch, tmp_path, [f"{build_exe.APP_NAME}/_internal/a.py"])
    (cast(Path, build_exe.RELEASE_DIR) / "_ffmpeg_temp.zip").write_bytes(b"half downloaded")
    with pytest.raises(SystemExit) as caught:
        build_exe.make_zip("9.9.9")
    assert "_ffmpeg_temp.zip" in str(caught.value)


def test_release_temp_residue_patterns_cover_both_download_chains() -> None:
    # 表与落盘名的同构锁：改临时件的落盘名却忘了改这里，残留断言会静默失效（判的是文件名模式）。
    source = (ROOT / "build_exe.py").read_text(encoding="utf-8")
    for name in build_exe.RELEASE_TEMP_ARCHIVE_GLOBS:
        if name.startswith("node-"):
            continue  # node 归档名由 f-string 拼出，见下方单独核对
        literal = name.replace("*", "")
        assert literal in source, f"残留判据里的 {name} 与任何落盘名都对不上（表漂移）"
    assert "target_dir / filename" in source and "_NODE_ARCH_MAP" in source
    assert "_node_extract" in build_exe.RELEASE_TEMP_DIR_NAMES
    for dir_name in build_exe.RELEASE_TEMP_DIR_NAMES:
        assert dir_name in source, f"{dir_name} 已不再是任何下载链的落盘目录"
