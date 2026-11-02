# Linux arm64 ffmpeg 支持 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Linux aarch64 成为「有人构建、能自取已校验二进制、有原生镜像」的一等发布目标，而不只是钉定表里一个没人用的键。

**Architecture:** 三段互不耦合：S1 给既有发布链补一个 arm64 runner（`build_exe.py` 的取数与钉定**一行不改**，
只让 CI 真的去构建它）；S2 新增 `src/ffmpeg_linux_download.py`，在包管理器链失败后以「月末不可变标签 +
GitHub API 公布 digest」做已校验直下，TOFU 只在显式开关下才可达；S3 新增 GHCR 多架构发布工作流，
原生双 runner 各出一层、merge job 合成 manifest，零新增 secret。

**Tech Stack:** Python 3.14 / GitHub Actions（`ubuntu-24.04-arm`）/ requests + tarfile + loguru /
pytest 9 + PyYAML / buildx + GHCR。

**Spec:** `docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md`（已获批，2026-10-02；本计划逐段对应其 S1/S2/S3）

## Global Constraints

每条都对所有 Task 生效，取值一律逐字来自 `AGENTS.md` / 规格，不得凭印象改写：

- **不执行任何 `git commit`**（用户 2026-10-02 明确指令：在当前 89 个文件 staged 未提交的状态上开工）。
  本计划所有 Task 的收尾步骤是「记录改动三元组」而非提交。
- **门禁唯一入口**：`python scripts/run_gates.py`；命令清单的事实源是 `AGENTS.md`「格式化命令（门禁唯一基准）」，
  **不得**在任何文件里复制一套 black/isort/mypy 参数。mypy 一律**不带路径**。
- **Python 3.14 venv**：语法/编译检查必须用项目 venv 的 3.14（3.13 会把 `except A, B:` 误报成 SyntaxError）。
- **多异常写法**：新增/修改代码写无括号 `except A, B:`（PEP 758）；需要 `as` 绑定时才加括号。
- **注释**：统一 `#`，**禁止 docstring**；写「为什么」不写「做什么」；改注释只增不改（被证伪的除外）。
- **行宽 120**（black + isort）。
- **形参日志一律 `i18n.tr(常量模板, **kw)`，禁止 f-string**；新模板**同批**补进
  `i18n/zh_CN/LC_MESSAGES/zh_CN.po`、`i18n/en_US.json`、`i18n/en_GB.json`、`i18n/zh_TW.yaml`
  四目录并 `python scripts/compile_po.py` 重编 `.mo`（`tests/test_i18n_migration.py` 是硬门禁）。
- **异常日志必须带 `{type_name}` 与 `{masked_url}`**，URL/代理进日志前一律过 `utils.mask_credentials()`。
- **下载源三处同改**（AGENTS.md 关键约定 #10）：源码 URL 常量 + `tests/test_ffmpeg_install.py::DOWNLOAD_SOURCES`
  + `DOWNLOAD_MODULES`；缺一即锁红。完整性方式取值域 = `{"官方哈希","官方签名","第4类","TOFU"}`。
- **测试替身**：环境变量只用 `monkeypatch.setenv/delenv`（禁 `patch.dict(os.environ)`）；
  替换 `requests`/`subprocess`/`os` 必须走 `types.SimpleNamespace(**vars(真身))` 覆盖**被测模块的全局引用**，
  绝不动 stdlib/第三方模块本体；产物一律落 `tmp_path`。
- **变异验证**：安全不变量类用例（T-1/T-2/T-5）必做；改动行加 `MUTATION-<短id>` 标记并**当轮还原**，
  收尾断言 `read_bytes() == 原字节`。
- **平台判定用 `sys.platform` / `platform.machine()` 字面量**，且新增用例不得用 `skipif` 让 Linux CI 跳过
  Windows 分支（反向同理）。
- **`.dockerignore`/`.gitignore` 不新增前缀**：本文件与规格同用既有 `PROPOSAL_*.md` 按名模式，不动 ignore 文件。

---

## 文件结构总览

| 动作 | 路径 | 职责 |
| --- | --- | --- |
| Modify | `.github/workflows/build-release.yml` | 矩阵第 4 项、两个 `if:` 条件、`-lt 8`、头部注释 |
| Modify | `scripts/check_runtime_pins.py:58-62` | `RUNNER_TO_RUNTIME_KEY` 登记 `ubuntu-24.04-arm` |
| Modify | `build_exe.py:425-427` | 只改注释措辞（三平台 → 四平台），**行为零改动** |
| Modify | `tests/test_check_runtime_pins.py` | `_MATRIX_KEYS` 补 `linux-arm64`（顺序即契约） |
| Create | `src/ffmpeg_linux_download.py` | Linux 原生 ffmpeg 直下 + 官方 digest 校验 + 降级 TOFU |
| Modify | `src/ffmpeg_install.py:516-566` | 包管理器链失败后接线新模块（传 `master_allowed`） |
| Create | `tests/test_ffmpeg_linux_download.py` | 真值表四格 + 架构分流 + URL 反解 + 取件/缺件 + 失败不抛 + 两处副本一致性锁 |
| Modify | `tests/test_ffmpeg_install.py:77,885-912` | `DOWNLOAD_MODULES` 加新模块、`DOWNLOAD_SOURCES` 加 `api.github.com` |
| Modify | `i18n/*/{zh_CN.po,en_US.json,en_GB.json,zh_TW.yaml}` + 重编 `.mo` | 新模板条目 |
| Create | `.github/workflows/docker-publish.yml` | GHCR 多架构发布（原生双建 + imagetools 合成） |
| Create | `tests/test_docker_publish_workflow.py` | 工作流结构锁（T-8） |
| Modify | `AGENTS.md`、`CODE_WIKI.md`、`CODE_WIKI_EN.md`、`README.md`、`README_EN.md` | 长期约定与产物/镜像口径 |

---

## Task 1: 发布矩阵接入 linux-arm64

**Files:**
- Modify: `.github/workflows/build-release.yml`（矩阵 :256-262、两个 `if:` :298/:368/:374、齐全性 :511-522、头部 :2）
- Modify: `scripts/check_runtime_pins.py:55-62`
- Modify: `build_exe.py:425-427`（仅注释）
- Test: `tests/test_check_runtime_pins.py`（`_MATRIX_KEYS`）

**Interfaces:**
- Consumes: 无（本 Task 是链条起点）
- Produces: 发布矩阵运行时键序列 `["windows-x64", "linux-x64", "linux-arm64", "macos-arm64"]`；
  `RUNNER_TO_RUNTIME_KEY["ubuntu-24.04-arm"] == "linux-arm64"`。Task 6 的产物齐全性口径与本序列同源。

- [ ] **Step 1：先把 `check_runtime_pins` 跑一遍，确认改前基线 rc=0**

Run: `python scripts/check_runtime_pins.py`
Expected: rc=0，且 `[NOTE]`/告警里 `linux-arm64` 出现在「矩阵外键只告警」那一档（今天它**不在**矩阵里）。

- [ ] **Step 2：登记 runner 标签**

把 `scripts/check_runtime_pins.py:55-62` 改为（注释同步实况，映射本体是新增行）：

```python
# runner 标签 → 运行时键。与 build-release.yml 的 matrix.include 四平台一致：
# windows-latest / ubuntu-latest 为 x64，ubuntu-24.04-arm 为 linux aarch64，macos-latest 为 arm64（Apple Silicon）。
# 若矩阵将来改用显式架构标签或再加平台，须同步这张映射，否则会出现
# 「表里有键、矩阵里没平台」（无害）或「矩阵有平台、表里缺键」（本脚本报红）。
RUNNER_TO_RUNTIME_KEY = {
    "windows-latest": "windows-x64",
    "ubuntu-latest": "linux-x64",
    "ubuntu-24.04-arm": "linux-arm64",
    "macos-latest": "macos-arm64",
}
```

- [ ] **Step 3：矩阵插入第 4 项（位置即契约）**

`build-release.yml` 的 `strategy.matrix.include` 改为（`ubuntu-24.04-arm` **必须**紧跟 `ubuntu-latest`，
在 `macos-latest` 之前——`_runtime_matrix_keys()` 按 `os:` 行出现顺序返回列表，
而 Step 4 的测试断言与 `_MATRIX_KEYS` **逐序相等**，不是集合比较）：

```yaml
      matrix:
        include:
          - os: windows-latest
            platform: windows
          - os: ubuntu-latest
            platform: linux
          - os: ubuntu-24.04-arm
            platform: linux-arm64
          - os: macos-latest
            platform: macos
```

- [ ] **Step 4：三个 `if:` 条件扩到 linux 家族**

`:298` 与 `:368` 两步的条件由 `matrix.platform == 'linux'` 改为 `startsWith(matrix.platform, 'linux')`；
`:374`「Build executables + smoke test」由 `!= 'linux'` 改为 `!startsWith(matrix.platform, 'linux')`。
两步的 `name` 里「(Linux, xvfb)」保持不变。
**理由必须写进 YAML 注释**（否则下一个改矩阵的人会重犯）：arm64 job 若不落进 xvfb 分支，
GUI 冒烟在无头 aarch64 上必红；若又落进通用分支，它拿到的是 `tee build_exe.log` 而没有 `xvfb-run`。

```yaml
      # 两个 Linux 分支按**家族**判定而不是精确等于：linux-arm64 与 linux-x64 需要同一条
      # xvfb + 包管理器安装链，差别只在 runner 架构（build_exe.py 自己按 runtime_slot_key() 取对应产物）。
      - name: Install ffmpeg + xvfb (Linux)
        if: startsWith(matrix.platform, 'linux')
```

- [ ] **Step 5：产物齐全性 6 → 8**

`Verify artifact completeness` 步骤（:511-522）改：

```bash
          if [ "$count" -lt 8 ]; then
            echo "::error::产物数量不足（期望 8 个：windows/linux/linux-arm64/macos × lite/full，实际 ${count} 个）"
            exit 1
          fi
```

并把上方注释「3 平台 × (lite + full) = 6 个 zip」改为「4 平台 × 2 = 8 个 zip」。

- [ ] **Step 6：同步两处纯注释**

`build-release.yml:2` 标题段「三平台可执行文件构建与 GitHub Release 发布」→「四平台（含 linux aarch64）…」；
`build_exe.py:425-427` 上方注释「与 .github/workflows/build-release.yml 的三平台矩阵同源」→「四平台矩阵同源」。
`build_exe.py` 的 `RELEASE_RUNTIME_KEYS` 本体**不动**（已含 `linux-arm64`）。

- [ ] **Step 7：更新测试常量并跑锁**

`tests/test_check_runtime_pins.py` 的 `_MATRIX_KEYS` 改为与 Step 3 顺序逐字一致：

```python
_MATRIX_KEYS = ["windows-x64", "linux-x64", "linux-arm64", "macos-arm64"]
```

Run: `pytest tests/test_check_runtime_pins.py -q`
Expected: PASS，含 `test_workflow_matrix_and_test_constant_stay_in_sync` 与
`test_real_matrix_parser_rejects_unregistered_runner_tag`（后者用合成样本，不受本次影响）。
若 `_MATRIX_KEYS` 忘了改，同步锁会直接列出两侧差异——这条就是本 Task 的失败模式。

- [ ] **Step 8：确认 `--strict` 现在真的管住 linux-arm64**

Run: `python scripts/check_runtime_pins.py --strict`
Expected: rc=0（该键已钉定）。**反向见证**：临时把 `build_exe._PINNED_RUNTIME_SHA256["linux-arm64"]["ffmpeg"]`
改成 `UNVERIFIED_PIN`（加标记 `# MUTATION-S1-ARM64PIN`），本命令必须 rc=1；随后**按字节还原**并复跑 rc=0。
这一步证明「进入矩阵」不是纸面动作——它现在进了 `--strict` 的失败集合。

- [ ] **Step 9：记录三元组（不提交）**

回复里写：最终修订文件 + 实际执行命令 + 通过/失败；并列出 `git status --short` 中本 Task 新增的改动。

---

## Task 2: `src/ffmpeg_linux_download.py` 的纯函数层

**Files:**
- Create: `src/ffmpeg_linux_download.py`
- Test: `tests/test_ffmpeg_linux_download.py`

**Interfaces:**
- Consumes: 无外部依赖（只 import `requests`/`i18n`/`src.utils`）
- Produces:
  - `_LINUX_FFMPEG_URLS: dict[str, str]`（键 `"linux64"` / `"linuxarm64"`，值 = 与 `build_exe._FFMPEG_DOWNLOAD_URLS` 逐字相同的 URL）
  - `_linux_arch() -> str`
  - `_asset_url(arch: str) -> str`
  - `_api_release_url(asset_url: str) -> str`（反解失败回 `""`）
  - `_asset_name(asset_url: str) -> str`
  - `_fetch_asset_digest(asset_url: str) -> str`（64 位小写十六进制或 `""`）
  - Task 3 依赖这些签名，**不得**改名。

- [ ] **Step 1：先写失败测试（架构分流 + URL 反解）**

新建 `tests/test_ffmpeg_linux_download.py`，头部按本仓约定用 `#` 注释说明组织方式。
**本 Task 的 import 段只写** `platform` / `types` / `typing.Any` / `pytest` / `requests` /
`import src.ffmpeg_linux_download as fld`；`hashlib/io/subprocess/tarfile/Path` 随 Task 3 的用例补，
`from pathlib import Path` 与 `from build_exe import _FFMPEG_DOWNLOAD_URLS` 随 Task 5 的 parity 锁补
（提前引入就是未用导入，basedpyright 本地门禁会报）。然后：

```python
# tests/test_ffmpeg_linux_download.py —— src/ffmpeg_linux_download.py 的回归锁。
#
# 组织方式：按「删掉哪条判据就该变红」分组（分流 / URL 反解 / 真值表 / 失败不抛 / 两处副本一致性）。
# 全部离线：requests / subprocess / 落盘目录三面被打桩或收敛到 tmp_path，
#   绝不真下 ~110MB 产物，也不写程序目录（AGENTS.md「测试产物一律走 tmp_path」）。
# 替身口径：stdlib 与第三方模块一律走**被测模块命名空间的 shim**
#   （types.SimpleNamespace(**vars(真身)) 浅拷贝后只覆盖所需属性，再 monkeypatch.setattr(fld, ...)）；
#   直接 monkeypatch.setattr(fld.platform, "machine", ...) 改的是全进程 platform 本体，
#   窗口内其它模块（loguru / 后台线程）的 machine() 调用一并被换——AGENTS.md M-27 明令禁止该形态。

import platform
import types
from typing import Any

import pytest
import requests

import src.ffmpeg_linux_download as fld

LINUX64_URL = fld._LINUX_FFMPEG_URLS["linux64"]
LINUXARM64_URL = fld._LINUX_FFMPEG_URLS["linuxarm64"]


def _platform_shim(machine: str) -> Any:
    shim = types.SimpleNamespace(**vars(platform))
    shim.machine = lambda: machine
    return shim


class TestArchSelection:
    @pytest.mark.parametrize(
        ("machine", "expected"),
        [
            ("aarch64", "linuxarm64"),
            ("arm64", "linuxarm64"),
            ("x86_64", "linux64"),
            ("AMD64", "linux64"),
            ("", "linux64"),
            ("riscv64", "linux64"),
        ],
    )
    def test_unknown_arch_falls_back_to_linux64(
        self, monkeypatch: pytest.MonkeyPatch, machine: str, expected: str
    ) -> None:
        monkeypatch.setattr(fld, "platform", _platform_shim(machine))
        assert fld._linux_arch() == expected

    def test_asset_url_is_registered_for_both_arches(self) -> None:
        assert fld._asset_url("linuxarm64") == LINUXARM64_URL
        assert fld._asset_url("linux64") == LINUX64_URL
        # 陌生 arch 必须抛而不是回落：静默回落 = 给 aarch64 机器装 x86_64 二进制还不吭声。
        with pytest.raises(KeyError):
            fld._asset_url("s390x")


class TestApiUrlDerivation:
    def test_api_url_is_derived_from_asset_url(self) -> None:
        api = fld._api_release_url(LINUXARM64_URL)
        assert api == "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27"
        assert fld._asset_name(LINUXARM64_URL) == "ffmpeg-n9.0.1-11-ge47273f4d9-linuxarm64-gpl-9.0.tar.xz"

    def test_unparsable_url_yields_empty_api(self) -> None:
        # 含 http（非 https）与陌生域：绝不带着猜想的 API URL 出站。
        for bad in ("", "https://example.com/x.tar.xz", "http://github.com/a/b/releases/download/t/n.tar.xz"):
            assert fld._api_release_url(bad) == ""
```

digest 形状关与两处副本一致性锁在 **Task 5** 落（它们依赖 Task 5 才抽出的 `_digest_from_assets`）；
真值表与「失败不抛」在 **Task 3** 落，届时随用例补 `hashlib/io/subprocess/tarfile` 四个 import。

- [ ] **Step 2：跑测试确认失败**

Run: `pytest tests/test_ffmpeg_linux_download.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'src.ffmpeg_linux_download'`。

- [ ] **Step 3：写模块头部与纯函数层**

新建 `src/ffmpeg_linux_download.py`。**本 Task 只 import 本 Task 用到的名字**
（`platform/re/Any/cast/requests/logger/i18n/utils`）；`os/stat/shutil/subprocess/tarfile/tempfile/time/Path`
留到 Task 3 随各自消费者一起加——basedpyright 的未用导入会在本地补充门禁里报红，
而「先抄全再删」会让 Task 2 的门禁读数不可信。**头部注释是本模块的存在理由，必须写全**
（按本仓「为什么」约定）：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Linux 原生 ffmpeg 直下安装器（AGENTS.md「三类钉定/校验」的类别②，Linux 分支）。
#
# 为什么需要它：install_ffmpeg_linux() 原先只有 yum/apt 两条路，两者都要求 root 且要求发行版仓库里
#   有 ffmpeg 包。aarch64 上的轻量发行版/容器/无 root 部署正好同时缺这两条，于是「未装 ffmpeg」
#   在 Linux 上只剩「请手动安装」一句死路。
#
# 为什么默认路径必须已校验：AGENTS.md ② 的红线是「TOFU 不得成为默认路径」。本模块的期望值来自
#   api.github.com 上该 release asset 的 digest 字段，而下载 URL 里的标签是**月末 autobuild**
#   （与 build_exe._FFMPEG_DOWNLOAD_URLS 同一份，一致性由 tests/test_ffmpeg_linux_download.py 的
#   TestUrlParityWithBuildExe 锁住）——标签不可变，期望值不会随上游重发漂移。
#   [口径] 它与产物同属 GitHub 平台但**异服务**（API 域 ↔ 对象存储域），属
#   「同源一致性校验而非来源认证」，与 gyan.dev 的 .sha256 同级（MIN-2258 同一措辞），
#   **不得**在注释或日志里写成「已认证来源」。
#
# 为什么降级档仍要开关：GitHub API 不可达 / 403 限流时拿不到 digest，此时唯一可选项是首次信任。
#   那一条与 Windows 的 master 源同强度，故复用同一个默认关闭的开关 FFMPEG_MASTER_ALLOWED，
#   并由**调用方传入** master_allowed（本模块反向 import ffmpeg_install 会构成循环依赖）。
#
# 为什么单独成模块：ffmpeg_master_download.py 的语义是「master 滚动别名 + 只有 TOFU 一档 + 只认 zip」，
#   把「不可变标签 + 官方 digest + tar.xz」塞进去会让两个完整性档在同模块内互相打脸。

import platform
import re
from typing import Any, cast

import requests
from loguru import logger

import i18n
from src import utils

# 与 ffmpeg_master_download 同量级但**各自持有**：跨模块引私有常量会把 Windows 语义模块的内部细节
# 变成第二个耦合点（该模块的超时取值是为「挑战页探针」调的，Linux 侧没有这个问题）。
_CONNECT_TIMEOUT = 15
_READ_TIMEOUT = 30
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0

# 与 build_exe._is_pinned 同一条形状关：只看形状不看语义，占位/截断/大写形态一律算「取不到」。
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
# 只认 https 的 GitHub release 直链：形态不符即无法反解 repo/tag，一律按「取不到官方哈希」处理，
# 绝不带着猜想的 API URL 出站。
_ASSET_URL_PATTERN = re.compile(
    r"^https://github\.com/(?P<repo>[^/]+/[^/]+)/releases/download/(?P<tag>[^/]+)/(?P<asset>[^/]+)$"
)

_HASH_PREFIX = "_ffmpeg_linux"
_HASH_SUFFIX = ".tar.xz.sha256"

# 两条 URL 与 build_exe._FFMPEG_DOWNLOAD_URLS 的 linux 两项**逐字相同**（物理上两份：冻结 exe 里
# import 不到根目录 build 脚本）。改一处必须同步另一处，由 TestUrlParityWithBuildExe 机检。
_LINUX_FFMPEG_URLS: dict[str, str] = {
    "linux64": (
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
        "autobuild-2026-08-31-13-27/ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0.tar.xz"
    ),
    "linuxarm64": (
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
        "autobuild-2026-08-31-13-27/ffmpeg-n9.0.1-11-ge47273f4d9-linuxarm64-gpl-9.0.tar.xz"
    ),
}


def _linux_arch() -> str:
    # 保守判据与 ffmpeg_master_download._windows_arch() 同构：只认 arm64/aarch64 为 ARM，
    # 其余（x86_64/AMD64/空串/未知）一律 linux64——架构信息不可信时宁可装能跑的那份。
    return "linuxarm64" if platform.machine().lower() in ("arm64", "aarch64") else "linux64"


def _asset_url(arch: str) -> str:
    # 未知 arch 必须抛 KeyError 而不是回落：回落等于「静默拿错架构的产物」，
    # 而调用方给的 arch 只可能来自 _linux_arch() 或测试，出现陌生值只可能是改错。
    return _LINUX_FFMPEG_URLS[arch]


def _api_release_url(asset_url: str) -> str:
    match = _ASSET_URL_PATTERN.match(asset_url)
    if match is None:
        return ""
    return f"https://api.github.com/repos/{match.group('repo')}/releases/tags/{match.group('tag')}"


def _asset_name(asset_url: str) -> str:
    match = _ASSET_URL_PATTERN.match(asset_url)
    return match.group("asset") if match else ""


def _mask(url: str) -> str:
    return utils.mask_credentials(url)


def _fetch_asset_digest(asset_url: str) -> str:
    # 恒不抛：任何异常/非 200/形态非法一律回 ""，由调用方按「取不到官方哈希」分支处理。
    api_url = _api_release_url(asset_url)
    if not api_url:
        return ""
    want = _asset_name(asset_url)
    try:
        response = requests.get(
            api_url,
            headers={"Accept": "application/vnd.github+json"},
            timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
        )
        if response.status_code != 200:
            # 403（限流）与 404 都在此归一成「取不到」——本模块的降级路径就是为此而设计，
            # 把它当错误中断安装只会让用户在 GitHub API 限流时完全装不上 ffmpeg。
            logger.debug(
                i18n.tr(
                    "未取得 ffmpeg 官方 SHA256（API 返回 {status}）: {masked_url}",
                    status=response.status_code,
                    masked_url=_mask(api_url),
                )
            )
            return ""
        payload = cast("dict[str, Any]", response.json())
    except Exception as e:
        logger.debug(
            i18n.tr(
                "未取得 ffmpeg 官方 SHA256（请求异常）: {masked_url} - {type_name}: {err}",
                masked_url=_mask(api_url),
                type_name=type(e).__name__,
                err=e,
            )
        )
        return ""
    for asset in payload.get("assets") or []:
        if not isinstance(asset, dict) or str(asset.get("name") or "") != want:
            continue
        digest = str(asset.get("digest") or "").strip().lower()
        if digest.startswith("sha256:"):
            digest = digest.partition(":")[2]
        return digest if _SHA256_PATTERN.fullmatch(digest) else ""
    return ""
```

- [ ] **Step 4：跑测试确认通过**

Run: `pytest tests/test_ffmpeg_linux_download.py -q`
Expected: PASS（本 Task 只含纯函数层）。

- [ ] **Step 5：补两条门禁自检**

Run: `mypy` （不带路径）与 `python -m black --check --diff --line-length 120 --target-version py314 src/ffmpeg_linux_download.py`
Expected: 均 0。`import src.ffmpeg_linux_download` 会触发 `i18n`/`src.utils` 的既有类型面，不应新增任何 mypy 条目。

- [ ] **Step 6：记录三元组（不提交）**

---

## Task 3: 完整性真值表与安装入口

**Files:**
- Modify: `src/ffmpeg_linux_download.py`（追加校验/下载/解包/入口）
- Test: `tests/test_ffmpeg_linux_download.py`（真值表四格 + 失败不抛）
- Modify: `i18n/zh_CN/LC_MESSAGES/zh_CN.po`、`i18n/en_US.json`、`i18n/en_GB.json`、`i18n/zh_TW.yaml`

**Interfaces:**
- Consumes: Task 2 的 `_asset_url` / `_linux_arch` / `_fetch_asset_digest` / `_asset_name`（签名见 Task 2 Produces）
- Produces: `install_ffmpeg_linux_native(dest_dir: str, arch: str | None = None, *, master_allowed: bool = False) -> bool`
  —— Task 4 唯一的接线点；**恒不抛、失败回 False**。

- [ ] **Step 1：写失败测试——真值表四格**

追加到 `tests/test_ffmpeg_linux_download.py`，并补四个 stdlib import（一行一个，isort 的 black profile 不接受
`import hashlib, io` 这种合写）：`import hashlib` / `import io` / `import subprocess` / `import tarfile`，
外加 `from pathlib import Path`（`_tar_xz` 与 `tmp_path` 是本 Task 的首个消费者）。替身口径：`requests`/`subprocess`
一律走 `types.SimpleNamespace(**vars(真身))` 覆盖 **fld 模块自己的名字**，判定分支走真实实现。

```python
def _tar_xz(members: dict[str, bytes]) -> bytes:
    # 必须是真 tar.xz：fld 走 tarfile.is_tarfile + extractall(filter="data")，多层 mock 锁不住实现换法。
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _digest_resp(digest: str | None) -> Any:
    # digest=None → 模拟 API 不可达（403 限流是本模块降级分支最常见的真实成因）。
    class _Resp:
        status_code = 200 if digest is not None else 403

        @staticmethod
        def json() -> dict[str, Any]:
            return {"assets": [{"name": fld._asset_name(LINUXARM64_URL), "digest": f"sha256:{digest}"}]}

    return _Resp()


class _FakeDownload:
    # 真身替身只覆盖 fld 模块自己的 requests 名字（绝不动 stdlib/第三方本体），
    # 且按 URL 前缀分流：api.github.com → digest 响应；github.com → 产物字节流。
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int = 1) -> Any:
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *a: Any) -> None:
        return None


def _stub_egress(monkeypatch: pytest.MonkeyPatch, dest_dir: str, *, digest: str | None, payload: bytes, rc: int = 0) -> None:
    class _Requests:
        exceptions = requests.exceptions
        RequestException = requests.RequestException

        @staticmethod
        def get(url: str, **kw: Any) -> Any:
            if url.startswith("https://api.github.com"):
                return _digest_resp(digest)
            return _FakeDownload(payload)

    monkeypatch.setattr(fld, "requests", _Requests())

    def _run(*args: Any, **kwargs: Any) -> Any:
        return types.SimpleNamespace(returncode=rc, stdout=b"", stderr=b"")

    proc = types.SimpleNamespace(**vars(subprocess))
    proc.run = _run
    monkeypatch.setattr(fld, "subprocess", proc)
    # 产品代码安装成功后会就地改写 os.environ["PATH"]；不收敛就会污染同会话后续用例，
    # 而 monkeypatch.setenv 的还原由 fixture 兜底（本仓禁 patch.dict(os.environ)）。
    monkeypatch.setenv("PATH", dest_dir)


class TestIntegrityTruthTable:
    def test_digest_matches_installs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(monkeypatch, str(tmp_path), digest=hashlib.sha256(payload).hexdigest(), payload=payload)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is True
        assert (tmp_path / "ffmpeg" / "ffmpeg").is_file()

    def test_installed_binary_must_actually_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 「装了但 -version 非零」必须算失败：返回值是整条链唯一的成功信号，不能被落盘动作本身满足。
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b"#!/bin/sh\n"})
        _stub_egress(monkeypatch, str(tmp_path), digest=hashlib.sha256(payload).hexdigest(), payload=payload, rc=1)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is False

    def test_digest_mismatch_refuses_and_deletes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b""})
        _stub_egress(monkeypatch, str(tmp_path), digest="a" * 64, payload=payload)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is False
        assert list(tmp_path.glob("*ffmpeg_linux_native_temp*")) == []
        assert not (tmp_path / "ffmpeg" / "ffmpeg").exists()

    def test_no_digest_and_switch_off_refuses(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b""})
        _stub_egress(monkeypatch, str(tmp_path), digest=None, payload=payload)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=False) is False
        # 默认关时**不得留下基准**：留了就等于偷偷启用了 TOFU。
        assert list(tmp_path.glob("_ffmpeg_linux*")) == []

    def test_no_digest_and_switch_on_records_tofu(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _tar_xz({"pkg/bin/ffmpeg": b"#!/bin/sh\n", "pkg/bin/ffprobe": b""})
        _stub_egress(monkeypatch, str(tmp_path), digest=None, payload=payload)
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is True
        baselines = list(tmp_path.glob("_ffmpeg_linux*.tar.xz.sha256"))
        assert len(baselines) == 1, f"首次记账必须留且只留一份基准：{baselines}"


class TestFailureIsNeverAnException:
    @pytest.mark.parametrize("boom", [OSError("disk full"), RuntimeError("unexpected")])
    def test_download_errors_return_false(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boom: Exception) -> None:
        def _raise(*args: Any, **kwargs: Any) -> Any:
            raise boom

        class _Requests:
            exceptions = requests.exceptions
            RequestException = requests.RequestException
            get = staticmethod(_raise)

        monkeypatch.setattr(fld, "requests", _Requests())
        assert fld.install_ffmpeg_linux_native(str(tmp_path), "linuxarm64", master_allowed=True) is False
```

**三条落地要点**：
1. `_digest_resp(None)` 返回 `status_code=403`，让「API 不可达 / 限流」真的走过 `_fetch_asset_digest`
   的非 200 分支，而不是靠 monkeypatch 直接伪造空串——那样锁不住判定链本身。
2. 桩一律覆盖 **fld 模块自己的 `requests` / `subprocess` 名字**（`types.SimpleNamespace(**vars(真身))` 浅拷贝），
   判序、真值表、基准记账、异常归一等分支全部走真实实现（AGENTS.md「测试不得自实现被测逻辑」）。
3. `TestFailureIsNeverAnException` 覆盖 MIN-2266⑤ 同族：OSError（磁盘满/无权限）与通用异常都不得穿出
   「失败一律 False、不抛」的契约，且半截归档必须被 `finally` 删掉。

- [ ] **Step 2：跑测试确认失败**

Run: `pytest tests/test_ffmpeg_linux_download.py -q -k "TruthTable or Failure"`
Expected: FAIL —— `AttributeError: module 'src.ffmpeg_linux_download' has no attribute 'install_ffmpeg_linux_native'`。

- [ ] **Step 3：写实现（追加到模块末尾）**

先补 Task 3 各消费者的 import（isort 会把它们排进同一 stdlib 段，`from pathlib import Path` 单独一段）：

```python
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
```

```python
def _baseline_path(dest_dir: Path, asset: str) -> Path:
    # 资产名进文件名：换标签即换基准，不会出现「新标签的产物被旧标签的基准判成篡改」。
    stem = asset.rsplit("/", 1)[-1].replace(".tar.xz", "")
    return dest_dir / f"{_HASH_PREFIX}.{stem}{_HASH_SUFFIX}"


def _prune_stale_baselines(dest_dir: Path, keep: Path) -> list[str]:
    removed: list[str] = []
    for stale in sorted(dest_dir.glob(f"{_HASH_PREFIX}*{_HASH_SUFFIX}")):
        if stale.name == keep.name:
            continue
        try:
            stale.unlink()
            removed.append(stale.name)
        except OSError as e:
            logger.warning(
                i18n.tr(
                    "修剪 Linux ffmpeg 陈旧 SHA256 基准失败（不影响本次安装）: {file} - {type_name}: {err}",
                    file=stale.name,
                    type_name=type(e).__name__,
                    err=e,
                )
            )
    return removed


def _verify_archive(archive: Path, official: str, dest_dir: Path, source_url: str, master_allowed: bool) -> bool:
    # 判序（形态 → 哈希 → 解压）与 ffmpeg_install.download_ffmpeg_official 同口径：
    # 三者校验的都是同一个产物文件，颠倒会让挑战页/错误页的哈希被当成基准写下去。
    if not tarfile.is_tarfile(str(archive)):
        logger.error(
            i18n.tr(
                "Linux ffmpeg 下载产物不是有效的 tar.xz 压缩包，拒绝校验与安装: {masked_url}",
                masked_url=_mask(source_url),
            )
        )
        return False
    current = utils.sha256_of_file(archive)
    if official:
        if current != official:
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 的 SHA256 与官方公布值不符（{expected} vs {actual}），"
                    "产物可能已被替换，已删除: {masked_url}",
                    expected=official,
                    actual=current,
                    masked_url=_mask(source_url),
                )
            )
            return False
        logger.debug(i18n.tr("Linux ffmpeg 已通过官方公布 SHA256 校验: {masked_url}", masked_url=_mask(source_url)))
        return True
    hash_file = _baseline_path(dest_dir, source_url)
    if not master_allowed:
        # 默认路径必须已校验：拿不到官方哈希就拒装，且**不留下**任何基准（留了就等于偷偷启用 TOFU）。
        logger.error(
            i18n.tr(
                "未取得 ffmpeg 官方公布的 SHA256，本次不安装未校验的二进制"
                "（如接受首次信任降级，请显式设 {env}=1）: {masked_url}",
                env="FFMPEG_MASTER_ALLOWED",
                masked_url=_mask(source_url),
            )
        )
        return False
    if hash_file.exists():
        try:
            expected = hash_file.read_text(encoding="ascii").strip().lower()
        except OSError as e:
            # SEV-2222 同口径：基准存在却读不出 = 本机唯一一道检查处于不可信状态，必须拒装。
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 的 SHA256 基准存在但读取失败，拒绝安装（请人工核对或删除 {file} 后重试）: "
                    "{type_name}: {err}",
                    file=str(hash_file),
                    type_name=type(e).__name__,
                    err=e,
                )
            )
            return False
        if expected != current:
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 的 TOFU 基准与本次产物不符（{expected} vs {actual}），已拒绝: {file}",
                    expected=expected,
                    actual=current,
                    file=str(hash_file),
                )
            )
            return False
        return True
    try:
        hash_file.write_text(current, encoding="ascii")
        removed = _prune_stale_baselines(dest_dir, hash_file)
        # 首次记账必须 warning（与 Windows master 侧同一档）：这是「本次没有可比对期望值」的唯一书面证据。
        logger.warning(
            i18n.tr(
                "未取得官方 SHA256，本次为 Linux ffmpeg 首次记录基准（TOFU，等同未校验安装）: "
                "{file} = {actual}{stale}",
                file=str(hash_file),
                actual=current,
                stale=("（已修剪陈旧基准 " + ", ".join(removed) + "）") if removed else "",
            )
        )
    except OSError as e:
        logger.warning(
            i18n.tr("写入 Linux ffmpeg SHA256 基准失败（不影响本次安装）: {type_name}: {err}", type_name=type(e).__name__, err=e)
        )
    return True


def _download(archive_url: str, archive: Path) -> bool:
    # 只有连接级/读取级异常才重试；4xx/5xx 直接失败（重试不会把 404 变成 200，只会白等退避）。
    last_err: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with requests.get(archive_url, stream=True, timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT)) as response:
                response.raise_for_status()
                with open(archive, "wb") as sink:
                    for chunk in response.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            sink.write(chunk)
            return True
        except requests.HTTPError as e:
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 下载返回 HTTP 错误: {type_name}: {err} - {masked_url}",
                    type_name=type(e).__name__,
                    err=e,
                    masked_url=_mask(archive_url),
                )
            )
            return False
        except (requests.RequestException, OSError) as e:
            last_err = e
            if archive.exists():
                try:
                    archive.unlink()
                except OSError:
                    pass
            logger.warning(
                i18n.tr(
                    "Linux ffmpeg 下载异常（第 {attempt}/{max} 次）: {type_name}: {err}",
                    attempt=attempt,
                    max=_MAX_RETRIES,
                    type_name=type(e).__name__,
                    err=e,
                )
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BACKOFF**attempt)
    logger.error(
        i18n.tr(
            "Linux ffmpeg 下载重试 {max} 次后仍失败: {type_name}: {err} - {masked_url}",
            max=_MAX_RETRIES,
            type_name=type(last_err).__name__ if last_err is not None else "RequestException",
            err=last_err,
            masked_url=_mask(archive_url),
        )
    )
    return False


def _install_binaries(archive: Path, ffmpeg_dir: Path) -> list[str]:
    # 递归按名取件（与 build_exe._extract_linux_ffmpeg_binaries 同一判据）：BtbN 顶层目录名带构建号，
    # 写死 <顶层>/bin/ 会让「解包成功但一件没拷」重新变成一行 warning。
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    with tempfile.TemporaryDirectory(dir=ffmpeg_dir.parent) as tmp:
        with tarfile.open(archive, "r:xz") as tf:
            # MI-26 同源：显式传 filter，不依赖解释器默认值（防低版本回归出路径穿越）。
            tf.extractall(tmp, filter="data")
        root = Path(tmp)
        for binary in ("ffmpeg", "ffprobe"):
            found = next((p for p in root.rglob(binary) if p.is_file()), None)
            if found is None:
                missing.append(binary)
                continue
            target = ffmpeg_dir / binary
            shutil.copy2(found, target)
            # Python 的 tar 解包按成员 mode 落位，但归档外属性在部分构建里是 0o644；
            # 执行位必须显式补回，否则安装「成功」了却一跑就 PermissionError。
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return missing


def install_ffmpeg_linux_native(dest_dir: str, arch: str | None = None, *, master_allowed: bool = False) -> bool:
    # 契约与 install_ffmpeg_windows 一致：失败一律 False，绝不抛出穿出 install_ffmpeg_linux()。
    resolved = arch or _linux_arch()
    url = _asset_url(resolved)
    dest = Path(dest_dir)
    ffmpeg_dir = dest / "ffmpeg"
    archive = dest / "ffmpeg_linux_native_temp.tar.xz"
    logger.debug(
        i18n.tr("Linux 包管理器未提供 ffmpeg，改试官方月末构建直下: {arch} - {masked_url}", arch=resolved, masked_url=_mask(url))
    )
    try:
        official = _fetch_asset_digest(url)
        if not _download(url, archive):
            return False
        if not _verify_archive(archive, official, dest, url, master_allowed):
            return False
        missing = _install_binaries(archive, ffmpeg_dir)
        if missing:
            logger.error(
                i18n.tr(
                    "Linux ffmpeg 归档里找不到 {missing}，本次安装终止: {masked_url}",
                    missing="、".join(missing),
                    masked_url=_mask(url),
                )
            )
            return False
    except Exception as e:
        logger.error(
            i18n.tr(
                "Linux ffmpeg 直下安装异常（已归一为失败，不向上抛）: {type_name}: {err}",
                type_name=type(e).__name__,
                err=e,
            )
        )
        return False
    finally:
        if archive.exists():
            try:
                archive.unlink()
            except OSError:
                pass

    os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + (os.environ.get("PATH") or "")
    try:
        probe = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=30)
    except Exception as e:
        logger.error(
            i18n.tr(
                "Linux ffmpeg 安装后验证失败: {type_name}: {err} - {dest}",
                type_name=type(e).__name__,
                err=e,
                dest=str(ffmpeg_dir),
            )
        )
        return False
    if probe.returncode != 0:
        logger.error(
            i18n.tr("Linux ffmpeg 安装后 -version 返回非零（rc={rc}），判为安装失败: {dest}", rc=probe.returncode, dest=str(ffmpeg_dir))
        )
        return False
    logger.debug(
        i18n.tr("Linux ffmpeg ({arch}) 已安装并验证: {dest}", arch=resolved, dest=str(ffmpeg_dir))
    )
    return True
```

- [ ] **Step 4：跑测试确认通过**

Run: `pytest tests/test_ffmpeg_linux_download.py -q`
Expected: PASS，**0 warnings**（本仓 warnings summary 为空是硬口径；出现 `RuntimeWarning: coroutine` 一律修根因）。

- [ ] **Step 5：新模板补进四语目录并重编**

`python scripts/extract_i18n_strings.py` 会在「== 缺失 ==」段列出本模块全部新模板（`i18n.tr` 首参是常量串，
提取器看得见——不在 AGENTS.md 的三个盲区里）。逐条补进：
1. `i18n/zh_CN/LC_MESSAGES/zh_CN.po`：`msgid` = 模板原文，`msgstr` = 同文（简中即源文）。
2. `i18n/en_US.json` 与 `i18n/en_GB.json`：英文译文（两文件内容本次逐键相同，与既有惯例一致）。
   例：`"未取得 ffmpeg 官方公布的 SHA256，本次不安装未校验的二进制（如接受首次信任降级，请显式设 {env}=1）: {masked_url}"`
   → `"Could not obtain the officially published SHA256 for ffmpeg; refusing to install an unverified binary "
   "(set {env}=1 to opt into the trust-on-first-use fallback): {masked_url}"`。
3. `i18n/zh_TW.yaml`：繁体检落点同键。
4. `python scripts/compile_po.py` 重编 `.mo`（测试强制 .po/.mo 字节级同步）。

Run: `PYTHONUTF8=1 python scripts/compile_po.py --check && pytest tests/test_i18n_migration.py -q`
Expected: 均 PASS。若四目录键集不等，提取器会打 `[不一致]` 行、`test_runtime_templates_covered_by_catalog` 变红。

- [ ] **Step 6：变异验证真值表**

按 AGENTS.md「当轮还原」手法：内存备份 `src/ffmpeg_linux_download.py` 字节 → 把 `_verify_archive` 的
`if current != official:` 改为 `if False:`（加标记 `# MUTATION-S3-DIGESTGATE`）→
`pytest tests/test_ffmpeg_linux_download.py -q` 必须**至少一格转红**（mismatch 那格）→
按字节还原 → 断言 `read_bytes() == 原字节` → 复跑 PASS。

- [ ] **Step 7：记录三元组（不提交）**

---

## Task 4: 接线 `install_ffmpeg_linux()` 并登记下载源

**Files:**
- Modify: `src/ffmpeg_install.py`（模块级 import + `install_ffmpeg_linux()` 末尾）
- Modify: `tests/test_ffmpeg_install.py:77`（`DOWNLOAD_MODULES`）、`:885-912`（`DOWNLOAD_SOURCES`）
- Test: `tests/test_ffmpeg_install.py`（调用顺序行为锁）

**Interfaces:**
- Consumes: Task 3 的 `install_ffmpeg_linux_native(dest_dir, arch=None, *, master_allowed=False) -> bool`
- Produces: 无新对外接口（`install_ffmpeg_linux()` 返回值语义不变：成功 True / 失败 False）

- [ ] **Step 1：写失败的行为锁（顺序，不是文本正则）**

追加到 `tests/test_ffmpeg_install.py`（复用文件里既有的 `_proc_shim(codes, calls)`——
它按**完整命令元组**查退出码、查不到取默认 0，`calls` 记录顺序；**不要**新造一个平行 helper）。
按 M-26：钉「谁被调用、带不带凭据」这类行为，不钉变量名字面量。

```python
class TestInstallFfmpegLinuxNativeFallback:
    def test_package_manager_success_skips_native_download(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        # yum 一步返回 0 → _proc_shim 默认码即 0，无需枚举；断言看的是「有没有第二次调用」。
        monkeypatch.setattr(ffmpeg_install, "subprocess", _proc_shim({}, calls))
        monkeypatch.setattr(
            ffmpeg_install,
            "install_ffmpeg_linux_native",
            lambda *args, **kwargs: pytest.fail("包管理器已成功，不得触达直下路径"),
        )
        assert ffmpeg_install.install_ffmpeg_linux() is True
        assert calls == ["yum install -y ffmpeg"]

    def test_both_package_managers_missing_falls_back_exactly_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[dict[str, Any]] = []
        calls: list[str] = []

        def _native(dest_dir: str, arch: str | None = None, *, master_allowed: bool = False) -> bool:
            seen.append({"dest_dir": dest_dir, "arch": arch, "master_allowed": master_allowed})
            return True

        class _Result:
            returncode = 0
            stdout = b"ffmpeg version n7.1"
            stderr = b""

        def fake_run(cmd: list[str], *args: object, **kwargs: object) -> _Result:
            calls.append(" ".join(cmd))
            # 既无 yum 也无 apt（轻量发行版/容器的真实形态）：两条包管理器路径都以 FileNotFoundError 收场。
            raise FileNotFoundError(cmd[0])

        shim = types.SimpleNamespace(**vars(subprocess))
        shim.run = fake_run
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_linux_native", _native)
        monkeypatch.delenv("FFMPEG_MASTER_ALLOWED", raising=False)
        assert ffmpeg_install.install_ffmpeg_linux() is True
        assert calls == ["yum install -y ffmpeg", "apt update"]
        assert len(seen) == 1, f"直下兜底必须恰好触达一次：{seen}"
        assert seen[0]["dest_dir"] == ffmpeg_install.execute_dir
        # 开关默认关：master_allowed 必须原样是 False，而不是新模块自己去读环境变量。
        assert seen[0]["master_allowed"] is False

    def test_native_failure_still_ends_with_manual_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        # apt update 也要给非零，否则 _proc_shim 的默认 0 会让它「装成功」而永远走不到兜底。
        shim = _proc_shim({("yum", "install", "-y", "ffmpeg"): 1, ("apt", "update"): 1}, calls)
        monkeypatch.setattr(ffmpeg_install, "subprocess", shim)
        monkeypatch.setattr(ffmpeg_install, "install_ffmpeg_linux_native", lambda *args, **kwargs: False)
        assert ffmpeg_install.install_ffmpeg_linux() is False
```

**另有一条加进既有类**：把下面的方法**插入既有的 `TestDownloadSourceWhitelist` 类体内**（缩进 4 格；
**不要**另开一个同名 class——pytest 会收集两个同名类，id 冲突且看不出哪一红归谁）。
它锁 Step 3 的白名单登记，`DOWNLOAD_SOURCES` / `DOWNLOAD_MODULES` 都是该文件的模块级常量：

```python
    def test_api_github_com_is_registered_as_official_hash(self) -> None:
        assert DOWNLOAD_SOURCES["api.github.com"][0] == "官方哈希"
        assert DOWNLOAD_SOURCES["api.github.com"][1].strip(), "白名单要写清「为什么这一档可接受」"
        assert "src.ffmpeg_linux_download" in DOWNLOAD_MODULES
        # TOFU 源集合不得因本次改动扩大或缩小：github.com 的 master-latest 路径仍是默认关闭的 TOFU。
        assert {h for h, (m, _n) in DOWNLOAD_SOURCES.items() if m == "TOFU"} == {"github.com", "fyhub.cn"}
```

**为什么不用文件里另一条 `_fake_subprocess(...)`**：它是某个测试类的**绑定方法**（`self` 起步、返回
`(shim, calls)`），跨类借用要么继承要么复制，而本 Task 的两个用例需要的是「`run` 直接抛
FileNotFoundError」——`_proc_shim` 只会按元组返回码、不会抛。按上面内联 `fake_run` 写，
不跨类借 helper，也不给 `_proc_shim` 加参数（那会波及它的 30+ 既有调用点）。

- [ ] **Step 2：跑测试确认失败**

Run: `pytest tests/test_ffmpeg_install.py -q -k "NativeFallback or api_github"`
Expected: 三条 fallback 用例红在 `AttributeError: <module 'src.ffmpeg_install' ...> has no attribute
'install_ffmpeg_linux_native'`（monkeypatch 的目标不存在时即报错，正是「生产还没接线」的证据）；
白名单那条红在 `KeyError: 'api.github.com'`。

- [ ] **Step 3：登记两处白名单**

`DOWNLOAD_MODULES` 追加 `"src.ffmpeg_linux_download"`；`DOWNLOAD_SOURCES` 追加（`github.com` 条目**保持 TOFU 不动**
——它描述的是 master-latest 那条路；若把 github.com 改成「官方哈希」，`test_tofu_sources_are_all_gated_off_by_default`
的 TOFU 集合会缩成 `{"fyhub.cn"}`，而 master 那条 TOFU 路径还在，等于**假绿**）：

```python
    "api.github.com": (
        "官方哈希",
        "Linux 运行期直下的期望值来源（release asset 的 digest 字段，与产物下载域异服务）；"
        "URL 里的月末 autobuild 标签不可变，故期望值不随上游重发漂移",
    ),
```

- [ ] **Step 4：接线**

`src/ffmpeg_install.py` 模块级 import 段（第 34 行 `from src.ffmpeg_master_download import download_ffmpeg_master` 下方）：

```python
# Linux 原生 ffmpeg 直下（类别② 的 Linux 分支）。master_allowed 由本模块传入而非该模块自读环境变量：
# ffmpeg_install → ffmpeg_linux_download 已有一条 import 边，反向 import _master_source_allowed() 即成环。
from src.ffmpeg_linux_download import install_ffmpeg_linux_native
```

`install_ffmpeg_linux()` 在 apt 分支的 `except Exception` 之后、
`logger.error("Manual installation of ffmpeg is required. ...")` **之前**插入：

```python
    if install_ffmpeg_linux_native(execute_dir, master_allowed=_master_source_allowed()):
        return True
```

顺序判据（写进注释）：包管理器优先，因为 apt/yum 天然给原生 arm64 且带发行版自己的签名链；
直下只在「拿不到包管理器」时兜底，**不得**颠倒。

- [ ] **Step 5：跑测试确认通过 + 复核发布侧白名单未被牵连**

Run: `pytest tests/test_ffmpeg_install.py tests/test_ffmpeg_linux_download.py -q`
Expected: 双文件 PASS + 0 warnings。特别确认 `TestDownloadSourceWhitelist` 四条全绿——
`test_scan_actually_sees_the_sources_it_claims` 要求「持有白名单宿主的模块集合 == `DOWNLOAD_MODULES` 文件名集合」，
新模块若没被 `DOWNLOAD_MODULES` 收编就会在此红（这正是 AGENTS.md #10 的三处同改机制）。

Run: `pytest tests/test_build_exe.py -q`
Expected: PASS。发布侧的 `_ALLOWED_HOSTS`（`tests/test_build_exe.py:44`）**保持不动**——
它是 `build_exe._FFMPEG_DOWNLOAD_URLS` 的主机锁，而本次发布链一行未改；
`api.github.com` 只属于运行期那张 `DOWNLOAD_SOURCES`（T-7 的全部含义就是「两张锁不得混用」）。

- [ ] **Step 6：记录三元组（不提交）**

---

## Task 5: 两处 URL 副本的一致性锁

**Files:**
- Test: `tests/test_ffmpeg_linux_download.py`（追加 `TestUrlParityWithBuildExe`）

**Interfaces:**
- Consumes: `fld._LINUX_FFMPEG_URLS`（Task 2）、`build_exe._FFMPEG_DOWNLOAD_URLS`（既有）
- Produces: 无代码接口；本 Task 是防漂移闸口。

- [ ] **Step 1：写测试**

追加到 `tests/test_ffmpeg_linux_download.py`，并在 import 段补
`from build_exe import _FFMPEG_DOWNLOAD_URLS as BUILD_EXE_FFMPEG_URLS`（本 Task 的 parity 锁是它的首个消费者；
根目录 `build_exe` 可被测试直接 import，先例 `tests/test_build_exe.py`）：

```python
class TestUrlParityWithBuildExe:
    def test_linux_urls_are_identical_to_the_release_table(self) -> None:
        # 两份物理副本：build_exe（发布期）与本模块（运行期）。冻结 exe 里 import 不到根目录 build 脚本，
        # 所以副本不可避免，那就不让它漂移——换标签必须同批改两处，本条锁就是那只手。
        assert fld._LINUX_FFMPEG_URLS["linux64"] == BUILD_EXE_FFMPEG_URLS["linux-x64"]
        assert fld._LINUX_FFMPEG_URLS["linuxarm64"] == BUILD_EXE_FFMPEG_URLS["linux-arm64"]

    def test_runtime_digest_channel_agrees_with_the_release_pin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 离线复现「API digest 通道 == 发布期人工核过的钉定值」这一实测结论：
        # 桩掉 requests 返回 build_exe 的 linuxarm64 钉定值，走真实 _fetch_asset_digest 判定链。
        import build_exe

        pinned = build_exe._PINNED_RUNTIME_SHA256["linux-arm64"]["ffmpeg"]

        class _Resp:
            status_code = 200

            @staticmethod
            def json() -> dict[str, Any]:
                return {"assets": [{"name": fld._asset_name(LINUXARM64_URL), "digest": f"sha256:{pinned}"}]}

        class _Requests:
            exceptions = requests.exceptions
            RequestException = requests.RequestException

            @staticmethod
            def get(*a: Any, **kw: Any) -> Any:
                return _Resp()

        monkeypatch.setattr(fld, "requests", _Requests())
        assert fld._fetch_asset_digest(LINUXARM64_URL) == pinned

    def test_malformed_digest_shape_is_rejected(self) -> None:
        # 形状关（同 build_exe._is_pinned）：截断/前缀残留/大写一律算「取不到」，不得放行。
        want = fld._asset_name(LINUXARM64_URL)
        for bad in ("", "e2dd447c", "sha256:" + "e" * 63, "E" * 64, "x" * 64):
            assert fld._digest_from_assets([{"name": want, "digest": bad}], want) == ""
        assert fld._digest_from_assets([{"name": "other.tar.xz", "digest": "e" * 64}], want) == ""
        assert fld._digest_from_assets([{"name": want, "digest": "sha256:" + "e" * 64}], want) == "e" * 64
```

- [ ] **Step 2：跑测试确认失败**

Run: `pytest tests/test_ffmpeg_linux_download.py -q -k "Parity or Malformed"`
Expected: 前两条 PASS（值本应一致；若红说明 Task 2 的 URL 抄错了），
第三条 FAIL —— `AttributeError: module 'src.ffmpeg_linux_download' has no attribute '_digest_from_assets'`。

- [ ] **Step 3：把 digest 解析抽成可测函数（两个实参，不读宿主架构）**

```python
def _digest_from_assets(assets: list[Any], want_name: str) -> str:
    # 从 release 的 assets 列表里取本资产的 digest；形状非法（截断/大写/未剥净前缀）与「没有该项」同级回 ""。
    # want_name 必须是实参，不得在本函数里回头调 _asset_name(_asset_url(_linux_arch()))：
    # 那会让这个纯判定函数依赖宿主架构，而同文件的分流用例正靠 monkeypatch machine 跑——结果会随机器漂。
    for asset in assets:
        if not isinstance(asset, dict) or str(asset.get("name") or "") != want_name:
            continue
        digest = str(asset.get("digest") or "").strip().lower()
        if digest.startswith("sha256:"):
            digest = digest.partition(":")[2]
        return digest if _SHA256_PATTERN.fullmatch(digest) else ""
    return ""
```

把 Task 2 里 `_fetch_asset_digest` 的内层 for 循环整体替换为这一行调用（判定逻辑只留一处）：

```python
    return _digest_from_assets(payload.get("assets") or [], _asset_name(asset_url))
```

- [ ] **Step 4：跑测试确认通过**

Run: `pytest tests/test_ffmpeg_linux_download.py -q`
Expected: 全 PASS。

- [ ] **Step 5：变异验证**

内存改写 `build_exe._FFMPEG_DOWNLOAD_URLS["linux-arm64"]`（在**测试进程内**用
`monkeypatch.setattr(build_exe, "_FFMPEG_DOWNLOAD_URLS", {..., "linux-arm64": "...different-tag..."})`）
→ parity 测试必须转红；不落盘即无需还原（铁律 1：优先不落盘）。

- [ ] **Step 6：一次真实取数核对（只读，不落盘）**

Run:
```bash
python - <<'PY'
import build_exe, src.ffmpeg_linux_download as fld
d = fld._fetch_asset_digest(fld._LINUX_FFMPEG_URLS["linuxarm64"])
p = build_exe._PINNED_RUNTIME_SHA256["linux-arm64"]["ffmpeg"]
print("api digest == release pin:", d == p, d)
PY
```
Expected: `True` 且打印 64 位十六进制。
（2026-10-02 已实测：linux64 `182c1b50…`、linuxarm64 `e2dd447c…` 与钉定值逐字相等，
体积 126,600,656 / 108,761,296 B 与 `build_exe.py:997` 注释读数一致。）
无外网时在回复里写明「未执行 + 原因」，不得当作已通过。

- [ ] **Step 7：记录三元组（不提交）**

---

## Task 6: GHCR 多架构镜像发布工作流

**Files:**
- Create: `.github/workflows/docker-publish.yml`
- Test: `tests/test_docker_publish_workflow.py`

**Interfaces:**
- Consumes: `Dockerfile`（不动）、`pyproject.toml` 的 version
- Produces: `ghcr.io/<owner>/douyin-live-recorder` 的 `linux/amd64,linux/arm64` 清单，tag = `vX.Y.Z` + `latest`

- [ ] **Step 1：写结构锁（先失败）**

```python
# tests/test_docker_publish_workflow.py —— .github/workflows/docker-publish.yml 的结构锁。
#
# 为什么要有：多架构发布链的正确性全靠几个「看起来像细节」的约束（只在 tag 上推 latest、
#   两个构建 job 的 runner 与 --platform 必须一一对应、凭据只能是自动 GITHUB_TOKEN），
#   而工作流文件不在任何门禁的判据面里——改坏它不会有任何测试红，只会在下一次发版时炸。
# YAML 1.1 陷阱：`on:` 会被 PyYAML 解析成布尔 True 键，本文件按 data[True] 取值，
#   写代码的人容易在这里写下「KeyError: 'on'」然后误判成「工作流没触发条件」。

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "docker-publish.yml"


@pytest.fixture(scope="module")
def data() -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")))


def test_only_tag_push_can_publish_latest(data: dict[str, Any]) -> None:
    triggers = data[True]
    assert set(triggers) == {"push"}, f"发布链触发面只能有 tag push：{sorted(triggers)}"
    assert triggers["push"]["tags"] == ["v*"]


def test_arch_jobs_run_on_matching_native_runners(data: dict[str, Any]) -> None:
    jobs = data["jobs"]
    expected = {
        "docker-build-amd64": ("ubuntu-latest", "linux/amd64"),
        "docker-build-arm64": ("ubuntu-24.04-arm", "linux/arm64"),
    }
    for name, (runner, image_platform) in expected.items():
        job = jobs[name]
        assert job["runs-on"] == runner, f"{name} 必须跑在原生 {runner} 上，不得用 QEMU 交叉构建"
        build = next(s for s in job["steps"] if s.get("uses", "").startswith("docker/build-push-action"))
        assert build["with"]["platform"] == image_platform
        assert build["with"]["push"] is True
        # merge job 取值靠这两个 id：任一处改名会让 needs.*.outputs.digest 静默变空串。
        assert build["id"] == "build"
        assert job["outputs"]["digest"] == "${{ steps.build.outputs.digest }}"


def test_manifest_merge_needs_both_arch_jobs(data: dict[str, Any]) -> None:
    merge = data["jobs"]["docker-manifest"]
    assert set(merge["needs"]) == {"prepare", "docker-build-amd64", "docker-build-arm64"}
    command = next(s["run"] for s in merge["steps"] if "imagetools create" in str(s.get("run", "")))
    for ref in ("needs.docker-build-amd64.outputs.digest", "needs.docker-build-arm64.outputs.digest"):
        assert ref in command, f"合成清单必须按 digest 引用两个架构层，缺 {ref}"
    assert ":latest" in command and ":v${{ needs.prepare.outputs.version }}" in command


def test_only_the_auto_github_token_is_referenced() -> None:
    # 发布链的凭据只能是被自动注入的那一把：出现任何其它 secrets.* 就说明有人塞了手工密钥。
    # 断言形态必须是「集合相等」而不是「不含 secrets.」——后者会把 GITHUB_TOKEN 一起禁掉，
    # 而 login-action 没有 password 根本登不上 GHCR。
    text = WORKFLOW.read_text(encoding="utf-8")
    refs = set(re.findall(r"secrets\.[A-Za-z0-9_]+", text))
    assert refs == {"secrets.GITHUB_TOKEN"}, f"发布链引入了非自动凭据：{sorted(refs)}"


def test_release_style_concurrency(data: dict[str, Any]) -> None:
    assert data["concurrency"]["cancel-in-progress"] is False


def test_no_in_job_package_install_steps() -> None:
    # 依赖安装全部发生在 Dockerfile 里（镜像层），job 内不得再出现 apt/pip/choco 直装步骤：
    # 那既绕过 .github/actions/retry 的统一重试口径，又会让「镜像里有什么」与「job 里装了什么」分家。
    text = WORKFLOW.read_text(encoding="utf-8")
    for anchor in ("apt-get install", "pip install", "choco install", "brew install"):
        assert anchor not in text, f"job 内出现 {anchor}：安装链应只在 Dockerfile"


def test_release_style_concurrency(data: dict[str, Any]) -> None:
    assert data["concurrency"]["cancel-in-progress"] is False
```

Run: `pytest tests/test_docker_publish_workflow.py -q`
Expected: FAIL —— `FileNotFoundError`（工作流尚不存在）。

- [ ] **Step 2：写工作流**

新建 `.github/workflows/docker-publish.yml`（要点全部来自规格 §5.1）：

```yaml
# =============================================================================
# Docker Publish —— GHCR 多架构镜像发布（linux/amd64 + linux/arm64）
# -----------------------------------------------------------------------------
# 触发：仅 push tag `v*`。latest 只允许由**不可变的 tag 推**出来，
#   不留 workflow_dispatch 覆盖 latest 的口子（那等于把发布物变成可反复改写的别名）。
# 凭据：自动注入的 GITHUB_TOKEN + permissions: packages: write，不引入任何**手工配置**的 secret。
# 构建：两个原生 runner 各出一层，再由 merge job 用 imagetools 合成清单；
#   不走 QEMU——本镜像构建期要 apt 装 ffmpeg/nodejs + pip 装全量依赖，
#   模拟 aarch64 整层重活（trivy.yml 已注明完整 docker build 是全仓最重的一次外网动作）。
# 第三方动作一律浮动大版本标签：本工作流的触发源是维护者推的 tag（可信输入），
#   与 build-release.yml 用 softprops/action-gh-release@v3 同一条 MIN-17 区分线；
#   trivy-action 的 SHA 钉定先例属「cron 无人值守 + 外部可读输入」那一侧。
# 结构锁：tests/test_docker_publish_workflow.py。
# =============================================================================

name: Docker Publish

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read

concurrency:
  group: docker-publish-${{ github.ref }}
  cancel-in-progress: false

env:
  REGISTRY: ghcr.io

jobs:
  prepare:
    name: Prepare (image name & tags)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    outputs:
      image: ${{ steps.names.outputs.image }}
      version: ${{ steps.names.outputs.version }}
    steps:
      - name: Extract image name and version
        id: names
        shell: bash
        run: |
          set -euo pipefail
          # 镜像名用 GITHUB_REPOSITORY_OWNER，绝不用仓库名：fork 推自己的命名空间，不会撞上游。
          IMAGE="${REGISTRY}/$(echo "${GITHUB_REPOSITORY_OWNER}" | tr '[:upper:]' '[:lower:]')/douyin-live-recorder"
          if [ "${GITHUB_REF_TYPE}" = "tag" ]; then
            VERSION="${GITHUB_REF_NAME#v}"
          else
            echo "::error::本工作流只应由 tag 触发（GITHUB_REF_TYPE=${GITHUB_REF_TYPE}）"
            exit 1
          fi
          echo "image=${IMAGE}" >> "$GITHUB_OUTPUT"
          echo "version=${VERSION}" >> "$GITHUB_OUTPUT"

  docker-build-amd64:
    name: Image (linux/amd64)
    needs: prepare
    runs-on: ubuntu-latest
    timeout-minutes: 90
    permissions:
      contents: read
      packages: write
    # digest 必须显式提升成 **job 级 output**：漏声明时 needs.*.outputs.digest 拿到空串，
    # imagetools create 会报无效引用（而 build 本身全绿，最难归因的一种红）。
    outputs:
      digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v7
      - uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push (amd64)
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64
          push: true
          provenance: false
          # 只推分架构的临时 tag；真正的对外 tag 由 merge job 在两个 digest 都齐了之后合成。
          tags: ${{ needs.prepare.outputs.image }}:v${{ needs.prepare.outputs.version }}-amd64
          build-args: |
            APP_VERSION=${{ needs.prepare.outputs.version }}

  docker-build-arm64:
    name: Image (linux/arm64)
    needs: prepare
    runs-on: ubuntu-24.04-arm
    timeout-minutes: 90
    permissions:
      contents: read
      packages: write
    outputs:
      digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v7
      - uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push (arm64)
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/arm64
          push: true
          provenance: false
          tags: ${{ needs.prepare.outputs.image }}:v${{ needs.prepare.outputs.version }}-arm64
          build-args: |
            APP_VERSION=${{ needs.prepare.outputs.version }}

  docker-manifest:
    name: Merge manifest (amd64 + arm64)
    needs: [prepare, docker-build-amd64, docker-build-arm64]
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: read
      packages: write
    steps:
      - uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Create and push multi-arch manifest
        # 用 buildx 的原生命令而不是第三个第三方动作：语义完全等价（imagetools create 就是
        # docker/buildx-action 内部跑的那条），少一个依赖也就少一处 ref 需要人工核实。
        # 引用两个构建 job 的 manifest **digest** 而不是分架构临时 tag 名：digest 不可变，
        # 临时 tag 之后被清理也不会让这份清单失去意义。
        run: |
          set -euo pipefail
          IMAGE="${{ needs.prepare.outputs.image }}"
          VERSION="${{ needs.prepare.outputs.version }}"
          docker buildx imagetools create \
            -t "${IMAGE}:v${VERSION}" \
            -t "${IMAGE}:latest" \
            "${IMAGE}@${{ needs.docker-build-amd64.outputs.digest }}" \
            "${IMAGE}@${{ needs.docker-build-arm64.outputs.digest }}"
```

- [ ] **Step 3：跑结构锁**

Run: `pytest tests/test_docker_publish_workflow.py -q`
Expected: 全 PASS。六条锁各自的失败形态：漏 `outputs:` → 第一条 arch 锁红；
把 arm64 改成 `ubuntu-latest` → runner 锁红；加 `workflow_dispatch` → 触发面锁红；
塞进 `secrets.DOCKERHUB_TOKEN` → 凭据锁红。

- [ ] **Step 4：YAML 可解析性与动作 ref 复核**

Run:
```bash
python -c "import yaml,pathlib;d=yaml.safe_load(pathlib.Path('.github/workflows/docker-publish.yml').read_text(encoding='utf-8'));print(sorted(d['jobs']))"
```
Expected: 打印 4 个 job 名，`on` 键以 True 呈现（YAML 1.1 行为，不是 bug）。

- [ ] **Step 5：记录三元组（不提交）**

**本 Task 明确不做的两件事**（写进回复，别当已完成）：
- 不把 `docker-compose.yaml` 的 `image: ihmily/douyin-live-recorder:latest` 改为 ghcr（规格 §二.4 已定）。
- 不设置 GHCR 包可见性：Actions 不会代为放开，需用户在 Package settings 里设 public。

---

## Task 7: 文档同源与收尾门禁

**Files:**
- Modify: `AGENTS.md`（3 条）、`CODE_WIKI.md`、`CODE_WIKI_EN.md`、`README.md`、`README_EN.md`
- Test: 无（纯文档，DoD 豁免第 2/3 步）

- [ ] **Step 1：AGENTS.md 写回长期约定**

三处，逐条：
1. 「CI / workflow 约定」的发布矩阵条目：把「三平台」相关表述改为四平台，并加一句
   **runner 标签↔运行时键映射的唯一登记点是 `scripts/check_runtime_pins.py::RUNNER_TO_RUNTIME_KEY`**，
   新增 runner 必须同批登记，否则 `--strict` 在 prepare 即断。
2. 「已知坑 · 构建产物」新增一条：
   **运行期 Linux 直下的 URL 与 `build_exe._FFMPEG_DOWNLOAD_URLS` 是两份物理副本**（冻结 exe import 不到
   根目录 build 脚本），一致性由 `tests/test_ffmpeg_linux_download.py::TestUrlParityWithBuildExe` 机检；
   换月末标签必须同批改两处 + 重取钉定值。同时写明
   **`api.github.com` 的 digest 属「同源一致性校验」而非来源认证**，
   与产物**异服务**（API 域 ↔ 对象存储域）但**同平台**，日志与注释不得写成「已认证来源」。
3. 「CI / workflow 约定」新增一条：**多架构镜像只走原生双 runner + imagetools 合成，禁止单 job QEMU 交叉**
   （构建期含 apt/pip 全量安装，模拟整层）；GHCR 凭据固定为自动 `GITHUB_TOKEN`，
   发布链**不得**引用任何其它 `secrets.*`；`latest` 只能由 `v*` tag 推出。

- [ ] **Step 2：CODE_WIKI.md / CODE_WIKI_EN.md 更新日志**

中英各追加一条（DoD 第 4 步），内容含：S1 四平台矩阵、S2 新模块与其完整性真值表、S3 GHCR 多架构，
以及第 3 步里那次 `api.github.com` 实测读数（linux64 `182c1b50…` / linuxarm64 `e2dd447c…`，
体积 126,600,656 / 108,761,296 B，读数时刻 2026-10-02）。

- [ ] **Step 3：README 产物与镜像口径**

`README.md` / `README_EN.md`：下载产物清单加 `linux-aarch64`（注明 `platform.machine()` 的实际取值形态）；
Docker 章节加 `docker pull ghcr.io/<owner>/douyin-live-recorder:latest`，并保留原 compose 说明不动。

- [ ] **Step 4：孪生副本核对（AGENTS.md 硬要求，提交说明要写结论）**

Run: `grep -n "install_ffmpeg\|download_ffmpeg" scripts/douyin_live_recorder_standalone.py`
Expected: 无命中（2026-10-02 已核对）→ 结论写「已核对 / 刻意不回灌：该副本不含 ffmpeg 安装链，
只有 `should_prepend_bundled_ffmpeg_dir` 的同名 PATH 让位判据，本次未改其语义」。若命中变了，本次改动回灌。

- [ ] **Step 5：全量门禁（DoD 第 1 步，必须在最后一次编辑之后）**

Run: `python scripts/run_gates.py`
Expected: rc=0（含 `mypy` 无参 + `mypy --platform linux` + `mypy --platform win32` 三跑、
`check_annotations.py`、`check_runtime_pins.py`、`check_skill_agents_consistency.py` 等）。

Run: `pytest -q` 与 `python scripts/check_coverage.py`
Expected: pytest 0 警告全绿；覆盖率对**新模块 `src/ffmpeg_linux_download.py`** 达标
（新文件通常不在 `MODULE_THRESHOLDS` 里，确认走默认阈值分支而非「查不到按失败处理」那条红）。

Run: `basedpyright`（不传路径，本地补充门禁）
Expected: 0 error / 0 warning。新模块里 `payload.get("assets")` 之类 Any 泄漏是高危点，
必要时用 `cast` 收窄（禁三参 `getattr`，AGENTS.md「Any 泄漏」条目）。

- [ ] **Step 6：收尾清理与日志（DoD 第 5/6 步）**

- 确认仓库内无本计划产生的临时脚本（本计划全程用 `python - <<'PY'` 内联，未落盘）；
  `git status --short` 只应多出：新模块、新测试 ×2、工作流、被改的工作流/脚本/测试/i18n/文档，
  **不应**出现 `MUTATION-` 标记残留（`grep -rn "MUTATION-" --include=*.py .` 只允许命中
  `tests/test_test_hygiene.py` 的守卫内刻意拆写字面量与 `AGENTS.md`/`.workbuddy` 的记述）。
- `.workbuddy/memory/2026-10-02.md` 追加一条：三段落点 + 门禁读数 + **未执行项**（arm64 真机录制、
  GHCR 首次推送、arm runner 配额）；可复用经验写进 `docs/agent-reference/session-learnings.md`。

---

## 验收对照（规格 → 计划，自检用）

| 规格条目 | 落点 |
| --- | --- |
| S1 矩阵 + `if:` 家族判定 + 8 zip + runner 映射 | Task 1 Step 2-5 |
| S1 注释同步（含 `build_exe.py` 措辞） | Task 1 Step 6 |
| S2 真值表四格 / 架构分流 / URL 反解 / digest 形状关 | Task 2 + Task 3 Step 1-4 |
| S2 不引入循环依赖（master_allowed 传参） | Task 4 Step 4 |
| S2 失败不抛契约 | Task 3 Step 1（`TestFailureIsNeverAnException`） |
| S2 TOFU 默认关 + 基准读不出即拒装 | Task 3 Step 3（`_verify_archive`）+ Step 6 变异 |
| 下载源三处同改 | Task 4 Step 3 |
| T-5 两处副本一致性 + 活体取数核对 | Task 5 |
| S3 多架构 GHCR（原生双建 + imagetools） | Task 6 |
| compose 镜像名不改 / 可见性交回用户 | Task 6 Step 5 |
| i18n 四目录 + .mo | Task 3 Step 5 |
| AGENTS.md / CODE_WIKI 中英 / README | Task 7 Step 1-3 |
| 孪生副本核对 | Task 7 Step 4 |
| 门禁全绿 + 清理 + 日志 | Task 7 Step 5-6 |
| DoD 第 2 步「端到端真机」的 arm64 部分无法本机执行 | Task 5 Step 6 给出可本机做的离线等价核对 + Task 7 Step 6 记「未执行 + 原因」 |

---

## 实现期裁定回写（Unit A 收尾，2026-10-02）

- Task 3 Step 3 的 `_install_binaries` 单边版文本已被证伪：实现改为**两趟**（先全量定位、缺件即返回且 dest 侧零改动，两件齐了才 mkdir+copy+补执行位）。依据是规格 §4.2「缺件即失败不静默出空目录」+ 评审锁 I-1⑤「不留下半截安装」。**后续任何单元不得把它复原成单边形态**，否则该锁静默失效（账本 R-9）。
- `_digest_from_assets` 不带 `.lower()`：形状关 `^[0-9a-f]{64}$` 只认小写，大写形态判「取不到」= fail-closed（账本 R-7）。
- `[tool.mypy].exclude` 的裸 `"ffmpeg"` 子串使 `src/ffmpeg_*`、`tests/test_ffmpeg_*` 对不带路径 mypy 失明；本轮以「显式传参 mypy + basedpyright」替代，改 exclude 形态属独立工作包（账本 R-8）。
