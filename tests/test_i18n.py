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
    def test_no_lang_env_pollution(self):
        # 原实现导入即写死 LANG=zh_CN.utf8（macOS 非法 locale），并传染子进程
        assert os.environ.get("LANG") != "zh_CN.utf8"

    def test_locale_path_exists(self):
        assert Path(i18n.locale_path).exists()

    def test_init_gettext_returns_callable(self):
        tr = i18n.init_gettext(i18n.locale_path, "zh_CN")
        assert callable(tr)
        assert tr("任意文本") == "任意文本"  # 源语言为中文，恒等映射


class TestMoCatalog:
    def test_mo_file_exists(self):
        # gettext 运行时只读取 .mo；.po 修改后必须重编译并随仓库分发（见 .gitignore 约定）
        assert MO_PATH.exists() and MO_PATH.stat().st_size > 0

    def test_translation_works_without_lang_env(self):
        # Windows 客户端普遍不设置 LANG/LC_* 环境变量；翻译加载不得依赖它们。
        # 清空这些变量后直接走 init_gettext 真实加载路径做一次翻译查找：
        # 若实现回退为按环境变量查找的全局 gettext.gettext，此处会查不到而失败。
        cleaned = {k: v for k, v in os.environ.items() if not k.startswith(("LANG", "LC_"))}
        with patch.dict(os.environ, cleaned, clear=True):
            tr = i18n.init_gettext(i18n.locale_path, "zh_CN")
            assert tr("IP banned. Please change device or network.") == "IP被禁止 请更换设备或网络"

    def test_po_and_mo_in_sync(self):
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
    def test_translated_print_calls_builtin_print(self):
        captured: list[object] = []
        # i18n 内部调用导入时保存的 original_print 引用，需 patch 该引用
        with patch.object(i18n, "original_print", side_effect=lambda *a, **k: captured.append(a)):
            i18n.translated_print("hello", "world", sep="-", end="")
        assert captured[0][0] == "hello-world"

    def test_should_translate_project_files(self):
        assert i18n._should_translate(str(Path(__file__).resolve())) is True

    def test_should_translate_foreign_files(self):
        assert i18n._should_translate("C:/somewhere/else/file.py") is False
