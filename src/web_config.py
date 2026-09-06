# src/web_config.py
# Web 管理面板：配置读取与 URL_config.ini 解析/格式化的纯函数模块。
# 不依赖 FastAPI / 网络，便于单测。
from __future__ import annotations

import base64
import configparser
import functools
import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path
from typing import Iterable, cast

# 与 main.py 保持一致的文本编码
TEXT_ENCODING = "utf-8-sig"

# 内置画质档位全集（对齐 main.py 画质白名单与 src/stream_select.get_quality_code）。
# 元组顺序即 WEB 下拉与 GUI 切换菜单的展示顺序（自高画质到低画质）。
BUILTIN_QUALITIES: tuple[str, ...] = (
    "原画",
    "蓝光",
    "蓝光30M",
    "蓝光20M",
    "蓝光8M",
    "蓝光4M",
    "超清",
    "高清",
    "标清",
    "流畅",
)

# 画质关键词（历史别名，成员判定用；与 BUILTIN_QUALITIES 同一集合）
QUALITY_KEYWORDS = BUILTIN_QUALITIES

# 画质选项在 config.ini 中的落盘位置：[录制设置] 自定义画质选项(逗号分隔)
QUALITY_OPTIONS_SECTION = "录制设置"
QUALITY_OPTIONS_KEY = "自定义画质选项(逗号分隔)"

# 与 main.py CLEAN_URL_HOST_LIST 一致：这些 host 的 URL 去除 query string
CLEAN_URL_HOST_LIST = (
    "live.douyin.com",
    "live.bilibili.com",
    "www.huajiao.com",
    "www.zhihu.com",
    "www.huya.com",
    "chzzk.naver.com",
    "www.liveme.com",
    "www.haixiutv.com",
    "v.6.cn",
    "m.6.cn",
    "www.lehaitv.com",
)

# 默认画质（对齐 main.py）
DEFAULT_QUALITY = "原画"

# Web 配置默认值
WEB_DEFAULTS: dict[str, str | int | bool] = {
    "web_host": "127.0.0.1",
    "web_port": 8000,
    "web_auth_enable": False,
    "web_password": "",
    "web_token_expiry": 86400,
    "web_show_console": True,
    "web_minimize_to_tray": True,
    # 可信代理列表（逗号分隔）：仅当直连对端在列表中才信任 X-Forwarded-For
    "web_trusted_proxy": "",
}


def normalize_url(url: str) -> str:
    # 规范化 URL：补 https://，并对 CLEAN_URL_HOST_LIST 的 host 去除 query。
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        host = url.split("/", 3)[2]
    except IndexError:
        return url
    if host in CLEAN_URL_HOST_LIST:
        url = url.split("?")[0]
    return url


def parse_url_config(file_path: str | Path) -> list[dict[str, str | bool]]:
    # 解析 URL_config.ini，返回直播间列表。
    # 每项: {url, quality, name, enabled, raw_line}
    # 行格式: [画质,]URL[,主播: 名称]，# 前缀表示注释（禁用）。
    rooms: list[dict[str, str | bool]] = []
    path = Path(file_path)
    if not path.exists():
        return rooms

    with path.open("r", encoding=TEXT_ENCODING, errors="ignore") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n").rstrip("\r")
            stripped = line.strip()
            if not stripped:
                continue

            enabled = True
            content = stripped
            if content.startswith("#"):
                enabled = False
                content = content.lstrip("#").strip()

            parts = re.split(r"[,，]", content)

            quality = DEFAULT_QUALITY
            url = ""
            name = ""

            if len(parts) == 1:
                url = parts[0].strip()
            elif len(parts) == 2:
                if _is_url(parts[0]):
                    url = parts[0].strip()
                    name = parts[1].strip()
                else:
                    quality = _normalize_quality(parts[0].strip())
                    url = parts[1].strip()
            else:
                quality = _normalize_quality(parts[0].strip())
                url = parts[1].strip()
                name = " ".join(p.strip() for p in parts[2:])

            if name.startswith("主播:"):
                name = name[len("主播:") :].strip()
            elif name.startswith("主播："):
                name = name[len("主播：") :].strip()

            if not url:
                continue

            url = normalize_url(url)
            rooms.append(
                {
                    "url": url,
                    "quality": quality,
                    "name": name,
                    "enabled": enabled,
                    "raw_line": raw_line,
                }
            )
    return rooms


def _is_url(s: str) -> bool:
    return "://" in s or "." in s


def _normalize_quality(q: str) -> str:
    q = q.strip()
    return q if q in QUALITY_KEYWORDS else DEFAULT_QUALITY


def _reject_newline(kind: str, value: str) -> None:
    # 换行注入防护：URL_config.ini 行级格式，任何字段含换行即可伪造额外配置行
    if value and ("\n" in value or "\r" in value):
        raise ValueError(f"{kind} 含换行符，禁止写入配置文件")


def format_url_line(url: str, quality: str | None = None, name: str | None = None) -> str:
    # 格式化一行 URL_config.ini 内容（不含换行）。
    # - 仅 URL：返回 url
    # - 画质+URL：返回 "画质,url"
    # - 全部：返回 "画质,url,主播: 名称"
    # quality 为空或默认"原画"时省略画质段（与 main.py 风格一致）。
    _reject_newline("URL", url)
    _reject_newline("画质", quality or "")
    _reject_newline("主播名", name or "")
    url = normalize_url(url)
    parts: list[str] = []
    q = (quality or "").strip()
    if q and q != DEFAULT_QUALITY:
        parts.append(q)
    parts.append(url)
    n = (name or "").strip()
    if n:
        parts.append(f"主播: {n}")
    return ",".join(parts)


def validate_config_target(section: str, key: str, value: str) -> None:
    # 校验 /api/config 写入目标：值含换行即拒绝（同换行注入防护，避免伪造配置行）
    _reject_newline(f"配置项 [{section}] {key} 的值", value)


def validate_room_target(url: str, quality: str | None = None, name: str | None = None) -> None:
    # 校验房间写入目标（URL/画质/主播名均不得含换行）
    _reject_newline("URL", url)
    _reject_newline("画质", quality or "")
    _reject_newline("主播名", name or "")


# ─── 画质选项（WEB 下拉 / GUI 切换菜单共用，落地 config.ini） ────────────────


# 拆分逗号分隔的多值配置（支持全角逗号），逐项 strip 并丢弃空项
def _split_multi_value(raw: str) -> list[str]:
    return [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]


# 规范化画质选项：仅保留内置档位并去重（保持传入顺序），结果为空时回退内置全集。
# 为什么不放开任意名称：main.py 对行首画质段做白名单校验，白名单外的名称会被静默
# 回退成「原画」，让用户勾选一个永远不生效的档位比不给他选更糟。
def normalize_quality_options(options: Iterable[str]) -> list[str]:
    result: list[str] = []
    for item in options:
        name = (item or "").strip()
        if name in BUILTIN_QUALITIES and name not in result:
            result.append(name)
    return result or list(BUILTIN_QUALITIES)


# 读取用户勾选的画质选项；键缺失/为空/全部非法时回退内置全集（首次使用行为不变）
def read_quality_options(config_file: str | Path) -> list[str]:
    parser = configparser.ConfigParser(interpolation=None)
    _ = parser.read(config_file, encoding=TEXT_ENCODING)
    raw = ""
    if parser.has_section(QUALITY_OPTIONS_SECTION):
        raw = parser.get(QUALITY_OPTIONS_SECTION, QUALITY_OPTIONS_KEY, fallback="")
    return normalize_quality_options(_split_multi_value(raw))


# 写回画质选项（行级更新，保留注释与节顺序）；返回实际落盘的规范化列表
def write_quality_options(config_file: str | Path, options: Iterable[str]) -> list[str]:
    # 换行注入防护必须在 normalize 之前做：normalize 会把含换行的项静默丢掉，
    # 那时再校验就感知不到了（C3 与 format_url_line 同款）
    raw_list = list(options)
    for item in raw_list:
        _reject_newline("画质选项", str(item))
    normalized = normalize_quality_options(raw_list)
    value = ",".join(normalized)
    _reject_newline("画质选项", value)
    if not update_config_line(config_file, QUALITY_OPTIONS_SECTION, QUALITY_OPTIONS_KEY, value):
        # 键缺失（历史 config.ini 无此项）：补建到目标节内，不改其余内容
        _ = append_config_line(config_file, QUALITY_OPTIONS_SECTION, QUALITY_OPTIONS_KEY, value)
    return normalized


# ─── URL_config.ini 房间画质保序改写 ──────────────────────────────────────


# 段是否像网址（仅需区分画质槽位与 URL 段，故只判 scheme，不用完整 URL 正则）
def _looks_like_url(segment: str) -> bool:
    return "://" in segment


# 段级 URL 匹配：配置行里的 URL 段可能缺 scheme 或带 query，统一规范化后比较，
# 避免 "live.douyin.com/1" 与 "https://live.douyin.com/1" 判为两行。
# 主播名字段直接排除——即便它含点号也不会被 normalize_url 误判成网址。
def _segment_matches_url(segment: str, url: str) -> bool:
    seg = segment.strip()
    if not seg or seg.startswith(("主播:", "主播：")):
        return False
    return seg == url or normalize_url(seg) == url


# 重写单行配置的画质段；行不匹配 URL 或已是目标画质时返回 None（无需变更）。
# 行格式: [画质,]URL[,主播: 名称]——画质槽位是 URL 段之前的那一段（与 main.py 的行
# 解析约定一致），注释前缀、行尾换行、主播名字段与 URL 原文全部保留。
def _rewrite_quality_field(raw_line: str, url: str, quality: str) -> str | None:
    stripped = raw_line.rstrip("\r\n")
    eol = raw_line[len(stripped) :]
    comment_prefix = ""
    body = stripped
    # 行首可有缩进 + `#` + 可选空白；完整前缀（含 `#` 与其后的空格）一并保留，
    # 避免 `# 注释` 被改写成 `#注释` 这种风格损坏
    m = re.match(r"^(\s*#\s*)", body)
    if m:
        comment_prefix = m.group(1)
        body = body[m.end() :]
    if not body.strip():
        return None

    segments = [seg.strip() for seg in re.split(r"[,，]", body)]
    url_idx = -1
    for i, seg in enumerate(segments):
        if _segment_matches_url(seg, url):
            url_idx = i
            break
    if url_idx < 0:
        return None

    # 目标画质：空或默认「原画」时移除画质段，让该房间回落到全局默认画质
    target_q = quality if quality and quality != DEFAULT_QUALITY else ""
    # 画质槽位：URL 段之前的首段。该段本身像网址时（异常行 "URL1,URL2"）不动它，
    # 避免把数据当成画质静默吞掉
    slot_idx = url_idx - 1 if url_idx > 0 and not _looks_like_url(segments[0]) else -1
    if (segments[slot_idx] if slot_idx >= 0 else "") == target_q:
        return None  # 已是目标画质，幂等跳过

    keep = [seg for i, seg in enumerate(segments) if i not in (url_idx, slot_idx) and seg]
    rebuilt_parts: list[str] = []
    if target_q:
        rebuilt_parts.append(target_q)
    rebuilt_parts.append(segments[url_idx])
    rebuilt_parts.extend(keep)
    return f"{comment_prefix}{','.join(rebuilt_parts)}{eol}"


# 将 URL_config.ini 中指定 URL 所在行的画质段更新为 quality；返回是否发生变更。
# quality 为空或等于 DEFAULT_QUALITY 时移除画质段（写为 "URL[,主播: 名称]"）；
# 否则按「画质,URL[,主播: 名称]」写入（如 "超清,https://live.douyin.com/745964462470"）。
# 未命中 URL / 已是目标画质 / 文件不存在均返回 False。
# 原子写（临时文件 + os.replace）：与录制子进程无跨进程锁，避免读到半写内容。
def update_room_quality(url_config_file: str | Path, url: str, quality: str | None) -> bool:
    if not url:
        return False
    target = normalize_url(url)
    new_quality = (quality or "").strip()
    _reject_newline("画质", new_quality)

    path = Path(url_config_file)
    if not path.exists():
        return False
    # newline=""：读/写均不做换行符翻译，保留文件原有的 \n / \r\n 行尾风格
    with path.open("r", encoding=TEXT_ENCODING, newline="") as f:
        lines = f.readlines()

    changed = False
    out_lines: list[str] = []
    for raw_line in lines:
        rewritten = _rewrite_quality_field(raw_line, target, new_quality)
        if rewritten is not None:
            changed = True
            out_lines.append(rewritten)
        else:
            out_lines.append(raw_line)
    if not changed:
        return False

    joined = "".join(out_lines)
    _atomic_write_text(path, joined)
    return True


# 原子写文本：同目录临时文件写完后 os.replace 覆盖，读方只会看到旧/新完整内容
def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding=TEXT_ENCODING, newline="") as f:
        _ = f.write(text)
    try:
        os.replace(tmp, path)
    except OSError:
        # 覆盖失败（文件被占用 / 只读）时清理临时文件，避免残留垃圾
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


# 按主播名反查直播间地址（GUI 画质监控行以主播名为键，写回配置需要 URL）。
# 精确命中优先；未命中返回空串，由调用方决定降级行为（如禁用该行切换菜单）。
def find_room_url_by_anchor_name(url_config_file: str | Path, anchor_name: str) -> str:
    target = (anchor_name or "").strip()
    if not target:
        return ""
    rooms = parse_url_config(url_config_file)
    for room in rooms:
        if str(room["name"]).strip() == target:
            return str(room["url"])
    # 兜底：主播名含全角/半角差异或多个主播名段时，退化为行内子串匹配
    for room in rooms:
        if target in str(room["name"]):
            return str(room["url"])
    return ""


def read_web_config(config_file: str | Path) -> dict[str, str | int | bool]:
    # 读取 [Web] 节配置，缺失项用默认值填充。
    parser = configparser.ConfigParser(interpolation=None)
    _ = parser.read(config_file, encoding=TEXT_ENCODING)
    result: dict[str, str | int | bool] = {}
    for key, default in WEB_DEFAULTS.items():
        if not parser.has_section("Web"):
            result[key] = default
            continue
        raw = parser.get("Web", key, fallback=str(default))
        if isinstance(default, bool):
            result[key] = raw.strip().lower() in ("true", "1", "yes", "是")
        elif isinstance(default, int):
            try:
                result[key] = int(raw)
            except ValueError, TypeError:
                result[key] = default
        else:
            result[key] = raw
    return result


SENSITIVE_SECTIONS = {"Cookie", "账号密码", "Authorization"}
SENSITIVE_MASK = "***"


def read_config_safe(config_file: str | Path) -> dict[str, dict[str, str]]:
    # 读取 config.ini 全部节键值，敏感节非空值脱敏为 '***'。
    # 用于 API 返回前端展示；写入仍用 utils.update_config。
    # Web 节单独对 web_password 脱敏（其他 Web 键需可编辑，故不整节脱敏）。
    parser = configparser.ConfigParser(interpolation=None)
    _ = parser.read(config_file, encoding=TEXT_ENCODING)
    result: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        items: dict[str, str] = {}
        for key, value in parser.items(section):
            if section in SENSITIVE_SECTIONS and value.strip():
                items[key] = SENSITIVE_MASK
            elif section == "Web" and key == "web_password" and value.strip():
                items[key] = SENSITIVE_MASK
            else:
                items[key] = value
        result[section] = items
    return result


# 按 key 缓存编译后的行匹配模式：模式串依赖 key，无法整体预编译，但同 key 反复更新时应复用。
# maxsize 取 128，远超配置文件键数量，命中率接近 100%。
@functools.lru_cache(maxsize=128)
def _key_line_pattern(key: str) -> re.Pattern[str]:
    # 匹配 key 行：允许 = 或 ：或 : 分隔，key 前后空白（大小写不敏感）
    return re.compile(r"^(\s*" + re.escape(key) + r"\s*[=:：]\s*)(.*)$", re.IGNORECASE)


def update_config_line(config_file: str | Path, section: str, key: str, value: str) -> bool:
    # 注释保留的行级配置更新。
    # 逐行扫描：进入目标 section 后，匹配 `^\\s*key\\s*[=：:]\\s*` 的行并替换其值；
    # 未找到 section 或 key 时返回 False（不写入）。
    # 保留所有注释、空行、节顺序与原分隔符风格。
    # key 匹配大小写不敏感：configparser 读取侧经 optionxform 统一小写，
    # 代码内常量（如「禁用SSL证书验证的平台」）与配置文件实际行（小写 ssl）
    # 大小写不一致时仍应可定位（与 configparser 语义对齐）。
    path = Path(config_file)
    if not path.exists():
        return False
    lines: list[str] = path.read_text(encoding=TEXT_ENCODING).splitlines(keepends=True)
    cur_section: str | None = None
    in_target = False
    replaced = False
    key_pattern = _key_line_pattern(key)
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        # section header: [name]
        if stripped.startswith("[") and stripped.endswith("]"):
            cur_section = stripped[1:-1].strip()
            in_target = cur_section == section
            new_lines.append(line)
            continue
        if in_target and not replaced:
            m = key_pattern.match(line.rstrip("\n").rstrip("\r"))
            if m:
                prefix = m.group(1)  # "key = " 部分
                old_tail = m.group(2)  # 原值（可能含行内注释）
                # 检测行内注释：首个 " #" 或 " ;"（前置空白），保留注释部分
                inline_comment = ""
                for marker in (" #", " ;"):
                    idx = old_tail.find(marker)
                    if idx > 0:  # >0 表示前面有非空内容（不是行首注释）
                        inline_comment = old_tail[idx:]
                        break
                # 保留原行尾换行符
                eol = "\n" if line.endswith("\n") else ("\r\n" if line.endswith("\r\n") else "")
                new_lines.append(f"{prefix}{value}{inline_comment}{eol}")
                replaced = True
                continue
        new_lines.append(line)
    if not replaced:
        return False
    _ = path.write_text("".join(new_lines), encoding=TEXT_ENCODING)
    return True


def append_config_line(config_file: str | Path, section: str, key: str, value: str) -> bool:
    # 缺键补建的行级追加：update_config_line 只做替换、键或节缺失时返回 False
    # （如历史 config.ini 没有 `language` 键，Web 先于引擎首轮读配置时切换语言），
    # 本函数把 `key = value` 插入目标 section 内；节不存在时于文件尾新建。
    # 与 update_config_line 相同的行级文本风格：注释、空行、节顺序与其余内容全部保留。
    path = Path(config_file)
    if not path.exists():
        return False
    lines: list[str] = path.read_text(encoding=TEXT_ENCODING).splitlines(keepends=True)
    insert_at: int | None = None  # 目标节内的插入点（下一节头之前）；None＝文件尾
    in_section = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not (stripped.startswith("[") and stripped.endswith("]")):
            continue
        name = stripped[1:-1].strip()
        if in_section:
            insert_at = idx  # 走到下一节头部即目标节结束
            break
        if name == section:
            in_section = True
    # 末行无尾换行时先补一个：无论插入文件中间还是尾部，都不得与原内容粘连成一行
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    entry = f"{key} = {value}\n"
    if in_section:
        lines.insert(insert_at if insert_at is not None else len(lines), entry)
    else:
        lines.append(f"[{section}]\n{entry}")
    _ = path.write_text("".join(lines), encoding=TEXT_ENCODING)
    return True


# === Web 登录密码哈希（PBKDF2-HMAC-SHA256）===
# 存储格式：pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>
# 落地配置只保存哈希，不保存明文；历史明文配置在首次登录时自动升级。
_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 200_000


def hash_web_password(plaintext: str) -> str:
    # 将明文密码派生为带随机盐的哈希串，用于安全存储（避免明文落盘）。
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_ALGO}${_PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def is_hashed_web_password(value: str) -> bool:
    # 判断存储值是否已是哈希格式（而非历史明文）。
    return bool(value) and value.startswith(f"{_PBKDF2_ALGO}$")


def verify_web_password(plaintext: str, stored: str) -> bool:
    # 校验密码：stored 为哈希串时按 PBKDF2 校验；历史明文也允许直接比较以兼容升级前配置。
    if not stored:
        return False
    if is_hashed_web_password(stored):
        try:
            _, iters_s, salt_b64, hash_b64 = stored.split("$")
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(hash_b64)
            dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode("utf-8"), salt, int(iters_s))
        except ValueError:
            # 哈希串损坏/迭代数非法（base64.b64decode 的 binascii.Error 亦为 ValueError 子类）：
            # 视为校验失败而非崩溃
            return False
        return hmac.compare_digest(dk, expected)
    # 兼容历史明文存储。必须先编码再比较：compare_digest 对含非 ASCII 字符的 str
    # 直接抛 TypeError（历史明文密码含中文时 /api/login 会 500），bytes 比较无此限制
    return hmac.compare_digest(plaintext.encode("utf-8"), stored.encode("utf-8"))
