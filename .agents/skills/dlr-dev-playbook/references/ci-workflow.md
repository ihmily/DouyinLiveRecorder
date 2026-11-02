# CI / workflow 约定

> 改 CI 配置（`.github/workflows/`、`.github/actions/`）时才需要读本节。
> 唯一事实源仍是 `AGENTS.md`；本文件展开详细背景与事故记录。

---

- **网络安装重试统一走 `.github/actions/retry` 复合动作**（线性退避），禁止在 job 内重新内联 `for i in 1 2 3` 重试循环；核对 `grep -c 'uses: \./\.github/actions/retry' .github/workflows/<file>`。
- **actions 大版本基线 v7**: `checkout`/`setup-python`/`setup-node`/`upload-artifact` 统一 v7；第三方非认证动作的 ref 口径见「已知坑」MIN-17。
- **版本常量跨 workflow 同值**: `python_build`(3.14) 与 `node_version`(24) 在 ci.yml 与 build-release.yml 各自声明，改一处须同步另一处。
- **触发与并发策略区分**: ci.yml 由 `pull_request`（branches: [main]）+ `workflow_dispatch`（补充入口）双触发 + `cancel-in-progress: true`；build-release.yml 由 `v*` tag 触发 + `cancel-in-progress: false`。[2026-10-24 修订] 原 2026-10-17 改为仅 `workflow_dispatch` 的窗口期结束，恢复 `pull_request` 自动触发以匹配 ci-summary required check 的强制执行语义。
- **发布矩阵为四平台，runner 标签↔运行时键的映射单点登记**: `.github/workflows/build-release.yml` 的 `matrix.include` 含 `windows-latest`/`ubuntu-latest`/`ubuntu-24.04-arm`/`macos-latest`（`platform` 依次 `windows`/`linux`/`linux-arm64`/`macos`），一次发布产出 4 ×（lite+full）= **8 个 zip**，`Verify artifact completeness` 的判据随之为 `-lt 8`。**runner 标签↔运行时键映射的唯一登记点是 `scripts/check_runtime_pins.py::RUNNER_TO_RUNTIME_KEY`**，新增 runner 必须同批登记。矩阵条目的**插入位置也是契约**——`_runtime_matrix_keys()` 按 `os:` 行出现顺序返回键列表，测试断言逐序相等。Linux 两支共用家族判定 `if: startsWith(matrix.platform, 'linux')`，取反那步的标量**必须带引号**写成 `if: "!startsWith(matrix.platform, 'linux')"`：YAML 把行首 `!` 当 tag 指令。
- **多架构镜像只走「原生双 runner 各出一层 + imagetools 按 digest 合成」**: `.github/workflows/docker-publish.yml`（仅 `v*` tag 触发、推 GHCR）由 `docker-build-amd64`(`ubuntu-latest`) 与 `docker-build-arm64`(`ubuntu-24.04-arm`) 各推一个分架构临时 tag，merge job 用 `docker buildx imagetools create` 按两个构建 job 提升到 job 级 `outputs:` 的 digest 合成。**禁止单 job QEMU 交叉双平台**。凭据固定为自动注入的 `GITHUB_TOKEN`，发布链**不得**引用任何其它 `secrets.*`。结构锁 `tests/test_docker_publish_workflow.py`（12 条）。
- **dockerignore / gitignore 同源约定**: 本地工具生成目录与运行期产物目录须在两份 ignore 文件与 pyproject 各工具排除列表（black/isort/mypy/basedpyright/coverage）同步维护，漏一处即「未跟踪目录 / 误入镜像 / 工具误扫描」。**第五处同源点**是 `scripts/check_annotations.py::EXCLUDE_DIRS`——由测试与 pyproject 的 black/isort/coverage 三份清单逐名比对。
- **配置键审计须先归一化大小写**: 核对「代码读取的键」与 `config/config.ini` 实际键时先转小写再比对（configparser 大小写不敏感）。
- **venv 依赖修复分级处置**: 三级：① 一级（代理自行）单/少数包破损——wheel 直解绕开卸载；② 二级（代理可试）常规补装单个小包；③ 三级（交回用户）批量重装。
- **覆盖率排除规则两 job 同源**: `pyproject [tool.coverage.report]` 与 `.coveragerc-concurrency` 排除条目必须一致且一律用 `exclude_also`（追加）而非 `exclude_lines`（替换）。
- **镜像额外排除集**（仅 `.dockerignore`）：`uv.lock`/`scripts/`/`AGENTS.md`/`README_EN.md`/`CODE_WIKI_EN.md`/`.coveragerc-concurrency` 及审查记录通配。
- **门禁环境变量 `PYTHONUTF8=1`**: 见「格式化命令」MID-63 条目。
- **`deps-audit` job**: `ci.yml` 中 `pip-audit -r requirements.txt`，独立成 job 且是 `ci-summary.needs` 的一部分。
- **门禁强制执行（2026-10-24 修订）**：`ci-summary` 是对外暴露的**唯一 required check**，汇总全部上游 job。Settings → Branches 中 ci-summary 的 required 勾选必须保持勾选。
- **漏洞审查双防线策略（`deps-audit` 阻断 + Trivy advisory）**: `deps-audit` 审 Python 依赖清单（blocking）；`trivy.yml` 扫 Docker 镜像全层（advisory only）。**Trivy 维持 advisory-only 不升级为阻断**。
- **`static` job 的派生元数据一致性校验（`sync_metadata.py --check`）**: 纯读 `uv.lock`/`egg-info/PKG-INFO`/`pyproject.toml` 比对，漂移修复：`python scripts/sync_metadata.py`。
- **发布链运行时钉定在 prepare 单点收敛（SEV-10）**: 钉定值事实源是 `build_exe.py`，不得把哈希副本写进 workflow。
- **build 失败会留下空 Release，须由 `release-guard` 回收**: `release-guard` 按「残缺即不发布」删除空 Release。不得为「让流水线变绿」给上传步骤关掉 `fail_on_unmatched_files`。
- **维护脚本里「按名字起子进程」必须 `shutil.which` 早退或捕 `OSError`**。
- **跑 pytest 的 job 必须装齐 `requirements.txt`（2026-10-18 事故定型）**: `tests/conftest.py` 的 autouse fixture 会 import `src` 与 `i18n`，门槛是**整份运行时依赖**。判据由 `tests/test_ci_pytest_env_parity.py` 机检。
- **`scripts/smoke_test.py` 的配置形态畸形一律 rc=2**: 消费方靠 rc=2 区分「配置问题」与「面板故障」。回归锁 `tests/test_ci_retry_action.py`。
