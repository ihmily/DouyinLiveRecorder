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
 *
 * 安全提示：本文件被钉定，但**真正执行签名算法的 mgprtcl.wasm 是每次运行现取的**，
 * 不在钉定范围内——完整信任边界与运维口径见下方「远程取用的信任边界（MID-62）」。
 */

// 播放器内置默认加密因子（dataFetcher.js EncryptionFactor 常量，因子接口失败时的回退值）
const DEFAULT_FACTOR = { sv: '119', factor: 'BjfS7eNf3OIROs2T1E8hHQ==' };

// ── 远程取用的信任边界（MID-62，改动本段前先读完这段）────────────────────────
// **被钉定的**：只有「本文件的胶水层字节」。src/utils.py 的 _JS_SHA256_EXPECTED 在把字节
// 交给 node 之前逐字节比对（不符即告警；DLR_JS_STRICT_HASH=1 时直接拒绝执行）。
// **未被钉定、按「每次 fetch 到的内容」信任的**：
//   ① H5_DetailPage 设置接口返回的 playerVersion —— 它决定 ② 的下载地址；
//   ② mgprtcl.wasm 本体 —— 真正执行签名算法的是它，本文件只是把参数搬进线性内存；
//   ③ videox/staticcache/v2/factor 下发的 sv / factor 加密因子。
// 为什么不把 ①②③ 也钉住：wasm 与 playerVersion 随官网发版频繁变动（版本号形如
// v_20260731），钉死即供应商每次改版都让咪咕静默解析失败，而钉定值又没有可让用户自助更新的
// 正规来源（胶水层不同：它随仓库分发、变更必经维护者）。故此处选择「写明边界 + 加离线
// 可做的廉价护栏」，而不是假装已经完整校验过被执行的字节码。
// 护栏**能**挡：把取用改到 http 明文、指向非 miguvideo 主机、响应被换成 HTML 挑战页 /
// 空 body / 缺字段、wasm 被换成非 wasm 或体积异常（页面、压缩包、巨型 payload）、
// playerVersion 带路径穿越或 `#`/`?`/`@` 之类能改写请求目标的字符、导出表被换构建后错位。
// 护栏**不**挡：上游或 CDN 自身被投毒后，仍在同域、同体积区间内递来的「形状完全合法」的
// wasm —— 那等价于在签名进程内执行远端字节码。要真正收敛这一面只有两条路：把 wasm 也纳入
// 人工跟版的 SRI 钉定，或让咪咕签名不进录制进程。
// 运维该怎么做：把这三处 fetch 当作高信任面看待，出网白名单只放 https://*.miguvideo.com；
// 升级胶水层后先核对来源再更新 _JS_SHA256_EXPECTED，CI / 加固部署里设 DLR_JS_STRICT_HASH=1；
// 若 ddCalcu 集中变空或大面积 403，优先怀疑上游内容变化（本文件的护栏会先抛明确错误）。
const TRUSTED_MIGU_HOSTS = new Set(['www.miguvideo.com', 'app-sc.miguvideo.com']);

// playerVersion 只允许出现在 URL 路径段里的字符集：挡住 ../（换路径）、#（截断请求）、
// @（把 host 换成别的）、以及空白/控制字符。长度上界防的是「整段 HTML 被塞进版本号」。
const PLAYER_VERSION_PATTERN = /^[A-Za-z0-9._-]{1,64}$/;

// wasm 体积护栏（**不是**钉定）：mgprtcl.wasm 实测在数十 KB 量级。区间取得宽，是因为它只
// 负责拦「几十 MB 的垃圾 payload / 1KB 的错误页」这类离群值，不承担识别同域精细投毒的职责。
// 上游若显著改变构建体积，按报错提示放宽这两个数即可（改这里必须连同上面的边界说明一起看）。
const WASM_MIN_BYTES = 20 * 1000;
const WASM_MAX_BYTES = 4 * 1000 * 1000;

// 取用地址校验：协议必须是 https，主机必须在白名单内（精确匹配，不做后缀匹配——
// 后缀匹配会被 miguvideo.com.attacker.example 这类域名绕过）。
function assertTrustedHttpsUrl(rawUrl, label) {
    let parsed = null;
    try {
        parsed = new URL(rawUrl);
    } catch {
        throw new Error(`${label}: 取用地址不是合法 URL`);
    }
    // 明文 http 一律拒绝：那会把「投毒 CDN」降级成「链路上任意一跳都能替换 wasm」，
    // 危害更大且完全无法从内容上察觉。宁可本次签名失败，也不静默放宽信任。
    if (parsed.protocol !== 'https:') {
        throw new Error(`${label}: 拒绝非 https 取用地址（protocol=${parsed.protocol} host=${parsed.host}）`);
    }
    if (parsed.username || parsed.password) {
        throw new Error(`${label}: 取用地址不得携带 userinfo`);
    }
    if (!TRUSTED_MIGU_HOSTS.has(parsed.hostname.toLowerCase())) {
        throw new Error(`${label}: 取用主机不在 migu 白名单内（host=${parsed.hostname}）`);
    }
    return parsed.toString();
}

// wasm 二进制 Sanity：魔数 \0asm + 版本字段 + 体积区间。
// 只判「这是不是一份结构合法的 wasm、尺寸是否在量级正确的区间」，不判内容是否可信。
function assertWasmSanity(bytes, label) {
    if (bytes.length < WASM_MIN_BYTES || bytes.length > WASM_MAX_BYTES) {
        throw new Error(`${label}: 体积 ${bytes.length} 字节超出合理区间 [${WASM_MIN_BYTES}, ${WASM_MAX_BYTES}]，拒绝执行`);
    }
    const magic = [0x00, 0x61, 0x73, 0x6d];
    for (let i = 0; i < 4; i++) {
        if (bytes[i] !== magic[i]) {
            throw new Error(`${label}: 缺少 wasm 魔数 \\0asm（疑为错误页/重定向落地内容），拒绝执行`);
        }
    }
    const version = bytes[4] | (bytes[5] << 8) | (bytes[6] << 16) | (bytes[7] << 24);
    if (version < 1 || version > 13) {
        throw new Error(`${label}: wasm 版本字段异常（${version}）`);
    }
}

// 设置接口响应形状检查：把「body.paramValue 是 JSON 字符串、playerVersion 是受限字符串」
// 这两条钉死，避免把 HTML 挑战页或缺字段的响应直接拼进 URL 去下载并执行。
function readPlayerVersion(settingsData) {
    const body = settingsData && settingsData.body;
    if (!body || typeof body.paramValue !== 'string') {
        throw new Error('H5_DetailPage 响应形状不符预期（缺 body.paramValue）');
    }
    let decoded = null;
    try {
        decoded = JSON.parse(body.paramValue);
    } catch {
        throw new Error('H5_DetailPage 的 body.paramValue 不是合法 JSON');
    }
    if (!decoded || typeof decoded !== 'object') {
        throw new Error('H5_DetailPage 的 paramValue 不是 JSON 对象');
    }
    const playerVersion = decoded.playerVersion;
    if (typeof playerVersion !== 'string' || !PLAYER_VERSION_PATTERN.test(playerVersion)) {
        throw new Error('H5_DetailPage 的 playerVersion 缺失或形态异常');
    }
    return playerVersion;
}

// 获取加密因子：优先请求官网接口，失败时回退内置默认（与播放器行为一致）
async function fetchEncryptionFactor() {
    const appId = 'miguvideo';
    const terminal = 'www';
    const api = `https://www.miguvideo.com/gateway/app-management/videox/staticcache/v2/factor/${appId}/${terminal}`;
    try {
        const resp = await fetch(assertTrustedHttpsUrl(api, 'migu 加密因子接口'), {
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
    let memory = null; // WebAssembly.Memory 本体；grow 之后 memory.buffer 会被**整体替换**

    // 视图（Uint8Array / Uint32Array）一律**即时**从 memory.buffer 构造，绝不缓存成变量：
    // Emscripten 约定 memory.grow 会替换 memory.buffer，此前创建的视图随即 detach
    // （byteLength 归 0），之后写入是**静默 no-op**、读取恒为 0 —— 表现就是
    // `&ddCalcu=&sv=…` 的空签名 + 供应商 403，而是否触发只取决于本次请求是否扩容，
    // 没有任何可见症状（MID-61：2026-08 版把两视图缓存在所有 malloc 之前，即此形态）。
    function heapU8() {
        return new Uint8Array(memory.buffer);
    }

    function heapU32() {
        return new Uint32Array(memory.buffer);
    }

    const TEXT_ENCODER = new TextEncoder();

    // UTF-8 字节长度：交给 wasm 的 length 实参必须是**字节数**，不是 String.length
    // （UTF-16 码元数）。非 ASCII 时按 .length 分配会少给、按 .length 传参会截断。
    function utf8Len(str) {
        return TEXT_ENCODER.encode(str).length;
    }

    // 工具函数：把字符串按 UTF-8 写入内存并补 \0 结尾
    function stringToUTF8(string, offset) {
        const view = heapU8();
        const encoded = TEXT_ENCODER.encode(string);
        if (offset + encoded.length >= view.byteLength) {
            // 越界写在 typed array 上同样是静默丢弃 —— 与 MID-61 同类的「无症状空签名」，
            // 必须显式抛错而不是让签名继续往下走。
            throw new Error(`stringToUTF8 out of bounds: offset=${offset} bytes=${encoded.length} heap=${view.byteLength}`);
        }
        view.set(encoded, offset);
        view[offset + encoded.length] = 0; // Null-terminate
    }

    // 工具函数：从内存地址读取 \0 结尾的字符串，按 UTF-8 解码。
    // 原实现逐字节 String.fromCharCode，实为 **Latin-1** 解码，与 stringToUTF8 的 UTF-8
    // 编码不对称：非 ASCII 字节会解成 mojibake，且其 .length 又被用于下一次 malloc，
    // 于是 midValue → midPtr2 那一跳会按错误长度截断。当前所有产物（mid / ddCalcu）实测
    // 恒为 ASCII，故两口径等价；此处仍改为 TextDecoder，使读写对称、不再依赖 ASCII 假设。
    function UTF8ToString(offset) {
        const view = heapU8();
        let end = offset;
        while (end < view.byteLength && view[end] !== 0) {
            end++;
        }
        return new TextDecoder('utf-8').decode(view.subarray(offset, end));
    }

    // WASM 导入函数（模块 "a"）：a 为求和实现，其余为 Emscripten 环境桩。
    // 2025 下半年起 wasm 需要 12 个导入（a..l），缺失会在实例化时抛
    // LinkError: function import requires a callable（任何 Node 版本一致）。
    function a(e, t, r, n) {
        let s = 0;
        const view = heapU32(); // 每次调用即时取视图，理由见 heapU32 上方（MID-61）
        for (let i = 0; i < r; i++) {
            const d = view[(t + 4) >> 2];
            t += 8;
            s += d;
        }
        view[n >> 2] = s;
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
    // 信任边界见文件头「远程取用的信任边界」：以下两步取回的内容**都没有**被哈希钉定，
    // 被钉定的只是本文件自身；这里只做事前形状/协议/体积护栏，失败一律明确抛错。
    const settingsUrl = assertTrustedHttpsUrl('https://app-sc.miguvideo.com/common/v1/settings/H5_DetailPage', 'migu 设置接口');
    const settingsResp = await fetch(settingsUrl);
    if (!settingsResp.ok) throw new Error(`migu 设置接口 http ${settingsResp.status}`);
    const playerVersion = readPlayerVersion(await settingsResp.json());

    // 第二步：下载并实例化 WASM 模块
    const wasmUrl = assertTrustedHttpsUrl(
        `https://www.miguvideo.com/mgs/player/prd/${playerVersion}/dist/mgprtcl.wasm`,
        'migu wasm 下载地址'
    );
    const wasmResp = await fetch(wasmUrl);
    if (!wasmResp.ok) throw new Error("Failed to download WASM");
    const wasmBuffer = await wasmResp.arrayBuffer();
    assertWasmSanity(new Uint8Array(wasmBuffer), 'migu mgprtcl.wasm');

    const importObject = {
        a: { a, b, c, d, e, f, g, h, i, j, k, l }
    };

    const { instance } = await WebAssembly.instantiate(wasmBuffer, importObject);
    const wasmInstance = instance;

    // 导出表形状检查（护栏之一）：下面的导出名映射与 wasm 构建一一钉死，任一位置不是预期
    // 类型就说明拿到的不是预期构建——继续跑只会在 undefined 上抛裸 TypeError，或更糟：
    // 静默产出垃圾签名（签名错是 403，形状错却可能什么都看不出来）。
    if (!(wasmInstance.exports.m instanceof WebAssembly.Memory)) {
        throw new Error('WASM 导出形状不符预期：exports.m 不是 WebAssembly.Memory');
    }
    for (const name of ['p', 'q', 't', 'u', 'v', 'w', 'y', 'z', 'A', 'B', 'C', 'D', 'F']) {
        if (typeof wasmInstance.exports[name] !== 'function') {
            throw new Error(`WASM 导出形状不符预期：exports.${name} 不是函数`);
        }
    }

    memory = wasmInstance.exports.m;
    // 视图不在这里缓存：heapU8()/heapU32() 会在每次读写时按当前 memory.buffer 重建（MID-61）

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

    // 分配内存：长度一律取 UTF-8 **字节数**（utf8Len），不用 String.length。
    // 这里隐含的 ASCII-only 假设是「签名入参与产物恒为 ASCII」：userid / timestamp /
    // ProgramID / Channel_ID / puData 均来自 URL query（已百分号编码为 ASCII），factor 是
    // base64，ddCalcu 与 mid 实测为 hex/短标识串——串长 == 字节长，故本改动与旧实现输出
    // 逐字节相同。假设一旦被上游打破（例如 mid 变成含非 ASCII 的串），按 .length 分配会
    // 少给内存、stringToUTF8 随即越界；改为字节数后这一形态自动正确，同时也满足
    // 「outPtr/midPtr 各 128 字节的定长缓冲」的容量依据（ASCII 短串）。
    const useridLen = utf8Len(userid);
    const tsLen = utf8Len(timestamp);
    const pidLen = utf8Len(programId);
    const cidLen = utf8Len(channelId);
    const pudLen = utf8Len(puData);
    const factorLen = utf8Len(factor);
    const useridPtr = exports.malloc(useridLen + 1);
    const tsPtr = exports.malloc(tsLen + 1);
    const pidPtr = exports.malloc(pidLen + 1);
    const cidPtr = exports.malloc(cidLen + 1);
    const pudPtr = exports.malloc(pudLen + 1);
    const factorPtr = exports.malloc(factorLen + 1);
    const midPtr = exports.malloc(128);
    const outPtr = exports.malloc(128);

    // 写入数据（视图在每次写入时重建，扩容后依然有效）
    stringToUTF8(userid, useridPtr);
    stringToUTF8(timestamp, tsPtr);
    stringToUTF8(programId, pidPtr);
    stringToUTF8(channelId, cidPtr);
    stringToUTF8(puData, pudPtr);
    stringToUTF8(factor, factorPtr);

    // 按播放器调用顺序执行签名
    const ctx = exports.CallInterface6(); // 创建上下文
    if (-1 === exports.CallInterface1(ctx, pidPtr, pidLen)) throw new Error('CallInterface1 failed');
    if (-1 === exports.CallInterface10(ctx, tsPtr, tsLen)) throw new Error('CallInterface10 failed');
    if (-1 === exports.CallInterface9(ctx, useridPtr, useridLen)) throw new Error('CallInterface9 failed');
    if (-1 === exports.CallInterface3(ctx, null, 0)) throw new Error('CallInterface3 failed');
    if (-1 === exports.CallInterface11(ctx, null, 0)) throw new Error('CallInterface11 failed');
    if (-1 === exports.CallInterface8(ctx, pudPtr, pudLen)) throw new Error('CallInterface8 failed');
    if (-1 === exports.CallInterface2(ctx, cidPtr, cidLen)) throw new Error('CallInterface2 failed');
    if (-1 === exports.CallInterface14(ctx, factorPtr, factorLen, midPtr, 128)) throw new Error('CallInterface14 failed');

    const midValue = UTF8ToString(midPtr);
    const midLen = utf8Len(midValue);
    const midPtr2 = exports.malloc(midLen + 1);
    stringToUTF8(midValue, midPtr2);

    if (-1 === exports.CallInterface7(ctx, midPtr2, midLen)) {
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
    // 空签名必须当场炸掉：`&ddCalcu=&sv=…` 只会在供应商侧变成一次 403，而「哪一步丢了字节」
    // 的归因线索全落在录制进程之外。MID-61 的视图失效形态正是「一路静默到最后产出空串」，
    // 这条断言是它最后一道哨兵——宁可脚本非 0 退出，也不返回半成品地址。
    if (ddCalcu.length === 0) {
        throw new Error('ddCalcu 计算结果为空（疑为内存视图失效或导出错位）');
    }
    // 释放堆内存（free 存在时）
    if (exports.free) {
        for (const ptr of [useridPtr, tsPtr, pidPtr, cidPtr, pudPtr, factorPtr, midPtr, outPtr, midPtr2]) {
            try { exports.free(ptr); } catch (_) { /* 释放失败可忽略 */ }
        }
    }
    // 输出契约（AGENTS.md「migu.js 输出契约为完整签名 URL」）：返回**完整地址**而非仅签名值，
    // spider.get_migu_stream_url 直接使用、不再自行拼接 sv。改这行形态须同步该处。
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
