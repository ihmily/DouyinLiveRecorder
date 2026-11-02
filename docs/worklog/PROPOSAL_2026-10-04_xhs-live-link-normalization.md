# Xiaohongshu Live Link Normalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 扩展现有小红书直播支持，统一识别标准直播链接、分享短链、动态路径链接和完整分享参数链接，稳定提取直播间 ID，并确保合法链接能进入现有录制启动链。

**Architecture:** 在 `src/spider.py` 现有小红书解析器旁增加一个同步、可独立测试的 URL 解析/归一化入口；短链先沿用现有安全重定向，再把落地地址交回同一入口。解析结果继续复用 `get_xhs_stream_url` 与 `main.py::_resolve_xhslink_com`，通过现有 `new_record_url` 回写机制保存规范地址，不新增重复平台注册或第二套取流链。

**Tech Stack:** Python 3.14、`urllib.parse`、现有 `async_req`/`trace_error_decorator`、pytest/pytest-asyncio、现有平台分发表与 `start_record` 录制链。

---

## 已批准的设计边界

- 接受 `https://www.xiaohongshu.com/livestream/<数字房间ID>`。
- 接受 `https://www.xiaohongshu.com/livestream/<动态段>/<数字房间ID>`。
- 接受 `https://xhslink.com/o/<短码>`；只在安全重定向成功后解析落地直播地址。
- 保留既有 `https://www.xiaohongshu.com/user/profile/<用户ID>` 监控兼容。
- 仅保留 `host_id`、`xsec_token`、`xsec_source`；剥离 `timestamp`、`share_source`、`share_id`、fragment 及其他无关参数。
- 合法动态路径保持原样，不假定删掉动态段后页面仍可访问；动态段、短码和主页 ID 只接受 ASCII 字母数字、下划线与连字符，拒绝点段及编码点段；`room_id` 始终从路径末段独立提取。
- 标准直播链接即使未带 `host_id`，也用房间 ID 生成稳定占位主播名，避免首轮离线时因空主播名无法创建监控作业。
- 非法域名、非直播/主页路径、房间 ID 缺失、短链重定向失败分别给出明确错误，不转入其他平台；错误文本不得内嵌未脱敏的完整 URL，调用方需要记录 URL 时必须先经过 `utils.mask_credentials()`。
- 现有外部跳转、内网落地页、凭据泄露防线保持不变并补回归锁。

## 活体取证（2026-10-04，未写入任何凭据值）

- 用户给出的标准链接、动态路径链接与短链当前均返回同一小红书直播页面。
- 短链最终落到 `www.xiaohongshu.com/livestream/<动态段>/<数字房间ID>`；查询键实际包含 `host_id`、`share_id`、`share_source`、`source`、`timestamp`、`xsec_source`、`xsec_token`，与“保留三项、剥离统计参数”的设计吻合。
- 页面 `window.__INITIAL_STATE__.liveStream.roomData.hostInfo.nickName` 在 `liveStatus="end"` 时仍存在，可用于离线等待阶段建立稳定监控作业；旧实现没有读取该字段，实测标准链接返回空主播名与空 room_id。

## Task 1：建立小红书 URL 解析契约

**Files:**
- Create: `tests/test_xhs_live_links.py`
- Modify: `src/spider.py`（现有 `_XHS_ALLOWED_HOST_SUFFIXES` 与 `get_xhs_stream_url` 附近）

**Step 1: 写失败测试**

覆盖：

```python
@pytest.mark.parametrize(
    ("url", "kind", "room_id"),
    [
        ("https://www.xiaohongshu.com/livestream/570480456678837366", "live", "570480456678837366"),
        ("https://www.xiaohongshu.com/livestream/dynpathj5ajT8rr/570480456678837366", "live", "570480456678837366"),
        ("https://xhslink.com/o/4NnyJghfl4P", "short", ""),
        ("https://www.xiaohongshu.com/user/profile/abc", "profile", ""),
    ],
)
def test_parse_xhs_link_shapes(url: str, kind: str, room_id: str) -> None:
    info = spider.parse_xhs_live_url(url)
    assert info["kind"] == kind
    assert info["room_id"] == room_id
```

另加完整分享参数断言：规范 URL 只含 `host_id`、`xsec_token`、`xsec_source`，且不含 `timestamp/share_source/share_id`。

**Step 2: 验证测试先红**

Run: `python -m pytest tests/test_xhs_live_links.py -q`
Expected: FAIL，`src.spider` 尚无 `parse_xhs_live_url`。

**Step 3: 写最小实现**

在 `src/spider.py` 增加：

```python
class XhsUrlError(ValueError):
    code: str


def parse_xhs_live_url(url: str) -> dict[str, str]:
    # 用 urlparse 精确校验 scheme、host、userinfo、port 与路径结构。
    # 返回 kind / normalized_url / room_id / user_id。
    ...
```

实现细则：
- 只接受 `http/https`，规范结果统一为 `https`；拒绝 userinfo 与非默认端口。
- 长链主机精确为 `www.xiaohongshu.com`，短链主机精确为 `xhslink.com`。
- `/livestream/` 后只接受一个房间 ID 段，或一个动态段加一个房间 ID 段；房间 ID 必须是 ASCII 数字（`[0-9]+`，不使用会放行全角数字的 `\d+`），动态段只接受 ASCII 字母数字、下划线与连字符。
- `/user/profile/<id>` 保持兼容，ID 与短码使用同一字符白名单。
- 用 `parse_qs(..., keep_blank_values=False)` + 固定键顺序重建白名单 query，删除 fragment。
- `XhsUrlError.code` 至少区分 host / non_live_path / room_id / short_path；错误文本不得包含完整原始 URL、query token 或未脱敏原始 path。

**Step 4: 跑测试转绿**

Run: `python -m pytest tests/test_xhs_live_links.py -q`
Expected: URL 结构与参数归一化用例全部 PASS。

## Task 2：短链解析、错误分类与现有取流链融合

**Files:**
- Modify: `tests/test_xhs_live_links.py`
- Modify: `src/spider.py:2481-2634`
- Modify: `tests/test_regression_spider.py:220-283`（仅在既有安全契约需要同步时）

**Step 1: 写失败测试**

- mock `async_req(..., redirect_url=True)` 返回动态路径落地页，断言再次解析后得到房间 ID 和规范 URL。
- redirect 返回空串时断言 `error` 为“短链重定向解析失败”。
- redirect 落到 `/explore/...` 时断言 `error` 为“不是直播或作者主页链接”。
- 非 XHS host、XHS 笔记页、直播路径缺房间 ID 分别返回不同错误。
- 确认非法落地页不触发第二次带 Cookie/`xy-common-params` 请求。

**Step 2: 验证测试先红**

Run: `python -m pytest tests/test_xhs_live_links.py tests/test_regression_spider.py -q`
Expected: 新用例 FAIL，旧安全用例保持 PASS。

**Step 3: 最小接入现有解析器**

- `get_xhs_stream_url` 在构造凭据请求前先调用 `parse_xhs_live_url`。
- `kind == "short"` 时解析最终地址，保留现有域族白名单 + 内网目标两道闸，再次调用同一解析函数；失败立即返回带 `error` 的离线结果。
- 页面请求使用 `normalized_url`。
- 返回结果稳定携带 `room_id` 与 `normalized_url`。
- 对直播链接优先读取当前页面 `liveStream.roomData.hostInfo.nickName` 作为主播名；活体页面已验证该字段在 `liveStatus="end"` 时仍存在。若页面未给出昵称且 URL 没有 `host_id`，再使用 `小红书_<room_id>` 作为稳定监控名，避免首轮离线时无法创建作业；主页链接继续按既有 profile 兜底。
- 现有 `__INITIAL_STATE__`、直播状态、回放过滤、FLV/HLS 构造逻辑不重写。

**Step 4: 跑测试转绿**

Run: `python -m pytest tests/test_xhs_live_links.py tests/test_spider_platform.py tests/test_spider_hardening.py tests/test_regression_spider.py -q`
Expected: 全部 PASS、0 warnings。

## Task 3：接入分派、配置归一化与明确错误提示

**Files:**
- Modify: `main.py:1693-1715,2285-2299,3462-3499,4235-4243,5663-5667`
- Modify: `tests/test_platform_dispatch.py`
- Modify: `tests/test_xhs_live_links.py`
- Modify: `i18n/zh_CN/LC_MESSAGES/zh_CN.po`
- Modify: `i18n/zh_CN/LC_MESSAGES/zh_CN.mo`
- Modify: `i18n/en_US.json`
- Modify: `i18n/en_GB.json`
- Modify: `i18n/zh_TW.yaml`

**Step 1: 写失败测试**

- `_DISPATCH_CASES` 增加标准直播、动态路径、短链三种代表地址，均命中 `get_xhs_stream_url`。
- resolver 收到 `port_info["normalized_url"]` 时把它写入 `new_record_url`。
- resolver 收到 `port_info["error"]` 时输出“小红书链接解析失败”并设置 `unrecognized`，不进入其他平台。
- 配置参数归一化不再用只保留 `host_id` 的正则；通过统一函数保留三项白名单参数。

**Step 2: 验证测试先红**

Run: `python -m pytest tests/test_platform_dispatch.py tests/test_xhs_live_links.py -q`
Expected: 新分派/回写/错误用例 FAIL。

**Step 3: 最小接线**

- `_resolve_xhslink_com` 读取 `error` 与 `normalized_url`；错误走明确日志，成功把规范 URL放入现有 `new_record_url`。
- 将 `new_record_url` 注释从“S​​hopee 专用”改为“平台解析后需回写的规范 URL”，不改变四元组结构。
- URL 配置读取阶段对 `www.xiaohongshu.com` 长链调用同一纯解析函数；短链不在准入阶段发网络请求。
- 新增用户可见字符串同步四语目录并重编译 `.mo`。

**Step 4: 跑测试转绿**

Run: `python -m pytest tests/test_platform_dispatch.py tests/test_xhs_live_links.py tests/test_i18n.py -q`
Expected: 全部 PASS、四语键集一致。

## Task 4：证明录制作业能创建并启动

**Files:**
- Modify: `tests/test_xhs_live_links.py`
- Reference: `tests/test_record_watchdog.py` 的 `start_record` 桩与退出控制模式

**Step 1: 写失败集成测试**

调用 `start_record(("原画", XHS_URL, ""), 1, ...)`，仅替换：
- 小红书页面/短链网络请求；
- 流探针选择；
- `check_subprocess`；
- 轮询退出与时间相关依赖。

断言：
- URL 命中“小红书直播”；
- 解析结果携带目标房间 ID；
- `check_subprocess` 被调用，输入为选择后的 XHS 流地址；
- 规范 URL 被加入既有配置回写队列。

**Step 2: 验证测试先红**

Run: `python -m pytest tests/test_xhs_live_links.py -q`
Expected: 集成断言在接线完成前 FAIL。

**Step 3: 补足最小缺口并复绿**

只补测试揭示的接线缺口，不改通用录制命令构造。

Run: `python -m pytest tests/test_xhs_live_links.py tests/test_record_watchdog.py -q`
Expected: 全部 PASS、0 warnings。

## Task 5：文档、变异验证与全量门禁

**Files:**
- Modify: `CODE_WIKI.md`
- Modify: `CODE_WIKI_EN.md`
- Modify: `AGENTS.md`（仅新增本次可复用的 XHS URL 判据与测试锚点）
- Modify: `.workbuddy/memory/2026-10-04.md`（当前工作区追加日志）

**Step 1: 安全不变量变异验证**

临时破坏以下任一判据并确认专项测试转红，随后按字节还原：
- 允许非数字房间 ID；或
- 把 query 白名单改回全量保留；或
- 跳过短链落地页二次路径校验。

Expected: 至少一个新增专项测试 FAIL；还原后全绿，仓库无 `MUTATION-` 残留。

**Step 2: 更新文档**

- 中英文 `CODE_WIKI` 同批追加本功能、错误语义与验证结果。
- `AGENTS.md` 只登记长期有效的 URL 形态/参数白名单/短链二次校验坑位，不复制实现细节。
- 保持原行尾形态；不覆盖当前工作区已有未提交文档改动。

**Step 3: 运行专项与全量门禁**

Run: `python scripts/run_gates.py`
Expected: 退出码 0。

Run: `python -m pytest -q`
Expected: 全部 PASS、warnings summary 为空。

Run: `python scripts/check_coverage.py`
Expected: 所有模块达到既有阈值。

**Step 4: 真机/端到端边界**

- 用用户给出的四类地址做解析与作业创建验证；若实际直播已结束，至少验证到“成功识别房间 ID并进入等待直播”，不伪造“已成功录到视频”。
- 短链和分享参数中的真实 token 只用于内存请求，不写测试、不写日志、不写文档。

## 假设与回滚

- 假设小红书直播房间 ID 为纯数字，动态路径至多一段；如果真机返回其他形态，先保存脱敏样例再扩规则，不提前放宽。
- 假设 `xsec_token` 与 `xsec_source` 是当前页面鉴权相关参数，`host_id` 继续承担主页兜底；其他分享参数均不参与取流。
- 回滚方式：撤销本功能对 `src/spider.py`、`main.py`、专项测试及 i18n/文档的独立改动；现有小红书旧解析与其他平台分发表不受影响。
