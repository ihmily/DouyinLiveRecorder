# -*- coding: utf-8 -*-
# pyrightconfig.json 与 pyproject 的类型检查口径同源锁。
#
# 为什么需要它：本仓的类型门禁是「CI 跑 mypy（Linux）+ 本地跑 basedpyright」，而 IDE 里的红线来自
# Pylance —— 它没有命令行入口，也没有可核对的配置面，于是「IDE 里看着没问题」长期是一句无法复核的话
# （AGENTS.md 因此明文禁止把 Pylance 当门禁证据）。补一份 pyrightconfig.json 之后，IDE 语言服务器与
# `pyright` CLI 读同一份 include / exclude / typeCheckingMode：IDE 的结论可以用 CLI 逐条复现，
# 「不可验证的 IDE 判断」这件事从口径上被消掉，而不是靠自觉。
#
# 本文件只锁「同源」，不锁「pyright 必须零错误」——后者是本地补充检查的结论，随代码状态变化；
# 让它进 CI 反而会开出第三条互相矛盾的类型门禁（mypy 才是 CI 裁决者）。

import tomllib
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "pyrightconfig.json"


def _json() -> dict[str, Any]:
    # 本文件是 JSONC（pyright 官方支持带注释的 pyrightconfig.json）：注释只允许整行 `//`，
    # 校验前先按行剥掉——顺带把「有人把说明写成顶层键」这种形态排除在外（pyright 会报
    # "Config contains unrecognized setting"，实测如此，故说明一律留在行注释里）
    import json
    import re

    raw = CONFIG.read_bytes().decode("utf-8")
    return cast(dict[str, Any], json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M)))


def _pyproject() -> dict[str, Any]:
    return cast(dict[str, Any], tomllib.loads((ROOT / "pyproject.toml").read_bytes().decode("utf-8")))


def _dir_names(entries: list[str], *, regex_style: bool) -> set[str]:
    # 归一各工具自己的写法后再比对，否则「**/downloads」与「*/downloads/*」会被判成两份清单：
    # 必须先剥 `**/` 再剥 `*/`（先剥后者会把 `**/downloads` 切成 `*downloads`，制造假差异）。
    # 末尾通配符一并去掉：mypy 的 exclude 是正则（`pytest-cache-files-` 前缀即全义），
    # basedpyright / pyright 的是 glob（写 `**/pytest-cache-files-*`），留着 `*` 会判成两个名字。
    out: set[str] = set()
    for raw in entries:
        item = raw.strip().strip('"')
        if not item:
            continue
        if regex_style:
            item = item.replace("(^|/)", "").replace("\\.", ".").rstrip("/")
        item = item.removeprefix("**/").removeprefix("*/").removesuffix("/*").rstrip("/")
        out.add(item.rstrip("*"))
    return {o for o in out if o}


def test_pyright_config_exists_and_declares_the_gate_surface() -> None:
    cfg = _json()
    assert cfg.get("include"), "pyrightconfig.json 必须有 include，否则 IDE 与 CLI 各自按默认范围扫"
    # 反向见证：include 必须真的覆盖三个根入口，只断言「非空」会让「只剩 src」的改动混过去
    for entry in ("main.py", "gui.py", "web.py"):
        assert entry in cfg["include"], f"include 缺根入口 {entry}：IDE 与 CLI 的扫描面会再度分叉"


def test_include_matches_mypy_files_exactly() -> None:
    # include == [tool.mypy].files：三者（CI mypy / 本地 mypy / IDE+pyright）扫同一批文件，
    # 才是「IDE 结论可复核」的成立前提
    cfg = _json()
    files = _pyproject()["tool"]["mypy"]["files"]
    assert sorted(cfg["include"]) == sorted(files), (
        f"pyrightconfig include 与 [tool.mypy].files 不一致：\n"
        f"  仅 pyright 有：{sorted(set(cfg['include']) - set(files))}\n"
        f"  仅 mypy 有：  {sorted(set(files) - set(cfg['include']))}"
    )


def test_strictness_and_interpreter_match_basedpyright() -> None:
    cfg = _json()
    bp = _pyproject()["tool"]["basedpyright"]
    assert (
        cfg.get("typeCheckingMode") == bp["typeCheckingMode"]
    ), "严格度与 basedpyright 不一致：IDE 红线与本地门禁不同尺度"
    assert cfg.get("pythonVersion") == bp["pythonVersion"], "pythonVersion 与 basedpyright 不一致"
    assert cfg.get("venvPath") == bp["venvPath"] and cfg.get("venv") == bp["venv"], "venv 指向与 basedpyright 不一致"


def test_exclude_covers_both_tool_exclude_lists() -> None:
    # exclude 必须同时盖住 [tool.mypy].exclude 与 [tool.basedpyright].exclude 的目录名：
    # 少一个名字，IDE/pyright 就会去扫 mypy 与 basedpyright 都排除的东西（典型是运行期产物与工具目录）
    cfg = _json()
    pyproject = _pyproject()["tool"]
    right = _dir_names(list(cfg.get("exclude", [])), regex_style=False)
    for name, entries in (
        ("[tool.mypy].exclude", list(pyproject["mypy"]["exclude"])),
        ("[tool.basedpyright].exclude", list(pyproject["basedpyright"]["exclude"])),
    ):
        missing = sorted(_dir_names(entries, regex_style=True) - right - {"node_modules"})
        assert not missing, f"pyrightconfig exclude 未覆盖 {name} 的条目：{missing}"


def test_pylance_is_not_claimed_as_gate_evidence() -> None:
    # 元守卫：本仓的门禁裁决者是 mypy（CI）+ basedpyright（本地）。这条断言把「pyrightconfig 存在」
    # 与「它不取代 CI 结论」绑在一起——若有人把 pyright 加进 ci.yml 当第三道类型门禁，这里不会红，
    # 但 AGENTS.md 与 CI 的口径分叉会由 tests/test_run_gates.py 一侧暴露；本用例只保证配置文件
    # 不夹带「CI 用 pyright」的暗示（例如被误改成 requireConfiguration 阻断本地跑）
    cfg = _json()
    assert cfg.get("typeCheckingMode") != "off", "typeCheckingMode=off 会让这份配置变成纯装饰"
    assert (
        "strict" not in str(cfg.get("typeCheckingMode", "")).lower()
    ), "strict 会把 IDE 变成第三条门禁（mypy/basedpyright 都不按它判），制造无法自证的红色波浪线"
