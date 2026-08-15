# Tests for i18n.py 批次5修复 - 环境变量污染与翻译环境回归测试.

import builtins
import os
from pathlib import Path
from unittest.mock import patch

import i18n


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
