---
name: runtime-security-response
description: "排查并修复运行时安全公告涉及的版本风险：Node.js Brotli CVE-2026-111497 与 PHP php2shell（PHP-CGI/multipart 参数注入 RCE）。用于版本核查、解压与参数注入入口追踪、容器与服务升级及缓解方案、补丁落地与验收复跑。默认只读排查并准备方案，生产变更须经确认。不替代通用依赖审计。"
agent_created: true
---

# 运行时安全应急（Node.js 与 PHP）

## 本轮合并（2026-10-29）

本 Skill 是 2026-10-29 同类合并的归并结果。以下源能力的完整 playbook 已收编进本目录，按需加载 `references/<name>/SKILL.md`，不要把全部参考文档读进上下文：

- `php2shell-defense` → `references/php2shell-defense/SKILL.md`
- 宿主：本目录 SKILL.md 主体来自 `nodejs-security-guard`，目录名按合并后语义重命名。

被吸收源技能的 frontmatter 仅在其原子文档内作历史留存；本目录的 `name` 与路由表为准。跨组的兄弟能力引用见各参考文档内的重定向注。

帮助用户把“是否受影响”落实为可复核的运行时证据和最小修复。事实基线为 2026-10-22；本次公告最高级别为 **High**。使用前读 [advisory.md](references/advisory.md)，联网可用时复核官方公告和实际供应商更新，不把内置版本表当成持续更新的漏洞数据库。

## 工作方式

**默认只读检查并准备方案，不直接操作生产。** 开发者明确确认具体修复方案后才实施。方案必须列出目标环境、具体文件/包/镜像变更、拟执行命令、影响与中断风险、验证及回滚方法。

确认前可保存报告和独立补丁文件供审阅，不得将补丁应用到项目、修改运行配置、安装或升级包、部署、重启、停服或调整防火墙。笼统的“帮我修复”、已有凭证或漏洞严重程度都不能替代方案确认。本地/测试确认不包含生产授权；生产目标与操作需明确确认。相同方案已明确确认则不重复询问，范围或影响发生变化时先补充确认。

1. 确认用户指定项目、运行环境与工作范围。默认从本地文件和已有运行信息做只读排查，不扫描公网、不发送畸形压缩数据或利用载荷。用户只要诊断时，不改配置、不升级、不重启。
2. 识别真正承载业务的 Node.js：开发 CLI、容器最终阶段、PM2/systemd、CI、Serverless、Electron/SEA 等可能使用不同运行时。记录版本来源和覆盖范围。
3. 用下面的离线检查器比较版本；它只给出版本层面的信号。继续按 [runbook.md](references/runbook.md) 追踪 Brotli 解压入口、供应商回补补丁及其他 CVE 条件。仓库未命中关键字不能证明无影响。
4. 用户要求修复时，先提交最小升级和配置变更方案及拟应用的 diff。等待开发者确认后，在其确认的环境与操作范围内实施、测试与复核；等待期间只继续不依赖确认的只读工作。未确认时标为“方案待确认，未实施”，不把方案写成已上线结果。
5. 按 [report-template.md](references/report-template.md) 区分版本结果、可达路径、上线覆盖和剩余未知。只有真正服务流量的全部目标进程与依赖完成验证，才能报告目标范围内修复完成。

涉及镜像升级时，必须按 [处置手册](references/runbook.md) 提交镜像升级影响评估：对比新旧镜像和底层环境，列出运行时/扩展或原生模块、启动配置、关联服务、发布中断和数据回滚的影响、证据及测试安排。仅改 tag 或同分支补丁升级不等于低风险；未核验项明确标出，并纳入开发者确认范围。

## 离线版本核查

检查器仅需 Python 3.9+ 标准库，不安装依赖、不联网、不加载项目代码。将 `<skill-dir>` 替换为本 skill 的安装目录。

```bash
python3 <skill-dir>/scripts/nodecheck.py --version-string 24.22.0 --json
python3 <skill-dir>/scripts/nodecheck.py --local --json
python3 <skill-dir>/scripts/nodecheck.py --local --node /trusted/path/to/node --json
```

优先使用从业务进程取得的 `--version-string`。`--local` 只启动所选可信 Node 的 `--version`，清除 `NODE_OPTIONS` / `NODE_PATH`，默认超时 10 秒；不要执行来自未知仓库的二进制。即便版本通过，也保留 `service_patch_status: not_verified`，不能把新 CLI 当成存量工作进程。

| 退出码 | 状态 | 正确含义 |
| --- | --- | --- |
| 0 | `version_fixed` | 达到本次上游版本基线，业务进程与链接库仍待确认 |
| 1 | `below_fixed` | 低于基线；需升级或查供应商回补证据，未证明可利用 |
| 2 | 参数错误 | 未形成结论 |
| 3 | `eol_review` / `unknown` | EOL、未知、预发行或执行失败，需要进一步核查 |

## 关键边界

- Node.js 22 / 24 / 26 分支的本次基线分别为 **22.23.4 / 24.22.1 / 26.12.1**；选择官方当前仍受支持且含修复的更新版本。20 / 23 / 25 等 EOL 分支应迁移或取得可信供应商支持与回补证据，不归为安全。
- `npm audit`、升级 `package.json` 依赖、仅修改 `engines.node` 均不能替代运行时修补。发行版可能动态链接 Brotli，需确认实际库包与加载映射。Electron 或 SEA 内嵌运行时需要产品升级或重新构建。
- 临时阻断不可信 Brotli 解压只缓解特定路径，不能代替完整安全更新；只设置 `Accept-Encoding: identity` 或关闭响应压缩不能证明解码入口消失。
- 不宣称“全部 Node 网站可被攻击”“Critical/CVSS 10”或“扫描通过即安全”；实际可达性、利用与入侵状态是不同结论。

社区参考范围与原创说明见 [community-research.md](references/community-research.md)。本 skill 与 PHP 护航 skill 独立安装、独立运行。
