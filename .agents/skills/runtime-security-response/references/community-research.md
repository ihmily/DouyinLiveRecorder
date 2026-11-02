# 社区检索与来源说明

检索日期：2026-10-22。检索范围为公开 GitHub / Web 的 `CVE-2026-111497 skill`、`Brotli SKILL.md`、Node.js security skill 等查询，并阅读下列仓库。这个范围内未发现明确覆盖本次 Node.js 2026 年 10 月公告的专用 skill；不能据此声称社区不存在。

| 社区项目 | 相关能力 | 与本 skill 的区别 |
| --- | --- | --- |
| [Paldom/node-skills — node-supply-chain](https://github.com/Paldom/node-skills/blob/main/skills/node-supply-chain/SKILL.md) | Node / npm 供应链风险与加固 | 重点是依赖供应链，不是此次运行时补丁和线上进程验收 |
| [hlsitechio/claude-skills-security — nodejs-express-security](https://github.com/hlsitechio/claude-skills-security/blob/main/appsec-stack-pack/nodejs-express-security/SKILL.md) | Node.js / Express 应用安全审计 | 一般应用审计，未作为本次 CVE 的修复版本依据 |

本 skill 的指引、检查器和测试为此次需求独立编写，没有复制上述社区 skill 源码或正文。技术事实来自 [Node.js 官方公告](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases)及官方项目实现/文档。社区项目仅作为方向参考，不暗示其作者背书或官方合作。

本包独立采用 Apache-2.0 许可证；不依赖 PHP skill，也不包含第三方扫描器、漏洞载荷或远程遥测。
