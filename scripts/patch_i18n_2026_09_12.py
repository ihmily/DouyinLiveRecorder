# -*- coding: utf-8 -*-
# i18n 模板补齐脚本（2026-09-12 审查）
#
# 修复 test_i18n_migration::test_runtime_templates_covered_by_catalog 失败：
# 把新增 f-string 迁移到 i18n.tr 后产生的 21 条运行时模板加到所有 4 个目录：
#   - i18n/zh_CN/LC_MESSAGES/zh_CN.po  (源 gettext)
#   - i18n/en_US.json
#   - i18n/en_GB.json
#   - i18n/zh_TW.yaml
#
# 新增条目 msgstr 与 msgid 相同（zh_CN 是恒等映射；其它三语给最简占位译文）：
# en_US/en_GB 直接复用 msgid 占位符；zh_TW 同理；并调用 compile_po 重生成 .mo。
#
# 设计取舍：脚本是一次性维护工具（2026-09-12 之后无新增即不应再运行），故所有
# 字符串与表项以常量形式写在本文件，而非走 i18n.tr——后者会因本脚本无运行上下文
# 而被 i18n 提取器误识别为运行时模板。脚本注释密度低是有意为之（无业务逻辑），
# 仍通过 check_annotations 的密度阈值；如有偏差按需补注释。
import json
import subprocess
import sys
from pathlib import Path

# ROOT 由硬编码的旧开发机路径改为「本文件所在仓库根」（M-22，2026-10-18 审查）：
# 原值 Path("D:/DouyinLiveRecorder-dev") 只在那台机器上成立，在本仓运行会在 append_po()
# 的第一次 read_text 就抛 FileNotFoundError（连一条目录都没补上就崩栈），使这个「可幂等重跑」
# 的补齐件完全不可用；按 __file__ 定位与 src/javascript/*.js 的同款惯例（AGENTS.md 关键约定 #5）。
ROOT = Path(__file__).resolve().parent.parent
PO_PATH = ROOT / "i18n" / "zh_CN" / "LC_MESSAGES" / "zh_CN.po"
EN_US = ROOT / "i18n" / "en_US.json"
EN_GB = ROOT / "i18n" / "en_GB.json"
ZH_TW = ROOT / "i18n" / "zh_TW.yaml"

# 21 个新增模板（zh_CN 是恒等映射，msgstr = msgid）
NEW_TEMPLATES = [
    (
        "[弹幕]后台协程异常: {type_name}: {exc}",
        "Background coroutine exception: {type_name}: {exc}",
        "[彈幕]後台協程異常: {type_name}: {exc}",
        "[彈幕]後台協程異常: {type_name}: {exc}",
    ),
    (
        "[B站弹幕]帧解析异常: {type_name} head={head}",
        "[Bilibili danmaku] frame parse error: {type_name} head={head}",
        "[B站彈幕]幀解析異常: {type_name} head={head}",
        "[B站彈幕]幀解析異常: {type_name} head={head}",
    ),
    (
        "[B站弹幕]消息解析异常: {type_name} item={item}",
        "[Bilibili danmaku] message parse error: {type_name} item={item}",
        "[B站彈幕]訊息解析異常: {type_name} item={item}",
        "[B站彈幕]訊息解析異常: {type_name} item={item}",
    ),
    (
        "[抖音弹幕]帧解析异常: {type_name} head={head}",
        "[Douyin danmaku] frame parse error: {type_name} head={head}",
        "[抖音彈幕]幀解析異常: {type_name} head={head}",
        "[抖音彈幕]幀解析異常: {type_name} head={head}",
    ),
    (
        "[抖音弹幕]弹幕解析异常: {type_name} payload={payload}",
        "[Douyin danmaku] message parse error: {type_name} payload={payload}",
        "[抖音彈幕]彈幕解析異常: {type_name} payload={payload}",
        "[抖音彈幕]彈幕解析異常: {type_name} payload={payload}",
    ),
    (
        "[斗鱼弹幕]帧解析异常: {type_name} head={head}",
        "[Douyu danmaku] frame parse error: {type_name} head={head}",
        "[鬥魚彈幕]幀解析異常: {type_name} head={head}",
        "[鬥魚彈幕]幀解析異常: {type_name} head={head}",
    ),
    (
        "[虎牙弹幕]帧解析异常: {type_name} head={head}",
        "[Huya danmaku] frame parse error: {type_name} head={head}",
        "[虎牙彈幕]幀解析異常: {type_name} head={head}",
        "[虎牙彈幕]幀解析異常: {type_name} head={head}",
    ),
    ("ffmpeg SHA256 校验通过", "ffmpeg SHA256 verification passed", "ffmpeg SHA256 校驗通過", "ffmpeg SHA256 校驗通過"),
    (
        "Node.js SHA256 校验通过",
        "Node.js SHA256 verification passed",
        "Node.js SHA256 校驗通過",
        "Node.js SHA256 校驗通過",
    ),
    ("蓝奏云 SHA256 校验通过", "lanzou SHA256 verification passed", "藍奏雲 SHA256 校驗通過", "藍奏雲 SHA256 校驗通過"),
    (
        "首次下载 SHA256 已记录：{current_hash}",
        "First download SHA256 recorded: {current_hash}",
        "首次下載 SHA256 已記錄：{current_hash}",
        "首次下載 SHA256 已記錄：{current_hash}",
    ),
    (
        "首次下载 Node.js SHA256 已记录：{current_hash}",
        "First Node.js SHA256 recorded: {current_hash}",
        "首次下載 Node.js SHA256 已記錄：{current_hash}",
        "首次下載 Node.js SHA256 已記錄：{current_hash}",
    ),
    (
        "蓝奏云 ffmpeg SHA256: {lanzou_hash}",
        "lanzou ffmpeg SHA256: {lanzou_hash}",
        "藍奏雲 ffmpeg SHA256: {lanzou_hash}",
        "藍奏雲 ffmpeg SHA256: {lanzou_hash}",
    ),
    (
        "蓝奏云为非官方个人分发源，建议优先使用 gyan.dev 官方源。",
        "lanzou is a third-party distribution source; prefer the gyan.dev official source.",
        "藍奏雲為非官方個人分發源，建議優先使用 gyan.dev 官方源。",
        "藍奏雲為非官方個人分發源，建議優先使用 gyan.dev 官方源。",
    ),
    (
        "ffmpeg 官方源 zip SHA256 与上次记录不一致（{expected} vs {actual}）。可能 CDN 被篡改或版本变更。请删除 {hash_file} 后重试，或手动下载校验。",
        "ffmpeg official source zip SHA256 differs from last record ({expected} vs {actual}). CDN may be tampered or version changed. Please delete {hash_file} and retry, or download manually for verification.",
        "ffmpeg 官方源 zip SHA256 與上次記錄不一致（{expected} vs {actual}）。可能 CDN 被篡改或版本變更。請刪除 {hash_file} 後重試，或手動下載校驗。",
        "ffmpeg 官方源 zip SHA256 與上次記錄不一致（{expected} vs {actual}）。可能 CDN 被篡改或版本變更。請刪除 {hash_file} 後重試，或手動下載校驗。",
    ),
    (
        "Node.js zip SHA256 与上次记录不一致（{expected} vs {actual}）。可能 CDN 被篡改或版本变更。请删除 {hash_file} 后重试，或手动下载校验。",
        "Node.js zip SHA256 differs from last record ({expected} vs {actual}). CDN may be tampered or version changed. Please delete {hash_file} and retry, or download manually for verification.",
        "Node.js zip SHA256 與上次記錄不一致（{expected} vs {actual}）。可能 CDN 被篡改或版本變更。請刪除 {hash_file} 後重試，或手動下載校驗。",
        "Node.js zip SHA256 與上次記錄不一致（{expected} vs {actual}）。可能 CDN 被篡改或版本變更。請刪除 {hash_file} 後重試，或手動下載校驗。",
    ),
    (
        "蓝奏云 ffmpeg SHA256 与 FFMPEG_LANZOU_SHA256 不一致（{expected} vs {actual}）。拒绝安装。",
        "lanzou ffmpeg SHA256 differs from FFMPEG_LANZOU_SHA256 ({expected} vs {actual}). Installation rejected.",
        "藍奏雲 ffmpeg SHA256 與 FFMPEG_LANZOU_SHA256 不一致（{expected} vs {actual}）。拒絕安裝。",
        "藍奏雲 ffmpeg SHA256 與 FFMPEG_LANZOU_SHA256 不一致（{expected} vs {actual}）。拒絕安裝。",
    ),
    (
        "写入 SHA256 缓存失败（不影响本次安装）: {e}",
        "Failed to write SHA256 cache (does not affect current install): {e}",
        "寫入 SHA256 快取失敗（不影響本次安裝）: {e}",
        "寫入 SHA256 快取失敗（不影響本次安裝）: {e}",
    ),
    (
        "读取 SHA256 缓存失败，跳过校验: {e}",
        "Failed to read SHA256 cache, skipping verification: {e}",
        "讀取 SHA256 快取失敗，跳過校驗: {e}",
        "讀取 SHA256 快取失敗，跳過校驗: {e}",
    ),
    (
        "原子写失败（已保留原文件）: {file_path} - {type_name}: {e}",
        "Atomic write failed (original file preserved): {file_path} - {type_name}: {e}",
        "原子寫失敗（已保留原檔案）: {file_path} - {type_name}: {e}",
        "原子寫失敗（已保留原檔案）: {file_path} - {type_name}: {e}",
    ),
    (
        "读取 URL 配置失败，跳过删除: {e}",
        "Failed to read URL config, skipping deletion: {e}",
        "讀取 URL 配置失敗，跳過刪除: {e}",
        "讀取 URL 配置失敗，跳過刪除: {e}",
    ),
]


def append_po() -> int:
    # 追加到 gettext 源（zh_CN 是恒等映射，msgstr = msgid 即可）；
    # 已存在条目跳过——保证多次运行幂等（CI 重复跑不会污染）
    text = PO_PATH.read_text(encoding="utf-8")
    added = 0
    out_lines = []
    for msgid_zh, _msgstr_en, _msgstr_gb, _msgstr_tw in NEW_TEMPLATES:
        # msgid 已存在就跳过（按字面字符串精确匹配，不做翻译回查）
        if f'msgid "{msgid_zh}"' in text:
            continue
        out_lines.append("")
        out_lines.append(f'msgid "{msgid_zh}"')
        out_lines.append(f'msgstr "{msgid_zh}"')
        added += 1
    if out_lines:
        # 直接 append 到文件末尾：与既有「补齐条目」段风格一致，无须重排既有条目
        with PO_PATH.open("a", encoding="utf-8") as f:
            f.write("\n".join(out_lines) + "\n")
    return added


def append_json(path: Path, lang: str) -> int:
    # 加载 → 追加 → 写回；JSON 是 dict 字面量映射，与 .po 的 msgid 字段一对一对应
    obj = json.loads(path.read_text(encoding="utf-8"))
    added = 0
    # NEW_TEMPLATES 元组位置：1=en_US 译文、2=en_GB 译文、3=zh_TW 译文
    # ——与 i18n.py 语言目录加载优先级一致
    idx = {"en_US": 1, "en_GB": 2, "zh_TW": 3}[lang]
    for entry in NEW_TEMPLATES:
        msgid_zh, msgstr_en, msgstr_gb, msgstr_tw = entry
        msgstr = (msgstr_en, msgstr_gb, msgstr_tw)[idx - 1]
        # 已存在跳过：避免覆盖人工精修译文
        if msgid_zh in obj:
            continue
        # 在 dict 末尾追加：JSON dict 本就无序，写入位置不影响翻译查找
        obj[msgid_zh] = msgstr
        added += 1
    if added:
        # indent=2 与既有文件风格对齐；ensure_ascii=False 保中文/全角字符不被 \uXXXX 转义
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def append_yaml() -> int:
    # YAML 解析/写回：直接当 key: value 追加，复杂结构可能与 yaml 模块的 round-trip 不一致；
    # 但本文件是单层 key-value 字符串映射，与 JSON 同构，直接正则追加即可（避免对 yaml 库 round-trip 的依赖）
    text = ZH_TW.read_text(encoding="utf-8")
    added = 0
    new_lines = []
    for entry in NEW_TEMPLATES:
        msgid_zh, _en, _gb, msgstr_tw = entry
        # 已存在则跳过：单层 key-value 文件不做深度比对，字面字符串存在即可
        if f'"{msgid_zh}": ' in text or f"'{msgid_zh}': " in text:
            continue
        # YAML 双引号字符串需要转义 \ 和 "；与 JSON 不同，YAML 还需考虑 :、# 等特殊字符，
        # 本目录字符串均为常见中文 + 标识符占位符，无须额外处理
        msgid_escaped = msgid_zh.replace("\\", "\\\\").replace('"', '\\"')
        msgstr_escaped = msgstr_tw.replace("\\", "\\\\").replace('"', '\\"')
        new_lines.append(f'"{msgid_escaped}": "{msgstr_escaped}"')
        added += 1
    if new_lines:
        # append 模式：不重排既有条目，与文件中既有「以 json/yaml 同构追加」惯例一致
        with ZH_TW.open("a", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")
    return added


def main() -> int:
    # 四份目录并行追加；任一文件写入失败应让脚本退出非零以便发现
    # （不静默退化为"只成功一部分"——追加失败的目录会让运行时模板缺失）
    n_po = append_po()
    n_en = append_json(EN_US, "en_US")
    n_gb = append_json(EN_GB, "en_GB")
    n_tw = append_yaml()
    # 输出追加条数：手工核对 4 份目录一致；不一致须人工介入（极小概率）
    print(f"Appended: po={n_po} en_US={n_en} en_GB={n_gb} zh_TW={n_tw}")
    # 重编译 .mo：与 zh_CN.po 同步——CI 用 compile_po.py --check 强制 .mo 与 .po 字节级一致，
    # 此处直接调脚本以跑标准编译流程而不是手工编译（避免编码/字节序等边角差异）
    # 解释器一律取 sys.executable 而不是按名字起 `python`（L-29/M-22 同族坑）：① PATH 无 `python`
    # 时 subprocess.run 抛 FileNotFoundError 而非回非零码，本脚本会以崩溃栈退出；② 系统 python 与
    # 项目 venv 混用时，3.13 解释器会对 PEP 758 无括号 except 语法误报 SyntaxError（AGENTS.md「Python 版本」）。
    res = subprocess.run(
        [sys.executable, "scripts/compile_po.py"], cwd=str(ROOT), capture_output=True, text=True, check=False
    )
    print("compile_po stdout:", res.stdout)
    print("compile_po stderr:", res.stderr)
    print("compile_po returncode:", res.returncode)
    # returncode 非零透传给上层（CI 可见）；append 阶段无显式 return，由 0 兜底
    # M-21（2026-10-18 审查）：上一行注释描述的就是本函数的契约，但旧实现在此无条件 return 0，
    # 于是 .mo 编译失败（compile_po 退非 0）在 CI 完全不可见——翻译产物缺失却被报成成功。
    return int(res.returncode)


if __name__ == "__main__":
    sys.exit(main())
