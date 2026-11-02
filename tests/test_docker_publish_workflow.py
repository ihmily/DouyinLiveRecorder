# .github/workflows/docker-publish.yml 的结构锁（GHCR 多架构发布链）。
#
# 为什么要有：多架构发布链的正确性全靠几个「看起来像细节」的约束——只在 tag 上推 latest、两个
# 构建 job 的 runner 与 --platform 一一对应、凭据只能是自动 GITHUB_TOKEN、分架构 digest 必须提升
# 为 job 级 output——而工作流文件不在任何门禁的判据面里：改坏它不会有测试红，只会在下一次发版时
# 炸成「build 全绿、清单合成报无效引用」这种最难归因的形态。规格依据：
# docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md §五.1、测试面 T-8。
#
# 纯静态结构锁而非行为锁：本机既无 docker 也无推送权限，端到端只能在 CI 首跑时验证，故判据全取
# 「谁被调用、带不带凭据、引用了哪个 output」这类不变量，不钉行号也不钉排版。
#
# YAML 1.1 陷阱：`on:` 会被 PyYAML 解析成布尔 True 键（on/off/yes/no 都是布尔字面量），取值一律
# 经 _triggers()；它对「两种键形态都找不到」显式失败——「触发面读空」在本锁里不是绿灯。
#
# 变异取证（2026-10-03 实跑，按「临时改写 → 跑 → 还原」执行，仓库零残留）：加 workflow_dispatch
# → only_tag_push_can_publish_latest 红；arm64 的 runs-on 改成 ubuntu-latest →
# arch_jobs_run_on_matching_native_runners 红；删掉 outputs.digest → 同一条红；删 provenance: false
# → provenance_disabled 红；merge 改按分架构 tag 引用 → digest_refs 红；amd64 的 tags 追加 :latest
# → temp_only 红；runs-on 换成清单外标签 ubuntu-24.04-arm64 → matching_native_runners 红（单侧改时
# 两处断言同时落）；两侧同改（workflow 与本表的 ARCH_JOBS 一起换成同一支未登记标签）则只红在
# 「未登记」那条断言——这一格才证明 I-2 的断言不是 runs-on == runner 的冗余重复。

from __future__ import annotations

import importlib.util
import re
import shlex
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "docker-publish.yml"

# 「这个 job 必须跑在哪个 runner 上、产出哪个平台」的对应表。判据取原生 runner 而不是
# 「platforms 里出现两个平台」：build-release.yml 的发布矩阵已用 ubuntu-24.04-arm（并由
# scripts/check_runtime_pins.py 的 RUNNER_TO_RUNTIME_KEY 登记为 linux-arm64），本表与之同口径。
# [评审 I-2 补的机检] 上面那句「同口径」此前只是评论：本表把标签又硬编了一份，而唯一登记点
# RUNNER_TO_RUNTIME_KEY 从不与本工作流比对——「workflow 换标签 + 本表跟着改」两侧同改仍全绿，
# 而新标签从未登记。同源断言落在 test_arch_jobs_run_on_matching_native_runners，登记表按文件
# 路径动态加载、不在本文件复述标签清单（复述即第二份事实源）。
ARCH_JOBS: dict[str, tuple[str, str]] = {
    "docker-build-amd64": ("ubuntu-latest", "linux/amd64"),
    "docker-build-arm64": ("ubuntu-24.04-arm", "linux/arm64"),
}

# 会推镜像的三个 job：顶层 permissions 只给 contents: read，packages: write 必须逐 job 按需授予。
PUSH_JOBS = ("docker-build-amd64", "docker-build-arm64", "docker-manifest")

# build-push-action 的 steps.<id>：merge job 靠它取 digest，任一处改名会让 needs.*.outputs.digest
# 静默变空串（构建本身全绿，只有合成步骤红，是最难归因的一种失败）。
BUILD_STEP_ID = "build"

# 安装链锚点：依赖安装只允许发生在 Dockerfile 的镜像层里。
INSTALL_ANCHORS = ("apt-get install", "pip install", "choco install", "brew install")

# —— 评审 I-1/I-2/I-3 三条补锁的判据常量 ——
# 共同取舍：判定先落到「解析后的结构」（YAML 取值 + shell 词法单元），再对结构断言；拿整段 run
# 原文写正则等于把排版当契约（M-26 的教训：契约一反转这种锁就静默空洞成立）。另有三处刻意的
# 唯一形态约束（①with.tags 只认标量串 ②provenance 只认布尔 False ③实参解析只认 `-t/--tag <值>`），
# 红点各自写在对应锁的上方并标了序号：放宽它们要在 shell 词法之外再引入「选项语义」解析（哪个
# 选项带值、列表与标量同义、布尔与字符串在 action 入参处同形），复杂度与收益不匹配——本链唯一
# 对外产物是 latest 清单，宁可让改写者显式适配这三种形态。三处的红是误报方向（改写者被迫改锁），
# 不是假绿方向。
LATEST_TAG = ":latest"

# 分架构 job ↔ 临时 tag 应有的架构后缀。与 ARCH_JOBS 同源但判据不同：那张管 runner↔platform
# 的对应，这张管「临时 tag 必须且只带自己那一份后缀」（缺后缀即两个架构写同一个 tag）。
ARCH_TAG_SUFFIX: dict[str, str] = {
    "docker-build-amd64": "amd64",
    "docker-build-arm64": "arm64",
}

# `@` 右边的形态：允许表达式花括号内的空格差异（`${{x}}` 与 `${{ x }}` 语义相同），
# 钉的是「引用了哪个 job 的哪个 output」，不是钉缩进与空格。
DIGEST_REF = re.compile(r"^\$\{\{\s*needs\.docker-build-(?P<arch>amd64|arm64)\.outputs\.digest\s*\}\}$")

# 输入项里带这个后缀 = 清单改成按分架构临时 tag（可变、可被后续推送覆盖）引用。
ARCH_TAG_SUFFIX_RE = re.compile(r"-(?:amd64|arm64)$")

# 合成命令的词法锚点：这四个 token 连续出现处之后的才是「实参」。
CREATE_ANCHOR = ("docker", "buildx", "imagetools", "create")

# 合成命令里不得出现的 attestation 类入参：imagetools create 只合成清单，attestation 的取舍
# 只在构建步（provenance: false）决定，两处都写就等于把同一条契约摊到两个地方。
ATTESTATION_TOKENS = ("provenance", "attest", "sbom")


def _load_workflow() -> dict[Any, Any]:
    # 返回整个工作流的解析结果。类型标成 dict[Any, Any] 而不是 dict[str, Any] 是必需的：
    # YAML 1.1 的 `on:` 落成的键是 bool，用 str 键类型会让 mypy 直接判 data[True] 索引非法，
    # 于是「按真实形态写」的取值反而过不了门禁。
    if not WORKFLOW.is_file():
        raise AssertionError(f"发布工作流不存在：{WORKFLOW}")
    return cast("dict[Any, Any]", yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def data() -> dict[Any, Any]:
    return _load_workflow()


def _runner_registry() -> dict[str, str]:
    # runner 标签 ↔ 运行时键的唯一登记点（scripts/check_runtime_pins.py::RUNNER_TO_RUNTIME_KEY），
    # 按文件路径动态加载取常量，**不在本文件复制一份标签清单**——复制即造出第二份事实源。
    # 加载先例取同仓既有两处：check_runtime_pins._load_build_exe 与 tests/test_check_runtime_pins.
    # _load_checker（scripts/ 不在包路径内，只能 spec_from_file_location；该脚本 main() 受 __name__
    # 守卫，模块级只有常量定义，import 期零副作用、零联网）。
    # 「读不到就显式失败」而非返回空 dict：空表会让下面的成员断言在真空里成立（假绿），
    # 而登记表本身失效属「门禁坏了」档，与 check_runtime_pins 走 sys.exit(2) 的口径一致。
    path = ROOT / "scripts" / "check_runtime_pins.py"
    spec = importlib.util.spec_from_file_location("_runner_registry_for_docker_publish_lock", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法按文件路径加载 {path}，runner 登记表读不到即判失败")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = cast("dict[str, str]", module.RUNNER_TO_RUNTIME_KEY)
    if not registry:
        raise AssertionError(f"{path} 的 RUNNER_TO_RUNTIME_KEY 为空——唯一登记点已失效，本锁无从比对")
    return registry


def _triggers(doc: dict[Any, Any]) -> dict[Any, Any]:
    # 触发条件块。YAML 1.1 下 `on:` → 布尔 True 键；引号形态（"on":）→ str 键。
    # 两种都认，但认不到就显式失败：返回空 dict 会让「触发面 == {push}」这类断言无从判起，
    # 把「读不到」伪装成「没有多余触发器」的绿灯。
    for key in (True, "on"):
        value = doc.get(key)
        if isinstance(value, dict):
            return cast("dict[Any, Any]", value)
    raise AssertionError("无法从工作流读出触发条件块（`on:` 缺失或形态非预期）")


def _job(doc: dict[Any, Any], name: str) -> dict[Any, Any]:
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        raise AssertionError("工作流没有 jobs 块")
    job = jobs.get(name)
    if not isinstance(job, dict):
        raise AssertionError(f"工作流缺少 job：{name}")
    return cast("dict[Any, Any]", job)


def _steps(job: dict[Any, Any], name: str) -> list[dict[Any, Any]]:
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        raise AssertionError(f"job {name} 没有 steps 列表")
    return cast("list[dict[Any, Any]]", steps)


def _build_step(job: dict[Any, Any], name: str) -> dict[Any, Any]:
    # 取 docker/build-push-action 那一步。命中 0 条或多条都算失败：多步构建意味着分架构
    # 临时 tag / digest 的来源不再唯一，锁住 `id == build` 就失去了意义。
    matches = [s for s in _steps(job, name) if str(s.get("uses", "")).startswith("docker/build-push-action")]
    if len(matches) != 1:
        raise AssertionError(f"job {name} 的 build-push-action 步骤应恰好 1 条，实测 {len(matches)} 条")
    return matches[0]


def _run_containing(job: dict[Any, Any], name: str, needle: str) -> str:
    # 取 run 脚本里含 needle 的那一步的原文。判不到就显式失败：让 next() 的 StopIteration 或
    # 「取到空串再断言为空」替我们解释失败，报出来的是一行堆栈而不是「工作流少了什么」。
    for step in _steps(job, name):
        run = str(step.get("run", ""))
        if needle in run:
            return run
    raise AssertionError(f"job {name} 没有含 {needle!r} 的 run 步骤")


def _job_names(doc: dict[Any, Any]) -> list[str]:
    # 全部 job 名。判不到就失败：空列表会让「所有 job 都不得出现 :latest」这类全称断言
    # 在真空里成立——那正是本仓禁止的假绿形态。
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise AssertionError("工作流没有 jobs 块")
    return [str(name) for name in jobs]


def _create_args(command: str) -> list[str]:
    # 把 merge 的 run 原文解析成 `docker buildx imagetools create` 之后的实参序列：
    # 先接回反斜杠续行（块标量里每个实参各占一行，但改写者完全可能并成一行或换排版），
    # 再按 shell 词法切分——${{ … }} 表达式对 shlex 就是普通字符，外层双引号被剥掉。
    # 锚点命中 0 处或多处都显式失败：多处意味着「合成的不是同一份清单」，实参集合失去唯一所指。
    joined = " ".join(line.strip().rstrip("\\").strip() for line in command.splitlines() if line.strip())
    try:
        tokens = shlex.split(joined)
    except ValueError as exc:  # 引号未闭合之类的畸形命令：解析不了就判失败，绝不给绿灯
        raise AssertionError(f"无法对 merge 的合成命令做词法解析：{exc}") from exc
    anchor = list(CREATE_ANCHOR)
    hits = [i for i in range(len(tokens) - len(anchor) + 1) if tokens[i : i + len(anchor)] == anchor]
    if len(hits) != 1:
        raise AssertionError(f"合成命令里 `{' '.join(CREATE_ANCHOR)}` 应恰好 1 处，实测 {len(hits)} 处")
    return tokens[hits[0] + len(anchor) :]


def _split_create_args(args: list[str]) -> tuple[list[str], list[str], list[str]]:
    # 实参分三堆：-t/--tag 的对外 tag、位置实参（被合成的输入项）、其余选项。逐词游标而不是
    # 「整段文本判定」：-t 的取值本身不带前导 -，混进输入项就会把「对外 tag」当「digest 引用」判，
    # 于是锁红在错误的位置上（真实缺陷是引用形态，报出来的却是 tag 数量）。
    tags: list[str] = []
    sources: list[str] = []
    options: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token in ("-t", "--tag"):
            if index + 1 >= len(args):
                raise AssertionError(f"{token} 后面没有 tag 取值")
            tags.append(args[index + 1])
            index += 2
            continue
        if token.startswith("-"):
            # 刻意的唯一形态约束③：本解析只认 `-t/--tag <值>` 这一种带值选项，其余以 - 开头的词
            # 一律按「自身即完整」记账，其后那个词仍按位置实参处理。故给合成命令加 --builder NAME
            # 时，NAME 会被当成输入项、在 I-2 锁的「没有 @ 即红」处判红（方向同样是误报，不是假绿）。
            options.append(token)
            index += 1
            continue
        sources.append(token)
        index += 1
    return tags, sources, options


def test_only_tag_push_can_publish_latest(data: dict[Any, Any]) -> None:
    # latest 只允许由不可变的 tag 推出来：留 workflow_dispatch/schedule 的口子等于把发布物
    # 变成可反复改写的别名（规格 §二.5 明文否掉）。
    triggers = _triggers(data)
    assert set(triggers) == {"push"}, f"发布链触发面只能有 tag push：{sorted(map(str, triggers))}"
    push = triggers["push"]
    assert isinstance(push, dict) and push["tags"] == ["v*"], f"push 触发必须限定 v* tag：{push!r}"


def test_arch_jobs_run_on_matching_native_runners(data: dict[Any, Any]) -> None:
    registry = _runner_registry()
    seen_runners: list[str] = []
    for name, (runner, image_platform) in ARCH_JOBS.items():
        job = _job(data, name)
        actual = str(job["runs-on"])
        assert actual == runner, f"{name} 必须跑在原生 {runner} 上，不得用 QEMU 交叉构建"
        # 评审 I-2 的跨文件同源断言：本 job 实际用的 runner 标签必须**已在唯一登记点里**。
        # 只看「与 ARCH_JOBS 相等」不够——那张表就硬编在本文件里，两侧一起改就同时成立；
        # 与登记表比对才抓得住「这个标签根本没被登记过」（改名的典型形态：ubuntu-24.04-arm64）。
        assert actual in registry, (
            f"{name} 的 runs-on={actual!r} 不在 scripts/check_runtime_pins.py::RUNNER_TO_RUNTIME_KEY 里；"
            f"新增 runner 标签必须同批登记，否则发布链的运行时覆盖校验根本不知道有这个平台（已登记：{sorted(registry)}）"
        )
        seen_runners.append(actual)
        build = _build_step(job, name)
        # 入参名实测取自 docker/build-push-action 的 action.yml：是 platforms（不是 platform）。
        # 写错的名字不会报错，只会被当作未知入参忽略，退化成单架构构建。
        assert build["with"]["platforms"] == image_platform, f"{name} 的目标平台应为 {image_platform}"
        assert build["with"]["push"] is True, f"{name} 必须把分架构层推到 registry，merge job 才拿得到 digest"
        assert build["id"] == BUILD_STEP_ID, f"{name} 的构建步骤 id 必须是 {BUILD_STEP_ID}（merge job 按它取值）"
        digest_out = job["outputs"]["digest"]
        assert digest_out == "${{ steps.build.outputs.digest }}", f"{name} 必须把 digest 提升为 job 级 output"
    # 防空转：ARCH_JOBS 被清空、或两个 job 塌到同一个标签时，上面的全称循环会在真空里成立。
    # 「两个架构各占一支互不相同的已登记原生 runner」是本锁的语义本体，故按集合大小而非条数断言。
    assert len(set(seen_runners)) == len(ARCH_JOBS), f"每个 arch job 必须各占一支互不相同的 runner：{seen_runners}"


def test_manifest_merge_needs_both_arch_jobs(data: dict[Any, Any]) -> None:
    merge = _job(data, "docker-manifest")
    assert set(merge["needs"]) == {"prepare", "docker-build-amd64", "docker-build-arm64"}, "合成清单必须等三者齐备"
    command = _run_containing(merge, "docker-manifest", "imagetools create")
    for ref in ("needs.docker-build-amd64.outputs.digest", "needs.docker-build-arm64.outputs.digest"):
        assert ref in command, f"合成清单必须按 digest 引用两个架构层，缺 {ref}"
    # 版本 tag 与 latest 必须落在同一条命令里：分开发布会出现「只有 latest 变了、版本 tag 没变」的半发状态。
    assert ":latest" in command and ":v${{ needs.prepare.outputs.version }}" in command


def test_only_the_auto_github_token_is_referenced() -> None:
    # 发布链的凭据只能是被自动注入的那一把：出现任何其它 secrets.* 就说明有人塞了手工密钥。
    # 断言形态必须是「集合相等」而不是「不含 secrets.」——后者会把 GITHUB_TOKEN 一起禁掉，
    # 而 login-action 没有 password 根本登不上 GHCR。
    text = WORKFLOW.read_text(encoding="utf-8")
    refs = set(re.findall(r"secrets\.[A-Za-z0-9_]+", text))
    assert refs == {"secrets.GITHUB_TOKEN"}, f"发布链引入了非自动凭据：{sorted(refs)}"


def test_release_style_concurrency(data: dict[Any, Any]) -> None:
    # 发布类不允许半途取消：推一半被杀会留下「分架构临时 tag 已存在、对外清单未合成」的残缺态，
    # 与 build-release.yml 的 cancel-in-progress: false 同一条理由。
    concurrency = data["concurrency"]
    assert concurrency["cancel-in-progress"] is False


def test_no_in_job_package_install_steps() -> None:
    # 依赖安装全部发生在 Dockerfile 里（镜像层），job 内不得再出现 apt/pip/choco 直装步骤：
    # 那既绕过 .github/actions/retry 的统一重试口径，又会让「镜像里有什么」与「job 里装了什么」分家。
    text = WORKFLOW.read_text(encoding="utf-8")
    for anchor in INSTALL_ANCHORS:
        assert anchor not in text, f"job 内出现 {anchor}：安装链应只在 Dockerfile"


def test_packages_write_only_where_images_are_pushed(data: dict[Any, Any]) -> None:
    # 最小权限：GITHUB_TOKEN 自带 packages: write 的能力，故必须靠 permissions 收窄而不是靠
    # 「没人去用」。判据双向——推镜像的三个 job 都得有 packages: write（缺一个即那一步 401），
    # 顶层不得预先给 write（缺这条即任何新 job 默认继承写权限，最小权限名存实亡）。
    top = data["permissions"]
    assert top.get("contents") == "read", f"顶层 permissions 应只读：{top!r}"
    assert "packages" not in top, f"顶层不得授予 packages 写权限：{top!r}"
    for name in PUSH_JOBS:
        perms = _job(data, name)["permissions"]
        assert perms.get("packages") == "write", f"{name} 要推镜像，必须有 packages: write"
        assert perms.get("contents") == "read", f"{name} 的 contents 应保持只读"


def test_image_version_still_comes_from_build_arg(data: dict[Any, Any]) -> None:
    # Dockerfile 的 ARG 行序约束（MIN-14）与 scripts/check_version.py 的断言都不动，
    # 本工作流的职责只是把版本传进去；漏传会让镜像内版本固化成空串且构建期不报错。
    for name in ("docker-build-amd64", "docker-build-arm64"):
        build = _build_step(_job(data, name), name)
        build_args = str(build["with"]["build-args"])
        assert "APP_VERSION=${{ needs.prepare.outputs.version }}" in build_args, f"{name} 未注入 APP_VERSION"


def test_image_name_is_derived_from_the_running_owner(data: dict[Any, Any]) -> None:
    # 镜像名一律 ghcr.io/<owner 小写>/douyin-live-recorder：用仓库 owner 而不是上游命名空间，
    # fork 才推得进自己的包；GHCR 强制小写，owner 带大写时推送会直接 4xx，故派生链里必须有小写化。
    run = _run_containing(_job(data, "prepare"), "prepare", "douyin-live-recorder")
    assert "GITHUB_REPOSITORY_OWNER" in run, "镜像名必须由 GITHUB_REPOSITORY_OWNER 派生，不得写死任何命名空间"
    assert "[:upper:]" in run, "owner 必须显式转小写后再拼镜像名"


def test_provenance_is_disabled_on_both_arch_builds_and_absent_from_merge(data: dict[Any, Any]) -> None:
    # I-1：`provenance: false` 是承重取值，删掉它 CI 三步全绿、只在用户 docker pull 时暴露。
    # 因果链（2026-10-03 取证）：docker/build-push-action v6/v7 的 action.yml 里 provenance 入参
    # 没有 default 键，不显式写就交给 buildx；docker/docs 写明「Provenance attestations with the
    # mode=min level are added to images by default」，attestation 被 attach 成 image index 里的
    # 一个 manifest（platform 记为 unknown/unknown）。于是 push 出去的顶层对象不再是单架构
    # manifest 而是 index，steps.build.outputs.digest 退化成 index digest，merge 合成的对外清单
    # 里就混入非镜像条目。
    for name in ARCH_TAG_SUFFIX:
        build = _build_step(_job(data, name), name)
        # 取 .get() 而不是 ["provenance"]：「删掉这一行」与「改成 true」都要红，且消息可读。
        # 刻意的唯一形态约束②：只认 YAML 布尔 False。写成字符串 "false" 行为等价（GitHub 把 with:
        # 的值一律转成文本，provenance 经 core.getInput 读到的都是 "false"），但 `is False` 判红；
        # 方向是误报而非假绿，共同理由见文件上方常量段。
        assert build["with"].get("provenance") is False, f"{name} 必须显式 provenance: false（承重取值，见上方注释）"
    # merge 侧：合成命令里不得出现 attestation/provenance 类入参。imagetools create 只做清单合成，
    # 在这里补一个「attestation 参数」既救不了 digest 契约，又把同一条契约摊到两处、再也无法一起核对。
    merge_command = _run_containing(_job(data, "docker-manifest"), "docker-manifest", "imagetools create")
    for token in _create_args(merge_command):
        lowered = token.lower()
        assert not any(t in lowered for t in ATTESTATION_TOKENS), f"合成命令出现 attestation 类入参：{token!r}"


def test_manifest_merge_inputs_are_digest_refs_not_arch_tags(data: dict[Any, Any]) -> None:
    # I-2：合成清单的输入项必须是「镜像名 @ 该架构 job output 的 digest」。旧锁只查
    # needs.docker-build-<arch>.outputs.digest 这个子串是否出现在 run 原文，于是 `IMAGE@<digest>`
    # 写成 `IMAGE:<tag>`（退回可变分架构 tag）或干脆丢掉 `@` 都能全绿。丢 @ 的后果：imagetools
    # create 收到无效引用直接 rc=1，而两个 build job 已推成功、临时 tag 已落 registry，只剩最后
    # 一步红（最难归因的那种）。
    merge = _job(data, "docker-manifest")
    command = _run_containing(merge, "docker-manifest", "imagetools create")
    _tags, sources, _options = _split_create_args(_create_args(command))
    assert sources, "合成命令没有位置实参：等于什么都没合成，引用形态无从判定"
    seen: dict[str, str] = {}
    for token in sources:
        # 先按 @ 切成两半再各自判定，而不是拿整串字面量比排版。
        head, at, tail = token.rpartition("@")
        assert at, f"输入项 {token!r} 没有 @ —— 按 tag（可变）而不是按 digest（不可变）引用架构层"
        assert head, f"输入项 {token!r} 的 @ 左边为空：缺镜像名，imagetools create 必 rc=1"
        assert not ARCH_TAG_SUFFIX_RE.search(token), f"输入项 {token!r} 带分架构临时 tag 后缀"
        matched = DIGEST_REF.match(tail)
        assert matched, f"输入项 {token!r} 的 @ 右边不是 needs.docker-build-<arch>.outputs.digest"
        arch = matched.group("arch")
        assert arch not in seen, f"架构 {arch} 被引用两次：{seen[arch]!r} 与 {token!r}"
        seen[arch] = token
    for arch in ("amd64", "arm64"):
        assert arch in seen, f"合成清单缺少 {arch} 的 digest 引用（merge 会拿空串或只出一层）"


def test_arch_build_tags_are_temp_only_and_latest_appears_once_in_merge(data: dict[Any, Any]) -> None:
    # I-3：分架构 build job 只推「一行、带自己架构后缀、不含 :latest」的临时 tag；对外 :latest
    # 在整个工作流里只允许出现一次且落在 merge 的合成命令里（规格 §二.5「latest 只由不可变 tag、
    # 经 merge 单点合成」的否定面）。评审实测：往 amd64 的 tags 追加 :latest 时旧锁全绿，真实后果是
    # latest 退化成单架构层（arm64 主机拉 latest 拿到 amd64 层），且 merge 之后仍可能被后续半发覆盖。
    for name, arch in ARCH_TAG_SUFFIX.items():
        build = _build_step(_job(data, name), name)
        # 刻意的唯一形态约束①：with.tags 只认**标量串**（串里可以多行，逐行判）。改成语义等价的
        # YAML 列表形态（tags: 下一个 "- <image>:v…-amd64"）时，str() 拿到的是 "['…']" 这个 repr，
        # endswith(f"-{arch}") 于是判红（行数与 :latest 计数两条不受影响）。方向是误报而非假绿：
        # 列表与标量同义要多一层 YAML 类型语义才认得，共同理由见上方常量段。
        lines = [line.strip() for line in str(build["with"]["tags"]).splitlines() if line.strip()]
        assert len(lines) == 1, f"{name} 的 tags 应只有一行临时 tag，实测 {len(lines)} 行：{lines!r}"
        tag = lines[0]
        assert tag.endswith(f"-{arch}"), f"{name} 的临时 tag 必须以 -{arch} 结尾（否则两个架构写同一个 tag）"
        assert LATEST_TAG not in tag, f"{name} 不得直接推 {LATEST_TAG}：latest 只能由 merge 按两个 digest 合成"
    # 扫描面取解析后的结构而不是全文：本文件的承重注释里就写着 :latest 这个词（provenance 那段
    # 的因果说明），全文计数会把「注释」当成「发布行为」一起算进去。
    hits = 0
    for name in _job_names(data):
        for step in _steps(_job(data, name), name):
            texts = [str(step.get("run", ""))]
            with_block = step.get("with")
            if isinstance(with_block, dict):
                texts.extend(str(value) for value in with_block.values())
            hits += sum(text.count(LATEST_TAG) for text in texts)
    merge_command = _run_containing(_job(data, "docker-manifest"), "docker-manifest", "imagetools create")
    assert merge_command.count(LATEST_TAG) == 1, f"merge 的合成命令里 {LATEST_TAG} 应恰好出现 1 次"
    assert hits == 1, f"{LATEST_TAG} 在全工作流解析结果里应恰好 1 次（实算 {hits} 次），且只能在 merge 的命令里"
