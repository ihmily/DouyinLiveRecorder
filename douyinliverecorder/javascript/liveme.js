/**
 * @author Hmily
 * @createTime 2024-10-10
 */

const id = 1;
const r = `${new Date().getTime()}${id}`
const Am = "LM6000101139961122666757";
const rl = "undefined"

function createRandom(length = 32) {
    let result = "";
    const characters = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678";
    for (let i = 0; i < length; ++i) {
        const randomIndex = Math.floor(Math.random() * characters.length);
        result += characters.charAt(randomIndex);
    }
    return result;
}

function createSignature(input = "4l4m5") {
    let signature = "";
    let number = 0;
    for (let i = 0; i < input.length; ++i) {
        const charCode = input.charCodeAt(i);
        if (charCode >= 48 && charCode <= 57) {
            number = number * 10 + (charCode - 48);
        } else {
            if (number !== 0) {
                signature += createRandom(number);
                number = 0;
            }
            signature += String.fromCharCode(charCode);
        }
    }
    if (number !== 0) {
        signature += createRandom(number);
    }
    return signature;
}

function oC(e) {
    return e && e.__esModule && Object.prototype.hasOwnProperty.call(e, "default") ? e.default : e
}
var Tm = {
    exports: {}
}
  , Sm = {
    exports: {}
};
(function() {
    var e = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
      , t = {
        rotl: function(n, r) {
            return n << r | n >>> 32 - r
        },
        rotr: function(n, r) {
            return n << 32 - r | n >>> r
        },
        endian: function(n) {
            if (n.constructor == Number)
                return t.rotl(n, 8) & 16711935 | t.rotl(n, 24) & 4278255360;
            for (var r = 0; r < n.length; r++)
                n[r] = t.endian(n[r]);
            return n
        },
        randomBytes: function(n) {
            for (var r = []; n > 0; n--)
                r.push(Math.floor(Math.random() * 256));
            return r
        },
        bytesToWords: function(n) {
            for (var r = [], s = 0, o = 0; s < n.length; s++,
            o += 8)
                r[o >>> 5] |= n[s] << 24 - o % 32;
            return r
        },
        wordsToBytes: function(n) {
            for (var r = [], s = 0; s < n.length * 32; s += 8)
                r.push(n[s >>> 5] >>> 24 - s % 32 & 255);
            return r
        },
        bytesToHex: function(n) {
            for (var r = [], s = 0; s < n.length; s++)
                r.push((n[s] >>> 4).toString(16)),
                r.push((n[s] & 15).toString(16));
            return r.join("")
        },
        hexToBytes: function(n) {
            for (var r = [], s = 0; s < n.length; s += 2)
                r.push(parseInt(n.substr(s, 2), 16));
            return r
        },
        bytesToBase64: function(n) {
            for (var r = [], s = 0; s < n.length; s += 3)
                for (var o = n[s] << 16 | n[s + 1] << 8 | n[s + 2], i = 0; i < 4; i++)
                    s * 8 + i * 6 <= n.length * 8 ? r.push(e.charAt(o >>> 6 * (3 - i) & 63)) : r.push("=");
            return r.join("")
        },
        base64ToBytes: function(n) {
            n = n.replace(/[^A-Z0-9+\/]/ig, "");
            for (var r = [], s = 0, o = 0; s < n.length; o = ++s % 4)
                o != 0 && r.push((e.indexOf(n.charAt(s - 1)) & Math.pow(2, -2 * o + 8) - 1) << o * 2 | e.indexOf(n.charAt(s)) >>> 6 - o * 2);
            return r
        }
    };
    Sm.exports = t
}
)();
var iC = Sm.exports
  , nl = {
    utf8: {
        stringToBytes: function(e) {
            return nl.bin.stringToBytes(unescape(encodeURIComponent(e)))
        },
        bytesToString: function(e) {
            return decodeURIComponent(escape(nl.bin.bytesToString(e)))
        }
    },
    bin: {
        stringToBytes: function(e) {
            for (var t = [], n = 0; n < e.length; n++)
                t.push(e.charCodeAt(n) & 255);
            return t
        },
        bytesToString: function(e) {
            for (var t = [], n = 0; n < e.length; n++)
                t.push(String.fromCharCode(e[n]));
            return t.join("")
        }
    }
}, sd = nl;

var aC = function(e) {
    return e != null && (Cm(e) || lC(e) || !!e._isBuffer)
};
function Cm(e) {
    return !!e.constructor && typeof e.constructor.isBuffer == "function" && e.constructor.isBuffer(e)
}
function lC(e) {
    return typeof e.readFloatLE == "function" && typeof e.slice == "function" && Cm(e.slice(0, 0))
}
(function() {
    var e = iC
      , t = sd.utf8
      , n = aC
      , r = sd.bin
      , s = function(o, i) {
        o.constructor == String ? i && i.encoding === "binary" ? o = r.stringToBytes(o) : o = t.stringToBytes(o) : n(o) ? o = Array.prototype.slice.call(o, 0) : !Array.isArray(o) && o.constructor !== Uint8Array && (o = o.toString());
        for (var a = e.bytesToWords(o), l = o.length * 8, c = 1732584193, u = -271733879, f = -1732584194, d = 271733878, m = 0; m < a.length; m++)
            a[m] = (a[m] << 8 | a[m] >>> 24) & 16711935 | (a[m] << 24 | a[m] >>> 8) & 4278255360;
        a[l >>> 5] |= 128 << l % 32,
        a[(l + 64 >>> 9 << 4) + 14] = l;
        for (var v = s._ff, w = s._gg, R = s._hh, y = s._ii, m = 0; m < a.length; m += 16) {
            var b = c
              , _ = u
              , g = f
              , C = d;
            c = v(c, u, f, d, a[m + 0], 7, -680876936),
            d = v(d, c, u, f, a[m + 1], 12, -389564586),
            f = v(f, d, c, u, a[m + 2], 17, 606105819),
            u = v(u, f, d, c, a[m + 3], 22, -1044525330),
            c = v(c, u, f, d, a[m + 4], 7, -176418897),
            d = v(d, c, u, f, a[m + 5], 12, 1200080426),
            f = v(f, d, c, u, a[m + 6], 17, -1473231341),
            u = v(u, f, d, c, a[m + 7], 22, -45705983),
            c = v(c, u, f, d, a[m + 8], 7, 1770035416),
            d = v(d, c, u, f, a[m + 9], 12, -1958414417),
            f = v(f, d, c, u, a[m + 10], 17, -42063),
            u = v(u, f, d, c, a[m + 11], 22, -1990404162),
            c = v(c, u, f, d, a[m + 12], 7, 1804603682),
            d = v(d, c, u, f, a[m + 13], 12, -40341101),
            f = v(f, d, c, u, a[m + 14], 17, -1502002290),
            u = v(u, f, d, c, a[m + 15], 22, 1236535329),
            c = w(c, u, f, d, a[m + 1], 5, -165796510),
            d = w(d, c, u, f, a[m + 6], 9, -1069501632),
            f = w(f, d, c, u, a[m + 11], 14, 643717713),
            u = w(u, f, d, c, a[m + 0], 20, -373897302),
            c = w(c, u, f, d, a[m + 5], 5, -701558691),
            d = w(d, c, u, f, a[m + 10], 9, 38016083),
            f = w(f, d, c, u, a[m + 15], 14, -660478335),
            u = w(u, f, d, c, a[m + 4], 20, -405537848),
            c = w(c, u, f, d, a[m + 9], 5, 568446438),
            d = w(d, c, u, f, a[m + 14], 9, -1019803690),
            f = w(f, d, c, u, a[m + 3], 14, -187363961),
            u = w(u, f, d, c, a[m + 8], 20, 1163531501),
            c = w(c, u, f, d, a[m + 13], 5, -1444681467),
            d = w(d, c, u, f, a[m + 2], 9, -51403784),
            f = w(f, d, c, u, a[m + 7], 14, 1735328473),
            u = w(u, f, d, c, a[m + 12], 20, -1926607734),
            c = R(c, u, f, d, a[m + 5], 4, -378558),
            d = R(d, c, u, f, a[m + 8], 11, -2022574463),
            f = R(f, d, c, u, a[m + 11], 16, 1839030562),
            u = R(u, f, d, c, a[m + 14], 23, -35309556),
            c = R(c, u, f, d, a[m + 1], 4, -1530992060),
            d = R(d, c, u, f, a[m + 4], 11, 1272893353),
            f = R(f, d, c, u, a[m + 7], 16, -155497632),
            u = R(u, f, d, c, a[m + 10], 23, -1094730640),
            c = R(c, u, f, d, a[m + 13], 4, 681279174),
            d = R(d, c, u, f, a[m + 0], 11, -358537222),
            f = R(f, d, c, u, a[m + 3], 16, -722521979),
            u = R(u, f, d, c, a[m + 6], 23, 76029189),
            c = R(c, u, f, d, a[m + 9], 4, -640364487),
            d = R(d, c, u, f, a[m + 12], 11, -421815835),
            f = R(f, d, c, u, a[m + 15], 16, 530742520),
            u = R(u, f, d, c, a[m + 2], 23, -995338651),
            c = y(c, u, f, d, a[m + 0], 6, -198630844),
            d = y(d, c, u, f, a[m + 7], 10, 1126891415),
            f = y(f, d, c, u, a[m + 14], 15, -1416354905),
            u = y(u, f, d, c, a[m + 5], 21, -57434055),
            c = y(c, u, f, d, a[m + 12], 6, 1700485571),
            d = y(d, c, u, f, a[m + 3], 10, -1894986606),
            f = y(f, d, c, u, a[m + 10], 15, -1051523),
            u = y(u, f, d, c, a[m + 1], 21, -2054922799),
            c = y(c, u, f, d, a[m + 8], 6, 1873313359),
            d = y(d, c, u, f, a[m + 15], 10, -30611744),
            f = y(f, d, c, u, a[m + 6], 15, -1560198380),
            u = y(u, f, d, c, a[m + 13], 21, 1309151649),
            c = y(c, u, f, d, a[m + 4], 6, -145523070),
            d = y(d, c, u, f, a[m + 11], 10, -1120210379),
            f = y(f, d, c, u, a[m + 2], 15, 718787259),
            u = y(u, f, d, c, a[m + 9], 21, -343485551),
            c = c + b >>> 0,
            u = u + _ >>> 0,
            f = f + g >>> 0,
            d = d + C >>> 0
        }
        return e.endian([c, u, f, d])
    };
    s._ff = function(o, i, a, l, c, u, f) {
        var d = o + (i & a | ~i & l) + (c >>> 0) + f;
        return (d << u | d >>> 32 - u) + i
    }
    ,
    s._gg = function(o, i, a, l, c, u, f) {
        var d = o + (i & l | a & ~l) + (c >>> 0) + f;
        return (d << u | d >>> 32 - u) + i
    }
    ,
    s._hh = function(o, i, a, l, c, u, f) {
        var d = o + (i ^ a ^ l) + (c >>> 0) + f;
        return (d << u | d >>> 32 - u) + i
    }
    ,
    s._ii = function(o, i, a, l, c, u, f) {
        var d = o + (a ^ (i | ~l)) + (c >>> 0) + f;
        return (d << u | d >>> 32 - u) + i
    }
    ,
    s._blocksize = 16,
    s._digestsize = 16,
    Tm.exports = function(o, i) {
        if (o == null)
            throw new Error("Illegal argument " + o);
        var a = e.wordsToBytes(s(o, i));
        return i && i.asBytes ? a : i && i.asString ? r.bytesToString(a) : e.bytesToHex(a)
    }
}
)();
var cC = Tm.exports;
var t = {
    utf8: {
        stringToBytes: function(e) {
            return nl.bin.stringToBytes(unescape(encodeURIComponent(e)))
        },
        bytesToString: function(e) {
            return decodeURIComponent(escape(nl.bin.bytesToString(e)))
        }
    },
    bin: {
        stringToBytes: function(e) {
            for (var t = [], n = 0; n < e.length; n++)
                t.push(e.charCodeAt(n) & 255);
            return t
        },
        bytesToString: function(e) {
            for (var t = [], n = 0; n < e.length; n++)
                t.push(String.fromCharCode(e[n]));
            return t.join("")
        }
    }
};

const hC = (e, t, n=!1) => {
    if (t.params) {
        const o = {};
        Object.keys(t.params).forEach(i => {
            t.params[i] !== void 0 && t.params[i] !== null && (o[i] = t.params[i])
        }
        ),
        t.params = o
    }
    let r = {};
    const s = t.method.toLowerCase();
    if (s === "get")
        t.params = Object.assign({}, e, t.params || {});
    else if (s === "post")
        if (typeof t.data == "string") {
            let o;
            t.data.split("&").forEach(i => {
                o = i.split("="),
                r[o[0]] = o[1]
            }
            ),
            r = Object.assign({}, e, r),
            t.data = Object.keys(r).map(i => `${i}=${r[i]}`).join("&")
        } else
            r = Object.assign(r, e, t.data || {}),
            t.data = r;
    return n ? t : (r = Object.assign({}, t.params, r),
    r)
}

const Rm = oC(cC);
const s = Rm(r);

pC = e => {
    let t = Object.keys(e).sort().map(n => {
        function r(s) {
            return Array.isArray(s) ? s.join(",") : typeof s === "object" ? JSON.stringify(s) : s
        }
        return n + r(e[n])
    }
    ).join("");
    return t += Am + e.lm_s_ts + rl,
    Rm(t)
}


// final encryption function
let CryptoJS = null;
lm_s_key = atob('ZGQ0NmRiYjQ0MmI2ZTRiYTgxN2Q2MzQ3ZDJkZGY0OTM=');
function requestSign(signParams, cryptoJSPath) {
  let sKey = Object.keys(signParams).sort().map(key => {
    function getValue(val) {
      if (Array.isArray(val)) {
        return val.join(',');
      }
      if (typeof val === 'object') {
        return JSON.stringify(val);
      }
      return val;
    }
    return key + getValue(signParams[key]);
  }).join('');

  sKey += signParams.lm_s_id + signParams.lm_s_ts + lm_s_key;
  console.log(`sKey: ${sKey}`);
  CryptoJS = require(cryptoJSPath);
  return CryptoJS.MD5(sKey).toString();
}

function sign(videoid, cryptoJSPath, platform='web'){
    const vali = createSignature();
    const data_e = {
        lm_s_id: Am,
        lm_s_ts: r,
        lm_s_str: s,
        lm_s_ver: 1,
        h5: 1
    };
    /* data_e example value
    const data_e = {
        lm_s_id: Am,
        lm_s_ts: "17284909009151",
        lm_s_str: "88f9777231dc2d6ac462a1d7ebf5f54e",
        lm_s_ver: 1,
        h5: 1
    };
    */
    console.log("data_e:",data_e);

    data_i = {
        ...data_e,
        _time: new Date().valueOf(),
        thirdchannel: 6,
        videoid: videoid,
        area: 'zh',
        vali: vali
      }
    console.log("data_i:",data_i);
    
    // fake lm_s_sign param value
    let lm_s_sign = pC(data_i);
    console.log(`fake lm_s_sign: ${lm_s_sign}`);

    //finnal request params
    /* 
    signParams = {
    "alias": "liveme",
    "tongdun_black_box": "iWPU21728483558afruvSVo6x0",
    "os": "android",
    "lm_s_id": "LM6000101139961122666757",
    "lm_s_ts": "17284909009151",
    "lm_s_str": "88f9777231dc2d6ac462a1d7ebf5f54e",
    "lm_s_ver": 1,
    "h5": 1,
    "_time": 1728490664651,
    "thirdchannel": 6,
    "videoid": "17284844223282059697",
    "area": "zh",
    "vali": "zH8SlBwnCm4AZWp"
    }# 
    //result: 4eaf71a1ec19b49b7267e4d16e007105
    */
    signParams = {
        "alias": "liveme",
        "tongdun_black_box": "",
        "os": platform,
        ...data_i
    }
    console.log("signParams: ", signParams);
    lm_s_sign = requestSign(signParams, cryptoJSPath);
    console.log(`\x1b[32mfinal lm_s_sign: \x1b[0m${lm_s_sign}\n`);
    data = {
        ...signParams,
        lm_s_sign
    }
    return data;

}

module.exports = {
    sign
  };
