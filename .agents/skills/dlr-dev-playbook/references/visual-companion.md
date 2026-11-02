# 可视化伴侣（浏览器）

设计阶段用于在浏览器里展示 mockup、图表和方案选项的伴侣。**它是工具，不是模式**：用户接受它只是意味着「需要视觉化时可以用」，不代表每个问题都要过浏览器。

## 何时使用

**逐题判断，不是逐会话判断。** 判断标准：**用户看一眼是否比读文字更容易理解？**

**用浏览器**（内容本身就是视觉的）：

- **UI mockup** —— 线框图、布局、导航结构、组件设计
- **架构图** —— 系统组件、数据流、关系图
- **并排视觉对比** —— 两种布局、两套配色、两个设计方向
- **设计质感** —— 观感、间距、视觉层级
- **空间关系** —— 状态机、流程图、实体关系（以图形呈现）

**用终端**（内容是文字或表格的）：

- **需求与范围问题** ——「X 是什么意思？」「哪些功能在范围内？」
- **概念型 A/B/C 选择** —— 用文字描述的方案之间做选择
- **权衡清单** —— 优缺点、对比表
- **技术决策** —— API 设计、数据建模、架构选型
- **澄清问题** —— 答案是文字而不是视觉偏好的任何问题

**关于 UI 的问题不自动等于视觉问题**。「这个向导要什么形态？」是概念问题 → 用终端。「这几个向导布局哪个更对？」是视觉问题 → 用浏览器。

## 提议方式

当预计接下来的问题会涉及视觉内容（mockup、布局、图表）时，**只提议一次**征求同意：

> 我们后面有些内容如果在浏览器里展示给你看，可能会更好解释。我可以在过程中做 mockup、图表、对比和其他可视化。这个功能还比较新，可能会消耗较多 token。要试试吗？（需要打开一个本地 URL）

**这条提议必须单独成一条消息。** 不要和澄清问题、上下文摘要或任何其他内容混在一起；消息里**只有**上面这段邀请，别的什么都不要有。等用户回应后再继续；用户拒绝就走纯文字设计流程。

## 工作原理

服务端监听一个目录里的 HTML 文件，把**最新**的那个提供给浏览器。你把 HTML 内容写进 `screen_dir`，用户在浏览器里看到并可以点击选择。选择记录写入 `state_dir/events`，你在下一轮读取。

**内容片段 vs 完整文档**：如果 HTML 文件以 `<!DOCTYPE` 或 `<html` 开头，服务端原样提供（只注入 helper 脚本）；否则服务端会自动把内容包进 frame 模板——加上页头、CSS 主题、选中指示器和全部交互基础设施。**默认写内容片段**，只有需要完全掌控页面时才写完整文档。

## 启动会话

```bash
# 带持久化启动（mockup 存到项目里）
scripts/start-server.sh --project-dir /path/to/project

# 返回：{"type":"server-started","port":52341,"url":"http://localhost:52341",
#        "screen_dir":"/path/to/project/.superpowers/brainstorm/12345-1706000000/content",
#        "state_dir":"/path/to/project/.superpowers/brainstorm/12345-1706000000/state"}
```

保存返回的 `screen_dir` 和 `state_dir`，把 URL 告诉用户打开。

**找回连接信息**：服务端会把启动 JSON 写到 `$STATE_DIR/server-info`。如果你在后台启动却没抓到 stdout，读那个文件即可拿到 URL 和端口。用了 `--project-dir` 时，去 `<project>/.superpowers/brainstorm/` 找会话目录。

**注意**：务必传项目根目录给 `--project-dir`，这样 mockup 才会持久化在 `.superpowers/brainstorm/` 并在服务重启后保留；不传则文件进 `/tmp` 并被清理。提醒用户把 `.superpowers/` 加进 `.gitignore`（若尚未添加）。

### 按平台启动

**Claude Code（macOS / Linux）：**

```bash
# 默认模式即可 —— 脚本自己会把服务放到后台
scripts/start-server.sh --project-dir /path/to/project
```

**Claude Code（Windows）：**

```bash
# Windows 会自动检测并改用前台模式，而前台模式会阻塞工具调用。
# 在 Bash 工具调用上设置 run_in_background: true，让服务跨对话轮次存活。
scripts/start-server.sh --project-dir /path/to/project
```

调用时给 Bash 工具设 `run_in_background: true`，下一轮再读 `$STATE_DIR/server-info` 拿 URL 和端口。

**Codex：**

```bash
# Codex 会回收后台进程。脚本自动检测 CODEX_CI 并切到前台模式。
# 正常跑即可，不需要额外参数。
scripts/start-server.sh --project-dir /path/to/project
```

**Gemini CLI：**

```bash
# 用 --foreground，并在 shell 工具调用上设 is_background: true，
# 让进程跨轮次存活
scripts/start-server.sh --project-dir /path/to/project --foreground
```

**其他环境**：服务必须跨对话轮次在后台保持运行。若你的环境会回收 detached 进程，用 `--foreground` 并用所在平台的后台执行机制启动。

若 URL 在你的浏览器里不可达（远程/容器环境常见），绑定非 loopback 地址：

```bash
scripts/start-server.sh \
  --project-dir /path/to/project \
  --host 0.0.0.0 \
  --url-host localhost
```

`--url-host` 用来控制返回 URL JSON 里打印的主机名。

## 循环

1. **确认服务存活**，然后往 `screen_dir` 写一个新 HTML 文件：
   - 每次写之前检查 `$STATE_DIR/server-info` 是否存在。不存在（或存在 `$STATE_DIR/server-stopped`）说明服务已关闭——先用 `start-server.sh` 重启再继续。**服务空闲 30 分钟后自动退出**。
   - 用语义化文件名：`platform.html`、`visual-style.html`、`layout.html`
   - **绝不复用文件名** —— 每一屏都是新文件
   - 用 Write 工具 —— **绝不用 cat/heredoc**（会把噪声灌进终端）
   - 服务端自动提供最新的那个文件

2. **告诉用户会看到什么，然后结束本轮**：
   - 提醒 URL（**每一步都提醒**，不只是第一次）
   - 简短文字说明屏幕上是什么（如「正在展示首页的 3 个布局方案」）
   - 请用户在终端回复：「看一下，告诉我你的想法。想选哪个可以点一下。」

3. **下一轮** —— 用户回复后：
   - 若存在 `$STATE_DIR/events`，读取它——里面是用户的浏览器交互（点击、选择），每行一个 JSON
   - 与用户的终端文字合并，得到完整反馈
   - **终端消息是主要反馈**，`state_dir/events` 提供结构化交互数据

4. **迭代或推进** —— 反馈改动当前屏就写新文件（如 `layout-v2.html`）。当前步被确认后才进入下一个问题。

5. **回到终端时卸载画面** —— 下一步不需要浏览器时（如澄清问题、权衡讨论），推一个等待屏清掉过时内容：

   ```html
   <!-- 文件名：waiting.html（或 waiting-2.html 等） -->
   <div style="display:flex;align-items:center;justify-content:center;min-height:60vh">
     <p class="subtitle">Continuing in terminal...</p>
   </div>
   ```

   这能避免对话已经往前走了、用户还盯着一个已经解决的选择。下一个视觉问题来了就照常推新内容文件。

6. 重复直到结束。

## 写内容片段

只写放进页面里的那部分内容，服务端会自动用 frame 模板包装（页头、主题 CSS、选中指示器、全部交互基础设施）。

**最小示例：**

```html
<h2>Which layout works better?</h2>
<p class="subtitle">Consider readability and visual hierarchy</p>

<div class="options">
  <div class="option" data-choice="a" onclick="toggleSelect(this)">
    <div class="letter">A</div>
    <div class="content">
      <h3>Single Column</h3>
      <p>Clean, focused reading experience</p>
    </div>
  </div>
  <div class="option" data-choice="b" onclick="toggleSelect(this)">
    <div class="letter">B</div>
    <div class="content">
      <h3>Two Column</h3>
      <p>Sidebar navigation with main content</p>
    </div>
  </div>
</div>
```

就这样：不需要 `<html>`、不需要 CSS、不需要 `<script>` 标签，服务端全都提供。

## 可用的 CSS 类

frame 模板为内容提供了这些 CSS 类：

### 选项（A/B/C 选择）

```html
<div class="options">
  <div class="option" data-choice="a" onclick="toggleSelect(this)">
    <div class="letter">A</div>
    <div class="content">
      <h3>Title</h3>
      <p>Description</p>
    </div>
  </div>
</div>
```

**多选**：给容器加 `data-multiselect`，用户就能选多个；每次点击切换选中状态，指示器条显示数量。

```html
<div class="options" data-multiselect>
  <!-- 同样的 option 结构 —— 用户可多选/取消 -->
</div>
```

### 卡片（视觉设计）

```html
<div class="cards">
  <div class="card" data-choice="design1" onclick="toggleSelect(this)">
    <div class="card-image"><!-- mockup 内容 --></div>
    <div class="card-body">
      <h3>Name</h3>
      <p>Description</p>
    </div>
  </div>
</div>
```

### Mockup 容器

```html
<div class="mockup">
  <div class="mockup-header">Preview: Dashboard Layout</div>
  <div class="mockup-body"><!-- 你的 mockup HTML --></div>
</div>
```

### 分屏（并排）

```html
<div class="split">
  <div class="mockup"><!-- 左 --></div>
  <div class="mockup"><!-- 右 --></div>
</div>
```

### 优缺点

```html
<div class="pros-cons">
  <div class="pros"><h4>Pros</h4><ul><li>Benefit</li></ul></div>
  <div class="cons"><h4>Cons</h4><ul><li>Drawback</li></ul></div>
</div>
```

### Mock 元素（线框积木）

```html
<div class="mock-nav">Logo | Home | About | Contact</div>
<div style="display: flex;">
  <div class="mock-sidebar">Navigation</div>
  <div class="mock-content">Main content area</div>
</div>
<button class="mock-button">Action Button</button>
<input class="mock-input" placeholder="Input field">
<div class="placeholder">Placeholder area</div>
```

### 排版与区块

- `h2` —— 页面标题
- `h3` —— 章节标题
- `.subtitle` —— 标题下的次级文字
- `.section` —— 带下边距的内容块
- `.label` —— 小型大写标签文字

## 浏览器事件格式

用户在浏览器里点击选项时，交互以 JSON Lines 形式写入 `$STATE_DIR/events`。**推新屏时该文件会自动清空。**

```jsonl
{"type":"click","choice":"a","text":"Option A - Simple Layout","timestamp":1706000101}
{"type":"click","choice":"c","text":"Option C - Complex Grid","timestamp":1706000108}
{"type":"click","choice":"b","text":"Option B - Hybrid","timestamp":1706000115}
```

完整的事件流能显示用户的探索路径——他们可能在定下来之前点了多个选项。最后一个 `choice` 事件通常是最终选择，但点击的模式本身能揭示犹豫或偏好，值得追问。

若 `$STATE_DIR/events` 不存在，说明用户没在浏览器里交互——只用他的终端文字。

## 设计建议

- **保真度匹配问题** —— 布局问题用线框，质感问题就给质感
- **每页都要解释问题** ——「哪个布局看起来更专业？」而不是只写「选一个」
- **迭代优先于推进** —— 反馈改动当前屏就写新版本
- **每屏最多 2-4 个选项**
- **关键处用真实内容** —— 摄影作品集就放真实图片（Unsplash）；占位内容会掩盖设计问题
- **mockup 保持简单** —— 聚焦布局和结构，不要追求像素级

## 文件命名

- 语义化命名：`platform.html`、`visual-style.html`、`layout.html`
- 绝不复用文件名 —— 每屏都是新文件
- 迭代版本加后缀：`layout-v2.html`、`layout-v3.html`
- 服务端按修改时间提供最新文件

## 清理

```bash
scripts/stop-server.sh $SESSION_DIR
```

若会话用了 `--project-dir`，mockup 文件会保留在 `.superpowers/brainstorm/` 供后续参考；只有 `/tmp` 会话会在 stop 时被删除。

## 参考

- frame 模板（CSS 参考）：`scripts/frame-template.html`
- 客户端 helper 脚本：`scripts/helper.js`
