// DouyinLiveRecorder Web 管理面板前端逻辑（Task 9）。
// 将 UI 绑定到 src/web_api.py 暴露的 REST API。不修改 index.html / style.css。
(function () {
    'use strict';

    var TOKEN_KEY = 'dlr_token';
    var THEME_KEY = 'dlr_theme';
    var SENSITIVE_SECTIONS = { 'Cookie': true, '账号密码': true, 'Authorization': true };

    var sseSource = null;
    var sseStopped = true;
    var configBackup = null;
    var toastTimer = null;

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
            throw new Error(text || '未授权');
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

    function hideAllViews() {
        var views = document.querySelectorAll('.view');
        for (var i = 0; i < views.length; i++) {
            views[i].classList.add('hidden');
        }
    }

    // 8. showView
    function showView(name) {
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
            loadRooms();
        } else if (name === 'config') {
            loadConfig();
        } else if (name === 'files') {
            loadFiles('');
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
    }

    // 10. doLogin
    async function doLogin() {
        var pw = $('login-password').value;
        try {
            var data = await api('/api/login', { method: 'POST', body: { password: pw } });
            setToken(data.token || '');
            $('login-error').textContent = '';
            showView('dashboard');
        } catch (e) {
            $('login-error').textContent = e.message || '登录失败';
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
        $('stat-errors').textContent = (s.error_count != null ? s.error_count : '-');
        $('stat-disk').textContent = (s.disk_free_gb != null ? s.disk_free_gb : '-');
        var tbody = $('recording-tbody');
        var rec = s.recording || [];
        if (!rec.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty">暂无录制</td></tr>';
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

    // 13. loadLogs
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

    // 14. loadRooms
    async function loadRooms() {
        var tbody = $('rooms-tbody');
        try {
            var rooms = await api('/api/rooms');
            if (!rooms.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无直播间</td></tr>';
                return;
            }
            var html = '';
            for (var i = 0; i < rooms.length; i++) {
                var r = rooms[i];
                var checked = r.enabled ? ' checked' : '';
                var toggleCall = 'toggleRoom(' + JSON.stringify(r.url) + ', this.checked)';
                var deleteCall = 'deleteRoom(' + JSON.stringify(r.url) + ')';
                html += '<tr>'
                    + '<td title="' + esc(r.url) + '">' + esc(r.url) + '</td>'
                    + '<td>' + esc(r.quality) + '</td>'
                    + '<td>' + esc(r.name) + '</td>'
                    + '<td><label class="switch"><input type="checkbox"' + checked
                        + ' onchange="' + esc(toggleCall) + '"><span class="slider"></span></label></td>'
                    + '<td>' + (r.recording ? '是' : '否') + '</td>'
                    + '<td><button class="danger" onclick="' + esc(deleteCall) + '">删除</button></td>'
                    + '</tr>';
            }
            tbody.innerHTML = html;
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty">加载失败</td></tr>';
        }
    }

    // 15. window.toggleRoom
    window.toggleRoom = async function (url, enable) {
        try {
            await api('/api/rooms/toggle', { method: 'POST', body: { url: url, enable: enable } });
            toast(enable ? '已启用' : '已禁用', 'success');
        } catch (e) {
            toast('操作失败: ' + e.message, 'error');
            loadRooms();
        }
    };

    // 16. window.deleteRoom
    window.deleteRoom = async function (url) {
        if (!confirm('确认删除该直播间？')) return;
        try {
            await api('/api/rooms?url=' + encodeURIComponent(url), { method: 'DELETE' });
            toast('已删除', 'success');
            loadRooms();
        } catch (e) {
            toast('删除失败: ' + e.message, 'error');
        }
    };

    // 17. loadConfig
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
                    html += '<div class="config-row">'
                        + '<label>' + esc(key) + '</label>'
                        + '<input type="' + inputType + '" data-section="' + esc(section) + '"'
                        + ' data-key="' + esc(key) + '" value="' + esc(val) + '">'
                        + '</div>';
                }
                html += '</div>';
            }
            container.innerHTML = html || '无配置';
        } catch (e) {
            container.textContent = '加载失败';
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
                toast('已保存 ' + count + ' 项', 'success');
            } else {
                toast('无变更', 'info');
            }
            await loadConfig();
        } catch (e) {
            toast('保存失败: ' + e.message, 'error');
        }
    }

    // 19. loadFiles
    async function loadFiles(path) {
        path = path || '';
        var tbody = $('files-tbody');
        var crumb = $('file-breadcrumb');
        try {
            var items = await api('/api/files?path=' + encodeURIComponent(path));
            // 面包屑：根目录 + 逐级路径
            var crumbHtml = '';
            var rootCall = 'loadFiles(' + JSON.stringify('') + ')';
            crumbHtml += '<a onclick="' + esc(rootCall) + '">根目录</a>';
            var parts = path ? path.split('/') : [];
            var cumul = '';
            for (var i = 0; i < parts.length; i++) {
                var p = parts[i];
                if (!p) continue;
                cumul = cumul ? cumul + '/' + p : p;
                var call = 'loadFiles(' + JSON.stringify(cumul) + ')';
                crumbHtml += ' / <a onclick="' + esc(call) + '">' + esc(p) + '</a>';
            }
            crumb.innerHTML = crumbHtml;
            // 文件列表
            if (!items.length) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty">空目录</td></tr>';
                return;
            }
            var html = '';
            for (var j = 0; j < items.length; j++) {
                var it = items[j];
                var icon = it.type === 'dir' ? '📁' : '📄';
                var action;
                if (it.type === 'dir') {
                    var enterCall = 'loadFiles(' + JSON.stringify(it.path) + ')';
                    action = '<button class="small" onclick="' + esc(enterCall) + '">进入</button>';
                } else {
                    action = '<button class="small" onclick="downloadFile(' + JSON.stringify(it.path) + ')">下载</button>';
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
            tbody.innerHTML = '<tr><td colspan="5" class="empty">加载失败</td></tr>';
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
            .catch(function (e) { toast('下载失败: ' + e.message, 'error'); });
    };

    // 20. addRoom（room-add-form submit 处理）
    async function addRoom() {
        var url = $('room-url').value.trim();
        var quality = $('room-quality').value;
        var name = $('room-name').value.trim();
        if (!url) {
            toast('请输入直播间地址', 'error');
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
            toast('已添加', 'success');
            $('room-url').value = '';
            $('room-quality').value = '';
            $('room-name').value = '';
            loadRooms();
        } catch (e) {
            toast('添加失败: ' + e.message, 'error');
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

        var tabs = document.querySelectorAll('.tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].addEventListener('click', function () {
                showView(this.getAttribute('data-view'));
            });
        }
        $('theme-toggle').addEventListener('click', toggleTheme);
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
        $('config-save-btn').addEventListener('click', saveConfig);

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
