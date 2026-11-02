# scripts/check_runtime_pins.py 的回归用例（随 W1「第 4 类口径」入库）。
#
# 被测面是**闸门的分流语义**，不是仓库当前的钉定数据（数据会变，锁数据会把用例变成倒计时）：
#   ① 发布矩阵内的未钉定槽位 → --strict 必红；
#   ② 矩阵外的键（无 runner 产出）→ 只告警，但**必须被打印出来**（静默省略等于谎称全覆盖）；
#   ③ SOURCE-BUILD-PROVENANCE 标记：证据齐备才算满足，缺证据与「未钉定」同等处置
#      （防「换个更容易填的标记拿免检」的唯一防线）；
#   ④ 缺槽位 / 缺键等结构缺陷 → rc=2（门禁本身坏了 ≠ 代码不合格）。
# 全部离线：_load_build_exe 被打桩成受控表，不触发网络也不读真实 build_exe 的数据。

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
_MATRIX_KEYS = ["windows-x64", "linux-x64", "linux-arm64", "macos-arm64"]
_ALL_KEYS = ("windows-x64", "linux-x64", "linux-arm64", "macos-x64", "macos-arm64")


def _load_checker() -> ModuleType:
    # scripts/ 不在包路径内，按文件路径显式加载（与 test_run_gates.py / check_runtime_pins 自身同手法）
    spec = importlib.util.spec_from_file_location(
        "_runtime_pins_probe_under_test", ROOT / "scripts" / "check_runtime_pins.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_build_exe() -> Any:
    spec = importlib.util.spec_from_file_location("_build_exe_for_pins_probe", ROOT / "build_exe.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()
build_exe = _load_build_exe()

_HEX64 = "a" * 64


def _fake_module(
    table: dict[str, dict[str, str]],
    declared_keys: tuple[str, ...] = _ALL_KEYS,
    slots_for: Any = None,
) -> SimpleNamespace:
    # _slot_is_gated 复用 build_exe 的真实现：判定口径必须只有一份事实源，
    # 打桩打成「恒 True」会让本文件的用例全部失去意义。
    # runtime_slots_for 默认桩成「只有通用两槽」：本文件测的是**分流语义**（矩阵内/外、标记是否
    # 算满足），而「哪个平台该有几个槽」的事实源在 build_exe._EXTRA_EXECUTABLE_URLS，由
    # tests/test_build_exe.py::test_ffprobe_is_a_separate_download_point_only_on_macos 锁。
    return SimpleNamespace(
        _PINNED_RUNTIME_SHA256=table,
        RUNTIME_SLOTS=("ffmpeg", "node"),
        RELEASE_RUNTIME_KEYS=declared_keys,
        runtime_slots_for=slots_for or (lambda key: ("ffmpeg", "node")),
        _slot_is_gated=build_exe._slot_is_gated,
        _is_source_build_marker=build_exe._is_source_build_marker,
        SOURCE_BUILD_PROVENANCE=build_exe.SOURCE_BUILD_PROVENANCE,
        # 官方签名档：判定与标记常量同样只能取自 build_exe（本脚本不得自定口径）
        _is_signature_marker=build_exe._is_signature_marker,
        _is_signature_satisfied=build_exe._is_signature_satisfied,
        OFFICIAL_SIGNATURE_PIN=build_exe.OFFICIAL_SIGNATURE_PIN,
        UNVERIFIED_PIN=build_exe.UNVERIFIED_PIN,
    )


@pytest.fixture(autouse=True)
def _matrix_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # 矩阵固定成 CI 真实四平台，避免本用例随 build-release.yml 的矩阵调整而误红/误绿
    monkeypatch.setattr(checker, "_runtime_matrix_keys", lambda: list(_MATRIX_KEYS))


# MID-2260：上面那条 autouse fixture 把 `_runtime_matrix_keys` **整体桩掉**，于是没有任何
# 用例会驱动真解析器——把真实现改成 `return []`，未钉定槽位都会落进「矩阵外 → 只告警」
# 的桶，`--strict` 对全占位表返回 0，发布链直接放行未经校验的 ffmpeg/node。下面的用例一律
# **先把真实现装回去**（保留模块级引用绕开 autouse），驱动真解析器 + 真分流语义。
_REAL_RUNTIME_MATRIX_KEYS = checker._runtime_matrix_keys


def _restore_real_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checker, "_runtime_matrix_keys", _REAL_RUNTIME_MATRIX_KEYS)


def _unpinned_everywhere() -> dict[str, dict[str, str]]:
    # 「全部槽位仍是占位标记」形态：只有真矩阵参与判定才会红，桩成空矩阵就全绿。
    return {key: {"ffmpeg": build_exe.UNVERIFIED_PIN, "node": build_exe.UNVERIFIED_PIN} for key in _ALL_KEYS}


def test_real_matrix_parser_reads_workflow_runner_tags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _restore_real_matrix(monkeypatch)
    workflow = tmp_path / "build-release.yml"
    workflow.write_text(
        "jobs:\n"
        "  build:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        include:\n"
        "          - os: windows-latest\n"
        "            arch: x64\n"
        "          - os: ubuntu-latest\n"
        "          - os: macos-latest\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "_WORKFLOW", workflow)
    assert checker._runtime_matrix_keys() == ["windows-x64", "linux-x64", "macos-arm64"]


def test_real_matrix_parser_rejects_unregistered_runner_tag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 新 runner 标签未登记进 RUNNER_TO_RUNTIME_KEY 时必须 rc=2：「静默丢掉一个平台」正是
    # 「表里五键都管住了」错觉的来源。样本标签刻意用 ubuntu-24.04-arm64（ubuntu-24.04-arm
    # 已随 linux-arm64 接入矩阵被登记，拿它当反例会让用例退化成「验证接受已知标签」）。
    # 先行断言样本确实不在映射里：将来有人登记了它，本用例以明确信息变红而非静默失去拦截面。
    _restore_real_matrix(monkeypatch)
    assert (
        "ubuntu-24.04-arm64" not in checker.RUNNER_TO_RUNTIME_KEY
    ), "样本标签已被登记进映射，请更换一个真正未登记的 runner 标签"
    workflow = tmp_path / "build-release.yml"
    workflow.write_text(
        "        include:\n          - os: windows-latest\n          - os: ubuntu-24.04-arm64\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "_WORKFLOW", workflow)
    with pytest.raises(SystemExit) as excinfo:
        checker._runtime_matrix_keys()
    assert excinfo.value.code == 2


def test_real_matrix_parser_rejects_workflow_without_os_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 矩阵结构被改写（例如改用 runs-on: ${{ matrix.os }} 的两段式写法）→ 解析不到 os，
    # 绝不能退化成「无平台可查 → 通过」。
    _restore_real_matrix(monkeypatch)
    workflow = tmp_path / "build-release.yml"
    workflow.write_text("jobs:\n  build:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
    monkeypatch.setattr(checker, "_WORKFLOW", workflow)
    with pytest.raises(SystemExit) as excinfo:
        checker._runtime_matrix_keys()
    assert excinfo.value.code == 2


def test_workflow_matrix_and_test_constant_stay_in_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    # 跨文件同源锁：本文件把矩阵「固定成四平台」这件事必须与真 workflow 一致。
    # _MATRIX_KEYS 漂移（矩阵加/删平台而测试没跟）时，autouse fixture 会把真缺口桩掉。
    _restore_real_matrix(monkeypatch)
    assert checker._runtime_matrix_keys() == list(_MATRIX_KEYS), (
        "build-release.yml 的发布矩阵与 tests/test_check_runtime_pins.py 的 _MATRIX_KEYS 不一致，"
        "请同步两处（同 AGENTS.md「版本常量跨 workflow 同值」口径）"
    )


def test_strict_blocks_all_placeholder_table_with_real_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    # MID-2260 的正主：真矩阵 + 全占位表 + --strict 必须 rc=1。
    # 把 `_runtime_matrix_keys` 改成 `return []`（或桩成空列表且无人见证）→ 这里必红。
    _restore_real_matrix(monkeypatch)
    assert (
        _run(monkeypatch, _unpinned_everywhere(), strict=True) == 1
    ), "全占位表在 --strict 下放行：矩阵解析被旁路 = 发布链无校验（SEV-10 形态）"
    # 结构模式仍只报结构问题（rc=0），两种模式的语义不得混用。
    assert _run(monkeypatch, _unpinned_everywhere(), strict=False) == 0


def _run(
    monkeypatch: pytest.MonkeyPatch,
    table: dict[str, dict[str, str]],
    *,
    strict: bool,
    slots_for: Any = None,
) -> int:
    # 只打桩「表从哪来」，判定路径全程走真实现：本文件的价值就在于证明**分流与判据**正确，
    # 若连 check() 一起桩掉就成了自证（AGENTS.md「测试不得自实现被测逻辑」同源）。
    monkeypatch.setattr(checker, "_load_build_exe", lambda: _fake_module(table, slots_for=slots_for))
    return int(checker.check(strict=strict))


def _pinned_table() -> dict[str, dict[str, str]]:
    # 基线取「全部满足」形态，各用例再各自破坏一格——这样任何新增键/槽位都会在基线里暴露
    # （缺槽位 → rc=2），而不是悄悄少测一格。
    return {key: {"ffmpeg": _HEX64, "node": _HEX64} for key in _ALL_KEYS}


def test_real_slot_inventory_is_wired_into_the_coverage_check(monkeypatch: pytest.MonkeyPatch) -> None:
    # 接线锁：check() 必须按 build_exe.runtime_slots_for() 圈定每个键的义务范围。
    # 若把它改回全局 RUNTIME_SLOTS，macOS 的 ffprobe 槽就永远没人查（多一个下载点少一道闸）；
    # 若表里留了个该平台并不存在的槽位，也必须在结构模式就被发现而不是当「多余数据」忽略。
    table = _pinned_table()
    for key in ("macos-x64", "macos-arm64"):
        table[key]["ffprobe"] = _HEX64
    assert _run(monkeypatch, table, strict=False, slots_for=build_exe.runtime_slots_for) == 0
    broken = {key: dict(value) for key, value in table.items()}
    del broken["macos-arm64"]["ffprobe"]
    assert (
        _run(monkeypatch, broken, strict=False, slots_for=build_exe.runtime_slots_for) == 2
    ), "macOS 缺 ffprobe 钉定项却没报结构缺陷：槽位覆盖面又被退回成全局 RUNTIME_SLOTS"
    drifted = {key: dict(value) for key, value in table.items()}
    drifted["windows-x64"]["ffprobe"] = _HEX64
    assert (
        _run(monkeypatch, drifted, strict=False, slots_for=build_exe.runtime_slots_for) == 2
    ), "表里多出该平台没有的下载槽位却被当成没看见"


def test_repository_pin_table_passes_the_real_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    # 用真表 + 真槽位清单跑一遍结构模式：新增运行时键/独立归档件却忘了同步钉定表，
    # 这条是第一道网（--strict 侧的钉定值由 test_real_matrix_parser_* 一族覆盖）。
    monkeypatch.setattr(checker, "_load_build_exe", _load_build_exe)
    assert int(checker.check(strict=False)) == 0


def test_matrix_unpinning_still_blocks_release(monkeypatch: pytest.MonkeyPatch) -> None:
    # 两个模式必须同时成立才叫「没收窄过头」：strict 拦矩阵内缺口，结构模式只报结构问题。
    # 只看 strict 会漏掉另一侧退化——把结构模式也判红，等于每个 PR 都因数据未钉定而挂。
    table = _pinned_table()
    table["linux-x64"]["ffmpeg"] = build_exe.UNVERIFIED_PIN
    assert _run(monkeypatch, table, strict=True) == 1, "矩阵内未钉定却放行 = 发布链被旁路"
    assert _run(monkeypatch, table, strict=False) == 0, "结构模式不应因未钉定变红（那是数据态不是缺陷）"


def test_offmatrix_unpinned_is_warned_not_hidden(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 没有任何 runner 产出 macos-x64 → 要求它钉定既不拦真实产物，又会让人以为「五键都管住了」；
    # 因此它不参与 --strict，但**必须被打印**，否则后来的人会以为表里这些键同样有闸。
    table = _pinned_table()
    table["macos-x64"]["ffmpeg"] = build_exe.UNVERIFIED_PIN
    assert _run(monkeypatch, table, strict=True) == 0
    out = capsys.readouterr().out
    assert "macos-x64/ffmpeg" in out and "不在发布矩阵内" in out, out


def test_source_build_marker_without_evidence_is_not_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    # 第 4 类的标记若比 64 位十六进制更容易填，就必须同等拦下；否则「放宽判定」变成了
    # 一条绕闸通道（与 CR-11 的「空表 + warn 后继续」同一族失效）。
    table = _pinned_table()
    table["macos-arm64"]["ffmpeg"] = build_exe.SOURCE_BUILD_PROVENANCE
    assert _run(monkeypatch, table, strict=True) == 1


def test_source_build_marker_with_full_evidence_passes_and_is_announced(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    evidence = {"source_sha256": "b" * 64, "recipe_sha256": "c" * 64, "provenance_ref": "build-release.yml@sha"}
    monkeypatch.setitem(build_exe._SOURCE_BUILD_EVIDENCE, "macos-arm64", {"ffmpeg": evidence})
    table = _pinned_table()
    table["macos-arm64"]["ffmpeg"] = build_exe.SOURCE_BUILD_PROVENANCE
    assert _run(monkeypatch, table, strict=True) == 0
    assert "第 4 类" in capsys.readouterr().out, "满足第 4 类必须显式说出来，不得与「已钉定」混为一谈"


@pytest.mark.parametrize(
    "broken",
    ["missing_ref", "short_source", "nonhex_recipe", "empty_all"],
    ids=["缺 provenance", "source 长度不足", "recipe 非十六进制", "三件全空"],
)
def test_incomplete_evidence_never_satisfies_the_fourth_class(monkeypatch: pytest.MonkeyPatch, broken: str) -> None:
    good = {"source_sha256": "b" * 64, "recipe_sha256": "c" * 64, "provenance_ref": "build-release.yml@sha"}
    if broken == "missing_ref":
        good.pop("provenance_ref")
    elif broken == "short_source":
        good["source_sha256"] = "b" * 63
    elif broken == "nonhex_recipe":
        good["recipe_sha256"] = "z" * 64
    else:
        good = {}
    monkeypatch.setitem(build_exe._SOURCE_BUILD_EVIDENCE, "macos-arm64", {"ffmpeg": dict(good)})
    table = _pinned_table()
    table["macos-arm64"]["ffmpeg"] = build_exe.SOURCE_BUILD_PROVENANCE
    assert _run(monkeypatch, table, strict=True) == 1, f"证据形态不完整却放行：{broken}"


_SIG_MARKER = build_exe.OFFICIAL_SIGNATURE_PIN


def test_signature_mode_passes_strict_and_is_announced(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 官方签名档是「上游确实不公布哈希」时的合法满足方式（判据 = GPG 验签 + 带外钉死的 40 位主钥
    # 指纹，登记在 build_exe._RUNTIME_GPG_SIGNATURES）。满足时必须放行**且显式播报**：
    # 报告若把它算进「已钉定 64 位十六进制」，就是在谎称发布链拿到的是一手哈希。
    table = _pinned_table()
    table["macos-arm64"]["ffmpeg"] = _SIG_MARKER
    assert _run(monkeypatch, table, strict=True) == 0
    assert "官方签名档" in capsys.readouterr().out, "靠签名管住的槽位必须单独说出来，不得与「已钉定」混为一谈"


def test_signature_marker_without_registration_is_not_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    # 与第 4 类「光有标记不算」同一条防线：登记面在 _RUNTIME_GPG_SIGNATURES，那里没有该槽
    # （或指纹形状不符）就必须与「未钉定」同等拦下——否则填标记比填哈希还容易，闸口等于拆除。
    table = _pinned_table()
    table["linux-x64"]["ffmpeg"] = _SIG_MARKER
    assert _run(monkeypatch, table, strict=True) == 1, "未登记的签名档标记被放行 = 绕闸通道"


def test_missing_slot_is_a_structural_failure_not_a_data_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    # 缺槽位/空表/键不在矩阵内 = 门禁本身失效 → rc=2（与「代码不合格」的 rc=1 必须分开）
    table = _pinned_table()
    del table["windows-x64"]["node"]
    assert _run(monkeypatch, table, strict=False) == 2
    assert _run(monkeypatch, {}, strict=False) == 2, "空表必须硬失败（CR-11 的原始形态）"


def test_missing_build_exe_attribute_exits_two_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # L-29：本门禁取的是 build_exe 的**私有**符号，改名/删除在 build_exe 侧没有任何提示。
    # 旧写法直取属性 → AttributeError 崩溃栈 → rc=1，而 rc=1 在本脚本契约里专指「--strict
    # 查到未钉定项」，于是「门禁自己没跑成」会被读成「发布链有未钉定的二进制」。
    # 缺失一律 rc=2（同「空表 / 取不到表」那一档）。
    fake = _fake_module(_pinned_table())
    del fake._PINNED_RUNTIME_SHA256
    monkeypatch.setattr(checker, "_load_build_exe", lambda: fake)
    with pytest.raises(SystemExit) as excinfo:
        checker.check(strict=False)
    assert excinfo.value.code == 2, "属性缺失被退成崩溃栈/rc=1：门禁失效与发布失败混同"
    err = capsys.readouterr().err
    assert "_PINNED_RUNTIME_SHA256" in err, f"报错须点名缺失的属性，否则无从恢复：{err}"


def test_emit_env_missing_attribute_exits_two_too(monkeypatch: pytest.MonkeyPatch) -> None:
    # --emit-env 是 CI 把钉定值透传给 build job 的唯一通道，同一条属性缺失在这里也必须 rc=2：
    # 退 1 时 build-release.yml 的 prepare job 会把「取不到表」当成「表里有未钉定项」。
    fake = _fake_module(_pinned_table())
    del fake._PINNED_RUNTIME_SHA256
    monkeypatch.setattr(checker, "_load_build_exe", lambda: fake)
    with pytest.raises(SystemExit) as excinfo:
        checker.emit_env()
    assert excinfo.value.code == 2


def test_required_attr_inventory_covers_both_the_fake_and_the_real_build_exe() -> None:
    # 防空转：探测清单本身是「取用点」的镜像，清单为空或漏项时上面两条用例一律不会触发。
    # ① 清单非空；② 本文件的替身模块提供齐这些符号（否则替身会被门禁自己判成缺失）；
    # ③ 真 build_exe.py 也提供齐这些符号（漏一个就是 check() 立刻 rc=2，CI 当场红）。
    required = list(checker._REQUIRED_BUILD_EXE_ATTRS)
    assert required, "探测清单为空 = L-29 的防线没装上"
    fake = _fake_module(_pinned_table())
    assert [name for name in required if not hasattr(fake, name)] == []
    real = _load_build_exe()
    assert [name for name in required if not hasattr(real, name)] == []


def test_matrix_key_missing_from_table_is_structural(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _pinned_table()
    del table["macos-arm64"]
    monkeypatch.setattr(
        checker, "_load_build_exe", lambda: _fake_module(table, declared_keys=("windows-x64", "linux-x64"))
    )
    assert checker.check(strict=True) == 2, "矩阵要建的平台在表里没有 = 覆盖缺口，须按门禁失效处理"


def test_emit_env_exports_the_live_table(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # CI 靠这段 JSON 把钉定值透传给 build job；导出的必须是**同一份事实源**而不是脚本内副本
    monkeypatch.setattr(checker, "_load_build_exe", lambda: _fake_module(_pinned_table()))
    assert checker.emit_env() == 0
    exported = json.loads(capsys.readouterr().out)
    assert set(exported) == set(_ALL_KEYS)
    assert exported["linux-x64"]["node"] == _HEX64
