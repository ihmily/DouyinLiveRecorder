# 第三方组件说明

弹幕抓取功能引入了两个非本项目原创的文件，来源与许可情况列在这里，便于维护者判断。

## 1. src/javascript/douyin_ws_sign.js

| | |
|---|---|
| 内容 | 字节跳动官方前端 SDK `webmssdk.js`（混淆后的线上分发版本） |
| 用途 | 生成抖音 webcast WebSocket 握手所需的 `signature` 参数 |
| 版权 | 归字节跳动所有。本文件是抖音线上公开分发的前端资源副本，**不是任何下游开源项目的原创代码** |
| 获取来源 | `jwwsjlm/douyinLive`（**MIT**）仓库的 `jsScript/webmssdk.js` |

选择 MIT 仓库而非其他来源的原因：同一份 SDK 也被若干 **AGPL-3.0** 许可的项目打包分发，
从那些仓库复制会给本项目（MIT）带来 copyleft 传染问题。这里刻意避开了。

**配套的浏览器环境垫片**：该 SDK 面向浏览器编写，直接在 Node 下执行会报
`window is not defined`。`src/danmaku.py` 中的 `BROWSER_POLYFILL` 是**本项目原创代码**，
只提供最小可用的 `window` / `navigator` / `document` 等对象，用于避免引入 jsdom 这类重依赖。

## 2. src/protobuf/douyin.proto

| | |
|---|---|
| 内容 | 抖音 webcast IM 的 protobuf 消息结构（PushFrame / Response / Message 及各类业务消息） |
| 性质 | 对线上二进制协议的逆向描述，属于**接口事实的陈述**，不是可用于其他场景的创作性代码 |
| 字段校验 | 消息类型与字段编号均已用真实直播间数据实测校验（`payloadType`、`payloadEncoding`、`internalExt`、`messagesList` 等） |

需要说明的是，社区流传的同类协议描述多由 **AGPL-3.0** 许可的项目发布，
本文件最初也取自其中之一。若维护者认为不宜直接引入，可按需重新逆向：
协议结构并不复杂，且 `src/protobuf/douyin_pb2.py` 已编译好，也可改用运行时动态构造 descriptor 的方式彻底去掉该文件。

## 小结

- 签名 SDK：字节官方资源，取自 MIT 仓库 —— 无 copyleft 风险
- 浏览器垫片：本项目原创 —— 无风险
- 协议描述：事实性信息，已实测校验 —— 若存疑可自行替换

三者都不会让本项目（MIT）承担 AGPL 义务。
