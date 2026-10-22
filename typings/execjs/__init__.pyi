# Minimal type stub for PyExecJS (execjs).
#
# The upstream package ships no type information; basedpyright's default
# auto-generated stub leaves ``compile``/``call`` untyped (``Unknown``), which
# cascades ``reportUnknownMemberType`` warnings at every call site (e.g.
# ``execjs.compile(...)`` reads an ``Unknown`` member). This stub gives
# ``compile`` a concrete ``ExternalRuntime`` return type and lets ``call`` return
# ``Any`` (JS values are dynamically typed), which callers narrow with
# ``cast(...)``.
#
# This is a *type-only* stub; it intentionally does not shadow runtime behaviour.

# 第三方无类型包（PyExecJS）的最小存根；JS 运行期返回值本身即为动态类型，
# 故此处有意使用 Any，并放宽本文件的类型检查。
# pyright: reportGeneralTypeIssues=none

from typing import Any

class ExternalRuntime:
    def __init__(self, name: str, runtime: Any, code: str) -> None: ...
    def call(self, name: str, *args: Any, **kwargs: Any) -> Any: ...
    def eval(self, source: str) -> Any: ...

def compile(source: str, cwd: str | None = ...) -> ExternalRuntime: ...
def eval(source: str, cwd: str | None = ...) -> Any: ...
def exec_(source: str, cwd: str | None = ...) -> Any: ...
def get() -> Any: ...
def get_from_environment(name: str | None = ...) -> Any: ...
def register(name: str, runtime: Any) -> Any: ...
def runtimes() -> list[Any]: ...

class Error(Exception): ...
class ProgramError(Exception): ...
class RuntimeError(Exception): ...
class RuntimeUnavailableError(Exception): ...

__all__ = [
    "compile",
    "eval",
    "exec_",
    "get",
    "get_from_environment",
    "register",
    "runtimes",
    "ExternalRuntime",
    "Error",
    "ProgramError",
    "RuntimeError",
    "RuntimeUnavailableError",
]
