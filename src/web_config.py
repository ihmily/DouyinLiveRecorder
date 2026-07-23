# src/web_config.py
# Web 管理面板：配置读取与 URL_config.ini 解析/格式化的纯函数模块。
# 不依赖 FastAPI / 网络，便于单测。
from __future__ import annotations

import configparser
import re
from pathlib import Path
from typing import Any

# 与 main.py 保持一致的文本编码
TEXT_ENCODING = "utf-8-sig"

# 画质关键词（对齐 main.py get_quality_code）
QUALITY_KEYWORDS = ("原画", "蓝光", "超清", "高清", "标清", "流畅")

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
WEB_DEFAULTS: dict[str, Any] = {
    "web_host": "0.0.0.0",
    "web_port": 8000,
    "web_auth_enable": False,
    "web_password": "",
    "web_token_expiry": 86400,
}


def normalize_url(url: str) -> str:
    """规范化 URL：补 https://，并对 CLEAN_URL_HOST_LIST 的 host 去除 query。"""
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


def parse_url_config(file_path: str | Path) -> list[dict[str, Any]]:
    """解析 URL_config.ini，返回直播间列表。

    每项: {url, quality, name, enabled, raw_line}
    行格式: [画质,]URL[,主播: 名称]，# 前缀表示注释（禁用）。
    """
    rooms: list[dict[str, Any]] = []
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
                name = name[len("主播:"):].strip()
            elif name.startswith("主播："):
                name = name[len("主播："):].strip()

            if not url:
                continue

            url = normalize_url(url)
            rooms.append({
                "url": url,
                "quality": quality,
                "name": name,
                "enabled": enabled,
                "raw_line": raw_line,
            })
    return rooms


def _is_url(s: str) -> bool:
    return "://" in s or "." in s


def _normalize_quality(q: str) -> str:
    q = q.strip()
    return q if q in QUALITY_KEYWORDS else DEFAULT_QUALITY


def format_url_line(url: str, quality: str | None = None, name: str | None = None) -> str:
    """格式化一行 URL_config.ini 内容（不含换行）。

    - 仅 URL：返回 url
    - 画质+URL：返回 "画质,url"
    - 全部：返回 "画质,url,主播: 名称"
    quality 为空或默认"原画"时省略画质段（与 main.py 风格一致）。
    """
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


def read_web_config(config_file: str | Path) -> dict[str, Any]:
    """读取 [Web] 节配置，缺失项用默认值填充。"""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config_file, encoding=TEXT_ENCODING)
    result: dict[str, Any] = {}
    for key, default in WEB_DEFAULTS.items():
        if not parser.has_section("Web"):
            result[key] = default
            continue
        raw = parser.get("Web", key, fallback=str(default))
        if isinstance(default, bool):
            result[key] = str(raw).strip().lower() in ("true", "1", "yes", "是")
        elif isinstance(default, int):
            try:
                result[key] = int(raw)
            except (ValueError, TypeError):
                result[key] = default
        else:
            result[key] = str(raw)
    return result


SENSITIVE_SECTIONS = {"Cookie", "账号密码", "Authorization"}
SENSITIVE_MASK = "***"


def read_config_safe(config_file: str | Path) -> dict[str, dict[str, str]]:
    """读取 config.ini 全部节键值，敏感节非空值脱敏为 '***'。

    用于 API 返回前端展示；写入仍用 utils.update_config。
    Web 节单独对 web_password 脱敏（其他 Web 键需可编辑，故不整节脱敏）。
    """
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config_file, encoding=TEXT_ENCODING)
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


def update_config_line(
    config_file: str | Path, section: str, key: str, value: str
) -> bool:
    """注释保留的行级配置更新。

    逐行扫描：进入目标 section 后，匹配 `^\\s*key\\s*[=：:]\\s*` 的行并替换其值；
    未找到 section 或 key 时返回 False（不写入）。
    保留所有注释、空行、节顺序与原分隔符风格。
    """
    path = Path(config_file)
    if not path.exists():
        return False
    lines = path.read_text(encoding=TEXT_ENCODING).splitlines(keepends=True)
    cur_section: str | None = None
    in_target = False
    replaced = False
    # 匹配 key 行：允许 = 或 ：或 : 分隔，key 前后空白
    key_pattern = re.compile(r'^(\s*' + re.escape(key) + r'\s*[=:：]\s*)(.*)$')
    new_lines = []
    for line in lines:
        stripped = line.strip()
        # section header: [name]
        if stripped.startswith('[') and stripped.endswith(']'):
            cur_section = stripped[1:-1].strip()
            in_target = (cur_section == section)
            new_lines.append(line)
            continue
        if in_target and not replaced:
            m = key_pattern.match(line.rstrip('\n').rstrip('\r'))
            if m:
                # 保留原行尾换行符
                eol = '\n' if line.endswith('\n') else ('\r\n' if line.endswith('\r\n') else '')
                new_lines.append(f"{m.group(1)}{value}{eol}")
                replaced = True
                continue
        new_lines.append(line)
    if not replaced:
        return False
    path.write_text(''.join(new_lines), encoding=TEXT_ENCODING)
    return True
