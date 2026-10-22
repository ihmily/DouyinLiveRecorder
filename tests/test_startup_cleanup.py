# 启动期陈旧字节码缓存清理（src/startup_cleanup.py）回归测试。
#
# 覆盖：
# 1. 扫描根白名单越界防护（downloads/ logs/ tests/ scripts/ node/ 及「不含 .py 的目录」必须存活）
# 2. 目录名不精确等于 __pycache__ 时一律不动
# 3. 指纹一致 → 零删除（健康轮次不重编译）
# 4. 仅版本号变 → 触发清理
# 5. 源码同 size、同 mtime、只改内容 → 仍能检出（锁住「内容哈希」不变量，mtime 实现必红）
# 6. 单个文件删除失败 → 不抛异常、计入 errors、哨兵仍写（不重复触发风暴）
# 7. 冻结 exe → no-op
# 8. 配置开关关闭 → 零 I/O（不删、不建哨兵）
# 9. 哨兵缺失 → 清一次并建立基线（读不到基线就无法证明缓存新鲜）
#
# 判据全部走真实文件系统与被测实现（AGENTS.md「测试不得自实现被测逻辑」）：只在 tmp_path 下造
# 目录树、只在用例 6 用「同名目录冒充 .pyc」让 unlink 天然抛 OSError，不 patch 任何 stdlib 模块属性。

import os
from pathlib import Path

import pytest

import src.startup_cleanup as startup_cleanup

# __pycache__ 里的替身内容：固定 32 字节的假 .pyc，只为让目录非空、可被统计与删除
_CACHE_PAYLOAD = b"x" * 32


def _make_tree(root: Path) -> None:
    # 搭一棵最小可用的伪应用树：三个合法扫描根 + 若干必须存活的越界位置。
    (root / "main.py").write_text("print(1)\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "utils.py").write_text("A = 1\n", encoding="utf-8")
    (root / "src" / "platforms").mkdir()
    (root / "src" / "platforms" / "__init__.py").write_text("", encoding="utf-8")
    # ①类越界：不在白名单根内，但目录里有 .py（真实的 tests/ 与 scripts/ 正是这种形态，
    #    本机实测 tests/__pycache__ 有 128 个 .pyc）——只有「正向白名单」这条规则能救它们
    for rel in _OUT_OF_SCOPE_WITH_PY:
        (root / rel).mkdir(parents=True, exist_ok=True)
        (root / rel / "payload.py").write_text("B = 2\n", encoding="utf-8")
    # ②类越界：在白名单树内但直接不含 .py（真实对应 src/javascript/，只有签名脚本）——
    #    只有「目录直接含 .py 才算缓存根」这条规则能救它们
    (root / "src" / "javascript").mkdir()
    (root / "src" / "javascript" / "sign.js").write_text("//\n", encoding="utf-8")
    (root / "src" / "old_build").mkdir()


def _cache_dir(dirs_under: Path, names: tuple[str, ...] = ("a.pyc",)) -> Path:
    # 建 __pycache__ 并写入指定文件名，返回该缓存目录
    dirs_under.mkdir(parents=True, exist_ok=True)
    for name in names:
        (dirs_under / name).write_bytes(_CACHE_PAYLOAD)
    return dirs_under


# 必须被清理的扫描根内缓存位置（相对 app_root）
_IN_SCOPE = ("__pycache__", "src/__pycache__", "src/platforms/__pycache__")
# ①类越界位置：目录含 .py 但不属于白名单根
_OUT_OF_SCOPE_WITH_PY = (
    "logs",
    "downloads",
    "tests",
    "scripts",
    "node",
    "my_data",
)
# ②类越界位置：白名单树内但不含 .py
_OUT_OF_SCOPE_NO_PY = ("src/javascript", "src/old_build")
_OUT_OF_SCOPE = tuple(f"{rel}/__pycache__" for rel in (*_OUT_OF_SCOPE_WITH_PY, *_OUT_OF_SCOPE_NO_PY))


def _seed(root: Path) -> None:
    # 在白名单内/外各造一个缓存目录，供「删了谁、留了谁」逐条比对
    for rel in _IN_SCOPE:
        _cache_dir(root / rel)
    for rel in _OUT_OF_SCOPE:
        _cache_dir(root / rel)


def test_purges_only_whitelisted_roots(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    _seed(tmp_path)

    result = startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=True)

    assert result.removed_dirs == len(_IN_SCOPE)
    for rel in _IN_SCOPE:
        assert not (tmp_path / rel).exists(), f"白名单内缓存未清: {rel}"
    for rel in _OUT_OF_SCOPE:
        assert (tmp_path / rel).is_dir(), f"越界目录被删（清理范围失控）: {rel}"


def test_directory_not_named_pycache_is_untouched(tmp_path: Path) -> None:
    # 缓存目录名必须逐字相等：近似名（__pycache__2 / pycache）即便落在扫描根内也不得动
    _make_tree(tmp_path)
    keep = _cache_dir(tmp_path / "src" / "__pycache__2")
    keep2 = _cache_dir(tmp_path / "src" / "pycache")

    startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=True)

    assert keep.is_dir() and keep2.is_dir()


def test_unchanged_sources_do_not_purge_again(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    first = _cache_dir(tmp_path / "src" / "__pycache__")

    startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=True)
    assert not first.exists(), "首轮未建立基线并清理"
    rebuilt = _cache_dir(first)

    result = startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=True)

    assert result.triggered is False
    assert result.removed_dirs == 0
    assert rebuilt.is_dir(), "源码未变却再次删除（每轮都会白付重编译成本）"


def test_version_change_triggers_purge(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=True)
    cache = _cache_dir(tmp_path / "src" / "__pycache__")

    result = startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.1.0", enabled=True)

    assert result.triggered is True
    assert not cache.exists()


def test_same_size_same_mtime_content_change_is_detected(tmp_path: Path) -> None:
    # 本条是「内容哈希」与「mtime 指纹」的唯一分水岭：覆盖升级时复制工具常保留 mtime，
    # 若源码长度恰好也没变，Python 自身的 timestamp 失效判定与 mtime 式指纹会同时失明。
    _make_tree(tmp_path)
    source = tmp_path / "src" / "utils.py"
    startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=True)

    original = (source.stat().st_mtime_ns, source.stat().st_size)
    source.write_text("A = 2\n", encoding="utf-8")
    assert source.stat().st_size == original[1], "替身内容长度须与原文一致，否则本条退化成 size 判定"
    os.utime(source, ns=(original[0], original[0]))
    cache = _cache_dir(tmp_path / "src" / "__pycache__")

    result = startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=True)

    assert result.triggered is True, "同 size 同 mtime 的内容变化未被检出（指纹退化为 mtime/size 判定）"
    assert not cache.exists()


def test_delete_failure_is_contained(tmp_path: Path) -> None:
    # 让 unlink 天然抛 OSError：在缓存目录里放一个「名字以 .pyc 结尾的子目录」。
    # Windows 上 unlink 目录抛 PermissionError、POSIX 抛 IsADirectoryError，同属 OSError，
    # 故本条不依赖任何 stdlib 打桩即可跨平台执行（Linux CI 与 Windows 本机同判据）。
    _make_tree(tmp_path)
    cache = _cache_dir(tmp_path / "src" / "__pycache__")
    (cache / "blocked.pyc").mkdir()
    other = _cache_dir(tmp_path / "__pycache__")

    result = startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=True)

    assert result.errors >= 2, "unlink 与 rmdir 两处失败都要计入，否则删不净被抹成零信息"
    assert cache.is_dir(), "非字节码残留被连带删掉（越界删除）"
    assert other.exists() is False, "同批次里可删的目录被失败项带崩"
    assert result.triggered is True
    assert startup_cleanup._stamp_path(tmp_path).is_file(), "删除失败即不写基线，会每轮重复全量清理"


def test_frozen_build_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 冻结包（PyInstaller）的 script_path 指向 _internal/，其内不存在 __pycache__；
    # 形态判定按 AGENTS.md 抽成模块级常量并走 monkeypatch，让该分支在任意主机上真实执行。
    _make_tree(tmp_path)
    cache = _cache_dir(tmp_path / "src" / "__pycache__")
    monkeypatch.setattr(startup_cleanup, "_IS_FROZEN", True)

    result = startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=True)

    assert result.triggered is False
    assert cache.is_dir()
    assert not startup_cleanup._stamp_path(tmp_path).exists()


def test_disabled_performs_no_io(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    cache = _cache_dir(tmp_path / "src" / "__pycache__")

    result = startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=False)

    assert result.triggered is False
    assert cache.is_dir()
    assert not startup_cleanup._stamp_path(tmp_path).exists(), "开关关闭仍读写哨兵（零动作约定落空）"


def test_missing_stamp_purges_once_and_establishes_baseline(tmp_path: Path) -> None:
    # 覆盖升级 + logs/ 被清（或换目录安装）是本功能要服务的主场景：此时无基线可比，
    # 保守动作是清一次（代价仅一轮重编译），而不是静默放弃。
    _make_tree(tmp_path)
    cache = _cache_dir(tmp_path / "src" / "__pycache__")
    assert not startup_cleanup._stamp_path(tmp_path).exists()

    result = startup_cleanup.purge_stale_bytecode_caches(tmp_path, version="v1.0.0", enabled=True)

    assert result.triggered is True
    assert not cache.exists()
    assert startup_cleanup._stamp_path(tmp_path).is_file()
