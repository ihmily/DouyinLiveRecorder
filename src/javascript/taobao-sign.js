function sign(e) {
    function t(e, t) {
        return e << t | e >>> 32 - t
    }
    function o(e, t) {
        var o, n, r, i, a;
        return r = 2147483648 & e,
        i = 2147483648 & t,
        a = (1073741823 & e) + (1073741823 & t),
        (o = 1073741824 & e) & (n = 1073741824 & t) ? 2147483648 ^ a ^ r ^ i : o | n ? 1073741824 & a ? 3221225472 ^ a ^ r ^ i : 1073741824 ^ a ^ r ^ i : a ^ r ^ i
    }
    function n(e, n, r, i, a, s, u) {
        return o(t(e = o(e, o(o(function(e, t, o) {
            return e & t | ~e & o
        }(n, r, i), a), u)), s), n)
    }
    function r(e, n, r, i, a, s, u) {
        return o(t(e = o(e, o(o(function(e, t, o) {
            return e & o | t & ~o
        }(n, r, i), a), u)), s), n)
    }
    function i(e, n, r, i, a, s, u) {
        return o(t(e = o(e, o(o(function(e, t, o) {
            return e ^ t ^ o
        }(n, r, i), a), u)), s), n)
    }
    function a(e, n, r, i, a, s, u) {
        return o(t(e = o(e, o(o(function(e, t, o) {
            return t ^ (e | ~o)
        }(n, r, i), a), u)), s), n)
    }
    function s(e) {
        var t, o = "", n = "";
        for (t = 0; 3 >= t; t++)
            o += (n = "0" + (e >>> 8 * t & 255).toString(16)).substr(n.length - 2, 2);
        return o
    }
    var u, l, d, c, p, f, h, m, y, g;
    for (g = function(e) {
        for (var t = e.length, o = t + 8, n = 16 * ((o - o % 64) / 64 + 1), r = Array(n - 1), i = 0, a = 0; t > a; )
            i = a % 4 * 8,
            r[(a - a % 4) / 4] |= e.charCodeAt(a) << i,
            a++;
        return i = a % 4 * 8,
        r[(a - a % 4) / 4] |= 128 << i,
        r[n - 2] = t << 3,
        r[n - 1] = t >>> 29,
        r
    }(e = function(e) {
        var t = String.fromCharCode;
        e = e.replace(/\r\n/g, "\n");
        for (var o, n = "", r = 0; r < e.length; r++)
            128 > (o = e.charCodeAt(r)) ? n += t(o) : o > 127 && 2048 > o ? (n += t(o >> 6 | 192),
            n += t(63 & o | 128)) : (n += t(o >> 12 | 224),
            n += t(o >> 6 & 63 | 128),
            n += t(63 & o | 128));
        return n
    }(e)),
    f = 1732584193,
    h = 4023233417,
    m = 2562383102,
    y = 271733878,
    u = 0; u < g.length; u += 16)
        l = f,
        d = h,
        c = m,
        p = y,
        h = a(h = a(h = a(h = a(h = i(h = i(h = i(h = i(h = r(h = r(h = r(h = r(h = n(h = n(h = n(h = n(h, m = n(m, y = n(y, f = n(f, h, m, y, g[u + 0], 7, 3614090360), h, m, g[u + 1], 12, 3905402710), f, h, g[u + 2], 17, 606105819), y, f, g[u + 3], 22, 3250441966), m = n(m, y = n(y, f = n(f, h, m, y, g[u + 4], 7, 4118548399), h, m, g[u + 5], 12, 1200080426), f, h, g[u + 6], 17, 2821735955), y, f, g[u + 7], 22, 4249261313), m = n(m, y = n(y, f = n(f, h, m, y, g[u + 8], 7, 1770035416), h, m, g[u + 9], 12, 2336552879), f, h, g[u + 10], 17, 4294925233), y, f, g[u + 11], 22, 2304563134), m = n(m, y = n(y, f = n(f, h, m, y, g[u + 12], 7, 1804603682), h, m, g[u + 13], 12, 4254626195), f, h, g[u + 14], 17, 2792965006), y, f, g[u + 15], 22, 1236535329), m = r(m, y = r(y, f = r(f, h, m, y, g[u + 1], 5, 4129170786), h, m, g[u + 6], 9, 3225465664), f, h, g[u + 11], 14, 643717713), y, f, g[u + 0], 20, 3921069994), m = r(m, y = r(y, f = r(f, h, m, y, g[u + 5], 5, 3593408605), h, m, g[u + 10], 9, 38016083), f, h, g[u + 15], 14, 3634488961), y, f, g[u + 4], 20, 3889429448), m = r(m, y = r(y, f = r(f, h, m, y, g[u + 9], 5, 568446438), h, m, g[u + 14], 9, 3275163606), f, h, g[u + 3], 14, 4107603335), y, f, g[u + 8], 20, 1163531501), m = r(m, y = r(y, f = r(f, h, m, y, g[u + 13], 5, 2850285829), h, m, g[u + 2], 9, 4243563512), f, h, g[u + 7], 14, 1735328473), y, f, g[u + 12], 20, 2368359562), m = i(m, y = i(y, f = i(f, h, m, y, g[u + 5], 4, 4294588738), h, m, g[u + 8], 11, 2272392833), f, h, g[u + 11], 16, 1839030562), y, f, g[u + 14], 23, 4259657740), m = i(m, y = i(y, f = i(f, h, m, y, g[u + 1], 4, 2763975236), h, m, g[u + 4], 11, 1272893353), f, h, g[u + 7], 16, 4139469664), y, f, g[u + 10], 23, 3200236656), m = i(m, y = i(y, f = i(f, h, m, y, g[u + 13], 4, 681279174), h, m, g[u + 0], 11, 3936430074), f, h, g[u + 3], 16, 3572445317), y, f, g[u + 6], 23, 76029189), m = i(m, y = i(y, f = i(f, h, m, y, g[u + 9], 4, 3654602809), h, m, g[u + 12], 11, 3873151461), f, h, g[u + 15], 16, 530742520), y, f, g[u + 2], 23, 3299628645), m = a(m, y = a(y, f = a(f, h, m, y, g[u + 0], 6, 4096336452), h, m, g[u + 7], 10, 1126891415), f, h, g[u + 14], 15, 2878612391), y, f, g[u + 5], 21, 4237533241), m = a(m, y = a(y, f = a(f, h, m, y, g[u + 12], 6, 1700485571), h, m, g[u + 3], 10, 2399980690), f, h, g[u + 10], 15, 4293915773), y, f, g[u + 1], 21, 2240044497), m = a(m, y = a(y, f = a(f, h, m, y, g[u + 8], 6, 1873313359), h, m, g[u + 15], 10, 4264355552), f, h, g[u + 6], 15, 2734768916), y, f, g[u + 13], 21, 1309151649), m = a(m, y = a(y, f = a(f, h, m, y, g[u + 4], 6, 4149444226), h, m, g[u + 11], 10, 3174756917), f, h, g[u + 2], 15, 718787259), y, f, g[u + 9], 21, 3951481745),
        f = o(f, l),
        h = o(h, d),
        m = o(m, c),
        y = o(y, p);
    return (s(f) + s(h) + s(m) + s(y)).toLowerCase()
}

// 正确sign值：05748e8359cd3e6deaab02d15caafc11
// var sg =sign('5655b7041ca049730330701082886efd&1719411639403&12574478&{"componentKey":"wp_pc_shop_basic_info","params":"{\\"memberId\\":\\"b2b-22133374292418351a\\"}"}')
// console.log(sg)