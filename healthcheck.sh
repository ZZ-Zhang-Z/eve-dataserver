#!/usr/bin/env bash
# EVE 采集控制器健康检查
# 用法：bash healthcheck.sh（脚本位置即项目根，不依赖固定路径）
# 退出码：0 正常 / 1 存在异常项
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
CTL="$ROOT/controller.py"
fail=0

check() { printf '%-22s %s\n' "$1" "$2"; }

if systemctl is-active --quiet eve-controller 2>/dev/null; then
    check "控制器服务" "active"
else
    check "控制器服务" "未运行"
    fail=1
fi

echo "--- 任务状态 ---"
if ! "$PY" "$CTL" --status 2>/dev/null; then
    check "状态读取" "失败"
    fail=1
fi

echo "--- 资源 ---"
avail=$(df -Pm "$ROOT" | awk 'NR==2{print $4}')
mem=$(awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)
check "可用磁盘(MB)" "${avail:-?}"
check "可用内存(MB)" "${mem:-?}"
if [ "${avail:-0}" -lt 2048 ]; then
    check "  -> 判定" "磁盘低于 2GB"
    fail=1
fi
if [ "${mem:-0}" -lt 180 ]; then
    check "  -> 判定" "内存低于 180MB，任务会被资源闸门拦下"
    fail=1
fi

echo "--- 近 60 分钟控制器告警 ---"
warn=$(journalctl -u eve-controller --since "-60 min" --no-pager 2>/dev/null \
        | grep -c -E " (WARNING|ERROR) " || true)
check "告警条数" "${warn:-0}"

if [ "$fail" -eq 0 ]; then
    echo "结论：正常"
else
    echo "结论：存在异常项（见上）"
fi
exit "$fail"
