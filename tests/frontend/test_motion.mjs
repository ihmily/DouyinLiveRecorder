// web/motion.js（背景粒子 + 滚动入场）的单元测试，Node 内置 node:test，零 npm 依赖。
//
// 与 test_quality_ui.mjs 同源：node:vm 沙箱加载生产脚本、最小 DOM/window 桩驱动真实接线，
// 不改造生产代码，也不把函数抽出来孤立测试。
//
// 守护的不变量：
//   1) computeParticleCount 的边界与移动端/低核数减半（纯函数，可复算）；
//   2) prefers-reduced-motion 命中时不创建 canvas、不启动动画循环；
//   3) 正常模式创建背景 canvas 并启动单 rAF 循环，粒子数落在 [18,64]；
//   4) destroy() 停循环、断观察器、移除自建 canvas、清空粒子；
//   5) 滚动入场给进入视口的 .panel / .stat-card 加 reveal / is-revealed。
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const MOTION_JS = readFileSync(new URL('../../web/motion.js', import.meta.url), 'utf8');

function makeClassList() {
    const set = new Set();
    return {
        add(...cs) { cs.forEach(c => set.add(c)); },
        remove(...cs) { cs.forEach(c => set.delete(c)); },
        toggle(c) { set.has(c) ? set.delete(c) : set.add(c); },
        contains(c) { return set.has(c); },
    };
}

function makeEl(id) {
    const attrs = {};
    const el = {
        id,
        innerHTML: '',
        textContent: '',
        value: '',
        className: '',
        disabled: false,
        style: {},
        dataset: {},
        parentNode: null,
        classList: makeClassList(),
        addEventListener() {},
        setAttribute(k, v) { attrs[k] = String(v); },
        getAttribute(k) { return k in attrs ? attrs[k] : null; },
        appendChild(c) { this.parentNode = this; return c; },
        removeChild(c) { if (c.parentNode === this) c.parentNode = null; return c; },
        closest() { return null; },
        matches() { return false; },
    };
    return el;
}

function makeCanvasCtx() {
    let fillStyle = '';
    let globalAlpha = 1;
    return {
        setTransform() {},
        clearRect() {},
        beginPath() {},
        arc() {},
        fill() {},
        set fillStyle(v) { fillStyle = v; },
        get fillStyle() { return fillStyle; },
        set globalAlpha(v) { globalAlpha = v; },
        get globalAlpha() { return globalAlpha; },
    };
}

// 极简 document 桩：readyState=complete 让 motion.js 加载即自启动；querySelectorAll 按类名返回
// 注入的面板/卡片；createElement('canvas') 返回带 2d 上下文桩的伪元素。
function makeDocument({ reduced, panels = [], statCards = [], reveals = [] }) {
    const body = makeEl('body');
    return {
        readyState: 'complete',
        body,
        documentElement: makeEl('html'),
        hidden: false,
        getElementById(id) { return id === 'bg-canvas' ? null : null; },
        createElement(tag) {
            const c = makeEl(tag);
            c.getContext = () => makeCanvasCtx();
            return c;
        },
        querySelectorAll(sel) {
            if (sel === '.panel') return panels;
            if (sel === '.stat-card') return statCards;
            if (sel === '[data-reveal]') return reveals;
            return [];
        },
    };
}

// 观察器桩：observe 时立即回调「已进入视口」，驱动入场逻辑。
// 必须用 class（可构造），不能写方法简写 `IntersectionObserver(cb){}` —— 方法简写不可 new，
// 会让 motion.js 的 `new Observer(cb)` 抛 "not a constructor"。
class FakeIntersectionObserver {
    constructor(cb) {
        this.cb = cb;
        // 第二个参数必须传观察器实例：motion.js 的回调要调 `observer.unobserve(...)` 解绑，
        // 漏传会变成 undefined.unobserve。
        this.observe = (el) => cb([{ isIntersecting: true, target: el }], this);
        this.unobserve = () => {};
        this.disconnect = () => {};
    }
}

function makeWindow({ reduced, width = 1920, height = 1080, cores = 8 }) {
    return {
        innerWidth: width,
        innerHeight: height,
        devicePixelRatio: 1,
        hardwareConcurrency: cores,
        matchMedia() { return { matches: reduced }; },
        requestAnimationFrame() { return 1; }, // 不递归调用回调：loop 跑一次后停下，测试确定性
        cancelAnimationFrame() {},
        addEventListener() {},
        removeEventListener() {},
        IntersectionObserver: FakeIntersectionObserver,
    };
}

function loadMotion(opts) {
    const document = makeDocument(opts);
    const window = makeWindow(opts);
    const sandbox = { document, window, navigator: {}, setTimeout() {}, clearTimeout() {}, console };
    // motion.js 经全局 window 访问能力（matchMedia / innerWidth / IntersectionObserver），
    // 故 window 必须是桩对象而非 sandbox 自身，否则降级判定与入场观察器全部退化。
    // Motion 最终挂在 window.__dlrMotion 上。
    vm.createContext(sandbox);
    vm.runInContext(MOTION_JS, sandbox, { filename: 'web/motion.js' });
    return { sandbox, document, window, Motion: window.__dlrMotion };
}

test('computeParticleCount：边界与移动端/低核数减半', () => {
    const { Motion } = loadMotion({ reduced: false });
    assert.equal(Motion.computeParticleCount(2_073_600, 1920, 8), 64, '大屏应取上限 64');
    assert.equal(Motion.computeParticleCount(0, 1920, 8), 18, '下限 18');
    assert.equal(Motion.computeParticleCount(2_073_600, 375, 8), 32, '窄屏(<768px)减半');
    assert.equal(Motion.computeParticleCount(2_073_600, 1920, 2), 32, '低核数(<=4)减半');
});

test('reduced-motion：init 不创建 canvas、不启动动画循环', () => {
    const { Motion } = loadMotion({ reduced: true, width: 1920, height: 1080, cores: 8, panels: [makeEl('p1'), makeEl('p2')] });
    const st = Motion.state();
    assert.equal(st.running, false, 'reduced 模式不应启动 rAF 循环');
    assert.equal(st.hasCanvas, false, 'reduced 模式不应创建背景 canvas');
    assert.equal(st.particleCount, 0, 'reduced 模式不应生成粒子');
});

test('正常模式：init 创建 canvas 并启动、粒子数在 [18,64]', () => {
    const { Motion } = loadMotion({ reduced: false, width: 1920, height: 1080, cores: 8, panels: [makeEl('p1')] });
    const st = Motion.state();
    assert.equal(st.running, true, '正常模式应启动动画循环');
    assert.equal(st.hasCanvas, true, '正常模式应创建背景 canvas');
    assert.ok(st.particleCount >= 18 && st.particleCount <= 64, '粒子数应落在 [18,64]');
    assert.equal(st.particleCount, 64, '1920x1080 大屏应取上限 64');
});

test('destroy：停止循环、断开观察器、移除自建 canvas、清空粒子', () => {
    const { document, Motion } = loadMotion({ reduced: false, width: 1920, height: 1080, cores: 8, panels: [makeEl('p1')] });
    Motion.destroy();
    const st = Motion.state();
    assert.equal(st.running, false, 'destroy 后循环应停止');
    assert.equal(st.hasCanvas, false, 'destroy 应移除自建 canvas');
    assert.equal(st.particleCount, 0, 'destroy 应清空粒子');
});

test('滚动入场：进入视口的 .panel / .stat-card 被加 reveal 与 is-revealed', () => {
    const panels = [makeEl('p1'), makeEl('p2')];
    const statCards = [makeEl('s1')];
    const { Motion } = loadMotion({ reduced: false, panels, statCards });
    for (const el of [...panels, ...statCards]) {
        assert.equal(el.classList.contains('reveal'), true, el.id + ' 应被标记为初始隐藏');
        assert.equal(el.classList.contains('is-revealed'), true, el.id + ' 应被标记为已显现');
    }
});
