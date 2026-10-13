/**
 * Function to get the ddCalcu parameter value
 * @param {string} inputUrl - The original URL before encryption
 * @returns {Promise<string>} - Returns the calculated ddCalcu value
 */
async function getDdCalcu(inputUrl) {
    let wasmInstance = null;
    let memory_p = null; // Uint8Array view
    let memory_h = null; // Uint32Array view

    // Fixed parameter
    const f = 'PBTxuWiTEbUPPFcpyxs0ww==';

    // Utility function: Convert string to UTF-8 in memory
    function stringToUTF8(string, offset) {
        const encoder = new TextEncoder();
        const encoded = encoder.encode(string);
        for (let i = 0; i < encoded.length; i++) {
            memory_p[offset + i] = encoded[i];
        }
        memory_p[offset + encoded.length] = 0; // Null-terminate
    }

    // Utility function: Read UTF-8 string from memory address
    function UTF8ToString(offset) {
        let s = '';
        let i = 0;
        while (memory_p[offset + i]) {
            s += String.fromCharCode(memory_p[offset + i]);
            i++;
        }
        return s;
    }

    // WASM import function stubs
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

    // Step 1: Retrieve playerVersion
    const settingsResp = await fetch('https://app-sc.miguvideo.com/common/v1/settings/H5_DetailPage');
    const settingsData = await settingsResp.json();
    const playerVersion = JSON.parse(settingsData.body.paramValue).playerVersion;

    // Step 2: Load WASM module
    const wasmUrl = `https://www.miguvideo.com/mgs/player/prd/${playerVersion}/dist/mgprtcl.wasm`;
    const wasmResp = await fetch(wasmUrl);
    if (!wasmResp.ok) throw new Error("Failed to download WASM");
    const wasmBuffer = await wasmResp.arrayBuffer();

    const importObject = {
        a: { a, b, c }
    };

    const { instance } = await WebAssembly.instantiate(wasmBuffer, importObject);
    wasmInstance = instance;

    const memory = wasmInstance.exports.d;
    memory_p = new Uint8Array(memory.buffer);
    memory_h = new Uint32Array(memory.buffer);

    const exports = {
        CallInterface1: wasmInstance.exports.h,
        CallInterface2: wasmInstance.exports.i,
        CallInterface3: wasmInstance.exports.j,
        CallInterface4: wasmInstance.exports.k,
        CallInterface6: wasmInstance.exports.m,
        CallInterface7: wasmInstance.exports.n,
        CallInterface8: wasmInstance.exports.o,
        CallInterface9: wasmInstance.exports.p,
        CallInterface10: wasmInstance.exports.q,
        CallInterface11: wasmInstance.exports.r,
        CallInterface14: wasmInstance.exports.t,
        malloc: wasmInstance.exports.u,
    };

    const parsedUrl = new URL(inputUrl);
    const query = Object.fromEntries(parsedUrl.searchParams);

    const o = query.userid || '';
    const a_val = query.timestamp || '';
    const s = query.ProgramID || '';
    const u = query.Channel_ID || '';
    const v = query.puData || '';

    // Allocate memory
    const d = exports.malloc(o.length + 1);
    const h = exports.malloc(a_val.length + 1);
    const y = exports.malloc(s.length + 1);
    const m = exports.malloc(u.length + 1);
    const g = exports.malloc(v.length + 1);
    const b_val = exports.malloc(f.length + 1);
    const E = exports.malloc(128);
    const T = exports.malloc(128);

    // Write data to memory
    stringToUTF8(o, d);
    stringToUTF8(a_val, h);
    stringToUTF8(s, y);
    stringToUTF8(u, m);
    stringToUTF8(v, g);
    stringToUTF8(f, b_val);

    // Call interface functions
    const S = exports.CallInterface6(); // Create context
    exports.CallInterface1(S, y, s.length);
    exports.CallInterface10(S, h, a_val.length);
    exports.CallInterface9(S, d, o.length);
    exports.CallInterface3(S, 0, 0);
    exports.CallInterface11(S, 0, 0);
    exports.CallInterface8(S, g, v.length);
    exports.CallInterface2(S, m, u.length);
    exports.CallInterface14(S, b_val, f.length, T, 128);

    const w = UTF8ToString(T);
    const I = exports.malloc(w.length + 1);
    stringToUTF8(w, I);

    exports.CallInterface7(S, I, w.length);
    exports.CallInterface4(S, E, 128);

    return UTF8ToString(E);
}

const url = process.argv[2];

getDdCalcu(url).then(result => {
    console.log(result);
}).catch(err => {
    console.error(err);
    process.exit(1);
});