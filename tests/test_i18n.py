# Tests for i18n.py 批次5修复 - 环境变量污染与翻译环境回归测试.

import importlib.util
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import i18n

ROOT = Path(__file__).resolve().parents[1]
MO_PATH = ROOT / "i18n" / "zh_CN" / "LC_MESSAGES" / "zh_CN.mo"


class TestInitGettext:
    def test_no_lang_env_pollution(self) -> None:
        # 原实现导入即写死 LANG=zh_CN.utf8（macOS 非法 locale），并传染子进程
        assert os.environ.get("LANG") != "zh_CN.utf8"

    def test_locale_path_exists(self) -> None:
        assert Path(i18n.locale_path).exists()

    def test_init_gettext_returns_callable(self) -> None:
        tr = i18n.init_gettext(i18n.locale_path, "zh_CN")
        assert callable(tr)
        assert tr("任意文本") == "任意文本"  # 源语言为中文，恒等映射


class TestMoCatalog:
    def test_mo_file_exists(self) -> None:
        # gettext 运行时只读取 .mo；.po 修改后必须重编译并随仓库分发（见 .gitignore 约定）
        assert MO_PATH.exists() and MO_PATH.stat().st_size > 0

    def test_translation_works_without_lang_env(self) -> None:
        # Windows 客户端普遍不设置 LANG/LC_* 环境变量；翻译加载不得依赖它们。
        # 清空这些变量后直接走 init_gettext 真实加载路径做一次翻译查找：
        # 若实现回退为按环境变量查找的全局 gettext.gettext，此处会查不到而失败。
        cleaned = {k: v for k, v in os.environ.items() if not k.startswith(("LANG", "LC_"))}
        with patch.dict(os.environ, cleaned, clear=True):
            tr = i18n.init_gettext(i18n.locale_path, "zh_CN")
            assert tr("IP banned. Please change device or network.") == "IP被禁止 请更换设备或网络"

    def test_po_and_mo_in_sync(self) -> None:
        # .po 与 .mo 字节级同步，改动 .po 忘记重编译时在此失败；
        # 以 import 方式复用 scripts/compile_po.py 的编译逻辑（与 CI --check 同源）。
        spec = importlib.util.spec_from_file_location("compile_po_check", ROOT / "scripts" / "compile_po.py")
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        entries = mod.parse_po(mod.PO_PATH)
        with tempfile.TemporaryDirectory() as tmp_dir:
            fresh_bytes = mod.write_mo(entries, Path(tmp_dir) / "zh_CN.mo")
        assert fresh_bytes == MO_PATH.read_bytes(), ".po 已修改但 .mo 未重编译，请运行 python scripts/compile_po.py"


class TestTranslatedPrint:
    def test_translated_print_calls_builtin_print(self) -> None:
        captured: list[tuple[object, ...]] = []
        # i18n 内部调用导入时保存的 original_print 引用，需 patch 该引用
        with patch.object(i18n, "original_print", side_effect=lambda *a, **k: captured.append(a)):
            i18n.translated_print("hello", "world", sep="-", end="")
        assert captured[0][0] == "hello-world"

    def test_should_translate_project_files(self) -> None:
        assert i18n._should_translate(str(Path(__file__).resolve())) is True

    def test_should_translate_foreign_files(self) -> None:
        assert i18n._should_translate("C:/somewhere/else/file.py") is False


class TestMultiFormatCatalogs:
    """多格式翻译目录：gettext .mo（zh_CN）+ JSON（en_US/en_GB）+ YAML（zh_TW）。"""

    def test_supported_languages_complete(self) -> None:
        assert set(i18n.SUPPORTED_LANGUAGES.keys()) == {"zh_CN", "en_US", "en_GB", "zh_TW"}
        assert i18n.DEFAULT_LANGUAGE == "zh_CN"

    def test_catalog_files_exist(self) -> None:
        base = Path(i18n.locale_path)
        assert (base / "zh_CN" / "LC_MESSAGES" / "zh_CN.mo").is_file()
        assert (base / "en_US.json").is_file()
        assert (base / "en_GB.json").is_file()
        assert (base / "zh_TW.yaml").is_file()

    def test_catalogs_share_same_keyset(self) -> None:
        # 四种语言的目录键集合一致（同一批 msgid），保证切换语言后查找行为一致
        mo = i18n._load_mo_catalog(i18n.locale_path, "zh_CN")
        en_us = i18n._load_json_catalog(Path(i18n.locale_path) / "en_US.json")
        en_gb = i18n._load_json_catalog(Path(i18n.locale_path) / "en_GB.json")
        zh_tw = i18n._load_yaml_catalog(Path(i18n.locale_path) / "zh_TW.yaml")
        assert mo is not None and en_us is not None and en_gb is not None and zh_tw is not None
        assert set(mo) == set(en_us) == set(en_gb) == set(zh_tw)

    def test_load_translations_priority(self) -> None:
        # .mo 优先于 JSON/YAML：zh_CN 命中 .mo
        catalog = i18n._load_translations(i18n.locale_path, "zh_CN")
        assert catalog is not None
        assert catalog.get("The anchor did not start broadcasting.") == "主播并未开播"
        # en_US 命中 JSON
        en = i18n._load_translations(i18n.locale_path, "en_US")
        assert en is not None
        assert en.get("开始录制") == "Start Recording"
        # zh_TW 命中 YAML
        tw = i18n._load_translations(i18n.locale_path, "zh_TW")
        assert tw is not None
        assert tw.get("开始录制") == "開始錄製"


class TestLanguageSwitching:
    """运行时语言切换（Web 面板/GUI 即时切换语言功能的底层机制）。"""

    def setup_method(self) -> None:
        self._saved = i18n.get_language()

    def teardown_method(self) -> None:
        # 恢复默认语言，避免污染其他测试
        _ = i18n.set_language(self._saved)

    def test_set_language_hot_swaps_translator(self) -> None:
        sample = "The anchor did not start broadcasting."
        _ = i18n.set_language("zh_CN")
        assert i18n.get_language() == "zh_CN"
        assert i18n._tr(sample) == "主播并未开播"
        _ = i18n.set_language("en_US")
        assert i18n.get_language() == "en_US"
        assert i18n._tr(sample) == sample  # 英文源恒等
        assert i18n._tr("开始录制") == "Start Recording"
        _ = i18n.set_language("zh_TW")
        assert i18n._tr(sample) == "主播並未開播"
        _ = i18n.set_language("en_GB")
        assert i18n._tr("开始录制") == "Start Recording"

    def test_set_language_normalizes_input(self) -> None:
        assert i18n.set_language("zh-cn") is True
        assert i18n.get_language() == "zh_CN"
        assert i18n.set_language("EN") is True
        assert i18n.get_language() == "en_US"

    def test_normalize_language_variants(self) -> None:
        assert i18n.normalize_language("zh_cn") == "zh_CN"
        assert i18n.normalize_language("zh_CN.UTF-8") == "zh_CN"
        assert i18n.normalize_language("en") == "en_US"
        assert i18n.normalize_language("en-us") == "en_US"
        assert i18n.normalize_language("en_GB") == "en_GB"
        assert i18n.normalize_language("zh_TW") == "zh_TW"
        assert i18n.normalize_language("zh-Hant") == "zh_TW"
        assert i18n.normalize_language("fr") == "zh_CN"  # 未知回退默认
        assert i18n.normalize_language(None) == "zh_CN"
        assert i18n.normalize_language("") == "zh_CN"

    def test_is_recognized_language(self) -> None:
        assert i18n.is_recognized_language("zh_CN") is True
        assert i18n.is_recognized_language("zh_cn") is True
        assert i18n.is_recognized_language("en_US.UTF-8") is True
        assert i18n.is_recognized_language("fr") is False
        assert i18n.is_recognized_language("") is False
        assert i18n.is_recognized_language(None) is False

    def test_available_languages_returns_copy(self) -> None:
        langs = i18n.available_languages()
        langs["xx_XX"] = "injected"
        assert "xx_XX" not in i18n.available_languages()

    def test_unknown_language_falls_back_identity(self) -> None:
        # 未加载目录的语言（理论不存在于受支持集）经 set_language 归一化后仍是受支持语言；
        # 直接构造翻译函数时目录缺失回退恒等映射
        tr = i18n._build_translator(i18n.locale_path, "zh_CN")
        assert tr("不存在的串") == "不存在的串"
