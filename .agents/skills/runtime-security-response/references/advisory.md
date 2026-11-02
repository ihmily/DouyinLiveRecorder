# 官方公告与事实边界

核对日期：2026-10-22。来源：[Node.js 2026-10-21 安全公告](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases)。本次最高级别 **High**，共 10 个 CVE。下表是公告列出的受支持分支，不是 EOL 分支的免责清单。

| CVE | 级别 | 公告涉及分支 | 关注点 |
| --- | --- | --- | --- |
| CVE-2026-111497 | High | 22 / 24 / 26 | Brotli 解码越界写，可导致远程代码执行 |
| CVE-2026-105482 | High | 22 / 24 / 26 | DNS 名称中 NUL 截断 |
| CVE-2026-105483 | High | 24 / 26 | 全角数字 IP 的 TLS 主机名校验 |
| CVE-2026-106069 | High | 22 / 24 / 26 | 宽松 IP 解析的 TLS 主机名校验 |
| CVE-2026-105481 | Medium | 22 / 24 / 26 | keep-alive 响应顺序 |
| CVE-2026-106072 | Medium | 22 / 24 / 26 | 非规范 IPv4 的证书校验 |
| CVE-2026-106074 | Medium | 22 / 24 / 26 | 启动快照与 SEA 保留随机熵缓存 |
| CVE-2026-106070 | Low | 26 | ZIP 头校验失败后的数据返回 |
| CVE-2026-106071 | Low | 26 | 权限模型通配符匹配 |
| CVE-2026-106073 | Low | 22 / 24 / 26 | realpathSync 权限模型 |

首次修复版本为 **22.23.4、24.22.1、26.12.1**。更高的同分支稳定版本满足本次版本基线，但其他新公告、供应商构建差异和线上旧进程仍需核实。

上游公告要求 EOL 用户更新受支持版本。版本表未列出 EOL 不表示不受影响；脚本将 20、23、25 等已结束支持的版本标为 `eol_review`。供应商回补必须匹配具体平台、包版本、CVE 和实际运行构建，不能仅以版本号较旧判定补丁缺失。

## 解码路径证据

- [Undici 官方 Fetch 实现](https://github.com/nodejs/undici/blob/main/lib/web/fetch/index.js) 中，响应 `Content-Encoding: br` 可进入 `createBrotliDecompress`。核对目标使用的具体版本；这是检查出站请求处理的理由，不是任意调用 Fetch 就必然可利用的结论。
- [Express 官方 body-parser 文档](https://expressjs.com/en/resources/middleware/body-parser/) 描述自动解压 Brotli，`inflate` 默认开启。目标可能使用不同版本或配置，须确认请求经过哪个中间件。
- 直接调用 `node:zlib` 的解码、上传文件、消息处理、批任务也应按不可信数据流逐项检查。仅检查 HTTP 入站会漏掉其他来源。

只从官方公告取得漏洞级别和修复线。不要推演未经官方确认的 CVSS、利用载荷、所有历史版本边界或特定供应商补丁版本。
