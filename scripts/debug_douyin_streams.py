# -*- coding: utf-8 -*-
import asyncio
import argparse
import configparser
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import spider, stream
from src.ab_sign import ab_sign
from src.http_clients.async_http import async_req


CONFIG_FILE = ROOT / "config" / "config.ini"
URL_CONFIG_FILE = ROOT / "config" / "URL_config.ini"


UA_PROFILES = {
    "project_qqbrowser_116": {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/116.0.5845.97 Safari/537.36 "
            "Core/1.116.567.400 QQBrowser/19.7.6764.400"
        ),
        "browser_name": "Chrome",
        "browser_version": "116.0.0.0",
        "browser_platform": "Win32",
    },
    "chrome_win_141": {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        ),
        "browser_name": "Chrome",
        "browser_version": "141.0.0.0",
        "browser_platform": "Win32",
        "extra_headers": {
            "accept": "application/json, text/plain, */*",
            "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        },
    },
    "edge_win_141": {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"
        ),
        "browser_name": "Chrome",
        "browser_version": "141.0.0.0",
        "browser_platform": "Win32",
    },
    "chrome_mac_141": {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        ),
        "browser_name": "Chrome",
        "browser_version": "141.0.0.0",
        "browser_platform": "MacIntel",
        "extra_headers": {
            "accept": "application/json, text/plain, */*",
            "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        },
    },
    "safari_mac_18": {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/18.0 Safari/605.1.15"
        ),
        "browser_name": "Safari",
        "browser_version": "18.0.0.0",
        "browser_platform": "MacIntel",
    },
}


def read_cookie() -> str:
    config = configparser.RawConfigParser()
    config.read(CONFIG_FILE, encoding="utf-8-sig")
    return config.get("Cookie", "抖音cookie", fallback="")


def read_tuniang_url() -> str:
    for line in URL_CONFIG_FILE.read_text(encoding="utf-8-sig").splitlines():
        if "兔娘" in line:
            return line.split(",", 1)[0].strip()
    raise RuntimeError("URL_config.ini 里没有找到兔娘直播地址")


async def fetch_douyin_web_stream_data_with_profile(
        url: str,
        cookies: str,
        profile: dict,
        proxy_addr: str | None = None,
) -> dict:
    headers = {
        "cookie": cookies,
        "referer": "https://live.douyin.com/",
        "user-agent": profile["user_agent"],
    }
    headers.update(profile.get("extra_headers", {}))
    web_rid = url.split("?", 1)[0].split("live.douyin.com/")[-1]
    params = {
        "aid": "6383",
        "app_name": "douyin_web",
        "live_id": "1",
        "device_platform": "web",
        "language": "zh-CN",
        "browser_language": "zh-CN",
        "browser_platform": profile["browser_platform"],
        "browser_name": profile["browser_name"],
        "browser_version": profile["browser_version"],
        "web_rid": web_rid,
        "msToken": "",
    }
    api = f"https://live.douyin.com/webcast/room/web/enter/?{urllib.parse.urlencode(params)}"
    api += "&a_bogus=" + ab_sign(urllib.parse.urlparse(api).query, headers["user-agent"])

    json_str = await async_req(url=api, proxy_addr=proxy_addr, headers=headers)
    if not json_str:
        raise RuntimeError("empty response")
    json_data = json.loads(json_str)["data"]
    if not json_data["data"]:
        raise RuntimeError("response data.data is empty")

    room_data = json_data["data"][0]
    room_data["anchor_name"] = json_data["user"]["nickname"]
    return room_data


def load_sdk_params(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"_raw": value}
    return {}


def summarize_url(url: str) -> str:
    parsed = urlparse(url or "")
    query = parse_qs(parsed.query)
    kept = []
    for key in ("codec", "abr_pts", "ratio", "wsSecret", "txSecret"):
        if key in query:
            kept.append(f"{key}={query[key][0]}")
    suffix = f"?{'&'.join(kept)}" if kept else ""
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}{suffix}"


def print_sdk(label: str, sdk_params: dict, url: str | None = None) -> None:
    fields = {
        "VCodec": sdk_params.get("VCodec"),
        "vbitrate": sdk_params.get("vbitrate"),
        "resolution": sdk_params.get("resolution"),
        "fps": sdk_params.get("fps") or sdk_params.get("FPS"),
        "format": sdk_params.get("format"),
        "codec_type": sdk_params.get("codec_type"),
    }
    fields = {key: value for key, value in fields.items() if value not in (None, "")}
    print(f"- {label}: {fields or sdk_params}")
    if url:
        print(f"  url: {summarize_url(url)}")


def print_url_value(prefix: str, value) -> None:
    if isinstance(value, str):
        print(f"  {prefix}: {summarize_url(value)}")
    elif isinstance(value, list):
        print(f"  {prefix}: list[{len(value)}]")
        for index, item in enumerate(value[:3]):
            print_url_value(f"{prefix}[{index}]", item)
    elif isinstance(value, dict):
        print(f"  {prefix}: dict keys={list(value.keys())}")
        for key, item in list(value.items())[:10]:
            if isinstance(item, str) and item.startswith(("http://", "https://")):
                print(f"    {key}: {summarize_url(item)}")
            elif key in ("url", "main", "backup", "h264", "h265", "dash", "sdk_params"):
                print_url_value(f"{prefix}.{key}", item)


def inspect_stream_data(label: str, stream_data_text: str | None) -> None:
    if not stream_data_text:
        return
    try:
        data = json.loads(stream_data_text).get("data", {})
    except Exception as exc:
        print(f"\n[{label}] stream_data JSON 解析失败: {exc}")
        return

    print(f"\n[{label}] stream_data data keys: {list(data.keys())}")
    parsed_markers = find_marker_paths(data, ("h265", "hevc", "vp9", "dash"))
    for path, marker in parsed_markers:
        print(f"  parsed marker {marker}: {path}")
    for quality, info in data.items():
        main = info.get("main") if isinstance(info, dict) else None
        if not isinstance(main, dict):
            continue
        sdk_params = load_sdk_params(main.get("sdk_params"))
        print_sdk(
            f"{label}.{quality}",
            sdk_params,
            main.get("hls") or main.get("flv") or main.get("dash"),
        )
        for proto in ("hls", "flv", "dash"):
            if proto in main:
                print_url_value(proto, main[proto])

        dash = info.get("dash") if isinstance(info, dict) else None
        if isinstance(dash, dict):
            print(f"  dash keys: {list(dash.keys())}")
            for dash_key, dash_value in dash.items():
                if not isinstance(dash_value, dict):
                    continue
                dash_sdk = load_sdk_params(dash_value.get("sdk_params"))
                print_sdk(
                    f"{label}.{quality}.dash.{dash_key}",
                    dash_sdk,
                    dash_value.get("url") or dash_value.get("hls") or dash_value.get("flv"),
                )
                for url_key, url_value in dash_value.items():
                    if isinstance(url_value, str) and url_value.startswith(("http://", "https://")):
                        print(f"    {url_key}: {summarize_url(url_value)}")


def inspect_pull_maps(room_data: dict) -> None:
    stream_url = room_data.get("stream_url") or {}
    if stream_url.get("hevc_flv_url"):
        print(f"\n[hevc_flv_url]\n{summarize_url(stream_url['hevc_flv_url'])}")
    for name in ("hls_pull_url_map", "flv_pull_url"):
        values = stream_url.get(name) or {}
        print(f"\n[{name}] {len(values)} entries")
        for quality, url in values.items():
            codec = parse_qs(urlparse(url).query).get("codec", [""])[0]
            print(f"- {quality}: codec={codec or '(none)'} url={summarize_url(url)}")


def collect_codecs(room_data: dict) -> dict:
    result = {
        "pull_map_codecs": set(),
        "stream_data_codecs": set(),
        "pull_datas_keys": [],
    }

    stream_url = room_data.get("stream_url") or {}
    for name in ("hls_pull_url_map", "flv_pull_url"):
        for url in (stream_url.get(name) or {}).values():
            codec = parse_qs(urlparse(url).query).get("codec", [""])[0]
            if codec:
                result["pull_map_codecs"].add(codec)

    def collect_stream_data(stream_data_text: str | None) -> None:
        if not stream_data_text:
            return
        try:
            data = json.loads(stream_data_text).get("data", {})
        except Exception:
            return
        for info in data.values():
            main = info.get("main") if isinstance(info, dict) else None
            if not isinstance(main, dict):
                continue
            codec = load_sdk_params(main.get("sdk_params")).get("VCodec")
            if codec:
                result["stream_data_codecs"].add(codec)

    live_core_sdk_data = stream_url.get("live_core_sdk_data") or {}
    collect_stream_data((live_core_sdk_data.get("pull_data") or {}).get("stream_data"))
    pull_datas = stream_url.get("pull_datas") or {}
    result["pull_datas_keys"] = list(pull_datas.keys())
    for value in pull_datas.values():
        collect_stream_data(value.get("stream_data"))

    return result


def contains_markers(value, markers: tuple[str, ...]) -> set[str]:
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found |= contains_markers(key, markers)
            found |= contains_markers(item, markers)
    elif isinstance(value, list):
        for item in value:
            found |= contains_markers(item, markers)
    elif isinstance(value, str):
        lowered = value.lower()
        for marker in markers:
            if marker in lowered:
                found.add(marker)
    return found


def find_marker_paths(value, markers: tuple[str, ...], path: str = "$", limit: int = 30) -> list[tuple[str, str]]:
    found = []

    def visit(item, item_path):
        if len(found) >= limit:
            return
        if isinstance(item, dict):
            for key, child in item.items():
                lowered_key = str(key).lower()
                for marker in markers:
                    if marker in lowered_key:
                        found.append((f"{item_path}.{key}", marker))
                        break
                visit(child, f"{item_path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{item_path}[{index}]")
        elif isinstance(item, str):
            lowered = item.lower()
            for marker in markers:
                if marker in lowered:
                    found.append((item_path, marker))
                    return

    visit(value, path)
    return found


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?", default=None)
    parser.add_argument(
        "--profile",
        choices=[*UA_PROFILES.keys(), "all", "project"],
        default="project",
    )
    args = parser.parse_args()

    url = args.url or read_tuniang_url()
    cookie = read_cookie()
    print(f"debug url: {url}")
    print(f"cookie loaded: {'yes' if cookie else 'no'} ({len(cookie)} chars, not printed)")

    if args.profile == "project":
        room_data = await spider.get_douyin_web_stream_data(url=url, cookies=cookie)
    elif args.profile == "all":
        print("\n[ua profile summary]")
        for name, profile in UA_PROFILES.items():
            try:
                room_data = await fetch_douyin_web_stream_data_with_profile(url, cookie, profile)
                codecs = collect_codecs(room_data)
                print(
                    f"- {name}: status={room_data.get('status')} "
                    f"pull_map={sorted(codecs['pull_map_codecs']) or ['(none)']} "
                    f"stream_data={sorted(codecs['stream_data_codecs']) or ['(none)']} "
                    f"pull_datas={codecs['pull_datas_keys']}"
                )
            except Exception as exc:
                print(f"- {name}: ERROR {type(exc).__name__}: {exc}")
        print("\n[detail profile] chrome_win_141")
        room_data = await fetch_douyin_web_stream_data_with_profile(url, cookie, UA_PROFILES["chrome_win_141"])
    else:
        room_data = await fetch_douyin_web_stream_data_with_profile(url, cookie, UA_PROFILES[args.profile])

    print(f"room status: {room_data.get('status')} anchor={room_data.get('anchor_name')}")
    stream_extra = (room_data.get("stream_url") or {}).get("extra") or {}
    if stream_extra:
        interesting_extra = {
            key: stream_extra.get(key)
            for key in sorted(stream_extra)
            if any(marker in key.lower() for marker in ("h265", "hevc", "dash", "codec"))
        }
        print(f"stream_url.extra codec fields: {interesting_extra or '(none)'}")
    markers = contains_markers(room_data, ("h265", "hevc", "vp9", "dash"))
    print(f"raw marker scan: {sorted(markers) or ['(none)']}")
    for path, marker in find_marker_paths(room_data, ("h265", "hevc", "vp9", "dash")):
        print(f"  marker {marker}: {path}")
    inspect_pull_maps(room_data)

    stream_url = room_data.get("stream_url") or {}
    live_core_sdk_data = stream_url.get("live_core_sdk_data") or {}
    pull_data = live_core_sdk_data.get("pull_data") or {}
    inspect_stream_data("live_core_sdk_data.pull_data", pull_data.get("stream_data"))

    pull_datas = stream_url.get("pull_datas") or {}
    print(f"\n[pull_datas] {len(pull_datas)} entries: {list(pull_datas.keys())}")
    for key, value in pull_datas.items():
        inspect_stream_data(f"pull_datas.{key}", value.get("stream_data"))

    selected = await stream.get_douyin_stream_url(room_data, "原画", None)
    print("\n[selected 原画]")
    for key in ("m3u8_url", "flv_url", "record_url"):
        print(f"{key}: {summarize_url(selected.get(key, ''))}")


if __name__ == "__main__":
    asyncio.run(main())
