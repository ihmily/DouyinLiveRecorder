#!/usr/bin/env bash
# =============================================================================
# CI 专用：Web 管理面板 HTTP 冒烟的一次完整尝试（启动 → 就绪等待 → 断言 → 收尾）
# -----------------------------------------------------------------------------
# 为什么落成脚本而不是 workflow 内联 run：本步经 .github/actions/retry 复合动作执行
# （网络型抖动重试策略收敛在 action.yml 一处，AGENTS.md 统一策略禁止 job 内重新内联 for 循环），
# 而 retry 只接受**单条命令字符串**；且每轮重试都必须从零起一个干净面板进程——四段逻辑收进
# 本脚本后，retry 的每一轮都会重新执行它，天然得到「重开面板」语义（进程崩了、端口被上一轮
# 残留占用时能自愈）。retry 以 `bash -c "$CMD"` 执行、cwd = 仓库根，故相对路径可用。
#
# 退出码 = 冒烟结论（关键契约）：
#   本脚本以 smoke_test.py 的退出码退出（0 通过 / 1 断言失败 / 2 配置问题）；面板未起 /
#   就绪超时等启动类故障统一退 1。retry 见非 0 即按 attempts 重试，最终仍非 0 会让
#   「Web panel smoke test」步骤变红——这正是「明确失败即让该 job 变红」的落点，因此
#   workflow 不再需要单独的落锤步骤（失败工件由后续 `if: always()` 上传步骤保留）。
# =============================================================================
# M-96（2026-10-21）：补 -e。此前只有 `set -uo pipefail`，中间任何一步失败都被静默吞掉——
# 典型是「面板日志转储失败」或「报告写出失败」这类本应立刻判失败的故障，脚本仍带着上一个
# 命令的残留 rc 继续往下走，把启动类故障混淆成冒烟结论。加 -e 的同时必须把下面几处「失败即
# 预期」的调用改成显式吞退出码（pkill/kill 无匹配返回非 0、`rc=$?` 与 `$(...)` 的赋值捕获），
# 否则 -e 会在拿到结论前就中止脚本。
set -euo pipefail

PANEL_LOG=logs/web-panel-smoke.log
REPORT=logs/web-smoke-report.json
PID_FILE=logs/web-panel.pid
# 就绪等待上限（秒）：uvicorn + fastapi 冷加载在 runner 上通常 3~8s，留足余量到 90s；
# 超时即判失败（进程没起来或卡死），不往下跑断言，避免把「没起来」混淆成「接口断言失败」。
READY_LIMIT=90
PORT=8000

# 收尾：杀掉本轮面板进程及其子进程（uvicorn 可能带 worker；录制引擎是守护线程，随主进程退出）。
# 恒返回 0：清理失败不得掩盖冒烟结论（真正的判定依据是本脚本的最终 exit 码）。
panel_pid=""
cleanup() {
  if [ -n "$panel_pid" ] && kill -0 "$panel_pid" 2>/dev/null; then
    # set -e 下这些「无匹配/已退出」的清理命令返回非 0 会直接中止 EXIT trap，故显式吞掉。
    pkill -P "$panel_pid" 2>/dev/null || true
    kill "$panel_pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$panel_pid" 2>/dev/null || break
      sleep 1
    done
    kill -9 "$panel_pid" 2>/dev/null || true
  fi
  # 兜底只清**本轮进程树**的漏网子进程（M-96，2026-10-21）。旧形态 `pkill -f 'python web\.py'`
  # 按命令行子串匹配，共享 runner 上任何同名进程都会被无差别杀掉，与本脚本「只收拾自己起的
  # 进程」的边界相悖；上面 `pkill -P "$panel_pid"` 已在父进程被杀前覆盖常规子进程，故这里
  # 不再保留按名字的全量清理。pkill 无匹配时返回非 0，故吞掉退出码。
  if [ -n "$panel_pid" ]; then
    pkill -P "$panel_pid" 2>/dev/null || true
  fi
  return 0
}
trap cleanup EXIT

mkdir -p config logs
# 全注释的 URL 清单 → 待录制房间为空，引擎只跑配置热加载循环，绝不起 ffmpeg、绝不访问
# 平台接口（与 build_exe.py 冒烟的 _ensure_url_config 同一手法）。
[ -s config/URL_config.ini ] || echo '#https://live.douyin.com/000000000000' >config/URL_config.ini
# config/config.ini 不入库（含口令/Cookie），缺失时 read_web_config 回退 WEB_DEFAULTS：
# 127.0.0.1:8000 + 不开认证，与 smoke_web.json 的 base_url 对齐。

# 启动面板。子 shell + & 让它脱离本脚本的控制终端；PID 记入全局供 cleanup 使用。
nohup python web.py >"$PANEL_LOG" 2>&1 &
panel_pid=$!
echo "$panel_pid" >"$PID_FILE"

# 就绪等待：轮询 /health（恒公开、不依赖认证开关，见 src/web_api.py）。连接被拒
# （进程仍在导入 fastapi/uvicorn）期间静默重试；进程中途退出则立即判失败并转储日志。
ready=""
for ((i = 0; i < READY_LIMIT; i++)); do
  if ! kill -0 "$panel_pid" 2>/dev/null; then
    echo "::error::面板进程在就绪等待期间退出，$PANEL_LOG 末尾："
    tail -n 80 "$PANEL_LOG" 2>/dev/null || true
    exit 1
  fi
  if curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    ready=yes
    echo "面板就绪（等待 ${i}s），开始断言"
    break
  fi
  sleep 1
done
if [ -z "$ready" ]; then
  echo "::error::面板在 ${READY_LIMIT}s 内未对 /health 应答，$PANEL_LOG 末尾："
  tail -n 80 "$PANEL_LOG" 2>/dev/null || true
  exit 1
fi

# 断言：与本地用法完全一致（scripts/smoke_web.json），不在此处重复维护期望值。
# 报告无条件写出（成功/失败都留一份机读结果），供 workflow 上传为工件。
# set -e 下 `cmd; rc=$?` 拿不到非零码（命令失败即中止），必须写成 `rc=0; cmd || rc=$?`。
rc=0
python scripts/smoke_test.py -c scripts/smoke_web.json -r "$REPORT" -f json || rc=$?

# MIN-2260：rc=0 只代表「已执行的检查全通过」，不代表「执行过检查」。smoke_test.py 现在
# 对空 checks 退 2，但报告仍可能被上一轮残留 / 被截断 / 被换成别的文件——故以**实物报告**
# 再断言一次 summary.total > 0。两道判据互不替代：脚本侧管配置损坏，这里管工件与结论的一致性。
if [ "$rc" -eq 0 ]; then
  # 同上：命令替换失败会被 set -e 拦下，而「报告不可解析」本身要落到下面 rc=2 的分支里判。
  total=$(python -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["summary"]["total"])' "$REPORT" 2>/dev/null) || total=""
  case "$total" in
    ''|*[!0-9]*)
      echo "::error::冒烟报告 $REPORT 的 summary.total 不可解析（实际值：${total:-<空>}），判失败"
      rc=2
      ;;
    *)
      if [ "$total" -le 0 ]; then
        echo "::error::冒烟报告 summary.total=$total，一条断言都没执行，判失败"
        rc=2
      else
        echo "冒烟报告断言条数：$total"
      fi
      ;;
  esac
fi

echo "冒烟退出码：$rc"
exit "$rc"
