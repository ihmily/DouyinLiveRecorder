# 日志故障分诊

对用户粘贴的运行时日志做「正常 vs 缺陷」判定，并只对缺陷做最小修复。

## 适用与排除

- **适用**：用户粘贴日志片段并问「这些日志正常吗 / 有问题吗 / 帮我看看 / 全部修复」；贴 WARNING/ERROR 想要根因；改动后贴新日志确认行为。
- **不适用**：崩溃栈回溯（走 systematic-debugging）；纯日志格式美化请求。

## 工作流

### Step 1 — 解析日志行

逐行提取时间戳、级别（DEBUG/INFO/WARNING/ERROR）与 `file:func:line` 标记（loguru 格式为 `| __name__:func:line - message`）。注意**空消息**（`- ` 后面什么都没有）——这一定是日志缺陷，必须查。

### Step 2 — 定位发出日志的源码

对每个不同的 `file:func:line`，读源码对应区域，用 Grep 找函数边界和到达它的调用路径。两条同级别的日志可能来自**互不相关**的代码路径（例如异步的 `get_response_status` 与同步的 `_validate_stream_url`），确认之后再建立因果关系。

### Step 3 — 判定正常 vs 缺陷

- **正常（只解释，不改代码）**：由**有意的回退链**发出的 WARNING/DEBUG，且回退随后成功（"X failed, falling back to Y" 之后紧跟 "Y succeeded"）。这是预期容错，不是故障。汇报该行含义并说明流水线已自愈。
- **缺陷（修）**：命中下列任一反模式 ——
  1. `logger.debug(e)` 产出空消息（`e.__str__()` 为空，如 httpx `ConnectError`、部分 `OSError`）；
  2. 仅用 HEAD 做 URL 校验而误杀合法源（CDN m3u8/HLS 常见）；
  3. 瞬时性 API 软拒绝（如 `status_code=10002`）直接触发昂贵回退，而没有先重试；
  4. 吞掉异常、回退分支漏传 proxy/cookies、重复冗余网络请求。

拿不准时去读周边控制流，不要猜。

### Step 4 — 安全的最小修复

只修缺陷，**绝不「顺手优化」正常的回退路径**。范围收紧：一条日志 → 一处修复，不重构无关代码。保留容错能力：重试必须在持续失败时仍能回退；校验探针不得对非目标 URL 类型运行。风格与项目既有写法保持一致（await 模式、logging 调用、异常类型）。

### Step 5 — 验证

走 SKILL.md「统一验证门禁」：`py_compile` 改动文件 → `pytest -q` → `python scripts/run_gates.py` → 涉及平台分支时增跑 `mypy --platform linux`。

**补一条测试锁住新行为**（重试后成功、缓存命中、探针仅对 m3u8 生效）。**这条是要入库的回归测试，不属于临时文件，不要清理。**

### Step 6 — 清理验证残留（强制）

只要落盘过任何临时脚本/输出目录，就按 SKILL.md 铁律 1 全部删除：`git status --porcelain` 确认无预期外残留；`__pycache__` / `.pytest_cache` / 探针输出目录一并清掉。测试失败或中断时同样执行，不得跳过。

### Step 7 — 汇报

给出逐行判定表（级别 / 含义 / 正常或缺陷），说明改了什么、刻意没动什么，并引用验证结果。末尾附一行清理结果（`已清理 N 个临时脚本：<路径>` 或 `未产生临时文件`）。把后续可选项交给用户决定，不要主动扩大清理范围。

## 修复配方（本仓已验证）

### 配方 1 — 空消息日志行

**症状**：

```text
2026-08-01 18:32:10.055 | DEBUG | src.async_http:get_response_status:188 -
```

`-` 后面什么都没有：告诉你出错了，但没说错在哪。

**根因**：`except Exception as e: logger.debug(e)`。当 `str(e)` 为空（httpx `ConnectError`、部分 `OSError`/`TimeoutException`）时，loguru 只打印 `- `。

**修复**：把裸 `logger.debug(e)` 换成带上下文的字符串；需要栈时再加 `exc_info=True`。

```python
except Exception as e:
    logger.debug(f"get_response_status validation failed (treated as unreachable): {e}")
    return False
```

这永远安全——只改善消息，不改变行为。

### 配方 2 — 仅 HEAD 校验误杀合法 m3u8/HLS 源

**症状**：

```text
WARNING | __main__:select_source_url:1196 - HLS URL validation failed, falling back to FLV
```

m3u8 存在且可用，校验器却说不可用，流水线每个周期都降级到 FLV。

**根因**：CDN 的 m3u8 端点经常拒绝 `HEAD`（401/403/405），或对 HEAD 返回非 `video/*` 的 content-type。只信 HEAD 200 的校验器会把好源判成坏源（本仓已知坑：`douyinliving.com` 的 m3u8 对 HEAD 返回 405 + `text/html`）。

**修复**：HEAD 失败后，加一个轻量 `Range: bytes=0-0` GET 探针——**只对 `.m3u8`**、**只在 HEAD 已失败时**；同时接受 `mpegurl` 类型的 content-type。

```python
def _validate_stream_url(url, proxy_addr=None, timeout=5):
    try:
        with httpx.Client(timeout=timeout, proxy=proxy_addr) as client:
            resp = client.head(url, follow_redirects=True)
            ct = resp.headers.get("content-type", "")
            if "video" in ct or "octet-stream" in ct or "flash" in ct or "mpegurl" in ct:
                return True
            if "text/html" in ct or "application/json" in ct:
                return False
            if resp.status_code == 200:
                return True
        # HEAD 被拒 —— 用 1 字节 Range GET 探测 m3u8
        if url.endswith(".m3u8"):
            with httpx.Client(timeout=timeout, proxy=proxy_addr) as client:
                r2 = client.get(url, headers={"Range": "bytes=0-0"}, follow_redirects=True)
                if r2.status_code in (200, 206):
                    return True
    except Exception:
        return False
    return False
```

异步版 `get_response_status` 类校验器同理。非 m3u8 源（FLV / record_url）**不得改变行为**——GET 探针只在「HEAD 失败 + `.m3u8`」时运行。

### 配方 3 — 瞬时 API 软拒绝触发昂贵回退

**症状**：

```text
WARNING | src.spider:get_douyin_web_stream_data:321 - Douyin web API failed: API returned status_code=10002, msg=unknown error, falling back to HTML scraping
DEBUG   | src.spider:get_douyin_web_stream_data:327 - HTML scraping fallback succeeded
```

`10002 unknown error` 是通用软拒绝（风控 / 缺 msToken / 瞬时限流）。HTML 回退能成，但每个周期多烧一次约 1MB 的请求和一条 WARNING。

**根因**：API 调用遇到任何非零 `status_code` 就抛，调用方立即回退，没有重试；而多数软拒绝是瞬时的。

**修复**：给 API 调用包一层「重试一次 + 短 `asyncio.sleep` 缓冲」，两次都失败才回退；重试成功就完全跳过 HTML 抓取。

```python
async def _try_web_api(url, proxy_addr, headers):
    api = f".../webcast/room/web/enter/?{urllib.parse.urlencode(params)}"
    json_str = _get_str_response(await async_req(url=api, proxy_addr=proxy_addr, headers=headers))
    if not json_str:
        raise Exception("empty response from API (possible risk control)")
    parsed = _loads_dict(json_str)
    status_code = parsed.get("status_code")
    if status_code is not None and int(status_code) != 0:
        raise Exception(f"API returned status_code={status_code}, msg={parsed.get('status_msg', 'unknown error')}")
    return room_data

room_data = None
last_err = None
for attempt in range(2):
    try:
        room_data = await _try_web_api(url, proxy_addr, headers)
        break
    except Exception as e:
        last_err = e
        if attempt == 0:
            await asyncio.sleep(0.5)   # 缓冲瞬时风控
        else:
            logger.warning(f"Douyin web API failed twice: {e}, falling back to HTML scraping")
if room_data is None:
    html_str = _get_str_response(await async_req(url=url, proxy_addr=proxy_addr, headers=headers))
    room_data = _extract_room_data_from_html(html_str)  # 回退保留全部原有行为
    if not room_data:
        raise Exception(f"Douyin web data fetch error (API: {last_err}).")
```

注意：**不要动**对所有 web 路径都跑的 HEVC/原画 HTML 抓取——那是必需的，与 10002 路径无关。只有被 10002 触发的那次回退 HTML 被省掉。
