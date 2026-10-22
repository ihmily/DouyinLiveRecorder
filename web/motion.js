// web/motion.js — 轻量动效层（零依赖、纯原生）。
//
// 职责：在保持 index.html 结构与 app.js 渲染逻辑不变的前提下，为面板提供克制的动效：
//   1) 滚动入场（IntersectionObserver，命中即显，一次性 unobserve，不插包裹元素）；
//   2) 悬停/焦点反馈（纯 CSS，见 style.css）；
//   3) 轻量粒子背景（单 canvas、单 rAF、视口面积定粒子数、document.hidden 暂停）；
//   4) 可访问性闸门：prefers-reduced-motion 命中时完全关闭 canvas 与入场过渡。
// 自启动：DOM 就绪即 init，不依赖 app.js，降低回归风险（app.js 改动面缩小）。
// 被 tests/frontend/test_motion.mjs 在 node:vm 沙箱内驱动（零 npm 依赖）。
(function () {
    "use strict";

    var Motion = {};
    var rafId = null;
    var canvas = null;
    var cctx = null;
    var particles = [];
    var running = false;
    var io = null;

    function win() { return (typeof window !== "undefined") ? window : {}; }
    function doc() { return (typeof document !== "undefined") ? document : {}; }

    // prefers-reduced-motion：环境缺失时降级为「不开启动效」，绝不报错。
    function prefersReduced() {
        try {
            var m = win().matchMedia;
            if (m) return !!m.call(win(), "(prefers-reduced-motion: reduce)").matches;
        } catch (e) { /* 环境无 matchMedia：按不开启处理 */ }
        return false;
    }

    // 纯函数：粒子数 = clamp(18, area/22000, 64)；小屏（<768px）或低核数（<=4）减半。
    // 提取为纯函数便于单测与不依赖 DOM 的复算。
    Motion.computeParticleCount = function (area, width, cores) {
        var n = Math.floor((area || 0) / 22000);
        if (n < 18) n = 18;
        if (n > 64) n = 64;
        if ((width || 0) < 768 || (cores || 8) <= 4) n = Math.ceil(n / 2);
        return n;
    };

    function viewport() {
        var w = win().innerWidth || (doc().documentElement && doc().documentElement.clientWidth) || 0;
        var h = win().innerHeight || (doc().documentElement && doc().documentElement.clientHeight) || 0;
        return { w: w, h: h, area: w * h };
    }

    function spawnParticles(n) {
        particles = [];
        var v = viewport();
        var w = v.w || 800, h = v.h || 600;
        for (var i = 0; i < n; i++) {
            particles.push({
                x: Math.random() * w,
                y: Math.random() * h,
                vx: (Math.random() - 0.5) * 0.25,
                vy: (Math.random() - 0.5) * 0.25,
                r: Math.random() * 1.6 + 0.6,
                a: Math.random() * 0.35 + 0.1,
            });
        }
    }

    function resize() {
        if (!canvas || !cctx) return;
        var v = viewport();
        var w = v.w || 800, h = v.h || 600;
        var dpr = Math.min(win().devicePixelRatio || 1, 2); // DPR 封顶 2：移动端高分屏不至于画布爆炸
        canvas.width = Math.max(1, Math.floor(w * dpr));
        canvas.height = Math.max(1, Math.floor(h * dpr));
        canvas.style.width = w + "px";
        canvas.style.height = h + "px";
        cctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        spawnParticles(Motion.computeParticleCount(w * h, w, win().hardwareConcurrency));
    }

    function step() {
        var v = viewport();
        var w = v.w || 800, h = v.h || 600;
        for (var i = 0; i < particles.length; i++) {
            var p = particles[i];
            p.x += p.vx; p.y += p.vy;
            if (p.x < 0) p.x += w; else if (p.x > w) p.x -= w;
            if (p.y < 0) p.y += h; else if (p.y > h) p.y -= h;
        }
    }

    function draw() {
        if (!cctx) return;
        var v = viewport();
        var w = v.w || 800, h = v.h || 600;
        cctx.clearRect(0, 0, w, h);
        var theme = (doc().body && doc().body.dataset && doc().body.dataset.theme) || "light";
        cctx.fillStyle = (theme === "dark") ? "rgba(255,255,255,1)" : "rgba(79,109,245,1)";
        for (var i = 0; i < particles.length; i++) {
            var p = particles[i];
            cctx.globalAlpha = p.a;
            cctx.beginPath();
            cctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            cctx.fill();
        }
        cctx.globalAlpha = 1;
    }

    function loop() {
        if (!running) return;
        // 页面不可见：跳过步进与绘制，仍保留循环以便回到前台续跑（避免卸载/重建成本）。
        if (!doc().hidden) { step(); draw(); }
        rafId = (win().requestAnimationFrame || setTimeout)(loop);
    }

    // 背景 canvas：优先复用 index.html 静态声明的 #bg-canvas，缺失时自建并挂到 body。
    function setupCanvas() {
        var d = doc();
        try {
            canvas = d.getElementById ? d.getElementById("bg-canvas") : null;
            if (!canvas && d.createElement) {
                canvas = d.createElement("canvas");
                canvas.id = "bg-canvas";
                canvas.setAttribute("aria-hidden", "true");
                var host = d.body || d.documentElement;
                if (host && host.appendChild) host.appendChild(canvas);
            }
            cctx = canvas && canvas.getContext ? canvas.getContext("2d") : null;
            if (!cctx) { canvas = null; return; }
            if (win().addEventListener) win().addEventListener("resize", resize, { passive: true });
            resize();
        } catch (e) { canvas = null; cctx = null; }
    }

    function start() {
        if (running || !canvas || !cctx) return;
        running = true;
        rafId = (win().requestAnimationFrame || setTimeout)(loop);
    }

    // 滚动入场：对 .panel / .stat-card / [data-reveal] 加 .reveal（初始隐藏），
    // 进入视口后加 .is-revealed 触发 CSS 过渡。reduced 模式直接可见，不加隐藏态。
    Motion.applyReveal = function () {
        var d = doc();
        var els = [];
        try {
            var lists = [".panel", ".stat-card", "[data-reveal]"];
            for (var l = 0; l < lists.length; l++) {
                var found = d.querySelectorAll ? d.querySelectorAll(lists[l]) : [];
                for (var k = 0; k < found.length; k++) els.push(found[k]);
            }
        } catch (e) { return; }
        if (!els.length) return;
        if (prefersReduced()) {
            for (var r = 0; r < els.length; r++) els[r].classList.add("is-revealed");
            return;
        }
        var Observer = win().IntersectionObserver;
        if (Observer) {
            io = new Observer(function (entries, observer) {
                for (var i = 0; i < entries.length; i++) {
                    if (entries[i].isIntersecting) {
                        entries[i].target.classList.add("reveal");
                        entries[i].target.classList.add("is-revealed");
                        // 用回调第二个参数（observer 实例）而非外层 io：避免「new 之后同步 observe
                        // 时 io 尚未赋值」的闭包顺序问题（同步触发的桩会暴露，浏览器异步回调不暴露）。
                        observer.unobserve(entries[i].target);
                    }
                }
            }, { threshold: 0.15, rootMargin: "0px 0px -8% 0px" });
            for (var j = 0; j < els.length; j++) { els[j].classList.add("reveal"); io.observe(els[j]); }
        } else {
            for (var m = 0; m < els.length; m++) {
                (function (el, idx) {
                    setTimeout(function () { el.classList.add("is-revealed"); }, Math.min(idx * 40, 240));
                })(els[m], m);
                els[m].classList.add("reveal");
            }
        }
    };

    Motion.init = function () {
        Motion.applyReveal();
        if (prefersReduced()) return; // 关闭入场过渡与背景动画
        setupCanvas();
        start();
    };

    // 清理：停止循环、断开观察器、移除 resize 监听、拆掉自建 canvas。
    Motion.destroy = function () {
        running = false;
        if (rafId != null && win().cancelAnimationFrame) {
            try { win().cancelAnimationFrame(rafId); } catch (e) { /* noop */ }
        }
        rafId = null;
        if (io && io.disconnect) { try { io.disconnect(); } catch (e) { /* noop */ } io = null; }
        if (win().removeEventListener) win().removeEventListener("resize", resize);
        if (canvas && canvas.parentNode && canvas.parentNode.removeChild) {
            try { canvas.parentNode.removeChild(canvas); } catch (e) { /* noop */ }
        }
        canvas = null; cctx = null; particles = [];
    };

    // 测试探针：返回运行期内部状态，零副作用。
    Motion.state = function () {
        return {
            running: running,
            hasCanvas: !!canvas,
            particleCount: particles.length,
            rafId: rafId,
        };
    };

    // 自启动：DOM 就绪后 init（无需等待 app.js）。
    function boot() {
        if (Motion._booted) return;
        Motion._booted = true;
        try { Motion.init(); } catch (e) { /* 启动期异常不得影响面板主流程 */ }
    }
    if (typeof document !== "undefined") {
        if (doc().readyState === "loading") {
            if (win().addEventListener) win().addEventListener("DOMContentLoaded", boot);
        } else { boot(); }
    }
    if (typeof window !== "undefined") window.__dlrMotion = Motion;
})();
