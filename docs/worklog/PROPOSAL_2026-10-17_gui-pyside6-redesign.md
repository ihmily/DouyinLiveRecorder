# GUI 重设计：迁移 PySide6 并按 gui-redesign 视觉语言重构

> 状态：设计已批准（2026-10-17 用户确认「无异议，执行」）。本文件是本次改造的规格事实源。
> **[2026-10-31 结项]** 迁移期 legacy tkinter 栈已完全移除：`gui.py` 退化为薄入口，`src/ui_kit.py` / `src/ui_motion.py` 与 ttk 主题注册、Tk 字体解析均已删除，PySide6 为唯一窗口实现。下文的「迁移期保留 / 验证后删除」按完成态理解。
> 视觉事实源：`docs/gui-redesign/index.html`（设计令牌、布局骨架、动效曲线）。

## 1. 背景与目标

- 现有 `gui.py`（5243 行，纯 tkinter/ttk + `src/ui_kit.py` + `src/ui_theme.py`）已完成 UI 现代化五阶段，但 ttk 无法原生实现设计稿的大圆角卡片（radius 8–24px）、柔和投影与弹簧动效。
- 用户决策（2026-10-17）：**迁移 PySide6**；还原范围为「视觉语言全覆盖 + 部分交互细节（空状态引导 / Toast / 卡片悬浮态）」；不引入聊天式交互。
- 必须保证：性能良好、界面不卡顿、原有功能完整可用。

## 2. 架构

```
gui.py                      # 瘦入口：参数 → QApplication → MainWindow
src/gui_qt/
  app.py                    # 应用装配、崩溃 Sink、退出序列
  theme.py                  # 设计令牌（对齐 HTML :root）→ QSS 模板运行时渲染
  widgets/                  # Card（圆角+投影）、Sidebar、NavButton、Toast、
                            #   StatusDot（脉冲）、DataTable（QTableView + 模型）
  pages/                    # dashboard / config / logs / quality / danmaku
  tray.py                   # QSystemTrayIcon 替代 pystray
  controllers/              # 录制子进程管理、日志总线（队列+节流 flush）、
                            #   弹幕尾随、配置监听——不含 Qt import（Signal 桥接除外），可离屏单测
```

- 控制器层与 UI 解耦是本次迁移的净收益：现状 tk 耦合导致大量逻辑只能在真窗下验证。
- 线程模型：子进程 stdout 读取、弹幕尾随放 QThread，经 Signal 回主线程（替代现 `post_ui` 队列泵）。
- 日志/弹幕页高吞吐：模型层批量 append + 60ms 节流 flush，虚拟化列表而非逐行控件。

## 3. 视觉令牌（与 HTML :root 一一对应）

| 令牌 | 浅色 | 深色 |
| --- | --- | --- |
| accent | #c96442 | #d97757 |
| bg-app | #f7f7f5 | #1b1b19 |
| bg-sidebar | #f0efec | #171716 |
| bg-elevated | #ffffff | #262624 |
| text-1/2/3 | #1a1a1a / #5c5c5c / #9a9a9a | #ececea / #a3a3a0 / #6b6b68 |
| border / border-strong | rgba(0,0,0,.08/.14) | rgba(255,255,255,.08/.16) |
| 圆角 | 8 / 12 / 18 / 24 | 同左 |
| 阴影 | 三档（QGraphicsDropShadowEffect，仅卡片等静态元素） | 同左 |
| 缓动 | spring cubic-bezier(.34,1.4,.44,1)、out cubic-bezier(.22,.8,.36,1) | 同左 |

主题持久化沿用 `config.ini [GUI] gui_theme`（空 = 跟随系统），键名不变。

## 4. 依赖 / 打包 / 测试

- `PySide6>=6.10`（Python 3.14 支持起点）进 `[project.optional-dependencies].gui` 与 `requirements.txt`——两侧包名集合相等由 `tests/test_regression_gates.py` 锁死，必须同批双写。
- `build_exe.py`：`collect_all('PySide6')`，`BLOAT_EXCLUDES` 维持挂三个 Analysis；体积预计 91.81MB → ~150MB+，完成后 `scripts/report_bundle_size.py` 实测刷新基线并落 `measured-evidence.md`。
- 测试：`QT_QPA_PLATFORM=offscreen` 真窗断言（替代 xvfb 方案）；主题 token/对比度契约、页面装配、控制器逻辑三类；旧 `test_ui_kit.py` / `test_ui_theme.py` 随 ttk 层退役删除。
- i18n 复用 `src/ui_i18n.py`（迁移时验证 tk 独立性，有耦合则抽离）。
- 平台专属代码（ctypes 控制台、kernel32）原样搬运；mypy 双平台增跑照旧。

## 5. 风险与回滚

- LGPL：PySide6 动态链接分发合规，exe 打包属标准做法。
- 最大风险 = 工期与回归面：五页 + 托盘 + 高级设置窗全量重写。缓解：按页分批，每批门禁全绿；迁移期旧 ttk 版改名 `gui_legacy.py` 共存，新 GUI 真机验证通过后删除（git 历史可回滚）。
- 假设：①只移植视觉语言 + 空态/Toast/悬浮态；②接受体积增长 50–70MB；③旧版验证后退役。

## 6. 批次计划

0. 依赖接入 + 骨架（theme/app/主窗口/侧边栏）
1. 控制器层（录制/日志/配置/弹幕）
2. 五页面逐页落地
3. 托盘、高级设置窗、退出序列
4. 测试 + 门禁全绿 + 文档（CODE_WIKI 双侧）+ 体积实测 + 收尾清理
