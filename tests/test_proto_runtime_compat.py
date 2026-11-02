#
# src/proto/douyin_pb2.py 是 protoc 25.x（gencode 4.25.3）生成物、标注 DO NOT EDIT，本环境无
# protoc / grpcio-tools 无法重新生成，因此护栏落在三件事：
#   1. requirements.txt / pyproject.toml 给 runtime 加 `<8` 上限；
#   2. 断言已安装 runtime 满足声明区间且不早于 gencode 版本——升到窗口外时 CI 立刻变红，
#      而不是等到线上弹幕解码时才炸；
#   3. 断言 douyin_pb2 能 import 并完成一次往返编解码（不兼容的典型症状：AttributeError /
#      序列化异常 / 字段静默丢失）。
# 升级 runtime 的正确姿势：先用**同代 protoc**重新生成 *_pb2.py，再放开上限，并回归本文件。

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PB2_PATH = _REPO_ROOT / "src" / "proto" / "douyin_pb2.py"

# gencode 版本：从生成文件头注释里解析，避免手写一个会随重新生成而失效的常量
_GENCODE_RE = re.compile(r"#\s*Protobuf Python Version:\s*(\d+)\.(\d+)\.(\d+)")


def _gencode_version() -> tuple[int, int, int]:
    match = _GENCODE_RE.search(_PB2_PATH.read_text(encoding="utf-8"))
    assert match, f"未能从 {_PB2_PATH.name} 解析出 Protobuf Python Version 头注释"
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _declared_protobuf_specifier() -> str:
    # 从 requirements.txt 取声明区间（形如 `protobuf>=6.33.5,<8 # 注释`）
    for line in (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith("protobuf"):
            return stripped[len("protobuf") :].strip()
    # 这里刻意用 raise 而非 pytest.fail()：CI 的 typecheck job 只装 requirements.txt + mypy，
    # 未装 pytest 时 `import pytest` 解析为 Any，pytest.fail() 的 NoReturn 丢失，mypy 会认为
    # 本函数可能隐式返回 None 而报 [return]（本机装了 pytest 则看不到）。raise 与是否装 pytest 无关。
    raise AssertionError("requirements.txt 中未找到 protobuf 声明")


def test_declared_specifier_is_bounded_above() -> None:
    # 上限是该核心护栏：无上限意味着 pip 会自动升到下一个大版本，
    # gencode 兼容窗口可能在某次升级后突然关闭。
    spec = _declared_protobuf_specifier()
    assert "<" in spec, f"protobuf 声明缺少上限（当前：{spec}）——F-14 护栏失效"


def _parse_version(text: str) -> tuple[int, ...]:
    # 只取数字段比较（protobuf 主流版本形如 7.36.1 / 6.31.1，rc 后缀不影响区间判定）
    return tuple(int(part) for part in re.findall(r"\d+", text))


def _satisfies(version: tuple[int, ...], spec: str) -> bool:
    # 极简区间判定：仅支持本项目实际用到的 `>=x.y.z` / `<n` / `<=n` 组合，
    # 不引入 packaging 依赖（测试环境不保证安装）。
    for clause in (c.strip() for c in spec.split(",") if c.strip()):
        for op in (">=", "<=", ">", "<", "=="):
            if clause.startswith(op):
                bound = _parse_version(clause[len(op) :])
                if op == ">=" and not version >= bound:
                    return False
                if op == ">" and not version > bound:
                    return False
                if op == "<=" and not version <= bound:
                    return False
                if op == "<" and not version < bound:
                    return False
                if op == "==" and version != bound:
                    return False
                break
        else:
            pytest.fail(f"无法解析的版本约束片段：{clause}")
    return True


def test_installed_runtime_satisfies_declared_specifier() -> None:
    import google.protobuf

    spec = _declared_protobuf_specifier()
    installed = _parse_version(google.protobuf.__version__)
    assert _satisfies(installed, spec), (
        f"已安装 protobuf {google.protobuf.__version__} 不满足声明区间 {spec}："
        "升级 runtime 前须先用同代 protoc 重新生成 src/proto/*_pb2.py"
    )


def test_runtime_not_older_than_gencode() -> None:
    # protobuf 的硬规则：runtime 不得早于 gencode 版本，否则 import 期即失败
    import google.protobuf

    installed = _parse_version(google.protobuf.__version__)
    gencode = _gencode_version()
    assert installed >= gencode, f"runtime {installed} 早于 gencode {gencode}"


def test_douyin_pb2_roundtrip_under_current_runtime() -> None:
    # 组合兼容性最终判据：能 import、能建消息、能往返编解码。
    from src.proto import douyin_pb2

    frame = douyin_pb2.PushFrame()
    frame.payloadType = "hb"
    frame.logId = 1234567890
    blob = frame.SerializeToString()

    parsed = douyin_pb2.PushFrame()
    parsed.ParseFromString(blob)
    assert parsed.payloadType == "hb"
    assert parsed.logId == 1234567890
