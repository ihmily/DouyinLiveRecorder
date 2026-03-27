import hashlib
import re
import urllib.parse


OptionalStr = str | None


def get_params(url: str, params: str) -> OptionalStr:
    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    if params in query_params:
        return query_params[params][0]

    return None


def is_taobao_live_url(url: str) -> bool:
    return any(marker in url for marker in ("tb.cn", "tbzb.taobao.com/live"))


def get_taobao_live_id(url: str) -> OptionalStr:
    return get_params(url, "liveId") or get_params(url, "id")


def get_cookie_value(cookie_str: str, key: str) -> OptionalStr:
    match = re.search(rf"(?:^|;\s*){re.escape(key)}=([^;]+)", cookie_str)
    return match.group(1) if match else None


def merge_cookie_header(cookie_str: str, new_cookie: dict | None) -> str:
    if not new_cookie:
        return cookie_str

    cookie_dict: dict[str, str] = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        cookie_dict[key] = value

    cookie_dict.update(new_cookie)
    return "; ".join(f"{key}={value}" for key, value in cookie_dict.items())


def build_taobao_sign(token: str, t13: int, data: str) -> str:
    raw = f"{token.split('_', 1)[0]}&{t13}&12574478&{data}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()
