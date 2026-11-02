# pytest 全局配置与 autouse fixture：测试环境的确定性隔离（运行时检查 / 日志 / 弹幕枢纽 /
# 凭据缓存 / 翻译 / 标准流编码守卫）。

import os
import shutil
import sys
from collections.abc import Generator
from typing import Any

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
# 测试运行期临时输出目录（SRT 落盘等），会话结束后统一清理，避免残留。
# 只保留 `_out_live`：五个 `test_*_live_collector.py` 双模式脚本（含真机验证）仍把 SRT 落在
# 该目录，不得一并删。[历史注] 2026-09-24 移除 `_out_e2e`——唯一写入方
# tests/test_srt_timeline_anchor.py 已改用 tmp_path，而它原先在**导入期** makedirs、由本钩子在
# **任意**会话退出时 rmtree，正是「全量 `pytest` 运行期间不得再启第二个 pytest 会话」的成因；
# 该约束现由 AGENTS.md「测试产物一律走 tmp_path」条目承载。
_TEST_OUT_DIRS = (os.path.join(_TESTS_DIR, "_out_live"),)


def pytest_configure(config: Any) -> None:
    # 跳过 src 包导入期的运行时检查（node 子进程检查/自动安装）：受限环境下子进程管道
    # 偶发失败会让收集崩溃，跳过也使测试导入确定。
    os.environ.setdefault("DOUYIN_SKIP_RUNTIME_CHECK", "1")
    # 禁用 loguru 异步入队：enqueue 依赖 multiprocessing 命名管道，受限环境可能阻塞/失败
    os.environ.setdefault("DOUYIN_LOG_NO_ENQUEUE", "1")
    # 测试进程导入 main 会注册日志归档 atexit；pytest 退出并非「停止录制」事件，
    # 禁用归档以免改名开发者工作副本里的真实 logs/ 日志（归档专项用例内自行 delenv）
    os.environ.setdefault("DOUYIN_DISABLE_LOG_ARCHIVE", "1")


@pytest.fixture(autouse=True)
def _hermetic_danmaku_hub(monkeypatch: pytest.MonkeyPatch) -> None:
    # 弹幕监控枢纽替换为无文件输出实例：经 DanmakuCollector 上报的测试不写真实
    # logs/danmaku_monitor.jsonl，测试与仓库目录互不污染。
    import src.danmaku_monitor as dm

    monkeypatch.setattr(dm, "_hub", dm.DanmakuMonitorHub(log_path=None))


@pytest.fixture(autouse=True)
def _clean_credential_caches() -> Generator[None]:
    # 凭据缓存进程级隔离：cookie_cache 的 _cookie_cache/_generic_cache 与 spider/ttwid 的
    # 模块级 _cached_* 兜底变量是两套独立状态（singleflight 命中即返回，模块变量仅在调用
    # 方成功时回写），只清一边会让另一边继续提供旧值。跨用例残留会让「打桩后重新拉取」的
    # 断言命中旧值，表现为「单独跑通过、整包跑失败」；yield 前后各清一次，覆盖用例内写入的
    # 下游污染。[历史注] 2026-09-12 审查该把快手 did / Twitch Client-Id / B站 buvid3 /
    # 抖音 ttwid 四处去重统一到 singleflight 后，残留面从 1 个缓存扩大到 2 个。
    from src import spider as _spider
    from src import ttwid as _ttwid
    from src.cookie_cache import clear as _clear

    def _reset() -> None:
        _clear()
        # import 在 fixture 顶部且不做容错：这里出错说明被测模块真的坏了，收集/执行期就该红
        # （ImportError 不是需要吞掉的环境差异）。[历史注] 早前，两个 import 各裹在
        # `try/except Exception: return` 里，src.spider 导入期抛错（或被摘出 sys.modules）时
        # 四个 `_cached_*` 与其后的 `_cached_ttwid` **全部不重置且不报错**。
        _spider._cached_kuaishou_did = ""
        _spider._cached_twitch_client_id = ""
        _spider._bili_buvid_cached = ""
        _spider._bili_buvid_is_fallback = False
        _ttwid._cached_ttwid = ""

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def _pin_identity_translation(monkeypatch: pytest.MonkeyPatch) -> None:
    # 冻结翻译为「恒等映射」，使断言与语言配置/宿主 locale 解耦：i18n.tr() 迁移后，
    # logger/print 的形参日志按当前语言翻译，结果依赖 config.ini 的 language 与宿主系统语言
    # （本机 language 为空 → 探测出 en_US），同一断言在不同机器上会得到不同文本。
    # 断言的是「源语言模板文本」，故 tr(模板, **kw) == 模板.format(**kw) == 迁移前 f-string 输出；
    # 翻译机制本身由 tests/test_i18n_tr.py 与 test_web_api.py 的语言用例单独覆盖。
    import i18n

    monkeypatch.setattr(i18n, "_tr", lambda text: text)


def _stream_policy(stream: object) -> tuple[str | None, str | None]:
    # 取标准流的编码策略；替身对象上缺失或非字符串的取值统一归一为 None，便于直接比较。
    encoding = getattr(stream, "encoding", None)
    errors = getattr(stream, "errors", None)
    return encoding if isinstance(encoding, str) else None, errors if isinstance(errors, str) else None


@pytest.fixture(autouse=True)
def _guard_stdio_encoding_policy() -> Generator[None]:
    # 标准流编码策略守卫（2026-09-23 故障引出的通用护栏）：用例不得改动**宿主进程**的
    # stdout/stderr 编码策略。build_exe._ensure_utf8_streams 的裸 reconfigure(encoding="utf-8")
    # 会把 pytest fd 捕获包装器（EncodedFile，errors="replace"）就地翻成 strict，代价要到
    # 会话收尾读捕获时才以 UnicodeDecodeError 炸出来，还常先嫁祸给无关用例
    # （见 DIAGNOSIS_2026-09-23_pytest-teardown-crash.md）；这里把代价提前到「当场点名」。
    watched = {"stdout": sys.stdout, "stderr": sys.stderr}
    before = {name: _stream_policy(stream) for name, stream in watched.items()}
    yield
    violations: list[str] = []
    for name, stream in watched.items():
        current = getattr(sys, name)
        if current is not stream:
            # pytest 自身的捕获机制会在用例前后替换这两个对象，属框架行为而非用例副作用
            continue
        after = _stream_policy(current)
        if after == before[name]:
            continue
        violations.append(f"sys.{name}: {before[name]} -> {after}")
        # 先尽力复原再断言：避免单个用例的污染顺会话扩散、把后面几十条用例全染红
        encoding, errors = before[name]
        reconfigure = getattr(current, "reconfigure", None)
        if callable(reconfigure) and isinstance(encoding, str) and isinstance(errors, str):
            try:
                reconfigure(encoding=encoding, errors=errors)
            except ValueError, OSError:
                # 已被重定向到已关闭/非法句柄时放过：本守卫只做隔离与点名，不参与判定
                pass
    assert not violations, (
        "用例改动了宿主进程的 stdout/stderr 编码策略（这会破坏 pytest 的 fd 捕获，"
        f"详见 DIAGNOSIS_2026-09-23_pytest-teardown-crash.md）：{'；'.join(violations)}"
    )


def pytest_unconfigure(config: Any) -> None:
    # 会话结束（含收集失败/中断退出）后清理测试输出目录，不残留临时文件。
    # ignore_errors=True：目录不存在或 Windows 下句柄占用（杀毒/索引扫描）时静默跳过，
    # 清理失败不应让 pytest 以异常退出码结束。所列目录已在 .gitignore。当前清单只有
    # `tests/_out_live/`：`tests/_out_e2e/` 已于 2026-09-24 移除（唯一写入方改用 tmp_path），
    # 本钩子不再清理它——旧副本或外部脚本仍可能重建该目录，需要时按需手工清理。
    for out_dir in _TEST_OUT_DIRS:
        shutil.rmtree(out_dir, ignore_errors=True)
