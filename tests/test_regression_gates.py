#
# 本文件只锁「本轮报告点名的那几种失效形态本身」，不复述被测实现的门禁语义——
# 复述型断言（「调用了 X」）在实现被改坏后照样能过，抓不住真失效。
#
import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────── ──────────────────────────────
# 形态：httpx 的 h2 / socksio 只在「运行期真正走到那条分支」时才被 import，
# 静态导入图与 pip 解析都不会报缺；于是清单里漏一条，用户 `pip install -r` 后仍然缺包。
# 这里的锁是**双侧包名集合一致**：单侧遗漏（本次形态）立即变红。


def _normalize_dist_name(name: str) -> str:
    # PyPI 规范化名（PEP 503）：小写 + 连续 [-_.] 折叠成单个 '-'。只比较**包名**、不管版本
    # 说明符，所以必须在剥离 '[...]'/版本之前就结束解析。
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


# PEP 508 名称后必须跟「说明符 / 空白 / 行尾 / 分号」；用前瞻卡住，避免把 `>=4.3.0` 吃进名字里
_REQ_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?=[\s\[<>=!~;,)]|$)")


def _names_from_requirements(text: str) -> set[str]:
    # 逐行解析 requirements.txt：剥行尾注释（本清单大量使用）→ 取行首包名。
    # `pkg[extra]>=x` 的 extra 段在取名字时天然被 `[` 的字符集排除，故无需特意处理。
    names: set[str] = set()
    for line in text.splitlines():
        spec = line.split("#", 1)[0].strip()
        if not spec:
            continue
        # `-r other.txt` / `--index-url ...` 之类的指令行没有包名，跳过
        if spec.startswith("-"):
            continue
        m = _REQ_NAME.match(spec)
        if m:
            names.add(_normalize_dist_name(m.group(1)))
    return names


def _names_from_pyproject_dependencies(text: str) -> set[str]:
    # 从 pyproject.toml 的 [project.dependencies] 取包名集合（用 tomllib 解析，非正则）。
    deps = tomllib.loads(text).get("project", {}).get("dependencies", [])
    names: set[str] = set()
    for dep in deps:
        m = _REQ_NAME.match(str(dep).strip())
        assert m is not None, f"[project.dependencies] 里有一条无法解析出包名：{dep!r}"
        names.add(_normalize_dist_name(m.group(1)))
    return names


def test_requirements_and_pyproject_dependency_name_sets_match() -> None:
    # 主锁：requirements.txt 与 pyproject [project.dependencies] 的包名集合必须相等。
    # 二者是「单源双写」（Docker/CI 消费前者，pip 安装消费后者），单侧增删即漂移。
    req_names = _names_from_requirements((ROOT / "requirements.txt").read_text(encoding="utf-8"))
    proj_names = _names_from_pyproject_dependencies((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    only_req = req_names - proj_names
    only_proj = proj_names - req_names
    assert not only_req, f"只在 requirements.txt 里、pyproject [project.dependencies] 缺失: {sorted(only_req)}"
    assert not only_proj, f"只在 pyproject [project.dependencies] 里、requirements.txt 缺失: {sorted(only_proj)}"


# 元数据生成物也会反向影响运行时：源码目录下的 egg-info 优先于 pyproject 回退，uv.lock 则是 README
# 推荐的 `uv sync` 输入。二者若不同步，版本展示与安装依赖会在同一工作区分叉。
def test_tracked_egg_info_matches_pyproject_metadata() -> None:
    pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = tomllib.loads(pyproject_text)["project"]
    pkg_info = (ROOT / "DouyinLiveRecorder.egg-info" / "PKG-INFO").read_text(encoding="utf-8")

    version = next(line.partition(":")[2].strip() for line in pkg_info.splitlines() if line.startswith("Version:"))
    runtime_specs = [
        line.partition(":")[2].strip()
        for line in pkg_info.splitlines()
        if line.startswith("Requires-Dist:") and "extra ==" not in line
    ]
    egg_names = {
        _normalize_dist_name(match.group(1)) for spec in runtime_specs if (match := _REQ_NAME.match(spec)) is not None
    }

    assert version == str(project["version"]), "egg-info 版本未随 pyproject.toml 重建"
    assert egg_names == _names_from_pyproject_dependencies(pyproject_text), "egg-info 运行时依赖集合已漂移"


def test_uv_lock_root_package_matches_pyproject_metadata() -> None:
    pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = tomllib.loads(pyproject_text)["project"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    roots = [
        package
        for package in lock.get("package", [])
        if package.get("name") == "douyinliverecorder" and package.get("source", {}).get("editable") == "."
    ]

    assert len(roots) == 1, f"uv.lock 应恰有一个本项目 editable 根包，实际 {len(roots)} 个"
    root_package = roots[0]
    lock_names = {_normalize_dist_name(str(item["name"])) for item in root_package.get("dependencies", [])}

    assert root_package.get("version") == project["version"], "uv.lock 根包版本未随 pyproject.toml 更新"
    assert lock_names == _names_from_pyproject_dependencies(pyproject_text), "uv.lock 根包运行时依赖集合已漂移"


def test_httpx_extra_runtime_requirements_are_declared() -> None:
    # 主锁：httpx 的 extra 只有运行期走到那条分支才 import，因此「清单里有没有声明」
    # 必须单独钉住。判据分两层：① 静态：h2 / socksio 在两侧都在；② 动态：向 httpx 自身追问它
    # 在这条配置下要不要这俩包——把「我记错了依赖名」这类文档性错误也一并抓住。
    httpx_reqs = _httpx_extra_requirements()

    req_names = _names_from_requirements((ROOT / "requirements.txt").read_text(encoding="utf-8"))
    proj_names = _names_from_pyproject_dependencies((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for pkg in ("h2", "socksio"):
        assert pkg in req_names, f"{pkg} 未在 requirements.txt 声明（httpx 运行期会 import 它）"
        assert pkg in proj_names, f"{pkg} 未在 pyproject [project.dependencies] 声明"

    # 本仓用 httpx[http2] 拿前者、显式声明后者；若 httpx 将来把二者并进默认依赖，下面的 extra
    # 名单会变，届时该断言即失效——这正是要人复核的信号，不是误报。
    extras_seen = {r.split("extra ==")[1].strip().strip("'\"") for r in httpx_reqs if "extra ==" in r}
    assert "http2" in extras_seen, f"httpx 元数据里已找不到 http2 extra（依赖形态可能已变）: {sorted(extras_seen)}"
    assert "socks" in extras_seen, f"httpx 元数据里已找不到 socks extra（依赖形态可能已变）: {sorted(extras_seen)}"


def test_httpx_runtime_import_sites_match_the_declared_extras() -> None:
    # **机理锁**：不猜「哪些包要声明」，而是回源到 httpx 源码，断言「本仓 declare 的
    # extra 名」与「httpx 真正 import 的依赖名」对齐。httpx 换实现（改名/换包）时这里会红，
    # 而纯静态的清单比对不会。
    import httpx

    httpx_pkg = Path(httpx.__file__).resolve().parent
    client_src = (httpx_pkg / "_client.py").read_text(encoding="utf-8")
    transport_src = (httpx_pkg / "_transports" / "default.py").read_text(encoding="utf-8")

    # http2=True 分支必须仍以 `import h2` 作为前置检查；socks5 分支必须仍 `import socksio`
    assert re.search(r"^\s*import h2\b", client_src, re.M), "httpx 不再在 http2 分支 import h2：请复核 h2 是否仍需声明"
    assert re.search(
        r"^\s*import socksio\b", transport_src, re.M
    ), "httpx 不再在 socks5 分支 import socksio：请复核 socksio 是否仍需声明"


def test_repo_has_enabled_http2_at_runtime() -> None:
    # 断言「http2 在本仓确实是运行期可达的配置」——否则 h2 的声明理由就站不住，
    # 该条注释就该被证伪而不是留着。判据：src/async_http.py 的 async_req 形参 http2 默认值为 True。
    source = (ROOT / "src" / "async_http.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    default: ast.expr | None = None
    for node in ast.walk(tree):
        # async_req 是协程函数 → AST 里是 AsyncFunctionDef（FunctionDef 抓不到，实测踩过）
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_req":
            # 形参可能带注解（ast.arg）也可能不带；用 args 列表按**位置**对齐尾部 defaults，
            # 故必须把 posonly + args 合并后再取尾部（只取 args 会在有 posonly 时整体错位）。
            positional = [*node.args.posonlyargs, *node.args.args]
            if not node.args.defaults:
                continue
            paired = list(zip(positional[-len(node.args.defaults) :], node.args.defaults))
            for arg, dflt in paired:
                if arg.arg == "http2":
                    default = dflt
    assert default is not None, "src/async_http.py 的 async_req 已无 http2 形参（SEV-2216 的注释理由需复核）"
    assert (
        isinstance(default, ast.Constant) and default.value is True
    ), "async_req 的 http2 默认值不再是 True：若 http2 已全程关闭，h2 的声明理由需重新论证"


def test_repo_supports_socks5_proxy_scheme() -> None:
    # 同理锁 socksio 的声明理由：本仓必须仍把 socks5/socks5h 当合法代理协议（白名单在
    # src/web_config.py）。若这条不成立，socksio 的注释即被证伪。
    source = (ROOT / "src" / "web_config.py").read_text(encoding="utf-8")
    assert re.search(
        r"_PROXY_SCHEMES\s*=\s*frozenset\(\([^)]*\"socks5\"", source, re.S
    ), "src/web_config.py 的 _PROXY_SCHEMES 已不含 socks5：请复核 socksio 是否仍需声明"


def _httpx_extra_requirements() -> list[str]:
    # 读当前解释器里 httpx 的 Requires-Dist（含 extra 标记），供上一条用例做形态核对。
    import importlib.metadata as md

    return list(md.requires("httpx") or [])


# ────────────────────────────── ──────────────────────────────
# 形态：tests/test_concurrency.py 用自己重写的一份 rate_limit 闭包做断言，从不调用 src 侧真正的
# _douyin_rate_limit —— 「限流被删掉」这类回归完全不会被发现。本锁直接驱动 src 实现。


def test_douyin_rate_limit_actually_sleeps_and_advances_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    # 直接驱动 src/stream_select._douyin_rate_limit：断言它真的 (a) 读 main.douyin_min_interval
    # (b) 间隔不足时 sleep 该差值 (c) 把 douyin_last_request_time 推进到当前时刻。
    # 换掉的是 **stream_select 模块自己的 time 引用**（浅拷贝 shim），不是 stdlib time 本体：
    # 改本体会全进程生效，波及 loguru enqueue 线程 / harness 守护线程 / coverage（R1 会红）。
    import types

    import main
    import src.stream_select as stream_select

    sleeps: list[float] = []
    fake_now = [1000.0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        fake_now[0] += seconds  # 让时间随 sleep 前进，模拟真实等待

    time_shim = types.SimpleNamespace(**vars(stream_select.time))
    time_shim.sleep = fake_sleep
    time_shim.time = lambda: fake_now[0]
    monkeypatch.setattr(stream_select, "time", time_shim)
    # 上一条请求发生在 1.0s 前、最小间隔 3.0s → 应补睡 2.0s；实现是「sleep 后重新 time.time()」，
    # 故时间戳推进到 1002.0（fake_sleep 已让 fake_now 随 sleep 前进，模拟真实时钟在等待期间流逝）。
    monkeypatch.setattr(main, "douyin_min_interval", 3.0, raising=False)
    monkeypatch.setattr(main, "douyin_last_request_time", 999.0, raising=False)

    stream_select._douyin_rate_limit()

    assert sleeps == [pytest.approx(2.0)], f"间隔不足时未按差值补睡（实际 sleeps={sleeps}）"
    assert main.douyin_last_request_time == pytest.approx(1002.0), "限流后未把 douyin_last_request_time 推进到当前时刻"


def test_douyin_rate_limit_does_not_sleep_when_interval_already_elapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    # 反向锁：间隔已满足时**不得**无谓 sleep——否则每个房间每轮都被拖慢一秒，
    # 是「限流过严」这一族回归（比漏限流更隐蔽，因为它不会报错，只会变慢）。
    # 同样只换 stream_select 自己的 time 引用（浅拷贝 shim），理由见上一条用例。
    import types

    import main
    import src.stream_select as stream_select

    sleeps: list[float] = []
    time_shim = types.SimpleNamespace(**vars(stream_select.time))
    time_shim.sleep = sleeps.append
    time_shim.time = lambda: 2000.0
    monkeypatch.setattr(stream_select, "time", time_shim)
    monkeypatch.setattr(main, "douyin_min_interval", 3.0, raising=False)
    monkeypatch.setattr(main, "douyin_last_request_time", 1990.0, raising=False)

    stream_select._douyin_rate_limit()

    assert sleeps == [], f"间隔已满足却仍 sleep：{sleeps}"
    assert main.douyin_last_request_time == pytest.approx(2000.0)


def test_concurrency_rate_limit_case_drives_src_not_a_local_copy() -> None:
    # 把 /**根因形态**固化成硬断言：tests/test_concurrency.py 里三个曾自建
    # 实现的类不得只靠自己重写的锁/限流/缓存闭包来「验证限流」——类体内必须出现对 src 真实入口
    # （下表符号任一）的引用，只允许打桩网络层与时间常量。
    #   [历史注] 2026-09-23 前本条写成 `if not drives_src: pytest.xfail(...)`：违例只软登记，
    #   修好后无人回来摘标记，此后改回自实现也会被悄悄放过；且判据只覆盖单个类。
    source = (ROOT / "tests" / "test_concurrency.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    wanted = {
        # 类名 -> 该类体内必须出现的**真实实现**符号（任一命中即算驱动了 src）
        "TestThreadSafeCredential": ("ttwid_module.get_ttwid", "src.ttwid"),
        "TestRateLimit": ("stream_select._douyin_rate_limit", "_douyin_rate_limit"),
        "TestCredentialSharing": ("cookie_cache.singleflight", "singleflight"),
    }
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in wanted:
            found.append(node.name)
            body_src = ast.get_source_segment(source, node) or ""
            assert any(symbol in body_src for symbol in wanted[node.name]), (
                f"tests/test_concurrency.py::{node.name} 又回到「测试内自建锁/限流/缓存」的假绿形态"
                f"（体内找不到 {wanted[node.name]} 任一符号）—— SEV-2222/SEV-2223"
            )
    assert set(found) == set(wanted), f"三个自建实现类被改名/删除，锁位需重定位（实际找到 {found}）"


# ────────────────────────────── ──────────────────────────────
# 形态：门禁步骤「只扫 stderr 不判 rc」/「退出码被丢弃」，于是子进程以非 0 退出但门禁仍判通过。


def test_run_gates_run_command_surfaces_nonzero_rc() -> None:
    # 直接调 scripts/run_gates.run_command，喂一条**必然失败**的命令，
    # 断言返回的 rc 就是子进程真实退出码（3），而不是被吞成 0。
    run_gates = _load_script_module("run_gates")
    rc, _dur, hits = run_gates.run_command(f'"{sys.executable}" -c "raise SystemExit(3)"')
    assert rc == 3, f"子进程退出码被丢弃：期望 3，实际 {rc}"
    assert hits == [], f"这条命令不该命中致命告警模式，实际 {hits}"


def test_run_gates_failed_command_is_reported_as_failure() -> None:
    # 上一条锁的是 run_command 的返回值；这条锁**收集判据**：
    # main() 用 `if rc == 0 and not hits:` 判通过，故 rc!=0 必须落到「失败」分支。
    # 直接复现该判据（而非跑整个 main()，那会连带跑全量门禁）。
    run_gates = _load_script_module("run_gates")
    rc, _dur, hits = run_gates.run_command('"{}" -c "raise SystemExit(3)"'.format(sys.executable))
    passed = rc == 0 and not hits
    assert not passed, "rc!=0 的步骤被判为通过：门禁丢失退出码（SEV-2223 的原始形态）"


def test_run_gates_keep_going_does_not_affect_exit_code_semantics() -> None:
    # --keep-going 只影响「是否继续跑后续步骤」，不得影响最终退出码：
    # 源码里失败必进 `failed` 列表、且主流程以 `return 1` 收口。锁住这条结构不变量。
    src = (ROOT / "scripts" / "run_gates.py").read_text(encoding="utf-8")
    assert "if not args.keep_going:" in src, "--keep-going 的收口点已改，需复核是否仍只控制「是否继续」"
    assert re.search(r"if failed:\s*\n\s*print", src), "失败集合未参与最终退出码判定"


def test_run_gates_comment_about_stdout_matches_implementation() -> None:
    # 定点锁：run_command 的注释曾声称「stdout 原样继承 / 逐行转发」，而实现是不接管
    # stdout（未传 stdout= ⇒ 子进程直接继承句柄），二者结论不同：只走 stdout 的失效信号是盲区。
    # 判据（可复核）：Popen 调用里不得出现 stdout= 关键字；刻意走 AST 而非子串——注释里也会出现
    # stdout=subprocess.PIPE 字样，纯子串匹配会把自己的说明当实现（首版即此坑）。
    src = (ROOT / "scripts" / "run_gates.py").read_text(encoding="utf-8")
    run_cmd_popen_kwargs = _popen_keywords(src, "run_command")
    assert "stdout" not in run_cmd_popen_kwargs, (
        f"run_command 现在接管了 stdout（kwargs={sorted(run_cmd_popen_kwargs)}）："
        "请同步改写其注释里「不接管 stdout、只扫 stderr」的结论"
    )
    # 反向：pytest 兜底那条**必须**接管 stdout（warnings summary 走 stdout，不接管就永远检不出）
    summary_kwargs = _popen_keywords(src, "gate_pytest_warnings_summary")
    assert (
        "stdout" in summary_kwargs
    ), "gate_pytest_warnings_summary 未接管 stdout：warnings summary 走 stdout，此回路会永久失明"


def _popen_keywords(source: str, function_name: str) -> set[str]:
    # 取 function_name 体内**所有子进程调用**（Popen 与 run 两种形态）的关键字参数名集合。只认
    # Popen 会让「必须接管 stdout」的反向见证凭空变红：pytest 兜底那步为避免管道死锁用的是
    # subprocess.run；run_command 仍只用 Popen，故「不接管 stdout」一侧的断言不受影响。
    #   [历史注] 2026-09-23 此前只扫 Popen(...) 一种形态。
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != function_name:
            continue
        kwargs: set[str] = set()
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            is_popen = (isinstance(func, ast.Attribute) and func.attr == "Popen") or (
                isinstance(func, ast.Name) and func.id == "Popen"
            )
            is_run = isinstance(func, ast.Attribute) and func.attr == "run" and isinstance(func.value, ast.Name)
            if is_popen or is_run:
                kwargs.update(kw.arg for kw in inner.keywords if kw.arg)
        return kwargs
    raise AssertionError(f"run_gates.py 里找不到函数 {function_name}()")


def test_run_gates_fatal_patterns_reach_stderr_channel() -> None:
    # 定点锁：FATAL_STDERR_PATTERNS 的**有效性**依赖「告警确实落在 stderr」。用一条真实的
    # isort 解析失败复现（非 UTF-8 字节混入源文件）：断言其 rc==0（只认退出码即假绿）**且**告警
    # 文本出现在 stderr（扫描回路有效）。若 isort 将来把告警改到 stdout，本用例会红。
    import tempfile

    run_gates = _load_script_module("run_gates")
    assert "Unable to parse file" in run_gates.FATAL_STDERR_PATTERNS, "致命告警清单已不含该形态"

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "bad_probe.py"
        # 合法的 py 头 + 两个非法 UTF-8 字节：要触发的必须是 isort 的**编码型**解析失败（只发
        # UserWarning、rc 仍为 0），不是语法错误——后者 rc 非 0，就证不出「只认退出码即假绿」。
        target.write_bytes(b"# coding: utf-8\n# " + bytes([0xFF, 0xFE]) + b" bad\nx = 1\n")
        proc = subprocess.run(
            [sys.executable, "-m", "isort", "--check-only", "--profile", "black", tmp],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    assert (
        proc.returncode == 0
    ), f"isort 解析失败的 rc 不再是 0（{proc.returncode}）：扫描回路的必要性变了，请复核本用例前提"
    assert "Unable to parse file" in (proc.stderr or ""), (
        f"告警不再出现在 stderr（可能在 stdout）：FATAL_STDERR_PATTERNS 的扫描通道会失明。"
        f"stdout={proc.stdout[:200]!r}"
    )


def test_run_gates_parses_all_gate_commands_and_env() -> None:
    # 门禁清单来源锁：AGENTS.md「格式化命令」章节必须仍能被解析出全部命令、
    # 且行首 `PYTHONUTF8=1` 前缀被正确解析为子进程环境变量（该语义载体）。
    # 这条同时防「章节标题被改 → 解析静默返空 → 门禁 rc=2 或跑空清单」的漂移。
    run_gates = _load_script_module("run_gates")
    agents = ROOT / "AGENTS.md"
    cmds = run_gates.extract_gate_commands(agents)
    assert cmds, "未能从 AGENTS.md 解析出任何门禁命令（章节标题/围栏可能已改）"
    # 本仓声明的全部门禁都应在清单内（抽查关键项，避免只断言「非空」）
    joined = "\n".join(cmds)
    for expected in ("black --check", "isort --check-only", "mypy", "check_annotations.py", "check_runtime_pins.py"):
        assert expected in joined, f"门禁清单缺少 {expected!r}（AGENTS.md 章节可能被改）"
    # 写型命令兜底拦截仍生效（清单里不得出现不带 --check 的 black/isort）
    assert not [c for c in cmds if run_gates.is_write_command(c)], "清单里出现了写型格式化命令"
    assert (
        run_gates.extract_gate_env(agents).get("PYTHONUTF8") == "1"
    ), "门禁块行首的 PYTHONUTF8=1 前缀未被解析出：isort 会在非 UTF-8 locale 下静默跳文件"


def _load_script_module(name: str) -> Any:
    # scripts/ 不在包路径内，按文件路径动态加载（与 check_runtime_pins._load_build_exe 同手法）。
    import importlib.util

    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_regression_probe_{name}", path)
    assert spec is not None and spec.loader is not None, f"无法加载 {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_build_exe() -> Any:
    # build_exe.py 在 import 期只做常量/函数定义（main() 受 __name__ 守卫），加载安全。
    import importlib.util

    path = ROOT / "build_exe.py"
    spec = importlib.util.spec_from_file_location("_regression_probe_build_exe", path)
    assert spec is not None and spec.loader is not None, f"无法加载 {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ────────────────────────────── ──────────────────────────────
# 形态：build_exe.py 的 copy_external_binaries 把 config/ **整目录复制**进发布目录，
# 而 make_zip 把发布目录整棵树压缩——含 Cookie / 代理账密 / Web 口令的 config.ini 与
# 含房间地址（可能内嵌 query token）的 URL_config.ini 随之对外分发。
# 这里锁两层：① 脱敏器本身（不产生凭据）② make_zip 前的校验（产生了就拦住）。


def _secret_bearing_pairs(text: str) -> list[tuple[str, str, str]]:
    # 取出 ini 文本里「非空且命中敏感判定」的 (节, 键, 值)，作为「必须被脱敏」的基准集合。
    # 入参是**文本**（不是 Path）：既有 _load_build_exe 那条链读的就是 read_text 结果，
    # 传路径会以 TypeError 炸在 read_string，而不是给出「有没有凭据」这个要断言的结论。
    import configparser

    from src import web_config

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[method-assign,assignment]
    parser.read_string(text)
    out: list[tuple[str, str, str]] = []
    for section in parser.sections():
        for key, value in parser.items(section):
            v = value.strip()
            if v and (web_config.is_sensitive_item(section, key) or web_config._looks_like_secret_value(v)):
                out.append((section, key, v))
    return out


def test_config_sanitizer_removes_every_sensitive_value() -> None:
    # 主锁（「不产生」一侧）：把**真实仓库 config.ini** 喂给脱敏器，断言所有「非空 +
    # 敏感」的键在产物里都变成空值，且节结构完整保留。用真实配置而非构造样本：缺陷本身就是
    # 「真实凭据被整目录复制」，只有真实样本才能证明脱敏对实际键名/节名成立。
    build_exe = _load_build_exe()
    src_ini = ROOT / "config" / "config.ini"
    if not src_ini.is_file():
        pytest.skip("本工作区无 config/config.ini（该文件是已跟踪的脱敏基线模板，本地被删/缺省时跳过真实样本校验）")

    source_text = src_ini.read_text(encoding="utf-8-sig", errors="replace")
    sanitized = build_exe._sanitized_config_text(source_text)

    baseline = _secret_bearing_pairs(source_text)
    assert baseline, "真实 config.ini 里应有敏感键（若为空说明判定口径被改窄，需复核）"

    import configparser

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[method-assign,assignment]
    parser.read_string(sanitized)
    survived = [
        (section, key)
        for section, key, _value in baseline
        if parser.get(section, key, fallback="<MISSING>").strip() != ""
    ]
    assert not survived, f"脱敏后仍有敏感键保留真实值: {survived}"

    # 结构完整性：节名不得因脱敏而丢失（否则产物不是可用模板）
    src_parser = configparser.ConfigParser(interpolation=None)
    src_parser.optionxform = str  # type: ignore[method-assign,assignment]
    src_parser.read_string(source_text)
    assert parser.sections() == src_parser.sections(), "脱敏改变了节结构，产物不再是可用模板"


def test_config_sanitizer_fails_closed_on_unparsable_input() -> None:
    # 反向锁：ini 解析失败时**不得**退回「原样返回」——那正是本次的失效形态。
    # 判据：损坏输入下产物必须不含原文里的凭据串。
    build_exe = _load_build_exe()
    broken = "[录制设置]\n代理地址 = socks5://user:LEAKME@127.0.0.1:1080\n[[[ 坏结构\n"
    out = build_exe._sanitized_config_text(broken)
    assert "LEAKME" not in out, "解析失败时退回了原样文本（fail-open），凭据会随 zip 外发"


def test_config_sanitizer_keeps_comments_and_structure() -> None:
    # M-06（2026-10-30）：函数头承诺「保留注释与节结构」必须有行为锁——旧 configparser 往返把
    # 注释全部丢弃（实测源 175 行/11 条注释 → 输出 164 行/0 条），发布 zip 里的模板成了无注释裸版。
    build_exe = _load_build_exe()
    source = (
        "# 顶部说明注释\n"
        "[录制设置]\n"
        "# 是否自动录制（中文键内嵌说明）\n"
        "自动录制 = true\n"
        "[账号密码]\n"
        "某平台密码 = SECRET_LEAK\n"
    )
    out = build_exe._sanitized_config_text(source)
    assert "# 顶部说明注释" in out, "顶部注释被丢弃（承诺与实现不符）"
    assert "# 是否自动录制（中文键内嵌说明）" in out, "节内注释被丢弃"
    assert "自动录制 = true" in out, "非敏感键的值不得被改动"
    assert "SECRET_LEAK" not in out, "敏感值必须被置空"
    assert "某平台密码 = " in out, "敏感键保留「键 = 」空值形态，模板仍可直接编辑"


def test_smoke_web_loopback_patch_covers_the_probe_window() -> None:
    # M-05（2026-10-30）结构锁：with _loopback_web_host() 的窗口必须包住探活循环与子进程终止点
    # （_finish 落在 with 块内）。旧实现只包 _launch——还原先于冻结子进程读配置（毫秒 vs 秒），
    # 补丁对子进程从未生效（模板恰为 127.0.0.1 使补丁字节恒等才未显形）；「子进程确实读到补丁值」
    # 的真机验证属打包链端到端（见 CODE_REVIEW_2026-10-30 M-05），不在本锁覆盖面内。
    import inspect

    build_exe = _load_build_exe()
    lines = inspect.getsource(build_exe.smoke_web).splitlines()
    with_idx = next(i for i, ln in enumerate(lines) if "with _loopback_web_host():" in ln)
    with_indent = len(lines[with_idx]) - len(lines[with_idx].lstrip())
    finish_inside = False
    for ln in lines[with_idx + 1 :]:
        if not ln.strip():
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent <= with_indent:
            break
        if "_finish(" in ln:
            finish_inside = True
            break
    assert finish_inside, "_finish 必须落在 with _loopback_web_host() 块内（配置还原不得早于子进程终止）"


def test_url_config_sanitizer_yields_comment_only_template() -> None:
    # URL_config.ini 一律重写为注释样例：不得出现任何未注释的有效房间行。
    build_exe = _load_build_exe()
    out = build_exe._sanitized_url_config_text()
    for line in out.splitlines():
        stripped = line.strip()
        assert not stripped or stripped.startswith("#"), f"样例里出现了有效行（应为纯注释）：{stripped!r}"


def test_make_zip_aborts_when_release_dir_contains_real_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 主锁（「产生了就拦住」一侧）：人为把一份**含真实凭据**的 config.ini 放进
    # 发布目录，断言 make_zip 之前的校验会非零退出（SystemExit），即 zip 不会被生成。
    # 这是对「校验存在但没接在 make_zip 上」这一形态的直接否定——只断言函数存在是不够的。
    build_exe = _load_build_exe()

    release = tmp_path / "DouyinLiveRecorder"
    (release / "config").mkdir(parents=True)
    # 构造一个必然命中敏感判定的值（代理地址带账密，本仓 _PROXY_ADDR_KEYS 明确管这类键）
    (release / "config" / "config.ini").write_text(
        "[录制设置]\n代理地址 = http://realuser:REALPASS@10.0.0.1:8080\n",
        encoding="utf-8",
    )
    (release / "config" / "URL_config.ini").write_text(
        "https://live.douyin.com/123456?token=REALTOKEN\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(build_exe, "RELEASE_DIR", release)
    # 让源 config.ini 也含同一凭据，以便走「逐键比对源值」那条判据
    src_dir = tmp_path / "src_config"
    src_dir.mkdir()
    (src_dir / "config.ini").write_text(
        "[录制设置]\n代理地址 = http://realuser:REALPASS@10.0.0.1:8080\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(build_exe, "PROJECT_ROOT", tmp_path)

    with pytest.raises(SystemExit):
        build_exe.assert_no_credentials_in_release()


def test_make_zip_calls_credential_assertion_before_archiving() -> None:
    # 结构锁：校验与封印的**先后关系**必须写在 make_zip 内（而非靠调用方自觉）——只断言「校验
    # 函数存在」会漏掉「make_zip 没调它」。函数体经 _function_body_source 用 AST 取源码段，
    # 不用字符串 index 找边界（体内嵌套 def 会把边界切错，实测踩过）。
    src = (ROOT / "build_exe.py").read_text(encoding="utf-8")
    body = _function_body_source(src, "make_zip")
    # 定位一律带括号（调用形态）：get_source_segment 是原文切片、**含函数体内的注释行**，只匹配
    # 裸函数名会先命中 build_exe.py 里的说明注释。
    # [历史注 2026-09-24] 压缩动作由 shutil.make_archive( 改为自建的 _zip_release_dir(（为指定
    # compresslevel=9），锚点同步改新接缝；锁的语义（凭据校验必须早于压缩）完全不变。
    assert "assert_no_credentials_in_release()" in body, "make_zip 未调用凭据校验"
    assert body.index("assert_no_credentials_in_release()") < body.index(
        "_zip_release_dir("
    ), "凭据校验晚于压缩：zip 已生成才拦，等于没拦"


def _function_body_source(source: str, name: str) -> str:
    # 返回名为 name 的顶层函数完整源码段（def 行到函数结束）。关键性质：ast.get_source_segment 做
    # 的是**原文切片**，体内 `#` 注释一并返回，故断言必须匹配可执行形态（调用带括号、参数带实参），
    # 否则注释文本就能喂饱断言，删掉调用点也不会变红。
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"build_exe.py 里找不到顶层函数 {name}()")


def test_copy_external_binaries_does_not_copytree_config() -> None:
    # 形态锁：copy_external_binaries 里不得再出现对 config/ 的 copytree
    # （整目录复制正是本次的根因；shutil.copytree 会把 config.ini 原样带过去）。
    src = (ROOT / "build_exe.py").read_text(encoding="utf-8")
    body = _function_body_source(src, "copy_external_binaries")
    assert "copytree(cfg_src" not in body, "config/ 仍在被整目录 copytree 复制（SEV-2213 复发）"


def test_no_credentials_in_release_passes_on_sanitized_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 正向对照：脱敏后的发布目录必须**通过**校验（否则校验会把正常构建也拦死）。
    build_exe = _load_build_exe()
    release = tmp_path / "DouyinLiveRecorder"
    (release / "config").mkdir(parents=True)
    (release / "config" / "config.ini").write_text("[录制设置]\n代理地址 = \n", encoding="utf-8")
    (release / "config" / "URL_config.ini").write_text("#https://live.douyin.com/000000000000\n", encoding="utf-8")
    monkeypatch.setattr(build_exe, "RELEASE_DIR", release)
    monkeypatch.setattr(build_exe, "PROJECT_ROOT", tmp_path / "nonexistent_root")

    build_exe.assert_no_credentials_in_release()  # 不抛异常即通过


def test_prepare_url_config_reentrant_with_sanitizer_output() -> None:
    # 兼容性锁：_prepare_url_config() 与 _prepare_config_dir() 必须**同源且可重入**——二者都会写
    # config/URL_config.ini，样例串不一致时后跑的那个会覆盖前者（冒烟路径与打包路径各调一次）。
    build_exe = _load_build_exe()
    assert (
        build_exe._sanitized_url_config_text() == "#https://live.douyin.com/000000000000\n"
    ), "URL_config.ini 的样例串与 _prepare_url_config 不一致（两处会互相覆盖）"


def test_three_exe_names_share_one_source() -> None:
    # 定点锁：三个 exe（CLI / GUI / Web）的名字必须同源于 APP_NAME——分别写死会在改名时
    # 漏改一个（产物半新半旧且不易察觉）。
    build_exe = _load_build_exe()
    template = build_exe.SPEC_TEMPLATE
    suffixes = re.findall(r"name='\{app\}([^']*)'", template)
    assert sorted(suffixes) == sorted(
        ["", "-GUI", "-Web", ""]
    ), f"exe 名称不再全部由 {{app}} 派生（实际后缀 {suffixes}）：改名时会漂移"


def test_smoke_fatal_markers_cover_import_failures() -> None:
    # 定点锁：--smoke 的 FATAL_MARKERS 必须覆盖「导入失败」这一类——
    # 缺 h2/socksio在冻结产物里正是以 ModuleNotFoundError 形态出现。
    build_exe = _load_build_exe()
    for marker in ("Traceback (most recent call last)", "ModuleNotFoundError", "ImportError"):
        assert marker in build_exe.FATAL_MARKERS, f"冒烟致命标记缺少 {marker!r}"


def test_version_is_read_from_single_source() -> None:
    # 定点锁：版本号必须只经 read_version() 从 pyproject.toml 读一次，
    # 且三个 exe 共享同一个 zip 前缀（避免某入口单独写死版本）。
    src = (ROOT / "build_exe.py").read_text(encoding="utf-8")
    assert src.count("read_version()") >= 1, "read_version() 不再被调用"
    body = _function_body_source(src, "read_version")
    assert "pyproject.toml" in body, "read_version 不再从 pyproject.toml 读取（事实源被改）"
