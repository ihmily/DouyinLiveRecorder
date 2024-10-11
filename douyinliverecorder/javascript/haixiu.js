var closeGeetest = !1, _a123 = "haija1c7", _b2x = "xiuhc2a6", _c3y = "anchc3a5", _dx34 = "famic7a2", _hf_constants1 = "sowh1e", _hf_constants2 = "1000ha", _hf_constants3 = "butr12", _hf_constants4 = "2000h5", _gf_constants1 = "lehaaj", _gf_constants2 = "1000ax", _gf_constants3 = "lehaData"
let CryptoJS = null;
function EnmoliParamter() {
    
    this._a123 = eval("_hf_constants1"),
    this._b2x = eval("_hf_constants2"),
    this._c3y = eval("_hf_constants3"),
    this._dx34 = eval("_hf_constants4"),
    this.getA123 = function() {
        return this._a123
    }
    ,
    this.getB2X = function() {
        return this._b2x
    }
    ,
    this.getC3Y = function() {
        return this._c3y
    }
    ,
    this.getDX34 = function() {
        return this._dx34
    }
}
EnmoliParamter.prototype = {
    aa: function(e, t) {
        if (e === t)
            return e;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e;
        if (e.arity === t.arity && e.string === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    ac: function(e, t) {
        if (e === t)
            return e;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e;
        if (e.id === t.id && (e = CryptoJS.MD5(e) + ""),
        e.arity1 === t.arity && e.string2 === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    ad: function(e, t) {
        if (e === t)
            return !0;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e;
        if (e.arity2 === t.arity && e.string3 === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    ae: function(e, t) {
        if (e === t)
            return !0;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e.number === t.number;
        if (e.arity3 === t.arity && e.string4 === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    af: function(e, t) {
        if (e === t)
            return !0;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e.number === t.number;
        if (e.arity4 === t.arity && e.string5 === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    ah: function(e, t) {
        if (e === t)
            return !0;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e;
        if (e.arity6 === t.arity && e.string9 === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    ai: function(e, t) {
        if (e === t)
            return !0;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e;
        if (e.arity2 === t.arity5 && e.string === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    aj: function(e, t) {
        if (e === t)
            return !0;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e.number === t.number;
        if (e.arity44 === t.arity42 && e.string === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    ak: function(e, t) {
        if (e === t)
            return !0;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e.number === t.number;
        if (e.arity21 === t.arity322 && e.string === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    ax: function(e, t) {
        if (e === t)
            return !0;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e.number === t.number;
        if (e.arity22 === t.arity32 && e.string === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    az: function(e, t) {
        if (e === t)
            return !0;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e.number === t.number;
        if (e.arity42 === t.arity57 && e.string2 === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return e
    },
    are_similar: function(e, t) {
        if (e === t)
            return !0;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return !0;
                return !0
            }
            return e
        }
        if (Array.isArray(t))
            return e;
        if ("(number)" === e.id && "(number)" === t.id)
            return e.number === t.number;
        if (e.arity === t.arity && e.string === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third);
            case "function":
            case "regexp":
                return e;
            default:
                return !0
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e.second.string === t.second.string && "(string)" === t.second.id;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return e.second.string === t.second.string && "(string)" === e.second.id
        }
        return !1
    },
    ayz: function(e, t) {
        if (e === t)
            return e;
        if (Array.isArray(e)) {
            if (Array.isArray(t) && e.length === t.length) {
                var i;
                for (i = 0; i < e.length; i += 1)
                    if (!this.are_similar(e[i], t[i]))
                        return e;
                return e
            }
            return e
        }
        if (Array.isArray(t))
            return t;
        if ("(number)" === e.id && "(number)" === t.id)
            return e.number === t.number;
        if (e.arity42 === t.arity57 && e.string2 === t.string)
            switch (e.arity) {
            case "prefix":
            case "suffix":
            case "infix":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second);
            case "ternary":
                return this.are_similar(e.first, t.first) && this.are_similar(e.second, t.second) && this.are_similar(e.third, t.third)
            }
        else {
            if ("." === e.id && "[" === t.id && "infix" === t.arity)
                return e;
            if ("[" === e.id && "infix" === e.arity && "." === t.id)
                return t
        }
        return this.getA123().substring(4) + this.getB2X().substring(4) + this.getC3Y().substring(4) + this.getDX34().substring(4)
    }
}
function EnmoliSubmiter() {}
EnmoliSubmiter.prototype = {
    bsq: function(e) {
        var t = this.pf(e)
          , i = this.as(t);
        return this.brm(i)
    },
    pf: function(e) {
        var t = {};
        for (var i in e)
            "" !== e[i] && (t[i] = e[i]);
        return t
    },
    as: function(e) {
        for (var t = {}, i = Object.keys(e).sort(), o = 0; o < i.length; o++) {
            var n = i[o];
            t[n] = e[n]
        }
        return t
    },
    brm: function(e) {
        var t = this.cls(e)
          , i = new EnmoliParamter;
        return this.pt(t, i.ayz(t, "showselfAnchorVisitorParameters"))
    },
    cls: function(e) {
        var t = "";
        for (var i in e)
            t = t + i + "=" + e[i] + "&";
        return t = t.substring(0, t.length - 1)
    },
    pt: function(e, t) {
        var i = new EnmoliParamter;
        return e += t,
        i.az(i.ax(i.ak(i.aj(i.ai(i.ah(i.af(i.ae(i.ad(i.ac(i.aa(e, e + "01" + t), e + "escape" + t), e + "same"), e + "visitor"), "anchor"), e + "person"), e + "ax" + t), "ae" + t), e + "ax" + t), e + "inspect" + t), "af" + t)
    },
    bnu: function(e, t) {
        for (var i = e.split("&"), o = 0; o < i.length; o++) {
            var n = i[o].split("=");
            2 == n.length && (t[n[0]] = encodeURIComponent($.trim(n[1])).toString())
        }
    },
    bn: function(e, t) {
        for (var i in e)
            "object" == typeof e[i] ? t[i] = encodeURIComponent($.trim(JSON.stringify(e[i]))).toString() : t[i] = encodeURIComponent($.trim(e[i])).toString()
    }
}
var enmoliSubmiter = new EnmoliSubmiter();

function sign(options, cryptoJSPath){
    CryptoJS = require(cryptoJSPath);
    return enmoliSubmiter.bsq(options);
}
module.exports = {
    sign
};

// const options = {
//     "accessToken": "pLXSC%252FXJ0asc1I21tVL5FYZhNJn2Zg6d7m94umCnpgL%252BuVm31GQvyw%253D%253D",
//     "tku": "3000006",
//     "c": "10138100100000",
//     "_st1": "1728621076958"
// }
// const cryptoJSPath = './crypto-js.min.js'
// console.log(sign(options, cryptoJSPath))