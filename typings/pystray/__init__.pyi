# 最小类型存根：pystray 官方未发布类型信息，本项目为静态检查补一份最小声明。
# 仅覆盖 web_tray.py 实际用到的 API。

# 第三方无类型包（pystray）的最小存根；icon 可为多种图像类型、回调返回动态值，
# 此处有意使用 Any，故放宽本文件的类型检查。
# pyright: reportGeneralTypeIssues=none

from typing import Any, Callable

class MenuItem:
    def __init__(
        self,
        text: str,
        action: Callable[..., Any] | None = ...,
        default: bool = ...,
    ) -> None: ...

class Menu:
    def __init__(self, *items: MenuItem) -> None: ...

class Icon:
    def __init__(
        self,
        name: str,
        icon: Any = ...,
        title: str | None = ...,
        menu: Menu | None = ...,
    ) -> None: ...
    def run(self, setup: Callable[[], Any] | None = ...) -> None: ...
    def stop(self) -> None: ...
    def notify(self, message: str, title: str | None = ...) -> None: ...
    @property
    def visible(self) -> bool: ...
    @visible.setter
    def visible(self, value: bool) -> None: ...
    # macOS darwin 后端在 pystray._base 上同样定义/使用的专有成员（gui.py 仅 macOS 分支调用）：
    # - run_detached()：macOS 专用，仅注册状态栏图标、不接管主线程事件循环；
    # - _assert_image() / _icon_valid：darwin 后端图标渲染与有效标记。
    def run_detached(self, setup: Callable[[], Any] | None = ...) -> None: ...
    def _assert_image(self) -> None: ...
    _icon_valid: bool
