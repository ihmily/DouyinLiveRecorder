// web/app.js 面板前端用例的统一入口（Node 内置 node:test，零 npm 依赖）。
//
// 【为什么用 node:vm 沙箱而非 jsdom】仓库无 package.json / 前端构建链，为一个 IIFE 页面脚本
// 引入 jsdom 会带来整条 npm 依赖树，与「纯 Python 仓库 + 运行时自带 Node」的定位不符。app.js
// 状态全部封闭在 IIFE 内（仅 window.toggleRoom 等少数导出），沙箱以 DOM/fetch 桩手动触发
// DOMContentLoaded，经真实事件委托链路驱动（tab → showView → 渲染 → 事件 → PUT → toast/回拉），
// 既不改生产代码，也覆盖真实接线而非孤立函数。
//
// 【桩的最小集合】app.js 加载期零副作用，初始化只触及 document / window / localStorage / sessionStorage
// （M-84：token 走 sessionStorage 主路径、两者都不可用时退内存；fetch /
// setTimeout / clearTimeout / confirm / EventSource（SSE 路径，本测试不进入）。setTimeout 桩为
// 「排队但不自跑」：toast 自动隐藏与轮询递归都不执行，用例完全确定；需要驱动弹幕轮询的用例显式
// 调 runTimers。Promise 微任务不受影响。
//
// 【启动引导走向】GET /api/status 固定回 401：api() 走 showLogin（不构造 EventSource、不启动
// 仪表盘轮询），得到静止的登录态应用；随后注入测试 token、点击目标 tab。语言由
// GET /api/language 控制，四语文案走行为级断言而非源码静态扫描。
//
// 覆盖范围：画质切换（本文件起点）、MID-37 掩码凭据、MID-38 登出入口、MID-39 错误体解析、
// MID-2263 前后端布尔解析不变量、M-17/M-18/M-19 动态容器与代次竞态、MIN-10 四语目录门禁。
// 新增用例沿用同一 harness，不另开 .mjs——另开会脱离 tests/test_frontend_quality_ui.py 的
// 单文件驱动与 ci.yml 的 node 清单，导致 CI 静默漏跑。
//
// 由 tests/test_frontend_quality_ui.py 以子进程运行（Node 缺失时该 pytest 用例 skip）。
import { readFileSync, readdirSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const APP_JS = readFileSync(new URL('../../web/app.js', import.meta.url), 'utf8');
// MIN-10 门禁需要静态读取面板 HTML（data-i18n 键清单 / 硬编码文案扫描），见文件末尾该段说明
const INDEX_HTML = readFileSync(new URL('../../web/index.html', import.meta.url), 'utf8');

// —— DOM 桩 ——————————————————————————————————————————————

// 极简元素桩：只实现 app.js 触及的接口。事件经 _listeners 记录、由测试手动派发。
//
// 两条真实 DOM 语义必须建模，否则整类回归锁恒绿：
//   ① textContent 赋值会**替换全部子节点**——M-17 的破坏面正是 applyTranslations 覆写动态容器，
//      把已渲染的配置表单清成一行占位文本；两个互不相干的字符串属性会让该形态完全隐形。
//   ② innerHTML 赋值会重建子节点，select.options 与选中态随之重置——M-19 断言「房间集合未变
//      不重建」，生产重建后要读 sel.options 复位，故 options 按 innerHTML 里的 <option value>
//      解析（值形态是 esc() 后的实体，本文件用例只用无特殊字符的房间名，不做二次解码）。
// _innerHTMLWrites 记录 ② 的发生次数，是 M-19「未重建」的计数判据。
function parseOptionValues(html) {
    return (html.match(/<option\b[^>]*>/g) || []).map(tag => {
        const m = tag.match(/\bvalue="([^"]*)"/);
        return { value: m ? m[1] : '' };
    });
}

function makeElement(id) {
    const listeners = {};
    const attrs = {};
    const el = {
        id,
        _listeners: listeners,
        _innerHTML: '',
        _innerHTMLWrites: 0,
        _text: '',
        options: [],
        value: '',
        className: '',
        disabled: false,
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
    Object.defineProperty(el, 'innerHTML', {
        get() { return el._innerHTML; },
        set(v) {
            el._innerHTML = String(v);
            el._innerHTMLWrites += 1;
            el.options = parseOptionValues(el._innerHTML);
            // 子节点整体替换 ⇒ 原选中态丢失，真实 select 复位到首个 option
            el.value = el.options.length ? el.options[0].value : '';
        },
    });
    Object.defineProperty(el, 'textContent', {
        get() { return el._text; },
        set(v) {
            el._text = String(v);
            // 覆写文本 = 换掉全部子节点（不计入 _innerHTMLWrites：那是「重建 option 集合」的计数）
            el._innerHTML = el._text;
            el.options = [];
            el.value = '';
        },
    });
    return el;
}

// index.html 的静态 data-i18n* 属性按 **id** 还原进桩，不另抄清单：M-17 的判据正是「真实首屏
// DOM 里这个容器带不带该属性」，抄一份等于把被测契约写进测试自己。
function attrsByIdFromHtml(html) {
    const map = new Map();
    for (const m of html.matchAll(/<[a-zA-Z][\w-]*\b([^>]*)>/g)) {
        const idM = m[1].match(/\bid="([^"]+)"/);
        if (!idM) continue;
        const attrs = {};
        for (const a of m[1].matchAll(/\b(data-i18n(?:-placeholder|-title)?)="([^"]*)"/g)) attrs[a[1]] = a[2];
        if (Object.keys(attrs).length) map.set(idM[1], attrs);
    }
    assert.ok(map.size >= 10, `未从 index.html 还原到足够的带 id 静态属性（${map.size}），解析已漂移`);
    assert.ok(map.has('logout-btn'), 'index.html 解析应命中 #logout-btn 的 data-i18n');
    return map;
}

const HTML_STATIC_ATTRS = attrsByIdFromHtml(INDEX_HTML);

function makeClassList() {
    const set = new Set();
    return {
        add(...cs) { cs.forEach(c => set.add(c)); },
        remove(...cs) { cs.forEach(c => set.delete(c)); },
        toggle(c) { set.has(c) ? set.delete(c) : set.add(c); },
        contains(c) { return set.has(c); },
    };
}

// fetch 路由桩：routes 键为 "METHOD path"，值为 {status?, json?|text?} 或 (callIndex) => 同构对象；
// text 表示非 JSON 响应体（见 makeResponse）。响应恒带 json 或 html 头（api() 据此决定
// JSON.parse），全部请求记进 log 供断言。路由函数也可返回其 Promise，桩会 await——M-18 需要
// 「先发的请求后落地」这种可控交错，不控制 resolve 时机就造不出乱序，竞态锁等于没锁。
function makeFetch(routes, log) {
    return async (path, init) => {
        init = init || {};
        const method = init.method || 'GET';
        log.push({ path, method, headers: init.headers || {}, body: init.body });
        const route = routes[method + ' ' + path];
        if (!route) {
            return makeResponse(404, { detail: 'no test route for ' + method + ' ' + path });
        }
        const spec = await (typeof route === 'function' ? route(log.length) : route);
        return makeResponse(spec.status || 200, spec.json || {}, spec.text);
    };
}

function makeResponse(status, data, rawText) {
    const text = rawText === undefined ? JSON.stringify(data) : rawText;
    return {
        status,
        ok: status >= 200 && status < 300,
        // rawText 用于「非 JSON 错误体」场景（HTML 错误页/纯文本），走 MID-39 的通用文案回退分支
        headers: { get: () => (rawText === undefined ? 'application/json' : 'text/html') },
        text: async () => text,
    };
}

// —— 应用启动 ————————————————————————————————————————————

// #config-container 的 input 还原：app.js 用 innerHTML 拼配置行、再按
// querySelectorAll('#config-container input') 取回，而 DOM 桩不解析 HTML。这里按属性把
// <input> 标签还原成元素桩并**按 innerHTML 缓存**，测试改动的才是 saveConfig 读到的同一批
// 对象（重新渲染后 innerHTML 变化才重解析，语义与真实 DOM 一致）。
function parseConfigInputs(html) {
    const inputs = [];
    for (const tag of html.match(/<input\b[^>]*>/g) || []) {
        const el = makeElement('config-input');
        for (const m of tag.matchAll(/([\w-]+)="([^"]*)"/g)) el.setAttribute(m[1], m[2]);
        el.readOnly = /\breadonly\b/.test(tag);
        el.value = el.getAttribute('value') || '';
        inputs.push(el);
    }
    return inputs;
}

// 在沙箱中加载 app.js 并完成 DOMContentLoaded 初始化（语言/主题/事件绑定/启动引导）。
// lang 控制初始语言；routes 补充被测视图所需接口。
async function bootApp({ lang, routes, confirm = () => true, injectToken = true, seedClasses = {} } = {}) {
    const lang_ = lang || 'zh_CN';
    const fetchLog = [];
    const confirmCalls = [];
    const elements = new Map();
    // 五个导航 tab 桩：'.tab' 选择器返回它们，tab 点击 → showView(data-view)
    const tabs = ['dashboard', 'danmaku', 'rooms', 'config', 'files'].map(v => {
        const el = makeElement('tab-' + v);
        el.setAttribute('data-view', v);
        return el;
    });
    const docListeners = {};
    // index.html 的初始 class（如 #logout-btn 的 hidden）与静态 data-i18n* 属性都按真实 HTML
    // 还原，否则显隐断言失去前提（判据见 HTML_STATIC_ATTRS）。
    function getOrCreate(id) {
        if (!elements.has(id)) {
            const el = makeElement(id);
            (seedClasses[id] || []).forEach(c => el.classList.add(c));
            for (const [k, v] of Object.entries(HTML_STATIC_ATTRS.get(id) || {})) el.setAttribute(k, v);
            elements.set(id, el);
        }
        return elements.get(id);
    }
    let configCache = { html: null, inputs: [] };
    function configInputs() {
        const html = getOrCreate('config-container').innerHTML;
        if (configCache.html !== html) configCache = { html, inputs: parseConfigInputs(html) };
        return configCache.inputs;
    }
    const document = {
        getElementById: getOrCreate,
        querySelectorAll(sel) {
            if (sel === '.tab') return tabs;
            if (sel === '#config-container input') return configInputs();
            // applyTranslations() 的三类静态扫描：按「已还原的静态属性」如实返回，
            // M-17 的锁全靠这里与真实首屏 DOM 同源（返回空数组等于该函数从不执行）。
            if (/^\[(data-i18n(?:-placeholder|-title)?)\]$/.test(sel)) {
                const attr = sel.slice(1, -1);
                return [...elements.values()].filter(el => el.getAttribute(attr) !== null);
            }
            return [];
        },
        // renderRecordingControl 走 class 选择器取状态标签；桩不建模 class 树，返回 null 即
        // 走 app.js 自己的 `if (onEl && offEl)` 跳过分支（该分支的显隐语义不在本文件覆盖范围）
        querySelector() { return null; },
        addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
        documentElement: makeElement('html'),
        body: makeElement('body'),
    };
    const storage = new Map();
    const localStorage = {
        getItem: k => (storage.has(k) ? storage.get(k) : null),
        setItem: (k, v) => storage.set(k, String(v)),
        removeItem: k => storage.delete(k),
    };
    // M-84：生产 _tokenStore() 的**首选**载体是 sessionStorage（关标签页即失效），沙箱必须提供它，
    // 用例才走得到主路径；两个载体各用一个 Map，「令牌绝不落 localStorage」才可能被观察到
    // （内存回退那一支由 tests/frontend/test_regression_gates.mjs 的 M-84 用例专门驱动）。
    const sessionData = new Map();
    const sessionStorage = {
        getItem: k => (sessionData.has(k) ? sessionData.get(k) : null),
        setItem: (k, v) => sessionData.set(k, String(v)),
        removeItem: k => sessionData.delete(k),
    };
    // 定时器桩：排队但不自跑——没人调 runTimers 就一条回调也不执行（与纯 no-op 等价），
    // 但 M-19 需要它驱动弹幕轮询：renderDanmaku 只经 dmChain 的 poll + setTimeout 进入，
    // no-op 形态下那条链永不落地。id 用队列下标 +1（0 是 falsy，兼容 app.js 的 `if (toastTimer)`
    // 判空口径），clearTimeout 把槽位置 null 而非移出数组，故 id 与槽位始终对齐。
    const timerQueue = [];
    const sandbox = {
        document,
        localStorage,
        sessionStorage,
        fetch: makeFetch({
            // 启动引导固定 401 → 登录态（静止应用）；语言由用例指定
            'GET /api/language': { json: { language: lang_ } },
            'GET /api/status': { status: 401, json: { detail: 'unauthorized' } },
            ...routes,
        }, fetchLog),
        setTimeout(fn) { timerQueue.push(fn); return timerQueue.length; },
        clearTimeout(id) { if (id) timerQueue[id - 1] = null; },
        confirm(...args) { confirmCalls.push(args[0]); return confirm(...args); },
        EventSource: class { constructor() {} close() {} addEventListener() {} },
    };
    sandbox.window = sandbox; // app.js 经 window.xxx 导出；浏览器里 window 即全局
    vm.createContext(sandbox);
    vm.runInContext(APP_JS, sandbox, { filename: 'web/app.js' });

    docListeners['DOMContentLoaded'][0]();
    await flush();
    // 401 引导已清空 token（api() 的 401 分支 setToken('')），注入测试 token 供鉴权头断言。
    // M-84：注入到**首选载体** sessionStorage——生产 _tokenStore() 只在它不可用时才退内存，
    // 注进 localStorage 已不再是生产会读的那一份。
    if (injectToken) sessionStorage.setItem('dlr_token', 'tok-test');
    // 手动执行当前已排期的定时器回调（一轮只跑「进队时已在队列里」的那些，跑完再排新的一轮），
    // 使轮询节拍由用例掌握而不是由真实时钟掌握。
    async function runTimers() {
        const due = timerQueue.splice(0, timerQueue.length);
        for (const fn of due) {
            if (fn) fn();
        }
        await flush();
    }
    return { sandbox, elements, tabs, fetchLog, localStorage, sessionStorage, confirmCalls, configInputs, runTimers, timerQueue };
}

// 派发「直播间」tab 点击：showView('rooms') → 拉画质选项 → 渲染房间列表
async function gotoRooms(ctx) {
    const tab = ctx.tabs.find(t => t.getAttribute('data-view') === 'rooms');
    tab._listeners.click[0].call(tab);
    await flush();
}

// 派发 rooms-tbody 的 change 事件委托（画质下拉）：target 仅需 matches/getAttribute/value
function fireQualityChange(ctx, url, value) {
    const target = {
        matches: s => s === 'select[data-action="quality"]',
        getAttribute: k => (k === 'data-url' ? url : null),
        value,
    };
    ctx.elements.get('rooms-tbody')._listeners.change[0]({ target });
}

// 等待微任务链排空：语言初始化、loadQualityOptions().finally(loadRooms) 等均为纯 Promise 链，
// 数轮 setImmediate 足以覆盖两级串行 fetch（宿主 setImmediate 未被沙箱桩替换）
async function flush(rounds) {
    for (let i = 0; i < (rounds || 8); i++) {
        await new Promise(r => setImmediate(r));
    }
}

function roomRoute(rooms) {
    // GET /api/rooms 响应器：rooms 传数组则恒定返回；传函数则每次调用求值（模拟服务端状态变化）
    if (typeof rooms === 'function') return () => ({ json: rooms() });
    return () => ({ json: rooms });
}

// —— 测试 ————————————————————————————————————————————————

test('沙箱加载 app.js 并导出事件处理函数', async () => {
    const ctx = await bootApp({ routes: {} });
    assert.equal(typeof ctx.sandbox.toggleRoom, 'function');
    assert.equal(typeof ctx.sandbox.deleteRoom, 'function');
});

test('房间列表渲染行内画质下拉：选项构成 / 选中态 / 转义 / 行结构', async () => {
    const rooms = [
        { url: 'https://www.huya.com/dank1ng', quality: '蓝光8M', name: 'DANK1NG', enabled: true, recording: true },
        { url: 'https://live.douyin.com/1', quality: '标清', name: 'A', enabled: false, recording: false },
        { url: 'https://evil.com/a"b', quality: '原画', name: 'B', enabled: true, recording: false },
    ];
    const ctx = await bootApp({
        routes: {
            'GET /api/rooms': roomRoute(rooms),
            // 用户画质选项不含「标清」：当前值须兜底追加为候选项，防止显示错位
            'GET /api/rooms/qualities': { json: { options: ['原画', '蓝光8M', '超清'], builtin: ['原画', '蓝光', '蓝光8M', '超清', '高清', '标清', '流畅'] } },
        },
    });
    await gotoRooms(ctx);
    const html = ctx.elements.get('rooms-tbody').innerHTML;

    // 每个房间一个画质下拉；启用开关与删除按钮行结构不回归
    assert.equal((html.match(/<select data-action="quality"/g) || []).length, rooms.length);
    assert.equal((html.match(/data-action="toggle"/g) || []).length, rooms.length);
    assert.equal((html.match(/data-action="delete"/g) || []).length, rooms.length);

    // 选项构成：首项「默认画质」（value=""，zh 文案）+ 画质选项列表
    assert.ok(html.includes('<option value=""'), '缺少默认画质首项');
    assert.ok(html.includes('>默认画质<'), '默认画质标签未本地化');
    // 当前画质选中态
    assert.ok(html.includes('value="蓝光8M" selected'), '蓝光8M 未选中');
    // 当前值不在选项列表时兜底追加（「标清」不在 qualities.options 中）
    assert.ok(html.includes('value="标清" selected'), '列表外当前画质未兜底追加');
    // 画质下拉的 data-url 经 esc() 转义（属性注入防护）。断言锚定 select 完整开标签：
    // 同行的启用开关/删除按钮本就各自转义 data-url，宽泛子串会被它们命中而漏检下拉本身
    assert.ok(
        html.includes('<select data-action="quality" data-url="https://evil.com/a&quot;b">'),
        '画质下拉的 data-url 未转义'
    );
});

test('画质 change 委托 → PUT /api/rooms/quality：请求契约与成功反馈', async () => {
    // 服务端状态随 PUT 变化：回拉后下拉显示新画质（读-写一致性）
    let quality = '蓝光8M';
    const url = 'https://www.huya.com/dank1ng';
    const ctx = await bootApp({
        routes: {
            'GET /api/rooms': roomRoute(() => [{ url, quality, name: 'DANK1NG', enabled: true, recording: true }]),
            'GET /api/rooms/qualities': { json: { options: ['原画', '蓝光8M', '超清'], builtin: [] } },
            'PUT /api/rooms/quality': () => {
                quality = '超清';
                return { json: { ok: true, changed: true } };
            },
        },
    });
    await gotoRooms(ctx);
    fireQualityChange(ctx, url, '超清');
    await flush();

    const put = ctx.fetchLog.find(f => f.method === 'PUT' && f.path === '/api/rooms/quality');
    assert.ok(put, '未发出 PUT /api/rooms/quality');
    // 载荷：url + 选择的画质档位
    assert.deepEqual(JSON.parse(put.body), { url, quality: '超清' });
    // 鉴权与序列化头
    assert.equal(put.headers.Authorization, 'Bearer tok-test');
    assert.equal(put.headers['Content-Type'], 'application/json');
    // 成功 toast（zh_CN 默认语言，{q} 占位符替换）
    assert.equal(ctx.elements.get('toast').textContent, '已切换画质为 超清，下一轮检测循环生效');
    // 成功后回拉列表，下拉反映服务端新状态
    assert.ok(ctx.elements.get('rooms-tbody').innerHTML.includes('value="超清" selected'), '回拉后未显示新画质');
});

test('选择「默认画质」（空值）→ quality 序列化为 null', async () => {
    const url = 'https://www.huya.com/dank1ng';
    const ctx = await bootApp({
        routes: {
            'GET /api/rooms': roomRoute([{ url, quality: '蓝光8M', name: 'DANK1NG', enabled: true, recording: false }]),
            'GET /api/rooms/qualities': { json: { options: ['原画', '蓝光8M'], builtin: [] } },
            'PUT /api/rooms/quality': { json: { ok: true, changed: true } },
        },
    });
    await gotoRooms(ctx);
    fireQualityChange(ctx, url, '');
    await flush();

    const put = ctx.fetchLog.find(f => f.method === 'PUT' && f.path === '/api/rooms/quality');
    assert.ok(put, '未发出 PUT /api/rooms/quality');
    assert.equal(JSON.parse(put.body).quality, null, '空值应序列化为 null（恢复默认画质）');
    assert.equal(ctx.elements.get('toast').textContent, '已恢复默认画质，下一轮检测循环生效');
});

test('切换失败：错误 toast + 回拉恢复服务端真值', async () => {
    const url = 'https://www.huya.com/dank1ng';
    const ctx = await bootApp({
        routes: {
            'GET /api/rooms': roomRoute([{ url, quality: '蓝光8M', name: 'DANK1NG', enabled: true, recording: false }]),
            'GET /api/rooms/qualities': { json: { options: ['原画', '蓝光8M', '超清'], builtin: [] } },
            'PUT /api/rooms/quality': { status: 500, json: { detail: 'boom' } },
        },
    });
    await gotoRooms(ctx);
    fireQualityChange(ctx, url, '超清');
    await flush();

    // 错误 toast：本地化前缀 + 服务端错误信息
    const toastText = ctx.elements.get('toast').textContent;
    assert.ok(toastText.startsWith('切换画质失败: '), 'toast 应为本地化错误前缀，实际: ' + toastText);
    assert.ok(toastText.includes('boom'));
    // 失败后回拉列表（下拉显示值恢复为服务端真值，不残留用户误选）
    const roomFetches = ctx.fetchLog.filter(f => f.method === 'GET' && f.path === '/api/rooms').length;
    assert.ok(roomFetches >= 2, '失败后未回拉列表，GET /api/rooms 次数: ' + roomFetches);
    assert.ok(ctx.elements.get('rooms-tbody').innerHTML.includes('value="蓝光8M" selected'), '失败后未恢复服务端真值');
});

test('四语切换成功文案行为级断言（toast 按当前语言渲染）', async () => {
    const expected = {
        zh_CN: '已切换画质为 超清，下一轮检测循环生效',
        en_US: 'Quality changed to 超清, effective on the next check cycle',
        en_GB: 'Quality changed to 超清, effective on the next check cycle',
        zh_TW: '已切換畫質為 超清，下一輪檢測循環生效',
    };
    const url = 'https://www.huya.com/dank1ng';
    for (const [lang, text] of Object.entries(expected)) {
        const ctx = await bootApp({
            lang,
            routes: {
                'GET /api/rooms': roomRoute([{ url, quality: '蓝光8M', name: 'DANK1NG', enabled: true, recording: false }]),
                'GET /api/rooms/qualities': { json: { options: ['原画', '蓝光8M', '超清'], builtin: [] } },
                'PUT /api/rooms/quality': { json: { ok: true, changed: true } },
            },
        });
        await gotoRooms(ctx);
        fireQualityChange(ctx, url, '超清');
        await flush();
        assert.equal(
            ctx.elements.get('toast').textContent, text,
            `语言 ${lang} 的切换成功文案缺失或不一致（I18N 四目录键集须一致）`
        );
    }
});

// —— 布尔配置解析口径（app.js 的 parseConfigBool） ——————————————————
//
// app.js 是单个 IIFE，只导出少数函数（刻意保持极小的全局面）。布尔解析属私有实现，故按大括号
// 配对从源码抽出「token 集 + parseConfigBool」片段单独求值，不为测试扩大生产导出面。
// 后半段另有行为级断言兜住「内部确实用 parseConfigBool」——只测片段会漏掉
// httpsRecordingEnabled 改回 `=== '是'` 的情况。

function extractParseBoolSource() {
    const start = APP_JS.indexOf('var CONFIG_TRUE_TOKENS');
    assert.ok(start >= 0, 'app.js 未找到 CONFIG_TRUE_TOKENS 定义');
    return APP_JS.slice(start, findFunctionEnd('parseConfigBool'));
}

// 按大括号配对取函数体结尾位置；未找到函数或括号不配对时断言失败（避免静默返回 -1 后
// 拿到半截源码、让后面的断言在错误前提上"碰巧通过"）。
function findFunctionEnd(name) {
    const start = APP_JS.indexOf('function ' + name + '(');
    assert.ok(start >= 0, `app.js 未找到函数 ${name}`);
    let depth = 0;
    for (let i = APP_JS.indexOf('{', start); i < APP_JS.length; i++) {
        if (APP_JS[i] === '{') depth++;
        else if (APP_JS[i] === '}') {
            depth--;
            if (depth === 0) return i + 1;
        }
    }
    throw new Error(`函数 ${name} 大括号未配对`);
}

function extractFunctionSource(name) {
    const end = findFunctionEnd(name);
    return APP_JS.slice(APP_JS.indexOf('function ' + name + '('), end);
}

const boolSandbox = { Object };
vm.createContext(boolSandbox);
vm.runInContext(extractParseBoolSource(), boolSandbox, { filename: 'app.js#parseConfigBool' });

// MID-2263：断言基准**必须**取自两端源码，不得在测试里内联字面量清单——旧写法把 token 表
// 抄进用例，两侧同时删/改也全绿（「后端回落 default、前端仍显示为『是』」的分叉只能靠人记）。
// 现在 JS 侧抠 CONFIG_*_TOKENS，Python 侧抠 src/config_bool.py 的 TRUE/FALSE_TOKENS，
// 逐 token 双向断言两端解析同一布尔。
const CONFIG_BOOL_PY = readFileSync(new URL('../../src/config_bool.py', import.meta.url), 'utf8');

function extractJsTokenSet(name) {
    const m = APP_JS.match(new RegExp(name + '\\s*=\\s*\\{([^}]*)\\}'));
    assert.ok(m, `app.js 未找到 ${name} 定义`);
    const keys = [];
    for (const entry of m[1].split(',')) {
        const key = entry.split(':')[0].trim().replace(/^['"]|['"]$/g, '');
        if (key) keys.push(key);
    }
    assert.ok(keys.length, `${name} 抠出 0 个 token（正则已漂移）`);
    return keys;
}

function extractPyTokenSet(name) {
    const m = CONFIG_BOOL_PY.match(new RegExp(name + '\\s*:\\s*frozenset\\[str\\]\\s*=\\s*frozenset\\(\\{([^}]*)\\}\\)'));
    assert.ok(m, `src/config_bool.py 未找到 ${name}`);
    const keys = [];
    for (const entry of m[1].split(',')) {
        const key = entry.trim();
        if (!key) continue;
        const lit = key.match(/^(['"])(.*)\1$/);
        assert.ok(lit, `${name} 里的 ${JSON.stringify(key)} 不是简单字符串字面量，抠取逻辑已失效`);
        keys.push(lit[2]);
    }
    assert.ok(keys.length, `${name} 抠出 0 个 token（正则已漂移）`);
    return keys;
}

test('MID-2263：前端 CONFIG_*_TOKENS 与后端 TRUE/FALSE_TOKENS 集合逐一相等（跨语言不变量）', () => {
    const jsTrue = extractJsTokenSet('CONFIG_TRUE_TOKENS');
    const jsFalse = extractJsTokenSet('CONFIG_FALSE_TOKENS');
    const pyTrue = extractPyTokenSet('TRUE_TOKENS');
    const pyFalse = extractPyTokenSet('FALSE_TOKENS');
    // 用 sorted 比较而非 deepEqual：集合语义下顺序不承载含义，两端书写顺序不同不应报红
    assert.deepEqual(jsTrue.slice().sort(), pyTrue.slice().sort(),
        'CONFIG_TRUE_TOKENS 与 src/config_bool.py::TRUE_TOKENS 不是同一集合（改一侧须同步另一侧）');
    assert.deepEqual(jsFalse.slice().sort(), pyFalse.slice().sort(),
        'CONFIG_FALSE_TOKENS 与 src/config_bool.py::FALSE_TOKENS 不是同一集合（改一侧须同步另一侧）');
    // 真/假集合不得有交集——两端各自的 token 语义必须互斥
    assert.deepEqual(jsTrue.filter(t => jsFalse.includes(t)), [], '真值 token 与假值 token 重叠');
    assert.deepEqual(pyTrue.filter(t => pyFalse.includes(t)), [], '后端真值 token 与假值 token 重叠');
});

test('SEV-2210：同一组输入串在前端 parseConfigBool 与后端 parse_config_bool 得到相同布尔', () => {
    const parse = boolSandbox.parseConfigBool;
    const pyTrue = extractPyTokenSet('TRUE_TOKENS');
    const pyFalse = extractPyTokenSet('FALSE_TOKENS');
    // 输入集由**后端源码里的 token 集合**驱动（含大小写与首尾空白变体），外加两端都必须
    // 回落 default 的空值/未识别值。
    const trueInputs = [];
    const falseInputs = [];
    for (const t of pyTrue) trueInputs.push(t, t.toUpperCase(), '  ' + t + '  ');
    for (const t of pyFalse) falseInputs.push(t, t.toUpperCase(), '  ' + t + '  ');
    for (const t of trueInputs) {
        assert.equal(parse(t, false), true, `前端未按后端口径判为开启: ${JSON.stringify(t)}`);
    }
    for (const t of falseInputs) {
        assert.equal(parse(t, true), false, `前端未按后端口径判为关闭: ${JSON.stringify(t)}`);
    }
    // 空值与未识别值：两端都回落 default（前端 fallback 形参，后端 default 形参）
    for (const t of ['', '   ', null, undefined, 'maybe', '真', '是/否', '2', 'onoff']) {
        assert.equal(parse(t, true), true, `fallback=true 未生效: ${JSON.stringify(t)}`);
        assert.equal(parse(t, false), false, `fallback=false 未生效: ${JSON.stringify(t)}`);
    }
});

test('SEV-2210：全文件不得残留 === / == 直比「是」「否」的旧形态', () => {
    // 「== \"是\"」是 SEV-2210 的历史坑（旧实现只认「是」）。仅锁 httpsRecordingEnabled 会漏掉
    // 新增的同类判定，故全文件扫描；注释行里的散文形态先剥掉，不算比较表达式。
    const offenders = [];
    const lines = APP_JS.split('\n');
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.trim().startsWith('//')) continue; // 注释里的历史说明不算
        if (/(===|==)\s*['"][是否]['"]/.test(line)) offenders.push(`app.js:${i + 1}: ${line.trim()}`);
    }
    assert.deepEqual(offenders, [], '存在把布尔配置直比「是/否」的旧形态，须走 parseConfigBool');
});

test('httpsRecordingEnabled 经 parseConfigBool 判定，不得退回直比「是」', () => {
    // 源码级断言：该函数决定 SSL 提示文案与用户对「是否启用https录制」写法的心智一致性，
    // 曾因只比较 === '是' 而让「= true」被显示成 HTTP 模式（与实际拉流协议相反）。
    const body = extractFunctionSource('httpsRecordingEnabled');
    assert.ok(body.includes('parseConfigBool('), 'httpsRecordingEnabled 未使用 parseConfigBool');
    assert.ok(!/==\s*['"]是['"]/.test(body), 'httpsRecordingEnabled 又退回直接比较「是」');
});

// —— MID-37 / MID-39：掩码凭据的空值保护与后端错误体解析 ——————————————————
//
// app.js 的 loadConfig 用 innerHTML 拼配置行、saveConfig 再读回，故本段走完整渲染链路
// （tab → GET /api/config → 渲染 → 保存 → 逐项 PUT），断言真实请求与真实 toast 文案。
const MASKED_CONFIG = {
    Cookie: { douyin_cookie: '***' },
    推送配置: { tgapi令牌: '***', 邮件服务器地址: 'smtp.qq.com' },
    录制设置: { 输出格式: 'ts' },
};

async function bootConfigView(cfg, { routes = {}, confirm } = {}) {
    const ctx = await bootApp({
        confirm,
        routes: { 'GET /api/config': () => ({ json: cfg }), 'PUT /api/config': { json: { ok: true } }, ...routes },
    });
    const tab = ctx.tabs.find(t => t.getAttribute('data-view') === 'config');
    tab._listeners.click[0].call(tab);
    await flush();
    return ctx;
}

function findInput(ctx, key) {
    return ctx.configInputs().find(i => i.getAttribute('data-key') === key);
}

async function clickSaveConfig(ctx) {
    ctx.elements.get('config-save-btn')._listeners.click[0]();
    await flush();
}

function putBodies(ctx) {
    return ctx.fetchLog.filter(f => f.method === 'PUT').map(f => JSON.parse(f.body));
}

test('loadConfig 给掩码凭据打 data-masked 标记并给出行内说明（MID-37 渲染侧）', async () => {
    const ctx = await bootConfigView(MASKED_CONFIG);
    const html = ctx.elements.get('config-container').innerHTML;
    assert.ok(html.includes('data-masked="1"'), '掩码项未打 data-masked 标记');
    assert.ok(html.includes('hint-masked'), '掩码项缺少说明提示，用户不知道 *** 背后仍有真实值');
    assert.equal(findInput(ctx, 'douyin_cookie').getAttribute('data-masked'), '1');
    assert.equal(findInput(ctx, 'tgapi令牌').getAttribute('data-masked'), '1');
    // 非掩码值（含同为敏感键名但后端未回掩码的项）不得被误标
    assert.equal(findInput(ctx, '输出格式').getAttribute('data-masked'), null);
    assert.equal(findInput(ctx, '邮件服务器地址').getAttribute('data-masked'), null);
    // password / text 输入类型的既有口径不回归
    assert.ok(html.includes('type="password"'), '敏感键未用 password 框');
    assert.ok(html.includes('type="text"'), '非敏感键被误改为 password 框');
});

test('原样提交掩码 *** 一律跳过，绝不回写（写入侧最后防线）', async () => {
    const ctx = await bootConfigView(MASKED_CONFIG);
    await clickSaveConfig(ctx);
    assert.deepEqual(putBodies(ctx), [], '掩码值被原样提交会覆盖真实凭据');
    assert.equal(ctx.elements.get('toast').textContent, '无变更');
});

test('掩码项被清空：用户拒绝确认 → 不提交并明确提示已跳过', async () => {
    const ctx = await bootConfigView(MASKED_CONFIG, { confirm: () => false });
    findInput(ctx, 'douyin_cookie').value = '';
    await clickSaveConfig(ctx);
    assert.equal(ctx.confirmCalls.length, 1, '清空掩码凭据必须弹确认');
    assert.ok(ctx.confirmCalls[0].includes('douyin_cookie'), '确认文案须点明是哪个键');
    assert.deepEqual(putBodies(ctx), [], '用户拒绝确认后仍提交了空值');
    assert.equal(ctx.elements.get('toast').textContent, '已跳过 1 项掩码凭据的空值提交');
});

test('掩码项清空且用户确认 → 提交空值，服务端 400 的 detail 明确显示（非通用错误）', async () => {
    const ctx = await bootConfigView(MASKED_CONFIG, {
        routes: {
            'PUT /api/config': { status: 400, json: { detail: '敏感配置项不得清空：如需移除请显式填写占位值并手工编辑 config.ini' } },
        },
    });
    findInput(ctx, 'douyin_cookie').value = '';
    await clickSaveConfig(ctx);
    assert.deepEqual(putBodies(ctx), [{ section: 'Cookie', key: 'douyin_cookie', value: '' }]);
    const toastText = ctx.elements.get('toast').textContent;
    assert.ok(toastText.startsWith('服务端拒绝保存: '), '400 须走「服务端拒绝」文案，实际: ' + toastText);
    assert.ok(toastText.includes('敏感配置项不得清空'), '须显示服务端给出的原因，实际: ' + toastText);
    assert.ok(!toastText.includes('"detail"'), 'toast 不得回显原始 JSON');
});

test('非掩码键留空无需确认（保护不得扩成全局阻塞）', async () => {
    const ctx = await bootConfigView(MASKED_CONFIG);
    findInput(ctx, '输出格式').value = '';
    await clickSaveConfig(ctx);
    assert.deepEqual(ctx.confirmCalls, [], '普通键留空不该弹凭据确认');
    assert.deepEqual(putBodies(ctx), [{ section: '录制设置', key: '输出格式', value: '' }]);
    assert.equal(ctx.elements.get('toast').textContent, '已保存 1 项');
});

test('MID-39：JSON 错误体只取 detail，登录页不再显示 {"detail":...}', async () => {
    const ctx = await bootApp({
        injectToken: false,
        routes: { 'POST /api/login': { status: 401, json: { detail: '口令错误' } } },
    });
    ctx.elements.get('login-password').value = 'bad';
    ctx.elements.get('login-submit')._listeners.click[0]();
    await flush();
    const text = ctx.elements.get('login-error').textContent;
    assert.equal(text, '口令错误', '登录报错应只显示 detail，实际: ' + text);
});

test('MID-39：非 JSON 错误体回退本地化通用文案，安装路径不进 toast', async () => {
    const ctx = await bootConfigView(MASKED_CONFIG, {
        routes: {
            'PUT /api/config': { status: 502, text: '<html>502 Bad Gateway<br>D:\\DouyinLiveRecorder\\logs\\streamget.log</html>' },
        },
    });
    findInput(ctx, '输出格式').value = 'mkv';
    await clickSaveConfig(ctx);
    const toastText = ctx.elements.get('toast').textContent;
    assert.ok(toastText.startsWith('保存失败: '), '非 400 失败仍走通用「保存失败」前缀，实际: ' + toastText);
    assert.ok(toastText.includes('请求失败 (502)'), '通用文案须带状态码便于报障，实际: ' + toastText);
    assert.ok(!toastText.includes('DouyinLiveRecorder'), '原始响应体（含安装绝对路径）不得进 toast');
});

// —— MID-38：登出入口显隐与 bearer 吊销 ————————————————————————————
//
// index.html 的 #logout-btn 带 class="hidden"（style.css 为 display:none!important）；
// 改动前全仓无代码移除它 → WD-09 的 POST /api/logout 在 UI 上不可达。桩按 HTML 初值还原
// 该 class（seedClasses），「登录后必须可见」的断言才与真实首屏一致。
const LOGOUT_SEED = { 'logout-btn': ['hidden'] };

test('MID-38 前提：index.html 的 #logout-btn 默认带 hidden（未登录不显示）', () => {
    const tag = (INDEX_HTML.match(/<button[^>]*id="logout-btn"[^>]*>/) || [])[0];
    assert.ok(tag, 'index.html 未找到 #logout-btn');
    assert.ok(/\bclass="[^"]*\bhidden\b[^"]*"/.test(tag), '#logout-btn 默认必须是 hidden');
});

test('登录成功后登出入口可见，点击调用 POST /api/logout 并清空 token', async () => {
    const ctx = await bootApp({
        injectToken: false,
        seedClasses: LOGOUT_SEED,
        routes: {
            'POST /api/login': { json: { token: 'tok-abc' } },
            'POST /api/logout': { json: { ok: true } },
        },
    });
    const btn = ctx.elements.get('logout-btn');
    assert.ok(btn.classList.contains('hidden'), '未登录时登出入口必须隐藏');
    ctx.elements.get('login-password').value = 'pw';
    ctx.elements.get('login-submit')._listeners.click[0]();
    await flush();
    assert.deepEqual(JSON.parse(ctx.fetchLog.find(f => f.path === '/api/login').body), { password: 'pw' });
    assert.ok(
        !btn.classList.contains('hidden'),
        'MID-38 回归：登录后登出入口仍不可见，/api/logout 无法从 UI 触达'
    );

    btn._listeners.click[0]();
    await flush();
    const logout = ctx.fetchLog.find(f => f.method === 'POST' && f.path === '/api/logout');
    assert.ok(logout, '未调用 POST /api/logout');
    assert.equal(logout.headers.Authorization, 'Bearer tok-abc', '登出请求必须带当前 bearer');
    // M-84：令牌的主载体是 sessionStorage，登出必须清它；顺带钉「localStorage 一侧从头到尾没有
    // 过令牌」——回退分支若被改回 localStorage，这里会先看到 setItem 后的值而不是 null。
    assert.equal(ctx.sessionStorage.getItem('dlr_token'), null, '登出后 sessionStorage 里的 token 必须清空');
    assert.equal(ctx.localStorage.getItem('dlr_token'), null, '令牌不得写进 localStorage（M-84 的落盘形态）');
    assert.ok(btn.classList.contains('hidden'), '登出后入口应收起');
    assert.ok(!ctx.elements.get('login-view').classList.contains('hidden'), '登出后应回到登录页');
});

test('登出请求失败也必须清本地并回登录页（不得把用户卡在面板里）', async () => {
    const ctx = await bootApp({
        injectToken: false,
        seedClasses: LOGOUT_SEED,
        routes: {
            'POST /api/login': { json: { token: 'tok-abc' } },
            'POST /api/logout': { status: 500, json: { detail: 'boom' } },
        },
    });
    ctx.elements.get('login-password').value = 'pw';
    ctx.elements.get('login-submit')._listeners.click[0]();
    await flush();
    const btn = ctx.elements.get('logout-btn');
    btn._listeners.click[0]();
    await flush();
    assert.equal(ctx.sessionStorage.getItem('dlr_token'), null, '登出失败也必须清掉 sessionStorage 里的 token（M-84 载体）');
    assert.ok(ctx.elements.get('login-view').classList.contains('hidden') === false, '注销失败也应回到登录页');
    assert.ok(btn.classList.contains('hidden'), '回到登录页后入口应收起');
});

test('无 token 的正常启动（认证关闭）不显示登出入口', async () => {
    const ctx = await bootApp({
        injectToken: false,
        seedClasses: LOGOUT_SEED,
        routes: { 'GET /api/status': { json: { engine_alive: true, recording_enabled: false } } },
    });
    assert.ok(!ctx.elements.get('dashboard-view').classList.contains('hidden'), '引导应进入仪表盘');
    assert.ok(ctx.elements.get('logout-btn').classList.contains('hidden'), '无 bearer 可吊销时不该显示登出');
});

// —— M-17 / M-18 / M-19：动态容器的翻译覆写、按需加载代次、筛选下拉重建 ————————
//
// 三条都是**行为锁**，不钉源码字面量：
//   · M-17：index.html 静态属性还原进桩 + textContent 写会替换子节点 + [data-i18n] 扫描面，
//     复现「切语言 → applyTranslations 覆写动态容器」，把 data-i18n 加回容器即转红；
//   · M-18：可控 resolve 造出「先发后到」的乱序（fetch 路由可返回 Promise），
//     删掉任一处 isCurrent 复核即转红；
//   · M-19：_innerHTMLWrites 计数 + 手动 runTimers 驱动轮询，退回「每轮无条件重建」即转红。

// 可控 resolve：用例握住 promise 不放手，先让新一代落地、再放开旧一代，乱序由此造出。
function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
}

// 派发任意导航 tab 的点击（showView(data-view)）
async function gotoView(ctx, name) {
    const tab = ctx.tabs.find(t => t.getAttribute('data-view') === name);
    tab._listeners.click[0].call(tab);
    await flush();
}

test('M-17：配置表单装载后切换语言，表单与未保存修改不得被清成一行占位文本', async () => {
    const ctx = await bootConfigView(MASKED_CONFIG, {
        routes: { 'PUT /api/language': { json: { language: 'en_US', fallback: false, notice: '' } } },
    });
    const inp = findInput(ctx, '输出格式');
    assert.ok(inp, '配置表单未渲染（本用例前提失效）');
    inp.value = 'mkv'; // 用户改了但还没保存
    const sel = ctx.elements.get('language-select');
    sel.value = 'en_US';
    sel._listeners.change[0].call(sel);
    await flush();

    // setLanguage 成功分支会调 applyTranslations()：它扫 [data-i18n] 覆写 textContent。
    // 容器若带该属性，textContent 一写就换掉全部子节点 → 整张表单（含上面那个未保存的 mkv）消失。
    const after = ctx.configInputs();
    assert.ok(after.length > 0, '切语言后配置容器被子节点清空：动态容器不得带 data-i18n（M-17 回归）');
    const kept = after.find(i => i.getAttribute('data-key') === '输出格式');
    assert.ok(kept, '输出格式这一行被清掉了');
    assert.equal(kept.value, 'mkv', '未保存的修改被语言切换抹掉');
    // 静态文案仍在该翻的位置上翻（防止「把 applyTranslations 整个跳过」这种假修）
    assert.equal(
        ctx.elements.get('config-save-btn').textContent,
        I18N.en_US['config.save'],
        '切语言后保存按钮文案未更新，说明静态翻译被一并跳过了'
    );
});

test('M-17 前提自检：index.html 的动态容器不得带 data-i18n，静态叶子才允许', () => {
    // 上一条是行为锁；这条把「同类病灶」的判据也机械化：凡是 app.js 里用 innerHTML 整体重建的
    // 容器（id 清单取自本文件实际驱动的这几张表/框），自身都不得挂 data-i18n*——
    // 挂在**会被一起替换掉的子节点**上才安全（那些键随重建消失，不会留下覆写父节点文本的属性）。
    const rebuiltContainers = ['config-container', 'rooms-tbody', 'files-tbody', 'danmaku-room-filter'];
    const offenders = [];
    for (const m of INDEX_HTML.matchAll(/<[a-zA-Z][\w-]*\b([^>]*)>/g)) {
        const idM = m[1].match(/\bid="([^"]+)"/);
        if (!idM || !rebuiltContainers.includes(idM[1])) continue;
        for (const a of m[1].matchAll(/\b(data-i18n(?:-placeholder|-title)?)="([^"]*)"/g)) {
            offenders.push(`#${idM[1]} 带 ${a[1]}="${a[2]}"`);
        }
    }
    assert.deepEqual(offenders, [], '动态重建的容器自身带上了静态翻译属性（applyTranslations 会清掉整棵子树）');
    // 反向见证：属性确实是从 HTML 解析出来的，不是空集自证
    assert.ok(/id="rooms-tbody"/.test(INDEX_HTML), 'index.html 解析前提失效');
});

test('M-18：文件浏览快速连点两跳，先发后到的旧响应不得覆盖最新目录', async () => {
    const older = deferred();
    const newer = deferred();
    const ctx = await bootApp({
        routes: {
            'GET /api/files?path=a': () => older.promise,
            'GET /api/files?path=b': () => newer.promise,
        },
    });
    ctx.sandbox.loadFiles('a');
    ctx.sandbox.loadFiles('b');
    await flush();
    newer.resolve({ json: [{ name: 'new.ts', type: 'file', size: 1, mtime: 0, path: 'b/new.ts' }] });
    await flush();
    older.resolve({ json: [{ name: 'old.ts', type: 'file', size: 1, mtime: 0, path: 'a/old.ts' }] });
    await flush();

    const crumb = ctx.elements.get('file-breadcrumb').innerHTML;
    const tbody = ctx.elements.get('files-tbody').innerHTML;
    assert.ok(crumb.includes('data-path="b"'), '面包屑被旧一代覆盖回上一级目录: ' + crumb);
    assert.ok(!crumb.includes('data-path="a"'), '旧一代的面包屑仍落了地: ' + crumb);
    assert.ok(tbody.includes('new.ts'), '文件列表未按最新一代渲染');
    assert.ok(!tbody.includes('old.ts'), '旧一代的行覆盖了最新目录');
});

test('M-18：旧一代的请求失败也不得把最新目录打成「加载失败」', async () => {
    const older = deferred();
    const newer = deferred();
    const ctx = await bootApp({
        routes: {
            'GET /api/files?path=a': () => older.promise,
            'GET /api/files?path=b': () => newer.promise,
        },
    });
    ctx.sandbox.loadFiles('a');
    ctx.sandbox.loadFiles('b');
    await flush();
    newer.resolve({ json: [{ name: 'ok.ts', type: 'file', size: 1, mtime: 0, path: 'b/ok.ts' }] });
    await flush();
    older.resolve({ status: 500, json: { detail: 'boom' } }); // 旧一代这次是失败
    await flush();
    const tbody = ctx.elements.get('files-tbody').innerHTML;
    assert.ok(tbody.includes('ok.ts'), '旧一代的失败分支覆盖了最新列表: ' + tbody);
    assert.ok(!tbody.includes('加载失败'), '失败文案来自已被取代的那一代');
});

test('M-18：直播间列表连点两代，只有最新一代落地', async () => {
    let hits = 0;
    const older = deferred();
    const newer = deferred();
    const ctx = await bootApp({
        routes: {
            'GET /api/rooms/qualities': { json: { options: ['原画'], builtin: [] } },
            'GET /api/rooms': () => (++hits === 1 ? older.promise : newer.promise),
        },
    });
    await gotoView(ctx, 'rooms'); // 第一代：path 恒定，两次点击发两支请求
    await gotoView(ctx, 'rooms'); // 第二代
    assert.equal(hits, 2, '未发出两代 GET /api/rooms（本用例前提失效）');
    newer.resolve({ json: [{ url: 'https://live.douyin.com/new', quality: '原画', name: 'NEW', enabled: true, recording: false }] });
    await flush();
    older.resolve({ json: [{ url: 'https://live.douyin.com/old', quality: '原画', name: 'OLD', enabled: true, recording: false }] });
    await flush();
    const tbody = ctx.elements.get('rooms-tbody').innerHTML;
    assert.ok(tbody.includes('https://live.douyin.com/new'), '列表未按最新一代渲染: ' + tbody);
    assert.ok(!tbody.includes('/old'), '旧一代把列表整体覆盖回了旧数据: ' + tbody);
});

test('M-18：配置页连点两代，旧一代不得覆盖已渲染表单', async () => {
    let hits = 0;
    const older = deferred();
    const newer = deferred();
    const ctx = await bootApp({
        routes: {
            'PUT /api/config': { json: { ok: true } },
            'GET /api/config': () => (++hits === 1 ? older.promise : newer.promise),
        },
    });
    await gotoView(ctx, 'config');
    await gotoView(ctx, 'config');
    assert.equal(hits, 2, '未发出两代 GET /api/config（本用例前提失效）');
    newer.resolve({ json: { 录制设置: { key_new: 'n' } } });
    await flush();
    older.resolve({ json: { 录制设置: { key_old: 'o' } } });
    await flush();
    const html = ctx.elements.get('config-container').innerHTML;
    assert.ok(html.includes('data-key="key_new"'), '表单未按最新一代渲染: ' + html);
    assert.ok(!html.includes('key_old'), '旧一代覆盖了配置表单: ' + html);
    // configBackup（saveConfig 的变更判定基线）在 loadConfig 里于代次复核**之后**才赋值，
    // 所以旧一代不会把基线带回保存前的那份——DOM 覆盖被挡住即等价于基线也没被污染。
    await clickSaveConfig(ctx);
    assert.deepEqual(putBodies(ctx), [], '基线被旧一代改写后，saveConfig 会凭空提交出不存在的变更');
});

test('M-19：房间集合未变的连续两轮轮询不得重建筛选下拉，选中项保持', async () => {
    let roomsNow = [
        { name: '房A', platform: 'bilibili', connected: true, msg_total: 1, msg_rate: 0, gift_total: 0, online: 1, started_at: '2026-10-18' },
    ];
    const ctx = await bootApp({
        routes: {
            'GET /api/danmaku?since=0': () => ({ json: { rooms: roomsNow, messages: [], last_seq: 0, truncated: false } }),
        },
    });
    await gotoView(ctx, 'danmaku');
    await ctx.runTimers(); // 第一轮 poll 落地

    const sel = ctx.elements.get('danmaku-room-filter');
    assert.equal(sel._innerHTMLWrites, 1, '首轮应重建一次 option 集合');
    sel.value = '房A'; // 用户展开下拉选中（此时下拉是展开态，重建会被浏览器关掉）

    await ctx.runTimers(); // 第二轮：房间集合与语言都没变
    assert.equal(sel._innerHTMLWrites, 1, '房间集合未变仍重建了下拉（展开的选择框会被关掉，M-19 回归）');
    assert.equal(sel.value, '房A', '未重建路径把用户选中项重置了');

    roomsNow = [
        ...roomsNow,
        { name: '房B', platform: 'douyu', connected: true, msg_total: 2, msg_rate: 1, gift_total: 0, online: 2, started_at: '2026-10-18' },
    ];
    await ctx.runTimers(); // 第三轮：新增房间 → 必须重建
    assert.equal(sel._innerHTMLWrites, 2, '房间集合变化后未重建下拉（新房间永远进不了筛选）');
    assert.ok(sel.innerHTML.includes('value="房B"'), '新增房间未出现在选项里: ' + sel.innerHTML);
    assert.equal(sel.value, '房A', '重建后未把选中项复位到用户原选择');
});

test('M-19：房间消失后重建下拉，选中项回落「全部房间」而不是残留在空气里', async () => {
    let roomsNow = [
        { name: '房A', platform: 'bilibili', connected: true, msg_total: 1, msg_rate: 0, gift_total: 0, online: 1, started_at: '2026-10-18' },
    ];
    const ctx = await bootApp({
        routes: {
            'GET /api/danmaku?since=0': () => ({ json: { rooms: roomsNow, messages: [], last_seq: 0, truncated: false } }),
        },
    });
    await gotoView(ctx, 'danmaku');
    await ctx.runTimers();
    const sel = ctx.elements.get('danmaku-room-filter');
    sel.value = '房A';
    roomsNow = [];
    await ctx.runTimers();
    assert.equal(sel._innerHTMLWrites, 2, '房间集合变空未重建');
    assert.equal(sel.value, '', '已消失的房间仍被当作选中项（筛选会恒无匹配）');
});

// —— MIN-10：前端内嵌四语目录的机械化门禁 ————————————————————————

//
// web/app.js 自带一套与后端 i18n/ 独立的四语目录（面板文案）。本段把「新增/修改翻译串须同步
// 多处」的人记约定变成门禁：前端语言集合 == 后端 i18n 实测集合、四目录键集逐一相等、
// index.html 的 data-i18n* 与 app.js 的 t('字面量') 键全部命中、无空值/键名回显、同模板占位符
// 一致、HTML 无未入目录的硬编码中文。目录直接从 app.js 源码截取字面量求值，不复制第二份清单。
function extractI18nCatalogs() {
    const start = APP_JS.indexOf('var I18N = {');
    assert.ok(start >= 0, 'app.js 未找到 var I18N 定义');
    let depth = 0;
    let i = APP_JS.indexOf('{', start);
    for (; i < APP_JS.length; i++) {
        if (APP_JS[i] === '{') depth++;
        else if (APP_JS[i] === '}') {
            depth--;
            if (depth === 0) break;
        }
    }
    const snippet = APP_JS.slice(start, i + 1) + ';';
    assert.ok(snippet.endsWith('};'), 'I18N 片段截取不完整（大括号不配对）');
    const box = { Object };
    vm.createContext(box);
    vm.runInContext(snippet, box, { filename: 'app.js#I18N' });
    assert.ok(box.I18N && box.I18N.zh_CN, 'I18N 目录求值失败');
    // 每个目录的最后一条若缺失即代表截取被截断（目录值里的 {q}/{n} 等成对花括号不影响配对）
    assert.ok(Object.keys(box.I18N.zh_CN).includes('toast.langSwitchFailed'), 'I18N 目录被截断');
    return box.I18N;
}

// 后端语言集合由 i18n/ 目录实测得出，避免在测试里再抄一份语言清单——新增语言时前端内嵌
// 目录漏补会被这条直接拦下。
function backendLanguages() {
    const dir = new URL('../../i18n/', import.meta.url);
    const langs = new Set();
    for (const entry of readdirSync(dir)) {
        if (/^[a-z]{2}_[A-Z]{2}\.(json|ya?ml)$/.test(entry)) langs.add(entry.split('.')[0]);
        else if (/^[a-z]{2}_[A-Z]{2}$/.test(entry)) {
            const files = readdirSync(new URL(`../../i18n/${entry}/LC_MESSAGES/`, import.meta.url));
            if (files.some(f => f.endsWith('.mo'))) langs.add(entry);
        }
    }
    return [...langs].sort();
}

const I18N = extractI18nCatalogs();
const FRONTEND_LANGS = Object.keys(I18N);
// CJK 判定按码位区间（扩展 A / 基本区 / 兼容表意文字）用十六进制字面量逐码位比较：
// 不用字面汉字写端点（编辑器形近字归一化会改码位，实测连 emoji 的 UTF-16 代理项都被判进
// 区间），也不用 \u 转义（测试文件里再放一份转义只增加读噪声）。
function hasCjk(text) {
    for (const ch of String(text)) {
        const cp = ch.codePointAt(0);
        if ((cp >= 0x3400 && cp <= 0x4dbf) || (cp >= 0x4e00 && cp <= 0x9fff) || (cp >= 0xf900 && cp <= 0xfaff)) return true;
    }
    return false;
}

test('前端内嵌目录的语言集合 == 后端 i18n 目录实测语言集合', () => {
    assert.deepEqual(FRONTEND_LANGS.slice().sort(), backendLanguages());
});

test('四语目录键集逐一相等（漏改任一处即红，MIN-10 的核心断言）', () => {
    const base = Object.keys(I18N.zh_CN);
    assert.ok(base.length >= 100, `目录键数异常偏小（${base.length}），疑似截取不完整`);
    for (const lang of FRONTEND_LANGS) {
        const keys = Object.keys(I18N[lang]);
        assert.equal(keys.length, base.length, `${lang} 目录键数 ${keys.length} 与 zh_CN ${base.length} 不等`);
        assert.deepEqual(base.filter(k => !keys.includes(k)), [], `${lang} 缺失键`);
        assert.deepEqual(keys.filter(k => !base.includes(k)), [], `${lang} 多出键`);
    }
});

test('index.html 的 data-i18n / -placeholder / -title 键全部命中四语目录', () => {
    const keys = new Set();
    for (const m of INDEX_HTML.matchAll(/data-i18n(?:-placeholder|-title)?="([^"]+)"/g)) keys.add(m[1]);
    assert.ok(keys.size >= 40, `未从 index.html 抓到足够的 data-i18n 键（${keys.size}），选择器可能已漂移`);
    for (const lang of FRONTEND_LANGS) {
        const missing = [...keys].filter(k => !Object.prototype.hasOwnProperty.call(I18N[lang], k));
        assert.deepEqual(missing, [], `${lang} 目录缺少界面键: ${missing.join(', ')}`);
    }
});

test('app.js 里 t(...) 字面量键与废弃键映射值全部命中四语目录', () => {
    const used = new Set();
    for (const m of APP_JS.matchAll(/[^A-Za-z_$.]t\('([^']+)'\)/g)) used.add(m[1]);
    // 废弃键经 t(DEPRECATED_CONFIG_KEYS[key]) 动态取值，须把该映射的值一并纳入检查
    const mapStart = APP_JS.indexOf('var DEPRECATED_CONFIG_KEYS = {');
    assert.ok(mapStart >= 0, 'app.js 未找到 DEPRECATED_CONFIG_KEYS');
    const mapBody = APP_JS.slice(mapStart, APP_JS.indexOf('};', mapStart) + 2);
    for (const m of mapBody.matchAll(/:\s*'([^']+)'/g)) used.add(m[1]);
    assert.ok(used.size >= 40, `未从 app.js 抓到足够的 t() 键（${used.size}）`);
    for (const lang of FRONTEND_LANGS) {
        const missing = [...used].filter(k => !Object.prototype.hasOwnProperty.call(I18N[lang], k));
        assert.deepEqual(missing, [], `${lang} 目录缺少动态文案键: ${missing.join(', ')}`);
    }
});

test('四语目录无空值、无「键名原样回显」，英文目录不得照抄中文源串', () => {
    for (const lang of FRONTEND_LANGS) {
        for (const [k, v] of Object.entries(I18N[lang])) {
            assert.equal(typeof v, 'string', `${lang}.${k} 不是字符串`);
            assert.ok(v.trim().length > 0, `${lang}.${k} 为空 → 界面渲染空白`);
            assert.notEqual(v.trim(), k, `${lang}.${k} 与键名相同 → 这是 t() 缺失回退的形态，说明未翻译`);
            if (lang.startsWith('en_')) {
                // 中文源串里含「是否弹幕监控(是/否)」这类后端配置键名是刻意保留，整体译文仍须不同
                const zh = I18N.zh_CN[k];
                assert.ok(
                    !(hasCjk(zh) && v.trim() === zh.trim()),
                    `${lang}.${k} 与中文源串完全相同 → 未翻译`
                );
            }
        }
    }
});

test('同一模板的四语译文占位符集合一致（漏一个会渲染出 {n} 原文）', () => {
    const ph = s => (String(s).match(/\{[^{}]+\}/g) || []).slice().sort().join(',');
    for (const k of Object.keys(I18N.zh_CN)) {
        const expected = ph(I18N.zh_CN[k]);
        for (const lang of FRONTEND_LANGS) {
            assert.equal(ph(I18N[lang][k]), expected, `${lang}.${k} 的占位符集合与 zh_CN 不一致`);
        }
    }
});

test('index.html 不存在未入目录的硬编码中文（含 title/placeholder）', () => {
    const catalogValues = new Set(Object.values(I18N.zh_CN).map(v => String(v).trim()));
    const visible = INDEX_HTML
        .replace(/<!--[\s\S]*?-->/g, '')
        .replace(/<script[\s\S]*?<\/script>/g, '')
        .replace(/<style[\s\S]*?<\/style>/g, '');
    const offenders = [];
    for (const m of visible.matchAll(/>([^<>]+)</g)) {
        const text = m[1].trim();
        if (text && hasCjk(text) && !catalogValues.has(text)) offenders.push('文本节点: ' + text);
    }
    for (const m of INDEX_HTML.matchAll(/\s(?:title|placeholder)="([^"]+)"/g)) {
        const text = m[1].trim();
        if (text && hasCjk(text) && !catalogValues.has(text)) offenders.push('属性值: ' + text);
    }
    assert.deepEqual(offenders, [], '存在切语言不会跟着变的硬编码文案');
});
