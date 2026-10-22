# src/web_models.py
# Web 管理面板请求体的「零依赖」校验层：用标准库 dataclass + 显式 parse_* 替换 FastAPI 的
# pydantic BaseModel，使 web_api.py 不再依赖 fastapi / pydantic（阶段 2：FastAPI → Starlette）。
#
# 设计约束（与旧 pydantic 行为对齐，避免契约漂移）：
#   · 必填字段缺失或非字符串 → ValueError（端点统一转 HTTPException(422, str(e))）。
#   · 可选字段（str | None）缺省为 None；若显式传入且非 None，必须是 str，否则 ValueError。
#   · bool 字段必须是 Python bool，否则 ValueError（前端恒以 JSON 真值提交，不作字符串宽松转换）。
#   · list[str] 字段必须是列表且元素全为 str，否则 ValueError。
#   · 多余字段一律忽略（对齐 pydantic 默认 extra="ignore"）。
#   · 不在此层做业务校验（SSRF / 画质白名单等），那些留在 web_api.py 调 web_config 的既有函数，
#     业务逻辑与旧实现逐字一致，仅搬运到 Starlette 接线。
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 这里的「零依赖」指不引 pydantic/fastapi；422 的 detail 是面板直接展示的文本，故走 i18n 查表
# （i18n 只依赖 stdlib + loguru，不回指 web_* 任何模块，无环）。
import i18n


def _as_str(value: Any, field: str) -> str:
    # 必填字符串字段：缺失或非 str 一律 ValueError，对应 pydantic 的 422。
    if not isinstance(value, str):
        raise ValueError(i18n.tr("字段 {field} 必须是字符串", field=field))
    return value


def _as_opt_str(value: Any, field: str) -> str | None:
    # 可选字符串字段：None 或缺失 → None；显式传入则必须是 str。
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(i18n.tr("字段 {field} 必须是字符串或留空", field=field))
    return value


def _as_bool(value: Any, field: str) -> bool:
    # 布尔字段：只接受 Python bool，避免 "true"/"1" 这类字符串宽松转换造成的语义漂移。
    if not isinstance(value, bool):
        raise ValueError(i18n.tr("字段 {field} 必须是布尔值", field=field))
    return value


def _as_str_list(value: Any, field: str) -> list[str]:
    # 字符串列表字段：必须是 list 且元素全为 str。
    if not isinstance(value, list):
        raise ValueError(i18n.tr("字段 {field} 必须是字符串列表", field=field))
    for item in value:
        if not isinstance(item, str):
            raise ValueError(i18n.tr("字段 {field} 的元素必须是字符串", field=field))
    return list(value)


def _require_dict(data: Any) -> dict[str, Any]:
    # 请求体必须是 JSON 对象；body 读取层（web_api._read_json_body）已先把非 dict / 非法 JSON
    # 转成 HTTPException(422)，这里再兜一层类型，避免 None / list 透传到字段解析。
    # [历史注] L-27（2026-10-02）：原注释误写 web_api._read_json，符号不存在，已更正。
    if not isinstance(data, dict):
        raise ValueError(i18n.tr("请求体必须是 JSON 对象"))
    return data


@dataclass
class LoginRequest:
    # POST /api/login。password 明文到达端点后走 PBKDF2 校验与旧哈希升级，本层只保证类型，
    # 绝不把凭据写进任何日志。
    password: str

    @classmethod
    def parse(cls, data: Any) -> LoginRequest:
        body = _require_dict(data)
        return cls(password=_as_str(body.get("password"), "password"))


@dataclass
class RoomCreate:
    # POST /api/rooms。quality/name 留空表示沿用全局默认；SSRF / 画质白名单等业务校验留在端点侧。
    url: str
    quality: str | None = None
    name: str | None = None

    @classmethod
    def parse(cls, data: Any) -> RoomCreate:
        body = _require_dict(data)
        return cls(
            url=_as_str(body.get("url"), "url"),
            quality=_as_opt_str(body.get("quality"), "quality"),
            name=_as_opt_str(body.get("name"), "name"),
        )


@dataclass
class RoomUpdate:
    # PUT /api/rooms。old_url 是旧行定位键（URL 即房间主键，改地址/改名/改画质都靠它找旧行），
    # 新 url 经 format_url_line 唯一写入口做 SEV-02 校验。
    old_url: str
    url: str
    quality: str | None = None
    name: str | None = None

    @classmethod
    def parse(cls, data: Any) -> RoomUpdate:
        body = _require_dict(data)
        return cls(
            old_url=_as_str(body.get("old_url"), "old_url"),
            url=_as_str(body.get("url"), "url"),
            quality=_as_opt_str(body.get("quality"), "quality"),
            name=_as_opt_str(body.get("name"), "name"),
        )


@dataclass
class RoomToggle:
    # POST /api/rooms/toggle。enable 翻转 URL_config.ini 房间行的启用位。
    url: str
    enable: bool

    @classmethod
    def parse(cls, data: Any) -> RoomToggle:
        body = _require_dict(data)
        return cls(
            url=_as_str(body.get("url"), "url"),
            enable=_as_bool(body.get("enable"), "enable"),
        )


@dataclass
class RoomQualityUpdate:
    # PUT /api/rooms/quality。quality 为 None/空表示清掉房间自定义档位、回落全局默认
    # （与 src/web_config.update_room_quality 的空值语义一致）。
    url: str
    quality: str | None = None

    @classmethod
    def parse(cls, data: Any) -> RoomQualityUpdate:
        body = _require_dict(data)
        return cls(
            url=_as_str(body.get("url"), "url"),
            quality=_as_opt_str(body.get("quality"), "quality"),
        )


@dataclass
class QualityOptionsUpdate:
    # PUT /api/rooms/qualities。options 是自定义画质档位的全集（PUT 覆盖式语义，非增量追加），
    # 端点持 file_update_lock 写 config.ini（H-6）。
    options: list[str]

    @classmethod
    def parse(cls, data: Any) -> QualityOptionsUpdate:
        body = _require_dict(data)
        return cls(options=_as_str_list(body.get("options"), "options"))


@dataclass
class RecordingToggle:
    # POST /api/recording/toggle。翻转的是运行期全局开关 main.recording_enabled，不落配置文件。
    enable: bool

    @classmethod
    def parse(cls, data: Any) -> RecordingToggle:
        body = _require_dict(data)
        return cls(enable=_as_bool(body.get("enable"), "enable"))


@dataclass
class IconUpload:
    # POST /api/icon（面板上传 ICO 图标）。data 是**剥离 data: URL 前缀后**的 base64 文本——
    # 前端 FileReader 读出来带 `data:image/x-icon;base64,`，提交前已切掉；带上前缀也能被
    # b64decode(validate=True) 拒掉，但报错只能到「不是合法 base64」这一层，看不出是前缀没剥。
    # name 只用作落盘文件名（经 ui_icons 的路径清洗），不构成任何路径信任链。
    name: str
    data: str

    @classmethod
    def parse(cls, data: Any) -> IconUpload:
        body = _require_dict(data)
        return cls(name=_as_str(body.get("name"), "name"), data=_as_str(body.get("data"), "data"))


@dataclass
class ConfigUpdate:
    # PUT /api/config。reauth_password 仅在改 Web 认证键（web_auth_enable / web_password）时必填：
    # bearer 只证明「登录过」，敏感开关的翻转必须复验当前口令（缺失即 403）。
    section: str
    key: str
    value: str
    reauth_password: str | None = None

    @classmethod
    def parse(cls, data: Any) -> ConfigUpdate:
        body = _require_dict(data)
        return cls(
            section=_as_str(body.get("section"), "section"),
            key=_as_str(body.get("key"), "key"),
            value=_as_str(body.get("value"), "value"),
            reauth_password=_as_opt_str(body.get("reauth_password"), "reauth_password"),
        )


@dataclass
class LanguageUpdate:
    # PUT /api/language。取值合法性由端点侧 i18n 支持列表裁决，本层只挡非字符串。
    language: str

    @classmethod
    def parse(cls, data: Any) -> LanguageUpdate:
        body = _require_dict(data)
        return cls(language=_as_str(body.get("language"), "language"))
