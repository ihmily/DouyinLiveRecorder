# tests/test_ffmpeg_path_preference.py - 守护「包内 ffmpeg 目录是否前置到 PATH」的判据（W6）
#
# 被测对象：src/ffmpeg_install.should_prepend_bundled_ffmpeg_dir()（判据唯一事实源）
#   + main.py 模块级 PATH 注入段（唯一接线点）。
# 为什么要锁：full 包内置的 macOS ffmpeg 是 evermeet 的 x86_64 静态构建（上游不发布 arm64），
#   原先无条件前置会遮蔽 Apple Silicon 用户已装的 brew 原生 arm64，重编码白付 Rosetta 开销。
#   PATH 优先级是全局副作用，故判据收成「五条同时成立才让位」，本文件逐条钉死这条保守边界：
#     ① 非 darwin（Windows / Linux）恒前置 —— 行为逐字不变；
#     ② darwin 但 machine != arm64（解释器自身跑在 Rosetta 下时也落这里，属刻意的漏判方向）恒前置；
#     ③ 包内目录不存在恒前置；④ 注入前 PATH 上没有 ffmpeg 时恒前置；
#     ⑤ 探到的那份就是包内那份时恒前置（否则日志承诺「原生 arm64」而实际仍是转译构建）；
#     ⑥ 五条全过才返回 False（让位），并留下一条 debug 日志写明哪一份生效。
#
# Mock 口径（AGENTS.md「测试编写强制约定」）：只打桩环境探针 —— sys.platform /
#   platform.machine / shutil.which 一律经 types.SimpleNamespace(**vars(<module>)) 浅拷贝后
#   setattr 到 **ffmpeg_install 的模块全局名**，绝不改 stdlib 模块本体（会波及同进程的 harness
#   守护线程）；判据逻辑走真实代码，不在测试里重算一遍。环境变量不使用 patch.dict(os.environ)
#   （harness 注入的超长变量会让其整体写回抛 ValueError）。

import ast
import importlib.util
import os
import platform
import shutil
import sys
import types
from pathlib import Path

import pytest
from loguru import logger

import src.ffmpeg_install as ffmpeg_install

MAIN_SOURCE = Path(__file__).resolve().parent.parent / "main.py"


def _patch_probes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sys_platform: str,
    machine: str,
    which_result: str | None,
    which_calls: list[tuple[str, str]],
) -> None:
    # 三个环境探针一次性换绑到模块全局名上：判据函数只读这三个值，其余 stdlib 行为保持真实。
    sys_shim = types.SimpleNamespace(**vars(sys))
    sys_shim.platform = sys_platform
    monkeypatch.setattr(ffmpeg_install, "sys", sys_shim)

    platform_shim = types.SimpleNamespace(**vars(platform))
    platform_shim.machine = lambda: machine
    monkeypatch.setattr(ffmpeg_install, "platform", platform_shim)

    def fake_which(cmd: str, mode: int = os.F_OK | os.X_OK, path: str | None = None) -> str | None:
        # 记下调用方传来的 path：判据必须探测「注入前的快照」，不能读实时 os.environ["PATH"]
        # （那样会看见刚被自己前置进来的包内目录，让位永不发生）。
        which_calls.append((cmd, path or ""))
        return which_result

    shutil_shim = types.SimpleNamespace(**vars(shutil))
    shutil_shim.which = fake_which
    monkeypatch.setattr(ffmpeg_install, "shutil", shutil_shim)


def _make_bundle(tmp_path: Path) -> Path:
    # 造一个「包内 ffmpeg 目录已存在」的场景（含可执行文件本身，供自我遮蔽比对）。
    bundle = tmp_path / "app" / "ffmpeg"
    bundle.mkdir(parents=True)
    (bundle / "ffmpeg").write_text("#!/bin/sh\n", encoding="utf-8")
    return bundle


def _make_native(tmp_path: Path) -> tuple[Path, Path]:
    # 典型 Homebrew 落点：目录与包内目录完全不同，其下的 ffmpeg 才是原生 arm64 那一份。
    native_dir = tmp_path / "opt" / "homebrew" / "bin"
    native_dir.mkdir(parents=True)
    native_exec = native_dir / "ffmpeg"
    native_exec.write_text("#!/bin/sh\n", encoding="utf-8")
    return native_dir, native_exec


def _capture_debug() -> tuple[list[str], int]:
    captured: list[str] = []
    handler_id = logger.add(lambda msg: captured.append(str(msg)), level="DEBUG")
    return captured, handler_id


class TestNonDarwinBehaviourUnchanged:
    def test_windows_always_prepends(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Windows 上包内 ffmpeg 由自动安装分支前置生效（见被测模块头「PATH 优先级策略」段），
        # 让位判据必须完全不参与，否则「装完找不到」的老问题回归。
        bundle = _make_bundle(tmp_path)
        calls: list[tuple[str, str]] = []
        _patch_probes(
            monkeypatch,
            sys_platform="win32",
            machine="AMD64",
            which_result=str(tmp_path / "system32" / "ffmpeg.exe"),
            which_calls=calls,
        )
        captured, handler_id = _capture_debug()
        try:
            assert ffmpeg_install.should_prepend_bundled_ffmpeg_dir(str(bundle), str(tmp_path)) is True
        finally:
            logger.remove(handler_id)
        # 短路即返回：不发 which 探针、不写日志（Windows 行为逐字不变）
        assert calls == []
        assert captured == []

    def test_linux_always_prepends(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Linux 镜像里包内目录即用户预期使用的那一份；连 machine 是 arm 系也不让位
        # （判据 ① 先于 ②，平台门控在架构之前）。
        bundle = _make_bundle(tmp_path)
        calls: list[tuple[str, str]] = []
        _patch_probes(
            monkeypatch,
            sys_platform="linux",
            machine="aarch64",
            which_result="/usr/bin/ffmpeg",
            which_calls=calls,
        )
        captured, handler_id = _capture_debug()
        try:
            assert ffmpeg_install.should_prepend_bundled_ffmpeg_dir(str(bundle), "/usr/bin") is True
        finally:
            logger.remove(handler_id)
        assert calls == []
        assert captured == []


class TestDarwinArchitectureGate:
    def test_intel_mac_keeps_prepending(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Intel Mac 上包内构建本身就是原生构建，没有让位理由，也不该发探针。
        bundle = _make_bundle(tmp_path)
        native_dir, _native_exec = _make_native(tmp_path)
        calls: list[tuple[str, str]] = []
        _patch_probes(
            monkeypatch,
            sys_platform="darwin",
            machine="x86_64",
            which_result=str(native_dir / "ffmpeg"),
            which_calls=calls,
        )
        assert ffmpeg_install.should_prepend_bundled_ffmpeg_dir(str(bundle), str(native_dir)) is True
        assert calls == []


class TestBundledDirPresence:
    def test_missing_bundled_dir_keeps_behaviour(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 包内目录不存在（lite 包 / 尚未安装）时无「遮蔽」可言：照常前置，与改动前逐字一致。
        bundle = tmp_path / "app" / "ffmpeg"
        native_dir, native_exec = _make_native(tmp_path)
        calls: list[tuple[str, str]] = []
        _patch_probes(
            monkeypatch,
            sys_platform="darwin",
            machine="arm64",
            which_result=str(native_exec),
            which_calls=calls,
        )
        assert ffmpeg_install.should_prepend_bundled_ffmpeg_dir(str(bundle), str(native_dir)) is True


class TestSystemFfmpegPresence:
    def test_no_system_ffmpeg_keeps_prepending(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        bundle = _make_bundle(tmp_path)
        system_dir = tmp_path / "usr" / "bin"
        system_dir.mkdir(parents=True)
        calls: list[tuple[str, str]] = []
        _patch_probes(
            monkeypatch,
            sys_platform="darwin",
            machine="arm64",
            which_result=None,
            which_calls=calls,
        )
        captured, handler_id = _capture_debug()
        try:
            assert ffmpeg_install.should_prepend_bundled_ffmpeg_dir(str(bundle), str(system_dir)) is True
        finally:
            logger.remove(handler_id)
        # 探测发生在注入之前：用的必须是调用方传来的 PATH 快照
        assert calls == [("ffmpeg", str(system_dir))]
        assert any("未探测到 ffmpeg" in line and "仍前置包内目录" in line for line in captured)

    def test_empty_path_string_keeps_prepending(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # PATH 取空（异常环境）时不得把空串交给 which：which(path=None) 会退回实时
        # os.environ["PATH"]，从而探测到「已经前置进来」的包内目录，让判据自我否定。
        bundle = _make_bundle(tmp_path)
        calls: list[tuple[str, str]] = []
        _patch_probes(
            monkeypatch,
            sys_platform="darwin",
            machine="arm64",
            which_result=str(tmp_path / "ffmpeg-here"),
            which_calls=calls,
        )
        assert ffmpeg_install.should_prepend_bundled_ffmpeg_dir(str(bundle), "") is True
        assert calls == []


class TestSelfShadowGuard:
    def test_system_hit_inside_bundled_dir_keeps_prepending(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 用户把包内目录永久写进了自己的 PATH：让位只是「不前置」，命中的仍是同一份
        # x86_64 构建 —— 此时必须维持前置，且日志不得承诺原生 arm64。
        bundle = _make_bundle(tmp_path)
        calls: list[tuple[str, str]] = []
        _patch_probes(
            monkeypatch,
            sys_platform="darwin",
            machine="arm64",
            which_result=str(bundle / "ffmpeg"),
            which_calls=calls,
        )
        captured, handler_id = _capture_debug()
        try:
            assert ffmpeg_install.should_prepend_bundled_ffmpeg_dir(str(bundle), str(bundle)) is True
        finally:
            logger.remove(handler_id)
        assert any("就是包内目录自身" in line for line in captured)
        # 「不再前置包内目录」是让位分支专属措辞：本分支（自我遮蔽）绝不能走到
        assert all("不再前置包内目录" not in line for line in captured)

    def test_nested_hit_inside_bundled_dir_keeps_prepending(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 包内布局的另一形态（Windows 官方源落在 ffmpeg/bin/ffmpeg.exe，macOS 包也可能
        # 多一层）：前缀判定必须覆盖嵌套，而不是只比 direct child。
        bundle = _make_bundle(tmp_path)
        nested = bundle / "bin" / "ffmpeg"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("#!/bin/sh\n", encoding="utf-8")
        calls: list[tuple[str, str]] = []
        _patch_probes(
            monkeypatch,
            sys_platform="darwin",
            machine="arm64",
            which_result=str(nested),
            which_calls=calls,
        )
        assert ffmpeg_install.should_prepend_bundled_ffmpeg_dir(str(bundle), str(nested.parent)) is True

    def test_symlinked_system_hit_inside_bundled_dir_keeps_prepending(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # macOS 常见形态：/usr/local/bin/ffmpeg -> 包内目录里的真实文件。which 返回链接路径，
        # 字面比较会漏判，故判据必须走 realpath 归一。
        bundle = _make_bundle(tmp_path)
        link_dir = tmp_path / "usr" / "local" / "bin"
        link_dir.mkdir(parents=True)
        link = link_dir / "ffmpeg"
        try:
            link.symlink_to(bundle / "ffmpeg")
        except OSError:
            pytest.skip("symlink not permitted on this host")
        # Windows（无开发者模式 / 无特权）上 symlink_to 不抛错却也造不出真链接：is_symlink() 仍为
        # False、os.readlink() 报 WinError 4390，于是下面走的是「普通文件」路径——realpath 归一判据
        # 根本没被覆盖，断言恒假。按既有约定显式跳过。
        if not link.is_symlink():
            pytest.skip("symlink silently unsupported: symlink_to() created no real link on this host")
        calls: list[tuple[str, str]] = []
        _patch_probes(
            monkeypatch,
            sys_platform="darwin",
            machine="arm64",
            which_result=str(link),
            which_calls=calls,
        )
        assert ffmpeg_install.should_prepend_bundled_ffmpeg_dir(str(bundle), str(link_dir)) is True


class TestYieldToNativeFfmpeg:
    def test_arm64_with_external_native_ffmpeg_yields(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        bundle = _make_bundle(tmp_path)
        native_dir, native_exec = _make_native(tmp_path)
        calls: list[tuple[str, str]] = []
        _patch_probes(
            monkeypatch,
            sys_platform="darwin",
            machine="arm64",
            which_result=str(native_exec),
            which_calls=calls,
        )
        captured, handler_id = _capture_debug()
        try:
            assert ffmpeg_install.should_prepend_bundled_ffmpeg_dir(str(bundle), str(native_dir)) is False
        finally:
            logger.remove(handler_id)
        assert calls == [("ffmpeg", str(native_dir))]
        # 决策必须可观测：恰好一条 debug，两个候选路径都在，且不打印整条 PATH
        assert len(captured) == 1
        line = captured[0]
        # 包内目录按 realpath 归一后入日志（与判据 ⑤ 的比对基准同源）
        assert "让位于系统原生 ffmpeg" in line
        assert str(native_exec) in line
        assert os.path.realpath(str(bundle)) in line
        assert str(native_dir) + os.pathsep not in line


def _assigns_path_env(node: ast.If) -> bool:
    # 判定分支体内是否有对 os.environ["PATH"] 的赋值（PATH 注入段的形状特征）
    for child in ast.walk(node):
        if not isinstance(child, ast.Assign):
            continue
        for target in child.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "PATH"
            ):
                return True
    return False


class TestMainWiring:
    # main.py 只做一次调用、判据不外泄：把条件内联回入口文件（或干脆忘了接线）都会让
    # 上面的分支覆盖失去意义，故对源码 AST 做静态锁。

    @staticmethod
    def _module_level_path_if_nodes() -> list[ast.If]:
        tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"), filename=str(MAIN_SOURCE))
        return [node for node in tree.body if isinstance(node, ast.If) and _assigns_path_env(node)]

    def test_path_prepend_is_guarded_by_the_single_judgement(self) -> None:
        nodes = self._module_level_path_if_nodes()
        assert nodes, "main.py 模块级找不到 PATH 注入分支（接线点被移动？）"
        guarded = 0
        for node in nodes:
            for call in ast.walk(node.test):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "should_prepend_bundled_ffmpeg_dir"
                ):
                    guarded += 1
        assert guarded == 1, "PATH 前置必须由 should_prepend_bundled_ffmpeg_dir 裁决且只裁决一次"

    def test_judgement_is_imported_from_ffmpeg_install(self) -> None:
        tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"), filename=str(MAIN_SOURCE))
        imported = [
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "src.ffmpeg_install"
            for alias in node.names
        ]
        assert "should_prepend_bundled_ffmpeg_dir" in imported

    def test_existing_duplicate_insert_guard_kept(self) -> None:
        # 「已在 PATH 里就不重复插入」是改动前就有的守卫，不得被新判据顶掉。
        source = MAIN_SOURCE.read_text(encoding="utf-8")
        assert "not in _current_path.split(os.pathsep)" in source


# ---------------------------------------------------------------------------
# 孪生副本等价锁（R-5）
#
# scripts/douyin_live_recorder_standalone.py 按设计不 import src/（可独立单文件分发），
# 因此同一判据在那里有一份**同名同语义副本**（先例：src/scheduler.py 与它的并发副本）。
# 复制件的通病是「单边修改 → 语义漂移」，而漂移的后果正好是 R-5 登记的那件事：
# 主程序让位给原生 arm64、单文件版继续吃 Rosetta。所以这里刻意**不重复写一遍期望值**，
# 而是把两个实现放进同一组桩里逐一比对结果 —— 谁改了判据而另一边没跟上，本用例就红。
# ---------------------------------------------------------------------------

STANDALONE_SOURCE = Path(__file__).resolve().parent.parent / "scripts" / "douyin_live_recorder_standalone.py"


def _load_standalone(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    # 必须先注册进 sys.modules 再 exec_module：该文件里有 @dataclass，dataclasses._is_type 会回查
    # sys.modules[cls.__module__]，未注册时取到 None 直接 AttributeError（实测踩过；加载这个
    # 单文件脚本的人也会踩，所以写在这里兼当文档）。
    spec = importlib.util.spec_from_file_location("_dlr_standalone_twin_probe", STANDALONE_SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def _patch_twin_probes(
    monkeypatch: pytest.MonkeyPatch,
    modules: list[types.ModuleType],
    *,
    sys_platform: str,
    machine: str,
    which_result: str | None,
) -> None:
    # 每个模块各做一份浅拷贝桩、喂同一个值：比的是判据本身，不是桩的差异。
    for module in modules:
        sys_shim = types.SimpleNamespace(**vars(sys))
        sys_shim.platform = sys_platform
        monkeypatch.setattr(module, "sys", sys_shim)

        platform_shim = types.SimpleNamespace(**vars(platform))
        platform_shim.machine = lambda: machine
        monkeypatch.setattr(module, "platform", platform_shim)

        shutil_shim = types.SimpleNamespace(**vars(shutil))
        shutil_shim.which = lambda cmd, mode=0, path=None: which_result
        monkeypatch.setattr(module, "shutil", shutil_shim)


def _twin_pair(monkeypatch: pytest.MonkeyPatch) -> tuple[types.ModuleType, types.ModuleType]:
    standalone = _load_standalone(monkeypatch)
    assert hasattr(standalone, "should_prepend_bundled_ffmpeg_dir"), "单文件版丢了孪生判据 = 漂移成「永远优先包内」"
    return ffmpeg_install, standalone


@pytest.mark.parametrize(
    ("sys_platform", "machine", "use_bundle", "which_kind", "expected"),
    [
        # 判据 1：非 darwin 恒前置（即使系统装了别的 ffmpeg 也不改行为）
        ("win32", "AMD64", True, "native", True),
        ("win32", "AMD64", True, "none", True),
        ("linux", "x86_64", True, "native", True),
        # 判据 2：架构必须是 arm64 —— 这一格**必须带 native 命中**，否则判据 4 会先短路，
        # 整条矩阵就区分不出「谁删了架构判据」（第一版就栽在这里，故显式配成对）
        ("darwin", "x86_64", True, "native", True),
        ("darwin", "x86_64", True, "none", True),
        # 判据 3/4/5：包内目录存在、注入前另有 ffmpeg、且那份不在包内
        ("darwin", "arm64", False, "native", True),
        ("darwin", "arm64", True, "none", True),
        ("darwin", "arm64", True, "self", True),
        # 五条全过 → 两侧都必须让位
        ("darwin", "arm64", True, "native", False),
    ],
    ids=[
        "windows+native",
        "windows+none",
        "linux+native",
        "intel-mac+native",
        "intel-mac+none",
        "无包内目录",
        "系统无 ffmpeg",
        "自我遮蔽",
        "五条全过",
    ],
)
def test_twin_agrees_on_every_criterion_combination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_platform: str,
    machine: str,
    use_bundle: bool,
    which_kind: str,
    expected: bool,
) -> None:
    main_mod, standalone = _twin_pair(monkeypatch)
    bundle = _make_bundle(tmp_path / "main")
    native_dir, native_exe = _make_native(tmp_path / "native")
    bundled_dir = str(bundle) if use_bundle else str(tmp_path / "not-there")
    # which_kind 决定「系统 PATH 上探到什么」：none=没有；self=探到包内那份（自我遮蔽）；
    # native=探到包外的原生构建。三种都要喂给两侧，否则矩阵无法逐条区分判据。
    if which_kind == "none":
        which_result: str | None = None
    elif which_kind == "self":
        which_result = str(bundle / "ffmpeg")
    else:
        which_result = str(native_exe)
    _patch_twin_probes(
        monkeypatch, [main_mod, standalone], sys_platform=sys_platform, machine=machine, which_result=which_result
    )

    from_main = main_mod.should_prepend_bundled_ffmpeg_dir(bundled_dir, "some/path")
    from_standalone = standalone.should_prepend_bundled_ffmpeg_dir(bundled_dir, "some/path")
    assert from_main == from_standalone, f"两份实现漂移：main={from_main} standalone={from_standalone}"
    assert (
        from_main is expected
    ), f"判据本身变了：{sys_platform}/{machine}/{which_kind} 期望 {expected} 实得 {from_main}"
    assert native_dir.is_dir() and bundle.is_dir()


def test_twin_agrees_when_all_five_criteria_hold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 五条全过 → 两侧都必须返回 False（让位）。这是唯一「行为会变化」的分支，漂移代价最大。
    main_mod, standalone = _twin_pair(monkeypatch)
    bundle = _make_bundle(tmp_path)
    native_dir, native_exe = _make_native(tmp_path)
    _patch_twin_probes(
        monkeypatch, [main_mod, standalone], sys_platform="darwin", machine="arm64", which_result=str(native_exe)
    )

    assert main_mod.should_prepend_bundled_ffmpeg_dir(str(bundle), "some/path") is False
    assert standalone.should_prepend_bundled_ffmpeg_dir(str(bundle), "some/path") is False
    assert native_dir.is_dir()


def test_twin_agrees_on_the_self_shadow_form(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 自我遮蔽（探到的就是包内那份）：两侧都必须维持包内优先，否则日志会承诺原生 arm64 而实际没变。
    main_mod, standalone = _twin_pair(monkeypatch)
    bundle = _make_bundle(tmp_path)
    _patch_twin_probes(
        monkeypatch, [main_mod, standalone], sys_platform="darwin", machine="arm64", which_result=str(bundle / "ffmpeg")
    )

    from_main = main_mod.should_prepend_bundled_ffmpeg_dir(str(bundle), "some/path")
    from_standalone = standalone.should_prepend_bundled_ffmpeg_dir(str(bundle), "some/path")
    assert (
        from_main is True and from_standalone is True
    ), f"自我遮蔽分支不一致：main={from_main} standalone={from_standalone}"


def test_standalone_resolves_ffmpeg_through_the_twin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 接线锁：find_ffmpeg 必须真的过这道判据（光有函数不接线 = 等于没修 R-5）。
    _main_mod, standalone = _twin_pair(monkeypatch)
    calls: list[tuple[str, str]] = []

    def spy(bundled_dir: str, current_path: str) -> bool:
        calls.append((bundled_dir, current_path))
        return True

    monkeypatch.setattr(standalone, "should_prepend_bundled_ffmpeg_dir", spy)
    # 把「脚本同级」改到 tmp 下并造出包内可执行文件：__file__ 是模块全局名，函数内
    # Path(__file__) 会读到它 —— 不碰 os.name（那是 stdlib 模块本体，改了会影响整个进程）。
    scripts_dir = tmp_path / "app" / "scripts"
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    (scripts_dir / "ffmpeg").mkdir(parents=True)
    (scripts_dir / "ffmpeg" / exe).write_text("x", encoding="utf-8")
    monkeypatch.setattr(standalone, "__file__", str(scripts_dir / "standalone.py"))

    found = standalone.find_ffmpeg()
    assert calls, "find_ffmpeg 没有调用判据，说明复制的函数是死代码"
    assert found == str(scripts_dir / "ffmpeg" / exe), f"判据返回「包内优先」时结果变了: {found}"


def test_both_copies_cross_reference_each_other() -> None:
    # 「两处同改」全靠注释互相点名来兑现（scheduler 副本先例的教训：只有副本侧指回、
    # 主实现侧没有回指，就会有人只改一边）。这条锁的是这条防线的存在本身。
    src_text = Path(ffmpeg_install.__file__).read_text(encoding="utf-8")
    twin_text = STANDALONE_SOURCE.read_text(encoding="utf-8")
    assert "douyin_live_recorder_standalone.py" in src_text, "主实现侧没有指向副本的回指注释"
    assert "src/ffmpeg_install" in twin_text, "副本侧没有指回主实现"
