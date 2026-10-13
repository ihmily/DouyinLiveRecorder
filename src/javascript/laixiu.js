
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function calculateSign() {
    const a = new Date().getTime();
    const s = generateUUID().replace(/-/g, "");
    const u = 'kk792f28d6ff1f34ec702c08626d454b39pro';

    const input = "web" + s + a + u;

    const hash = CryptoJS.MD5(input).toString();

    return {
        timestamp: a,
        imei: s,
        requestId: hash,
        inputString: input
    };
}

function sign(cryptoJSPath) {
    CryptoJS = require(cryptoJSPath);
    return calculateSign();
}

module.exports = {
    sign
  };