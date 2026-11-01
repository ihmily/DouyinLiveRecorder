# Linux 取数端点约束

> **约束事实源**: dlr-dev-playbook `references/known-pitfalls.md`「构建产物、依赖与运行时基线」下的
> 「发布链运行时二进制必须 fail-closed 钉定」。约束变更以 AGENTS.md 为准。
> [2026-11-01 用户批准] ffmpeg 三槽判据动态化后本文件整体改版；旧「人工钉月末标签」口径作废。

## Linux 取数端点约束

- **判据来源（adopt 档）**：构建期经 `https://api.github.com/repos/BtbN/FFmpeg-Builds/releases?per_page=100`
  列表接口解析**最新月末 autobuild 标签**，取该标签下匹配 `asset_glob` 的唯一 9.0 系非 shared 资产的
  digest 作判据；下载直链与 digest 来自**同一次** API 响应（`build_exe._parse_monthly_releases`，
  纯解析函数；判据与下载对象脱钩 = 恒失配假红）。
- **仍然禁止** `releases/latest` 滚动别名与日更标签作判据或直链：`latest` 是滚动别名（同名资产被上游
  重发即换 digest），日更标签上游只保留约两周（钉它等于预埋一次 404）。月末解析档靠标签形状关
  （`autobuild-YYYY-MM-DD-HH-MM` 且日期 == 月份实际末日，闰年由 `calendar.monthrange` 处理）把两者
  整体排除，不依赖 API 排序约定。
- **资产匹配必须恰好一个**：0 个（标签内容变化）或多于 1 个（glob 放得太宽）一律回退内置表，
  绝不猜。glob 形态如 `ffmpeg-n*-linux64-gpl-9.0.tar.xz`，后缀天然排除 `-gpl-shared-9.0` 变体。
- **静态直链退为回退基线**：解析失败时**整对**回退（`_FFMPEG_DOWNLOAD_URLS` 的内置月末标签直链 +
  `_PINNED_RUNTIME_SHA256` 的内置哈希，两者不可变、带外可验、同批一致），发布继续但版本滞后并
  显式告警——与 windows 槽「回退后滚动产物对旧哈希失配即 fail-closed」不同型，与 node 回退档同构。
- 回归锁：
  - `tests/test_build_exe.py::test_linux_ffmpeg_urls_pin_an_immutable_release_tag`（回退直链仍必须是
    不可变月末标签）；
  - `test_github_pin_asset_name_matches_the_download_url_basename` 的 monthly 分支（回退直链 basename
    必须落在 `asset_glob` 形态内）；
  - 月末解析器用例组（最新标签选择 / 闰年与末日形状 / 歧义资产拒绝 / 坏 digest / 白名单外直链 /
    非 JSON）与 `test_release_ffmpeg_slots_carry_the_user_approved_adopt_ack`（三槽 adopt 姿态锁）。
