/**
 * 计算咪咕播放地址的 ddCalcu 签名参数（2026-08 重写，适配 Node.js 24.19.0 / migu 播放器 v_20260731+）
 *
 * 背景：migu 官网播放器（/mgs/player/prd/dist/dataFetcher.js）自 2025 下半年起变更了
 * mgprtcl.wasm 的接口——导入函数从 3 个（a/b/c）扩至 12 个（a..l），导出名整体重排
 * （对照播放器 Emscripten 胶水层映射：memory=m、malloc=p、free=q、CI1=t、CI2=u、
 * CI3=v、CI4=w、CI5=x、CI6=y、CI7=z、CI8=A、CI9=B、CI10=C、CI11=D、CI12=E、CI14=F），
 * 且固定加密因子改为经 /gateway/app-management/videox/staticcache/v2/factor 接口下发
 * （失败时回退播放器内置默认因子）。旧脚本按旧导出名（d/h..r/t/u）取函数，在任何
 * Node 版本下实例化/调用均失败。
 *
 * 用法：node migu.js <含 puData 参数的播放地址>
 * 输出：带 ddCalcu 与 sv 参数的完整地址（stdout 单行；URL 无 puData 参数时原样输出）
 */

// 播放器内置默认加密因子（dataFetcher.js EncryptionFactor 常量，因子接口失败时的回退值）
const DEFAULT_FACTOR = { sv: '119', factor: 'BjfS7eNf3OIROs2T1E8hHQ==' };

// 获取加密因子：优先请求官网接口，失败时回退内置默认（与播放器行为一致）
async function fetchEncryptionFactor() {
    const appId = 'miguvideo';
    const terminal = 'www';
    const api = `https://www.miguvideo.com/gateway/app-management/videox/staticcache/v2/factor/${appId}/${terminal}`;
    try {
        const resp = await fetch(api, {
            headers: {
                'User-Agent':
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0',
                Referer: 'https://www.miguvideo.com/',
                Origin: 'https://www.miguvideo.com',
                Accept: 'application/json, text/plain, */*',
                appCode: 'miguvideo_default_www',
                appId: appId,
                channel: 'H5',
            },
        });
        if (!resp.ok) throw new Error(`factor api http ${resp.status}`);
        const json = await resp.json();
        const body = json && json.body;
        if (body && body.sv && body.factor) {
            return { sv: String(body.sv), factor: String(body.factor) };
        }
        throw new Error('factor api empty body');
    } catch {
        // 接口 403/网络失败等：回退内置默认因子（播放器同款兜底逻辑）
        return DEFAULT_FACTOR;
    }
}

/**
 * 对播放地址计算 ddCalcu 签名，返回带 ddCalcu/sv 参数的完整地址
 * @param {string} inputUrl - 加密前的原始播放地址（须含 puData 查询参数）
 * @returns {Promise<string>} - 追加 ddCalcu 与 sv 参数后的地址
 */
async function getDdCalcu(inputUrl) {
    let memory_p = null; // Uint8Array view
    let memory_h = null; // Uint32Array view

    // 工具函数：把字符串按 UTF-8 写入内存并补 \0 结尾
    function stringToUTF8(string, offset) {
        const encoder = new TextEncoder();
        const encoded = encoder.encode(string);
        for (let i = 0; i < encoded.length; i++) {
            memory_p[offset + i] = encoded[i];
        }
        memory_p[offset + encoded.length] = 0; // Null-terminate
    }

    // 工具函数：从内存地址读取 \0 结尾的 UTF-8 字符串
    function UTF8ToString(offset) {
        let s = '';
        let i = 0;
        while (memory_p[offset + i]) {
            s += String.fromCharCode(memory_p[offset + i]);
            i++;
        }
        return s;
    }

    // WASM 导入函数（模块 "a"）：a 为求和实现，其余为 Emscripten 环境桩。
    // 2025 下半年起 wasm 需要 12 个导入（a..l），缺失会在实例化时抛
    // LinkError: function import requires a callable（任何 Node 版本一致）。
    function a(e, t, r, n) {
        let s = 0;
        for (let i = 0; i < r; i++) {
            const d = memory_h[t + 4 >> 2];
            t += 8;
            s += d;
        }
        memory_h[n >> 2] = s;
        return 0;
    }
    function b() {}
    function c() {}
    function d() {}
    function e() {}
    function f() {}
    function g() {}
    function h() {}
    function i() {}
    function j() {}
    function k() {}
    function l() {}

    // 第一步：获取 playerVersion（决定 wasm 下载地址）
    const settingsResp = await fetch('https://app-sc.miguvideo.com/common/v1/settings/H5_DetailPage');
    const settingsData = await settingsResp.json();
    const playerVersion = JSON.parse(settingsData.body.paramValue).playerVersion;

    // 第二步：下载并实例化 WASM 模块
    const wasmUrl = `https://www.miguvideo.com/mgs/player/prd/${playerVersion}/dist/mgprtcl.wasm`;
    const wasmResp = await fetch(wasmUrl);
    if (!wasmResp.ok) throw new Error("Failed to download WASM");
    const wasmBuffer = await wasmResp.arrayBuffer();

    const importObject = {
        a: { a, b, c, d, e, f, g, h, i, j, k, l }
    };

    const { instance } = await WebAssembly.instantiate(wasmBuffer, importObject);
    const wasmInstance = instance;

    const memory = wasmInstance.exports.m;
    memory_p = new Uint8Array(memory.buffer);
    memory_h = new Uint32Array(memory.buffer);

    // 导出映射（对照播放器 Emscripten 胶水层，v_20260731+ 版 wasm）
    const exports = {
        CallInterface1: wasmInstance.exports.t,
        CallInterface2: wasmInstance.exports.u,
        CallInterface3: wasmInstance.exports.v,
        CallInterface4: wasmInstance.exports.w,
        CallInterface6: wasmInstance.exports.y,
        CallInterface7: wasmInstance.exports.z,
        CallInterface8: wasmInstance.exports.A,
        CallInterface9: wasmInstance.exports.B,
        CallInterface10: wasmInstance.exports.C,
        CallInterface11: wasmInstance.exports.D,
        CallInterface14: wasmInstance.exports.F,
        malloc: wasmInstance.exports.p,
        free: wasmInstance.exports.q,
    };

    // 第三步：获取加密因子（接口失败回退内置默认）
    const { sv, factor } = await fetchEncryptionFactor();

    // URL 无 puData 参数时无需签名（与播放器行为一致，原样返回）
    const parsedUrl = new URL(inputUrl);
    const query = Object.fromEntries(parsedUrl.searchParams);
    const puData = query.puData || '';
    if (puData.length === 0) {
        return inputUrl;
    }

    const userid = query.userid || '';
    const timestamp = query.timestamp || '';
    const programId = query.ProgramID || '';
    const channelId = query.Channel_ID || '';

    // 分配内存
    const useridPtr = exports.malloc(userid.length + 1);
    const tsPtr = exports.malloc(timestamp.length + 1);
    const pidPtr = exports.malloc(programId.length + 1);
    const cidPtr = exports.malloc(channelId.length + 1);
    const pudPtr = exports.malloc(puData.length + 1);
    const factorPtr = exports.malloc(factor.length + 1);
    const midPtr = exports.malloc(128);
    const outPtr = exports.malloc(128);

    // 写入数据
    stringToUTF8(userid, useridPtr);
    stringToUTF8(timestamp, tsPtr);
    stringToUTF8(programId, pidPtr);
    stringToUTF8(channelId, cidPtr);
    stringToUTF8(puData, pudPtr);
    stringToUTF8(factor, factorPtr);

    // 按播放器调用顺序执行签名
    const ctx = exports.CallInterface6(); // 创建上下文
    if (-1 === exports.CallInterface1(ctx, pidPtr, programId.length)) throw new Error('CallInterface1 failed');
    if (-1 === exports.CallInterface10(ctx, tsPtr, timestamp.length)) throw new Error('CallInterface10 failed');
    if (-1 === exports.CallInterface9(ctx, useridPtr, userid.length)) throw new Error('CallInterface9 failed');
    if (-1 === exports.CallInterface3(ctx, null, 0)) throw new Error('CallInterface3 failed');
    if (-1 === exports.CallInterface11(ctx, null, 0)) throw new Error('CallInterface11 failed');
    if (-1 === exports.CallInterface8(ctx, pudPtr, puData.length)) throw new Error('CallInterface8 failed');
    if (-1 === exports.CallInterface2(ctx, cidPtr, channelId.length)) throw new Error('CallInterface2 failed');
    if (-1 === exports.CallInterface14(ctx, factorPtr, factor.length, midPtr, 128)) throw new Error('CallInterface14 failed');

    const midValue = UTF8ToString(midPtr);
    const midPtr2 = exports.malloc(midValue.length + 1);
    stringToUTF8(midValue, midPtr2);

    if (-1 === exports.CallInterface7(ctx, midPtr2, midValue.length)) {
        throw new Error('CallInterface7 failed');
    }

    // CI4 可能未就绪：按播放器逻辑小间隔重试（非 0 非 -1 为"未完成"）
    let code = -1;
    for (let attempt = 0; attempt < 5; attempt++) {
        code = exports.CallInterface4(ctx, outPtr, 128);
        if (code === 0 || code === -1) break;
        await new Promise((resolve) => setTimeout(resolve, 200));
    }
    if (code !== 0) throw new Error(`CallInterface4 failed with code ${code}`);

    const ddCalcu = UTF8ToString(outPtr);
    // 释放堆内存（free 存在时）
    if (exports.free) {
        for (const ptr of [useridPtr, tsPtr, pidPtr, cidPtr, pudPtr, factorPtr, midPtr, outPtr, midPtr2]) {
            try { exports.free(ptr); } catch (_) { /* 释放失败可忽略 */ }
        }
    }
    return `${inputUrl}&ddCalcu=${ddCalcu}&sv=${sv}`;
}

const url = process.argv[2];

if (!url) {
    console.error('Usage: node migu.js <play_url_with_puData>');
    process.exit(1);
}

getDdCalcu(url).then(result => {
    console.log(result);
}).catch(err => {
    console.error(err);
    process.exit(1);
});
