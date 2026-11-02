// DouyinLiveRecorder Web 管理面板前端逻辑：把 UI 绑定到 src/web_api.py 暴露的 REST API，
// 覆盖仪表盘（状态/日志轮询）、弹幕监控（增量游标轮询）、直播间、配置、文件五块。
//
// 【结构】整体包在 IIFE 内，状态与函数封闭在私有作用域，只把 window.toggleRoom / deleteRoom /
// loadFiles / downloadFile 暴露给内联调用与事件委托（表格行由 innerHTML 拼接，一律走委托，
// 不在重渲染时重新解析内联 onclick）。状态是一组模块级闭包变量（sse*/dm* 轮询、configBackup
// 配置快照供 diff、toastTimer），不引入框架或状态机。
//
// 【与后端交互】统一经 api()：自动带 Bearer Token、JSON 序列化、401 跳登录、按 content-type
// 返回 JSON 或纯文本；二进制下载绕过 api()（它返回 text 会破坏 blob）直接 fetch + blob。
// 轮询全部是 setTimeout 递归（非真 SSE/WebSocket），每轮结束且未被停止才续期；切视图/离屏经
// stop* 停掉，避免多视图并发请求。「停止→立即重启」清不掉在途请求，故三条链的续期与落地一律
// 经 makePollChain() 比对代次（见 10b）：被取代的旧轮次既不续期、也不写回任何链状态。
//
// 【安全不变量】① 所有动态文本（房间名、弹幕、文件名、配置值、日志）进 innerHTML 前一律经 esc()；
// ② 敏感段输入框用 password 类型；③ 掩码凭据三条防线以 saveConfig 头注释为唯一事实源，其中
// 「原样看到 *** 即跳过提交」是**写入侧唯一防线**，删掉它掩码就会被回写、覆盖后端真实凭据。
(function () {
    'use strict';

    var TOKEN_KEY = 'dlr_token';
    var THEME_KEY = 'dlr_theme';
    // PARITY（M-61 前端同批）：节白名单必须与后端 src/web_config.py::SENSITIVE_SECTIONS 同源，
    // 后端增列「推送配置」时此处随之增列——两侧任一侧漏，该节内「键名正则看不见」的
    // 凭据（如 bark_key 一类）就会在面板里渲染成明文 text 框。
    var SENSITIVE_SECTIONS = { 'Cookie': true, '账号密码': true, 'Authorization': true, '推送配置': true };

    // MI-27：token 存取统一走此入口，sessionStorage 优先、不可用时回退内存载体。
    // 回退是必要的：Safari 无痕模式与「禁用站点数据」会把 storage 访问变成抛异常，直接写
    // sessionStorage 会让登录流程整体失败。
    // 回退载体是**仅存内存**（[历史注] 早期为 localStorage，M-84 改定）：bearer token 默认 24h 有效，
    // 落 localStorage 等于明文写盘、跨标签页与浏览器重启存活，
    // 与 Token helpers 处「关标签页即失效」的设计目标相反，且 XSS、恶意扩展、本机任意进程均可读取。
    // 回退本身仍保留（隐私模式下 storage 访问抛异常，不能让整个登录流程失败），只是换了载体；
    // 代价是偏好项（主题/语言）在该场景下随之只对本次会话生效——比「凭据落盘」轻一个量级。
    // tests/frontend 的三个沙箱已补 sessionStorage 替身（走主路径），内存回退分支单独用例外，
    // 那条用例断言的正是「令牌绝不落进 localStorage」。
    var _memoryTokenStore = null;
    var _memoryTokenStoreWarned = false;

    // 与 storage 同形的内存载体（getItem/setItem/removeItem），只作为 _tokenStore 的回退分支存在：
    // 刻意不挂到 window，页面脚本与扩展拿不到它，随本标签页一起消失。
    function _makeMemoryTokenStore() {
        var data = {};
        return {
            getItem: function (key) {
                return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null;
            },
            setItem: function (key, value) { data[key] = String(value); },
            removeItem: function (key) { delete data[key]; },
        };
    }

    function _tokenStore() {
        try {
            if (typeof sessionStorage !== 'undefined' && sessionStorage) return sessionStorage;
        } catch (e) { /* 访问被拒（隐私模式）：走内存回退 */ }
        try {
            if (!_memoryTokenStore) _memoryTokenStore = _makeMemoryTokenStore();
        } catch (e) {
            return null; // 连内存载体都建不出来：保持「无存储可用」原语义，由调用方判空
        }
        // 一次性提示：隐私模式下用户看不到「为什么关掉页面就要重新登录」，这里留一条可报障线索；
        // 只提醒一次，避免每轮轮询重复刷屏。
        if (!_memoryTokenStoreWarned) {
            _memoryTokenStoreWarned = true;
            if (typeof console !== 'undefined' && console.warn) {
                console.warn('[token] 会话存储不可用，登录令牌与界面偏好改为仅存内存（关闭页面即失效，不再落盘）');
            }
        }
        return _memoryTokenStore;
    }

    // MID-2238：initTheme() 是 DOMContentLoaded 回调的第一条语句，裸 storage 访问一旦抛异常，
    // 后面的 initLanguage、tab 绑定、登录/登出、事件委托、启动引导一个都不注册——面板退化成静态页
    // 且无任何报错。故 theme/lang 一律走这对安全存取口，两个 init 内部各自 try/catch，前一个失败
    // 不带走后续绑定。
    function safeGetItem(key) {
        try {
            var store = _tokenStore();
            return store ? store.getItem(key) : null;
        } catch (e) {
            return null; // 隐私模式下 storage 读取被拒：按「无持久化偏好」处理
        }
    }

    function safeSetItem(key, value) {
        try {
            var store = _tokenStore();
            if (store) store.setItem(key, value);
        } catch (e) { /* 写入被拒（配额/隐私模式）：偏好本次生效、不持久化即可 */ }
    }

    // 敏感项判定走「节白名单 + 键名正则」双重口径（与后端 web_config.is_sensitive_key /
    // _SENSITIVE_KEY_PATTERN 同步，新增配置键时须确认它是否落入正则）：仅靠节名会漏掉「推送配置」节内的
    // tgapi令牌/发件人密码(授权码)/pushplus推送token，以及各平台节内的 popkontv_token 等独立凭据
    // ——它们在 DOM 里会被渲染成明文 text 输入框。
    // 另补两类：端点型键名（钉钉/微信/bark 推送接口链接、ntfy 推送地址、代理地址）与值形态兜底
    // ——「凭据嵌在值里」的键按键名一律漏，而用户会在 text 框里一眼看到完整 webhook / userinfo 账密。
    var SENSITIVE_KEY_RE = /令牌|密码|授权码|token|secret|passwd|password|api[_-]?key|推送接口链接|推送地址|代理地址/i;
    // 例外：expiry/timeout/有效期 类键是数值型运维参数（如 web_token_expiry 秒数），无保密意义。
    var NOT_SECRET_KEY_RE = /expiry|timeout|有效期|过期/i;
    // 值形态检测（与后端 _looks_like_secret_value 同口径）：URL 且带凭据查询串或 userinfo
    var SECRET_VALUE_QUERY_RE = /(access[_-]?token|token|key|secret|pwd|passwd|password|auth)=/i;
    var URL_VALUE_RE = /^[a-z][a-z0-9+.-]*:\/\//i;
    // 后端 read_config_safe 对敏感项回显的掩码值（与 src/web_config.py::SENSITIVE_MASK 同值）。
    // 面板里看到它就知道「真实值存在但被隐藏」，据此区分「用户没动」与「用户改成了空串」。
    var SENSITIVE_MASK = '***';

    function isSensitiveValue(value) {
        if (!value) return false;
        var v = String(value).trim();
        if (!URL_VALUE_RE.test(v)) return false;
        var parts = v.split('/');
        if (parts.length > 2 && parts[2].indexOf('@') >= 0) return true; // http://user:pass@host
        return SECRET_VALUE_QUERY_RE.test(v);
    }

    function isSensitiveField(section, key) {
        // MIN-2237：判定顺序必须与后端 is_sensitive_item 逐字对齐——后端的例外表只在键名分支内部
        // 生效，即「敏感节」优先于例外。反例：[Cookie] 抖音cookie有效期 这类「敏感节 + 含有效期」的键
        // 后端脱敏、前端若先短路例外则渲染成明文 text 框（值仍是掩码，但用户会误读成「这项没被保护」）。
        // [L-07 备案] 「逐字对齐」与现状有两处已知分叉（CODE_REVIEW_2026-10-30 L-07）：
        // ① 前端 isSensitiveValue 多一道 scheme 门（URL_VALUE_RE 要求 ^scheme://，后端值形态判定无此要求）；
        // ② SENSITIVE_SECTIONS[section] 节名判定大小写敏感，后端节匹配大小写不敏感。
        // 两处分叉方向均为「前端更严」，不构成明文渲染面；对齐属后续改造，不在本批展开。
        if (SENSITIVE_SECTIONS[section]) return true;
        if (NOT_SECRET_KEY_RE.test(key)) return false;
        return SENSITIVE_KEY_RE.test(key);
    }

    // M-21：裸 timer 变量由 sseChain 取代——一个 id 记不住两条链，「停止→立即重启」时在途请求落地
    // 会把自己那一条重新排期并顶掉这里的 id，旧链从此失联（控制器见 10b）。
    var sseChain = makePollChain();
    var sseStopped = true;
    // SEV-2227：把「想要轮询」与「轮询已停」拆成两个状态（本文件唯一完整说明，其余各处只引用）。
    // sseWanted 表达用户意图（进仪表盘即 true），sseStopped 只表达「当前有没有在飞的定时器」，
    // 恢复条件为 sseWanted && sseStopped。原实现只有一个 sseStopped：隐藏时置 true、恢复分支却判断
    // 「为假则启」，切走一次标签页后轮询永不恢复，面板数据冻结在切走前那一帧。
    var sseWanted = false;
    var configBackup = null;
    var toastTimer = null;

    // 弹幕监控状态：dmChain/dmStopped 控制轮询，dmLastSeq 为增量游标，dmMessages 为前端保留的近期
    // 消息（最多 DM_MAX_MESSAGES 条），切筛选时全量重绘。
    var dmChain = makePollChain();
    var dmStopped = true;
    var dmLastSeq = 0;
    var dmMessages = [];
    var DM_MAX_MESSAGES = 300;
    // M-19：上一次写进 #danmaku-room-filter 的 option 集合原文（null = 尚未写过）。
    // 只有它变化才重建 innerHTML（判据见 renderDanmaku 的筛选下拉段）。
    var dmRoomFilterOpts = null;

    // M-18：三条**按需**加载链（loadRooms / loadConfig / loadFiles）的代次载体。复用 makePollChain()
    // 的同一判据（落地时证明自己仍是最新一代，否则丢弃），但只用 halt() 顶代次 + isCurrent() 复核：
    // 一次性拉取没有节拍，故既不调 begin() 也不调 renew()（链内 timer 恒为 null）。将来某条改成周期
    // 轮询，同一实例补 begin 即可。
    var roomsChain = makePollChain();
    var configChain = makePollChain();
    var filesChain = makePollChain();

    // 画质选项状态：qualityOptions 为用户已选档位（渲染下拉与 chips），
    // qualityBuiltin 为引擎支持的全部内置档位（渲染「添加画质」候选项）。
    var qualityOptions = [];
    var qualityBuiltin = [];

    // ===== API 接口契约速查（路径/方法/关键参数/返回）=====
    // 所有请求经 api() 自动带 Bearer Token；401 统一清 Token 并跳登录；非 2xx 抛错由调用方 catch。
    // GET  /api/status → 仪表盘快照 {engine_alive, recording_enabled, monitoring, recording_count,
    //      error_count, recent_errors, disk_free_gb, recording:[{name,quality,actual_quality,start_time,duration}]}
    //      可能带 stale:true（超时回退的陈旧快照）；error:"status_unavailable" 表示采样失败（HTTP 仍为
    //      200，不得当成功渲染）。[历史注] 契约里没有 main_loop_alive，该键从未在 main.py 定义、永不下发。
    // POST /api/recording/toggle body{enable:bool} → 切换引擎录制开关，成功即回拉 /api/status 同步按钮
    // GET  /api/logs?lines=100 → {lines:[...]} 纯文本日志行，拼到 #log-stream
    // GET  /api/danmaku?since=<seq> → {rooms:[...], messages:[...], last_seq, truncated}；首次 since=0，
    //      之后用返回 last_seq 续拉避免重复。error:"danmaku_unavailable" = 本次采样失败（仍是 200），
    //      renderDanmaku 保留上一轮表与缓冲、只提示取不到
    // GET/PUT /api/language → {language}；PUT body{language} 热切换（后端控制台/日志同步翻译）
    // POST /api/login body{password} → {token}；失败抛错显示到 #login-error
    // GET  /api/rooms → [{url,quality,name,enabled,recording}]；POST body{url,quality?,name?} 新增、
    //      DELETE ?url= 删除、POST /api/rooms/toggle body{url,enable} 启停
    // PUT  /api/rooms/quality body{url,quality} → 按房间切换画质（quality 空=恢复默认，与桌面端共用画质段）
    // GET/PUT /api/rooms/qualities → {options:[...], builtin:[...]}；PUT body{options:[...]} 回写画质选项
    //      （与桌面端画质切换菜单共用，落地 config.ini [录制设置]）
    // GET  /api/config → {section:{key:value}}；PUT /api/config body{section,key,value} 单键落盘
    // GET  /api/files?path= → [{name,type,path,size?,mtime?}]；下载绕过 api() 直接 blob 流
    function $(id) { return document.getElementById(id); }

    // 1. Token helpers —— MI-27：一律经 _tokenStore() 存取。token 由 localStorage 移到 sessionStorage，
    // 正常浏览器下关闭标签页即失效，配合 /api/logout 吊销服务端 bearer 收窄泄露窗口；仅 sessionStorage
    // 不可用时才回退内存载体（隐私模式的让步，此时「关标签页即失效」并不成立；同样不落盘、
    // 关闭页面即失效。[历史注] 回退载体早期是 localStorage，M-84 改定；存取形状不变，仍按 _tokenStore() 判空）。
    function getToken() {
        var st = _tokenStore();
        return st ? (st.getItem(TOKEN_KEY) || '') : '';
    }
    function setToken(t) {
        var st = _tokenStore();
        if (!st) return;
        if (t) {
            st.setItem(TOKEN_KEY, t);
        } else {
            st.removeItem(TOKEN_KEY);
        }
    }

    // 2. api fetch wrapper
    // WD-10：必须加超时。服务端若在 main.get_status() 里卡住（要与录制主循环抢 record_state_lock），
    // 无 signal 的 await fetch 会无限期 pending，而下一轮 setTimeout 排在 .then() 之后——轮询链就此
    // 停止，界面停在最后一帧且错误被 .catch 吞掉。超时与网络失败统一抛可识别错误，由调用方退避。
    // 2b. 后端错误体解析（MID-39）：非 2xx 的响应体通常是 FastAPI 的 {"detail": "..."}，只取 detail 作为
    // 用户可见消息；识别不出结构时回退本地化的通用文案，**不回显原文**（纯文本/HTML 错误页同样可能带
    // 路径与栈）。诊断线索不丢：状态码与原始响应体挂在 err.status / err.rawBody 上并写一条 console.warn。
    function apiError(status, text, path, fallback) {
        var detail = '';
        try {
            var parsed = JSON.parse(text);
            if (parsed && typeof parsed.detail === 'string') detail = parsed.detail;
        } catch (e) { /* 非 JSON 响应体：只用通用文案，原文仅进控制台 */ }
        var err = new Error(detail || fallback + ' (' + status + ')');
        err.status = status;
        err.rawBody = text;
        if (typeof console !== 'undefined' && console.warn) {
            console.warn('[api] ' + status + ' ' + path + ' -> ' + text);
        }
        return err;
    }

    var API_TIMEOUT_MS = 10000;
    async function api(path, opts) {
        opts = opts || {};
        var headers = Object.assign({}, opts.headers || {});
        var body = opts.body;
        if (body && typeof body === 'object') {
            headers['Content-Type'] = 'application/json';
            body = JSON.stringify(body);
        }
        var token = getToken();
        if (token) {
            headers['Authorization'] = 'Bearer ' + token;
        }
        var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
        var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, API_TIMEOUT_MS) : null;
        var resp;
        try {
            resp = await fetch(path, {
                method: opts.method || 'GET',
                headers: headers,
                body: body,
                signal: ctrl ? ctrl.signal : undefined,
            });
        } catch (e) {
            // 超时与网络失败统一为可识别的错误，交给调用方决定退避
            throw new Error(e && e.name === 'AbortError' ? 'timeout' : String(e));
        } finally {
            if (timer) clearTimeout(timer);
        }
        var text = await resp.text();
        if (resp.status === 401) {
            setToken('');
            showLogin();
            throw apiError(401, text, path, t('common.unauthorized'));
        }
        if (!resp.ok) {
            throw apiError(resp.status, text, path, t('common.requestFailed'));
        }
        var ct = resp.headers.get('content-type') || '';
        if (ct.indexOf('application/json') !== -1) {
            try {
                return JSON.parse(text);
            } catch (e) {
                return text;
            }
        }
        return text;
    }

    // 3. toast
    function toast(msg, type) {
        type = type || 'info';
        var el = $('toast');
        if (!el) return;
        el.textContent = msg;
        el.className = 'toast ' + type;
        el.classList.remove('hidden');
        if (toastTimer) {
            clearTimeout(toastTimer);
        }
        toastTimer = setTimeout(function () {
            el.classList.add('hidden');
        }, 2500);
    }

    // 4. fmtSize
    function fmtSize(bytes) {
        var n = Number(bytes);
        if (isNaN(n)) return '-';
        if (n < 1024) return n + ' B';
        if (n < 1024 * 1024) return (n / 1024).toFixed(2) + ' KB';
        if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(2) + ' MB';
        return (n / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
    }

    // 5. fmtTime（ts 为秒级 unix 时间戳）
    function fmtTime(ts) {
        var n = Number(ts);
        if (isNaN(n)) return '';
        var d = new Date(n * 1000);
        return d.toLocaleString('zh-CN', { hour12: false });
    }

    // 6. esc HTML 转义：所有外部可控文本进 innerHTML 前必须过这里。& < > 防标签/实体注入，两个引号防
    // 属性注入——表格行与配置行都是字符串拼接（value="…"、data-url="…"），漏转义引号即可从属性里
    // 逃出并挂上事件处理器。走 textContent 的位置不经它，但拼接路径一律不得裸插值。
    function esc(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // 6b. 前端 i18n：界面文案字典（语言集与后端 i18n.py 一致：zh_CN / en_US / en_GB / zh_TW）。
    // 后端负责控制台/日志输出翻译（GET/PUT /api/language 即时热切换），前端只负责静态界面文案：
    // data-i18n / data-i18n-placeholder / data-i18n-title 属性 + t() 动态拼接。
    // 下面四套目录是**字符串数据**（等同代码），键与值都不可随手改：四套键集必须逐一相等，且覆盖
    // index.html 的每个 data-i18n* 键与本文件每个 t() 字面量键——由 tests/frontend/test_quality_ui.mjs
    // 的 MIN-10 段机检（它从声明处按大括号配平截取本字典再求值，故声明行与键名不可重排或改名）。
    // 同步范围（实测）：面板点分键（config.save / common.cancel / danmaku.* 等）只进下面四套内嵌目录
    // ——后端 i18n/ 下的 gettext 目录按**中文源串**作 msgid、只服务控制台/GUI/推送，往里塞面板键只会
    // 得到无人 import 的孤儿 msgid（compile_po.py --check 与 extract_i18n_strings.py 都不报）。其余
    // 用户可见文案仍「五处同改」（四份 i18n 目录 + 本文件），见 AGENTS.md 的 i18n 扫描盲区清单。
    var LANG_KEY = 'dlr_lang';
    var currentLang = 'zh_CN';
    var I18N = {
        zh_CN: {
            'title': 'DouyinLiveRecorder 管理面板', 'brand': '直播录制管理面板',
            'tab.dashboard': '仪表盘', 'tab.danmaku': '弹幕监控', 'tab.rooms': '直播间',
            'tab.config': '配置', 'tab.files': '文件', 'logout': '退出',
            'theme.toggle': '切换主题', 'language.select': '语言',
            'login.title': '登录', 'login.password': '访问密码', 'login.submit': '登录', 'login.failed': '登录失败',
            'dashboard.engineWarning': '⚠️ 录制引擎已停止运行，请检查日志或重启服务',
            'dashboard.statusUnavailable': '⚠️ 状态数据获取失败，面板数据可能不是最新的（后端错误码 status_unavailable）',
            'dashboard.monitoring': '监测中', 'dashboard.recording': '录制中',
            'dashboard.errors': '错误数(累计/近期)', 'dashboard.disk': '磁盘剩余(GB)',
            'dashboard.recordingNow': '正在录制', 'dashboard.logs': '实时日志',
            'recording.state.on': '录制运行中', 'recording.state.off': '录制已停止',
            'recording.state.probeFailed': '状态取证失败',
            'recording.start': '开始录制', 'recording.stop': '停止录制',
            'toast.recordingStarted': '录制已开始', 'toast.recordingStopped': '录制已停止',
            'col.name': '名称', 'col.platform': '平台', 'col.status': '状态', 'col.startTime': '开始时间',
            'col.duration': '已录时长', 'col.qualitySet': '设置画质', 'col.qualityActual': '实际画质',
            'col.url': '地址', 'col.enabled': '启用', 'col.recording': '录制中', 'col.actions': '操作',
            'col.type': '类型', 'col.size': '大小', 'col.mtime': '修改时间',
            'empty.noRecording': '暂无录制', 'loading': '加载中...', 'loadFailed': '加载失败',
            'danmaku.rooms': '弹幕房间', 'danmaku.col.total': '累计弹幕', 'danmaku.col.rate': '速率(条/分)',
            'danmaku.col.gifts': '礼物', 'danmaku.col.online': '在线', 'danmaku.emptyRooms': '暂无监控数据',
            'danmaku.unavailable': '弹幕监控状态获取失败，以下为最后一次成功取到的数据（后端错误码 danmaku_unavailable）',
            'danmaku.live': '实时弹幕', 'danmaku.allRooms': '全部房间', 'danmaku.clear': '清空',
            'danmaku.connected': '已连接', 'danmaku.disconnected': '已断开', 'danmaku.noData': '暂无弹幕数据',
            // 筛选无匹配时的空态提示，理由见 dmRenderStream
            'danmaku.noMatch': '当前筛选条件下没有弹幕，试试切换房间或选择「全部房间」',
            'danmaku.gift': '[礼物] ', 'danmaku.sc': '[SC] ', 'danmaku.dropped': ' 条已省略)',
            'danmaku.truncated': '（消息量过大，部分已折叠）',
            'danmaku.hint': '未看到数据？请在「配置 → 录制设置」开启「是否弹幕监控(是/否)」，且直播间平台需支持弹幕（斗鱼/B站/虎牙/抖音/Twitch）',
            'rooms.add': '添加直播间', 'rooms.urlPlaceholder': '直播间地址', 'rooms.defaultQuality': '默认画质',
            'rooms.namePlaceholder': '主播名称（可选）', 'rooms.addBtn': '添加', 'rooms.list': '直播间列表',
            'rooms.empty': '暂无直播间', 'rooms.delete': '删除', 'rooms.enter': '进入', 'rooms.download': '下载',
            'rooms.deleteConfirm': '确认删除该直播间？',
            'rooms.manageQuality': '画质选项', 'rooms.addQuality': '添加画质',
            'rooms.qualityHint': '画质选项存于 config.ini，WEB 与桌面端画质切换菜单共用；仅内置档位可选（自定义名称不会被录制引擎识别）',
            'rooms.qualityEmpty': '已全部添加', 'rooms.qualityAddBtn': '添加',
            'toast.qualityAdded': '已添加画质选项', 'toast.qualityRemoved': '已移除画质选项',
            'toast.qualitySaveFailed': '保存画质选项失败: ', 'toast.qualityLoadFailed': '加载画质选项失败: ',
            'toast.qualityChanged': '已切换画质为 {q}，下一轮检测循环生效', 'toast.qualityReset': '已恢复默认画质，下一轮检测循环生效',
            'toast.qualityChangeFailed': '切换画质失败: ',
            'config.title': '录制与推送配置', 'config.save': '保存配置', 'config.noChanges': '无变更',
            'config.saved': '已保存 {n} 项', 'config.loadFailed': '加载失败', 'config.none': '无配置',
            'config.hint.https': '开启 = HTTPS 录制并跳过 SSL 证书校验；关闭 = HTTP 录制并恢复默认证书校验（已整合原「是否强制启用https录制」与「是否禁用SSL证书验证」）',
            'config.hint.sslOn': 'HTTPS 录制模式：已全局跳过 SSL 证书校验，此列表无需配置（兼容保留）',
            'config.hint.sslOff': 'HTTP 录制模式：默认校验证书；列表内平台将跳过证书校验（适用于证书异常平台，如虎牙/B站）',
            'config.deprecated': '已整合进「是否启用https录制」，此配置不再生效',
            // MID-37：掩码凭据的三条提示文案（行内说明 / 清空确认 / 跳过统计 / 服务端拒绝）
            'config.hint.masked': '该项已脱敏为 *** ，原值仍保存在服务端；留空提交需要先确认，且服务端不允许清空敏感项',
            'config.clearSecretConfirm': '「{k}」当前显示的是掩码 ***，提交空值会尝试用空串覆盖真实凭据（无法自动回滚）。确定仍要提交空值吗？',
            'config.secretSkipped': '已跳过 {n} 项掩码凭据的空值提交',
            'config.saveRejected': '服务端拒绝保存: ',
            'config.partialSaved': '已应用 {n} 项，第 {m} 项失败，其余改动未提交（已回拉服务端真值）',
            'config.authChangeConfirm': '即将修改认证相关配置「{k}」：这会改变谁能访问本面板（关闭认证或改写口令都可能让本机任意进程获得控制权），且该变更不随 token 吊销而回滚。确认提交？',
            'config.authChangeSkipped': '已跳过 {n} 项认证相关改动（未确认）',
            'config.authChangeReauth': '请复验当前 Web 口令（修改认证配置需要；留空或取消即放弃本次改动）:',
            'files.title': '录制文件', 'files.root': '根目录', 'files.emptyDir': '空目录',
            // common.cancel —— #reauth-modal 口令窗的取消按钮；四套目录同键同步添加，
            // 键集相等由 tests/frontend/test_quality_ui.mjs 的 MIN-10 段机检。
            'common.yes': '是', 'common.no': '否', 'common.cancel': '取消', 'common.unauthorized': '未授权',
            'common.requestFailed': '请求失败',
            'toast.enabled': '已启用', 'toast.disabled': '已禁用', 'toast.opFailed': '操作失败: ',
            'toast.deleted': '已删除', 'toast.deleteFailed': '删除失败: ', 'toast.added': '已添加',
            'toast.addFailed': '添加失败: ', 'toast.urlRequired': '请输入直播间地址',
            'toast.downloadFailed': '下载失败: ', 'toast.loginExpired': '登录已过期，请重新登录',
            'toast.saveFailed': '保存失败: ', 'toast.langSwitched': '语言已切换',
            'toast.langSwitchFailed': '语言切换失败: ',
            // 图标导入：err.* 的键名**就是** POST /api/icon 回传的机器码 detail，
            // 与 src/ui_icons.py::validate_icon_bytes 的 code 一一对应——前端只做码→文案映射，
            // 不在后端拼中文（少一处四目录漂移面）。四套目录同键同步，键集相等由前端用例机检。
            'icon.import': '导入图标',
            'icon.badFormat': '仅支持 .ico 图标文件（需含 16×16，建议含 256×256）',
            'icon.readFailed': '读取文件失败',
            'icon.err.not_ico': '不是有效的 ICO 文件',
            'icon.err.no_tray_size': '图标缺少 16×16 分辨率，系统托盘会显示模糊',
            'icon.err.too_large': '图标文件过大（上限 512KB）',
            'icon.err.empty': '文件内容为空',
            'icon.err.bad_base64': '图标数据不是合法的 base64',
            'icon.err.write_failed': '图标落盘失败，请检查 config/icons 目录可写',
            'icon.no_app_size': '图标缺少 256×256 分辨率，应用图标会放大发虚',
            'icon.ok': '图标已导入，页面标签已刷新；Web 托盘图标下次启动时生效',
            'icon.fail': '导入图标失败: '
        },
        en_US: {
            'title': 'DouyinLiveRecorder Panel', 'brand': 'Live Recording Panel',
            'tab.dashboard': 'Dashboard', 'tab.danmaku': 'Danmaku', 'tab.rooms': 'Rooms',
            'tab.config': 'Config', 'tab.files': 'Files', 'logout': 'Logout',
            'theme.toggle': 'Toggle theme', 'language.select': 'Language',
            'login.title': 'Login', 'login.password': 'Access password', 'login.submit': 'Login', 'login.failed': 'Login failed',
            'dashboard.engineWarning': '⚠️ The recording engine has stopped. Check logs or restart the service',
            'dashboard.statusUnavailable': '⚠️ Failed to fetch status data; the panel may be showing stale values (backend error code status_unavailable)',
            'dashboard.monitoring': 'Monitoring', 'dashboard.recording': 'Recording',
            'dashboard.errors': 'Errors (total/recent)', 'dashboard.disk': 'Disk free (GB)',
            'dashboard.recordingNow': 'Recording now', 'dashboard.logs': 'Live logs',
            'recording.state.on': 'Recording active', 'recording.state.off': 'Recording stopped',
            'recording.state.probeFailed': 'Status evidence unavailable',
            'recording.start': 'Start recording', 'recording.stop': 'Stop recording',
            'toast.recordingStarted': 'Recording started', 'toast.recordingStopped': 'Recording stopped',
            'col.name': 'Name', 'col.platform': 'Platform', 'col.status': 'Status', 'col.startTime': 'Start time',
            'col.duration': 'Duration', 'col.qualitySet': 'Set quality', 'col.qualityActual': 'Actual quality',
            'col.url': 'URL', 'col.enabled': 'Enabled', 'col.recording': 'Recording', 'col.actions': 'Actions',
            'col.type': 'Type', 'col.size': 'Size', 'col.mtime': 'Modified',
            'empty.noRecording': 'No recordings', 'loading': 'Loading...', 'loadFailed': 'Load failed',
            'danmaku.rooms': 'Danmaku rooms', 'danmaku.col.total': 'Messages', 'danmaku.col.rate': 'Rate (msg/min)',
            'danmaku.col.gifts': 'Gifts', 'danmaku.col.online': 'Online', 'danmaku.emptyRooms': 'No monitoring data',
            'danmaku.unavailable': 'Failed to fetch danmaku monitoring status; showing the last data retrieved successfully (backend error code danmaku_unavailable)',
            'danmaku.live': 'Live danmaku', 'danmaku.allRooms': 'All rooms', 'danmaku.clear': 'Clear',
            'danmaku.connected': 'Connected', 'danmaku.disconnected': 'Disconnected', 'danmaku.noData': 'No danmaku data',
            // empty state shown when the room filter matches nothing
            'danmaku.noMatch': 'No danmaku under the current filter — try another room or "All rooms"',
            'danmaku.gift': '[Gift] ', 'danmaku.sc': '[SC] ', 'danmaku.dropped': ' messages omitted)',
            'danmaku.truncated': '(Too many messages, some collapsed)',
            'danmaku.hint': 'No data? Enable "是否弹幕监控(是/否)" in Config → Recording settings, and make sure the platform supports danmaku (Douyu/Bilibili/Huya/Douyin/Twitch)',
            'rooms.add': 'Add room', 'rooms.urlPlaceholder': 'Live room URL', 'rooms.defaultQuality': 'Default quality',
            'rooms.namePlaceholder': 'Streamer name (optional)', 'rooms.addBtn': 'Add', 'rooms.list': 'Room list',
            'rooms.empty': 'No rooms', 'rooms.delete': 'Delete', 'rooms.enter': 'Open', 'rooms.download': 'Download',
            'rooms.deleteConfirm': 'Delete this room?',
            'rooms.manageQuality': 'Quality options', 'rooms.addQuality': 'Add quality',
            'rooms.qualityHint': 'Quality options are stored in config.ini and shared with the desktop quality switcher; only built-in tiers can be selected (custom names are not recognised by the recording engine)',
            'rooms.qualityEmpty': 'All added', 'rooms.qualityAddBtn': 'Add',
            'toast.qualityAdded': 'Quality option added', 'toast.qualityRemoved': 'Quality option removed',
            'toast.qualitySaveFailed': 'Failed to save quality options: ', 'toast.qualityLoadFailed': 'Failed to load quality options: ',
            'toast.qualityChanged': 'Quality changed to {q}, effective on the next check cycle', 'toast.qualityReset': 'Reset to default quality, effective on the next check cycle',
            'toast.qualityChangeFailed': 'Failed to change quality: ',
            'config.title': 'Recording & Push Config', 'config.save': 'Save config', 'config.noChanges': 'No changes',
            'config.saved': 'Saved {n} items', 'config.loadFailed': 'Load failed', 'config.none': 'No config',
            'config.hint.https': 'On = HTTPS recording with SSL certificate verification skipped; Off = HTTP recording with default certificate verification (merges the former "force HTTPS" and "disable SSL verification" options)',
            'config.hint.sslOn': 'HTTPS mode: certificate verification is globally skipped; this list is not needed (kept for compatibility)',
            'config.hint.sslOff': 'HTTP mode: certificates are verified by default; platforms in this list skip verification (for platforms with broken certificates, e.g. Huya/Bilibili)',
            'config.deprecated': 'Merged into "是否启用https录制"; this option no longer takes effect',
            // hints for masked credentials (inline note / clear confirmation / skipped count / server rejection)
            'config.hint.masked': 'This value is masked as ***; the real value is still stored server-side. Submitting it empty requires confirmation, and the server refuses to blank sensitive items',
            'config.clearSecretConfirm': '"{k}" currently shows the mask ***; submitting an empty value would overwrite the real credential with an empty string (not automatically reversible). Submit the empty value anyway?',
            'config.secretSkipped': 'Skipped {n} empty submission(s) for masked credentials',
            'config.saveRejected': 'Rejected by server: ',
            'config.partialSaved': 'Applied {n} item(s); item {m} failed and the remaining changes were not submitted (server values reloaded)',
            'config.authChangeConfirm': 'You are about to change the authentication setting "{k}": this alters who can reach this panel (disabling auth or resetting the password may let any local process take control), and the change is not reverted by revoking tokens. Submit?',
            'config.authChangeSkipped': 'Skipped {n} authentication-related change(s) (not confirmed)',
            'config.authChangeReauth': 'Re-enter the current Web password (required to change authentication settings; leave blank or cancel to discard this change):',
            'files.title': 'Recordings', 'files.root': 'Root', 'files.emptyDir': 'Empty folder',
            'common.yes': 'Yes', 'common.no': 'No', 'common.cancel': 'Cancel', 'common.unauthorized': 'Unauthorized',
            'common.requestFailed': 'Request failed',
            'toast.enabled': 'Enabled', 'toast.disabled': 'Disabled', 'toast.opFailed': 'Operation failed: ',
            'toast.deleted': 'Deleted', 'toast.deleteFailed': 'Delete failed: ', 'toast.added': 'Added',
            'toast.addFailed': 'Add failed: ', 'toast.urlRequired': 'Please enter a live room URL',
            'toast.downloadFailed': 'Download failed: ', 'toast.loginExpired': 'Login expired, please log in again',
            'toast.saveFailed': 'Save failed: ', 'toast.langSwitched': 'Language switched',
            'toast.langSwitchFailed': 'Language switch failed: ',
            // Icon import: err.* keys ARE the machine codes returned by POST /api/icon
            // (mirroring src/ui_icons.py::validate_icon_bytes). Front end only maps code -> text.
            'icon.import': 'Import Icon',
            'icon.badFormat': 'Only .ico files are supported (must contain 16x16, 256x256 recommended)',
            'icon.readFailed': 'Failed to read the file',
            'icon.err.not_ico': 'Not a valid ICO file',
            'icon.err.no_tray_size': 'Missing the 16x16 frame - the tray icon will look blurry',
            'icon.err.too_large': 'Icon file too large (512KB max)',
            'icon.err.empty': 'The file is empty',
            'icon.err.bad_base64': 'Icon data is not valid base64',
            'icon.err.write_failed': 'Could not save the icon - check that config/icons is writable',
            'icon.no_app_size': 'Missing the 256x256 frame - the app icon will be upscaled',
            'icon.ok': 'Icon imported; tab icon refreshed. The Web tray icon applies on next start',
            'icon.fail': 'Icon import failed: '
        },
        en_GB: {
            'title': 'DouyinLiveRecorder Panel', 'brand': 'Live Recording Panel',
            'tab.dashboard': 'Dashboard', 'tab.danmaku': 'Danmaku', 'tab.rooms': 'Rooms',
            'tab.config': 'Config', 'tab.files': 'Files', 'logout': 'Log out',
            'theme.toggle': 'Toggle theme', 'language.select': 'Language',
            'login.title': 'Log in', 'login.password': 'Access password', 'login.submit': 'Log in', 'login.failed': 'Log in failed',
            'dashboard.engineWarning': '⚠️ The recording engine has stopped. Check logs or restart the service',
            'dashboard.statusUnavailable': '⚠️ Failed to fetch status data; the panel may be showing stale values (backend error code status_unavailable)',
            'dashboard.monitoring': 'Monitoring', 'dashboard.recording': 'Recording',
            'dashboard.errors': 'Errors (total/recent)', 'dashboard.disk': 'Disk free (GB)',
            'dashboard.recordingNow': 'Recording now', 'dashboard.logs': 'Live logs',
            'recording.state.on': 'Recording active', 'recording.state.off': 'Recording stopped',
            'recording.state.probeFailed': 'Status evidence unavailable',
            'recording.start': 'Start recording', 'recording.stop': 'Stop recording',
            'toast.recordingStarted': 'Recording started', 'toast.recordingStopped': 'Recording stopped',
            'col.name': 'Name', 'col.platform': 'Platform', 'col.status': 'Status', 'col.startTime': 'Start time',
            'col.duration': 'Duration', 'col.qualitySet': 'Set quality', 'col.qualityActual': 'Actual quality',
            'col.url': 'URL', 'col.enabled': 'Enabled', 'col.recording': 'Recording', 'col.actions': 'Actions',
            'col.type': 'Type', 'col.size': 'Size', 'col.mtime': 'Modified',
            'empty.noRecording': 'No recordings', 'loading': 'Loading...', 'loadFailed': 'Load failed',
            'danmaku.rooms': 'Danmaku rooms', 'danmaku.col.total': 'Messages', 'danmaku.col.rate': 'Rate (msg/min)',
            'danmaku.col.gifts': 'Gifts', 'danmaku.col.online': 'Online', 'danmaku.emptyRooms': 'No monitoring data',
            'danmaku.unavailable': 'Failed to fetch danmaku monitoring status; showing the last data retrieved successfully (backend error code danmaku_unavailable)',
            'danmaku.live': 'Live danmaku', 'danmaku.allRooms': 'All rooms', 'danmaku.clear': 'Clear',
            'danmaku.connected': 'Connected', 'danmaku.disconnected': 'Disconnected', 'danmaku.noData': 'No danmaku data',
            // empty state shown when the room filter matches nothing
            'danmaku.noMatch': 'No danmaku under the current filter — try another room or "All rooms"',
            'danmaku.gift': '[Gift] ', 'danmaku.sc': '[SC] ', 'danmaku.dropped': ' messages omitted)',
            'danmaku.truncated': '(Too many messages, some collapsed)',
            'danmaku.hint': 'No data? Enable "是否弹幕监控(是/否)" in Config → Recording settings, and make sure the platform supports danmaku (Douyu/Bilibili/Huya/Douyin/Twitch)',
            'rooms.add': 'Add room', 'rooms.urlPlaceholder': 'Live room URL', 'rooms.defaultQuality': 'Default quality',
            'rooms.namePlaceholder': 'Streamer name (optional)', 'rooms.addBtn': 'Add', 'rooms.list': 'Room list',
            'rooms.empty': 'No rooms', 'rooms.delete': 'Delete', 'rooms.enter': 'Open', 'rooms.download': 'Download',
            'rooms.deleteConfirm': 'Delete this room?',
            'rooms.manageQuality': 'Quality options', 'rooms.addQuality': 'Add quality',
            'rooms.qualityHint': 'Quality options are stored in config.ini and shared with the desktop quality switcher; only built-in tiers can be selected (custom names are not recognised by the recording engine)',
            'rooms.qualityEmpty': 'All added', 'rooms.qualityAddBtn': 'Add',
            'toast.qualityAdded': 'Quality option added', 'toast.qualityRemoved': 'Quality option removed',
            'toast.qualitySaveFailed': 'Failed to save quality options: ', 'toast.qualityLoadFailed': 'Failed to load quality options: ',
            'toast.qualityChanged': 'Quality changed to {q}, effective on the next check cycle', 'toast.qualityReset': 'Reset to default quality, effective on the next check cycle',
            'toast.qualityChangeFailed': 'Failed to change quality: ',
            'config.title': 'Recording & Push Config', 'config.save': 'Save config', 'config.noChanges': 'No changes',
            'config.saved': 'Saved {n} items', 'config.loadFailed': 'Load failed', 'config.none': 'No config',
            'config.hint.https': 'On = HTTPS recording with SSL certificate verification skipped; Off = HTTP recording with default certificate verification (merges the former "force HTTPS" and "disable SSL verification" options)',
            'config.hint.sslOn': 'HTTPS mode: certificate verification is globally skipped; this list is not needed (kept for compatibility)',
            'config.hint.sslOff': 'HTTP mode: certificates are verified by default; platforms in this list skip verification (for platforms with broken certificates, e.g. Huya/Bilibili)',
            'config.deprecated': 'Merged into "是否启用https录制"; this option no longer takes effect',
            // hints for masked credentials (inline note / clear confirmation / skipped count / server rejection)
            'config.hint.masked': 'This value is masked as ***; the real value is still stored server-side. Submitting it empty requires confirmation, and the server refuses to blank sensitive items',
            'config.clearSecretConfirm': '"{k}" currently shows the mask ***; submitting an empty value would overwrite the real credential with an empty string (not automatically reversible). Submit the empty value anyway?',
            'config.secretSkipped': 'Skipped {n} empty submission(s) for masked credentials',
            'config.saveRejected': 'Rejected by server: ',
            'config.partialSaved': 'Applied {n} item(s); item {m} failed and the remaining changes were not submitted (server values reloaded)',
            'config.authChangeConfirm': 'You are about to change the authentication setting "{k}": this alters who can reach this panel (disabling auth or resetting the password may let any local process take control), and the change is not reverted by revoking tokens. Submit?',
            'config.authChangeSkipped': 'Skipped {n} authentication-related change(s) (not confirmed)',
            'config.authChangeReauth': 'Re-enter the current Web password (required to change authentication settings; leave blank or cancel to discard this change):',
            'files.title': 'Recordings', 'files.root': 'Root', 'files.emptyDir': 'Empty folder',
            'common.yes': 'Yes', 'common.no': 'No', 'common.cancel': 'Cancel', 'common.unauthorized': 'Unauthorised',
            'common.requestFailed': 'Request failed',
            'toast.enabled': 'Enabled', 'toast.disabled': 'Disabled', 'toast.opFailed': 'Operation failed: ',
            'toast.deleted': 'Deleted', 'toast.deleteFailed': 'Delete failed: ', 'toast.added': 'Added',
            'toast.addFailed': 'Add failed: ', 'toast.urlRequired': 'Please enter a live room URL',
            'toast.downloadFailed': 'Download failed: ', 'toast.loginExpired': 'Log in expired, please log in again',
            'toast.saveFailed': 'Save failed: ', 'toast.langSwitched': 'Language switched',
            'toast.langSwitchFailed': 'Language switch failed: ',
            // Icon import: err.* keys ARE the machine codes returned by POST /api/icon
            // (mirroring src/ui_icons.py::validate_icon_bytes). Front end only maps code -> text.
            'icon.import': 'Import Icon',
            'icon.badFormat': 'Only .ico files are supported (must contain 16x16, 256x256 recommended)',
            'icon.readFailed': 'Failed to read the file',
            'icon.err.not_ico': 'Not a valid ICO file',
            'icon.err.no_tray_size': 'Missing the 16x16 frame - the tray icon will look blurry',
            'icon.err.too_large': 'Icon file too large (512KB max)',
            'icon.err.empty': 'The file is empty',
            'icon.err.bad_base64': 'Icon data is not valid base64',
            'icon.err.write_failed': 'Could not save the icon - check that config/icons is writable',
            'icon.no_app_size': 'Missing the 256x256 frame - the app icon will be upscaled',
            'icon.ok': 'Icon imported; tab icon refreshed. The Web tray icon applies on next start',
            'icon.fail': 'Icon import failed: '
        },
        zh_TW: {
            'title': 'DouyinLiveRecorder 管理面板', 'brand': '直播錄製管理面板',
            'tab.dashboard': '儀表板', 'tab.danmaku': '彈幕監控', 'tab.rooms': '直播間',
            'tab.config': '設定', 'tab.files': '檔案', 'logout': '登出',
            'theme.toggle': '切換主題', 'language.select': '語言',
            'login.title': '登入', 'login.password': '存取密碼', 'login.submit': '登入', 'login.failed': '登入失敗',
            'dashboard.engineWarning': '⚠️ 錄製引擎已停止執行，請檢查日誌或重新啟動服務',
            'dashboard.statusUnavailable': '⚠️ 狀態資料取得失敗，面板資料可能不是最新的（後端錯誤碼 status_unavailable）',
            'dashboard.monitoring': '監測中', 'dashboard.recording': '錄製中',
            'dashboard.errors': '錯誤數(累計/近期)', 'dashboard.disk': '磁碟剩餘(GB)',
            'dashboard.recordingNow': '正在錄製', 'dashboard.logs': '即時日誌',
            'recording.state.on': '錄製運行中', 'recording.state.off': '錄製已停止',
            'recording.state.probeFailed': '狀態取證失敗',
            'recording.start': '開始錄製', 'recording.stop': '停止錄製',
            'toast.recordingStarted': '錄製已開始', 'toast.recordingStopped': '錄製已停止',
            'col.name': '名稱', 'col.platform': '平台', 'col.status': '狀態', 'col.startTime': '開始時間',
            'col.duration': '已錄時長', 'col.qualitySet': '設定畫質', 'col.qualityActual': '實際畫質',
            'col.url': '位址', 'col.enabled': '啟用', 'col.recording': '錄製中', 'col.actions': '操作',
            'col.type': '類型', 'col.size': '大小', 'col.mtime': '修改時間',
            'empty.noRecording': '暫無錄製', 'loading': '載入中...', 'loadFailed': '載入失敗',
            'danmaku.rooms': '彈幕房間', 'danmaku.col.total': '累計彈幕', 'danmaku.col.rate': '速率(條/分)',
            'danmaku.col.gifts': '禮物', 'danmaku.col.online': '線上', 'danmaku.emptyRooms': '暫無監控資料',
            'danmaku.unavailable': '彈幕監控狀態取得失敗，以下為最後一次成功取得的資料（後端錯誤碼 danmaku_unavailable）',
            'danmaku.live': '即時彈幕', 'danmaku.allRooms': '全部房間', 'danmaku.clear': '清空',
            'danmaku.connected': '已連線', 'danmaku.disconnected': '已斷線', 'danmaku.noData': '暫無彈幕資料',
            // 篩選無匹配時的空態提示
            'danmaku.noMatch': '目前篩選條件下沒有彈幕，請切換房間或選擇「全部房間」',
            'danmaku.gift': '[禮物] ', 'danmaku.sc': '[SC] ', 'danmaku.dropped': ' 條已省略)',
            'danmaku.truncated': '（訊息量過大，部分已摺疊）',
            'danmaku.hint': '未看到資料？請在「設定 → 錄製設定」開啟「是否彈幕監控(是/否)」，且直播間平台需支援彈幕（鬥魚/B站/虎牙/抖音/Twitch）',
            'rooms.add': '新增直播間', 'rooms.urlPlaceholder': '直播間位址', 'rooms.defaultQuality': '預設畫質',
            'rooms.namePlaceholder': '主播名稱（可選）', 'rooms.addBtn': '新增', 'rooms.list': '直播間列表',
            'rooms.empty': '暫無直播間', 'rooms.delete': '刪除', 'rooms.enter': '進入', 'rooms.download': '下載',
            'rooms.deleteConfirm': '確認刪除該直播間？',
            'rooms.manageQuality': '畫質選項', 'rooms.addQuality': '新增畫質',
            'rooms.qualityHint': '畫質選項存於 config.ini，Web 與桌面端畫質切換選單共用；僅內建檔位可選（自訂名稱不會被錄製引擎識別）',
            'rooms.qualityEmpty': '已全部新增', 'rooms.qualityAddBtn': '新增',
            'toast.qualityAdded': '已新增畫質選項', 'toast.qualityRemoved': '已移除畫質選項',
            'toast.qualitySaveFailed': '儲存畫質選項失敗: ', 'toast.qualityLoadFailed': '載入畫質選項失敗: ',
            'toast.qualityChanged': '已切換畫質為 {q}，下一輪檢測循環生效', 'toast.qualityReset': '已恢復預設畫質，下一輪檢測循環生效',
            'toast.qualityChangeFailed': '切換畫質失敗: ',
            'config.title': '錄製與推送設定', 'config.save': '儲存設定', 'config.noChanges': '無變更',
            'config.saved': '已儲存 {n} 項', 'config.loadFailed': '載入失敗', 'config.none': '無設定',
            'config.hint.https': '開啟 = HTTPS 錄製並跳過 SSL 憑證校驗；關閉 = HTTP 錄製並恢復預設憑證校驗（已整合原「是否強制啟用https錄製」與「是否禁用SSL憑證驗證」）',
            'config.hint.sslOn': 'HTTPS 錄製模式：已全域跳過 SSL 憑證校驗，此列表無需設定（相容保留）',
            'config.hint.sslOff': 'HTTP 錄製模式：預設校驗憑證；列表內平台將跳過憑證校驗（適用於憑證異常平台，如虎牙/B站）',
            'config.deprecated': '已整合進「是否啟用https錄製」，此設定不再生效',
            // 遮罩憑據的四條提示（行內說明 / 清空確認 / 跳過統計 / 服務端拒絕）
            'config.hint.masked': '該項已脫敏為 *** ，原值仍儲存於服務端；提交空值需要先確認，且服務端不允許清空敏感項',
            'config.clearSecretConfirm': '「{k}」目前顯示的是遮罩 ***，提交空值會嘗試以空字串覆寫真實憑據（無法自動回滾）。確定仍要提交空值嗎？',
            'config.secretSkipped': '已跳過 {n} 項遮罩憑據的空值提交',
            'config.saveRejected': '服務端拒絕儲存: ',
            'config.partialSaved': '已套用 {n} 項，第 {m} 項失敗，其餘變更未提交（已回拉服務端真值）',
            'config.authChangeConfirm': '即將修改認證相關設定「{k}」：這會改變誰能存取本面板（關閉認證或改寫口令都可能讓本機任意程序取得控制權），且該變更不隨 token 吊銷而回滾。確認提交？',
            'config.authChangeSkipped': '已跳過 {n} 項認證相關變更（未確認）',
            'config.authChangeReauth': '請複驗目前 Web 口令（修改認證設定需要；留空或取消即放棄本次變更）:',
            'files.title': '錄製檔案', 'files.root': '根目錄', 'files.emptyDir': '空資料夾',
            'common.yes': '是', 'common.no': '否', 'common.cancel': '取消', 'common.unauthorized': '未授權',
            'common.requestFailed': '請求失敗',
            'toast.enabled': '已啟用', 'toast.disabled': '已停用', 'toast.opFailed': '操作失敗: ',
            'toast.deleted': '已刪除', 'toast.deleteFailed': '刪除失敗: ', 'toast.added': '已新增',
            'toast.addFailed': '新增失敗: ', 'toast.urlRequired': '請輸入直播間位址',
            'toast.downloadFailed': '下載失敗: ', 'toast.loginExpired': '登入已過期，請重新登入',
            'toast.saveFailed': '儲存失敗: ', 'toast.langSwitched': '語言已切換',
            'toast.langSwitchFailed': '語言切換失敗: ',
            // 圖示匯入：err.* 的鍵名即 POST /api/icon 回傳的機器碼 detail
            'icon.import': '匯入圖示',
            'icon.badFormat': '僅支援 .ico 圖示檔案（需含 16×16，建議含 256×256）',
            'icon.readFailed': '讀取檔案失敗',
            'icon.err.not_ico': '不是有效的 ICO 檔案',
            'icon.err.no_tray_size': '圖示缺少 16×16 尺寸，系統托盤會顯示模糊',
            'icon.err.too_large': '圖示檔案過大（上限 512KB）',
            'icon.err.empty': '檔案內容為空',
            'icon.err.bad_base64': '圖示資料不是合法的 base64',
            'icon.err.write_failed': '圖示寫入失敗，請檢查 config/icons 目錄可寫',
            'icon.no_app_size': '圖示缺少 256×256 尺寸，應用程式圖示會被放大',
            'icon.ok': '圖示已匯入，分頁圖示已更新；Web 托盤圖示將於下次啟動生效',
            'icon.fail': '匯入圖示失敗: '
        }
    };

    // 界面文案取值：当前语言缺失时回退 zh_CN，再缺失回退键名本身
    function t(key) {
        var dict = I18N[currentLang] || I18N.zh_CN;
        if (Object.prototype.hasOwnProperty.call(dict, key)) return dict[key];
        if (Object.prototype.hasOwnProperty.call(I18N.zh_CN, key)) return I18N.zh_CN[key];
        return key;
    }

    // 应用静态文案：data-i18n → textContent；data-i18n-placeholder → placeholder；
    // data-i18n-title → title 悬浮提示（用独立属性而非 data-i18n，避免覆写 #theme-toggle 的 🌙/☀️ 文本）。
    function applyTranslations() {
        var nodes = document.querySelectorAll('[data-i18n]');
        for (var i = 0; i < nodes.length; i++) {
            nodes[i].textContent = t(nodes[i].getAttribute('data-i18n'));
        }
        var phNodes = document.querySelectorAll('[data-i18n-placeholder]');
        for (var j = 0; j < phNodes.length; j++) {
            phNodes[j].setAttribute('placeholder', t(phNodes[j].getAttribute('data-i18n-placeholder')));
        }
        var titleNodes = document.querySelectorAll('[data-i18n-title]');
        for (var k = 0; k < titleNodes.length; k++) {
            titleNodes[k].setAttribute('title', t(titleNodes[k].getAttribute('data-i18n-title')));
        }
        document.documentElement.setAttribute('lang', currentLang.replace('_', '-'));
    }

    // 初始化语言选择器：读后端当前语言（失败回退本地偏好 safeGetItem，sessionStorage 优先），渲染选项
    function initLanguage() {
        var sel = $('language-select');
        if (!sel) return;
        var langNames = { zh_CN: '简体中文', en_US: 'English (US)', en_GB: 'English (UK)', zh_TW: '繁體中文' };
        var codes = ['zh_CN', 'en_US', 'en_GB', 'zh_TW'];
        var opts = '';
        for (var i = 0; i < codes.length; i++) {
            opts += '<option value="' + codes[i] + '">' + langNames[codes[i]] + '</option>';
        }
        sel.innerHTML = opts;
        api('/api/language').then(function (data) {
            currentLang = data && data.language ? data.language : (safeGetItem(LANG_KEY) || 'zh_CN');
            safeSetItem(LANG_KEY, currentLang);
            sel.value = currentLang;
            applyTranslations();
        }).catch(function () {
            currentLang = safeGetItem(LANG_KEY) || 'zh_CN';
            sel.value = currentLang;
            applyTranslations();
        });
        sel.addEventListener('change', function () {
            setLanguage(sel.value);
        });
    }

    // MID-2239：PUT /api/language 的响应（language/fallback/notice）必须被消费，并按**生效码**更新，
    // 不得按请求值回写。典型失效：PyYAML 缺失使 zh_TW 装载不到 → 后端实际生效并落盘 en_US，前端却
    // 切成内嵌 zh_TW 并把偏好写成 zh_TW、回退说明一次都不显示。
    function setLanguage(target) {
        api('/api/language', { method: 'PUT', body: { language: target } }).then(function (res) {
            // 以**生效码**为准：后端回什么就切什么、就持久化什么
            currentLang = (res && res.language) || target;
            safeSetItem(LANG_KEY, currentLang);
            var sel = $('language-select');
            if (sel) sel.value = currentLang;
            applyTranslations();
            if (res && res.fallback) {
                // 回退说明由后端给出（含目标语言与生效语言），是本地化过的文案
                toast(res.notice || t('toast.langSwitched'), 'info');
            } else {
                toast(t('toast.langSwitched'), 'success');
            }
        }).catch(function (e) {
            toast(t('toast.langSwitchFailed') + (e.message || ''), 'error');
        });
    }

    function hideAllViews() {
        var views = document.querySelectorAll('.view');
        for (var i = 0; i < views.length; i++) {
            views[i].classList.add('hidden');
        }
    }

    // 7b. 登出按钮显隐（MID-38）：#logout-btn 在 index.html 里带 class="hidden"（.hidden 为
    // display:none !important），没有代码移除该 class 的话，POST /api/logout（泄露 token 的唯一吊销
    // 入口，token 默认有效 86400s）在界面上根本点不到。登录成功/进入任意视图即显示，回到登录页即收起。
    function setLogoutVisible(visible) {
        var btn = $('logout-btn');
        if (!btn) return;
        if (visible) {
            btn.classList.remove('hidden');
        } else {
            btn.classList.add('hidden');
        }
    }

    // 8. showView
    function showView(name) {
        stopDanmakuPolling();
        // 切视图先停掉上一视图的轮询：原本只在最后的 else 分支停 SSE，切到 rooms/config/files/danmaku
        // 后 /api/status 仍每 2s 轮询并渲染隐藏 DOM。MID-2240：日志轮询必须一并停——否则 /api/logs 仍在
        // 每 5s 读一次日志文件（纯浪费），且它不会被下面的分支重新判断。
        stopSSE();
        stopLogsPolling();
        hideAllViews();
        // 以「有 token」而非「有视图」为显示条件：认证关闭的部署根本没有 bearer 可吊销，
        // 而未登录时顶栏的 tab 依然可点（视图本就可见），无条件显示会露出一个无效入口。
        setLogoutVisible(!!getToken());
        var v = $(name + '-view');
        if (v) v.classList.remove('hidden');
        var tabs = document.querySelectorAll('.tab');
        for (var i = 0; i < tabs.length; i++) {
            if (tabs[i].getAttribute('data-view') === name) {
                tabs[i].classList.add('active');
            } else {
                tabs[i].classList.remove('active');
            }
        }
        if (name === 'rooms') {
            // 先拉画质选项再渲染房间列表：行内画质下拉的选项来自 qualityOptions，顺序颠倒会让首屏
            // 下拉只剩「默认画质」+ 当前值（选项未就绪）。
            loadQualityOptions().finally(loadRooms);
        } else if (name === 'config') {
            loadConfig();
        } else if (name === 'files') {
            loadFiles('');
        } else if (name === 'danmaku') {
            startDanmakuPolling();
        } else if (name === 'dashboard') {
            startSSE();
            // MID-2240：loadLogs 只在切到仪表盘时拉一次，长期停留就永远看不到新日志，故交给轮询续期。
            loadLogs();
            startLogsPolling();
        }
    }

    // 9. showLogin
    function showLogin() {
        hideAllViews();
        // MID-38：登录页不得留登出入口——token 已被（或即将被）清空，此处是唯一的收起时机。
        setLogoutVisible(false);
        var lv = $('login-view');
        if (lv) lv.classList.remove('hidden');
        stopSSE();
        stopDanmakuPolling();
        stopLogsPolling();
    }

    // 10. doLogin —— POST /api/login，成功即 setToken() 存好返回的 token 并进入仪表盘；失败（含 401）
    // 在 #login-error 显示后端文案。密码仅此一次明文发送，之后一律用 Token。语言/主题偏好
    // 同样落在 sessionStorage（「隐私模式下不抛异常」换来的取舍），故不再跨浏览器重启持久化。
    async function doLogin() {
        var pw = $('login-password').value;
        try {
            var data = await api('/api/login', { method: 'POST', body: { password: pw } });
            setToken(data.token || '');
            $('login-error').textContent = '';
            // 登录成功后口令不再需要，随即清空：视图只是被 .hidden 隐藏、value 一个字符都没少，
            // DevTools/扩展/自动填充快照都拿得到。失败分支刻意不清，方便改一两个字符重登。
            var pwEl = $('login-password');
            if (pwEl) pwEl.value = '';
            showView('dashboard');
        } catch (e) {
            $('login-error').textContent = e.message || t('login.failed');
        }
    }

    // 10b. makePollChain —— M-21：三条轮询链唯一共用的一份「代次」实现。
    // 失效形态：stop*/pause* 只能 clearTimeout 掉**已排期**的定时器，取消不了**在途**请求；而旧请求落地
    // 后的续期回调只看一个布尔标志，「停止→立即重启」把标志置回「在跑」后，旧链会再排一次 setTimeout
    // 并顶掉模块级 timer——两条链只剩一条能被回收，另一条从此失联、按节拍继续发请求并渲染隐藏 DOM。
    // 机制：每次 halt/begin 把代次 +1；每轮 poll 带着自己那一代的代次回来，续期前必须证明「我仍是当前
    // 这一代」（renew），响应分支用 isCurrent 同样过滤——过期轮次既不渲染，也不改动链状态（退避计数、
    // 增量游标）。
    // 代价（知情接受）：被顶替的在途请求仍会把当轮响应下载完（最长 API_TIMEOUT_MS=10s）再丢弃。未选
    // abort：api() 内部自建 AbortController、外部拿不到句柄；且 AbortError 会落进三条链各自的 catch，
    // 把「主动取消」记成一次网络失败（触发退避并弹横幅），比修复前更坏。
    function makePollChain() {
        var timer = null;
        var gen = 0;
        // 作废当前代：推进代次使一切在途回调失效，并清掉唯一那个已排期的定时器。
        function halt() {
            gen += 1;
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
            return gen;
        }
        // 起新链：先 halt 顶掉旧链（含其一切在途回调），再排第一轮，把本轮代次交给 poll 带着走。
        function begin(firstDelay, run) {
            var myGen = halt();
            timer = setTimeout(function () {
                run(myGen);
            }, firstDelay);
            return myGen;
        }
        // 唯一续期入口：代次不符说明这条链已被 halt/begin 取代，回调必须自行消失——
        // 既不排期，也不把 timer 写成自己的 id（那正是旧链顶掉新链句柄的那一步）。
        function renew(myGen, delay, run) {
            if (myGen !== gen) return false;
            timer = setTimeout(function () {
                run(myGen);
            }, delay);
            return true;
        }
        function isCurrent(myGen) {
            return myGen === gen;
        }
        return { halt: halt, begin: begin, renew: renew, isCurrent: isCurrent };
    }

    // 11. startSSE / stopSSE / pauseSSE（轮询实现，非真实 SSE）
    // WD-10：失败退避 + 页面可见性感知。「正常 2s，连续失败按 2→5→10→30s 退避」，页面隐藏时停轮询、
    // 可见时立即拉一次。三个入口的分工即上方 SEV-2227 的两态拆分：startSSE=想要轮询、stopSSE=不要
    // 轮询（连意图一起清）、pauseSSE=只清定时器并保留意图（仅供 visibilitychange 隐藏侧，切视图别用）。
    var SSE_OK_INTERVAL = 2000;
    var SSE_BACKOFF_STEPS = [2000, 5000, 10000, 30000];
    var sseFailCount = 0;
    function startSSE() {
        sseWanted = true;
        sseStopped = false;
        // begin() 内已含「清掉上一代定时器 + 推进代次」，无需再手写 clearTimeout。
        sseChain.begin(0, function poll(myGen) {
            api('/api/status')
                .then(function (data) {
                    // M-21：过期轮次不得渲染、也不得把退避计数复位（它属于已被取代的那条链）
                    if (!sseChain.isCurrent(myGen)) return;
                    sseFailCount = 0;
                    // M-88③：后端重新应答即视为「已恢复」，当场把断开标签还原，
                    // 不等下一轮弹幕/状态渲染顺带覆盖（只在真出现过断开态时生效）。
                    markBackendUnreachable(false);
                    renderStatus(data);
                })
                .catch(function () {
                    if (!sseChain.isCurrent(myGen)) return;
                    sseFailCount += 1;
                    // SEV-2228：网络层失败（后端不可达/超时）才是「已断开」这一支；
                    // 仪表盘上的提示必须经 showStatusWarning，只写弹幕流等于没提示（见 markBackendUnreachable）。
                    markBackendUnreachable(true);
                    showStatusWarning(t('dashboard.statusUnavailable'));
                })
                .then(function () {
                    if (sseStopped) return;
                    var delay = SSE_OK_INTERVAL;
                    if (sseFailCount > 0) {
                        delay = SSE_BACKOFF_STEPS[Math.min(sseFailCount - 1, SSE_BACKOFF_STEPS.length - 1)];
                    }
                    sseChain.renew(myGen, delay, poll);
                });
        });
    }

    // 放弃轮询（切离仪表盘/退出登录时调用）：连意图一起清掉，否则切回仪表盘会被
    // visibilitychange 的恢复分支重新拉起一个不该存在的轮询。
    function stopSSE() {
        sseWanted = false;
        _haltSSE();
    }

    // 暂停轮询但保留意图：仅用于「页面隐藏」，可见时按 sseWanted 恢复。
    function pauseSSE() {
        _haltSSE();
    }

    // pauseSSE 与 stopSSE 的共同底座：只清在飞定时器并把状态置「已停」，
    // 是否连「想要轮询」的意图一起清掉由调用方决定（两态拆分见上方 SEV-2227 的状态声明处）。
    // M-21：halt() 同时推进代次，故「停止 → 立即重启」窗口里落地的旧在途回调不会再排期。
    function _haltSSE() {
        sseStopped = true;
        sseChain.halt();
    }

    // 仪表盘告警横幅的唯一写入口（SEV-2228 起「拿不到 / 不新鲜 / 引擎死」三类都走这里），传空串即隐藏。
    // #status-warning 常驻仪表盘视图内，不像 #danmaku-stream 那样受视图可见性限制。
    function showStatusWarning(text) {
        var el = $('status-warning');
        if (!el) return;
        if (text) {
            el.textContent = text;
            el.classList.remove('hidden');
        } else {
            el.textContent = '';
            el.classList.add('hidden');
        }
    }

    // WD-10：把「已断开」显式呈现给用户，而不是让面板停在陈旧数据上。此处写的 #danmaku-stream 只
    // 存在于弹幕视图内，仪表盘侧由 showStatusWarning 独立承担（MID-2237）。
    // M-88③：后端恢复后「已断开」无人复写、只能等
    // 下一轮渲染顺带覆盖。补恢复分支（用既有键 danmaku.connected，与断开态成对，不新增 msgid），
    // 并用 _backendMarkedDown 做状态闸门：只有真出现过断开态才还原标签，健康轮次零噪音、
    // 也不会把弹幕流区域反复改写。
    var _backendMarkedDown = false;

    function markBackendUnreachable(flag) {
        var el = $('danmaku-stream');
        if (!el) return;
        if (flag) {
            _backendMarkedDown = true;
            el.textContent = t('danmaku.disconnected');
        } else if (_backendMarkedDown) {
            _backendMarkedDown = false;
            el.textContent = t('danmaku.connected');
        }
    }

    // SEV-2221 / SEV-2228：告警优先级即下面的判定顺序——先报「拿不到 / 不新鲜」，再报「引擎死」。
    // 存活判定一律用 === false 而非真假值：字段缺失（后端未接线）视为健康，否则未接线的后端会把所有
    // 面板刷成红色告警——修复自己变成假告警源。
    // [历史注 2026-09-23] 此处曾有一条「已撤下的主循环探针键 === false」分支：它读的计数字段从未在
    // main.py 定义、键永不下发，分支永不成立；「取证失败」改由两个真实信号承担：error 与 stale。
    function updateStatusWarning(s) {
        if (!s || s.error === 'status_unavailable') {
            showStatusWarning(t('dashboard.statusUnavailable'));
            return;
        }
        if (s.stale === true) {
            showStatusWarning(t('dashboard.statusUnavailable'));
            return;
        }
        if (s.engine_alive === false) {
            showStatusWarning(t('dashboard.engineWarning'));
            return;
        }
        showStatusWarning('');
    }

    // 12. renderStatus —— /api/status 快照的唯一渲染出口：启动引导、仪表盘轮询、toggleRecording 之后
    // 的状态回拉三处都调它。故「拿不到 / 不新鲜 / 引擎死」的裁决必须放在这里（经 updateStatusWarning 与
    // renderRecordingControl），放到任一调用方都会让另外两条入口的口径分叉。
    function renderStatus(s) {
        if (!s) s = {};
        // SEV-2228：HTTP 200 也可能带 error:"status_unavailable"——采样失败时后端不再回 5xx，为的是
        // 让面板继续响应。旧实现不看 error，把监测数/录制数/磁盘画成「-」当作成功，用户看到的是「一切
        // 正常但数字全是横杠」。这里统一裁决告警，并把陈旧值显式标注出来。
        updateStatusWarning(s);
        renderRecordingControl(s);
        var warnEl = $('engine-warning');
        if (warnEl) {
            if (s.engine_alive === false) {
                warnEl.classList.remove('hidden');
            } else {
                warnEl.classList.add('hidden');
            }
        }
        var unavailable = s.error != null || s.stale === true;
        $('stat-monitoring').textContent = (s.monitoring != null ? s.monitoring : '-');
        $('stat-recording').textContent = (s.recording_count != null ? s.recording_count : '-');
        // 错误数双口径：累计（进程启动起）/ 近期（近 error_window_size 次检测周期内）
        var errTotal = (s.error_count != null ? s.error_count : '-');
        var errRecent = (s.recent_errors != null ? s.recent_errors : '-');
        $('stat-errors').textContent = errTotal + ' / ' + errRecent;
        $('stat-disk').textContent = (s.disk_free_gb != null ? s.disk_free_gb : '-');
        var tbody = $('recording-tbody');
        var rec = unavailable ? [] : (s.recording || []);
        if (!rec.length) {
            // 失败/陈旧时用「取证失败」而非「暂无录制」——后者会让用户以为录制真的空了。文案来自本地
            // 四语目录、经 esc() 后再拼（与上方同型）。
            var emptyText = esc(unavailable ? t('dashboard.statusUnavailable') : t('empty.noRecording'));
            tbody.innerHTML = '<tr><td colspan="5" class="empty">' + emptyText + '</td></tr>';
            return;
        }
        var html = '';
        for (var i = 0; i < rec.length; i++) {
            var r = rec[i];
            // 降级判定：实际画质非空且与设置不同 → 标红（actual 为空表示无法回采，不标红）
            var downClass = '';
            if (r.actual_quality && r.quality && r.actual_quality !== r.quality) {
                downClass = ' class="quality-down"';
            }
            var actualDisplay = r.actual_quality ? esc(r.actual_quality) : '-';
            html += '<tr>'
                + '<td>' + esc(r.name) + '</td>'
                + '<td>' + esc(r.quality) + '</td>'
                + '<td' + downClass + '>' + actualDisplay + '</td>'
                + '<td>' + esc(r.start_time) + '</td>'
                + '<td>' + esc(r.duration) + '</td>'
                + '</tr>';
        }
        tbody.innerHTML = html;
    }

    // 12b. 录制控制条：按状态快照同步「开始/停止录制」按钮与状态标签。recording_enabled 为引擎级录制
    // 开关：开启时禁用「开始」并启用「停止」，关闭时反之；引擎线程死亡时两按钮均禁用（切换已无意义，
    // 页面顶部另有引擎告警横幅）。状态标签用三 span + hidden 切换（on/off/probe），文案交给 data-i18n
    // 静态翻译（语言切换即时生效，无需等下一次轮询）。
    function renderRecordingControl(s) {
        var enabled = s.recording_enabled === true;
        // SEV-2228 后半：`engine_alive !== false` 只挡得住「后端明说引擎已死」。采样失败回的是 HTTP 200 +
        // error:status_unavailable、超时回退则是 stale:true，两种形态**都不带 engine_alive 键** →
        // undefined !== false 判成「活着」，面板在完全不知道引擎死活时仍放行开始/停止：点下去只会在
        // POST /api/recording/toggle 上撞一个用户看不懂的错误，而「停止录制」这条兜底路径尤其不该在取证
        // 失败时被当成可用。故 error/stale 一律按「未知」处理（两键禁用 + 标签切「取证失败」），与
        // 仪表盘横幅同口径。
        var unknown = s.error != null || s.stale === true;
        var engineAlive = s.engine_alive !== false && !unknown;
        // 状态标签容器是 class（index.html 的 span.recording-state），勿用 #id 选择器
        var onEl = document.querySelector('.recording-state .state-on');
        var offEl = document.querySelector('.recording-state .state-off');
        var probeEl = document.querySelector('.recording-state .state-probe');
        if (onEl && offEl) {
            onEl.classList.toggle('hidden', !enabled || unknown);
            offEl.classList.toggle('hidden', enabled || unknown);
        }
        if (probeEl) probeEl.classList.toggle('hidden', !unknown);
        var startBtn = $('recording-start-btn');
        var stopBtn = $('recording-stop-btn');
        if (startBtn) startBtn.disabled = enabled || !engineAlive;
        if (stopBtn) stopBtn.disabled = !enabled || !engineAlive;
    }

    // 12c. 开始/停止录制：POST /api/recording/toggle 后立即拉取状态同步按钮，
    // 页面刷新/重连后的按钮真实态由仪表盘 2s 轮询（renderStatus）持续同步
    async function toggleRecording(enable) {
        var btn = enable ? $('recording-start-btn') : $('recording-stop-btn');
        if (btn) btn.disabled = true; // 防重复点击；成功后按后端真实状态恢复，失败立即恢复
        try {
            await api('/api/recording/toggle', { method: 'POST', body: { enable: enable } });
            toast(enable ? t('toast.recordingStarted') : t('toast.recordingStopped'), 'success');
        } catch (e) {
            toast(t('toast.opFailed') + (e.message || ''), 'error');
            if (btn) btn.disabled = false;
            return;
        }
        // 状态回拉独立容错：toggle 已成功，回拉失败静默交给 2s 轮询同步，勿误报「操作失败」
        try {
            renderStatus(await api('/api/status'));
        } catch (e) { /* 忽略 */ }
    }

    // 13. loadLogs —— GET /api/logs?lines=100，取最近 100 行纯文本日志拼到 #log-stream 并滚到底部。
    // isActive 是日志轮询链传入的「本轮代次是否仍有效」判据：过期轮次直接丢弃、不写 #log-stream
    // （视图已切走时把旧日志刷进隐藏面板没有意义）；showView 首次进仪表盘时不传，按恒有效处理。
    async function loadLogs(isActive) {
        var check = typeof isActive === 'function' ? isActive : null;
        try {
            var data = await api('/api/logs?lines=100');
            if (check && !check()) return;
            var lines = (data && data.lines) || [];
            var el = $('log-stream');
            el.textContent = lines.join('\n');
            el.scrollTop = el.scrollHeight;
        } catch (e) {
            /* 忽略日志加载错误 */
        }
    }

    // 13a. 仪表盘日志轮询（MID-2240）：loadLogs 只在切到仪表盘那一刻调一次，用户长时间停留时
    // 「实时日志」名不副实。节拍取 5s：日志不是秒级指标，而 /api/logs 是读文件、比 /api/status 更重，
    // 没必要同频。可见性感知与弹幕轮询同型：页面隐藏即停。logTimer 已由 logsChain 承载（机制见 10b）。
    var logsChain = makePollChain();
    var logStopped = true;
    var LOGS_POLL_INTERVAL = 5000;
    function startLogsPolling() {
        stopLogsPolling();
        logStopped = false;
        logsChain.begin(LOGS_POLL_INTERVAL, function poll(myGen) {
            loadLogs(function () {
                return logsChain.isCurrent(myGen);
            }).then(function () {
                if (!logStopped) {
                    logsChain.renew(myGen, LOGS_POLL_INTERVAL, poll);
                }
            });
        });
    }
    function stopLogsPolling() {
        logStopped = true;
        logsChain.halt();
    }

    // 13b. 弹幕监控：轮询 + 渲染（增量游标 since=seq，2 秒一次）。
    // 游标只前进（last_seq 大于 dmLastSeq 才赋值）：失败轮回的是原 since，用它覆盖会让已取到的序号
    // 倒退、下一轮重复拉同一段。轮询只随进入/离开弹幕视图起停，与仪表盘两条互不牵连。旧一代的请求
    // 落地后既不续期也不 renderDanmaku——后者会推进游标，改动新链的续拉位置（机制见 10b）。
    function startDanmakuPolling() {
        stopDanmakuPolling();
        dmStopped = false;
        dmChain.begin(0, function poll(myGen) {
            api('/api/danmaku?since=' + dmLastSeq)
                .then(function (data) {
                    if (!dmChain.isCurrent(myGen)) return;
                    return renderDanmaku(data);
                })
                .catch(function () {})
                .then(function () {
                    if (!dmStopped) {
                        dmChain.renew(myGen, 2000, poll);
                    }
                });
        });
    }
    function stopDanmakuPolling() {
        dmStopped = true;
        dmChain.halt();
    }

    // 时间戳（epoch 秒）→ HH:MM:SS
    function dmFmtTime(ts) {
        var n = Number(ts);
        if (isNaN(n)) return '';
        var d = new Date(n * 1000);
        function p(x) { return (x < 10 ? '0' : '') + x; }
        return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
    }

    // 单条消息 → 行 HTML（全量 esc() 转义；礼物/SC 高亮；采样折叠计数后缀）
    function dmLineHtml(m) {
        if (m.type === 'sys') {
            return '<span class="dm-line dm-dropped">[' + dmFmtTime(m.ts) + '] ' + esc(m.text) + '</span>';
        }
        var cls = m.type === 'gift' ? ' dm-gift' : (m.type === 'superChat' ? ' dm-sc' : '');
        var label = m.type === 'gift' ? t('danmaku.gift') : (m.type === 'superChat' ? t('danmaku.sc') : '');
        // M-23：dropped 也必须过 esc()。它是本函数唯一的裸插值，违反「拼接路径一律转义」不变量；后端
        // 当前把折叠计数写成 int、现网不可利用，但契约一变（改成带标记的可读串或服务端文案）这里就是
        // 弹幕流里的存储型注入点。选 esc() 而非 parseInt：后者会把「12 条」这类文案静默截成 12。
        var dropped = m.dropped ? ' <span class="dm-dropped">(+' + esc(m.dropped) + t('danmaku.dropped') + '</span>' : '';
        var userPart = m.user ? '<span class="dm-user">' + esc(m.user) + '</span>: ' : '';
        return '<span class="dm-line' + cls + '">[' + dmFmtTime(m.ts) + '] <span class="dm-room">['
            + esc(m.room) + ']</span> ' + label + userPart + esc(m.text) + dropped + '</span>';
    }

    // 全量重绘弹幕流（按当前筛选），保持底部跟随（用户上滚时不打扰）
    function dmRenderStream() {
        var el = $('danmaku-stream');
        if (!el) return;
        var filter = $('danmaku-room-filter') ? $('danmaku-room-filter').value : '';
        var nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
        var html = '';
        var shown = 0;
        for (var i = 0; i < dmMessages.length; i++) {
            var m = dmMessages[i];
            if (filter && m.room !== filter) continue;
            html += dmLineHtml(m);
            shown++;
        }
        if (!shown) {
            // F-21：有消息但筛选不匹配时给出明确「无匹配」提示，而不是清空区域——否则用户分不清
            // 「筛选选错了」和「真的没弹幕」，只能逐个切换筛选去试。
            el.textContent = dmMessages.length ? t('danmaku.noMatch') : t('danmaku.noData');
            return;
        }
        el.innerHTML = html;
        if (nearBottom) {
            el.scrollTop = el.scrollHeight;
        }
    }

    // 渲染一次 /api/danmaku 响应：房间表 + 筛选下拉 + 增量消息
    function renderDanmaku(data) {
        if (!data) data = {};
        // SEV-2228 后半：/api/danmaku 采样失败时后端回 HTTP 200 + 空 rooms/messages、last_seq 等于原
        // since、error:"danmaku_unavailable"。若照常渲染，空 rooms 会把房间表刷成「暂无监控数据」、筛选
        // 下拉重建为只剩「全部房间」并丢掉当前选择。故保留上一轮的表与缓冲、只在消息流上说明取不到，
        // 也不推进游标（last_seq 本就等于 since，推进反而会跳过失败期间的消息）。
        if (data.error === 'danmaku_unavailable') {
            var streamEl = $('danmaku-stream');
            if (streamEl) streamEl.textContent = t('danmaku.unavailable');
            return;
        }
        var rooms = data.rooms || [];
        var tbody = $('danmaku-rooms-tbody');
        if (tbody) {
            if (!rooms.length) {
                tbody.innerHTML = '<tr><td colspan="8" class="empty">' + esc(t('danmaku.emptyRooms')) + '</td></tr>';
            } else {
                var html = '';
                for (var i = 0; i < rooms.length; i++) {
                    var r = rooms[i];
                    var st = r.connected
                        ? '<span class="dm-status-on">' + esc(t('danmaku.connected')) + '</span>'
                        : '<span class="dm-status-off">' + esc(t('danmaku.disconnected')) + '</span>';
                    html += '<tr>'
                        + '<td>' + esc(r.name) + '</td>'
                        + '<td>' + esc(r.platform) + '</td>'
                        + '<td>' + st + '</td>'
                        + '<td>' + esc(r.msg_total) + '</td>'
                        + '<td>' + esc(r.msg_rate) + '</td>'
                        + '<td>' + esc(r.gift_total) + '</td>'
                        + '<td>' + esc(r.online) + '</td>'
                        + '<td>' + esc(r.started_at) + '</td>'
                        + '</tr>';
                }
                tbody.innerHTML = html;
            }
        }
        var hint = $('danmaku-hint');
        if (hint) {
            if (rooms.length) {
                hint.classList.add('hidden');
            } else {
                hint.classList.remove('hidden');
            }
        }
        // 房间筛选下拉：保留当前选择，选项随房间列表刷新。M-19：只在 option 集合本身变化时才重建
        // innerHTML——浏览器在 option 集合被替换时会收起已展开的下拉，而轮询 2s 一轮，用户几乎没机会完成
        // 选择。比较用「上一次写入的串原文」而非读 DOM 现值：真实浏览器会归一化 innerHTML，拿生成串比
        // DOM 现值会恒不等、退回每轮重建。串里已含 allRooms 标签，故切换语言必判为变化、照常重建一次
        // （「全部房间」不会冻结在旧语言）。重建后仍按原口径把选中项复位（房间消失则回落「全部房间」）。
        var sel = $('danmaku-room-filter');
        if (sel) {
            var cur = sel.value;
            var opts = '<option value="">' + esc(t('danmaku.allRooms')) + '</option>';
            for (var j = 0; j < rooms.length; j++) {
                opts += '<option value="' + esc(rooms[j].name) + '">' + esc(rooms[j].name) + '</option>';
            }
            if (opts !== dmRoomFilterOpts) {
                sel.innerHTML = opts;
                dmRoomFilterOpts = opts;
                var found = false;
                for (var k = 0; k < sel.options.length; k++) {
                    if (sel.options[k].value === cur) { found = true; break; }
                }
                sel.value = found ? cur : '';
            }
        }
        // 增量消息：追加到本地缓冲（截断标记说明中间有遗漏，补一条提示行）
        var msgs = data.messages || [];
        if (data.truncated) {
            dmMessages.push({ ts: msgs.length ? msgs[0].ts : Date.now() / 1000, room: '', type: 'sys', user: '', text: t('danmaku.truncated') });
        }
        for (var x = 0; x < msgs.length; x++) {
            dmMessages.push(msgs[x]);
        }
        if (dmMessages.length > DM_MAX_MESSAGES) {
            dmMessages = dmMessages.slice(-DM_MAX_MESSAGES);
        }
        var lastSeq = Number(data.last_seq);
        if (!isNaN(lastSeq) && lastSeq > dmLastSeq) {
            dmLastSeq = lastSeq;
        }
        dmRenderStream();
    }

    // 14. loadRooms —— GET /api/rooms 拉全量直播间，按 enabled 渲染开关、按 recording 渲染录制中；
    // 行内开关/删除按钮靠 data-url 透传，由 rooms-tbody 的事件委托转发 toggleRoom/deleteRoom；画质列为
    // 行内下拉（选项 = 默认画质 + qualityOptions + 当前值兜底）。url 拼进 data-url 与 title 前已 esc()；
    // 删除失败会回拉一次列表恢复 UI。
    // M-18 竞态防护：进函数先 halt() 顶一代，await 回来只有在仍是最新一代时才落地 DOM——否则「快速切走
    // 再切回」「addRoom/toggleRoom/changeRoomQuality 成功后各自回拉」会并发两支 GET /api/rooms，先发后到
    // 的那支把 tbody 覆盖回旧列表（用户看到「刚加的房间又消失了」）。catch 分支同样要过代次校验：旧一代的
    // 网络失败不得把新一代刚渲染好的列表打成「加载失败」。
    function buildRoomQualitySelect(url, current) {
        // 当前值可能不在选项列表（如用户已从画质选项中移除该档位），追加为候选项防止显示错位
        var opts = [''].concat(qualityOptions.slice());
        if (current && opts.indexOf(current) < 0) opts.push(current);
        var html = '<select data-action="quality" data-url="' + esc(url) + '">';
        for (var i = 0; i < opts.length; i++) {
            var sel = opts[i] === current ? ' selected' : '';
            var label = opts[i] === '' ? t('rooms.defaultQuality') : opts[i];
            html += '<option value="' + esc(opts[i]) + '"' + sel + '>' + esc(label) + '</option>';
        }
        return html + '</select>';
    }

    async function loadRooms() {
        var tbody = $('rooms-tbody');
        var myGen = roomsChain.halt();
        try {
            var rooms = await api('/api/rooms');
            if (!roomsChain.isCurrent(myGen)) return;
            if (!rooms.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty">' + esc(t('rooms.empty')) + '</td></tr>';
                return;
            }
            var html = '';
            for (var i = 0; i < rooms.length; i++) {
                var r = rooms[i];
                var checked = r.enabled ? ' checked' : '';
                html += '<tr>'
                    + '<td title="' + esc(r.url) + '">' + esc(r.url) + '</td>'
                    + '<td>' + buildRoomQualitySelect(r.url, r.quality) + '</td>'
                    + '<td>' + esc(r.name) + '</td>'
                    + '<td><label class="switch"><input type="checkbox"' + checked
                        + ' data-action="toggle" data-url="' + esc(r.url) + '"><span class="slider"></span></label></td>'
                    + '<td>' + (r.recording ? esc(t('common.yes')) : esc(t('common.no'))) + '</td>'
                    + '<td><button class="danger" data-action="delete" data-url="' + esc(r.url) + '">' + esc(t('rooms.delete')) + '</button></td>'
                    + '</tr>';
            }
            tbody.innerHTML = html;
        } catch (e) {
            if (!roomsChain.isCurrent(myGen)) return;
            tbody.innerHTML = '<tr><td colspan="6" class="empty">' + esc(t('loadFailed')) + '</td></tr>';
        }
    }

    // 14b. 画质选项（WEB 直播间设置的下拉项 + 桌面端画质切换菜单共用一份 config.ini 配置）：
    // qualityBuiltin 与 qualityOptions 的差值即「添加画质」的候选项。增删后 PUT 回写，以后端返回的
    // 规范化列表为准（非法项由后端剔除）。
    async function loadQualityOptions() {
        try {
            var data = await api('/api/rooms/qualities');
            qualityOptions = Array.isArray(data.options) ? data.options.slice() : [];
            qualityBuiltin = Array.isArray(data.builtin) ? data.builtin.slice() : qualityOptions.slice();
            renderQualityOptions();
        } catch (e) {
            toast(t('toast.qualityLoadFailed') + (e.message || ''), 'error');
        }
    }

    // 构建单个 chip：画质名 + 删除按钮（数据经 data-quality 透传，由事件委托处理）
    function buildQualityChip(name) {
        var span = document.createElement('span');
        span.className = 'quality-chip';
        span.appendChild(document.createTextNode(name));
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.setAttribute('data-action', 'remove-quality');
        btn.setAttribute('data-quality', name);
        btn.title = t('rooms.delete');
        btn.textContent = '\u00d7';
        span.appendChild(btn);
        return span;
    }

    // 清空并重建子节点（避免 innerHTML 拼接，画质名一律走 textContent）
    function replaceChildren(node, children) {
        while (node.firstChild) {
            node.removeChild(node.firstChild);
        }
        for (var i = 0; i < children.length; i++) {
            node.appendChild(children[i]);
        }
    }

    // 把当前选项渲染进三处：#room-quality 下拉、#quality-chips 标签、#quality-candidate 候选。
    // 下拉首位恒为「默认画质」（value 为空 = 不写画质段，回落到全局默认画质）。
    function renderQualityOptions() {
        var sel = $('room-quality');
        if (sel) {
            var keep = sel.value;
            var opts = [];
            var defOpt = document.createElement('option');
            defOpt.value = '';
            defOpt.textContent = t('rooms.defaultQuality');
            opts.push(defOpt);
            for (var i = 0; i < qualityOptions.length; i++) {
                var opt = document.createElement('option');
                opt.value = qualityOptions[i];
                opt.textContent = qualityOptions[i];
                opts.push(opt);
            }
            replaceChildren(sel, opts);
            sel.value = keep;
            // 选中项已被移除时 select.value 回落到空串，即「默认画质」
            if (sel.value !== keep) {
                sel.value = '';
            }
        }

        var chips = $('quality-chips');
        if (chips) {
            var chipNodes = [];
            for (var j = 0; j < qualityOptions.length; j++) {
                chipNodes.push(buildQualityChip(qualityOptions[j]));
            }
            replaceChildren(chips, chipNodes);
        }

        var cand = $('quality-candidate');
        if (cand) {
            var left = qualityBuiltin.filter(function (q) { return qualityOptions.indexOf(q) < 0; });
            var candOpts = [];
            if (left.length) {
                for (var k = 0; k < left.length; k++) {
                    var c = document.createElement('option');
                    c.value = left[k];
                    c.textContent = left[k];
                    candOpts.push(c);
                }
            } else {
                var empty = document.createElement('option');
                empty.value = '';
                empty.textContent = t('rooms.qualityEmpty');
                candOpts.push(empty);
            }
            replaceChildren(cand, candOpts);
            cand.disabled = !left.length;
            var addBtn = $('quality-add-btn');
            if (addBtn) {
                addBtn.disabled = !left.length;
            }
        }
    }

    // 增删后统一走这里回写：PUT 成功后以后端返回的规范化列表为准（非法项会被后端剔除）
    async function saveQualityOptions(next) {
        try {
            var data = await api('/api/rooms/qualities', { method: 'PUT', body: { options: next } });
            qualityOptions = Array.isArray(data.options) ? data.options.slice() : next.slice();
            renderQualityOptions();
            return true;
        } catch (e) {
            toast(t('toast.qualitySaveFailed') + (e.message || ''), 'error');
            return false;
        }
    }

    // 添加画质：把候选下拉选中的档位并入选项列表（后端会去重并剔除非法项）
    async function addQualityOption() {
        var cand = $('quality-candidate');
        if (!cand || !cand.value) {
            return;
        }
        var picked = cand.value;
        if (await saveQualityOptions(qualityOptions.concat([picked]))) {
            toast(t('toast.qualityAdded'), 'success');
        }
    }

    // 移除画质：从选项列表剔除；若该项正被下拉选中，renderQualityOptions 会回落到默认画质
    async function removeQualityOption(name) {
        var next = qualityOptions.filter(function (q) { return q !== name; });
        if (await saveQualityOptions(next)) {
            toast(t('toast.qualityRemoved'), 'success');
        }
    }

    // 15. window.toggleRoom
    // M-88②：本文件所有 toast 拼接一律走 (e.message || '') 兜底形态——e 不是 Error（被 reject 的
    // 字符串/对象、或刻意 throw 的非标准值）时 e.message 为 undefined，直拼会把「undefined」显示给用户。
    window.toggleRoom = async function (url, enable) {
        try {
            await api('/api/rooms/toggle', { method: 'POST', body: { url: url, enable: enable } });
            toast(enable ? t('toast.enabled') : t('toast.disabled'), 'success');
        } catch (e) {
            toast(t('toast.opFailed') + (e.message || ''), 'error');
            loadRooms();
        }
    };

    // 16. window.deleteRoom
    window.deleteRoom = async function (url) {
        if (!confirm(t('rooms.deleteConfirm'))) return;
        try {
            await api('/api/rooms?url=' + encodeURIComponent(url), { method: 'DELETE' });
            toast(t('toast.deleted'), 'success');
            loadRooms();
        } catch (e) {
            toast(t('toast.deleteFailed') + (e.message || ''), 'error');
        }
    };

    // 16b. changeRoomQuality —— PUT /api/rooms/quality 按房间切换画质（与桌面端画质监控共用
    // URL_config.ini 画质段，下一轮检测循环生效）。失败回拉列表恢复下拉显示值。
    async function changeRoomQuality(url, quality) {
        try {
            await api('/api/rooms/quality', { method: 'PUT', body: { url: url, quality: quality || null } });
            toast(quality ? t('toast.qualityChanged').replace('{q}', quality) : t('toast.qualityReset'), 'success');
            loadRooms();
        } catch (e) {
            toast(t('toast.qualityChangeFailed') + (e.message || ''), 'error');
            loadRooms();
        }
    }

    // 17. loadConfig —— GET /api/config 取 {section:{key:value}}，逐段逐键渲染为 input（敏感项用
    // password 类型、废弃旧键只读置灰、HTTPS 键与 SSL 平台列表键附动态提示）。渲染后把整份配置深拷贝进
    // configBackup，供 saveConfig 做「仅提交变更键」的 diff。
    // SSL/HTTPS 整合：「是否启用https录制」合并了原「是否强制启用https录制」与「是否禁用SSL证书验证
    // (是/否)」——开启 = https 拉流并跳过证书校验，关闭 = http 拉流并恢复默认证书校验；旧键只读置灰并
    // 明示整合去向。FFmpeg 9.0 起 TLS 验证默认开启，故「禁用SSL证书验证的平台」只在 HTTP 模式生效，
    // HTTPS 模式已全局跳过、该列表冗余（后端同一口径见 src/http_config.py::get_effective_ssl_verify）。
    var HTTPS_RECORD_KEY = '是否启用https录制';
    var DEPRECATED_CONFIG_KEYS = {
        '是否强制启用https录制': 'config.deprecated',
        '是否禁用SSL证书验证(是/否)': 'config.deprecated',
        '虎牙是否禁用SSL证书验证(是/否)': 'config.deprecated'
    };
    var SSL_PLATFORM_KEY = '禁用SSL证书验证的平台(逗号分隔)';

    // 布尔配置值 token 集，与后端 src/config_bool.py 的 TRUE_TOKENS/FALSE_TOKENS 同一口径（比较前 trim +
    // 小写），两份集合必须同步改：跨语言相等性由 tests/frontend/test_quality_ui.mjs 的 MID-2263 逐 token
    // 双向断言，读取侧一律经 parseConfigBool 解析。
    // [历史注 SEV-2210] 旧实现只比较「是」，用户按界面提示把值改成 true/false 后开关判定会静默翻转。
    var CONFIG_TRUE_TOKENS = { '是': 1, 'true': 1, 't': 1, 'yes': 1, 'y': 1, 'on': 1, '1': 1 };
    var CONFIG_FALSE_TOKENS = { '否': 1, 'false': 1, 'f': 1, 'no': 1, 'n': 1, 'off': 1, '0': 1 };

    function parseConfigBool(raw, fallback) {
        var token = (raw === null || raw === undefined) ? '' : String(raw).trim().toLowerCase();
        if (Object.prototype.hasOwnProperty.call(CONFIG_TRUE_TOKENS, token)) return true;
        if (Object.prototype.hasOwnProperty.call(CONFIG_FALSE_TOKENS, token)) return false;
        return fallback;
    }

    function httpsRecordingEnabled() {
        var inputs = document.querySelectorAll('#config-container input');
        for (var i = 0; i < inputs.length; i++) {
            if (inputs[i].getAttribute('data-key') === HTTPS_RECORD_KEY) {
                return parseConfigBool(inputs[i].value, false);
            }
        }
        return false;
    }

    function updateSslPlatformHint() {
        var hint = $('ssl-platform-hint');
        if (!hint) return;
        var enabled = httpsRecordingEnabled();
        // HTTPS 模式：全局跳过校验，列表冗余；HTTP 模式（FFmpeg 9.0 默认校验）：列表生效
        hint.textContent = enabled ? t('config.hint.sslOn') : t('config.hint.sslOff');
        hint.className = 'config-hint ' + (enabled ? 'hint-on' : 'hint-off');
    }

    async function loadConfig() {
        var container = $('config-container');
        // M-18：与 loadRooms 同一代次判据（机制说明见状态区 roomsChain 处）。
        // 本条额外要紧的是「未保存修改」：saveConfig 失败分支会 await loadConfig() 回拉服务端真值，
        // 用户也可能在保存回拉尚未落地时又切走/切回配置页；两支 GET /api/config 乱序落地时，
        // 旧一代那份 HTML 会把新一代（含用户已填的框）整体覆盖掉。
        var myGen = configChain.halt();
        try {
            var cfg = await api('/api/config');
            if (!configChain.isCurrent(myGen)) return;
            configBackup = JSON.parse(JSON.stringify(cfg));
            var html = '';
            for (var section in cfg) {
                if (!cfg.hasOwnProperty(section)) continue;
                html += '<div class="config-group"><h4>[' + esc(section) + ']</h4>';
                var items = cfg[section];
                for (var key in items) {
                    if (!items.hasOwnProperty(key)) continue;
                    var val = items[key];
                    // 值形态命中时同样按敏感字段渲染（password 框，不明文展示）
                    var inputType = (isSensitiveField(section, key) || isSensitiveValue(val)) ? 'password' : 'text';
                    // 后端把敏感项回显为掩码 '***'，渲染时打标，供 saveConfig 判定
                    // 「这个框留空 = 用户要清空真实凭据」而不是「用户把值改成了空串」。
                    var masked = String(val).trim() === SENSITIVE_MASK;
                    var hintHtml = '';
                    var rowClass = 'config-row';
                    var readOnly = '';
                    if (DEPRECATED_CONFIG_KEYS.hasOwnProperty(key)) {
                        // 废弃键：只读置灰，提示整合去向，防止误改无效配置
                        rowClass += ' row-deprecated';
                        readOnly = ' readonly';
                        hintHtml = '<div class="config-hint hint-off">' + esc(t(DEPRECATED_CONFIG_KEYS[key])) + '</div>';
                    } else if (key === HTTPS_RECORD_KEY) {
                        hintHtml = '<div class="config-hint">' + esc(t('config.hint.https')) + '</div>';
                    } else if (key === SSL_PLATFORM_KEY) {
                        hintHtml = '<div class="config-hint" id="ssl-platform-hint"></div>';
                    }
                    if (masked) {
                        hintHtml += '<div class="config-hint hint-masked">' + esc(t('config.hint.masked')) + '</div>';
                    }
                    html += '<div class="' + rowClass + '">'
                        + '<label>' + esc(key) + '</label>'
                        + '<input type="' + inputType + '" data-section="' + esc(section) + '"'
                        + ' data-key="' + esc(key) + '" value="' + esc(val) + '"'
                        + (masked ? ' data-masked="1"' : '') + readOnly + '>'
                        + hintHtml
                        + '</div>';
                }
                html += '</div>';
            }
            container.innerHTML = html || t('config.none');
            updateSslPlatformHint();
            var inputs = document.querySelectorAll('#config-container input');
            for (var j = 0; j < inputs.length; j++) {
                if (inputs[j].getAttribute('data-key') === HTTPS_RECORD_KEY) {
                    inputs[j].addEventListener('input', updateSslPlatformHint);
                }
            }
        } catch (e) {
            // M-18：旧一代的失败不得覆盖新一代已渲染的表单（同 loadRooms 的 catch 口径）
            if (!configChain.isCurrent(myGen)) return;
            container.textContent = t('loadFailed');
        }
    }

    // 18. saveConfig
    // 提交口径三条（缺一不可，MID-37）：
    //   ① 原样提交掩码 *** → 视为未改动直接跳过（**写入侧唯一防线**，不得移除：否则掩码会覆盖真实凭据）；
    //   ② 掩码字段被改成空串 → 必须经显式确认才提交（否则一次全选删除就静默抹掉 cookie/token，而
    //      backup_config 副本本身已脱敏，没有回滚路径）；服务端此时也会回 400 兜底（见
    //      src/web_api.py::update_config，其 detail 须原样显示给用户）；
    //   ③ 单项写入失败即中止后续写入（半份配置落盘比整体失败更难排查），400 单独给「服务端拒绝」文案。
    // MIN-2239 配套：标记失败行，并在回拉前统计还有多少行「改了没提交」；两者都只依赖 DOM 结构
    // （input 的 data-section/data-key 与 configBackup 快照），不引入新状态。
    function markRowFailed(inp) {
        var row = inp.closest ? inp.closest('.config-row') : null;
        if (!row) return;
        row.classList.add('row-failed');
        inp.setAttribute('aria-invalid', 'true');
    }

    // MIN-2239 配套：常驻状态行（#config-save-status）。传空串即隐藏。
    // 用它而不是 toast 的理由：toast 是单槽位且会自动消失，无法承担「配置与磁盘不一致」的持续提醒。
    function showSaveStatus(text) {
        var el = $('config-save-status');
        if (!el) return;
        if (text) {
            el.textContent = text;
            el.classList.remove('hidden');
        } else {
            el.textContent = '';
            el.classList.add('hidden');
        }
    }

    // 统计第 from 行起仍与快照不一致的行数，用于失败提示里的「第 m 项失败」：返回值不含当前失败行，
    // 故 m = pending + 1。掩码行不算脏（它本就不提交，与 saveConfig 的口径 ① 同源）。
    function countRemainingDirty(inputs, from) {
        var n = 0;
        for (var j = from; j < inputs.length; j++) {
            var it = inputs[j];
            if (it.value === SENSITIVE_MASK) continue;
            var sec = it.getAttribute('data-section');
            var k = it.getAttribute('data-key');
            var old = (configBackup && configBackup[sec]) ? configBackup[sec][k] : undefined;
            if (it.value !== old) n++;
        }
        return n;
    }

    // 18b. M-22：认证复验口令的采集弹窗，替代原 window.prompt——后者明文回显（本文件其它口令形态都是
    // type="password"）、无法指定 type/autocomplete（口令会进自动填充与历史候选）、且同步阻塞 UI 线程。
    // 形态：index.html 的静态节点 #reauth-modal（type="password" + autocomplete="off"）+ .modal-* 遮罩。
    // 本面板没有对话框组件，登录卡片/告警横幅都是「静态节点 + .hidden 切换」，沿用同一形态，也不在运行时
    // createElement（那会让前端 .mjs 沙箱用例无法驱动）。
    // 出口一律经 _settleReauth 收敛：确认取走输入值、取消/Esc/点遮罩回空串，四个出口都立刻清空输入节点
    // 并重新挂上 .hidden（口令不残留在隐藏视图里）。空串 = 放弃本次认证改动。
    // 开窗期间必须禁用 #config-save-btn：window.prompt 是阻塞的、第二次点击进不来；换成非阻塞弹窗后
    // saveConfig 可被重复进入，两条链会各自走到这里互相作废 resolver（上一轮被以空串结算 → 那一轮认证键
    // 被跳过），口令不外泄但界面会显示「改成功了却没生效」，故在源头关掉重入入口。
    // 后端契约（src/web_api.py::update_config 的 MID-2241 段）：认证当前开启时，写 [Web] web_auth_enable /
    // web_password 必须带能过 verify_web_password 的 reauth_password，否则 403；故空串在前端就地跳过，
    // 不去撞 403。认证**当前关闭**时后端不做该判定，前端也就不采口令——否则第一次启用认证的人没有旧口令
    // 可填，会被本窗口死锁。
    var _reauthResolver = null;

    function _settleReauth(value) {
        var input = $('reauth-password');
        var modal = $('reauth-modal');
        // 先清 DOM、再放行调用方：resolver 一返回，saveConfig 立刻把原文拼进请求体，
        // 此时弹窗已不可见、输入框里不应再留有任何字符。
        if (input) input.value = '';
        if (modal) modal.classList.add('hidden');
        var saveBtn = $('config-save-btn');
        if (saveBtn) saveBtn.disabled = false;
        var resolve = _reauthResolver;
        _reauthResolver = null;
        if (resolve) resolve(value || '');
    }

    // 打开口令窗并等待用户输入；labelText 由调用方传入（t('config.authChangeReauth')），
    // 使「本次要复验的是什么」与调用点保持同源，弹窗自身不猜文案。
    function askReauthPassword(labelText) {
        return new Promise(function (resolve) {
            var modal = $('reauth-modal');
            var input = $('reauth-password');
            // 弹窗节点缺失（HTML 被裁剪/换用旧模板）时按「放弃认证改动」处理：
            // 拿不到复验口令的 PUT 必然 403，不如在这里就不提交，绝不把空 reauth 发出去。
            if (!modal || !input) {
                resolve('');
                return;
            }
            // saveConfig 是串行 await 的，理论上不会有上一轮还没结算；真出现（异常路径）就先作废它，
            // 避免两个等待方互相覆盖 resolver 导致其中一条 Promise 永不落地。
            if (_reauthResolver) _settleReauth('');
            var label = $('reauth-modal-label');
            if (label) label.textContent = labelText || t('config.authChangeReauth');
            input.value = '';
            var saveBtn = $('config-save-btn');
            if (saveBtn) saveBtn.disabled = true;
            modal.classList.remove('hidden');
            _reauthResolver = resolve;
            // 桩化 DOM（tests/frontend/*.mjs 的 node:vm 沙箱）不建模 focus，判空后再调
            if (input.focus) input.focus();
        });
    }

    async function saveConfig() {
        var inputs = document.querySelectorAll('#config-container input');
        var count = 0;
        var skippedBlank = 0;
        var skippedAuth = 0;
        // M-22：复验口令是本轮局部状态——authAsked 记录本轮是否已弹过窗（两个认证键共用一次输入，用户
        // 不必为「关认证 + 改口令」输两遍当前口令），authReauth 是采集到的原文（'' = 取消/留空 = 放弃）。
        // 口令只能挂在认证两键的请求上：先前用循环外的一个变量，认证行赋值之后每个键的 PUT 都会捎带
        // reauth_password（代理日志/扩展/抓包都能记下）。其余请求的 body 必须与改动前逐字段一致。
        var authAsked = false;
        var authReauth = '';
        for (var i = 0; i < inputs.length; i++) {
            var inp = inputs[i];
            var section = inp.getAttribute('data-section');
            var key = inp.getAttribute('data-key');
            var newVal = inp.value;
            if (newVal === SENSITIVE_MASK) continue;
            var masked = inp.getAttribute('data-masked') === '1';
            if (masked && !newVal.trim()) {
                if (!confirm(t('config.clearSecretConfirm').replace('{k}', String(key)))) {
                    skippedBlank++;
                    continue;
                }
            }
            var oldVal = (configBackup && configBackup[section]) ? configBackup[section][key] : undefined;
            if (newVal === oldVal) continue;
            // MID-2241：web_auth_enable / web_password 原本走普通写入通道、零二次确认——一次 PUT 即可关掉
            // 认证（回环监听下 SEV-04 不拦）或改口令（连带清空全部 token），且该降级在 token 吊销后依然留存。
            // 故先点明后果要确认；未确认即跳过并计入 skippedAuth，末尾单独提示（不静默吞掉）。
            var isAuthKey = section === 'Web' && (key === 'web_auth_enable' || key === 'web_password');
            if (isAuthKey) {
                if (!confirm(t('config.authChangeConfirm').replace('{k}', String(key)))) {
                    skippedAuth++;
                    continue;
                }
                // 后端据 reauth_password 做准入判定（src/web_api.py::update_config 的 MID-2241 段）：认证
                // 当前开启时，这两个键不带可验过的口令即 403。故 confirm + 口令窗只挡手滑，不是唯一防线。
                // 采集判据必须与后端同一条：只判 configBackup（服务端真值快照）里认证**当前是否开启**——
                // 认证关闭时面板对任何能访问端口的人都全开、没有可信的「当前口令」可验，强复验会把「按提示
                // 收紧配置」打死。布尔解析走 parseConfigBool（与后端 config_bool 同 token 集合）。
                var authRecheckRequired = parseConfigBool(
                    (configBackup && configBackup.Web) ? configBackup.Web.web_auth_enable : '', false
                );
                if (authRecheckRequired) {
                    if (!authAsked) {
                        authAsked = true;
                        authReauth = await askReauthPassword(t('config.authChangeReauth'));
                    }
                    if (!authReauth) {
                        skippedAuth++;
                        continue;
                    }
                }
            }
            try {
                // 只在认证两键被确认后才附加 reauth_password：判据是「这一行本身就是认证键」，不能用
                // 「口令非空」——后者会让口令捎带到后续每个键的请求上，而既有回归锁按整体 deepEqual 断言
                // body 形状，键集合没变时锁不住这种多余字段（由 test_auth_reauth.mjs 逐请求断言）。
                var body = { section: section, key: key, value: newVal };
                if (isAuthKey && authReauth) body.reauth_password = authReauth;
                await api('/api/config', {
                    method: 'PUT',
                    body: body,
                });
                count++;
            } catch (e) {
                if (e.status === 400) {
                    toast(t('config.saveRejected') + (e.message || ''), 'error');
                } else {
                    toast(t('toast.saveFailed') + (e.message || ''), 'error');
                }
                // MIN-2239：不能在这里直接 return 就算完——失败行之后的输入仍保持用户填的值、无任何未保存
                // 标记，configBackup 也停在保存前快照，用户看到「配置页还是我填的样子」就会以为已生效。故：
                // 失败行标红 + #config-save-status 常驻明细（已应用 n / 第 m 项失败 / 其余未提交）+ 回拉服务端
                // 真值。不额外 toast：400 与非 400 的文案各有回归锁，且 toast 承担不了常驻提醒。
                markRowFailed(inp);
                var pending = countRemainingDirty(inputs, i + 1);
                showSaveStatus(t('config.partialSaved').replace('{n}', String(count)).replace('{m}', String(pending + 1)));
                try {
                    await loadConfig();
                } catch (e2) { /* 回拉失败：保留行标红，至少不谎报已保存 */ }
                return;
            }
        }
        // 全部提交成功（含「无可提交项」）：清掉上一轮的常驻失败明细
        showSaveStatus('');
        if (count > 0) {
            toast(t('config.saved').replace('{n}', String(count)), 'success');
        } else if (skippedAuth > 0) {
            // MID-2241：认证键被取消确认时优先报这条——关认证/改口令是能力降级，比「有一项没动」更需要被看见
            toast(t('config.authChangeSkipped').replace('{n}', String(skippedAuth)), 'info');
        } else if (skippedBlank > 0) {
            toast(t('config.secretSkipped').replace('{n}', String(skippedBlank)), 'info');
        } else {
            toast(t('config.noChanges'), 'info');
        }
        try {
            await loadConfig();
        } catch (e) {
            toast(t('toast.saveFailed') + (e.message || ''), 'error');
        }
    }

    // 19. loadFiles —— GET /api/files?path=，按路径取目录项渲染表格，并据 path 切分重构面包屑（根目录 +
    // 逐级累积路径）。dir 行「进入」/file 行「下载」按钮经事件委托转发 loadFiles/downloadFile；path 经
    // encodeURIComponent 编码，防分隔符/中文破坏路由。
    // M-18：本条是三条按需链里竞态最显眼的一支——连点「进入」/面包屑或「下钻后立即点上级」会并发两支
    // GET /api/files，先发后到的旧响应把面包屑与 tbody **整体**覆盖回上一级（两者必须同源落地，否则
    // 面包屑停在 A 而表格是 B 更糟）。代次判据同 loadRooms（机制见状态区 roomsChain 处）。
    async function loadFiles(path) {
        path = path || '';
        var myGen = filesChain.halt();
        var tbody = $('files-tbody');
        var crumb = $('file-breadcrumb');
        try {
            var items = await api('/api/files?path=' + encodeURIComponent(path));
            if (!filesChain.isCurrent(myGen)) return;
            // 面包屑：根目录 + 逐级路径
            var crumbHtml = '';
            crumbHtml += '<a data-path="">' + esc(t('files.root')) + '</a>';
            var parts = path ? path.split('/') : [];
            var cumul = '';
            for (var i = 0; i < parts.length; i++) {
                var p = parts[i];
                if (!p) continue;
                cumul = cumul ? cumul + '/' + p : p;
                crumbHtml += ' / <a data-path="' + esc(cumul) + '">' + esc(p) + '</a>';
            }
            crumb.innerHTML = crumbHtml;
            // 文件列表
            if (!items.length) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty">' + esc(t('files.emptyDir')) + '</td></tr>';
                return;
            }
            var html = '';
            for (var j = 0; j < items.length; j++) {
                var it = items[j];
                var icon = it.type === 'dir' ? '📁' : '📄';
                var action;
                if (it.type === 'dir') {
                    action = '<button class="small" data-action="enter" data-path="' + esc(it.path) + '">' + esc(t('rooms.enter')) + '</button>';
                } else {
                    action = '<button class="small" data-action="download" data-path="' + esc(it.path) + '">' + esc(t('rooms.download')) + '</button>';
                }
                html += '<tr>'
                    + '<td>' + icon + ' ' + esc(it.name) + '</td>'
                    + '<td>' + esc(it.type) + '</td>'
                    + '<td>' + (it.type === 'file' ? fmtSize(it.size) : '-') + '</td>'
                    + '<td>' + fmtTime(it.mtime) + '</td>'
                    + '<td>' + action + '</td>'
                    + '</tr>';
            }
            tbody.innerHTML = html;
        } catch (e) {
            if (!filesChain.isCurrent(myGen)) return;
            tbody.innerHTML = '<tr><td colspan="5" class="empty">' + esc(t('loadFailed')) + '</td></tr>';
        }
    }
    window.loadFiles = loadFiles;

    // 19b. downloadFile —— 走认证头拉二进制并触发下载（I1）：直接 fetch + .blob()，不经过 api()（它返回
    // res.text()，会破坏二进制）。MIN-2238：失败分支不得用 res.statusText——现代浏览器（HTTP/2 下连
    // reason phrase 都不再收到）对 statusText 恒给空串，toast 只能渲染成「下载失败: 」。改用 apiError 解析
    // 错误体的 detail（成功分支仍是 blob）。
    // M-88①：裸 fetch 在后端挂起（或大文件迟迟不响应）时请求无限 pending，同文件 api() 已有
    // API_TIMEOUT_MS + AbortController 的超时形态。这里复用同一形状：定时器只覆盖「响应头未到」阶段，
    // 拿到 res 立即 clearTimeout，随后的 blob 读取不受这层超时掐断（大文件仍然能下完）。
    window.downloadFile = function (path) {
        var headers = {};
        var token = getToken();
        if (token) headers['Authorization'] = 'Bearer ' + token;
        var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
        var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, API_TIMEOUT_MS) : null;
        fetch('/api/files/download?path=' + encodeURIComponent(path), {
            headers: headers,
            signal: ctrl ? ctrl.signal : undefined,
        })
            .then(function (res) {
                if (timer) {
                    clearTimeout(timer);
                    timer = null;
                }
                if (res.status === 401) {
                    setToken('');
                    showLogin();
                    throw new Error(t('toast.loginExpired'));
                }
                if (!res.ok) {
                    return res.text().then(function (text) {
                        throw apiError(res.status, text, '/api/files/download', t('toast.downloadFailed'));
                    });
                }
                return res.blob();
            })
            .then(function (blob) {
                var a = document.createElement('a');
                var url = URL.createObjectURL(blob);
                a.href = url;
                a.download = path.split('/').pop() || 'download';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            })
            .catch(function (e) {
                // 响应头阶段之后出的错（blob 读取、DOM 触发下载）都已不该再有定时器，兜底判空
                if (timer) clearTimeout(timer);
                // 超时中止的 Error 名是 AbortError、message 由浏览器给出，对用户没有信息量，
                // 统一成与 api() 同口径的 'timeout' 信号（M-88②：message 为空时不得显示 undefined）。
                var detail = e && e.name === 'AbortError' ? 'timeout' : (e && e.message || '');
                toast(t('toast.downloadFailed') + detail, 'error');
            });
    };

    // 20. addRoom（room-add-form submit 处理）
    async function addRoom() {
        var url = $('room-url').value.trim();
        var quality = $('room-quality').value;
        var name = $('room-name').value.trim();
        if (!url) {
            toast(t('toast.urlRequired'), 'error');
            return;
        }
        try {
            await api('/api/rooms', {
                method: 'POST',
                body: {
                    url: url,
                    quality: quality || null,
                    name: name || null,
                },
            });
            toast(t('toast.added'), 'success');
            $('room-url').value = '';
            $('room-quality').value = '';
            $('room-name').value = '';
            loadRooms();
        } catch (e) {
            toast(t('toast.addFailed') + (e.message || ''), 'error');
        }
    }

    // 21. uploadIcon —— 选择本地 .ico → FileReader 读成 base64 → POST /api/icon。
    // [为什么是 base64 JSON 而不是 FormData] python-multipart 已不在依赖清单里（Starlette 只在
    // Request.form() 内部 import 它），后端没有 multipart 解析面，走 FormData 会得到一个 500 而
    // 不是「不支持」；base64 方案零新依赖，且「体积上限」能在前端先粗筛一次（超过上限就不必上传）。
    async function uploadIcon(file) {
        var link = $('favicon-link');
        if (file.size > 512 * 1024) {
            toast(t('icon.err.too_large'), 'error');
            return;
        }
        var dataUrl;
        try {
            dataUrl = await new Promise(function (resolve, reject) {
                var reader = new FileReader();
                reader.onload = function () { resolve(String(reader.result || '')); };
                reader.onerror = function () { reject(new Error('read')); };
                reader.readAsDataURL(file);
            });
        } catch (e) {
            toast(t('icon.readFailed'), 'error');
            return;
        }
        // 剥掉 `data:image/x-icon;base64,` 前缀：留着它后端 b64decode(validate=True) 会拒，
        // 但报错只能到「不是合法 base64」这一层，看不出是前缀没剥。
        var comma = dataUrl.indexOf(',');
        var payload = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
        try {
            var res = await api('/api/icon', { method: 'POST', body: { name: file.name, data: payload } });
            if (res && res.code === 'no_app_size') toast(t('icon.no_app_size'), 'info');
            // 破缓存：favicon 的缓存极顽固，不带时间戳的换图标在多数浏览器上要等清缓存才可见
            if (link) link.href = '/favicon.ico?t=' + Date.now();
            toast(t('icon.ok'), 'success');
        } catch (e) {
            var msg = e && e.message ? String(e.message) : '';
            // 后端 detail 就是机器码：命中已知码就翻成本地文案，否则原样兜底（如 401 的 unauthorized）
            var known = Object.prototype.hasOwnProperty.call(I18N.zh_CN, 'icon.err.' + msg);
            toast(known ? t('icon.err.' + msg) : t('icon.fail') + msg, 'error');
        }
    }

    // 22. initTheme
    function initTheme() {
        // 它是 DOMContentLoaded 的第一条语句，任何异常都会让后续所有监听器注册被跳过（面板变静态页）。
        try {
            var theme = safeGetItem(THEME_KEY) || 'light';
            document.body.dataset.theme = theme;
            var btn = $('theme-toggle');
            if (btn) btn.textContent = theme === 'light' ? '🌙' : '☀️';
        } catch (e) {
            if (typeof console !== 'undefined' && console.warn) console.warn('[theme] init failed', e);
        }
    }

    // 22. toggleTheme
    function toggleTheme() {
        var cur = document.body.dataset.theme === 'dark' ? 'dark' : 'light';
        var next = cur === 'dark' ? 'light' : 'dark';
        document.body.dataset.theme = next;
        safeSetItem(THEME_KEY, next);
        var btn = $('theme-toggle');
        if (btn) btn.textContent = next === 'light' ? '🌙' : '☀️';
    }

    // 23. DOMContentLoaded init
    document.addEventListener('DOMContentLoaded', function () {
        initTheme();
        initLanguage();

        var tabs = document.querySelectorAll('.tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].addEventListener('click', function () {
                showView(this.getAttribute('data-view'));
            });
        }
        $('theme-toggle').addEventListener('click', toggleTheme);
        $('recording-start-btn').addEventListener('click', function () { toggleRecording(true); });
        $('recording-stop-btn').addEventListener('click', function () { toggleRecording(false); });
        $('login-submit').addEventListener('click', doLogin);
        $('login-password').addEventListener('keypress', function (e) {
            if (e.key === 'Enter' || e.keyCode === 13) {
                doLogin();
            }
        });
        $('logout-btn').addEventListener('click', function () {
            // WD-09：调服务端注销端点吊销当前 bearer（原实现只清 localStorage，服务端 token 在有效期（默认
            // 24 小时）内依旧完全有效）。注销失败也必须清本地并回到登录页，不能把用户卡在面板里。
            api('/api/logout', { method: 'POST' })
                .catch(function () {})
                .then(function () {
                    setToken('');
                    showLogin();
                });
        });
        $('room-add-form').addEventListener('submit', function (e) {
            e.preventDefault();
            addRoom();
        });
        // 画质选项管理：按钮展开/收起面板，候选下拉 + 添加按钮补选项，chip 上的 × 删选项
        $('quality-manage-btn').addEventListener('click', function () {
            $('quality-manage-panel').classList.toggle('hidden');
        });
        $('quality-add-btn').addEventListener('click', addQualityOption);
        $('quality-chips').addEventListener('click', function (e) {
            var btn = e.target.closest && e.target.closest('button[data-action="remove-quality"]');
            if (btn) {
                removeQualityOption(btn.getAttribute('data-quality'));
            }
        });
        $('config-save-btn').addEventListener('click', saveConfig);
        // 图标导入：按钮只负责唤起隐藏的 file input（accept 已限定 .ico，但用户仍可在系统对话框
        // 里改成「所有文件」，故后端仍独立校验——前端 accept 只是体验，不是防线）。
        var iconBtn = $('icon-import-btn');
        var iconInput = $('icon-file-input');
        if (iconBtn && iconInput) {
            iconBtn.addEventListener('click', function () { iconInput.click(); });
            iconInput.addEventListener('change', function () {
                var picked = iconInput.files && iconInput.files[0];
                // 先取文件再清空 value：不清的话连着选同一个文件不会再触发 change（无反馈的假死）
                iconInput.value = '';
                if (picked) uploadIcon(picked);
            });
        }
        // M-22：口令窗的四个出口全部经 _settleReauth（清空输入节点 + 隐藏弹窗 + 放行 saveConfig），
        // 少绑一个就会把已输入的口令留在隐藏的 #reauth-password 里（轻微项 41 的那类残留）。
        $('reauth-confirm').addEventListener('click', function () {
            var input = $('reauth-password');
            _settleReauth(input ? input.value : '');
        });
        $('reauth-cancel').addEventListener('click', function () {
            _settleReauth('');
        });
        // Enter 提交、Esc 取消：口令窗只有一个输入框，键盘路径必须与鼠标路径同结论
        $('reauth-password').addEventListener('keypress', function (e) {
            if (e.key === 'Enter' || e.keyCode === 13) {
                _settleReauth(e.target ? e.target.value : $('reauth-password').value);
            }
        });
        document.addEventListener('keydown', function (e) {
            if (!_reauthResolver) return;
            if (e.key === 'Escape' || e.keyCode === 27) {
                _settleReauth('');
            }
        });
        // 点遮罩空白处 = 取消（必须判 target 就是遮罩本身：卡片内的任何点击都会冒泡到这里，
        // 若在卡片上点一下就把口令交回调用方，等于凭空多出一个「误提交」出口）
        $('reauth-modal').addEventListener('click', function (e) {
            if (e && e.target && e.target === $('reauth-modal')) _settleReauth('');
        });
        $('danmaku-room-filter').addEventListener('change', dmRenderStream);
        $('danmaku-clear-btn').addEventListener('click', function () {
            dmMessages = [];
            dmRenderStream();
        });

        // 事件委托：替换内联 onclick/onchange 拼接，避免每次渲染重新解析 JS 字符串，更稳健
        $('rooms-tbody').addEventListener('change', function (e) {
            var t = e.target;
            if (t && t.matches && t.matches('input[type="checkbox"][data-action="toggle"]')) {
                toggleRoom(t.getAttribute('data-url'), t.checked);
            } else if (t && t.matches && t.matches('select[data-action="quality"]')) {
                changeRoomQuality(t.getAttribute('data-url'), t.value);
            }
        });
        $('rooms-tbody').addEventListener('click', function (e) {
            var t = e.target.closest && e.target.closest('button[data-action="delete"]');
            if (t) {
                deleteRoom(t.getAttribute('data-url'));
            }
        });
        $('file-breadcrumb').addEventListener('click', function (e) {
            var t = e.target.closest && e.target.closest('a[data-path]');
            if (t) {
                e.preventDefault();
                loadFiles(t.getAttribute('data-path'));
            }
        });
        $('files-tbody').addEventListener('click', function (e) {
            var t = e.target.closest && e.target.closest('button[data-action]');
            if (!t) return;
            var action = t.getAttribute('data-action');
            var p = t.getAttribute('data-path');
            if (action === 'enter') {
                loadFiles(p);
            } else if (action === 'download') {
                downloadFile(p);
            }
        });

        // WD-10 / SEV-2227：页面可见性感知。隐藏时停掉状态/日志/弹幕三条轮询（后台标签页与最小化窗口原本
        // 会持续请求）；回到前台按「意图 && 当前已停」恢复并补拉一次。隐藏侧必须用 pauseSSE（保留 sseWanted
        // 意图）而不是 stopSSE——后者会把意图一起清掉。
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                pauseSSE();
                stopDanmakuPolling();
                stopLogsPolling();
            } else {
                if (sseWanted && sseStopped) startSSE();
                var visibleView = document.querySelector('.view:not(.hidden)');
                if (visibleView && visibleView.id === 'danmaku-view') {
                    startDanmakuPolling();
                } else if (visibleView && visibleView.id === 'dashboard-view') {
                    startLogsPolling();
                }
            }
        });

        // F-09 / WD-07：把「未启用认证」的风险显式呈现给用户——后端 /api/auth/status 一直返回 warning 并
        // 为此端点放行，前端若不消费，用户无认证使用面板时看不到任何提示，错失「自己去打开认证」的引导时机。
        api('/api/auth/status')
            .then(function (st) {
                if (st && st.auth_required === false) {
                    showAuthWarning(st.warning);
                }
            })
            .catch(function () {});

        // 启动引导：尝试拉取状态，成功则进入仪表盘，否则显示登录
        (async function () {
            try {
                var s = await api('/api/status');
                renderStatus(s);
                showView('dashboard');
            } catch (e) {
                showLogin();
            }
        })();
    });

    // F-09：在顶栏下方插入风险横幅（仅无认证时出现，随登录页一起隐去）。textContent 赋值 + 固定位置插入，
    // 不引入 XSS 面，也不影响既有事件委托。
    function showAuthWarning(text) {
        if (document.getElementById('auth-warning-banner')) return;
        var topbar = document.querySelector('.topbar');
        if (!topbar || !topbar.parentNode) return;
        var bar = document.createElement('div');
        bar.id = 'auth-warning-banner';
        bar.className = 'auth-warning';
        bar.textContent = text || '';
        topbar.parentNode.insertBefore(bar, topbar.nextSibling);
    }
})();
