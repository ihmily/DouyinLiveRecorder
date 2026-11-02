// 组 G 前端回归锁：SEV-2221 / SEV-2227 / SEV-2228 / MID-2237 / MID-2240 / MID-2253；
// 后续 CODE_REVIEW_2026-09-29_2 的 M-21（轮询代次竞态）/ M-23（dropped 转义）/ M-26（认证复验
// 假绿锁改写）也落在此处。M-22 的口令窗行为另在 tests/frontend/test_auth_reauth.mjs。
//
// 与 test_quality_ui.mjs 的分工：那边是既有质量门禁（四语目录、parseConfigBool 跨语言不变量、
// 掩码写入、登出等）；本文件只放本轮修复对应的**失效形态**锁，把对应修复改回原样即变红。
//
// 沙箱策略与 test_quality_ui.mjs 同源（vm + 自制 DOM/fetch 桩，无 npm 依赖），但这里需要
// **可控定时器**：SEV-2227 的失效形态是「隐藏后 setTimeout 永不再排」，no-op 定时器观察不到，
// 故改为可手动推进的假定时器队列；M-21 另需可停在半路的 fetch（makeInflight）。
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
// M-85：行为锁需要把真文件里的 VBScript 函数原文交给 cscript 求值（非 Windows 无 cscript → skip）。
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_JS = readFileSync(new URL('../../web/app.js', import.meta.url), 'utf8');
const INDEX_HTML = readFileSync(new URL('../../web/index.html', import.meta.url), 'utf8');
const ROOT_INDEX_HTML = readFileSync(new URL('../../index.html', import.meta.url), 'utf8');
const WEB_API_PY = readFileSync(new URL('../../src/web_api.py', import.meta.url), 'utf8');
// 请求模型（含 ConfigUpdate.reauth_password）在 src/web_models.py，字段级断言扫该文件；
// update_config 端点本体仍在 web_api.py。
const WEB_MODELS_PY = readFileSync(new URL('../../src/web_models.py', import.meta.url), 'utf8');
// SEV-2221 撤销锁要核对 main.py 里有没有轮次计数器（判据见该用例），读原文而不猜。
const MAIN_PY = readFileSync(new URL('../../main.py', import.meta.url), 'utf8');

// —— DOM / 定时器 / fetch 桩 ————————————————————————————————

function makeClassList() {
    const set = new Set();
    return {
        add(...cs) { cs.forEach(c => set.add(c)); },
        remove(...cs) { cs.forEach(c => set.delete(c)); },
        // 第二参 force 必须支持：真实 DOM 里它是**绝对赋值**（true 一定加、false 一定去），
        // 一元翻转在「同一元素渲染两次」时结论相反。renderRecordingControl 正用
        // `classList.toggle('hidden', !enabled)`，SEV-2228 后半要断言三态标签显隐，
        // 不修这条桩就测不出真实语义。
        toggle(c, force) {
            const want = force === undefined ? !set.has(c) : Boolean(force);
            if (want) set.add(c); else set.delete(c);
            return want;
        },
        contains(c) { return set.has(c); },
    };
}

function makeElement(id) {
    const listeners = {};
    const attrs = {};
    return {
        id,
        _listeners: listeners,
        innerHTML: '',
        textContent: '',
        value: '',
        // options 是 HTMLSelectElement 独有的集合：renderDanmaku 推进增量游标（dmLastSeq）前会
        // 遍历 sel.options 保留当前筛选项（`for (var k = 0; k < sel.options.length; k++)`）。桩若
        // 不建模，该处读 undefined.length 抛 TypeError，其后的游标推进被整体跳过，用例会把
        // 「沙箱 DOM 不全」误报成「生产未推进游标」。真实浏览器里 select.options 恒存在。
        options: [],
        className: '',
        disabled: false,
        scrollTop: 0,
        scrollHeight: 0,
        style: {},
        dataset: {},
        classList: makeClassList(),
        addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
        setAttribute(k, v) { attrs[k] = String(v); },
        getAttribute(k) { return k in attrs ? attrs[k] : null; },
        appendChild() {},
        removeChild() {},
        closest() { return null; },
        matches() { return false; },
    };
}

// 可手动推进的定时器：nextId 单调递增（断言「是否还在排队下一次」时读它），
// runNext 只执行排在最前的一个回调，flush 反复执行直到队列空。
function makeTimers() {
    let seq = 0;
    const pending = new Map();
    return {
        pending,
        setTimeout(fn) { const id = ++seq; pending.set(id, fn); return id; },
        clearTimeout(id) { pending.delete(id); },
        // 只执行指定的一个回调（调用方先快照 id），执行前从队列摘除；
        // 不提供「跑空队列」入口——轮询回调会自我续期，跑空等于空转到稳定态。
        async runOne(id) {
            const fn = pending.get(id);
            if (!fn) return false;
            pending.delete(id);
            fn();
            return true;
        },
    };
}

function makeResponse(status, data) {
    const text = JSON.stringify(data);
    return {
        status,
        ok: status >= 200 && status < 300,
        headers: { get: () => 'application/json' },
        text: async () => text,
    };
}

// routes 键为 "METHOD path"，值为对象或 (callIndex) => 对象；path 含 query 时按前缀匹配失败，
// 故调用方须写全（本文件用到的 path 都是固定的）。spec.gate 存在时响应体要等 gate 落地才返回，
// 用来把请求「停在半路」（M-21，见 makeInflight）。
// spec.hang（M-88①）：响应永不落地，只在 init.signal 被中止时以 AbortError 拒绝——
// 用来造「后端挂起」，同时把 signal 交给用例观察是否真的被中止。
// log 条目附带 init（M-84 / M-88①）：断言请求头（Bearer）与中止信号都要靠它，
// 既有断言只读 path/method/body，多一个键不影响它们。
function makeFetch(routes, log) {
    return async (path, init) => {
        init = init || {};
        const method = init.method || 'GET';
        log.push({ path, method, init });
        const route = routes[method + ' ' + path] || routes[method + ' ' + path.split('?')[0]];
        if (!route) return makeResponse(404, { detail: 'no test route for ' + method + ' ' + path });
        const spec = typeof route === 'function' ? route(log.length) : route;
        if (spec.hang) {
            return new Promise((_resolve, reject) => {
                const signal = init.signal;
                if (!signal) return;
                const abort = () => {
                    const err = new Error('The user aborted a request.');
                    err.name = 'AbortError';
                    reject(err);
                };
                if (signal.aborted) abort();
                else signal.addEventListener('abort', abort, { once: true });
            });
        }
        if (spec.gate) {
            const status = spec.status || 200;
            const body = JSON.stringify(spec.json || {});
            return {
                status,
                ok: status >= 200 && status < 300,
                headers: { get: () => 'application/json' },
                text: async () => {
                    await spec.gate;
                    return body;
                },
            };
        }
        return makeResponse(spec.status || 200, spec.json || {});
    };
}

// —— M-21 用例专用：可「停在半路」的 fetch 路由 ————————————————
// 每次调用返回 text() 等外部 Promise 的响应，由 releaseNext() 精确放行「第 k 次在途请求落地」。
// 「停止 → 立即重启」的竞态只在**旧请求晚于新链启动**才落地时暴露，普通 fetch 桩（当轮即回）
// 造不出这一刻，故必须把在途请求做成测试可控的对象。jsonFor 传函数时按调用序号取载荷，
// 让「过期那一轮」带回可辨识的数据。
function makeInflight(jsonFor) {
    const waiting = [];
    let calls = 0;
    const route = () => {
        calls += 1;
        let release;
        const gate = new Promise(resolve => {
            release = resolve;
        });
        waiting.push(release);
        const payload = typeof jsonFor === 'function' ? jsonFor(calls) : jsonFor;
        return { json: payload, gate };
    };
    return {
        route,
        calls: () => calls,
        inflight: () => waiting.length,
        async releaseNext() {
            const release = waiting.shift();
            if (!release) throw new Error('没有可放行的在途请求（用例前提失效）');
            release();
            await flushMicrotasks();
        },
    };
}

// 点某个 tab（不推进定时器）：M-21 用例要在「新链已排期、旧请求仍在途」这一刻停住，
// 不能用 gotoDashboard/gotoDanmaku（它们附带一次 tick）。
function clickTab(ctx, view) {
    const tab = ctx.tabs.find(t => t.getAttribute('data-view') === view);
    tab._listeners.click[0].call(tab);
}

async function flushMicrotasks(rounds) {
    for (let i = 0; i < (rounds || 10); i++) {
        await new Promise(r => setImmediate(r));
    }
}

// 启动 app.js；hidden 控制初始 document.hidden（visibilitychange 用例要先处于可见态再切走）。
async function boot({ routes = {}, hidden = false, seedClasses = {} } = {}) {
    const fetchLog = [];
    const timers = makeTimers();
    const elements = new Map();
    const tabs = ['dashboard', 'danmaku', 'rooms', 'config', 'files'].map(v => {
        const el = makeElement('tab-' + v);
        el.setAttribute('data-view', v);
        return el;
    });
    const docListeners = {};
    // class 选择器桩：只建模 renderRecordingControl 用到的 .recording-state 三 span（on/off/probe）。
    // getElementById 按 id 惰性建元素，class 选择器没有对应物，故同样惰性建并在 ctx.selectors
    // 回读——SEV-2228 后半要断言「取证失败」标签的显隐，必须有可达的断言面。
    const selectors = new Map();
    const selectorById = sel => {
        if (!selectors.has(sel)) selectors.set(sel, makeElement('class:' + sel));
        return selectors.get(sel);
    };
    const elementById = id => {
        if (!elements.has(id)) {
            const el = makeElement(id);
            (seedClasses[id] || []).forEach(c => el.classList.add(c));
            elements.set(id, el);
        }
        return elements.get(id);
    };
    const document = {
        hidden,
        getElementById: elementById,
        querySelectorAll(sel) {
            if (sel === '.tab') return tabs;
            if (sel === '.view:not(.hidden)') {
                // 只建模「仪表盘可见」这一种情形：dashboard-view 无 hidden 类即视为可见
                const v = elementById('dashboard-view');
                return v.classList.contains('hidden') ? [] : [v];
            }
            return [];
        },
        querySelector(sel) { return /^\.recording-state \.state-\w+$/.test(sel) ? selectorById(sel) : null; },
        addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
        documentElement: makeElement('html'),
        body: makeElement('body'),
    };
    const storage = new Map();
    const sandbox = {
        document,
        localStorage: {
            getItem: k => (storage.has(k) ? storage.get(k) : null),
            setItem: (k, v) => storage.set(k, String(v)),
            removeItem: k => storage.delete(k),
        },
        fetch: makeFetch({
            // 语言：默认 zh_CN；/api/auth/status 与 /api/status 由用例覆盖
            'GET /api/language': { json: { language: 'zh_CN' } },
            'GET /api/auth/status': { json: { auth_required: true, warning: null } },
            ...routes,
        }, fetchLog),
        setTimeout: (fn, ms) => timers.setTimeout(fn, ms),
        clearTimeout: id => timers.clearTimeout(id),
        // M-88①：vm 上下文自带 ECMAScript 内置对象，但**不含** AbortController 这类宿主 API。
        // 不注入则生产代码的 `typeof AbortController !== 'undefined'` 恒假，超时支路整体不可达，
        // 「downloadFile 有没有真的中止请求」这条锁会永远测不到（同 api() 的超时也是同理）。
        AbortController,
        confirm: () => true,
        EventSource: class { constructor() {} close() {} addEventListener() {} },
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(APP_JS, sandbox, { filename: 'web/app.js' });
    const fire = (type, ev) => (docListeners[type] || []).forEach(fn => fn(ev || {}));
    // DOMContentLoaded 之后的启动引导会拉一次 /api/status；随后推进定时器队列把
    // 首次 dashboard 轮询（setTimeout(...,0)）也跑掉，测试才从「已进入稳态」开始。
    fire('DOMContentLoaded');
    await flushMicrotasks();
    return { sandbox, elements, selectors, tabs, fetchLog, timers, document, fire, storage };
}

// 切到仪表盘：tab 点击 → showView('dashboard') → startSSE()/loadLogs()/startLogsPolling()。
// 只推进一轮 tick：跑空会执行回调里新排的下一轮，摧毁「一次 tick = 一次请求」的计数前提
// （本文件多处按请求数增量断言）。
async function gotoDashboard(ctx) {
    const tab = ctx.tabs.find(t => t.getAttribute('data-view') === 'dashboard');
    tab._listeners.click[0].call(tab);
    return tick(ctx);
}

// 切到弹幕监控视图：tab 点击 → startDanmakuPolling() → 每轮 GET /api/danmaku?since=<游标>。
// 与 gotoDashboard 同理只推进一轮，用例才能按「第 N 次轮询」精确安排路由返回值。
async function gotoDanmaku(ctx) {
    const tab = ctx.tabs.find(t => t.getAttribute('data-view') === 'danmaku');
    tab._listeners.click[0].call(tab);
    return tick(ctx);
}

// 推进「一轮轮询」：跑掉当前排队的定时器回调（含其内部发起的 fetch microtask 链）。
// pending.size 归零即队列已空；若回调又排了新定时器，size 非零，留给下一次 tick。
async function tick(ctx) {
    const queued = [...ctx.timers.pending.keys()];
    for (const id of queued) await ctx.timers.runOne(id);
    await flushMicrotasks();
}

// 重复推进直到队列空（或到达上限）；用于「跑完展示性 fetch 链后再断言定时器队列」。
// 注意不能用于轮询中：轮询会自我续期，跑空等于空转，本函数正是为此设了上限。
async function settle(ctx, limit) {
    let n = 0;
    while (ctx.timers.pending.size > 0) {
        if (++n > (limit || 10)) throw new Error('定时器队列未收敛（疑似轮询自激）');
        await tick(ctx);
    }
}

const STATUS_ROUTE = { 'GET /api/status': { json: { monitoring: 1, recording_count: 0, recording: [] } } };
const LOGS_ROUTE = { 'GET /api/logs': { json: { lines: ['line'] } } };

// —— MID-2237：后端不可达提示不得只写进弹幕视图的 #danmaku-stream ————————

test('MID-2237：状态请求失败时仪表盘出现可见告警，而不是只写 #danmaku-stream', async () => {
    // 失效形态：旧实现 markBackendUnreachable 只把「已断开」写进 #danmaku-stream
    // （弹幕视图的元素，仪表盘上根本看不见），且仪表盘没有任何告警元素。
    const ctx = await boot({ routes: { 'GET /api/status': { status: 500, json: { detail: 'boom' } } } });
    await gotoDashboard(ctx);
    const statusWarn = ctx.elements.get('status-warning');
    assert.ok(statusWarn, 'index.html 缺少 #status-warning（仪表盘告警横幅）');
    assert.equal(statusWarn.classList.contains('hidden'), false, '后端不可达时 #status-warning 仍隐藏');
    assert.ok(statusWarn.textContent.trim().length > 0, '#status-warning 文案为空 → 用户看不到任何提示');
    assert.match(statusWarn.textContent, /status_unavailable/, '告警应带出后端错误码，便于用户自查');
});

test('MID-2237：index.html 里 #status-warning 确实位于仪表盘视图内且默认隐藏', () => {
    const dashIdx = INDEX_HTML.indexOf('id="dashboard-view"');
    const warnIdx = INDEX_HTML.indexOf('id="status-warning"');
    const danmakuIdx = INDEX_HTML.indexOf('id="danmaku-view"');
    assert.ok(dashIdx >= 0 && warnIdx >= 0, 'index.html 未找到 #dashboard-view / #status-warning');
    assert.ok(warnIdx > dashIdx, '#status-warning 必须在仪表盘视图内（否则提示落在他处视图中）');
    if (danmakuIdx > 0) assert.ok(warnIdx < danmakuIdx, '#status-warning 落到了弹幕视图区段');
    assert.match(INDEX_HTML.slice(warnIdx - 200, warnIdx + 200), /hidden/, '#status-warning 未默认隐藏');
});

// —— SEV-2228：HTTP 200 + {"error":"status_unavailable"} 不得渲染成假绿 ————

test('SEV-2228：/api/status 以 200 返回 error=status_unavailable 时必须告警', async () => {
    // 失效形态：后端采样失败时返回 HTTP 200 的 {"error":"status_unavailable"}（不是 5xx），
    // 旧 renderStatus 不看 error 字段 → 卡片全画成 '-'、录制表显示「暂无录制」，
    // 用户看到的是「一切正常但数字是横杠」的假绿。
    const ctx = await boot({
        routes: { 'GET /api/status': { json: { error: 'status_unavailable' } } },
    });
    await gotoDashboard(ctx);
    const warn = ctx.elements.get('status-warning');
    assert.equal(warn.classList.contains('hidden'), false, 'status_unavailable 未触发告警（假绿未修）');
    assert.match(warn.textContent, /status_unavailable/);
    const tbody = ctx.elements.get('recording-tbody');
    assert.doesNotMatch(tbody.innerHTML, /暂无录制|No recordings/, '取样失败不得显示「暂无录制」（会误导为真的没有录制）');
});

test('SEV-2228：stale=true 的陈旧快照也要显式告知用户数据可能不是最新', async () => {
    const ctx = await boot({
        routes: { 'GET /api/status': { json: { monitoring: 3, recording_count: 1, recording: [], stale: true } } },
    });
    await gotoDashboard(ctx);
    const warn = ctx.elements.get('status-warning');
    assert.equal(warn.classList.contains('hidden'), false, 'stale 快照未提示（用户会把旧数字当真）');
});

// —— SEV-2221 撤销 / SEV-2228 后半：main_loop_alive 是死路径，「取证失败」改由真信号承担 ——
//
// 原锁「main_loop_alive=false 的告警文案」。2026-09-23 实测证伪：该键读 main.main_loop_ticks，
// 而这个名字在 main.py 里**从未定义、从未自增**（下面第一条用例把它做成了断言，防「以后有人
// 以为还有效」）。键永不下发、前端 `=== false` 分支永不成立——「永不生效的存活信号」比「没有
// 该信号」更危险，后端已把键从契约撤下（见 src/web_api.py::_read_engine_status），前端改用两个
// 真实信号：error（采样抛错）与 stale（超时回退）。

test('SEV-2221 撤销：main_loop_alive 不得再出现在前端、后端或 main.py 任何一侧', () => {
    // 三侧同断言，缺一条就退化成「一半代码还在等一个永不来的键」：① app.js 不再读它（否则
    // 是一条永不成立的判定，还会在 main.py 接线那天静默失效）；② web_api.py 不再有探针实现
    // （否则 _read_engine_status 忘挂键时它就是死码）；③ main.py 仍无轮次计数器——「撤下」的
    // 事实依据。断言的是**代码引用**而非「文件里出现过这个名字」：撤下缘由要写在注释/契约速查里，
    // 按全文 includes 断言会把说明本身打成违规。
    assert.doesNotMatch(APP_JS, /s\.main_loop_alive\b/, 'app.js 仍在读取 main_loop_alive（死路径未清干净）');
    assert.doesNotMatch(APP_JS, /dashboard\.engineStalled/, '该文案只服务于已撤下的分支，四语目录应一并撤下');
    assert.doesNotMatch(WEB_API_PY, /_read_main_loop_alive|_MAIN_LOOP_TICKS_ATTR/,
        'web_api.py 仍留有主循环探针实现：撤下不彻底');
    assert.doesNotMatch(MAIN_PY, /\bmain_loop_ticks\b/,
        'main.py 已定义 main_loop_ticks —— 说明停摆判据的接线点已就绪，'
        + '此时应**重新接上**该键（web_api 挂键 + 前端 === false 判定 + 四语目录），而不是让本用例长红');
});

test('SEV-2221 撤销后面板不得假装知道引擎活着：error 形态要禁用两个录制按钮', async () => {
    // SEV-2228 后半的失效形态：renderRecordingControl 用 `s.engine_alive !== false` 判活，
    // 而采样失败时后端回 HTTP 200 + {"error":"status_unavailable"}——**不带 engine_alive 键**，
    // undefined !== false 判成「活着」，于是面板在完全不知道引擎死活的状态下仍让用户点
    // 「开始/停止录制」（「停止」这条兜底路径尤其不该在取证失败时被当成可用）。
    const ctx = await boot({ routes: { 'GET /api/status': { json: { error: 'status_unavailable' } } } });
    await gotoDashboard(ctx);
    assert.equal(ctx.elements.get('recording-start-btn').disabled, true, '取证失败时「开始录制」仍可点');
    assert.equal(ctx.elements.get('recording-stop-btn').disabled, true, '取证失败时「停止录制」仍可点');
    // 状态标签必须切到「取证失败」，且不得同时留着 on/off 任一态（那是假绿：明说「在录/没在录」）
    const probe = ctx.selectors.get('.recording-state .state-probe');
    const on = ctx.selectors.get('.recording-state .state-on');
    const off = ctx.selectors.get('.recording-state .state-off');
    assert.ok(probe && !probe.classList.contains('hidden'), '未显示「取证失败」标签');
    assert.ok(on.classList.contains('hidden') && off.classList.contains('hidden'),
        '取证失败时仍显示「录制运行中/已停止」之一（把未知说成已知）');
});

test('SEV-2228 后半：stale 陈旧快照与 error 同等对待（两键同样禁用）', async () => {
    // 超时回退走的是另一条分支：HTTP 200 + 完整旧快照 + stale:true，engine_alive 是**上一轮**的
    // true。只看 engine_alive !== false 会认为引擎健康并允许点录制——那是在一份过期证据上
    // 做不可逆操作，与 error 形态同等禁用才是自洽口径。
    const ctx = await boot({
        routes: { 'GET /api/status': { json: { engine_alive: true, recording_enabled: true, monitoring: 1, stale: true } } },
    });
    await gotoDashboard(ctx);
    assert.equal(ctx.elements.get('recording-start-btn').disabled, true, 'stale 快照下「开始录制」仍可点');
    assert.equal(ctx.elements.get('recording-stop-btn').disabled, true, 'stale 快照下「停止录制」仍可点');
    assert.ok(!ctx.selectors.get('.recording-state .state-probe').classList.contains('hidden'),
        'stale 未切到「取证失败」标签');
});

test('SEV-2228 后半反向边界：健康快照不得把按钮锁死（防线不得做成永久禁用）', async () => {
    // 最省事错法是「renderRecordingControl 里一律 disabled」——那既能骗过上面三条用例，
    // 又让面板再也无法开始/停止录制。engine_alive:true 且 recording_enabled:false 时
    // 「开始」必须可用、「停止」必须禁用（后者是既有语义，一并钉住）。
    const ctx = await boot({
        routes: { 'GET /api/status': { json: { engine_alive: true, recording_enabled: false, monitoring: 1, recording: [] } } },
    });
    await gotoDashboard(ctx);
    assert.equal(ctx.elements.get('recording-start-btn').disabled, false, '健康态下「开始录制」被误锁');
    assert.equal(ctx.elements.get('recording-stop-btn').disabled, true, '未在录制时「停止录制」应禁用');
    assert.ok(ctx.selectors.get('.recording-state .state-probe').classList.contains('hidden'),
        '健康态却显示「取证失败」');
    assert.ok(!ctx.selectors.get('.recording-state .state-off').classList.contains('hidden'),
        '健康态未显示「录制已停止」');
});

test('SEV-2221：字段缺失（未接线）一律视为健康，不得把健康面板刷成告警', async () => {
    // 反向锁（撤销后仍成立、且更重要）：现在契约里**没有任何**可选的存活字段，
    // 前端若改用真假值判定（`if (!s.engine_alive)`），每一个不带该键的正常响应都会被刷红。
    const ctx = await boot({ routes: STATUS_ROUTE });
    await gotoDashboard(ctx);
    const warn = ctx.elements.get('status-warning');
    assert.equal(warn.classList.contains('hidden'), true, '缺少 engine_alive 字段时误报告警（假告警）');
});

test('SEV-2221：app.js 对存活字段用 === 严格判定，不得退化为真假值判定', () => {
    // 源码级锁：`if (!s.engine_alive)` 会把 undefined（未带该键的正常快照）判成故障。
    // 旧版还要求 main_loop_alive 用 === false 判定；该键已撤下，继续断言只会逼实现保留
    // 一条永不成立的分支，故改为断言它**不存在**。
    const body = APP_JS.slice(APP_JS.indexOf('function updateStatusWarning'), APP_JS.indexOf('function renderRecordingControl'));
    assert.match(body, /s\.engine_alive\s*===\s*false/, 'updateStatusWarning 未用 === false 判定 engine_alive');
    assert.doesNotMatch(body, /!\s*s\.engine_alive\b/, '存在真假值判定（undefined 会被判成故障）');
    assert.doesNotMatch(body, /main_loop_alive/, 'updateStatusWarning 仍判已被撤下的 main_loop_alive');
});

// —— SEV-2228 后半：/api/danmaku 的 danmaku_unavailable 前端必须消费 ——————————

test('SEV-2228 后半：/api/danmaku 回 error=danmaku_unavailable 时不得清空房间表，必须显式说明', async () => {
    // 失效形态：后端采样失败回 HTTP 200 + {rooms:[], messages:[], last_seq:<原 since>,
    // error:'danmaku_unavailable'}。旧 renderDanmaku 不看 error：rooms 为空 → 房间表被刷成
    // 「暂无监控数据」、筛选下拉重建为只剩「全部房间」且当前选择被静默丢掉，
    // 用户以为监控真的断了或自己筛错了房间，而真实原因是一次内部异常。
    const roomRow = { name: '小乃', platform: '快手直播', connected: true, msg_total: 3, msg_rate: '1/s', gift_total: 0, online: 1, started_at: '09:00' };
    let n = 0;
    const ctx = await boot({
        routes: {
            'GET /api/danmaku': () => (++n <= 1
                ? { json: { rooms: [roomRow], messages: [], last_seq: 7, truncated: false } }
                : { json: { rooms: [], messages: [], last_seq: 7, truncated: false, error: 'danmaku_unavailable' } }),
        },
    });
    await gotoDanmaku(ctx);
    const tbody = ctx.elements.get('danmaku-rooms-tbody');
    assert.match(tbody.innerHTML, /小乃/, '用例前提不成立：第一轮未渲染出房间行');
    // 第二轮取到的是错误形态：断言它**没有**被当成「真的没有监控数据」
    await gotoDanmaku(ctx);
    assert.match(tbody.innerHTML, /小乃/, '采样失败把已有房间表刷空（用户误判为监控断了）');
    const stream = ctx.elements.get('danmaku-stream');
    assert.match(stream.textContent, /danmaku_unavailable/, '未在消息流上显式说明取不到（静默降级）');
});

test('SEV-2228 后半：danmaku_unavailable 不得推进增量游标（否则跳过失败期间的消息）', async () => {
    // 游标 dmLastSeq 只能由**成功**响应的 last_seq 推进。错误形态里 last_seq 虽等于 since
    // （后端刻意如此），但这条锁防的是「无条件把 data.last_seq 写进游标」的实现漂移——一旦
    // 后端在错误分支带回更大的值，就会静默丢掉那段弹幕。需三轮才锁得住：req2 的 path 由 req1
    // （成功，last_seq:7）决定，验证成功必须推进；req3 的 path 才反映 req2（error，刻意带
    // last_seq:99）有没有被误用。
    let n = 0;
    const ctx = await boot({
        routes: {
            'GET /api/danmaku': () => (++n <= 1
                ? { json: { rooms: [], messages: [], last_seq: 7, truncated: false } }
                : { json: { rooms: [], messages: [], last_seq: 99, truncated: false, error: 'danmaku_unavailable' } }),
        },
    });
    await gotoDanmaku(ctx);  // req1 → 成功 last_seq:7
    await gotoDanmaku(ctx);  // req2 → 拿到 error（last_seq:99）；其 path 由 req1 结果决定
    await gotoDanmaku(ctx);  // req3 → 其 path 才暴露「req2 的 error 有没有把游标推到 99」
    const calls = ctx.fetchLog.filter(r => r.path.startsWith('/api/danmaku'));
    assert.equal(calls.length, 3, '轮询次数与用例安排不符（前提不成立）: ' + JSON.stringify(ctx.fetchLog.map(x => x.path)));
    // 首轮从 0 起；req2 必须带上 req1 成功推进出的 since=7。
    assert.match(calls[0].path, /since=0$/, `首轮游标未从 0 起: ${JSON.stringify(calls.map(c => c.path))}`);
    assert.match(calls[1].path, /since=7$/, `成功响应的 last_seq 未推进游标: ${JSON.stringify(calls.map(c => c.path))}`);
    // 关键不变量：req2 的 error 响应带着更大的 last_seq:99，但错误分支不得推进游标——
    // req3 仍须是 since=7。若退化成无条件写 data.last_seq，这里会变成 since=99（静默丢掉 7→99 段的弹幕）。
    assert.match(calls[2].path, /since=7$/, `错误响应的 last_seq 被用于推进游标: ${JSON.stringify(calls.map(c => c.path))}`);
});


// —— M-23：弹幕折叠计数也必须过 esc()，拼接路径不得留裸插值 ——————

test('M-23：/api/danmaku 的 dropped 计数进 innerHTML 前必须转义（拼接路径一律 esc 的不变量）', async () => {
    // 失效形态：dmLineHtml 里 user/room/text 全过 esc()，唯独 dropped 是裸插值。后端当前把
    // dropped 写成 int（src/danmaku_monitor.py 的采样折叠计数），现网不可利用；但契约一变
    // （改成带标记的可读串或服务端拼文案）这里就是弹幕流的存储型注入点。用例按字符串形态喂，
    // 直接锁转义层，不依赖后端今天写什么类型。
    const hostile = '<img src=x onerror=alert(1)>';
    const ctx = await boot({
        routes: {
            'GET /api/danmaku': {
                json: {
                    rooms: [{ name: 'r1', platform: '抖音直播', connected: true, msg_total: 1, msg_rate: 1, gift_total: 0, online: 1, started_at: '' }],
                    messages: [{ ts: 1700000000, room: 'r1', type: 'chat', user: 'u1', text: 'hello', dropped: hostile }],
                    last_seq: 1,
                    truncated: false,
                },
            },
        },
    });
    await gotoDanmaku(ctx);
    const html = ctx.elements.get('danmaku-stream').innerHTML;
    assert.ok(html.includes('&lt;img'), 'dropped 未转义（渲染出的 innerHTML 里没有实体化的 <img）: ' + html);
    assert.ok(!html.includes('<img'), 'dropped 以裸插值进了 innerHTML —— 弹幕流存储型注入点');
    // 同函数其余字段的转义口径不得被「顺手优化」掉
    assert.ok(html.includes('r1') && html.includes('hello'), '用例前提失效：该行没渲染出来');
});

// —— SEV-2227：visibilitychange 后轮询必须自愈 ————————————————

test('SEV-2227：隐藏后回到前台，/api/status 轮询继续增长（不得永久停摆）', async () => {
    // 失效形态：旧实现隐藏时 stopSSE() 把 sseStopped 置 true，回前台的
    // `if (!sseStopped) startSSE()` 恒假 → 轮询永不恢复，面板数字冻结在切走前那一帧。
    const ctx = await boot({ routes: STATUS_ROUTE });
    await gotoDashboard(ctx);
    const statusCalls = () => ctx.fetchLog.filter(r => r.path === '/api/status').length;
    const before = statusCalls();
    assert.ok(before >= 1, '进入仪表盘未发出任何 /api/status 请求（用例前提不成立）');

    // 切走 → 回前台，两轮
    ctx.document.hidden = true;
    ctx.fire('visibilitychange');
    ctx.document.hidden = false;
    ctx.fire('visibilitychange');
    await tick(ctx);
    const afterFirst = statusCalls();
    await tick(ctx);
    const afterSecond = statusCalls();

    assert.ok(afterFirst > before, '回到前台后没有补拉状态（恢复分支未生效）');
    assert.ok(afterSecond > afterFirst, '回到前台后轮询不再继续排期（SEV-2227 回归：轮询永久停摆）');
});

test('SEV-2227：隐藏期间必须真正停掉轮询（不得退化为「隐藏也照发请求」）', async () => {
    // 反向锁：修 SEV-2227 最省事的错法是「隐藏时什么都不停」，那样后台标签页会持续请求。
    const ctx = await boot({ routes: STATUS_ROUTE });
    await gotoDashboard(ctx);
    const before = ctx.fetchLog.filter(r => r.path === '/api/status').length;
    ctx.document.hidden = true;
    ctx.fire('visibilitychange');
    await tick(ctx);
    await tick(ctx);
    assert.equal(ctx.fetchLog.filter(r => r.path === '/api/status').length, before,
        '页面隐藏期间仍在发 /api/status 请求');
    assert.equal(ctx.timers.pending.size, 0, '页面隐藏后仍有定时器在排队');
});

test('SEV-2227：切离仪表盘（非隐藏）不得留下轮询定时器，且切回不得双份轮询', async () => {
    const ctx = await boot({ routes: STATUS_ROUTE });
    await gotoDashboard(ctx);
    const cfgTab = ctx.tabs.find(t => t.getAttribute('data-view') === 'config');
    cfgTab._listeners.click[0].call(cfgTab);
    // showView('config') → loadConfig() 的 fetch 链仍在飞（它内部会排一次展示性定时器），
    // 必须让它彻底跑完再看队列——否则量到的是 loadConfig 的残留而不是状态/日志轮询。
    await settle(ctx);
    assert.equal(ctx.timers.pending.size, 0, '切离仪表盘后仍有定时器（状态/日志轮询未停）');

    // 切回仪表盘后再单独发一次可见性事件：不得叠出第二条轮询链（否则请求数翻倍）
    const dashTab = ctx.tabs.find(t => t.getAttribute('data-view') === 'dashboard');
    dashTab._listeners.click[0].call(dashTab);
    await flushMicrotasks();
    ctx.fire('visibilitychange');
    await flushMicrotasks();
    const before = ctx.fetchLog.filter(r => r.path === '/api/status').length;
    await tick(ctx);
    const after = ctx.fetchLog.filter(r => r.path === '/api/status').length;
    assert.ok(after - before <= 1, `一轮推进后续期了 ${after - before} 次状态请求（疑似双份轮询）`);
});

// —— MID-2240：仪表盘日志轮询 ————————————————————————————

test('MID-2240：停留在仪表盘上日志会继续刷新（不再只拉一次）', async () => {
    // 失效形态：旧实现只在 showView('dashboard') 里 loadLogs() 一次，
    // 用户不切视图就永远看不到新日志，「实时日志」名不副实。
    const ctx = await boot({ routes: { ...STATUS_ROUTE, ...LOGS_ROUTE } });
    await gotoDashboard(ctx);
    const logsCalls = () => ctx.fetchLog.filter(r => r.path.startsWith('/api/logs')).length;
    const before = logsCalls();
    assert.ok(before >= 1, '进入仪表盘未拉日志');
    await tick(ctx);
    const middle = logsCalls();
    await tick(ctx);
    assert.ok(middle > before && logsCalls() > middle, '日志请求数未持续增长 → 日志不再刷新（MID-2240 回归）');
});

test('MID-2240：日志轮询节拍必须严格慢于状态轮询（/api/logs 是读文件，不能同频/更频）', () => {
    // 源码级锁：/api/logs 是读文件（比 /api/status 的缓存快照重得多），节拍必须严格更大。
    // 断言 `>`（不是 `>=`）：把 LOGS_POLL_INTERVAL 调到与 SSE_OK_INTERVAL 同值也是缺陷形态。
    const logsIv = APP_JS.match(/var LOGS_POLL_INTERVAL\s*=\s*(\d+)/);
    const sseIv = APP_JS.match(/var SSE_OK_INTERVAL\s*=\s*(\d+)/);
    assert.ok(logsIv && sseIv, '未找到 LOGS_POLL_INTERVAL / SSE_OK_INTERVAL');
    assert.ok(Number(logsIv[1]) > Number(sseIv[1]),
        `日志轮询节拍 ${logsIv[1]}ms 未严格大于状态轮询 ${sseIv[1]}ms（会放大磁盘读压力）`);
});

test('MID-2240：页面隐藏时日志轮询一并停止', async () => {
    const ctx = await boot({ routes: { ...STATUS_ROUTE, ...LOGS_ROUTE } });
    await gotoDashboard(ctx);
    const before = ctx.fetchLog.filter(r => r.path.startsWith('/api/logs')).length;
    ctx.document.hidden = true;
    ctx.fire('visibilitychange');
    await tick(ctx);
    await tick(ctx);
    assert.equal(ctx.fetchLog.filter(r => r.path.startsWith('/api/logs')).length, before,
        '页面隐藏期间仍在拉日志');
});

// —— M-21：轮询链的「停止 → 立即重启」竞态 ——————————————————
//
// 失效形态（机制见 web/app.js 的 makePollChain 头注释）：stop* 只能 clearTimeout 掉**已排期**的
// 定时器，取消不了**在途**请求；旧请求落地后的续期回调只看一个布尔标志，而「停止 → 立即重启」
// 已把标志置回「在跑」——旧链于是再排一次 setTimeout 并顶掉模块级 timer 变量，两条链只剩一条
// 可被 stop* 回收，另一条持续发请求。三条链（/api/status、/api/logs、/api/danmaku）各锁一条：
// 机制共用一份（makePollChain），代次是每链各自的，只修一条时另外两条仍会红。

test('M-21：状态轮询在「隐藏 → 立即回前台」里落地的在途请求不得排出第二条轮询链', async () => {
    const status = makeInflight({ monitoring: 1, recording_count: 0, recording: [] });
    const ctx = await boot({ routes: { 'GET /api/status': status.route, ...LOGS_ROUTE } });
    // 引导期 starter 的那次 /api/status 成功后才会 showView('dashboard') 起链，先放行它
    await status.releaseNext();
    await tick(ctx);
    assert.ok(status.calls() >= 2, `用例前提失效：仪表盘轮询未起来（只调了 ${status.calls()} 次）`);
    const inFlightBefore = status.inflight();
    assert.equal(inFlightBefore, 1, '用例前提失效：应恰有一个在途 /api/status 请求');

    // 隐藏 → 立即回前台：pauseSSE(bump 代次) + startSSE(起新链)，而上面那个请求**还没落地**
    ctx.document.hidden = true;
    ctx.fire('visibilitychange');
    ctx.document.hidden = false;
    ctx.fire('visibilitychange');
    // 旧一代此刻落地：健康实现里它既不渲染、也不续期
    await status.releaseNext();

    const before = status.calls();
    await tick(ctx);
    assert.equal(
        status.calls() - before,
        1,
        `一轮推进发了 ${status.calls() - before} 次 /api/status（应为 1）—— 旧链未被回收，两条链并存`
    );
});

test('M-21：日志轮询在「切离仪表盘 → 立即切回」里落地的在途请求不得排出第二条轮询链', async () => {
    const logs = makeInflight({ lines: ['line'] });
    const ctx = await boot({ routes: { ...STATUS_ROUTE, 'GET /api/logs': logs.route } });
    // 引导期 showView('dashboard') 里那次**直接** loadLogs() 也命中本路由：先放行它，
    // 剩下的那个在途请求才是日志链的一轮（只有它的续期回调会被代次判据拦住）。
    await logs.releaseNext();
    await tick(ctx);
    assert.equal(logs.inflight(), 1, '用例前提失效：日志链未留下一个在途请求');

    // 切到配置视图（stopLogsPolling）再立刻切回（startLogsPolling）：上面那个请求仍未落地。
    // 这里刻意走 tab 切换而非 visibilitychange——桩里的 querySelector('.view:not(.hidden)') 返回
    // **数组**，app.js 按单个元素读 visibleView.id，故「回前台重启日志/弹幕链」分支在本沙箱里
    // 命中不了。属既有桩保真度缺口（已记入报告），不在这里顺手改桩。
    clickTab(ctx, 'config');
    clickTab(ctx, 'dashboard');
    await logs.releaseNext();

    const before = logs.calls();
    await tick(ctx);
    assert.equal(
        logs.calls() - before,
        1,
        `一轮推进发了 ${logs.calls() - before} 次 /api/logs（应为 1）—— /api/logs 是读文件，双链会成倍放大磁盘压力`
    );
});

test('M-21：弹幕轮询重进视图时在途请求落地不得排出第二条链，也不得推进增量游标', async () => {
    // 第 1 次调用（将成为过期那一轮）带回可辨识的载荷：last_seq=42 与一个专属房间名
    const dm = makeInflight(call =>
        call === 1
            ? { rooms: [{ name: 'stale-room', platform: '抖音直播' }], messages: [], last_seq: 42 }
            : { rooms: [], messages: [], last_seq: 42 }
    );
    const ctx = await boot({ routes: { 'GET /api/danmaku': dm.route } });
    await gotoDanmaku(ctx);
    assert.equal(dm.inflight(), 1, '用例前提失效：应恰有一个在途 /api/danmaku 请求');

    // 重进弹幕视图：showView 先 stopDanmakuPolling 再 startDanmakuPolling（新链已排期，旧请求在途）
    clickTab(ctx, 'danmaku');
    assert.equal(ctx.timers.pending.size, 1, '用例前提失效：新链应恰好排了一个定时器');
    await dm.releaseNext();

    // ① 不得再排期：队列里仍只有新链那一个定时器
    assert.equal(
        ctx.timers.pending.size,
        1,
        `旧一代落地后排了 ${ctx.timers.pending.size} 个定时器（应为 1）—— 两条弹幕链并存且只有一条可被回收`
    );
    // ② 过期轮次不得推进游标：下一条请求必须仍是 since=0，而不是被 stale 响应的 last_seq=42 带走
    const pathsBefore = ctx.fetchLog.filter(r => r.path.startsWith('/api/danmaku')).length;
    await tick(ctx);
    const paths = ctx.fetchLog.filter(r => r.path.startsWith('/api/danmaku')).map(r => r.path);
    assert.equal(paths.length, pathsBefore + 1, '一轮推进应恰好多发一条 /api/danmaku 请求');
    assert.equal(paths[paths.length - 1], '/api/danmaku?since=0',
        '过期轮次把增量游标推进到 42 —— 42 之前取到的消息会被新链跳过');
});

// —— MID-2253：已翻译模板不得混入中文常量值 ————————————————

test('MID-2253：i18n.tr 模板的字符串实参不得是中文常量（其它语言下会中英混杂）', () => {
    // 失效形态：tr("[web] 认证: {web_auth_enable}", web_auth_enable="开启" if ... else "关闭")——
    // 模板被翻译成「Authentication: {web_auth_enable}」而值仍是中文 → en_US 下中英混杂，
    // 中文下完全看不出。锁做成**文件无关**：任何 i18n.tr(...) 里出现「中文常量 + 无 tr 包装」即判红。
    const files = ['web.py', 'src/web_api.py'];
    const offenders = [];
    for (const rel of files) {
        const src = readFileSync(new URL('../../' + rel, import.meta.url), 'utf8');
        // 逐行看：行内含 i18n.tr( 且含中文字符串字面量，但该字面量没有被 i18n.tr( 紧邻包裹
        for (const [i, line] of src.split('\n').entries()) {
            if (line.trim().startsWith('#')) continue;
            if (!/i18n\.tr\(/.test(line)) continue;
            // 找出所有中文字符串字面量，排除那些本身作为 tr 的模板（tr("...") 的首个实参）
            for (const m of line.matchAll(/(?:^|[^.\w])(["'])([^"']*[\u4e00-\u9fff][^"']*)\1/g)) {
                const at = m.index + m[0].indexOf(m[1]);
                // 模板实参：紧跟在 tr( 之后（允许空白）
                const before = line.slice(0, at);
                const isTemplate = /i18n\.tr\(\s*$/.test(before);
                if (!isTemplate) offenders.push(`${rel}:${i + 1}: ${line.trim()}`);
            }
        }
    }
    // 去重（同一行可能命中多次）
    assert.deepEqual([...new Set(offenders)], [],
        'i18n.tr 模板里插入了中文常量值（非模板实参），其它语言下会中英混杂');
});

test('MID-2253：web.py 认证开关播报必须走 i18n.tr 或字面量目录，不得内联中文条件式', () => {
    // web.py 是组 G 独占文件；此锁直接钉住该行的写法形态。
    // 只查**代码行**：修复注释里会引用旧写法原文（那正是「就地改正 + 说明」的要求），
    // 注释行不算违规。
    const webPy = readFileSync(new URL('../../web.py', import.meta.url), 'utf8');
    const code = webPy.split('\n').filter(l => !l.trim().startsWith('#'));
    const line = code.find(l => l.includes('web_auth_enable='));
    assert.ok(line, 'web.py 未找到 web_auth_enable= 播报行');
    const rhs = line.slice(line.indexOf('web_auth_enable=') + 'web_auth_enable='.length);
    assert.doesNotMatch(rhs, /[\u4e00-\u9fff]/, `认证播报仍内联中文值: ${line.trim()}`);
    // 值必须来自 i18n.tr（本地化字面量），不能是裸布尔（会渲染成 True/False）
    assert.match(rhs, /i18n\.tr\(|_auth_text|^\s*\w+\s*$/, '认证播报的值未走本地化，其它语言下不可读');
});

// —— MIN-2237：前端 isSensitiveField 判定顺序必须与后端 is_sensitive_item 逐字对齐 ————

test('MIN-2237：敏感节命中必须优先于 NOT_SECRET_KEY_RE 例外（顺序与后端一致）', () => {
    // 失效形态：原实现把例外表提到最前短路（NOT_SECRET_KEY_RE 先 return false），而后端是
    // section 命中在前、例外只在 is_sensitive_key 内部 → `[Cookie] 抖音cookie有效期` 这类键
    // 后端脱敏、前端渲染成明文 text，用户误读成「没被保护」。断言顺序而非结果：节命中必须
    // 在例外之前返回 true。
    const fn = APP_JS.match(/function isSensitiveField\(section, key\) \{[\s\S]*?\n    \}/);
    assert.ok(fn, '未找到 isSensitiveField');
    const body = fn[0];
    const sectionIdx = body.indexOf('SENSITIVE_SECTIONS[section]');
    const notSecretIdx = body.indexOf('NOT_SECRET_KEY_RE.test(key)');
    assert.ok(sectionIdx >= 0 && notSecretIdx >= 0, 'isSensitiveField 缺少节判定或例外判定');
    assert.ok(sectionIdx < notSecretIdx,
        'isSensitiveField 的例外表仍在节判定之前短路 → 与后端 is_sensitive_item 顺序分叉');
});

// —— MID-2238：storage 访问必须走安全封装，init 不得因隐私模式整段中断 ————————————

test('MID-2238：app.js 不存在裸 localStorage/sessionStorage 访问（除封装内部）', () => {
    // 失效形态：initTheme() 是 DOMContentLoaded 回调第一条语句，裸 localStorage 在
    // Safari 无痕/「禁用站点数据」下抛异常 → 后续 tab、按钮、事件委托、引导监听器一个都不注册。
    // 锁法：白名单只有 _tokenStore/safeGetItem/safeSetItem 三个封装函数体允许直接接触 storage。
    const lines = APP_JS.split('\n');
    const offenders = [];
    let inWrapper = false;
    for (const [i, line] of lines.entries()) {
        const trimmed = line.trim();
        if (trimmed.startsWith('//')) continue;
        if (/^function\s+(_tokenStore|safeGetItem|safeSetItem)\s*\(/.test(trimmed)) inWrapper = true;
        else if (inWrapper && trimmed === '}') inWrapper = false;
        if (inWrapper) continue;
        if (/(?<![\w.])(localStorage|sessionStorage)\b/.test(line)
            && !/typeof\s+(localStorage|sessionStorage)/.test(line)) {
            offenders.push(`app.js:${i + 1}: ${trimmed}`);
        }
    }
    assert.deepEqual(offenders, [], '存在裸 storage 访问（隐私模式下会抛异常带走整个 init 回调）');
});

test('MID-2238：initTheme 与 initLanguage 各自 try/catch，单点失败不得带走后续绑定', () => {
    // 只要 initTheme 内部出现 try/catch，隐私模式下的 storage 异常就不会中断 DOMContentLoaded。
    const fn = APP_JS.match(/function initTheme\(\) \{[\s\S]*?\n    \}/);
    assert.ok(fn, '未找到 initTheme');
    assert.match(fn[0], /try\s*\{/, 'initTheme 未包 try/catch（storage 异常会中断整个 DOMContentLoaded）');
});

// —— MID-2239：PUT /api/language 必须消费生效码与回退说明 ————————————————

test('MID-2239：语言切换必须按响应里的 language（生效码）更新，不得回写请求值', () => {
    // 失效形态：`.then(function () { currentLang = target; ... })` —— 形参被丢掉、恒按请求值本地切换。
    // 后端可能回退（如 PyYAML 缺失使 zh_TW 装载不到 → 实际生效 en_US），前端必须以后端回的生效码为准。
    assert.match(APP_JS, /currentLang\s*=\s*\(res\s*&&\s*res\.language\)\s*\|\|\s*target/,
        '未按响应 language 生效码更新 currentLang');
    assert.match(APP_JS, /res\.fallback/, '未消费 fallback 标记，回退说明不会显示给用户');
    assert.match(APP_JS, /res\.notice/, '未消费后端返回的本地化回退说明 notice');
});

// —— MIN-2239：saveConfig 中途失败必须善后（不得留下「看起来已保存」的界面） ————————

test('MIN-2239：saveConfig 失败分支必须先回拉配置再返回，且标出失败行', () => {
    // 失效形态：失败即 `return`，跳过头注释要防的「半份配置落盘更难排查」——
    // 界面仍是用户填的样子、无任何未保存标记，用户以为已保存直接切走。
    const fn = APP_JS.match(/async function saveConfig\(\) \{[\s\S]*?\n    \}/);
    assert.ok(fn, '未找到 saveConfig');
    const body = fn[0];
    // 失败分支内必须有 await loadConfig()（在 return 之前）
    const catchIdx = body.indexOf("t('config.saveRejected')");
    assert.ok(catchIdx >= 0, 'saveConfig 缺少 400 专用文案分支（既有回归锁依赖它）');
    const after = body.slice(catchIdx);
    const returnIdx = after.indexOf('return;');
    assert.ok(returnIdx >= 0, 'saveConfig 失败分支缺少 return');
    assert.ok(after.slice(0, returnIdx).includes('await loadConfig()'),
        'saveConfig 失败分支未回拉服务端真值就 return → 界面停留在「看起来已保存」的假象');
    assert.ok(after.slice(0, returnIdx).includes('markRowFailed'),
        'saveConfig 失败分支未标出失败行 → 用户不知道哪一项没保存');
});

test('MIN-2239：index.html 提供常驻保存状态行 #config-save-status 且默认隐藏', () => {
    const idx = INDEX_HTML.indexOf('id="config-save-status"');
    assert.ok(idx >= 0, 'index.html 缺少 #config-save-status（常驻失败明细；toast 会消失且被覆盖）');
    assert.match(INDEX_HTML.slice(idx - 120, idx + 160), /hidden/, '#config-save-status 未默认隐藏');
});

// —— MIN-2238：downloadFile 失败必须解析 detail，不得用恒空的 statusText ————————

test('MIN-2238：downloadFile 失败分支不得使用 res.statusText（HTTP/2 下恒为空串）', () => {
    // 失效形态：`if (!res.ok) throw new Error(res.statusText)` →
    // 现代浏览器对 reason phrase 恒给空串，toast 渲染成「下载失败: 」，用户拿不到任何可报障信息。
    const fn = APP_JS.match(/window\.downloadFile = function \(path\) \{[\s\S]*?\n    \};/);
    assert.ok(fn, '未找到 downloadFile');
    const body = fn[0].split('\n').filter(l => !l.trim().startsWith('//')).join('\n');
    assert.doesNotMatch(body, /res\.statusText/, 'downloadFile 仍用 statusText 抛错（恒为空串）');
    assert.match(body, /apiError\(/, 'downloadFile 失败分支未复用 apiError 解析 detail');
});

// —— MID-2241：认证两键改动必须二次确认 + 复验口令 ————————————————

test('MID-2241：saveConfig 对 Web 认证两键先 confirm 再要求复验口令', () => {
    // 失效形态：这两键走与「循环时间(秒)」完全相同的普通写入通道，前后端都零确认——
    // 一次 PUT 即可关掉认证或改写口令（连带踢掉全部在线会话），且该降级不随 token 吊销回滚。
    const fn = APP_JS.match(/async function saveConfig\(\) \{[\s\S]*?\n    \}/);
    assert.ok(fn, '未找到 saveConfig');
    const body = fn[0];
    assert.match(body, /key === 'web_auth_enable' \|\| key === 'web_password'/,
        'saveConfig 未对认证两键做特殊处理（缺少确认/复验入口）');
    const guardIdx = body.search(/key === 'web_auth_enable'/);
    const confirmIdx = body.indexOf('confirm(t(\'config.authChangeConfirm\')', guardIdx);
    assert.ok(confirmIdx > guardIdx, '认证两键改动未弹二次确认');
    const promptIdx = body.indexOf('config.authChangeReauth', guardIdx);
    assert.ok(promptIdx > confirmIdx, '认证两键改动未要求复验口令');
    assert.match(body, /body\.reauth_password\s*=\s*\w+/, '复验口令未随请求下发');
    // 反向边界：其余键的请求体不得被污染（既有回归锁按整体 deepEqual 断言 body 形状）
    assert.match(body, /var body = \{ section: section, key: key, value: newVal \};/,
        '请求体基础形状被改动（会破坏其余配置键的既有请求契约）');
});

test('M-22/M-26：认证两键的复验口令经 password 弹窗采集、且只随认证键下发（正向锁）', () => {
    // 契约事实源是生产代码：src/web_api.py::update_config 的 MID-2241 段已实现强制复验（认证开启时
    // 写认证两键不带可过 verify_web_password 的 reauth_password 即 403），本条因此锁定「前端确实
    // 采集并下发」。[历史注] 此前两条 doesNotMatch 文本锁因后端字面量改名而**空洞成立**（实测 32/32
    // 全绿，而 Python 侧锁的恰是相反契约），故：① 不再以源码字面量锁安全边界；② 后端行为
    // 不在本文件复制，已由 test_regression_web_g.py::TestAuthKeyReauth 与
    // test_web_api.py::TestAuthDowngradeRejected 用真实端点 E2E 锁住；③ 前端保留这条正向断言，
    // 端到端行为另见 tests/frontend/test_auth_reauth.mjs。
    const fn = APP_JS.match(/async function saveConfig\(\) \{[\s\S]*?\n    \}/);
    assert.ok(fn, '未找到 saveConfig');
    const body = fn[0];
    const guardIdx = body.search(/key === 'web_auth_enable'/);
    assert.ok(guardIdx >= 0, 'saveConfig 里已没有认证两键的判定（正向锁的前提失效）');
    const confirmIdx = body.indexOf("confirm(t('config.authChangeConfirm')", guardIdx);
    assert.ok(confirmIdx > guardIdx, '认证两键改动未弹二次确认');
    const askIdx = body.indexOf('askReauthPassword(', guardIdx);
    assert.ok(askIdx > confirmIdx, '认证两键改动未采集复验口令（复验链断在确认之后）');
    // 下发：既要有赋值，也要落在「本行是认证键」的守卫之下——M-22 的失效形态正是循环外粘变量
    // （一旦赋值，本次保存的其余配置键 PUT 都带 reauth_password，口令暴露面被扩大）
    assert.match(body, /body\.reauth_password\s*=\s*authReauth/, '复验口令未随请求下发');
    assert.match(body, /if \(isAuthKey && authReauth\)/,
        'reauth_password 的下发不再以「本行是认证键」为判据 → 会被其余配置键捎带');
    // 采集形态：saveConfig 内不得再有 window.prompt（明文回显）。判据剥掉行注释后再看——本函数
    // 的沿革注释里写着旧形态名，不剥会把注释当成代码命中（同 downloadFile 那条的既有口径）。
    const code = body.split('\n').filter(l => !l.trim().startsWith('//')).join('\n');
    assert.ok(!code.includes('window.prompt'),
        'saveConfig 又用回 window.prompt 采集复验口令（M-22 回归：必须走 type="password" 弹窗）');
    // 载荷字段仍存在（正向 presence 断言：字段没了前端的 reauth 就会被后端静默丢弃 → 永远 403）
    assert.match(WEB_MODELS_PY, /reauth_password:\s*str\s*\|\s*None\s*=\s*None/,
        'ConfigUpdate 缺少 reauth_password 可选字段（强制复验契约的载荷载体）');
});

// —— MIN-2241：根 index.html 的远端脚本必须钉内容（SRI），钉版本不足以挡替换 ————————

test('MIN-2241：根 index.html 的每个跨源 <script> 都带 integrity 与 crossorigin', () => {
    // 失效形态：只写 src="https://cdn.jsdelivr.net/npm/hls.js@1.7.2/..."。钉版本 ≠ 钉内容——
    // jsdelivr 上同名同版本的文件仍可被替换，而本页不经 web_api 的 CSP/nosniff 中间件
    //（create_app 只挂 web/index.html 与 /web），是唯一把用户输入流地址直喂 hls.js/flv.js 的页面。
    // 按**每个 script 标签**逐个检查：全文件 grep 会被「一个标签有、另一个没有」蒙混过去。
    const scriptTags = ROOT_INDEX_HTML.match(/<script\b[^>]*\bsrc="https?:\/\/[^"]*"[^>]*>/g) || [];
    assert.ok(scriptTags.length > 0, '根 index.html 未找到任何跨源 script（选择器已漂移）');
    for (const tag of scriptTags) {
        assert.match(tag, /\sintegrity="sha(256|384|512)-[A-Za-z0-9+/=]+"/,
            `跨源脚本未钉内容（缺 integrity）: ${tag}`);
        assert.match(tag, /\scrossorigin=("anonymous"|"")/,
            `缺 crossorigin 会使 SRI 对跨源响应不生效: ${tag}`);
    }
});

test('MIN-2241：integrity 哈希必须是 sha384 且长度为真哈希，不得是占位串', () => {
    // 反向锁：把 integrity 写成 "sha384-x" 之类占位串能让上一条通过，却会让页面整段静默失效
    // （浏览器拒绝执行不匹配的脚本）。sha384 的 base64 定长为 64 字符。
    const hashes = ROOT_INDEX_HTML.match(/integrity="sha384-([A-Za-z0-9+/=]+)"/g) || [];
    assert.ok(hashes.length >= 2, `expected >=2 sha384 integrity, got ${hashes.length}`);
    for (const h of hashes) {
        const b64 = h.slice('integrity="sha384-'.length, -1);
        assert.equal(b64.length, 64, `sha384 base64 长度应为 64，实为 ${b64.length}: ${h}`);
        assert.match(b64, /^[A-Za-z0-9+/]+={0,2}$/, `不是合法 base64: ${h}`);
    }
});

test('MIN-2241：根 index.html 仍未被 Web 面板链路服务（修复不得把它挂进路由）', () => {
    // 反向边界：本条处置是「保留独立工具页 + 补 SRI」，不是接进面板。/ 必须仍指向 web/index.html，
    // 否则 CSP/鉴权/同源判定全被绕开（这正是本条要防的另一半）。
    // 锚点用 \r?\n\r?\n：src/web_api.py 是纯 CRLF，node 的 readFileSync(...,'utf8') 不做换行归一，
    // 写死 \n\n 的「空行」在 CRLF 源上恒不匹配（AGENTS.md「注释检查工具」盲点 3 的现例）。
    const idx = WEB_API_PY.match(/async def index\(\)[\s\S]*?\r?\n\r?\n/);
    assert.ok(idx, '未找到 / 路由');
    assert.match(idx[0], /_WEB_DIR\s*\/\s*"index\.html"/, '/ 未指向 web/index.html');
});

// —— M-84：令牌存储的回退载体必须是内存，绝不再是 localStorage ————————————

test('M-84：sessionStorage 不可用时令牌只进内存，绝不写 localStorage', async () => {
    // 失效形态（M-84）：_tokenStore 的回退分支返回 localStorage —— bearer token（默认 24h 有效）
    // 明文落盘、跨标签页与浏览器重启存活，与「关标签页即失效」的设计目标相反，且 XSS、恶意扩展、
    // 本机任意进程都能读走。本用例刻意**不注入 sessionStorage**（Safari 无痕/禁用站点数据的等价形态），
    // 断言两件事：① 令牌不进 localStorage（落盘面）；② getToken 照常供 api() 使用（功能面不退化）。
    const ctx = await boot({
        routes: {
            'POST /api/login': { json: { token: 'tok-memory' } },
            ...STATUS_ROUTE,
            ...LOGS_ROUTE,
        },
    });
    ctx.elements.get('login-password').value = 'pw';
    ctx.elements.get('login-submit')._listeners.click[0]();
    await flushMicrotasks();
    assert.ok(ctx.fetchLog.some(f => f.method === 'POST' && f.path === '/api/login'), '登录请求未发出');
    assert.equal(ctx.storage.has('dlr_token'), false, '令牌被写进 localStorage（M-84 的明文落盘形态）');
    assert.equal(ctx.storage.size, 0, '回退分支仍把任何键写进 localStorage（应为纯内存载体）');

    await tick(ctx);
    const statusCall = ctx.fetchLog.filter(f => f.path.startsWith('/api/status')).pop();
    assert.ok(statusCall, '登录后没有发起 /api/status 轮询');
    assert.equal(
        statusCall.init.headers.Authorization,
        'Bearer tok-memory',
        '内存回退后 getToken 必须照常把令牌交给 api()（否则本项修好了落盘却打断了登录态）'
    );
});

// —— M-88①：downloadFile 的超时中止（与 api() 同形状）————————————————

test('M-88①：downloadFile 必须带超时中止，后端挂起时请求不得无限 pending', async () => {
    // 失效形态：downloadFile 裸 fetch（无 AbortController/超时），同文件 api() 却已有 API_TIMEOUT_MS
    // 的封装——后端挂起（或大文件迟迟不给响应头）时这条请求无限 pending，没有任何出口。
    const ctx = await boot({
        routes: { 'GET /api/files/download': { hang: true }, ...STATUS_ROUTE, ...LOGS_ROUTE },
    });
    ctx.sandbox.window.downloadFile('downloads/a.flv');
    await flushMicrotasks();
    const call = ctx.fetchLog.find(f => f.path.startsWith('/api/files/download'));
    assert.ok(call, '未发起 /api/files/download 请求');
    assert.ok(call.init && call.init.signal, 'downloadFile 没把 AbortSignal 交给 fetch（不具备中止能力）');
    assert.equal(call.init.signal.aborted, false, '刚发出就已被中止（超时逻辑写反）');

    await tick(ctx); // 推进假定时器：排在那里的 abort 必须真的执行
    await flushMicrotasks();
    assert.equal(call.init.signal.aborted, true, '超时后请求仍未中止（M-88① 的无限 pending 原状）');
    const toastText = ctx.elements.get('toast').textContent;
    assert.match(toastText, /timeout/, `超时中止要给用户可读的失败原因，实际: ${toastText}`);
});

// —— M-88②：e.message 的兜底形态统一 ————————————————————————————

test('M-88②：toast 拼接 e.message 一律带空值兜底（不得把 undefined 显示给用户）', async () => {
    // 失效形态：5 处写成 t('...') + e.message，而 reject 出非 Error 值（字符串/无 message 的对象）
    // 时 toast 显示「删除失败: undefined」；同文件另有若干处已写 (e.message || '')，两套口径并存。
    // 判据取**代码形态的不变量**而非具体文案：剥注释后全文件不允许出现裸的 `+ e.message` 拼接。
    // 这是「同一文件内已统一成一种写法」的一致性锁，不钉任何变量名或错误文案。
    const code = APP_JS.split('\n')
        .filter(l => !l.trim().startsWith('//'))
        .join('\n');
    const bare = code.match(/\+\s*e\.message\s*(?!\|\|)/g) || [];
    assert.deepEqual(bare, [], `仍存在未兜底的 e.message 拼接: ${JSON.stringify(bare)}`);
    assert.ok(code.includes('(e.message || \'\')'), '兜底形态本身不得整体消失（否则上一条恒真）');
});

// —— M-88③：markBackendUnreachable 的恢复分支 ————————————————————

test('M-88③：后端恢复后必须当场还原断开标签，且只在真出现过断开态时改写', async () => {
    // 失效形态：markBackendUnreachable 只有 if (flag) 一支，形参的 false 语义不存在，
    // 「已断开」只能等下一轮渲染顺带覆盖。现补恢复分支（复用既有键 danmaku.connected）。
    // 同时用 _backendMarkedDown 闸门避免健康轮次把弹幕流区域反复改写——两个方向都要锁。
    let mode = 'down';
    const ctx = await boot({
        routes: {
            'GET /api/status': () =>
                mode === 'down' ? { status: 500, json: { detail: 'boom' } } : { json: { monitoring: 1, recording: [] } },
            ...LOGS_ROUTE,
        },
    });
    await gotoDashboard(ctx);
    const stream = ctx.elements.get('danmaku-stream');
    assert.equal(stream.textContent, '已断开', '后端不可达时未写断开标签（MID-2237 既有锁的同一形态）');

    mode = 'up';
    await tick(ctx);
    assert.equal(stream.textContent, '已连接', '后端恢复后未当场还原标签（M-88③ 原状：只能等下一轮覆盖）');

    await tick(ctx);
    assert.equal(stream.textContent, '已连接', '恢复分支必须幂等：健康轮次不得反复改写同一区域');

    mode = 'down';
    await tick(ctx);
    assert.equal(stream.textContent, '已断开', '再次断开要重新提示（闸门不得把状态卡死在「已连接」）');
});

// —— 前端/后端敏感节同源（M-61 增列「推送配置」的前端半边）——————————

test('后端 SENSITIVE_SECTIONS 的每一节，前端都必须渲染成 password 框', async () => {
    // 失效形态：前端另有一份节白名单（web/app.js::SENSITIVE_SECTIONS），后端增列而前端漏改时，
    // 该节内「键名正则看不见」的凭据（如 bark_key）在面板里是明文 text 框——用户一眼看到完整凭据。
    // 判据以**后端那份集合**为输入逐节驱动渲染（不是把两边字面量各写一遍再比字符串），
    // 后端再加节而前端没跟，本条立刻变红；前端多加节则不受本条约束（由后端脱敏口径负责）。
    const py = readFileSync(new URL('../../src/web_config.py', import.meta.url), 'utf8');
    const decl = py.match(/SENSITIVE_SECTIONS\s*=\s*\{([^}]*)\}/);
    assert.ok(decl, '未在 src/web_config.py 找到 SENSITIVE_SECTIONS 定义（判据已漂移）');
    const sections = [...decl[1].matchAll(/["']([^"']+)["']/g)].map(m => m[1]);
    assert.ok(sections.length >= 3, `后端敏感节集合异常（读到 ${sections.length} 个）: ${sections}`);

    // 每节放一个「键名正则与例外表都不命中、值也不是凭据形态」的探针键：
    // 该行渲染成 password 只可能是因为**节白名单**命中，从而与后端集合逐节同真同假。
    const cfg = { 录制设置: { zz_parity_probe: 'plain-value' } };
    for (const section of sections) cfg[section] = { zz_parity_probe: 'plain-value' };
    const ctx = await boot({
        routes: { 'GET /api/config': { json: cfg }, ...STATUS_ROUTE, ...LOGS_ROUTE },
    });
    const tab = ctx.tabs.find(t => t.getAttribute('data-view') === 'config');
    tab._listeners.click[0].call(tab);
    await flushMicrotasks();
    const html = ctx.elements.get('config-container').innerHTML;
    assert.ok(html.includes('zz_parity_probe'), '配置视图未渲染探针行（沙箱或渲染路径已漂移）');
    for (const section of sections) {
        assert.ok(
            html.includes(`type="password" data-section="${section}" data-key="zz_parity_probe"`),
            `后端把「${section}」列为敏感节，前端却渲染成明文输入框（两侧白名单分叉）`
        );
    }
    // 反向边界：白名单外的节不得被顺手打码（否则本条会退化成「全是 password」的无信息断言）。
    assert.ok(
        html.includes(`type="text" data-section="录制设置" data-key="zz_parity_probe"`),
        '非敏感节被误判成 password（判定面被整体放宽）'
    );
});

// —— M-85：StopRecording.vbs 的目录锚点与硬杀前身份复核 ————————————————
//
// 【为什么在这一份 .mjs 里跑 VBScript】本项要锁的是**误杀防护**：唯一算行为锁的写法是把真文件里
// 的函数原文交给 cscript 求值——在测试里用 JS 重写一份匹配逻辑正是「测试自实现被测逻辑」的假绿形态。
// 这类用例的自然归属是 tests/test_stop_recording_vbs.py（它已有同款「抽函数 + cscript」工装），
// 本轮由 web/ 与 .vbs 的负责人代持，后续迁移整段搬过去即可。
// 【安全前提】脚本只跑抽出来的纯函数与「假 shell / 假进程」替身，绝不执行整份 StopRecording.vbs
// （那会真的 taskkill 进程）；临时脚本写在仓库之外（os.tmpdir），跑完即删。
const VBS_PATH = fileURLToPath(new URL('../../StopRecording.vbs', import.meta.url));
const HAS_CSCRIPT = process.platform === 'win32';
const CSCRIPT_SKIP = HAS_CSCRIPT ? false : 'cscript 仅存在于 Windows（环境限制，非失败）';

// 读真文件的编码契约并解码（与 tests/test_stop_recording_vbs.py 同一口径：FF FE BOM 恰好一支 + 全量 CRLF）。
function vbsSourceText() {
    const buf = readFileSync(VBS_PATH);
    assert.ok(buf.length >= 2 && buf[0] === 0xff && buf[1] === 0xfe, 'StopRecording.vbs 必须带 FF FE BOM');
    const text = buf.toString('utf16le');
    assert.equal(text[0], '\ufeff', 'BOM 解码后应为 U+FEFF 首字符');
    assert.notEqual(text[1], '\ufeff', 'StopRecording.vbs 不得出现双重 BOM');
    const body = text.slice(1);
    assert.equal(
        body.split('\n').length,
        body.split('\r\n').length,
        'StopRecording.vbs 必须全量 CRLF，不得出现孤立 LF'
    );
    return body;
}

// 按名字抽「Function/Sub … End Function/Sub」原文块（连同它依赖的辅助函数一起搬进临时脚本）。
function vbsBlock(text, name) {
    const m = text.match(new RegExp('(Function|Sub) ' + name + '\\([\\s\\S]*?\\r\\nEnd \\1'));
    assert.ok(m, `StopRecording.vbs 未找到 ${name}（判据漂移）`);
    return m[0];
}

function vbsQuote(value) {
    return '"' + String(value).replace(/"/g, '""') + '"';
}

// 用与主文件相同的编码写出（cscript 直接识别 UTF-16 LE + BOM，不受系统 ANSI 代码页影响）。
function runVbs(lines) {
    const dir = mkdtempSync(join(tmpdir(), 'dlr-vbs-'));
    const file = join(dir, '_tmp_m85_selftest.vbs');
    try {
        writeFileSync(file, Buffer.from('\ufeff' + lines.join('\r\n') + '\r\n', 'utf16le'));
        return execFileSync('cscript', ['//nologo', file], { encoding: 'utf8', timeout: 120000 });
    } finally {
        rmSync(dir, { recursive: true, force: true });
    }
}

const M85_ANCHOR_CASES = [
    // 【必须仍然命中】真·本程序目录下的 ffmpeg（含带引号、大小写混杂、深层子目录三种形态）
    [String.raw`D:\dlr\ffmpeg.exe -i D:\dlr\downloads\a.flv`, true],
    [String.raw`"D:\dlr\ffmpeg.exe" -i "D:\dlr\in.flv"`, true],
    [String.raw`D:\DLR\record\ffmpeg.exe`, true],
    [String.raw`D:\dlr`, true],
    // 【必须不再命中】M-85 的误杀形态：同名前缀目录（裸子串 + Len(appDir)>3 兜底全部放行）
    [String.raw`D:\dlr-backup\ffmpeg.exe`, false],
    [String.raw`C:\tools\ffmpeg.exe -i D:\dlr-backup\in.flv`, false],
    [String.raw`D:\dlrx\ffmpeg.exe`, false],
    [String.raw`D:\dlr2\x\ffmpeg.exe`, false],
];

test('M-85：短程序目录的锚点必须落在目录边界上（同名前缀目录的 ffmpeg 不得判成本程序）', { skip: CSCRIPT_SKIP }, () => {
    const text = vbsSourceText();
    const lines = [
        'Option Explicit',
        'Dim appDir',
        'Const APP_DIR_KEY = "douyinliverecorder"',
        'appDir = ' + vbsQuote('D:\\dlr'),
        vbsBlock(text, 'IsPathAnchored'),
        vbsBlock(text, 'ContainsAtWordBoundary'),
        vbsBlock(text, 'ContainsAtDirBoundary'),
    ];
    M85_ANCHOR_CASES.forEach(([cmd], i) => {
        lines.push(`WScript.Echo "case${i}=" & CStr(IsPathAnchored(${vbsQuote(cmd)}))`);
    });
    const out = runVbs(lines);
    M85_ANCHOR_CASES.forEach(([, expected], i) => {
        const m = out.match(new RegExp('case' + i + '=(\\w+)'));
        assert.ok(m, `cscript 没有回出 case${i}，输出: ${out}`);
        assert.equal(
            m[1],
            expected ? 'True' : 'False',
            `IsPathAnchored(${M85_ANCHOR_CASES[i][0]}) → ${m[1]}，期望 ${expected}`
        );
    });
});

test('M-85：WMI 失败后不得对「身份无法复核」的 PID 直接 taskkill /f', { skip: CSCRIPT_SKIP }, () => {
    // 失效形态：阶段 2 在 TerminateByWmi 失败（其注释自述「进程已不存在」是常态）后直接
    // objShell.Run "taskkill /f /pid "；而阶段 1 的 taskkill /f /t 已连带结束子进程树、其后又
    // Sleep WAIT_SECONDS，这个 PID 完全可能已被系统重新分配给无关进程 → 硬杀即误杀。
    // 现要求硬杀前按 PID 复核身份。本用例喂给它一个**真实存在、但映像名不是 ffmpeg.exe** 的 PID
    // （正是「PID 已易主」的等价形态），断言假 shell 一条 taskkill 都没收到。
    const text = vbsSourceText();
    const lines = [
        'Option Explicit',
        'Dim objWMIService, objShell, appDir, killLog',
        'Const APP_DIR_KEY = "douyinliverecorder"',
        'Const PROCESS_FFMPEG = "ffmpeg.exe"',
        'appDir = ' + vbsQuote('D:\\dlr'),
        vbsBlock(text, 'IsPathAnchored'),
        vbsBlock(text, 'ContainsAtWordBoundary'),
        vbsBlock(text, 'ContainsAtDirBoundary'),
        vbsBlock(text, 'ProcessIdentityStillMatches'),
        vbsBlock(text, 'TerminateByWmi'),
        vbsBlock(text, 'TerminateProcesses'),
        'Class GoneProc',
        '    Public Function Terminate()',
        '        Terminate = 1',
        '    End Function',
        'End Class',
        'Class SpyShell',
        '    Public Function Run(cmd, windowStyle, waitOnReturn)',
        '        killLog = killLog & "|" & cmd',
        '        Run = 0',
        '    End Function',
        'End Class',
        'Dim svc, col, p, probePid, procs, gp',
        'probePid = 0',
        'Set objWMIService = Nothing',
        'On Error Resume Next',
        // 单点与生产 InitializeWMIService 逐字一致（winmgmts:\\.\root\cimv2）：
        // 写成 winmgmts:root\cimv2 在本机取不到服务对象，probe 恒 0、用例前提不成立。
        'Set svc = GetObject("winmgmts:\\\\.\\root\\cimv2")',
        'On Error GoTo 0',
        'If IsObject(svc) Then',
        // 刻意取 svchost.exe 而不是「任意 Name <> ffmpeg.exe」的第一条：WMI 枚举的第一项是
        // System Idle Process（ProcessID = 0），拿 0 当 PID 会让「不杀」的断言失去意义。
        '    Set col = svc.ExecQuery("Select ProcessID From Win32_Process Where Name = \'svchost.exe\'")',
        '    For Each p In col',
        '        probePid = CLng(p.ProcessID)',
        '        Exit For',
        '    Next',
        '    Set objWMIService = svc',
        'End If',
        'WScript.Echo "probe=" & CStr(probePid)',
        'killLog = ""',
        'Set objShell = New SpyShell',
        'Set procs = CreateObject("Scripting.Dictionary")',
        'Set gp = New GoneProc',
        'procs.Add CLng(probePid), gp',
        'Call TerminateProcesses(procs, False)',
        'WScript.Echo "killlog=" & killLog',
    ];
    const out = runVbs(lines);
    const probe = out.match(/probe=(\d+)/);
    assert.ok(probe, `cscript 未回出 probe 行，输出: ${out}`);
    assert.notEqual(probe[1], '0', '环境上取不到「真实存在且非 ffmpeg」的 PID（本用例前提不成立）');
    const log = out.match(/killlog=([\s\S]*)/)[1].trim();
    assert.equal(log, '', `身份复核未拦住硬杀（对 PID ${probe[1]} 下了 taskkill）: ${log}`);
});

test('M-85 结构不变量：ffmpeg 支路唯一的裸 taskkill 必须在身份复核之内', () => {
    // 上面两条 cscript 行为锁在非 Windows 上会 skip（CI 的 linux runner 也 skip），故这里补一道
    // **不变量**形态的结构锁（不是钉某个变量名或某句文案）：killTree=False 支路里，
    // `objShell.Run "taskkill /f /pid "` 这条语句必须出现在 ProcessIdentityStillMatches 的守卫之内。
    // 判据只看语句行：VBScript 注释行（' 开头）里出现同样的命令名是正常的沿革说明，
    // 不剥掉就会把注释当成语句、把「复核写在注释里」误判成「复核写在 taskkill 之后」。
    // killTree=True（录制主进程支路，另有 rc<>128 守卫）不在本项范围内，故从第一个 Else 起切片。
    const lines = vbsBlock(vbsSourceText(), 'TerminateProcesses')
        .split('\r\n')
        .filter(l => !l.trim().startsWith("'"));
    const elseIdx = lines.findIndex(l => l.trim() === 'Else');
    assert.ok(elseIdx >= 0, 'TerminateProcesses 缺少 killTree=False 支路');
    const branch = lines.slice(elseIdx + 1).join('\r\n');
    const runIdx = branch.indexOf('objShell.Run "taskkill /f /pid');
    assert.ok(runIdx >= 0, 'killTree=False 支路未找到 taskkill /f /pid 回退（结构已漂移）');
    const guardIdx = branch.indexOf('If ProcessIdentityStillMatches(');
    assert.ok(guardIdx >= 0, 'M-85 回归：身份复核未接进 killTree=False 支路');
    assert.ok(guardIdx < runIdx, 'M-85 回归：身份复核写在 taskkill 之后（先杀后查＝没有查）');
    assert.match(branch.slice(guardIdx, runIdx), /Then/, 'M-85 回归：复核结果没有作为 taskkill 的条件（只查不判）');
});
