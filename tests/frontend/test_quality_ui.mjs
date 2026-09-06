// WEB 端「按房间切换画质」前端功能的单元测试（Node 内置 node:test，零 npm 依赖）。
//
// 【为什么用 node:vm 沙箱而非 jsdom】仓库无 package.json / 前端构建链，为一个 IIFE 页面脚本
// 引入 jsdom 测试栈会带来整条 npm 依赖树，与「纯 Python 仓库 + 运行时自带 Node」的定位不符。
// app.js 全部状态封闭在 IIFE 私有作用域内（仅 window.toggleRoom 等少数导出），画质切换的
// buildRoomQualitySelect / changeRoomQuality / 事件委托均为私有函数——沙箱内以 DOM/fetch 桩
// 手动触发 DOMContentLoaded 后，通过真实的事件委托链路驱动（tab 点击 → showView('rooms') →
// 渲染下拉 → change 委托 → PUT /api/rooms/quality → toast/回拉），既不改动生产代码，也覆盖
// 真实接线而非孤立函数。
//
// 【桩的最小集合】app.js 加载期零副作用（IIFE 尾部仅注册 DOMContentLoaded），初始化触及的
// 全局仅有：document（getElementById/querySelectorAll/addEventListener/body.dataset/
// documentElement）、window（自身赋值）、localStorage、fetch、setTimeout/clearTimeout、
// confirm、EventSource（SSE 路径，本测试不进入）。setTimeout 桩为 no-op：toast 自动隐藏与
// 轮询递归全部依赖它，不执行可让测试完全确定性（无真实定时器竞态），Promise 微任务不受影响。
//
// 【启动引导走向】GET /api/status 固定回 401：api() 的 401 分支走 showLogin（不构造
// EventSource、不启动仪表盘轮询），得到一个静止的登录态应用；随后注入测试 token、点击
// 「直播间」tab 进入被测视图。语言由 GET /api/language 响应控制（initLanguage 依据它设置
// currentLang），四语文案用同一链路行为级断言，而非源码静态扫描。
//
// 由 tests/test_frontend_quality_ui.py 以子进程运行（node 缺失时该 pytest 用例 skip）。
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const APP_JS = readFileSync(new URL('../../web/app.js', import.meta.url), 'utf8');

// —— DOM 桩 ——————————————————————————————————————————————

// 极简元素桩：只实现 app.js 触及的接口。innerHTML/value/textContent 为纯属性赋值，
// 断言直接读字符串；事件经 _listeners 记录、由测试手动派发。
function makeElement(id) {
    const listeners = {};
    const attrs = {};
    return {
        id,
        _listeners: listeners,
        innerHTML: '',
        textContent: '',
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
}

function makeClassList() {
    const set = new Set();
    return {
        add(...cs) { cs.forEach(c => set.add(c)); },
        remove(...cs) { cs.forEach(c => set.delete(c)); },
        toggle(c) { set.has(c) ? set.delete(c) : set.add(c); },
        contains(c) { return set.has(c); },
    };
}

// fetch 路由桩：routes 以 "METHOD path" 为键，值为 {status?, json?} 或 (callIndex) => 同构对象。
// 响应恒带 application/json 头（api() 按它决定 JSON.parse），全部请求记录进 log 供断言。
function makeFetch(routes, log) {
    return async (path, init) => {
        init = init || {};
        const method = init.method || 'GET';
        log.push({ path, method, headers: init.headers || {}, body: init.body });
        const route = routes[method + ' ' + path];
        if (!route) {
            return makeResponse(404, { detail: 'no test route for ' + method + ' ' + path });
        }
        const spec = typeof route === 'function' ? route(log.length) : route;
        return makeResponse(spec.status || 200, spec.json || {});
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

// —— 应用启动 ————————————————————————————————————————————

// 在沙箱中加载 app.js 并完成 DOMContentLoaded 初始化（语言/主题/事件绑定/启动引导）。
// lang 控制初始语言；routes 补充被测视图所需接口（房间列表与画质选项须由用例提供）。
async function bootApp({ lang, routes } = {}) {
    const lang_ = lang || 'zh_CN';
    const fetchLog = [];
    const elements = new Map();
    // 五个导航 tab 桩：'.tab' 选择器返回它们，tab 点击 → showView(data-view)
    const tabs = ['dashboard', 'danmaku', 'rooms', 'config', 'files'].map(v => {
        const el = makeElement('tab-' + v);
        el.setAttribute('data-view', v);
        return el;
    });
    const docListeners = {};
    const document = {
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, makeElement(id));
            return elements.get(id);
        },
        querySelectorAll(sel) { return sel === '.tab' ? tabs : []; },
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
    const sandbox = {
        document,
        localStorage,
        fetch: makeFetch({
            // 启动引导固定 401 → 登录态（静止应用）；语言由用例指定
            'GET /api/language': { json: { language: lang_ } },
            'GET /api/status': { status: 401, json: { detail: 'unauthorized' } },
            ...routes,
        }, fetchLog),
        // no-op 定时器：toast 自动隐藏/轮询递归不执行，测试确定性（见模块头注释）
        setTimeout() { return 0; },
        clearTimeout() {},
        confirm() { return true; },
        EventSource: class { constructor() {} close() {} addEventListener() {} },
    };
    sandbox.window = sandbox; // app.js 经 window.xxx 导出；浏览器里 window 即全局
    vm.createContext(sandbox);
    vm.runInContext(APP_JS, sandbox, { filename: 'web/app.js' });

    docListeners['DOMContentLoaded'][0]();
    await flush();
    // 401 引导已清空 token（api() 的 401 分支 setToken('')），注入测试 token 供鉴权头断言
    localStorage.setItem('dlr_token', 'tok-test');
    return { sandbox, elements, tabs, fetchLog, localStorage };
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
