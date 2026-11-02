// 认证复验口令链（M-22 / M-26）的前端行为回归锁。
//
// 【为何单独成文件】要证的是**交互结果**（口令窗是否弹出、口令随哪些请求下发、取消/留空
// 是否真的不提交、DOM 是否残留），而非源码形状。test_regression_gates.mjs 里对同一
// 契约只有源码级断言——钉字面量在契约反转时会空过，故在此补行为侧。
//
// 【与后端契约同源】src/web_api.py::update_config 的 MID-2241 段：认证当前开启时写 [Web]
// web_auth_enable / web_password 必须带能过 verify_web_password 的 reauth_password，否则 403；
// 其余键不受影响。本文件锁三条前端行为：① 认证两键的 PUT 携带 reauth_password（缺了必然 403）；
// ② 其余键的 PUT 不带该字段（M-22 修的正是循环外粘变量把口令复制进本次保存的每个请求）；
// ③ 空口令/取消一律不提交（不白撞 403，也不留必然失败的 auth_reauth_denied 告警）。
// 后端自身判定不在此复制，已由 tests/test_regression_web_g.py 的 TestAuthKeyReauth
// 与 tests/test_web_api.py::TestAuthDowngradeRejected 用真实端点 E2E 锁住。
//
// 【桩的最小集合】与 test_quality_ui.mjs 同源：DOM/fetch/confirm 桩 + no-op 定时器；
// #config-container 的 input 按 innerHTML 里的 <input> 标签还原（app.js 用 innerHTML 拼行、
// 再 querySelectorAll 读回）。沙箱刻意没有 window.prompt：生产若退回 prompt 采集口令，用例会以
// ReferenceError 直接变红，而不是被「返回固定串」的桩悄悄放过——这是本文件的第一条断言。
//
// 由 tests/frontend/test_auth_reauth.py 以子进程 `node --test` 调用（Node 缺失时该包装 skip）。
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const APP_JS = readFileSync(new URL('../../web/app.js', import.meta.url), 'utf8');
const INDEX_HTML = readFileSync(new URL('../../web/index.html', import.meta.url), 'utf8');

function makeClassList() {
    const set = new Set();
    return {
        add(...cs) { cs.forEach(c => set.add(c)); },
        remove(...cs) { cs.forEach(c => set.delete(c)); },
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
        _focusCount: 0,
        innerHTML: '',
        textContent: '',
        value: '',
        className: '',
        disabled: false,
        readOnly: false,
        scrollTop: 0,
        scrollHeight: 0,
        style: {},
        dataset: {},
        options: [],
        classList: makeClassList(),
        addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
        setAttribute(k, v) { attrs[k] = String(v); },
        getAttribute(k) { return k in attrs ? attrs[k] : null; },
        appendChild() {},
        removeChild() {},
        closest() { return null; },
        matches() { return false; },
        focus() { this._focusCount += 1; },
    };
}

// 响应恒带 json 头（api() 据此决定 JSON.parse）；全部请求记进 log 供逐请求断言 body。
function makeFetch(routes, log) {
    return async (path, init) => {
        init = init || {};
        const method = init.method || 'GET';
        log.push({ path, method, body: init.body });
        const route = routes[method + ' ' + path] || routes[method + ' ' + path.split('?')[0]];
        if (!route) return makeResponse(404, { detail: 'no test route for ' + method + ' ' + path });
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

// #config-container 的 input 还原（与 test_quality_ui.mjs 同型）：app.js 用 innerHTML 拼配置行、
// 再用 querySelectorAll 取回，故桩按**当前 innerHTML** 缓存解析结果，测试改动的才是
// saveConfig 真正读到的那批对象。
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

async function flush(rounds) {
    for (let i = 0; i < (rounds || 8); i++) {
        await new Promise(r => setImmediate(r));
    }
}

// index.html 的初值还原：#reauth-modal 默认带 .hidden（口令窗只在认证键路径上被摘掉）。
const SEED_MODAL = { 'reauth-modal': ['hidden'] };

// 启动并进入配置视图：GET /api/config 渲染输入行并写入 configBackup（saveConfig 的 diff 基线）。
// seedClasses 按 index.html 的初始 class 还原元素——桩里 getElementById 惰性建空元素，不还原初值
// 会把「默认隐藏的 #reauth-modal」看成可见，反向边界断言随之失真。
async function bootConfigView(cfg, { routes = {}, confirm = () => true, seedClasses = SEED_MODAL } = {}) {
    const fetchLog = [];
    const confirmCalls = [];
    const elements = new Map();
    const tabs = ['dashboard', 'danmaku', 'rooms', 'config', 'files'].map(v => {
        const el = makeElement('tab-' + v);
        el.setAttribute('data-view', v);
        return el;
    });
    const docListeners = {};
    const getOrCreate = id => {
        if (!elements.has(id)) {
            const el = makeElement(id);
            (seedClasses[id] || []).forEach(c => el.classList.add(c));
            elements.set(id, el);
        }
        return elements.get(id);
    };
    let configCache = { html: null, inputs: [] };
    function configInputs() {
        const html = getOrCreate('config-container').innerHTML;
        if (configCache.html !== html) configCache = { html, inputs: parseConfigInputs(html) };
        return configCache.inputs;
    }
    const document = {
        hidden: false,
        getElementById: getOrCreate,
        querySelectorAll(sel) {
            if (sel === '.tab') return tabs;
            if (sel === '#config-container input') return configInputs();
            return [];
        },
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
    // 沙箱必须提供 sessionStorage——它是生产 _tokenStore() 的**首选**载体（关标签页即失效），否则用例
    // 走不到主路径；与 localStorage 各用一个 Map，「令牌不进 localStorage」才是可观察的事实（内存回退
    // 一支由 tests/frontend/test_regression_gates.mjs 的 M-84 用例专门驱动）。
    const sessionData = new Map();
    const sessionStorage = {
        getItem: k => (sessionData.has(k) ? sessionData.get(k) : null),
        setItem: (k, v) => sessionData.set(k, String(v)),
        removeItem: k => sessionData.delete(k),
    };
    const sandbox = {
        document,
        localStorage,
        sessionStorage,
        fetch: makeFetch({
            'GET /api/language': { json: { language: 'zh_CN' } },
            // 引导固定 401 → 停在登录态的静止应用；随后注入 token，测试直接驱动配置视图
            'GET /api/status': { status: 401, json: { detail: 'unauthorized' } },
            'GET /api/config': () => ({ json: cfg }),
            'PUT /api/config': { json: { ok: true } },
            ...routes,
        }, fetchLog),
        setTimeout() { return 0; },
        clearTimeout() {},
        confirm(...args) { confirmCalls.push(args[0]); return confirm(...args); },
        EventSource: class { constructor() {} close() {} addEventListener() {} },
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(APP_JS, sandbox, { filename: 'web/app.js' });
    docListeners['DOMContentLoaded'][0]();
    await flush();
    // 401 引导已清空 token，注入测试 token 供鉴权头断言（M-84：注入生产会读的那一份）
    sessionStorage.setItem('dlr_token', 'tok-test');
    const ctx = { sandbox, elements, tabs, fetchLog, localStorage, sessionStorage, confirmCalls, configInputs, docListeners };
    await gotoConfig(ctx);
    return ctx;
}

async function gotoConfig(ctx) {
    const tab = ctx.tabs.find(t => t.getAttribute('data-view') === 'config');
    tab._listeners.click[0].call(tab);
    await flush();
}

function findInput(ctx, key) {
    return ctx.configInputs().find(i => i.getAttribute('data-key') === key);
}

// 点「保存配置」——**不 await**：认证键路径会在口令窗上挂起，用例必须能在它挂起期间操作弹窗。
function clickSave(ctx) {
    ctx.elements.get('config-save-btn')._listeners.click[0]();
}

function modalVisible(ctx) {
    return !ctx.elements.get('reauth-modal').classList.contains('hidden');
}

// 口令窗的四个出口（与 web/app.js DOMContentLoaded 里的绑定一一对应）
function clickReauthConfirm(ctx) {
    ctx.elements.get('reauth-confirm')._listeners.click[0].call(ctx.elements.get('reauth-confirm'));
}

function clickReauthCancel(ctx) {
    ctx.elements.get('reauth-cancel')._listeners.click[0].call(ctx.elements.get('reauth-cancel'));
}

function clickReauthOverlay(ctx) {
    const modal = ctx.elements.get('reauth-modal');
    modal._listeners.click[0].call(modal, { target: modal });
}

function fireReauthKey(ctx, key) {
    const input = ctx.elements.get('reauth-password');
    input._listeners.keypress[0]({ key, target: input });
}

function fireDocumentKey(ctx, key) {
    (ctx.docListeners['keydown'] || []).forEach(fn => fn({ key }));
}

function putBodies(ctx) {
    return ctx.fetchLog.filter(f => f.method === 'PUT').map(f => JSON.parse(f.body));
}

function putFor(ctx, key) {
    return putBodies(ctx).find(b => b.key === key);
}

// [Web] 三个键 + 一个普通键：web_password 现值刻意留空（非掩码），「改成新值」即可判定为脏。
const AUTH_CONFIG = {
    Web: { web_host: '127.0.0.1', web_auth_enable: 'true', web_password: '' },
    录制设置: { 循环时间: '10' },
};

// —— 静态前提（HTML/CSS 形态）——————————————————————————————

test('M-22 前提：index.html 的口令窗用 type="password" 且默认隐藏', () => {
    const input = (INDEX_HTML.match(/<input[^>]*id="reauth-password"[^>]*>/) || [])[0];
    assert.ok(input, 'index.html 缺少 #reauth-password（复验口令的采集节点）');
    assert.match(input, /type="password"/, '口令输入框不是 password 形态（M-22 的明文回显回归）');
    assert.match(input, /autocomplete="off"/, '口令框未关自动填充');
    const modal = (INDEX_HTML.match(/<div[^>]*id="reauth-modal"[^>]*>/) || [])[0];
    assert.ok(modal, 'index.html 缺少 #reauth-modal');
    assert.match(modal, /\bclass="[^"]*\bhidden\b[^"]*"/, '口令窗必须默认隐藏（与 .login-card 同族形态）');
    assert.match(modal, /aria-modal="true"/, '对话框缺少 aria-modal，读屏会把口令提示念进正文');
});

test('M-22：app.js 全文件不存在 window.prompt 形态的口令采集（剥注释后判定）', () => {
    // 失效形态：用 window.prompt 采集复验口令——面板唯一**明文回显**的口令输入框，且原生弹窗
    // 无法指定 type/autocomplete，口令会进自动填充候选。判据先剥行注释：沿革注释里写着旧形态名，
    // 不剥会把注释当成代码命中。
    const code = APP_JS.split('\n').filter(l => !l.trim().startsWith('//')).join('\n');
    assert.ok(!/window\.prompt\s*\(/.test(code), '仍存在 window.prompt 调用');
    assert.ok(!/[^.\w]prompt\s*\(/.test(code), '仍存在裸 prompt 调用（同为明文采集形态）');
});

// —— 行为：下发范围 ————————————————————————————————

test('M-22：改认证键弹口令窗，其 PUT 携带 reauth_password（缺了必然被后端 403）', async () => {
    const ctx = await bootConfigView(AUTH_CONFIG);
    findInput(ctx, 'web_auth_enable').value = 'false';
    clickSave(ctx);
    assert.ok(modalVisible(ctx), '认证键改动未弹出口令窗（复验链断裂）');
    assert.equal(ctx.elements.get('reauth-password')._focusCount, 1, '口令窗未把焦点交给密码框');
    ctx.elements.get('reauth-password').value = 'current-pw';
    clickReauthConfirm(ctx);
    await flush();
    // 基础形状（section/key/value）必须逐字段保持——其余配置键的请求契约由它锚定
    assert.deepEqual(putFor(ctx, 'web_auth_enable'), {
        section: 'Web',
        key: 'web_auth_enable',
        value: 'false',
        reauth_password: 'current-pw',
    }, '认证键的 PUT 体形状不符合预期（reauth_password 缺失或基础字段被改动）');
});

test('M-22：同轮保存的普通配置键**不得**被 reauth_password 污染（本次保存逐请求断言）', async () => {
    // 失效形态：authReauth 是循环外的粘变量，认证行一旦赋值，之后**每个**有改动的键的 PUT 都带
    // reauth_password——口令被复制进本次保存的全部请求（代理日志/扩展/抓包都能记下）。
    const ctx = await bootConfigView(AUTH_CONFIG);
    findInput(ctx, '循环时间').value = '30';        // 排在 Web 之后：旧形态正是被它捎带
    findInput(ctx, 'web_auth_enable').value = 'false';
    clickSave(ctx);
    assert.ok(modalVisible(ctx), '用例前提失效：认证键未弹出口令窗');
    ctx.elements.get('reauth-password').value = 'current-pw';
    clickReauthConfirm(ctx);
    await flush();
    const bodies = putBodies(ctx);
    assert.equal(bodies.length, 2, '本轮应恰好提交两项改动: ' + JSON.stringify(bodies));
    assert.deepEqual(putFor(ctx, '循环时间'), { section: '录制设置', key: '循环时间', value: '30' },
        '普通配置键的请求体被认证口令污染（M-22 回归）');
    assert.equal(putFor(ctx, 'web_auth_enable').reauth_password, 'current-pw');
});

test('M-22 反向边界：只改普通 Web 键不弹口令窗、不发口令（复验范围不得扩大）', async () => {
    // 反向边界（与后端一致）：其余 Web 键（web_host/web_port…）不受强复验影响，
    // 否则「改个端口也要复验」会逼人绕过面板手改文件。
    const ctx = await bootConfigView(AUTH_CONFIG);
    findInput(ctx, 'web_host').value = '0.0.0.0';
    clickSave(ctx);
    await flush();
    assert.ok(!modalVisible(ctx), '非认证键的保存也弹出了口令窗（复验范围被扩大）');
    assert.deepEqual(putBodies(ctx), [{ section: 'Web', key: 'web_host', value: '0.0.0.0' }]);
});

test('M-22：两个认证键共用一次采集（每轮保存最多弹一次口令窗）', async () => {
    // 若第二次采集仍在，第二个 PUT 会因 Promise 永不落地而根本不发生——本用例不点第二次确认，
    // 因此「两个键都提交成功」就是「只问了一次」的证明。
    const ctx = await bootConfigView(AUTH_CONFIG);
    findInput(ctx, 'web_auth_enable').value = 'false';
    findInput(ctx, 'web_password').value = 'new-secret';
    clickSave(ctx);
    assert.ok(modalVisible(ctx), '用例前提失效：认证键未弹出口令窗');
    ctx.elements.get('reauth-password').value = 'current-pw';
    clickReauthConfirm(ctx);
    await flush();
    assert.equal(putFor(ctx, 'web_auth_enable').reauth_password, 'current-pw');
    assert.equal(putFor(ctx, 'web_password').reauth_password, 'current-pw');
    assert.ok(!modalVisible(ctx), '第二个认证键又弹出了口令窗（每轮最多采集一次的约定被破坏）');
});

test('M-22 反向边界：认证当前关闭时启用认证不采口令（否则第一次收紧配置被口令窗死锁）', async () => {
    // 判据与后端同源：update_config 的 MID-2241 段**只在 web_auth_enable 现为真**时要求
    // reauth_password（认证关闭时没有可信的「当前口令」可验）。前端若无条件弹窗，「第一次打开
    // 认证」就永远走不通：用户没有旧口令可填 → 留空即放弃 → 键被跳过。
    const ctx = await bootConfigView({
        Web: { web_host: '127.0.0.1', web_auth_enable: 'false', web_password: '' },
    });
    findInput(ctx, 'web_auth_enable').value = 'true';
    clickSave(ctx);
    await flush();
    assert.ok(!modalVisible(ctx), '认证处于关闭态时仍弹出口令窗（与后端判定条件不一致）');
    assert.deepEqual(putFor(ctx, 'web_auth_enable'), { section: 'Web', key: 'web_auth_enable', value: 'true' },
        '启用认证的请求体形状被改动（多带/少带字段都会破坏既有请求契约）');
});

// —— 行为：取消与空值（绝不裸提交）——————————————————————————

test('M-22：取消口令窗 → 认证键不提交并计入「已跳过 N 项认证相关改动」（不静默吞掉）', async () => {
    const ctx = await bootConfigView(AUTH_CONFIG);
    findInput(ctx, 'web_auth_enable').value = 'false';
    clickSave(ctx);
    clickReauthCancel(ctx);
    await flush();
    assert.equal(putFor(ctx, 'web_auth_enable'), undefined, '用户取消后仍提交了认证键');
    assert.match(ctx.elements.get('toast').textContent, /已跳过 1 项认证相关改动/);
    assert.equal(ctx.elements.get('reauth-password').value, '', '取消后口令残留在输入节点里');
});

test('M-22：取消认证键不得卡住同一轮里的普通配置键', async () => {
    // 取消只作用于认证两键，普通键照旧提交。末尾 toast 是「已保存 1 项」而非「已跳过…」——
    // saveConfig 的优先级是 count>0 先于 skippedAuth（既有口径），故这里按请求集合断言。
    const ctx = await bootConfigView(AUTH_CONFIG);
    findInput(ctx, 'web_auth_enable').value = 'false';
    findInput(ctx, '循环时间').value = '20';
    clickSave(ctx);
    clickReauthCancel(ctx);
    await flush();
    assert.deepEqual(putBodies(ctx), [{ section: '录制设置', key: '循环时间', value: '20' }],
        '取消认证键的提交集合不符合预期（普通键被连带阻塞，或认证键仍被提交）');
});

test('M-22：留空提交即放弃本次认证改动，绝不发出不带 reauth_password 的认证键 PUT', async () => {
    // 后端契约：认证已开启时空/缺 reauth_password 都是 403。旧形态让 prompt 的空串照样走 PUT
    // （白撞一次 403、日志里留一条 auth_reauth_denied），现在前端就地跳过。
    const ctx = await bootConfigView(AUTH_CONFIG);
    findInput(ctx, 'web_auth_enable').value = 'false';
    clickSave(ctx);
    clickReauthConfirm(ctx);   // 输入框为空即确认
    await flush();
    assert.equal(putFor(ctx, 'web_auth_enable'), undefined, '空口令仍被提交（必然撞上后端 403）');
    assert.match(ctx.elements.get('toast').textContent, /已跳过 1 项认证相关改动/);
});

test('M-22：Esc 与点遮罩都等同取消（四个出口同结论，不得有第五个「半提交」出口）', async () => {
    for (const close of [
        ctx => fireDocumentKey(ctx, 'Escape'),
        ctx => clickReauthOverlay(ctx),
    ]) {
        const ctx = await bootConfigView(AUTH_CONFIG);
        findInput(ctx, 'web_password').value = 'new-secret';
        clickSave(ctx);
        ctx.elements.get('reauth-password').value = 'typed-then-esc';
        close(ctx);
        await flush();
        assert.equal(putFor(ctx, 'web_password'), undefined, '取消路径仍提交了认证键');
        assert.ok(!modalVisible(ctx), '取消后口令窗未隐藏');
        assert.equal(ctx.elements.get('reauth-password').value, '', '取消后口令残留在输入节点里');
    }
});

test('M-22：Enter 等同确认，且确认后输入节点立即被清空（DOM 不残留口令）', async () => {
    const ctx = await bootConfigView(AUTH_CONFIG);
    findInput(ctx, 'web_auth_enable').value = 'false';
    clickSave(ctx);
    // 非阻塞弹窗必须关掉重入入口（原 window.prompt 是阻塞的，第二次点击进不来）
    assert.equal(ctx.elements.get('config-save-btn').disabled, true, '口令窗打开时「保存配置」未禁用（可重入两条 saveConfig）');
    ctx.elements.get('reauth-password').value = 'current-pw';
    fireReauthKey(ctx, 'Enter');
    await flush();
    assert.equal(putFor(ctx, 'web_auth_enable').reauth_password, 'current-pw', 'Enter 未提交口令');
    assert.equal(ctx.elements.get('reauth-password').value, '', '提交后口令仍留在 #reauth-password');
    assert.ok(!modalVisible(ctx), '提交后口令窗未收起');
    assert.equal(ctx.elements.get('config-save-btn').disabled, false, '结算后未恢复「保存配置」按钮');
});

// —— 行为：后端 403 的善后（与强制复验契约对齐）——————————————————

test('M-22：后端因复验失败回 403 时走既有善后（标红 + 常驻明细 + 回拉真值），不得静默', async () => {
    let reloads = 0;
    const ctx = await bootConfigView(AUTH_CONFIG, {
        routes: {
            'GET /api/config': () => { reloads += 1; return { json: AUTH_CONFIG }; },
            'PUT /api/config': () => ({
                status: 403,
                json: { detail: '修改 Web 认证配置必须复验当前访问口令（reauth_password）' },
            }),
        },
    });
    const reloadsBefore = reloads;
    findInput(ctx, 'web_auth_enable').value = 'false';
    clickSave(ctx);
    ctx.elements.get('reauth-password').value = 'wrong-pw';
    clickReauthConfirm(ctx);
    await flush();
    assert.equal(putFor(ctx, 'web_auth_enable').reauth_password, 'wrong-pw', '用例前提失效：未携带复验口令');
    // JSON 错误契约不得漂移：toast 只显示 detail
    assert.match(ctx.elements.get('toast').textContent, /必须复验当前访问口令/);
    assert.ok(!ctx.elements.get('toast').textContent.includes('"detail"'), 'toast 不得回显原始 JSON');
    assert.ok(!ctx.elements.get('config-save-status').classList.contains('hidden'),
        '403 后必须留下常驻失败明细（半份配置落盘更难排查）');
    assert.ok(reloads > reloadsBefore, '失败后未回拉服务端真值，界面停留在「看起来已保存」的假象');
});

// —— 登录框口令残留（不扩大为重构登录流程）——————————————————

test('M-22 配套：登录成功后清空 #login-password，失败时保留原文', async () => {
    const ok = await bootConfigView(AUTH_CONFIG, {
        routes: { 'POST /api/login': { json: { token: 'tok-abc' } } },
    });
    ok.elements.get('login-password').value = 'pw-1';
    ok.elements.get('login-submit')._listeners.click[0]();
    await flush();
    assert.equal(ok.elements.get('login-password').value, '', '登录成功后口令仍留在隐藏视图的输入框里');

    const bad = await bootConfigView(AUTH_CONFIG, {
        routes: { 'POST /api/login': { status: 401, json: { detail: '口令错误' } } },
    });
    bad.elements.get('login-password').value = 'pw-2';
    bad.elements.get('login-submit')._listeners.click[0]();
    await flush();
    assert.equal(bad.elements.get('login-password').value, 'pw-2', '登录失败清掉原文会让用户重打一遍');
});
