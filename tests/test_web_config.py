# Tests for src/web_config.py - Web 面板配置纯函数模块（安全回归）.
# 中文：本文件守护 Web 面板配置纯函数的安全不变量——换行注入防护（C3/C7）、
# 密钥哈希往返与明文兼容、原子写不残留临时文件、默认值含受信代理字段、
# 画质选项的规范化/持久化、URL_config.ini 房间画质保序改写与主播名反查 URL。
# 全程纯函数 + tmp_path，不触网、不依赖全局 config。
#
# 本次新增（按需滚动追加）：
# - TestQualityOptions：选项过滤、缺键回退、行级更新、换行注入防护
# - TestUpdateRoomQuality：行级改写 + URL 归一化匹配 + 注释前缀保留 + 幂等性 + 原子写
# - TestFindRoomUrlByAnchorName：主播名反查 URL，GUI 画质切换写回依赖此入口

from pathlib import Path

import pytest

from src.web_config import (
    BUILTIN_QUALITIES,
    find_room_url_by_anchor_name,
    format_url_line,
    hash_web_password,
    is_hashed_web_password,
    normalize_quality_options,
    read_quality_options,
    read_web_config,
    update_config_line,
    update_room_quality,
    validate_config_target,
    validate_room_target,
    verify_web_password,
    write_quality_options,
)


class TestFormatUrlLine:
    # format_url_line 换行注入防护（C3）.

    # 守护 C3：quality 含换行视为注入攻击，format_url_line 须抛 ValueError（不写出污染行）。
    def test_quality_newline_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_url_line("https://live.douyin.com/1", quality="高清\n# evil", name=None)

    def test_name_newline_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_url_line("https://live.douyin.com/1", quality=None, name="主播\nxx")

    # 守护 C3：url 字段含换行拒绝（防止在房间列表文件里插入新行篡改配置）。
    def test_url_newline_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_url_line("https://live.douyin.com/1\n# evil", quality=None, name=None)

    # 正常路径：quality/name 均无换行时拼出 "quality,url,主播: name" 标准格式行。
    def test_normal_line(self) -> None:
        line = format_url_line("https://live.douyin.com/1", "超清", "小明")
        assert line == "超清,https://live.douyin.com/1,主播: 小明"


class TestValidateTargets:
    def test_newline_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_config_target("Web", "web_host", "127.0.0.1\nweb_port=9999")

    def test_newline_url_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_room_target("https://live.douyin.com/1\n# x", None)


class TestUpdateConfigLine:
    def test_update_preserves_comments_and_cleans_tmp(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\n# 注释\nweb_host = 127.0.0.1\nweb_port = 8000\n", encoding="utf-8-sig")
        assert update_config_line(cfg, "Web", "web_host", "0.0.0.0") is True
        text = cfg.read_text(encoding="utf-8-sig")
        assert "web_host = 0.0.0.0" in text
        assert "# 注释" in text
        # 原子写不应留下临时文件（C7）：精确匹配 .tmp 扩展名
        leftovers = [p.name for p in tmp_path.glob("*.tmp")]
        assert leftovers == [], f"原子写残留临时文件: {leftovers}"

    def test_missing_key_returns_false(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\nweb_host = 127.0.0.1\n", encoding="utf-8-sig")
        assert update_config_line(cfg, "Web", "not_exist", "x") is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        assert update_config_line(tmp_path / "nope.ini", "Web", "web_host", "x") is False


class TestVerifyWebPassword:
    def test_hash_roundtrip(self) -> None:
        hashed = hash_web_password("secret123")
        assert is_hashed_web_password(hashed)
        assert verify_web_password("secret123", hashed)
        assert not verify_web_password("wrong", hashed)

    # 兼容旧配置：未哈希的明文口令按相等直接放行（平滑迁移，不强制重设密码）。
    def test_plaintext_compat(self) -> None:
        assert verify_web_password("abc", "abc")

    def test_malformed_iterations_returns_false(self) -> None:
        # 手工改坏迭代次数不应抛异常导致登录接口 500（C12）
        bad = "pbkdf2_sha256$notanumber$c2FsdA==$aGFzaA=="
        assert verify_web_password("x", bad) is False

    # 边界：存储口令为空串时验证返回 False（不抛异常、不误判为通过）。
    def test_empty_stored_returns_false(self) -> None:
        assert verify_web_password("x", "") is False


class TestReadWebConfig:
    # 默认值不变量：空配置读出的默认值须含 web_trusted_proxy(空) 与 web_host(127.0.0.1 本地)；
    # 缺省绑定本地回环，避免误开公网。
    def test_defaults_include_trusted_proxy(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("", encoding="utf-8-sig")
        result = read_web_config(cfg)
        assert result["web_trusted_proxy"] == ""
        assert result["web_host"] == "127.0.0.1"


class TestQualityOptions:
    # 画质选项的读/写/规范化：落地 config.ini [录制设置]，与 GUI/WEB 端共用。

    def test_normalize_drops_unknown_and_duplicates(self) -> None:
        # main.py 画质白名单外名称会被静默回退为「原画」，故选项必须仅取内置档位
        result = normalize_quality_options(["超清", "蓝光4M", "超清", "2K", "", " 流畅 "])
        assert result == ["超清", "蓝光4M", "流畅"]
        assert "2K" not in result  # 非法项剔除

    def test_normalize_falls_back_to_builtin_when_empty(self) -> None:
        # 全部非法/空 → 回退内置全集，避免下拉空空如也
        assert normalize_quality_options([]) == list(BUILTIN_QUALITIES)
        assert normalize_quality_options(["", "2K"]) == list(BUILTIN_QUALITIES)

    def test_read_missing_key_returns_builtin(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[录制设置]\n原画|超清|高清|标清|流畅 = 原画\n", encoding="utf-8-sig")
        assert read_quality_options(cfg) == list(BUILTIN_QUALITIES)

    def test_write_appends_when_key_missing_then_reads_back(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[录制设置]\nlanguage = zh_CN\n", encoding="utf-8-sig")
        result = write_quality_options(cfg, ["超清", "高清"])
        assert result == ["超清", "高清"]
        # 再次读取应拿到同样的列表（保留顺序）
        assert read_quality_options(cfg) == ["超清", "高清"]
        # 写入不应破坏节内其他键（language 原样保留）
        assert "language = zh_CN" in cfg.read_text(encoding="utf-8-sig")

    def test_write_updates_existing_key_in_place(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text(
            "[录制设置]\n自定义画质选项(逗号分隔) = 超清,流畅\nlanguage = zh_CN\n",
            encoding="utf-8-sig",
        )
        write_quality_options(cfg, ["蓝光8M", "标清"])
        text = cfg.read_text(encoding="utf-8-sig")
        assert "自定义画质选项(逗号分隔) = 蓝光8M,标清" in text
        assert "language = zh_CN" in text  # 行级替换不应误伤

    def test_write_newline_in_options_rejected(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[录制设置]\n", encoding="utf-8-sig")
        with pytest.raises(ValueError):
            write_quality_options(cfg, ["超清\n# 注入"])


class TestUpdateRoomQuality:
    # update_room_quality：行级改写 URL_config.ini 中指定 URL 的画质段。
    # 守护：C3 换行注入防护、行格式约束（画质,URL[,主播: 名称]）、幂等性、URL 归一化匹配。

    def _write(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8-sig")

    def test_add_quality_to_plain_url(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "https://live.douyin.com/1,主播: A\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "超清") is True
        # 格式: 画质,URL,主播: 名称（与需求示例一致）
        assert url_cfg.read_text(encoding="utf-8-sig") == "超清,https://live.douyin.com/1,主播: A\n"

    def test_change_existing_quality(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "蓝光8M,https://live.douyin.com/1,主播: A\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "超清") is True
        assert url_cfg.read_text(encoding="utf-8-sig") == "超清,https://live.douyin.com/1,主播: A\n"

    def test_remove_quality_when_default(self, tmp_path: Path) -> None:
        # 默认画质（空字符串与「原画」）= 移除画质段，回落到全局默认
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "超清,https://live.douyin.com/1,主播: A\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "") is True
        assert url_cfg.read_text(encoding="utf-8-sig") == "https://live.douyin.com/1,主播: A\n"
        # 再用「原画」显式回落：幂等返回 False（已无画质段）
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "原画") is False

    def test_preserves_comment_prefix(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "# https://live.douyin.com/1,主播: 禁用\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "超清") is True
        assert url_cfg.read_text(encoding="utf-8-sig") == "# 超清,https://live.douyin.com/1,主播: 禁用\n"

    def test_idempotent_when_no_change(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "超清,https://live.douyin.com/1,主播: A\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "超清") is False
        # 同一画质段重复调用不修改文件
        assert url_cfg.read_text(encoding="utf-8-sig") == "超清,https://live.douyin.com/1,主播: A\n"

    def test_url_normalized_match(self, tmp_path: Path) -> None:
        # 配置行可能不带 scheme；写入端带 scheme 时也应能匹配到
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "live.douyin.com/1\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "高清") is True
        assert "高清," in url_cfg.read_text(encoding="utf-8-sig")

    def test_no_match_returns_false(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "https://live.douyin.com/1,主播: A\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/999", "超清") is False
        # 文件未修改
        assert url_cfg.read_text(encoding="utf-8-sig") == "https://live.douyin.com/1,主播: A\n"

    def test_newline_in_quality_rejected(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "https://live.douyin.com/1\n")
        with pytest.raises(ValueError):
            update_room_quality(url_cfg, "https://live.douyin.com/1", "高清\n# evil")

    def test_atomic_write_no_leftover_tmp(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "https://live.douyin.com/1\n")
        _ = update_room_quality(url_cfg, "https://live.douyin.com/1", "超清")
        leftovers = [p.name for p in tmp_path.glob("*.tmp")]
        assert leftovers == [], f"原子写残留临时文件: {leftovers}"


class TestFindRoomUrlByAnchorName:
    # find_room_url_by_anchor_name：按主播名反查直播间地址，供 GUI 画质切换写回使用。

    def test_exact_match(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        url_cfg.write_text(
            "https://live.douyin.com/1,主播: 香芋\nhttps://live.douyin.com/2,主播: 小Q\n",
            encoding="utf-8-sig",
        )
        assert find_room_url_by_anchor_name(url_cfg, "香芋") == "https://live.douyin.com/1"
        assert find_room_url_by_anchor_name(url_cfg, "小Q") == "https://live.douyin.com/2"

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        url_cfg.write_text("https://live.douyin.com/1,主播: A\n", encoding="utf-8-sig")
        assert find_room_url_by_anchor_name(url_cfg, "不存在") == ""
        assert find_room_url_by_anchor_name(url_cfg, "") == ""
