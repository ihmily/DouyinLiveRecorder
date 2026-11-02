# -*- coding: utf-8 -*-
# 镜像侧 GUI 依赖开关（Dockerfile 的 INSTALL_GUI + compose 各服务的 build 配置）的结构锁。
#
# 背景：GUI 窗口层迁到 PySide6 后它进入运行时清单，镜像的 `pip install -r requirements.txt` 于是把
# 它一并装入（本机实测解压后 647.56MB），而镜像按设计只跑 recorder（main.py）与 web（web.py），
# 实测两者在屏蔽 PySide6 后导入链完整；slim-bookworm 运行阶段又缺 QtWidgets 的链接依赖
# （libEGL/libGL/glib/fontconfig/xkbcommon…），默认装入只会翻倍体积却仍起不动窗口。因此引入
# INSTALL_GUI（默认 false = 镜像侧过滤 GUI 依赖），compose 的 gui 服务显式开 true 并另用 tag。
#
# 四条不变量（全部静态、零 Docker 依赖，本机与 Linux CI 同一结论）：
#   ① 每个引用 $INSTALL_GUI 的阶段都必须先声明后使用（ARG 不跨阶段，与 MIN-14 同族判据）；
#   ② 默认值必须是 false，且过滤只发生在镜像侧——requirements.txt 与 pyproject 里 PySide6 必须仍在
#     （清单 ↔ pyproject 的集合相等锁由 tests/test_regression_gates.py 把守）；
#   ③ compose 的 gui 服务必须开 INSTALL_GUI=true 且与 recorder/web 用不同 tag（build 配置不同的
#     服务共用 image 名时，后构建的一方会覆盖另一方正在使用的 tag）；
#   ④ 镜像发布工作流不得传 INSTALL_GUI=true：对外发布的镜像必须是 slim 默认形态。
#
# 变异验证锚点：删掉 gui 的 INSTALL_GUI 或把 tag 改回与 recorder 同名 → ③ 红；把阶段2 的 ARG
# 声明挪到使用点之后 → ① 红；把默认值改成 true → ② 红；给 docker-publish.yml 加开关 → ④ 红。

import re
import tomllib
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "docker-compose.yaml"
REQUIREMENTS = ROOT / "requirements.txt"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "docker-publish.yml"
PYPROJECT = ROOT / "pyproject.toml"

# 阶段1 过滤 GUI 依赖的合法形态：用 grep -viE 按行首包名剔除、落到临时清单再交给 pip。
# 判据写成容错的宽式（钉「grep -viE + pyside6 + 输入 requirements.txt + 输出 *.nogui.txt」四要素），
# 不钉具体空白与字符类写法：那行在 Dockerfile 里带行尾续行反斜杠，严格式实测匹配不到（假红）。
GUI_FILTER = re.compile(r"grep -viE[^>]*pyside6[^>]*requirements\.txt\s*>\s*\S*requirements\.nogui\.txt")
# GUI 专用依赖（镜像侧被过滤的那一类）：本锁只认包名，不重复钉版本下限（下限事实源在 pyproject）
GUI_ONLY_PACKAGES = ("pyside6",)


def _text(path: Path) -> str:
    # 按原字节解码：本仓文本文件行尾混存（CRLF / LF），不能让行尾形态参与判定
    return path.read_bytes().decode("utf-8")


def _stages(dockerfile_text: str) -> list[list[str]]:
    # 按 FROM 切分构建阶段：Docker 的 ARG 作用域按阶段隔离，判「声明早于使用」必须同粒度。
    # 首个 FROM 之前的内容单独成桶并被丢弃——若把它算成「阶段1」，诊断信息里的阶段号就比
    # Dockerfile 自己的「阶段1/阶段2」注释错一位（实测报成「阶段3」），误导性提示比没有提示更糟。
    buckets: list[list[str]] = [[]]
    for line in dockerfile_text.splitlines():
        if line.startswith("FROM "):
            buckets.append([line])
        else:
            buckets[-1].append(line)
    return [b for b in buckets if any(not ln.lstrip().startswith("#") and ln.strip() for ln in b)]


def _gui_arg_order_violations(dockerfile_text: str) -> list[str]:
    # ① 的判据本体（全文件用例与判据自检共用，避免两处各写一份遍历而漂移）。
    # 「使用」只认引用了变量的指令行（`$INSTALL_GUI`）：ARG 上方的说明注释与 echo 文案里也出现
    # INSTALL_GUI 字样，按「包含即算」判会把这些注释当成使用点、反过来咬声明一处（实测假红）。
    violations: list[str] = []
    declared = 0
    for index, lines in enumerate(_stages(dockerfile_text), start=1):
        use_at = next(
            (i for i, ln in enumerate(lines) if "$INSTALL_GUI" in ln and not ln.lstrip().startswith("#")),
            None,
        )
        decl_at = next((i for i, ln in enumerate(lines) if ln.strip().startswith("ARG INSTALL_GUI")), None)
        if use_at is None:
            continue
        if decl_at is None:
            violations.append(f"阶段{index} 引用了 $INSTALL_GUI 却没在本阶段声明 ARG INSTALL_GUI")
            continue
        if decl_at > use_at:
            violations.append(f"阶段{index} 的 ARG 声明（段内第 {decl_at} 行）晚于使用点（段内第 {use_at} 行）")
        declared += 1
    if declared < 2:
        violations.append(
            f"应至少有「阶段1 过滤 GUI 依赖 + 阶段2 按需装 Qt 库」两处声明并使用 INSTALL_GUI，实测 {declared} 处"
        )
    return violations


def test_gui_arg_is_declared_before_use_in_every_stage() -> None:
    violations = _gui_arg_order_violations(_text(DOCKERFILE))
    assert not violations, "Dockerfile 的 INSTALL_GUI 声明/使用顺序有问题：" + "；".join(violations)


def test_gui_arg_order_predicate_really_bites() -> None:
    # 判据自检：必须真能抓到「使用先于声明」与「整段没声明」两种破坏形态，否则上一条只是在
    # 复述一个恒真表达式（AGENTS.md「测试不得自实现被测逻辑 / 假绿」同源）
    good = (
        'FROM a\nARG INSTALL_GUI=false\nRUN if [ "$INSTALL_GUI" = "true" ]; then :; fi\n'
        "FROM b\nARG INSTALL_GUI=false\nRUN echo $INSTALL_GUI\n"
    )
    assert _gui_arg_order_violations(good) == [], "自检误伤：合法形态被判违规"
    late = (
        "FROM a\nRUN echo $INSTALL_GUI\nARG INSTALL_GUI=false\n"
        "FROM b\nARG INSTALL_GUI=false\nRUN echo $INSTALL_GUI\n"
    )
    assert _gui_arg_order_violations(late), "自检漏抓：ARG 声明晚于使用点必须违规"
    missing = "FROM a\nRUN echo $INSTALL_GUI\nFROM b\nRUN echo $INSTALL_GUI\n"
    assert _gui_arg_order_violations(missing), "自检漏抓：阶段内未声明 ARG 必须违规"


def _manifest_names(text: str) -> set[str]:
    # requirements.txt 的行内注释紧贴版本号且不带空格（如 brotli>=1.2.0#b站弹幕解压），
    # 整行比对会全量误报——剥注释后再取行首包名（与 AGENTS.md「依赖对账」口径一致）
    out: set[str] = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        out.add(re.split(r"[<>=!~;\[]", line)[0].strip().lower().replace("_", "-"))
    return out


def test_image_build_defaults_to_slim_but_manifests_keep_gui_package() -> None:
    # ② 默认 slim + 过滤只在镜像侧
    text = _text(DOCKERFILE)
    decls = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("ARG INSTALL_GUI")]
    assert decls, "Dockerfile 里找不到 ARG INSTALL_GUI 声明"
    wrong_default = [d for d in decls if d != "ARG INSTALL_GUI=false"]
    assert not wrong_default, f"INSTALL_GUI 默认值必须是 false（对外发布的镜像默认 slim），实测 {wrong_default}"
    assert GUI_FILTER.search(text), "阶段1 必须用「行首包名剔除 + 临时清单」的形态过滤，不得改成手写包名白名单"
    assert 'INSTALL_GUI" = "true' in text, "必须保留 INSTALL_GUI=true 分支（compose 的 gui 服务依赖它）"

    req_names = _manifest_names(_text(REQUIREMENTS))
    proj = tomllib.loads(PYPROJECT.read_bytes().decode("utf-8"))
    proj_names = {
        re.split(r"[<>=!~;\[]", str(d))[0].strip().lower().replace("_", "-") for d in proj["project"]["dependencies"]
    }
    for pkg in GUI_ONLY_PACKAGES:
        assert pkg in req_names, f"{pkg} 被从 requirements.txt 删掉了：过滤只能发生在镜像侧，清单不得动"
        assert pkg in proj_names, f"{pkg} 被从 pyproject [project.dependencies] 删掉了：运行时清单的事实源"


def test_compose_gui_service_opts_in_with_its_own_tag() -> None:
    # ③ gui 服务：开开关 + 独立 tag；recorder/web 保持默认 slim
    services = cast(dict[str, Any], yaml.safe_load(COMPOSE.read_bytes().decode("utf-8-sig"))["services"])
    base_image = str(services["recorder"].get("image", ""))
    for name in ("recorder", "web"):
        args = cast(dict[str, Any], (services[name].get("build") or {}).get("args") or {})
        assert "INSTALL_GUI" not in args, f"{name} 服务不该设 INSTALL_GUI（默认 slim 才是镜像的发布形态）"
    gui = services["gui"]
    gui_args = cast(dict[str, Any], (gui.get("build") or {}).get("args") or {})
    assert str(gui_args.get("INSTALL_GUI")) == "true", "gui 服务必须显式传 INSTALL_GUI=true，否则容器里没有窗口层"
    assert (
        str(gui.get("image", "")) != base_image
    ), "gui 服务与 recorder 共用同一 image 名时，后构建的一方会覆盖另一方正在用的 tag（不同 build 配置必须不同 tag）"


def test_published_image_workflow_stays_slim() -> None:
    # ④ 发布链不得把 GUI 依赖带进对外镜像
    text = _text(PUBLISH_WORKFLOW)
    hits = [ln.strip() for ln in text.splitlines() if "INSTALL_GUI" in ln and "true" in ln.lower()]
    assert not hits, "docker-publish.yml 不得传 INSTALL_GUI=true（对外发布的镜像必须是 slim）：" + "；".join(hits)
