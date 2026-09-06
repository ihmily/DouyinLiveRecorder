// DouyinLiveRecorder Web 管理面板前端逻辑。
// 将 UI 绑定到 src/web_api.py 暴露的 REST API：
// 仪表盘（状态轮询/日志）、弹幕监控（增量游标轮询）、直播间、配置、文件。
//
// 【整体架构】
// 整个前端用一个 IIFE 模块包裹（见下方 (function(){...})()），所有状态与函数都封闭在
// 私有作用域内，仅把 window.toggleRoom / window.deleteRoom / window.loadFiles /
// window.downloadFile 暴露给内联/事件委托调用。这样避免污染全局，也避免每次重渲染表格时
// 重新解析内联 onclick 字符串（表格行由 innerHTML 拼接，已改用 rooms-tbody 上的事件委托）。
//
// 状态组织：以一组模块级闭包变量保存（sseStopped/sseSource 仪表盘轮询、dm* 弹幕轮询与缓冲、
// configBackup 配置原始快照用于 diff、toastTimer 提示定时器），没有引入框架或状态机。
//
// 与后端交互：统一经 api() 包装 fetch，自动附带 Bearer Token、JSON 序列化、401 跳转登录、
// 按 content-type 决定返回 JSON 还是纯文本；二进制下载绕过 api() 直接 fetch+blob。
// 轮询全部用 setTimeout 递归（非真 SSE/WebSocket），每轮结束后若未被停止则排下一轮，
// 离屏/切视图时通过 stop* 清理定时器，避免多个视图同时轮询造成请求堆积。
//
// 安全要点：所有动态文本（房间名、弹幕、文件名、配置值、日志）渲染前一律经 esc() 转义，
// 敏感配置段（Cookie/账号密码/Authorization）输入框用 password 类型，saveConfig 跳过 '***'
// 掩码，防止配置值原样回写覆盖后端真实凭据。
(function () {
    'use strict';

    var TOKEN_KEY = 'dlr_token';
    var THEME_KEY = 'dlr_theme';
    var SENSITIVE_SECTIONS = { 'Cookie': true, '账号密码': true, 'Authorization': true };

    var sseSource = null;
    var sseStopped = true;
    var configBackup = null;
    var toastTimer = null;

    // 弹幕监控状态：dmTimer/dmStopped 控制轮询；dmLastSeq 为增量游标；
    // dmMessages 为前端保留的近期消息（最多 300 条），切筛选时全量重绘。
    var dmTimer = null;
    var dmStopped = true;
    var dmLastSeq = 0;
    var dmMessages = [];
    var DM_MAX_MESSAGES = 300;

    // 画质选项状态：qualityOptions 为用户已选档位（渲染下拉与 chips），
    // qualityBuiltin 为引擎支持的全部内置档位（渲染「添加画质」候选项）。
    var qualityOptions = [];
    var qualityBuiltin = [];

    // ===== API 接口契约速查（路径/方法/关键参数/返回/前后端处理）=====
    // 所有请求经 api() 自动带 Bearer Token；401 统一清 Token 并跳登录；非 2xx 抛错由调用方 catch。
    // GET  /api/status                 → 仪表盘快照 {engine_alive, recording_enabled, monitoring,
    //                                         recording_count, error_count, recent_errors, disk_free_gb,
    //                                         recording:[{name,quality,actual_quality,start_time,duration}]}
    // POST /api/recording/toggle       body{enable:bool} → 切换引擎录制开关，成功即回拉 /api/status 同步按钮
    // GET  /api/logs?lines=100         → {lines:[...]} 纯文本日志行，拼到 #log-stream
    // GET  /api/danmaku?since=<seq>     → {rooms:[...], messages:[...], last_seq, truncated}
    //                                         增量游标：首次 since=0，之后用返回 last_seq 续拉，避免重复
    // GET  /api/language               → {language}；PUT body{language} 热切换（后端控制台/日志同步翻译）
    // POST /api/login    body{password}→ {token}；失败抛错显示到 #login-error
    // GET  /api/rooms                 → [{url,quality,name,enabled,recording}]；增删/启停/切画质：
    // POST /api/rooms   body{url,quality?,name?}；DELETE /api/rooms?url=；POST /api/rooms/toggle body{url,enable}
    // PUT  /api/rooms/quality         body{url,quality} → 按房间切换画质（quality 空=恢复默认，与桌面端共用画质段）
    // GET  /api/rooms/qualities       → {options:[...], builtin:[...]}；PUT body{options:[...]} 回写画质选项
    //                                         （与桌面端画质切换菜单共用，落地 config.ini [录制设置]）
    // GET  /api/config                 → {section:{key:value}}；PUT /api/config body{section,key,value} 单键落盘
    // GET  /api/files?path=            → [{name,type,path,size?,mtime?}]；下载绕过 api() 直接 blob 流
    function $(id) { return document.getElementById(id); }

    // 1. Token helpers
    function getToken() {
        return localStorage.getItem(TOKEN_KEY) || '';
    }
    function setToken(t) {
        if (t) {
            localStorage.setItem(TOKEN_KEY, t);
        } else {
            localStorage.removeItem(TOKEN_KEY);
        }
    }

    // 2. api fetch wrapper
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
        var resp = await fetch(path, {
            method: opts.method || 'GET',
            headers: headers,
            body: body,
        });
        var text = await resp.text();
        if (resp.status === 401) {
            setToken('');
            showLogin();
            throw new Error(text || t('common.unauthorized'));
        }
        if (!resp.ok) {
            throw new Error(text);
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

    // 6. esc HTML 转义
    function esc(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // 6b. 前端 i18n：界面文案字典（与后端 i18n.py 的语言集一致）。
    // 后端负责控制台/日志输出翻译（GET/PUT /api/language 即时热切换），
    // 前端负责静态界面文案：data-i18n / data-i18n-placeholder 属性 + t() 动态拼接。
    var LANG_KEY = 'dlr_lang';
    var currentLang = 'zh_CN';
    var I18N = {
        zh_CN: {
            'title': 'DouyinLiveRecorder 管理面板', 'brand': '直播录制管理面板',
            'tab.dashboard': '仪表盘', 'tab.danmaku': '弹幕监控', 'tab.rooms': '直播间',
            'tab.config': '配置', 'tab.files': '文件', 'logout': '退出',
            'login.title': '登录', 'login.password': '访问密码', 'login.submit': '登录', 'login.failed': '登录失败',
            'dashboard.engineWarning': '⚠️ 录制引擎已停止运行，请检查日志或重启服务',
            'dashboard.monitoring': '监测中', 'dashboard.recording': '录制中',
            'dashboard.errors': '错误数(累计/近期)', 'dashboard.disk': '磁盘剩余(GB)',
            'dashboard.recordingNow': '正在录制', 'dashboard.logs': '实时日志',
            'recording.state.on': '录制运行中', 'recording.state.off': '录制已停止',
            'recording.start': '开始录制', 'recording.stop': '停止录制',
            'toast.recordingStarted': '录制已开始', 'toast.recordingStopped': '录制已停止',
            'col.name': '名称', 'col.platform': '平台', 'col.status': '状态', 'col.startTime': '开始时间',
            'col.duration': '已录时长', 'col.qualitySet': '设置画质', 'col.qualityActual': '实际画质',
            'col.url': '地址', 'col.enabled': '启用', 'col.recording': '录制中', 'col.actions': '操作',
            'col.type': '类型', 'col.size': '大小', 'col.mtime': '修改时间',
            'empty.noRecording': '暂无录制', 'loading': '加载中...', 'loadFailed': '加载失败',
            'danmaku.rooms': '弹幕房间', 'danmaku.col.total': '累计弹幕', 'danmaku.col.rate': '速率(条/分)',
            'danmaku.col.gifts': '礼物', 'danmaku.col.online': '在线', 'danmaku.emptyRooms': '暂无监控数据',
            'danmaku.live': '实时弹幕', 'danmaku.allRooms': '全部房间', 'danmaku.clear': '清空',
            'danmaku.connected': '已连接', 'danmaku.disconnected': '已断开', 'danmaku.noData': '暂无弹幕数据',
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
            'files.title': '录制文件', 'files.root': '根目录', 'files.emptyDir': '空目录',
            'common.yes': '是', 'common.no': '否', 'common.unauthorized': '未授权',
            'toast.enabled': '已启用', 'toast.disabled': '已禁用', 'toast.opFailed': '操作失败: ',
            'toast.deleted': '已删除', 'toast.deleteFailed': '删除失败: ', 'toast.added': '已添加',
            'toast.addFailed': '添加失败: ', 'toast.urlRequired': '请输入直播间地址',
            'toast.downloadFailed': '下载失败: ', 'toast.loginExpired': '登录已过期，请重新登录',
            'toast.saveFailed': '保存失败: ', 'toast.langSwitched': '语言已切换',
            'toast.langSwitchFailed': '语言切换失败: '
        },
        en_US: {
            'title': 'DouyinLiveRecorder Panel', 'brand': 'Live Recording Panel',
            'tab.dashboard': 'Dashboard', 'tab.danmaku': 'Danmaku', 'tab.rooms': 'Rooms',
            'tab.config': 'Config', 'tab.files': 'Files', 'logout': 'Logout',
            'login.title': 'Login', 'login.password': 'Access password', 'login.submit': 'Login', 'login.failed': 'Login failed',
            'dashboard.engineWarning': '⚠️ The recording engine has stopped. Check logs or restart the service',
            'dashboard.monitoring': 'Monitoring', 'dashboard.recording': 'Recording',
            'dashboard.errors': 'Errors (total/recent)', 'dashboard.disk': 'Disk free (GB)',
            'dashboard.recordingNow': 'Recording now', 'dashboard.logs': 'Live logs',
            'recording.state.on': 'Recording active', 'recording.state.off': 'Recording stopped',
            'recording.start': 'Start recording', 'recording.stop': 'Stop recording',
            'toast.recordingStarted': 'Recording started', 'toast.recordingStopped': 'Recording stopped',
            'col.name': 'Name', 'col.platform': 'Platform', 'col.status': 'Status', 'col.startTime': 'Start time',
            'col.duration': 'Duration', 'col.qualitySet': 'Set quality', 'col.qualityActual': 'Actual quality',
            'col.url': 'URL', 'col.enabled': 'Enabled', 'col.recording': 'Recording', 'col.actions': 'Actions',
            'col.type': 'Type', 'col.size': 'Size', 'col.mtime': 'Modified',
            'empty.noRecording': 'No recordings', 'loading': 'Loading...', 'loadFailed': 'Load failed',
            'danmaku.rooms': 'Danmaku rooms', 'danmaku.col.total': 'Messages', 'danmaku.col.rate': 'Rate (msg/min)',
            'danmaku.col.gifts': 'Gifts', 'danmaku.col.online': 'Online', 'danmaku.emptyRooms': 'No monitoring data',
            'danmaku.live': 'Live danmaku', 'danmaku.allRooms': 'All rooms', 'danmaku.clear': 'Clear',
            'danmaku.connected': 'Connected', 'danmaku.disconnected': 'Disconnected', 'danmaku.noData': 'No danmaku data',
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
            'files.title': 'Recordings', 'files.root': 'Root', 'files.emptyDir': 'Empty folder',
            'common.yes': 'Yes', 'common.no': 'No', 'common.unauthorized': 'Unauthorized',
            'toast.enabled': 'Enabled', 'toast.disabled': 'Disabled', 'toast.opFailed': 'Operation failed: ',
            'toast.deleted': 'Deleted', 'toast.deleteFailed': 'Delete failed: ', 'toast.added': 'Added',
            'toast.addFailed': 'Add failed: ', 'toast.urlRequired': 'Please enter a live room URL',
            'toast.downloadFailed': 'Download failed: ', 'toast.loginExpired': 'Login expired, please log in again',
            'toast.saveFailed': 'Save failed: ', 'toast.langSwitched': 'Language switched',
            'toast.langSwitchFailed': 'Language switch failed: '
        },
        en_GB: {
            'title': 'DouyinLiveRecorder Panel', 'brand': 'Live Recording Panel',
            'tab.dashboard': 'Dashboard', 'tab.danmaku': 'Danmaku', 'tab.rooms': 'Rooms',
            'tab.config': 'Config', 'tab.files': 'Files', 'logout': 'Log out',
            'login.title': 'Log in', 'login.password': 'Access password', 'login.submit': 'Log in', 'login.failed': 'Log in failed',
            'dashboard.engineWarning': '⚠️ The recording engine has stopped. Check logs or restart the service',
            'dashboard.monitoring': 'Monitoring', 'dashboard.recording': 'Recording',
            'dashboard.errors': 'Errors (total/recent)', 'dashboard.disk': 'Disk free (GB)',
            'dashboard.recordingNow': 'Recording now', 'dashboard.logs': 'Live logs',
            'recording.state.on': 'Recording active', 'recording.state.off': 'Recording stopped',
            'recording.start': 'Start recording', 'recording.stop': 'Stop recording',
            'toast.recordingStarted': 'Recording started', 'toast.recordingStopped': 'Recording stopped',
            'col.name': 'Name', 'col.platform': 'Platform', 'col.status': 'Status', 'col.startTime': 'Start time',
            'col.duration': 'Duration', 'col.qualitySet': 'Set quality', 'col.qualityActual': 'Actual quality',
            'col.url': 'URL', 'col.enabled': 'Enabled', 'col.recording': 'Recording', 'col.actions': 'Actions',
            'col.type': 'Type', 'col.size': 'Size', 'col.mtime': 'Modified',
            'empty.noRecording': 'No recordings', 'loading': 'Loading...', 'loadFailed': 'Load failed',
            'danmaku.rooms': 'Danmaku rooms', 'danmaku.col.total': 'Messages', 'danmaku.col.rate': 'Rate (msg/min)',
            'danmaku.col.gifts': 'Gifts', 'danmaku.col.online': 'Online', 'danmaku.emptyRooms': 'No monitoring data',
            'danmaku.live': 'Live danmaku', 'danmaku.allRooms': 'All rooms', 'danmaku.clear': 'Clear',
            'danmaku.connected': 'Connected', 'danmaku.disconnected': 'Disconnected', 'danmaku.noData': 'No danmaku data',
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
            'files.title': 'Recordings', 'files.root': 'Root', 'files.emptyDir': 'Empty folder',
            'common.yes': 'Yes', 'common.no': 'No', 'common.unauthorized': 'Unauthorised',
            'toast.enabled': 'Enabled', 'toast.disabled': 'Disabled', 'toast.opFailed': 'Operation failed: ',
            'toast.deleted': 'Deleted', 'toast.deleteFailed': 'Delete failed: ', 'toast.added': 'Added',
            'toast.addFailed': 'Add failed: ', 'toast.urlRequired': 'Please enter a live room URL',
            'toast.downloadFailed': 'Download failed: ', 'toast.loginExpired': 'Log in expired, please log in again',
            'toast.saveFailed': 'Save failed: ', 'toast.langSwitched': 'Language switched',
            'toast.langSwitchFailed': 'Language switch failed: '
        },
        zh_TW: {
            'title': 'DouyinLiveRecorder 管理面板', 'brand': '直播錄製管理面板',
            'tab.dashboard': '儀表板', 'tab.danmaku': '彈幕監控', 'tab.rooms': '直播間',
            'tab.config': '設定', 'tab.files': '檔案', 'logout': '登出',
            'login.title': '登入', 'login.password': '存取密碼', 'login.submit': '登入', 'login.failed': '登入失敗',
            'dashboard.engineWarning': '⚠️ 錄製引擎已停止執行，請檢查日誌或重新啟動服務',
            'dashboard.monitoring': '監測中', 'dashboard.recording': '錄製中',
            'dashboard.errors': '錯誤數(累計/近期)', 'dashboard.disk': '磁碟剩餘(GB)',
            'dashboard.recordingNow': '正在錄製', 'dashboard.logs': '即時日誌',
            'recording.state.on': '錄製運行中', 'recording.state.off': '錄製已停止',
            'recording.start': '開始錄製', 'recording.stop': '停止錄製',
            'toast.recordingStarted': '錄製已開始', 'toast.recordingStopped': '錄製已停止',
            'col.name': '名稱', 'col.platform': '平台', 'col.status': '狀態', 'col.startTime': '開始時間',
            'col.duration': '已錄時長', 'col.qualitySet': '設定畫質', 'col.qualityActual': '實際畫質',
            'col.url': '位址', 'col.enabled': '啟用', 'col.recording': '錄製中', 'col.actions': '操作',
            'col.type': '類型', 'col.size': '大小', 'col.mtime': '修改時間',
            'empty.noRecording': '暫無錄製', 'loading': '載入中...', 'loadFailed': '載入失敗',
            'danmaku.rooms': '彈幕房間', 'danmaku.col.total': '累計彈幕', 'danmaku.col.rate': '速率(條/分)',
            'danmaku.col.gifts': '禮物', 'danmaku.col.online': '線上', 'danmaku.emptyRooms': '暫無監控資料',
            'danmaku.live': '即時彈幕', 'danmaku.allRooms': '全部房間', 'danmaku.clear': '清空',
            'danmaku.connected': '已連線', 'danmaku.disconnected': '已斷線', 'danmaku.noData': '暫無彈幕資料',
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
            'files.title': '錄製檔案', 'files.root': '根目錄', 'files.emptyDir': '空資料夾',
            'common.yes': '是', 'common.no': '否', 'common.unauthorized': '未授權',
            'toast.enabled': '已啟用', 'toast.disabled': '已停用', 'toast.opFailed': '操作失敗: ',
            'toast.deleted': '已刪除', 'toast.deleteFailed': '刪除失敗: ', 'toast.added': '已新增',
            'toast.addFailed': '新增失敗: ', 'toast.urlRequired': '請輸入直播間位址',
            'toast.downloadFailed': '下載失敗: ', 'toast.loginExpired': '登入已過期，請重新登入',
            'toast.saveFailed': '儲存失敗: ', 'toast.langSwitched': '語言已切換',
            'toast.langSwitchFailed': '語言切換失敗: '
        }
    };

    // 界面文案取值：当前语言缺失时回退 zh_CN，再缺失回退键名本身
    function t(key) {
        var dict = I18N[currentLang] || I18N.zh_CN;
        if (Object.prototype.hasOwnProperty.call(dict, key)) return dict[key];
        if (Object.prototype.hasOwnProperty.call(I18N.zh_CN, key)) return I18N.zh_CN[key];
        return key;
    }

    // 应用静态文案：data-i18n → textContent；data-i18n-placeholder → placeholder
    function applyTranslations() {
        var nodes = document.querySelectorAll('[data-i18n]');
        for (var i = 0; i < nodes.length; i++) {
            nodes[i].textContent = t(nodes[i].getAttribute('data-i18n'));
        }
        var phNodes = document.querySelectorAll('[data-i18n-placeholder]');
        for (var j = 0; j < phNodes.length; j++) {
            phNodes[j].setAttribute('placeholder', t(phNodes[j].getAttribute('data-i18n-placeholder')));
        }
        document.documentElement.setAttribute('lang', currentLang.replace('_', '-'));
    }

    // 初始化语言选择器：读后端当前语言（失败回退 localStorage），渲染选项
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
            currentLang = data && data.language ? data.language : (localStorage.getItem(LANG_KEY) || 'zh_CN');
            localStorage.setItem(LANG_KEY, currentLang);
            sel.value = currentLang;
            applyTranslations();
        }).catch(function () {
            currentLang = localStorage.getItem(LANG_KEY) || 'zh_CN';
            sel.value = currentLang;
            applyTranslations();
        });
        sel.addEventListener('change', function () {
            var target = sel.value;
            api('/api/language', { method: 'PUT', body: { language: target } }).then(function () {
                currentLang = target;
                localStorage.setItem(LANG_KEY, target);
                applyTranslations();
                toast(t('toast.langSwitched'), 'success');
            }).catch(function (e) {
                toast(t('toast.langSwitchFailed') + (e.message || ''), 'error');
            });
        });
    }

    function hideAllViews() {
        var views = document.querySelectorAll('.view');
        for (var i = 0; i < views.length; i++) {
            views[i].classList.add('hidden');
        }
    }

    // 8. showView
    function showView(name) {
        stopDanmakuPolling();
        hideAllViews();
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
            // 先拉画质选项再渲染房间列表：行内画质下拉的选项来自 qualityOptions，
            // 顺序颠倒会导致首屏下拉只有「默认画质」+ 当前值（选项未就绪）
            loadQualityOptions().finally(loadRooms);
        } else if (name === 'config') {
            loadConfig();
        } else if (name === 'files') {
            loadFiles('');
        } else if (name === 'danmaku') {
            startDanmakuPolling();
        } else if (name === 'dashboard') {
            startSSE();
            loadLogs();
        } else {
            stopSSE();
        }
    }

    // 9. showLogin
    function showLogin() {
        hideAllViews();
        var lv = $('login-view');
        if (lv) lv.classList.remove('hidden');
        stopSSE();
        stopDanmakuPolling();
    }

    // 10. doLogin —— 调 POST /api/login，成功把返回的 token 存入 localStorage 并进入仪表盘；
    // 失败（含 401）在 #login-error 显示后端报错文案。密码仅此一次明文发送，之后用 Token。
    async function doLogin() {
        var pw = $('login-password').value;
        try {
            var data = await api('/api/login', { method: 'POST', body: { password: pw } });
            setToken(data.token || '');
            $('login-error').textContent = '';
            showView('dashboard');
        } catch (e) {
            $('login-error').textContent = e.message || t('login.failed');
        }
    }

    // 11. startSSE / stopSSE（轮询实现，非真实 SSE）
    function startSSE() {
        stopSSE();
        sseStopped = false;
        sseSource = setTimeout(function poll() {
            api('/api/status').then(renderStatus).catch(function () {}).then(function () {
                if (!sseStopped) {
                    sseSource = setTimeout(poll, 2000);
                }
            });
        }, 0);
    }
    function stopSSE() {
        sseStopped = true;
        if (sseSource) {
            clearTimeout(sseSource);
            sseSource = null;
        }
    }

    // 12. renderStatus
    function renderStatus(s) {
        if (!s) s = {};
        renderRecordingControl(s);
        var warnEl = $('engine-warning');
        if (warnEl) {
            if (s.engine_alive === false) {
                warnEl.classList.remove('hidden');
            } else {
                warnEl.classList.add('hidden');
            }
        }
        $('stat-monitoring').textContent = (s.monitoring != null ? s.monitoring : '-');
        $('stat-recording').textContent = (s.recording_count != null ? s.recording_count : '-');
        // 错误数双口径：累计（进程启动起）/ 近期（近 error_window_size 次检测周期内）
        var errTotal = (s.error_count != null ? s.error_count : '-');
        var errRecent = (s.recent_errors != null ? s.recent_errors : '-');
        $('stat-errors').textContent = errTotal + ' / ' + errRecent;
        $('stat-disk').textContent = (s.disk_free_gb != null ? s.disk_free_gb : '-');
        var tbody = $('recording-tbody');
        var rec = s.recording || [];
        if (!rec.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty">' + esc(t('empty.noRecording')) + '</td></tr>';
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

    // 12b. 录制控制条：按状态快照同步「开始/停止录制」按钮与状态标签。
    // recording_enabled 为引擎级录制开关（后端 get_status 暴露）：开启时禁用「开始」
    // 并启用「停止」，关闭时反之；引擎线程死亡时两按钮均禁用（切换开关已无意义，
    // 页面顶部另有引擎告警横幅）。状态标签用双子 span + hidden 切换，文案交给
    // data-i18n 静态翻译（语言切换即时生效，无需等下一次轮询）。
    function renderRecordingControl(s) {
        var enabled = s.recording_enabled === true;
        var engineAlive = s.engine_alive !== false;
        // 状态标签容器是 class（index.html 的 span.recording-state），勿用 #id 选择器
        var onEl = document.querySelector('.recording-state .state-on');
        var offEl = document.querySelector('.recording-state .state-off');
        if (onEl && offEl) {
            onEl.classList.toggle('hidden', !enabled);
            offEl.classList.toggle('hidden', enabled);
        }
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

    // 13. loadLogs —— GET /api/logs?lines=100，取最近 100 行纯文本日志拼到 #log-stream
    // 并滚动到底部；错误被静默忽略（仪表盘轮询期间偶发失败不应闪烁界面）。
    async function loadLogs() {
        try {
            var data = await api('/api/logs?lines=100');
            var lines = (data && data.lines) || [];
            var el = $('log-stream');
            el.textContent = lines.join('\n');
            el.scrollTop = el.scrollHeight;
        } catch (e) {
            /* 忽略日志加载错误 */
        }
    }

    // 13b. 弹幕监控：轮询 + 渲染（增量游标 since=seq，2 秒一次）
    function startDanmakuPolling() {
        stopDanmakuPolling();
        dmStopped = false;
        dmTimer = setTimeout(function poll() {
            api('/api/danmaku?since=' + dmLastSeq).then(renderDanmaku).catch(function () {}).then(function () {
                if (!dmStopped) {
                    dmTimer = setTimeout(poll, 2000);
                }
            });
        }, 0);
    }
    function stopDanmakuPolling() {
        dmStopped = true;
        if (dmTimer) {
            clearTimeout(dmTimer);
            dmTimer = null;
        }
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
        var dropped = m.dropped ? ' <span class="dm-dropped">(+' + m.dropped + t('danmaku.dropped') + '</span>' : '';
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
            el.textContent = dmMessages.length ? '' : t('danmaku.noData');
            if (!dmMessages.length) { return; }
        }
        el.innerHTML = html;
        if (nearBottom) {
            el.scrollTop = el.scrollHeight;
        }
    }

    // 渲染一次 /api/danmaku 响应：房间表 + 筛选下拉 + 增量消息
    function renderDanmaku(data) {
        if (!data) data = {};
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
        // 房间筛选下拉：保留当前选择，选项随房间列表刷新
        var sel = $('danmaku-room-filter');
        if (sel) {
            var cur = sel.value;
            var opts = '<option value="">' + esc(t('danmaku.allRooms')) + '</option>';
            for (var j = 0; j < rooms.length; j++) {
                opts += '<option value="' + esc(rooms[j].name) + '">' + esc(rooms[j].name) + '</option>';
            }
            sel.innerHTML = opts;
            var found = false;
            for (var k = 0; k < sel.options.length; k++) {
                if (sel.options[k].value === cur) { found = true; break; }
            }
            sel.value = found ? cur : '';
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
    // 行内开关/删除按钮靠 data-url 透传，点击由 rooms-tbody 上的事件委托转发到 toggleRoom/deleteRoom。
    // 画质列为行内下拉（选项 = 默认画质 + qualityOptions + 当前值兜底），change 委托转发 changeRoomQuality。
    // 注意：url 直接拼进 data-url 与 title，已用 esc() 转义防止属性注入；del 失败会回拉一次列表恢复 UI。
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
        try {
            var rooms = await api('/api/rooms');
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
            tbody.innerHTML = '<tr><td colspan="6" class="empty">' + esc(t('loadFailed')) + '</td></tr>';
        }
    }

    // 14b. 画质选项（WEB 直播间设置的下拉项 + 桌面端画质切换菜单共用一份 config.ini 配置）。
    // qualityOptions = 用户已选档位（下拉项 + chips）；qualityBuiltin = 引擎支持的全部内置档位，
    // 两者差值即「添加画质」的候选项。增删后 PUT /api/rooms/qualities 回写，本地同步重渲染。
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
    window.toggleRoom = async function (url, enable) {
        try {
            await api('/api/rooms/toggle', { method: 'POST', body: { url: url, enable: enable } });
            toast(enable ? t('toast.enabled') : t('toast.disabled'), 'success');
        } catch (e) {
            toast(t('toast.opFailed') + e.message, 'error');
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
            toast(t('toast.deleteFailed') + e.message, 'error');
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
            toast(t('toast.qualityChangeFailed') + e.message, 'error');
            loadRooms();
        }
    }

    // 17. loadConfig —— GET /api/config 取 {section:{key:value}}，逐段逐键渲染为 input（敏感段用
    // password 类型、旧键置灰只读、HTTPS 键与 SSL 平台列表键附动态提示）。渲染后把整份配置深拷贝进
    // configBackup，供 saveConfig 做「仅提交变更键」的 diff 比较，避免无谓回写。
    // SSL/HTTPS 整合：「是否启用https录制」已合并原「是否强制启用https录制」与
    // 「是否禁用SSL证书验证(是/否)」——开启=https 拉流并跳过证书校验；关闭=http
    // 拉流并恢复默认证书校验。旧键标注为已废弃（只读置灰），整合语义在界面明示。
    // FFmpeg 9.0 起 TLS 证书验证默认开启：「禁用SSL证书验证的平台」在 HTTP 录制模式
    // （默认校验）下生效——列表内平台跳过证书校验；HTTPS 模式已全局跳过、列表冗余。
    var HTTPS_RECORD_KEY = '是否启用https录制';
    var DEPRECATED_CONFIG_KEYS = {
        '是否强制启用https录制': 'config.deprecated',
        '是否禁用SSL证书验证(是/否)': 'config.deprecated',
        '虎牙是否禁用SSL证书验证(是/否)': 'config.deprecated'
    };
    var SSL_PLATFORM_KEY = '禁用SSL证书验证的平台(逗号分隔)';

    function httpsRecordingEnabled() {
        var inputs = document.querySelectorAll('#config-container input');
        for (var i = 0; i < inputs.length; i++) {
            if (inputs[i].getAttribute('data-key') === HTTPS_RECORD_KEY) {
                return (inputs[i].value || '').trim() === '是';
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
        try {
            var cfg = await api('/api/config');
            configBackup = JSON.parse(JSON.stringify(cfg));
            var html = '';
            for (var section in cfg) {
                if (!cfg.hasOwnProperty(section)) continue;
                html += '<div class="config-group"><h4>[' + esc(section) + ']</h4>';
                var items = cfg[section];
                for (var key in items) {
                    if (!items.hasOwnProperty(key)) continue;
                    var val = items[key];
                    var inputType = SENSITIVE_SECTIONS[section] ? 'password' : 'text';
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
                    html += '<div class="' + rowClass + '">'
                        + '<label>' + esc(key) + '</label>'
                        + '<input type="' + inputType + '" data-section="' + esc(section) + '"'
                        + ' data-key="' + esc(key) + '" value="' + esc(val) + '"' + readOnly + '>'
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
            container.textContent = t('loadFailed');
        }
    }

    // 18. saveConfig
    async function saveConfig() {
        var inputs = document.querySelectorAll('#config-container input');
        var count = 0;
        try {
            for (var i = 0; i < inputs.length; i++) {
                var inp = inputs[i];
                var section = inp.getAttribute('data-section');
                var key = inp.getAttribute('data-key');
                var newVal = inp.value;
                if (newVal === '***') continue;
                var oldVal = (configBackup && configBackup[section]) ? configBackup[section][key] : undefined;
                if (newVal !== oldVal) {
                    await api('/api/config', {
                        method: 'PUT',
                        body: { section: section, key: key, value: newVal },
                    });
                    count++;
                }
            }
            if (count > 0) {
                toast(t('config.saved').replace('{n}', String(count)), 'success');
            } else {
                toast(t('config.noChanges'), 'info');
            }
            await loadConfig();
        } catch (e) {
            toast(t('toast.saveFailed') + e.message, 'error');
        }
    }

    // 19. loadFiles —— GET /api/files?path=，按路径取目录项渲染表格，并据 path 切分重构面包屑
    // （根目录 + 逐级累积路径）。dir 行渲染「进入」按钮（事件委托转发 loadFiles 下钻），
    // file 行渲染「下载」按钮（转 downloadFile）。path 经 encodeURIComponent 编码，防分隔符/中文破坏路由。
    async function loadFiles(path) {
        path = path || '';
        var tbody = $('files-tbody');
        var crumb = $('file-breadcrumb');
        try {
            var items = await api('/api/files?path=' + encodeURIComponent(path));
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
            tbody.innerHTML = '<tr><td colspan="5" class="empty">' + esc(t('loadFailed')) + '</td></tr>';
        }
    }
    window.loadFiles = loadFiles;

    // 19b. downloadFile — 走认证头拉取二进制并触发下载（I1）
    // 直接 fetch + .blob()，不经过 api() 包装（api() 返回 res.text() 会破坏二进制）。
    window.downloadFile = function (path) {
        var headers = {};
        var token = getToken();
        if (token) headers['Authorization'] = 'Bearer ' + token;
        fetch('/api/files/download?path=' + encodeURIComponent(path), { headers: headers })
            .then(function (res) {
                if (res.status === 401) {
                    setToken('');
                    showLogin();
                    throw new Error(t('toast.loginExpired'));
                }
                if (!res.ok) throw new Error(res.statusText);
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
            .catch(function (e) { toast(t('toast.downloadFailed') + e.message, 'error'); });
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
            toast(t('toast.addFailed') + e.message, 'error');
        }
    }

    // 21. initTheme
    function initTheme() {
        var theme = localStorage.getItem(THEME_KEY) || 'light';
        document.body.dataset.theme = theme;
        var btn = $('theme-toggle');
        if (btn) btn.textContent = theme === 'light' ? '🌙' : '☀️';
    }

    // 22. toggleTheme
    function toggleTheme() {
        var cur = document.body.dataset.theme === 'dark' ? 'dark' : 'light';
        var next = cur === 'dark' ? 'light' : 'dark';
        document.body.dataset.theme = next;
        localStorage.setItem(THEME_KEY, next);
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
            setToken('');
            showLogin();
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
})();
