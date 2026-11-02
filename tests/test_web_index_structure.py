# web/index.html 文档头部结构回归锁（CODE_REVIEW_2026-10-29 S-03）。
#
# 症状：冲突解决把 HEAD 侧三份重复副本折叠时，文件头残留了上一份的孤立 `</body></html>`
# 两行。HTML5 解析器见到首个非空 token 不是 DOCTYPE 即置 force-quirks，后续真 DOCTYPE 被忽略，
# 面板因此整体落入 quirks 模式——`table-layout: fixed`、盒模型、`dvh`/`env(safe-area-inset-*)`
# 这些布局契约不再按标准模式保证。既有前端用例只读取该文件的 DOM 片段，没有一条断言文档头部，
# 故该缺陷对所有门禁隐形；本文件补的正是这条结构锁。

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "web" / "index.html"


def _read_index_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def test_first_non_empty_token_is_doctype() -> None:
    text = _read_index_html()
    stripped = text.lstrip()
    assert stripped, "web/index.html 为空，解析前提失效"
    assert stripped[:15].lower() == "<!doctype html>", f"文档首个非空 token 不是 DOCTYPE: {stripped[:40]!r}"


def test_document_has_single_closing_pair() -> None:
    text = _read_index_html()
    assert text.count("</body>") == 1, "web/index.html 出现多个 </body>（合并残留）"
    assert text.count("</html>") == 1, "web/index.html 出现多个 </html>（合并残留）"


def test_html_element_declares_language() -> None:
    text = _read_index_html()
    assert '<html lang="' in text, "web/index.html 缺少 <html lang> 声明"
