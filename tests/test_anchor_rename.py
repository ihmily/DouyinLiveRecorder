# Tests for 主播名自动同步（anchor name auto-rename）:
# - src/config_io.update_anchor_name: URL_config.ini 主播名字段更新
# - main.rename_anchor_directory: 主播改名后录制目录/文件同步重命名

import os
import sys
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(scope="module")
def main_mod() -> ModuleType:
    # main.py 的 _app_root() 基于 sys.argv[0] 定位 config/，pytest 下 argv[0] 指向 pytest 自身，
    # 需在导入前修正为项目 main.py（与 test_main_fixes.py 相同的处理）
    old_argv = sys.argv[:]
    sys.argv = [str(Path(__file__).resolve().parent.parent / "main.py")]
    try:
        import main

        return main
    finally:
        sys.argv = old_argv


@pytest.fixture()
def url_config(tmp_path: Path, main_mod: ModuleType, monkeypatch: pytest.MonkeyPatch) -> Path:
    # 每个用例独立的 URL_config.ini + main 全局指向它
    cfg = tmp_path / "URL_config.ini"
    monkeypatch.setattr(main_mod, "url_config_file", str(cfg))
    monkeypatch.setattr(main_mod, "ini_URL_content", "")
    return cfg


# ============================ update_anchor_name ============================


class TestUpdateAnchorName:
    def test_basic_update(self, url_config: Path) -> None:
        from src.config_io import update_anchor_name

        url_config.write_text("https://live.douyin.com/1,主播: 旧名字\n", encoding="utf-8-sig")
        assert update_anchor_name("https://live.douyin.com/1", "新名字") is True
        assert url_config.read_text(encoding="utf-8-sig") == "https://live.douyin.com/1,主播: 新名字\n"

    def test_keeps_quality_segment(self, url_config: Path) -> None:
        from src.config_io import update_anchor_name

        url_config.write_text("超清,https://live.bilibili.com/123,主播: 旧名字\n", encoding="utf-8-sig")
        assert update_anchor_name("https://live.bilibili.com/123", "新名字") is True
        assert url_config.read_text(encoding="utf-8-sig") == "超清,https://live.bilibili.com/123,主播: 新名字\n"

    def test_preserves_comment_prefix(self, url_config: Path) -> None:
        from src.config_io import update_anchor_name

        url_config.write_text("#https://live.douyin.com/9,主播: 旧名字\n", encoding="utf-8-sig")
        assert update_anchor_name("https://live.douyin.com/9", "新名字") is True
        assert url_config.read_text(encoding="utf-8-sig") == "#https://live.douyin.com/9,主播: 新名字\n"

    def test_appends_when_field_missing(self, url_config: Path) -> None:
        from src.config_io import update_anchor_name

        url_config.write_text("https://live.douyin.com/2\n超清,https://live.douyin.com/3\n", encoding="utf-8-sig")
        assert update_anchor_name("https://live.douyin.com/2", "小明") is True
        assert update_anchor_name("https://live.douyin.com/3", "小红") is True
        content = url_config.read_text(encoding="utf-8-sig")
        assert "https://live.douyin.com/2,主播: 小明\n" in content
        assert "超清,https://live.douyin.com/3,主播: 小红\n" in content

    def test_fullwidth_colon_supported(self, url_config: Path) -> None:
        from src.config_io import update_anchor_name

        url_config.write_text("https://live.douyin.com/4,主播：旧名字\n", encoding="utf-8-sig")
        assert update_anchor_name("https://live.douyin.com/4", "新名字") is True
        # 统一重写为半角冒号格式（与 main.py 行解析一致）
        assert url_config.read_text(encoding="utf-8-sig") == "https://live.douyin.com/4,主播: 新名字\n"

    def test_idempotent_when_already_new_name(self, url_config: Path) -> None:
        from src.config_io import update_anchor_name

        url_config.write_text("https://live.douyin.com/5,主播: 新名字\n", encoding="utf-8-sig")
        assert update_anchor_name("https://live.douyin.com/5", "新名字") is False
        assert url_config.read_text(encoding="utf-8-sig") == "https://live.douyin.com/5,主播: 新名字\n"

    def test_url_prefix_not_mismatched(self, url_config: Path) -> None:
        # 回归：URL 前缀相似（/1 与 /12）时不得误改他行（段级匹配而非子串匹配）
        from src.config_io import update_anchor_name

        url_config.write_text(
            "https://live.douyin.com/1,主播: 甲\nhttps://live.douyin.com/12,主播: 乙\n",
            encoding="utf-8-sig",
        )
        assert update_anchor_name("https://live.douyin.com/1", "丙") is True
        content = url_config.read_text(encoding="utf-8-sig")
        assert "https://live.douyin.com/1,主播: 丙" in content
        assert "https://live.douyin.com/12,主播: 乙" in content

    def test_other_lines_untouched_and_eol_preserved(self, url_config: Path) -> None:
        from src.config_io import update_anchor_name

        url_config.write_bytes(
            "https://live.douyin.com/7,主播: 旧\r\nhttps://live.douyin.com/8,主播: 别人\n".encode("utf-8-sig")
        )
        assert update_anchor_name("https://live.douyin.com/7", "新") is True
        assert (
            url_config.read_bytes().decode("utf-8-sig")
            == "https://live.douyin.com/7,主播: 新\r\nhttps://live.douyin.com/8,主播: 别人\n"
        )

    def test_updates_snapshot(self, url_config: Path, main_mod: ModuleType) -> None:
        from src.config_io import update_anchor_name

        url_config.write_text("https://live.douyin.com/6,主播: 旧\n", encoding="utf-8-sig")
        update_anchor_name("https://live.douyin.com/6", "新")
        # 落盘后同步更新异常恢复快照（与 update_file 行为一致）
        assert "主播: 新" in main_mod.ini_URL_content

    def test_missing_file_returns_false(self, url_config: Path) -> None:
        from src.config_io import update_anchor_name

        # 文件不存在（url_config fixture 未写入内容）
        assert update_anchor_name("https://live.douyin.com/x", "新") is False

    def test_empty_args_return_false(self, url_config: Path) -> None:
        from src.config_io import update_anchor_name

        assert update_anchor_name("", "新") is False
        assert update_anchor_name("https://live.douyin.com/x", "") is False


# ============================ rename_anchor_directory ============================


@pytest.fixture()
def save_root(tmp_path: Path, main_mod: ModuleType, monkeypatch: pytest.MonkeyPatch) -> Path:
    # 每个用例独立的下载根目录 + main 全局指向它
    root = tmp_path / "downloads"
    root.mkdir()
    monkeypatch.setattr(main_mod, "video_save_path", "")
    monkeypatch.setattr(main_mod, "default_path", str(root))
    return root


class TestRenameAnchorDirectory:
    def test_renames_author_dir_and_prefixed_files(self, save_root: Path, main_mod: ModuleType) -> None:
        # folder_by_author（默认开启）结构：{platform}/{主播名}/日期/录制文件（含 SRT）
        anchor_dir = save_root / "抖音直播" / "旧名字"
        date_dir = anchor_dir / "260101"
        date_dir.mkdir(parents=True)
        (anchor_dir / "旧名字_260101_120000_000.ts").write_text("v")
        (date_dir / "旧名字_260101_120000.srt").write_text("s")
        (date_dir / "其他主播_260101.ts").write_text("o")

        assert main_mod.rename_anchor_directory("旧名字", "新名字", "抖音直播") is True

        assert not (save_root / "抖音直播" / "旧名字").exists()
        new_dir = save_root / "抖音直播" / "新名字"
        assert new_dir.is_dir()
        assert (new_dir / "新名字_260101_120000_000.ts").exists()
        assert (new_dir / "260101" / "新名字_260101_120000.srt").exists()
        # 非该主播前缀的文件不受影响
        assert (new_dir / "260101" / "其他主播_260101.ts").exists()

    def test_merges_when_target_dir_exists(self, save_root: Path, main_mod: ModuleType) -> None:
        # 主播改回曾用名：目标目录已存在 → 逐项合并而非失败
        old_dir = save_root / "抖音直播" / "名字A"
        new_dir = save_root / "抖音直播" / "名字B"
        old_dir.mkdir(parents=True)
        new_dir.mkdir(parents=True)
        (old_dir / "名字A_260101_010101.ts").write_text("a")
        (new_dir / "名字B_251231_010101.ts").write_text("b")

        assert main_mod.rename_anchor_directory("名字A", "名字B", "抖音直播") is True

        # 旧目录被清空删除，内容并入新目录且文件前缀统一为新名
        assert not old_dir.exists()
        assert (new_dir / "名字B_260101_010101.ts").exists()
        assert (new_dir / "名字B_251231_010101.ts").exists()

    def test_missing_old_dir_is_success(self, save_root: Path, main_mod: ModuleType) -> None:
        # 从未录制过（无旧目录）：视为成功，不产生任何副作用
        (save_root / "抖音直播").mkdir()
        assert main_mod.rename_anchor_directory("旧名字", "新名字", "抖音直播") is True
        assert list((save_root / "抖音直播").iterdir()) == []

    def test_missing_platform_dir_is_success(self, save_root: Path, main_mod: ModuleType) -> None:
        assert main_mod.rename_anchor_directory("旧名字", "新名字", "抖音直播") is True

    def test_renames_files_without_author_folder(self, save_root: Path, main_mod: ModuleType) -> None:
        # folder_by_author 关闭：录制文件平铺在平台目录/日期子目录下，仅按文件名前缀同步
        platform_dir = save_root / "B站直播"
        date_dir = platform_dir / "260102"
        date_dir.mkdir(parents=True)
        (platform_dir / "旧名字_260102_000000_000.ts").write_text("v")
        (date_dir / "旧名字_260102_000000.srt").write_text("s")
        (platform_dir / "别人_260102.ts").write_text("o")

        assert main_mod.rename_anchor_directory("旧名字", "新名字", "B站直播") is True

        assert (platform_dir / "新名字_260102_000000_000.ts").exists()
        assert (date_dir / "新名字_260102_000000.srt").exists()
        assert (platform_dir / "别人_260102.ts").exists()

    def test_renames_title_anchor_subdir(self, save_root: Path, main_mod: ModuleType) -> None:
        # folder_by_title + folder_by_time 组合：子目录名形如 "{标题}_{主播名}"
        anchor_dir = save_root / "抖音直播" / "旧名字"
        title_dir = anchor_dir / "演唱会_旧名字"
        title_dir.mkdir(parents=True)
        (title_dir / "旧名字_260103_000000.ts").write_text("v")

        assert main_mod.rename_anchor_directory("旧名字", "新名字", "抖音直播") is True

        new_anchor_dir = save_root / "抖音直播" / "新名字"
        assert (new_anchor_dir / "演唱会_新名字").is_dir()
        assert (new_anchor_dir / "演唱会_新名字" / "新名字_260103_000000.ts").exists()

    def test_locked_file_skipped_but_directory_renamed(
        self, save_root: Path, main_mod: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 路径引用完整性：个别文件被占用（如后台转码/播放器打开）时仅跳过该文件并告警，
        # 目录改名与其余文件不受影响，下轮轮询可补齐
        anchor_dir = save_root / "抖音直播" / "旧名字"
        anchor_dir.mkdir(parents=True)
        (anchor_dir / "旧名字_locked.ts").write_text("x")
        (anchor_dir / "旧名字_free.ts").write_text("y")

        real_rename = os.rename

        def selective_rename(src: str, dst: str) -> None:
            # 仅按文件名匹配（tmp_path 目录名含测试函数名，按全路径匹配会误伤目录改名）
            if "locked" in os.path.basename(src):
                raise OSError(13, "Permission denied")
            return real_rename(src, dst)

        monkeypatch.setattr(os, "rename", selective_rename)

        assert main_mod.rename_anchor_directory("旧名字", "新名字", "抖音直播") is True
        new_dir = save_root / "抖音直播" / "新名字"
        assert new_dir.is_dir()
        assert (new_dir / "旧名字_locked.ts").exists()  # 占用文件保留旧名
        assert (new_dir / "新名字_free.ts").exists()

    def test_directory_rename_failure_returns_false(
        self, save_root: Path, main_mod: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 目录级失败（如整目录被占用/权限）：返回 False，调用方下轮重试、不更新配置
        anchor_dir = save_root / "抖音直播" / "旧名字"
        anchor_dir.mkdir(parents=True)
        (anchor_dir / "旧名字_260104.ts").write_text("v")

        def fail_dir_rename(src: str, dst: str) -> None:
            raise OSError(5, "Access is denied")

        monkeypatch.setattr(os, "rename", fail_dir_rename)

        assert main_mod.rename_anchor_directory("旧名字", "新名字", "抖音直播") is False
        assert anchor_dir.is_dir()  # 原目录原样保留

    def test_same_and_empty_names_are_noop(self, save_root: Path, main_mod: ModuleType) -> None:
        assert main_mod.rename_anchor_directory("", "x", "抖音直播") is True
        assert main_mod.rename_anchor_directory("x", "", "抖音直播") is True
        assert main_mod.rename_anchor_directory("同", "同", "抖音直播") is True


# ============================ 端到端：配置 + 文件系统一致性 ============================


class TestAnchorRenameEndToEnd:
    def test_config_and_filesystem_stay_consistent(
        self, url_config: Path, save_root: Path, main_mod: ModuleType
    ) -> None:
        # 模拟 start_record 内的同步顺序：先改文件系统（失败则中止），成功后再更新配置
        from src.config_io import update_anchor_name

        url_config.write_text(
            "超清,https://live.douyin.com/66,主播: 旧名字\nhttps://live.douyin.com/77,主播: 无关\n",
            encoding="utf-8-sig",
        )
        anchor_dir = save_root / "抖音直播" / "旧名字"
        anchor_dir.mkdir(parents=True)
        (anchor_dir / "旧名字_260105_000000_000.ts").write_text("v")

        old_name = "旧名字"
        new_name = "新名字"
        if main_mod.rename_anchor_directory(old_name, new_name, "抖音直播"):
            assert update_anchor_name("https://live.douyin.com/66", new_name) is True

        # 文件系统与配置文件一致地使用新名，其他房间不受影响
        assert (save_root / "抖音直播" / "新名字" / "新名字_260105_000000_000.ts").exists()
        content = url_config.read_text(encoding="utf-8-sig")
        assert "超清,https://live.douyin.com/66,主播: 新名字" in content
        assert "https://live.douyin.com/77,主播: 无关" in content
