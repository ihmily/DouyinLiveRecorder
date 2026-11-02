# scripts/sync_metadata.py 与 scripts/smoke_test.py 的**错误处理契约**回归锁（WP-I / M-32）。
#
# 被测面（两块都是「退出码 + 降级路径」契约，不是业务逻辑）：
#   ① sync_metadata.regenerate()：PATH 无 uv 时不得抛栈，必须落 WARN，且**不依赖 uv 的
#      egg-info 重建仍要执行**；--check 一侧必须保持纯读（零子进程、零联网），退出码 0/1
#      语义不变（CI static job 在未装项目依赖的 job 里跑它）。
#   ② smoke_test.load_config()：任意形态畸形（checks 非 array、检查项非 object、
#      headers/expect_json 非 object、expect_contains/base_url 类型错）都必须退 2 且
#      无崩溃栈；合法配置的 0/1/2 判定路径不得回归。
#
# 全程离线：subprocess / urlopen 一律替身，绝不真跑 uv、setuptools egg_info 或 HTTP，
# 也绝不改写仓库里的 uv.lock 与 DouyinLiveRecorder.egg-info（派生产物，CI 靠 --check 校验）。
# 文件级用例设计参照 tests/test_run_gates.py / tests/test_build_exe.py 的 scripts/ 加载惯例。

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_script(filename: str) -> Any:
    # scripts/ 不在包路径内：按文件路径显式加载（与 test_run_gates._load_run_gates 同法）。
    # 返回 Any 而非 ModuleType：被测面是「脚本内的私有函数 + 模块全局替换」，
    # ModuleType 的属性访问本就是 Any，这里不靠类型收窄、只靠真实调用。
    spec = importlib.util.spec_from_file_location(f"_{filename[:-3]}_probe", ROOT / "scripts" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync_metadata = _load_script("sync_metadata.py")
smoke_test = _load_script("smoke_test.py")

# which 命中时返回的哨兵路径：只用于断言「子进程参数用的是解析后的绝对路径」，
# 不指向任何真实文件（用例里进程从未真的起来）。
UV_FAKE_PATH = "__fake_uv_on_path__"


class _Completed:
    # subprocess.run 返回值的最小形态：本文件只读 returncode。

    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


class _FakeEnv:
    # uv 安装状态 + 子进程返回值的一体化环境模型。
    # 为什么把 which 与 subprocess 放在同一个对象里：二者必须共享同一个事实（PATH 里有没有
    # uv）。若 which 说「没有」而 run 却优雅地返回非 0，用例就是在验证一个现实里不存在的
    # 世界——真机器上按裸名启动不存在的程序抛的是 FileNotFoundError，而**那正是 M-32① 的
    # 原始触发形态**（旧代码只看 returncode，从不预期异常，于是崩栈 + egg-info 段被带走）。
    def __init__(
        self,
        uv_path: str | None,
        probe_rc: int = 0,
        lock_rc: int = 0,
        probe_exc: OSError | None = None,
        lock_exc: OSError | None = None,
        lock_timeout: bool = False,
        egg_timeout: bool = False,
    ) -> None:
        self.uv_path = uv_path
        self.probe_rc = probe_rc
        self.lock_rc = lock_rc
        self.probe_exc = probe_exc
        self.lock_exc = lock_exc
        # M-94 新增两个超时形态开关：TimeoutExpired 不是 OSError 子类，
        # 不能复用 *_exc 通道（那条锁的是「无法启动 → 本段 WARN 降级」，语义完全不同）。
        self.lock_timeout = lock_timeout
        self.egg_timeout = egg_timeout
        self.calls: list[tuple[str, list[str]]] = []
        self.call_kwargs: list[dict[str, Any]] = []

    def which(self, name: str) -> str | None:
        return self.uv_path if name == "uv" else None

    def _exec_lookup(self, cmd: list[str]) -> None:
        # 裸名 "uv" 且 PATH 无 uv → 复刻 OS 查找失败。其余（sys.executable / 哨兵路径）视为可执行。
        if cmd and cmd[0] == "uv" and self.uv_path is None:
            raise FileNotFoundError(2, "bootscript: uv not found on PATH")

    def run(self, cmd: list[str], *args: Any, **kwargs: Any) -> _Completed:
        self._exec_lookup(list(cmd))
        self.calls.append(("run", list(cmd)))
        if self.probe_exc is not None:
            raise self.probe_exc
        return _Completed(self.probe_rc)

    def call(self, cmd: list[str], *args: Any, **kwargs: Any) -> int:
        argv = list(cmd)
        self._exec_lookup(argv)
        self.calls.append(("call", argv))
        self.call_kwargs.append(dict(kwargs))
        is_uv_lock = len(argv) > 1 and argv[1] == "lock"
        if is_uv_lock and self.lock_timeout:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=0)
        if is_uv_lock and self.lock_exc is not None:
            raise self.lock_exc
        if not is_uv_lock and self.egg_timeout:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=0)
        return self.lock_rc if is_uv_lock else 0

    # ---- 断言辅助：三个形态各自只看自己关心的那一段调用序列 ----
    def egg_calls(self) -> list[list[str]]:
        # egg-info 重建的识别锚：`-c` 后的代码串里带 egg_info（与 sys.executable 一起构成命令）。
        return [cmd for kind, cmd in self.calls if kind == "call" and len(cmd) > 2 and "egg_info" in cmd[2]]

    def uv_lock_calls(self) -> list[list[str]]:
        return [cmd for kind, cmd in self.calls if kind == "call" and len(cmd) > 1 and cmd[1] == "lock"]

    def probes(self) -> list[list[str]]:
        return [cmd for kind, cmd in self.calls if kind == "run"]


def _install(monkeypatch: pytest.MonkeyPatch, fake: _FakeEnv) -> _FakeEnv:
    # 只替换被测模块全局的 subprocess / shutil 引用（浅 namespace，见 AGENTS.md 的
    # 「patch subprocess 必须替换模块全局引用」条目）：不改 stdlib 本体，避免波及同进程
    # 其它用例与 harness 自身的子进程。
    # shutil 用 raising=False 打桩：本模块的 shutil 是修复（M-32① which 探测）才引入的，
    # 若要求属性必须存在，变异验证回退到修复前形态时用例只会因「属性不存在」而红，
    # 看不到真实失效面（FileNotFoundError 崩栈 + egg-info 段被带走）。改成强制装上后，
    # 旧形态仍会走 subprocess.run(["uv", ...]) → 命中本替身的 FileNotFoundError → 红在行为上。
    monkeypatch.setattr(sync_metadata, "shutil", types.SimpleNamespace(which=fake.which), raising=False)
    # 替身必须从**真 subprocess 命名空间**浅拷贝再覆盖两个入口（AGENTS.md 的 shim 口径）：
    # 只挑 run/call 会让替身缺 TimeoutExpired 等同模块常量，被测代码新增 except 分支时
    # 替身先 AttributeError，报错还被读成生产缺陷（M-94 加超时上界时实测踩到）。
    subprocess_shim = types.SimpleNamespace(**vars(subprocess))
    subprocess_shim.run = fake.run
    subprocess_shim.call = fake.call
    monkeypatch.setattr(sync_metadata, "subprocess", cast(Any, subprocess_shim))
    # regenerate() 末尾会 check() 真实仓库产物：钉成幂等，使「降级路径」用例与
    # 「别人正在改 pyproject/uv.lock」解耦（那是环境耦合，不是行为回归）。
    monkeypatch.setattr(sync_metadata, "check", lambda: True)
    return fake


class TestSyncMetadataUvDegradation:
    def test_missing_uv_warns_and_still_rebuilds_egg_info(self, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
        # M-32① 主用例：PATH 无 uv → ① WARN 可达（旧形态此处是 FileNotFoundError 崩溃栈），
        # ② egg-info 重建照常执行（旧形态整段 regenerate 被异常带走，一步都不剩）。
        fake = _install(monkeypatch, _FakeEnv(uv_path=None))
        assert sync_metadata.regenerate() is True

        err = capsys.readouterr().err
        assert "WARN" in err and "uv" in err, f"未见 uv 降级 WARN: {err!r}"
        assert fake.probes() == [], "PATH 无 uv 时不该再按裸名起探测子进程（应走 which 早退）"
        assert len(fake.egg_calls()) == 1, f"uv 缺失必须不影响 egg-info 重建，实际调用序列={fake.calls}"
        assert fake.uv_lock_calls() == []

    def test_uv_probe_oserror_warns_and_still_rebuilds_egg_info(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        # which 命中但不可 exec（命中目录 / 无执行位 / Windows 同名非 exe 文件）：
        # 与「PATH 没有」同属降级，不得抛栈，且 egg-info 段照样要跑。
        fake = _install(monkeypatch, _FakeEnv(uv_path=UV_FAKE_PATH, probe_exc=PermissionError(13, "not executable")))
        assert sync_metadata.regenerate() is True

        err = capsys.readouterr().err
        assert "PermissionError" in err and "WARN" in err, f"未见 OSError 归因 WARN: {err!r}"
        assert len(fake.egg_calls()) == 1
        assert fake.uv_lock_calls() == []

    def test_uv_probe_nonzero_returncode_skips_lock_but_rebuilds_egg_info(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        # uv 存在但 --version 非 0（损坏安装/包装脚本失败）：不进入 uv lock，但仍重建 egg-info。
        fake = _install(monkeypatch, _FakeEnv(uv_path=UV_FAKE_PATH, probe_rc=1))
        assert sync_metadata.regenerate() is True

        assert "WARN" in capsys.readouterr().err
        assert fake.uv_lock_calls() == []
        assert len(fake.egg_calls()) == 1

    def test_uv_lock_failure_still_rebuilds_egg_info(self, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
        # uv lock 本身失败（离线/锁冲突）：WARN 保留旧语义，egg-info 段不得被连带跳过。
        fake = _install(monkeypatch, _FakeEnv(uv_path=UV_FAKE_PATH, lock_rc=1))
        assert sync_metadata.regenerate() is True

        assert "uv lock 执行失败" in capsys.readouterr().err
        assert len(fake.uv_lock_calls()) == 1
        assert len(fake.egg_calls()) == 1

    def test_uv_lock_exec_failure_still_rebuilds_egg_info(self, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
        # uv lock 无法启动（探测与启动之间 PATH 变动 / 文件被替换）：同属降级，不退栈。
        fake = _install(monkeypatch, _FakeEnv(uv_path=UV_FAKE_PATH, lock_exc=FileNotFoundError(2, "uv vanished")))
        assert sync_metadata.regenerate() is True

        err = capsys.readouterr().err
        assert "FileNotFoundError" in err and "WARN" in err
        assert len(fake.egg_calls()) == 1

    def test_happy_path_orders_uv_lock_before_egg_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 装了 uv 的机器：原有行为不回归 —— 探测 → uv lock → egg_info 三段齐全、顺序不变。
        fake = _install(monkeypatch, _FakeEnv(uv_path=UV_FAKE_PATH))
        assert sync_metadata.regenerate() is True

        assert len(fake.probes()) == 1 and fake.probes()[0] == [UV_FAKE_PATH, "--version"]
        assert len(fake.uv_lock_calls()) == 1
        assert len(fake.egg_calls()) == 1
        # 顺序锁：探测在最前，egg-info 在最后
        assert fake.calls[0][0] == "run"
        assert fake.calls[-1] == ("call", fake.egg_calls()[0])

    def test_check_path_spawns_no_subprocess(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # --check 是 CI static job 的门禁：纯读三张文件，**绝不允许**调 subprocess / 联网。
        # 本用例把子进程入口全换成 tripwire，任何一次调用都会当场红（M-32① 的修复把 which
        # 引入 regenerate 一侧，这里锁住它没有被 --check 路径顺带牵进来）。
        def boom(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("--check 路径不得启动任何子进程/可执行文件查找")

        monkeypatch.setattr(sync_metadata, "subprocess", types.SimpleNamespace(run=boom, call=boom))
        # raising=False 同上：--check 一侧本就不该碰 shutil/subprocess，装得上装不上都不该
        # 影响本用例的结论（它锁的是「修复没有把子进程牵进只读路径」，不是锁 shutil 存在）。
        monkeypatch.setattr(sync_metadata, "shutil", types.SimpleNamespace(which=boom), raising=False)
        _write_consistent_metadata(monkeypatch, tmp_path)

        assert sync_metadata.check() is True

    def test_check_exit_codes_unchanged(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # 退出码语义锁：一致 → 0；漂移 → 1。且漂移只由文件内容决定，不由「工具装没装」决定。
        def boom(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("--check 路径不得启动任何子进程/可执行文件查找")

        monkeypatch.setattr(sync_metadata, "subprocess", types.SimpleNamespace(run=boom, call=boom))
        monkeypatch.setattr(sync_metadata, "shutil", types.SimpleNamespace(which=boom), raising=False)
        _write_consistent_metadata(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "argv", ["sync_metadata.py", "--check"])
        with pytest.raises(SystemExit) as ok:
            sync_metadata.main()
        assert cast(int, ok.value.code) == 0

        # 把 egg-info 版本改漂移一格：必须 1（旧脚本从不判这个 = 假绿）。
        pkg_info = sync_metadata.EGG_INFO / "PKG-INFO"
        pkg_info.write_text(
            pkg_info.read_text(encoding="utf-8").replace("Version: 9.9.9", "Version: 9.9.8"), encoding="utf-8"
        )
        with pytest.raises(SystemExit) as drift:
            sync_metadata.main()
        assert cast(int, drift.value.code) == 1

    def test_unreadable_artifact_exits_two_without_traceback(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any, tmp_path: Path
    ) -> None:
        # 产物「存在但不可读」是「没跑成」（rc=2，同 _RC_TIMEOUT 分档），
        # 不是「元数据漂移」（rc=1），更不是裸栈崩穿——两者排障方向相反。用同名目录替身触发
        # IsADirectoryError（exists() 为真、read_text 必抛 OSError），比真实 chmod 稳
        # （Windows 管理员下只读位不拦截读）。
        _write_consistent_metadata(monkeypatch, tmp_path)
        bad_lock = tmp_path / "uv.lock_dir"
        bad_lock.mkdir()
        monkeypatch.setattr(sync_metadata, "UV_LOCK", bad_lock)
        monkeypatch.setattr(sys, "argv", ["sync_metadata.py", "--check"])
        with pytest.raises(SystemExit) as exc:
            sync_metadata.main()
        assert cast(int, exc.value.code) == 2
        captured = capsys.readouterr()
        assert "Traceback" not in captured.err, f"不可读产物不得逃逸崩溃栈: {captured.err}"
        assert "无法读取/解析" in captured.err


def _write_consistent_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 三个路径常量一起搬到 tmp_path：--check 的判定完全由本用例自造的文件决定，
    # 与仓库当前 pyproject/uv.lock/egg-info 的真实状态无关（别的 agent 正在改它们）。
    pyproject = tmp_path / "pyproject.toml"
    _ = pyproject.write_text('[project]\nname = "DouyinLiveRecorder"\nversion = "9.9.9"\n', encoding="utf-8")
    uv_lock = tmp_path / "uv.lock"
    _ = uv_lock.write_text(
        '[[package]]\nname = "douyinliverecorder"\nversion = "9.9.9"\nsource = { editable = "." }\n', encoding="utf-8"
    )
    egg_info = tmp_path / "DouyinLiveRecorder.egg-info"
    egg_info.mkdir()
    _ = (egg_info / "PKG-INFO").write_text(
        "Metadata-Version: 2.4\nName: DouyinLiveRecorder\nVersion: 9.9.9\n", encoding="utf-8"
    )
    monkeypatch.setattr(sync_metadata, "PYPROJECT", pyproject)
    monkeypatch.setattr(sync_metadata, "UV_LOCK", uv_lock)
    monkeypatch.setattr(sync_metadata, "EGG_INFO", egg_info)


# ---------- smoke_test：配置形态与退出码 ----------
# 畸形形态清单：(配置对象, 报错里必须出现的键名, 报错里必须出现的期望形状词)。
# 期望形状词用 JSON 术语（array/object），与 _json_type / _SHAPE_REQUIREMENTS 的文案同源。
MALFORMED_CONFIGS: list[tuple[object, str, str]] = [
    ({"checks": {"path": "/"}}, "checks", "array"),
    ({"checks": "/health"}, "checks", "array"),
    ({"checks": ["just-a-string"]}, "checks[0]", "object"),
    ({"checks": [{"path": "/", "headers": "Referer: https://x/"}]}, "headers", "object"),
    ({"checks": [{"path": "/", "headers": ["Referer"]}]}, "headers", "object"),
    ({"checks": [{"path": "/", "expect_json": ["status"]}]}, "expect_json", "object"),
    ({"checks": [{"path": "/", "expect_contains": "欢迎"}]}, "expect_contains", "array"),
    # L-31：容器形态对、元素形态错同样属畸形。run_check 的 `token in content`
    # 对数字/对象元素抛 TypeError 并穿透 main()（只接 OSError/ValueError）→ rc=1 崩溃栈，
    # 被 .github/actions/retry 读成「面板接口挂了」。needle 带下标，定位到具体那一个元素。
    ({"checks": [{"path": "/", "expect_contains": ["ok", 200]}]}, "expect_contains[1]", "string"),
    ({"checks": [{"path": "/", "expect_contains": [{"k": "v"}]}]}, "expect_contains[0]", "string"),
    ({"checks": [{"path": "/", "expect_contains": [None]}]}, "expect_contains[0]", "string"),
    ({"checks": [{"path": "/"}], "base_url": 8000}, "base_url", "string"),
    # expected_status 标量畸形同样必须前置挡住——run_check 里
    # `300 <= expected_status < 400` 的重定向开关判定在 try 之外，字符串/ null 会以 TypeError
    # 穿透 main() 的 except (OSError, ValueError) → rc=1 崩溃栈，与上面 expect_contains 元素检同族。
    # bool 显式单列一条：bool 是 int 子类，isinstance(value, (int, float)) 会放行 true/false。
    ({"checks": [{"path": "/", "expected_status": "200"}]}, "expected_status", "number"),
    ({"checks": [{"path": "/", "expected_status": None}]}, "expected_status", "number"),
    ({"checks": [{"path": "/", "expected_status": True}]}, "expected_status", "number"),
]


def _write_cfg(tmp_path: Path, payload: object, name: str = "cfg.json") -> Path:
    cfg = tmp_path / name
    _ = cfg.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return cfg


def _call_main(monkeypatch: pytest.MonkeyPatch, cfg_path: Path, extra: tuple[str, ...] = ()) -> int:
    # 进程内驱动 main()：退出码就是 SystemExit.code，与真实子进程一致（main 只做 argparse +
    # sys.exit，无 atexit/日志归档等旁路）。真实 rc 另由 test_malformed_real_process_rc 兜一次。
    monkeypatch.setattr(sys, "argv", ["smoke_test.py", "--config", str(cfg_path), *extra])
    with pytest.raises(SystemExit) as excinfo:
        smoke_test.main()
    code = excinfo.value.code
    assert isinstance(code, int), f"main() 应以整数码退出，实际 {code!r}"
    return code


class _FakeResponse:
    # urlopen 返回值的最小形态：run_check 只用 __enter__ / status / read。
    def __init__(self, status: int, body: str) -> None:
        self._status = status
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    @property
    def status(self) -> int:
        return self._status

    def read(self, size: int = -1) -> bytes:
        # size 形参对齐真实 http.client.HTTPResponse.read(amt)：run_check 现按 _SMOKE_BODY_LIMIT
        # 传 size 上限，替身不忠实会在合法路径抛 TypeError。
        body = self._body.encode("utf-8")
        return body if size < 0 else body[:size]


def _install_fake_urlopen(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse) -> list[str]:
    # 同样走「替换被测模块全局引用」的路子：urllib.request 是 stdlib 本体，就地打桩会波及
    # 同进程其它用例；这里把 smoke_test 模块里的 urllib 引用换成浅 namespace，只改 urlopen 一支。
    seen: list[str] = []

    def fake_urlopen(req: Any, timeout: object = None) -> _FakeResponse:
        seen.append(str(getattr(req, "full_url", req)))
        return response

    request_shim = types.SimpleNamespace(**vars(smoke_test.urllib.request))
    request_shim.urlopen = fake_urlopen
    urllib_shim = types.SimpleNamespace(request=request_shim, error=smoke_test.urllib.error)
    monkeypatch.setattr(smoke_test, "urllib", urllib_shim)
    return seen


def _spawn_smoke_child(cfg_path: Path) -> subprocess.CompletedProcess[bytes] | None:
    # 真起子进程拿真实退出码（错误处理契约的最终裁判）。返回 None = 本机起不了子进程。
    # 只对「spawn 本身失败」重试：中文 Windows 的本机 harness 在多 agent 并发时偶发
    # `OSError: [WinError 6] 句柄无效`（子进程句柄复制被拦；实测 2026-09-29 单跑连过 6 次、
    # 并发窗口内 3 次重试全被拦），属 AGENTS.md「本机偶发环境噪声」，与退出码判定无关。
    # **断言永不参与重试**：一旦拿到 CompletedProcess，rc/输出不合规就是红。
    # 「起不来」刻意用 Optional 返回值交调用方 skip，而不是在辅助函数里直接 pytest.skip：
    # 按 AGENTS.md 口径辅助函数的终态不依赖 pytest 的 NoReturn 可见性（CI typecheck job
    # 装不装 pytest 结论都该一致），可省形态也免掉「不可达语句」那类二次告警。
    # 走 skip 的边界（不是放宽门禁）：
    #   · 被跳过的只有「进程边界」这一层；rc=2 + 无崩溃栈的判定在进程内由
    #     test_main_exits_two_without_traceback 全量覆盖（SystemExit.code 即退出码），
    #     故本机跳这条不会让任何一条畸形形态失去用例。
    #   · CI（ubuntu runner）能稳定起子进程，本条在门禁面上恒为真实执行，不存在
    #     「靠 skip 让 CI 少跑一段平台分支」的那种静默失效（AGENTS.md 反对的是那一类）。
    #   · skip reason 会出现在 `-rs`/汇总里，本机不会形成「全绿但其实没跑」的错觉。
    # 具体异常类型（FileExistsError 之外的 OSError 家族，实测为 PermissionError 型拦截与
    # WinError 6）不进返回值：调用方只需区分「跑得起来 / 跑不起来」，判定与理由都在用例里写。
    for _attempt in range(3):
        try:
            return subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "smoke_test.py"), "-c", str(cfg_path)],
                capture_output=True,
            )
        except OSError:
            continue
    return None


class TestSmokeConfigMalformed:
    @pytest.mark.parametrize("payload,needle,shape", MALFORMED_CONFIGS)
    def test_load_config_raises_value_error_not_attribute_error(
        self, tmp_path: Path, payload: object, needle: str, shape: str
    ) -> None:
        # 契约核心：畸形必须走 ValueError（→ main 退 2），不得留 AttributeError/TypeError 给
        # run_check 崩栈（旧形态就是 rc=1 + 满屏 Traceback，被消费方读成「面板接口挂了」）。
        cfg = _write_cfg(tmp_path, payload)
        with pytest.raises(ValueError) as excinfo:
            smoke_test.load_config(str(cfg))
        msg = str(excinfo.value)
        assert needle in msg, f"报错未定位到畸形处 {needle}: {msg}"
        assert shape in msg, f"报错未给出期望形状 {shape}: {msg}"

    @pytest.mark.parametrize("payload,needle,shape", MALFORMED_CONFIGS)
    def test_main_exits_two_without_traceback(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any, tmp_path: Path, payload: object, needle: str, shape: str
    ) -> None:
        cfg = _write_cfg(tmp_path, payload)
        assert _call_main(monkeypatch, cfg) == 2
        captured = capsys.readouterr()
        assert "Traceback" not in captured.err, f"畸形配置不得逃逸崩溃栈: {captured.err}"
        assert "ERROR:" in captured.err
        assert needle in captured.err and shape in captured.err
        # 配置坏了就绝不该发出任何请求：stdout 里连冒烟报告的头都没有。
        assert "冒烟测试报告" not in captured.out

    def test_malformed_real_process_rc_is_two(self, tmp_path: Path) -> None:
        # 真实子进程口径复核（按字节比较，与码页/语言解耦，见 AGENTS.md「探测子进程输出一律
        # 按字节比较」）：rc=2、无 Traceback、stderr 指明期望形状。
        cfg = _write_cfg(tmp_path, {"checks": [{"path": "/", "headers": "Referer: https://x/"}]}, "hdr_str.json")
        proc = _spawn_smoke_child(cfg)
        if proc is None:
            # 边界与理由见 _spawn_smoke_child 注释：只有「本机 harness 起不了子进程」会走到这里，
            # 判定面本身由 test_main_exits_two_without_traceback 在进程内全量覆盖，CI 侧恒真跑。
            pytest.skip(
                "子进程三次重试都起不来（本机 harness 句柄拦截，属环境限制非被测面缺陷）；"
                "rc=2 与「无崩溃栈」由 test_main_exits_two_without_traceback 进程内覆盖"
            )
        assert proc.returncode == 2, f"headers 为字符串应退 2，实际 rc={proc.returncode} stderr={proc.stderr!r}"
        assert b"Traceback" not in proc.stderr
        assert b"ERROR:" in proc.stderr
        assert b"headers" in proc.stderr
        assert b"object" in proc.stderr

    def test_broken_config_emits_no_request_and_no_report(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # 半执行状态防线：第 1 条合法、第 2 条 headers 坏 → 整体拒绝，一条请求都不发。
        seen = _install_fake_urlopen(monkeypatch, _FakeResponse(200, "{}"))
        cfg = _write_cfg(
            tmp_path,
            {"base_url": "http://127.0.0.1:9", "checks": [{"path": "/ok"}, {"path": "/bad", "headers": "x: y"}]},
        )
        assert _call_main(monkeypatch, cfg) == 2
        assert seen == []

    def test_bad_element_in_expect_contains_exits_two_before_any_request(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # L-31 的进程边界形态：元素级畸形必须同样落 rc=2（配置问题），而不是 run_check 抛
        # TypeError 的 rc=1（接口问题）。这两档在 scripts/_ci_web_smoke.sh 里处置相反——
        # 前者直接停、后者还会退避重试，混同等于把「配置写坏了」重跑一遍。
        seen = _install_fake_urlopen(monkeypatch, _FakeResponse(200, "ok"))
        cfg = _write_cfg(
            tmp_path,
            {"base_url": "http://127.0.0.1:9", "checks": [{"path": "/", "expect_contains": ["ok", 200]}]},
        )
        assert _call_main(monkeypatch, cfg) == 2
        assert seen == [], "畸形元素仍发出了请求 = 半执行状态回来了"


class TestSmokeConfigValid:
    def test_valid_dict_config_exits_zero(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # 合法形态（headers object / expect_contains array / expect_json object）：
        # 原有判定路径不变 —— 断言执行且全通过 → rc 0。
        seen = _install_fake_urlopen(monkeypatch, _FakeResponse(200, '{"status": "ok"}'))
        cfg = _write_cfg(
            tmp_path,
            {
                "base_url": "http://127.0.0.1:9",
                "checks": [
                    {
                        "name": "健康检查",
                        "path": "/health",
                        "method": "GET",
                        "expected_status": 200,
                        "headers": {"Referer": "https://example.invalid/"},
                        "expect_contains": ["status"],
                        "expect_json": {"status": "ok"},
                    }
                ],
            },
        )
        assert _call_main(monkeypatch, cfg) == 0
        assert seen == ["http://127.0.0.1:9/health"]

    def test_valid_top_level_list_config_with_cli_base_url(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # 顶层直接是 array 的合法形态 + 命令行 --base-url：同样不回归（该形态无 base_url 位）。
        seen = _install_fake_urlopen(monkeypatch, _FakeResponse(204, ""))
        cfg = _write_cfg(tmp_path, [{"path": "/ping", "expected_status": 204, "headers": {}}])
        assert _call_main(monkeypatch, cfg, ("--base-url", "http://127.0.0.1:9")) == 0
        assert seen == ["http://127.0.0.1:9/ping"]

    def test_explicit_null_containers_are_legal(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # 显式 null 与「不写该键」等价（校验放行 null）。旧形态下 `"headers": null` 会让
        # `check.get("headers", {})` 返回 None 再 .items() 崩栈 —— 故 run_check 一并改成 `or {}`。
        _ = _install_fake_urlopen(monkeypatch, _FakeResponse(200, "hello"))
        cfg = _write_cfg(
            tmp_path,
            {"base_url": "http://127.0.0.1:9", "checks": [{"path": "/", "headers": None, "expect_contains": None}]},
        )
        assert _call_main(monkeypatch, cfg) == 0

    def test_interface_failure_stays_rc_one(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # 2 与 1 不得混同（文件头契约）：配置合法、接口状态码不符 → 仍 1。
        _ = _install_fake_urlopen(monkeypatch, _FakeResponse(503, "down"))
        cfg = _write_cfg(tmp_path, {"base_url": "http://127.0.0.1:9", "checks": [{"path": "/"}]})
        assert _call_main(monkeypatch, cfg) == 1

    def test_empty_and_missing_checks_keep_rc_two(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # MIN-2260 的既有语义必须原样保留：空 array 与缺 checks 键都退 2（本次收口不得挤掉）。
        empty = _write_cfg(tmp_path, {"checks": []}, "empty.json")
        assert _call_main(monkeypatch, empty) == 2
        missing = _write_cfg(tmp_path, {"base_url": "http://127.0.0.1:9"}, "missing.json")
        assert _call_main(monkeypatch, missing) == 2

    def test_shipped_smoke_web_config_still_loads(self) -> None:
        # 仓库自带的 CI 配置（scripts/smoke_web.json）是新校验的第一个消费者：必须仍能解析，
        # 且解析出 2 条断言（MIN-2260 的「0 条也算红」在消费侧还有第二道判据）。
        checks, base_url = smoke_test.load_config(str(ROOT / "scripts" / "smoke_web.json"))
        assert len(checks) == 2
        assert base_url == "http://127.0.0.1:8000"
