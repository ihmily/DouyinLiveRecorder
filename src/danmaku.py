# -*- coding: utf-8 -*-
"""
抖音直播弹幕(IM 消息)抓取模块

通过抖音 webcast IM 的 WebSocket 长连接实时拉取直播间消息，抓到的内容远不止"弹幕"：
    - WebcastChatMessage            评论/弹幕
    - WebcastGiftMessage            礼物
    - WebcastLikeMessage            点赞
    - WebcastMemberMessage          进场/关注提示
    - WebcastSocialMessage          关注/分享
    - WebcastRoomStatsMessage       在线人数
    - WebcastMatchAgainstScoreMessage   PK 比分
    - WebcastEmojiChatMessage       表情弹幕
    - WebcastControlMessage         直播间状态(关播等)

输出格式：
    jsonl  逐行 JSON，全字段，适合二次分析
    srt    标准字幕，播放时挂载
    ass    ASS 字幕，样式可控，可用 ffmpeg 烧进画面

依赖：websocket-client、protobuf（已随 requirements 追加）
"""

import gzip
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional

from .logger import logger

JS_SIGN_PATH = Path(__file__).resolve().parent / 'javascript' / 'douyin_ws_sign.js'

# 生成 WebSocket signature 时参与 md5 的固定字段，顺序不能变
WS_SIGN_PARAMS = ("live_id,aid,version_code,webcast_sdk_version,"
                  "room_id,sub_room_id,sub_channel_id,did_rule,"
                  "user_unique_id,device_platform,device_type,ac,"
                  "identity").split(',')

try:
    from .protobuf import douyin_pb2 as pb
except ImportError as _e:  # pragma: no cover
    pb = None
    _PB_IMPORT_ERROR = _e

try:
    import websocket
except ImportError:  # pragma: no cover
    websocket = None


DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
)

# 兜底 ttwid：抖音的 webcast 接口没有 ttwid 会直接拒绝，
# 但任何硬编码凭证终会失效，所以下面会自动申请新的，这个值只在网络不通时兜底。
DEFAULT_COOKIE = (
    'ttwid=1%7C2iDIYVmjzMcpZ20fcaFde0VghXAA3NaNXE_SLR68IyE%7C1761045455'
    '%7Cab35197d5cfb21df6cbb2fa7ef1c9262206b062c315b9d04da746d0b37dfbc7d'
)

_TTWID_TTL = 6 * 3600  # 缓存 6 小时后重新申请
_ttwid_lock = threading.Lock()


def _cache_path() -> str:
    try:
        import tempfile
        return os.path.join(tempfile.gettempdir(), 'douyin_danmaku_ttwid.json')
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), '.ttwid_cache.json')


def _fetch_ttwid(user_agent: str = DEFAULT_USER_AGENT, timeout: int = 15) -> Optional[str]:
    """向抖音申请一个新的 ttwid，两种途径依次尝试，都失败返回 None。"""
    try:
        import requests
    except ImportError:
        return None
    headers = {'user-agent': user_agent}
    try:  # 官方注册接口
        resp = requests.post(
            'https://ttwid.bytedance.com/ttwid/union/register/',
            json={'region': 'cn', 'aid': '6383', 'needFid': 'false',
                  'service': 'https://live.douyin.com', 'migrate_info': '',
                  'cbUrlProtocol': 'https', 'union': 'true'},
            headers=headers, timeout=timeout)
        data = resp.json()
        value = (data.get('data') or {}).get('ttwid') or data.get('ttwid')
        if value:
            return value
    except Exception:
        pass
    try:  # 访问直播首页，从 Set-Cookie 里拿
        resp = requests.get('https://live.douyin.com/', headers=headers, timeout=timeout)
        value = resp.cookies.get('ttwid')
        if value:
            return value
    except Exception:
        pass
    return None


def get_default_cookie(force_refresh: bool = False) -> str:
    """返回可用的 ttwid cookie：优先本地缓存，过期/缺失时自动申请。"""
    path = _cache_path()
    cached = None
    with _ttwid_lock:
        if not force_refresh:
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    cached = json.load(fh)
            except Exception:
                cached = None
        if cached and cached.get('ttwid') and time.time() < cached.get('expire', 0):
            return f"ttwid={cached['ttwid']}"
        value = _fetch_ttwid()
        if value:
            try:
                with open(path, 'w', encoding='utf-8') as fh:
                    json.dump({'ttwid': value, 'expire': time.time() + _TTWID_TTL}, fh)
            except Exception:
                pass
            return f"ttwid={value}"
    if cached and cached.get('ttwid'):
        return f"ttwid={cached['ttwid']}"
    return DEFAULT_COOKIE


def resolve_room_id(value: str) -> tuple:
    """把用户给的分享链接 / web_rid 解析成 WebSocket 需要的真实 room_id。

    抖音网址里那串短数字是 web_rid，弹幕 WebSocket 要的是 enter 接口返回的
    id_str（19 位左右），两者不是一回事。

    返回 (room_id, 主播名)；解析失败时返回 (None, '')。
    """
    text = (value or '').strip()
    nums = re.findall(r'\d{8,25}', text)
    if not nums:
        return None, ''
    num = nums[0]
    if len(num) >= 15:  # 已经是真实 room_id
        return num, ''

    try:
        from .ab_sign import ab_sign
    except Exception:
        ab_sign = None

    params = {'aid': '6383', 'app_name': 'douyin_web', 'live_id': '1',
              'device_platform': 'web', 'language': 'zh-CN', 'browser_language': 'zh-CN',
              'browser_platform': 'Win32', 'browser_name': 'Chrome',
              'browser_version': '116.0.0.0', 'web_rid': num, 'msToken': ''}
    query = urllib.parse.urlencode(params)
    url = 'https://live.douyin.com/webcast/room/web/enter/?' + query
    if ab_sign:
        url += '&a_bogus=' + ab_sign(query, DEFAULT_USER_AGENT)
    try:
        import requests
        resp = requests.get(url, headers={
            'user-agent': DEFAULT_USER_AGENT,
            'referer': 'https://live.douyin.com/',
            'cookie': get_default_cookie(),
        }, timeout=15)
        payload = resp.json()
        rooms = (payload.get('data') or {}).get('data') or []
        room = rooms[0] if rooms else {}
        id_str = room.get('id_str')
        if id_str:
            anchor = (room.get('owner') or {}).get('nickname') or ''
            status = room.get('status')
            if status == 2:
                logger.info(f'「{anchor or num}」正在直播，room_id={id_str}')
            elif status == 4:
                logger.warning(f'「{anchor or num}」当前未开播(status=4)，连上也不会收到消息')
            else:
                logger.warning(f'「{anchor or num}」直播间状态 status={status}，可能已关播')
            return str(id_str), anchor
        logger.warning(f'enter 接口未返回 id_str: {payload.get("status_msg", "")}')
    except Exception as exc:
        logger.warning(f'解析直播间失败({exc})，改用原 ID 直连')
    return num, ''

WS_HOSTS = [
    'webcast100-ws-web-lq.douyin.com',
    'webcast5-ws-web-hl.douyin.com',
    'webcast3-ws-web-hl.douyin.com',
]

BROWSER_VERSION = ('5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

_sign_ctx = None
_sign_ctx_lock = threading.Lock()


def _random_id() -> str:
    return str(random.randint(10 ** 18, 10 ** 19 - 1))


# webmssdk 是字节官方的前端 SDK，面向浏览器编写，直接丢进 Node 会报
# "window is not defined"。这里补一层最小的浏览器环境（本项目原创代码），
# 让它可以脱离浏览器运行，省掉 jsdom 这类重依赖。
BROWSER_POLYFILL = r"""
var window = globalThis;
var self = globalThis;
globalThis.window = window;
if (!window.navigator) {
    window.navigator = {
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
        platform: 'Win32', language: 'zh-CN', languages: ['zh-CN'],
        vendor: 'Google Inc.', appVersion: '5.0', hardwareConcurrency: 8
    };
}
if (!window.screen) window.screen = { width: 1920, height: 1080, colorDepth: 24 };
if (!window.location) {
    window.location = {
        href: 'https://live.douyin.com/', hostname: 'live.douyin.com',
        protocol: 'https:', origin: 'https://live.douyin.com', pathname: '/'
    };
}
if (!window.document) {
    var _el = function () {
        return { style: {}, setAttribute: function () {}, getAttribute: function () { return ''; },
                 appendChild: function () {}, removeChild: function () {}, addEventListener: function () {},
                 getContext: function () { return null; }, toDataURL: function () { return ''; } };
    };
    window.document = {
        createElement: _el, createElementNS: _el, getElementsByTagName: function () { return []; },
        getElementById: function () { return null; }, querySelector: function () { return null; },
        addEventListener: function () {}, head: { appendChild: function () {} },
        body: { appendChild: function () {} }, cookie: '', referrer: ''
    };
}
"""


def _get_sign_ctx():
    """抖音 WS 签名走的是旧版 acrawler 的 get_sign，用 execjs 调 webmssdk 得到。"""
    global _sign_ctx
    with _sign_ctx_lock:
        if _sign_ctx is None:
            import execjs
            with open(JS_SIGN_PATH, 'r', encoding='utf-8') as f:
                _sign_ctx = execjs.compile(BROWSER_POLYFILL + '\n' + f.read())
    return _sign_ctx


def generate_ws_signature(wss_url: str) -> str:
    query = urllib.parse.urlparse(wss_url).query
    wss_maps = {}
    for item in query.split('&'):
        if '=' in item:
            key, value = item.split('=', 1)
            wss_maps[key] = value
    param = ','.join(f'{key}={wss_maps.get(key, "")}' for key in WS_SIGN_PARAMS)
    return _get_sign_ctx().call('get_sign', hashlib.md5(param.encode()).hexdigest())

# 参与字幕生成的消息类型（其余只进 jsonl）
#
# 刻意排除了 member(进场) / like(点赞) / social(关注)：这几类量极大（实测一场里
# 进场能占到六成以上），放进字幕会把真正的评论挤掉——顶部 4 行会被「XX进入直播间」
# 刷满，观众说了什么反而看不到。它们仍完整保留在 jsonl 里，需要的话改这个常量即可。
SUBTITLE_TYPES = ('chat', 'gift', 'emoji')

# 每类消息用什么样式、前缀什么标记。礼物和表情单独一档，画面上一眼能认出来，
# 否则它们混在普通评论里看不出区别。
SUBTITLE_STYLES = {'gift': 'Gift', 'emoji': 'Emoji'}
SUBTITLE_PREFIX = {
    'gift': '【礼物】',
    'emoji': '【表情】',
    'like': '【点赞】',
    'member': '【进场】',
    'social': '【关注】',
}


def subtitle_text(record: dict) -> str:
    """字幕里显示的单行文本（带类型前缀）。stats 类没有发言人也就会有这个分支。"""
    prefix = SUBTITLE_PREFIX.get(record.get('type'), '')
    body = f"{record.get('user', '')}：{record.get('content', '')}" if record.get('type') != 'stats' \
        else record.get('content', '')
    return prefix + body


def _fmt_srt_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = int(seconds % 60)
    ms = int(round(seconds * 1000) % 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def _fmt_ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = int(seconds % 60)
    cs = int(round(seconds * 100) % 100)
    return f'{h:d}:{m:02d}:{s:02d}.{cs:02d}'


def ass_font_name() -> str:
    """ASS 里写死的字体必须真实存在，否则 libass 渲染不出中文。

    Docker/Linux 镜像里没有微软雅黑，直接沿用 Windows 的名字会导致字幕整体不显示；
    这里按平台挑一个确定装了的字体，并在镜像里额外配了 fontconfig 别名兜底。
    """
    if sys.platform.startswith('win'):
        return 'Microsoft YaHei'
    return 'WenQuanYi Micro Hei'


SUBTITLE_FONT_SIZE = 40
_LINE_HEIGHT_RATIO = 1.45


def _escape_ass_text(text: str) -> str:
    """弹幕内容可能含有 ASS 的保留字符，原样写进去会把整行结构搞坏。"""
    return (text or '').replace('\\', '\\\\').replace('{', '(').replace('}', ')').replace('\n', ' ')


def _ass_text_width(text: str, font_size: int = SUBTITLE_FONT_SIZE) -> float:
    """粗略估算文本宽度：中日韩字符按一个字宽算，其余（拉丁字母、数字）按 0.55 字宽算。"""
    width = 0.0
    for ch in text or '':
        width += font_size if ord(ch) > 0x2E7F else font_size * 0.55
    return max(width, font_size * 2) + font_size * 0.5


def render_ass(records: list[dict], ass_path: str, max_lines: int = 4, duration: float = 5.0,
               mode: str = 'scroll', playres: tuple[int, int] = (1920, 1080),
               font_size: int = SUBTITLE_FONT_SIZE, types: tuple | list | None = None,
               gift_min_diamond: float = 0.0) -> tuple[int, int]:
    """把弹幕渲染成 ASS 字幕文件，返回 (写入条数, 丢弃条数)。

    mode='scroll'：弹幕从画面右侧滚动到左侧（用 move 标签），多条在不同轨道上同时飘；
    mode='fixed'：固定在画面顶部，每条停留 duration 秒后换下一条。

    playres 必须与最终视频的分辨率一致：libass 按 PlayRes 与实际画面的比例缩放，
    宽高比对不上时字幕会被拉扁或拉长。
    """
    max_lines = max(1, int(max_lines or 4))
    duration = float(duration or 5.0)
    width, height = int(playres[0]), int(playres[1])
    scroll = str(mode).strip().lower() not in ('fixed', '固定', '0', 'false', 'no')

    if scroll:
        align, margin_v = 7, 0
    else:
        align, margin_v = 8, 36
    font = ass_font_name()
    gift_size = int(font_size * 1.15)
    header = (
        '[Script Info]\n'
        'ScriptType: v4.00+\n'
        f'PlayResX: {width}\n'
        f'PlayResY: {height}\n'
        'WrapStyle: 2\n'
        '\n'
        '[V4+ Styles]\n'
        'Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, '
        'BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
        # 常规弹幕：白字黑描边
        f'Style: Danmaku,{font},{font_size},&H00FFFFFF,&H00000000,&H80000000,'
        f'0,0,1,2,0,{align},0,0,{margin_v},1\n'
        # 礼物：金色加粗、描边更粗
        f'Style: Gift,{font},{gift_size},&H0000D7FF,&H00101010,&H80300000,'
        f'-1,0,1,3,1,{align},0,0,{margin_v},1\n'
        # 表情（抖音小红心/微笑这类动态表情的名字）：浅黄
        f'Style: Emoji,{font},{font_size},&H00A0F0FF,&H00101010,&H80000000,'
        f'0,0,1,2,0,{align},0,0,{margin_v},1\n'
        '\n'
        '[Events]\n'
        'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    )

    line_height = int(font_size * _LINE_HEIGHT_RATIO)
    top_margin = max(12, int(height * 0.03))
    events: list[str] = []
    tracks: list[float] = []  # 每条轨道当前的占用结束时间
    dropped = 0

    allowed = None
    if types:
        allowed = {str(t).strip().lower() for t in types if str(t).strip()}
    min_diamond = float(gift_min_diamond or 0)
    filtered = 0

    for r in records:
        rtype = str(r.get('type') or 'chat').lower()
        if allowed is not None and rtype not in allowed:
            continue
        if rtype == 'gift' and min_diamond > 0:
            try:
                diamond = float(r.get('diamond', 0) or 0)
            except (TypeError, ValueError):
                diamond = 0.0
            if diamond < min_diamond:
                filtered += 1
                continue
        start = float(r.get('offset', 0) or 0)
        style_name = SUBTITLE_STYLES.get(rtype, 'Danmaku')
        text = _escape_ass_text(subtitle_text(r))
        if not text.strip():
            continue
        slot = None
        for i, busy_until in enumerate(tracks):
            if busy_until <= start:
                slot = i
                break
        if slot is None:
            if len(tracks) < max_lines:
                tracks.append(0.0)
                slot = len(tracks) - 1
            else:
                dropped += 1
                continue
        end = start + duration
        prefix = ''
        if scroll:
            text_width = _ass_text_width(text, font_size)
            # 同轨道的两条不能追尾：前一条得先把尾部挪进画面，后一条才能出发，
            # 所需时间占整趟行程的比例正好是「宽度 / 行程总长」
            tracks[slot] = start + duration * text_width / (width + text_width) + 0.25
            y = top_margin + slot * line_height
            prefix = '{\\an7\\move(' + f'{width},{y},{-int(text_width)},{y}' + ')}'
        else:
            tracks[slot] = end
        events.append(
            f'Dialogue: 0,{_fmt_ass_time(start)},{_fmt_ass_time(end)},{style_name},row{slot},0,0,0,,{prefix}{text}'
        )

    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(header + '\n'.join(events) + '\n')
    return len(events), dropped + filtered


def render_ass_from_jsonl(jsonl_path: str, ass_path: str, max_lines: int = 4, duration: float = 5.0,
                          mode: str = 'scroll', playres: tuple[int, int] = (1920, 1080),
                          types: tuple | list | None = None,
                          gift_min_diamond: float = 0.0,
                          font_size: int = SUBTITLE_FONT_SIZE) -> tuple[int, int]:
    """按指定分辨率从 jsonl 重新渲染 ASS。

    录像分辨率不一定是 1080p（抖音竖屏直播很常见），对着不分大小写的画面直接套
    固定分辨率的 ASS 会让字幕拉变形，所以烧录前按实际宽高重渲一遍。
    """
    allowed = tuple(types) if types else SUBTITLE_TYPES
    records = []
    if os.path.exists(jsonl_path):
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if record.get('type') in allowed:
                    records.append(record)
    records.sort(key=lambda r: r.get('offset', 0))
    return render_ass(records, ass_path, max_lines, duration, mode, playres,
                      font_size=font_size, types=allowed, gift_min_diamond=gift_min_diamond)


def clean_base_path(save_file_path: str) -> str:
    """从 ffmpeg 输出路径推出弹幕文件的公共前缀。

    处理分段录制时的 xxx_%03d.ts 这类模板路径。
    """
    base = str(save_file_path)
    base = re.sub(r'_%0\d+d', '', base)          # 去掉分段占位符
    base = re.sub(r'\.[A-Za-z0-9]+$', '', base)  # 去掉扩展名
    return base


class DanmakuRecorder:
    """单个直播间的弹幕抓取器，运行在独立线程里。"""

    def __init__(self, room_id: str, save_file_path: str, anchor_name: str = '',
                 cookie: Optional[str] = None, formats=('json',),
                 proxy: Optional[str] = None, sync_start: Optional[datetime] = None,
                 subtitle_max_lines: int = 4, subtitle_duration: float = 5.0,
                 subtitle_mode: str = 'scroll', playres: tuple[int, int] = (1920, 1080),
                 subtitle_types: tuple | list | None = None, gift_min_diamond: float = 0.0,
                 subtitle_font_size: int = SUBTITLE_FONT_SIZE):
        self.room_id = str(room_id)
        self.anchor_name = anchor_name or self.room_id
        self.formats = [f.strip().lower() for f in formats if f.strip()] or ['json']
        self.cookie = cookie or get_default_cookie()
        self.proxy = proxy
        self.sync_start = sync_start
        # 弹幕只占顶部若干行，避免密集时铺满画面
        self.subtitle_max_lines = max(1, int(subtitle_max_lines or 4))
        self.subtitle_duration = float(subtitle_duration or 5.0)
        # scroll=滚动飘屏 / fixed=顶部固定逐条替换
        self.subtitle_mode = 'fixed' if str(subtitle_mode).strip().lower() in ('fixed', '固定') else 'scroll'
        self.playres = (int(playres[0]), int(playres[1])) if playres else (1920, 1080)
        self.subtitle_types = tuple(str(t).strip().lower() for t in (subtitle_types or SUBTITLE_TYPES) if str(t).strip())
        try:
            self.gift_min_diamond = float(gift_min_diamond or 0)
        except (TypeError, ValueError):
            self.gift_min_diamond = 0.0
        try:
            self.subtitle_font_size = max(12, int(subtitle_font_size or SUBTITLE_FONT_SIZE))
        except (TypeError, ValueError):
            self.subtitle_font_size = SUBTITLE_FONT_SIZE
        self.base_path = clean_base_path(save_file_path)

        self.jsonl_path = f'{self.base_path}.danmaku.jsonl'
        self.srt_path = f'{self.base_path}.danmaku.srt'
        self.ass_path = f'{self.base_path}.danmaku.ass'

        self._stop_event = threading.Event()
        self._ws_host = WS_HOSTS[0]
        self._lock = threading.Lock()
        self._buffer: list[dict] = []
        self._last_flush = 0.0
        self._fh = None
        self._ws = None
        self._internal_ext = ''
        self._base_time: Optional[datetime] = None  # 无 sync_start 时作为时间轴基准
        self._thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self.count = 0

    # ------------------------------------------------------------------ 对外接口

    def start(self) -> bool:
        if websocket is None:
            logger.warning('弹幕抓取未启动：缺少 websocket-client，请执行 pip install websocket-client')
            return False
        if pb is None:
            logger.warning(f'弹幕抓取未启动：protobuf 模块未就绪 -> {_PB_IMPORT_ERROR}')
            return False
        os.makedirs(os.path.dirname(self.base_path) or '.', exist_ok=True)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name=f'danmaku_{self.room_id}', daemon=True)
        self._thread.start()
        logger.info(f'{self.anchor_name} 弹幕抓取已启动，保存至 {self.jsonl_path}')
        return True

    def stop(self) -> None:
        self._stop_event.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._flush(force=True)
        if self._fh:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
        self._write_subtitles()
        logger.info(f'{self.anchor_name} 弹幕抓取已停止，共 {self.count} 条 -> {self.jsonl_path}')

    # ------------------------------------------------------------------ 连接与收包

    def _build_ws_url(self) -> tuple[str, str]:
        now_ms = int(time.time() * 1000)
        user_unique_id = _random_id()
        push_did = _random_id()
        wrds_v = _random_id()
        internal_ext = (
            f'internal_src:dim|wss_push_room_id:{self.room_id}|wss_push_did:{push_did}'
            f'|first_req_ms:{now_ms}|fetch_time:{now_ms}|seq:1|wss_info:0-{now_ms}-0-0|wrds_v:{wrds_v}'
        )
        self._internal_ext = internal_ext

        params = {
            'app_name': 'douyin_web',
            'version_code': '180800',
            'webcast_sdk_version': '1.0.14-beta.0',
            'update_version_code': '1.0.14-beta.0',
            'compress': 'gzip',
            'device_platform': 'web',
            'cookie_enabled': 'true',
            'screen_width': '1536',
            'screen_height': '864',
            'browser_language': 'zh-CN',
            'browser_platform': 'Win32',
            'browser_name': 'Mozilla',
            'browser_version': BROWSER_VERSION,
            'browser_online': 'true',
            'tz_name': 'Asia/Shanghai',
            'cursor': f'd-1_u-1_fh-{push_did}_t-{now_ms}_r-1',
            'internal_ext': internal_ext,
            'host': 'https://live.douyin.com',
            'aid': '6383',
            'live_id': '1',
            'did_rule': '3',
            'endpoint': 'live_pc',
            'support_wrds': '1',
            'user_unique_id': user_unique_id,
            'im_path': '/webcast/im/fetch/',
            'identity': 'audience',
            'need_persist_msg_count': '15',
            'insert_task_id': '',
            'live_reason': '',
            'room_id': self.room_id,
            'heartbeatDuration': '0',
        }
        query = urllib.parse.urlencode(params)
        host = self._ws_host
        wss = f'wss://{host}/webcast/im/push/v2/?{query}'
        try:
            signature = generate_ws_signature(wss)
        except Exception as e:
            logger.warning(f'{self.anchor_name} 弹幕签名生成失败，尝试切换备用方案: {e}')
            signature = ''
        return f'{wss}&signature={signature}', host

    def _proxy_kwargs(self) -> dict:
        if not self.proxy:
            return {}
        try:
            parsed = urllib.parse.urlparse(self.proxy if '://' in self.proxy else f'http://{self.proxy}')
            if not parsed.hostname:
                return {}
            kwargs = {
                'http_proxy_host': parsed.hostname,
                'http_proxy_port': parsed.port or 80,
                'proxy_type': 'https' if parsed.scheme in ('https', 'wss') else 'http',
            }
            return kwargs
        except Exception:
            return {}

    def _run(self) -> None:
        retry = 0
        while not self._stop_event.is_set():
            url, host = self._build_ws_url()
            cookie_header = f'Cookie: {self.cookie}'
            ua_header = f'User-Agent: {DEFAULT_USER_AGENT}'
            origin_header = 'Origin: https://live.douyin.com'
            referer_header = 'Referer: https://live.douyin.com/'

            try:
                self._ws = websocket.WebSocketApp(
                    url,
                    header=[cookie_header, ua_header, origin_header, referer_header],
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(
                    ping_interval=0,
                    reconnect=0,
                    **self._proxy_kwargs(),
                )
            except Exception as e:
                logger.debug(f'弹幕连接异常({host}): {e}')

            if self._stop_event.is_set():
                break

            retry += 1
            # 连不上就换下一个接入点试试
            if retry % 2 == 0:
                self._ws_host = WS_HOSTS[(WS_HOSTS.index(self._ws_host) + 1) % len(WS_HOSTS)]
            if retry > 10:
                logger.warning(f'{self.anchor_name} 弹幕连接连续失败 10 次，停止重试')
                break
            logger.debug(f'{self.anchor_name} 弹幕连接断开，{min(retry * 2, 30)} 秒后重连(第 {retry} 次)')
            if self._stop_event.wait(min(retry * 2, 30)):
                break

    def _on_open(self, ws) -> None:
        logger.debug(f'{self.anchor_name} 弹幕 WebSocket 已连接(room_id={self.room_id})')
        if not self._heartbeat_thread or not self._heartbeat_thread.is_alive():
            self._heartbeat_thread = threading.Thread(target=self._heartbeat, args=(ws,), daemon=True)
            self._heartbeat_thread.start()

    def _on_error(self, ws, error) -> None:
        logger.debug(f'{self.anchor_name} 弹幕连接错误: {error}')

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logger.debug(f'{self.anchor_name} 弹幕连接关闭: {close_status_code} {close_msg}')

    def _heartbeat(self, ws) -> None:
        """抖音 IM 的心跳是一个 payload_type='hb' 的空 PushFrame，必须用 PING 帧发送"""
        while not self._stop_event.is_set():
            if self._stop_event.wait(10):
                break
            try:
                frame = pb.PushFrame()
                frame.payloadType = 'hb'
                ws.send(frame.SerializeToString(), opcode=websocket.ABNF.OPCODE_PING)
            except Exception:
                break

    def _send_ack(self, ws, internal_ext: str) -> None:
        """服务端要求回执时，把 internalExt 原样回传"""
        if pb is None or ws is None:
            return
        frame = pb.PushFrame()
        frame.payloadType = 'ack'
        frame.payload = (internal_ext or '').encode('utf-8')
        try:
            ws.send(frame.SerializeToString(), opcode=websocket.ABNF.OPCODE_BINARY)
        except Exception:
            pass

    def _on_message(self, ws, message) -> None:
        if not isinstance(message, (bytes, bytearray)):
            return
        try:
            frame = pb.PushFrame()
            frame.ParseFromString(bytes(message))
            if frame.payloadType != 'msg':
                return
            # 注意：不能只看 payloadEncoding。实测抖音现在会返回 'pb'，
            # 但 payload 实际仍带 gzip 头(1f8b)，按字段判断会漏解压，
            # 直接把压缩包丢给 protobuf 会报 "Wire format was corrupt"。
            # 这里以 magic number 为准，字段值仅作补充。
            payload = frame.payload
            if payload[:2] == b'\x1f\x8b' or frame.payloadEncoding == 'gzip':
                try:
                    payload = gzip.decompress(payload)
                except Exception:
                    pass

            response = pb.Response()
            response.ParseFromString(payload)

            if response.needAck:
                self._send_ack(ws, response.internalExt)

            for msg in response.messagesList:
                record = self._parse_message(msg)
                if record:
                    self._append(record)
        except Exception as e:
            logger.debug(f'弹幕消息解析失败: {e}')

    # ------------------------------------------------------------------ 消息解析

    def _parse_message(self, msg) -> Optional[dict]:
        method = msg.method
        if not method:
            return None
        try:
            if method == 'WebcastChatMessage':
                m = pb.ChatMessage()
                m.ParseFromString(msg.payload)
                content = m.content or (m.rtfContent.defaultPattern if m.rtfContent else '')
                return self._pack('chat', m.common, m.user, content, extra={})

            if method == 'WebcastEmojiChatMessage':
                m = pb.EmojiChatMessage()
                m.ParseFromString(msg.payload)
                content = m.defaultContent or (m.emojiContent.defaultPattern if m.emojiContent else '[表情]')
                return self._pack('emoji', m.common, m.user, content)

            if method == 'WebcastGiftMessage':
                m = pb.GiftMessage()
                m.ParseFromString(msg.payload)
                gift_name = m.gift.name if m.gift else '礼物'
                count = m.totalCount or m.repeatCount or m.comboCount or 1
                diamond = (m.gift.diamondCount if m.gift else 0) * count
                return self._pack('gift', m.common, m.user, f'送出 {gift_name} x{count}', extra={
                    'gift_name': gift_name,
                    'gift_count': count,
                    'diamond': diamond,
                })

            if method == 'WebcastLikeMessage':
                m = pb.LikeMessage()
                m.ParseFromString(msg.payload)
                return self._pack('like', m.common, m.user, f'点赞 x{m.count or 1}', extra={
                    'like_count': m.count,
                    'like_total': m.total,
                })

            if method == 'WebcastMemberMessage':
                m = pb.MemberMessage()
                m.ParseFromString(msg.payload)
                action_desc = m.actionDescription or ('进入直播间' if m.action == 1 else '关注主播')
                return self._pack('member', m.common, m.user, action_desc, extra={
                    'member_count': m.memberCount,
                    'action': m.action,
                })

            if method == 'WebcastSocialMessage':
                m = pb.SocialMessage()
                m.ParseFromString(msg.payload)
                return self._pack('social', m.common, m.user, f'关注了主播(共 {m.followCount} 人)')

            if method == 'WebcastRoomStatsMessage':
                m = pb.RoomStatsMessage()
                m.ParseFromString(msg.payload)
                return self._pack('stats', m.common, None, f'在线人数 {m.displayValue or m.displayShort}',
                                  extra={'online': m.displayValue})

            if method == 'WebcastMatchAgainstScoreMessage':
                m = pb.MatchAgainstScoreMessage()
                m.ParseFromString(msg.payload)
                a = m.against
                return self._pack('pk', m.common, None,
                                  f'PK {a.leftName or "左"} {a.leftGoalInt} : {a.rightGoalInt} {a.rightName or "右"}',
                                  extra={
                                      'left_name': a.leftName,
                                      'right_name': a.rightName,
                                      'left_score': a.leftGoalInt,
                                      'right_score': a.rightGoalInt,
                                      'match_status': m.matchStatus,
                                  })

            if method == 'WebcastControlMessage':
                m = pb.ControlMessage()
                m.ParseFromString(msg.payload)
                return self._pack('control', m.common, None, f'直播间状态变化 status={m.status}',
                                  extra={'status': m.status})
        except Exception as e:
            logger.debug(f'{method} 解析失败: {e}')
            return None
        return None

    @staticmethod
    def _to_timestamp_ms(value) -> Optional[int]:
        """把时间戳统一成毫秒。

        抖音不同消息的 createTime 单位并不一致：多数是秒(1e9)，
        但 WebcastRoomStatsMessage 给的是毫秒(1e12)，个别是微秒/纳秒。
        不归一化的话 *1000 后会把毫秒放大成 1e18，
        datetime.fromtimestamp 直接抛 OSError [Errno 22] Invalid argument。
        无法识别时返回 None，由调用方用当前时间兜底。
        """
        try:
            v = int(value)
        except (TypeError, ValueError):
            return None
        if v <= 0:
            return None
        if v < 100_000_000_000:  # 秒级
            v *= 1000
        while v > 4_102_444_800_000:  # 微秒 / 纳秒级，逐级缩小
            v //= 1000
        return v

    def _pack(self, msg_type: str, common, user, content: str, extra: Optional[dict] = None) -> dict:
        ts_ms = self._to_timestamp_ms(common.createTime) if common else None
        if ts_ms is None:
            ts_ms = int(time.time() * 1000)
        try:
            dt = datetime.fromtimestamp(ts_ms / 1000)
        except (OSError, ValueError, OverflowError):
            ts_ms = int(time.time() * 1000)
            dt = datetime.fromtimestamp(ts_ms / 1000)
        # 基准时刻：正常录制时是视频开始时刻（main.py 传入 sync_start）。
        # 单独自测时没有这个值，退化成「第一条消息的时间」，
        # 否则所有 offset 都是 0，字幕会全部堆在 0 秒没法用。
        if self.sync_start is not None:
            base = self.sync_start
        else:
            if self._base_time is None:
                self._base_time = dt
            base = self._base_time
        offset = (dt - base).total_seconds()
        record = {
            'type': msg_type,
            'time': dt.strftime('%Y-%m-%d %H:%M:%S'),
            'ts': ts_ms,
            'offset': round(max(offset, 0.0), 3),
            'user': user.nickName if user else '',
            'user_id': str(user.id) if user else '',
            'content': content,
        }
        if extra:
            record.update(extra)
        return record

    # ------------------------------------------------------------------ 落盘

    def _append(self, record: dict) -> None:
        with self._lock:
            self.count += 1
            self._buffer.append(record)
            now = time.time()
            if len(self._buffer) >= 20 or now - self._last_flush >= 5:
                self._flush(force=True)

    def _flush(self, force: bool = False) -> None:
        if not self._buffer:
            return
        if self._fh is None:
            self._fh = open(self.jsonl_path, 'a', encoding='utf-8')
        for record in self._buffer:
            self._fh.write(json.dumps(record, ensure_ascii=False) + '\n')
        self._buffer.clear()
        self._last_flush = time.time()
        try:
            self._fh.flush()
            if force:
                os.fsync(self._fh.fileno())
        except Exception:
            pass

    def _read_records(self) -> list[dict]:
        if not os.path.exists(self.jsonl_path):
            return []
        records = []
        with open(self.jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        return records

    def _write_subtitles(self) -> None:
        if 'srt' not in self.formats and 'ass' not in self.formats:
            return
        records = [r for r in self._read_records() if str(r.get('type') or '').lower() in self.subtitle_types]
        if not records:
            return
        records.sort(key=lambda r: r.get('offset', 0))
        kept = []
        for r in records:
            if str(r.get('type') or '').lower() == 'gift' and self.gift_min_diamond > 0:
                try:
                    diamond = float(r.get('diamond', 0) or 0)
                except (TypeError, ValueError):
                    diamond = 0.0
                if diamond < self.gift_min_diamond:
                    continue
            kept.append(r)
        if not kept:
            return
        if 'srt' in self.formats:
            self._write_srt(kept)
        if 'ass' in self.formats:
            self._write_ass(kept)

    def _write_srt(self, records: list[dict]) -> None:
        lines = []
        display_duration = self.subtitle_duration
        for index, r in enumerate(records, start=1):
            start = r.get('offset', 0)
            end = start + display_duration
            text = subtitle_text(r)
            lines.append(str(index))
            lines.append(f'{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}')
            lines.append(text)
            lines.append('')
        with open(self.srt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        logger.debug(f'弹幕字幕已生成: {self.srt_path}')

    def _write_ass(self, records: list[dict]) -> None:
        """生成 ASS 字幕。默认走滚动飘屏，多轨道并发，具体渲染见 render_ass。"""
        written, dropped = render_ass(
            records, self.ass_path, self.subtitle_max_lines, self.subtitle_duration,
            self.subtitle_mode, self.playres,
            font_size=self.subtitle_font_size,
            types=self.subtitle_types, gift_min_diamond=self.gift_min_diamond,
        )
        logger.debug(
            f'弹幕 ASS 字幕已生成: {self.ass_path}'
            f'(写入 {written} 条，'
            + ('飘屏滚动' if self.subtitle_mode == 'scroll' else '顶部固定')
            + f'，最多 {self.subtitle_max_lines} 行'
            + (f'，因轨道占满丢弃 {dropped} 条' if dropped else '')
            + ')'
        )


# ---------------------------------------------------------------------- 会话管理

_sessions: dict[str, DanmakuRecorder] = {}
_sessions_lock = threading.Lock()


def start_danmaku(room_id: str, save_file_path: str, anchor_name: str = '',
                  cookie: Optional[str] = None, formats=('json',),
                  proxy: Optional[str] = None, sync_start: Optional[datetime] = None,
                  subtitle_max_lines: int = 4, subtitle_duration: float = 5.0,
                  subtitle_mode: str = 'scroll', playres: tuple[int, int] = (1920, 1080),
                  subtitle_types: tuple | list | None = None,
                  gift_min_diamond: float = 0.0,
                  subtitle_font_size: int = SUBTITLE_FONT_SIZE) -> bool:
    key = os.path.abspath(clean_base_path(save_file_path))
    with _sessions_lock:
        if key in _sessions:
            return False
        recorder = DanmakuRecorder(room_id, save_file_path, anchor_name, cookie, formats, proxy, sync_start,
                                   subtitle_max_lines, subtitle_duration, subtitle_mode, playres,
                                   subtitle_types, gift_min_diamond, subtitle_font_size)
        ok = recorder.start()
        if ok:
            _sessions[key] = recorder
        return ok


def stop_danmaku(save_file_path: str) -> None:
    key = os.path.abspath(clean_base_path(save_file_path))
    with _sessions_lock:
        recorder = _sessions.pop(key, None)
    if recorder:
        recorder.stop()


def stop_all_danmaku() -> None:
    with _sessions_lock:
        recorders = list(_sessions.values())
        _sessions.clear()
    for recorder in recorders:
        try:
            recorder.stop()
        except Exception:
            pass


if __name__ == '__main__':
    # 自测：python -m src.danmaku <room_id|直播链接> [--seconds 30]
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='抖音直播弹幕抓取自测')
    parser.add_argument('room_id', help='直播间真实 room_id，或 https://live.douyin.com/xxx 链接')
    parser.add_argument('--seconds', type=int, default=30, help='抓取时长，默认 30 秒')
    parser.add_argument('--out', default='./danmaku_test.ts', help='输出文件路径前缀')
    args = parser.parse_args()

    room_id, anchor = resolve_room_id(args.room_id)
    if not room_id:
        logger.error('无法解析直播间，请检查链接或 room_id 是否正确')
        sys.exit(1)
    logger.info(f'直播间: {anchor or room_id} (room_id={room_id})')

    rec = DanmakuRecorder(room_id, args.out, anchor or room_id, formats=('json', 'srt', 'ass'))
    if not rec.start():
        sys.exit(1)
    try:
        import time as _time
        _time.sleep(args.seconds)
    except KeyboardInterrupt:
        pass
    rec.stop()
    print(f'共抓取 {rec.count} 条 -> {rec.jsonl_path}')
