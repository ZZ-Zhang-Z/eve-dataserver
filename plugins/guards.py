"""闸门插件：任务启动前的准入检查。

任一闸门不通过，本轮就跳过并记录原因，等下一轮再试。
新增闸门的模板：

    @register_guard("token_balance")
    class TokenGuard:
        def __init__(self, spec, cfg): ...
        def check(self, ctx) -> (bool, str): ...
"""
import time
from datetime import datetime

import monitor
from core.registry import register_guard
from plugins.schedules import in_window, parse_hhmm


@register_guard("resources")
class ResourceGuard:
    """内存 / 磁盘 / 负载闸门。任务级 spec 可覆盖全局 cfg.resources。"""

    def __init__(self, spec, cfg):
        self.cfg = cfg or {}
        self.limits = dict(self.cfg.get("resources") or {})
        for key, value in (spec or {}).items():
            if key not in ("type", "name"):
                self.limits[key] = value

    def check(self, ctx):
        snapshot = monitor.sample(ctx.root)
        ctx.scratch["resources"] = snapshot
        return monitor.check(snapshot, self.limits)

    def describe(self):
        parts = []
        if self.limits.get("min_free_mem_mb"):
            parts.append(f"内存≥{self.limits['min_free_mem_mb']}MB")
        if self.limits.get("min_free_disk_mb"):
            parts.append(f"磁盘≥{self.limits['min_free_disk_mb']}MB")
        if self.limits.get("max_load_per_core"):
            parts.append(f"load≤{self.limits['max_load_per_core']}×核数")
        return "，".join(parts) or "无限制"


@register_guard("time_window")
class TimeWindowGuard:
    """在指定时间窗内拒绝执行，用于避开 EVE 维护期等已知不稳定时段。"""

    def __init__(self, spec, cfg):
        self.windows = (spec or {}).get("windows") or []

    def check(self, ctx):
        hit = in_window(self.windows, time.time())
        if hit:
            return False, f"处于维护窗口 {hit[0]}-{hit[1]}"
        return True, ""

    def describe(self):
        if not self.windows:
            return "无窗口"
        return "跳过 " + "/".join(f"{a}-{b}" for a, b in self.windows)


@register_guard("always")
class AlwaysGuard:
    """永不拦截。用于临时关闭一组闸门时保持配置结构不变。"""

    def __init__(self, spec, cfg):
        self.spec = spec or {}

    def check(self, ctx):
        return True, ""

    def describe(self):
        return "放行"

    def plugin_name(self):  # pragma: no cover - 仅描述用
        return "always"


@register_guard("daily_success")
class DailySuccessGuard:
    """当天自 since 时刻起已经成功跑过一次，后续触发直接跳过。

    用于「窗口内多次触发、成功即停」的保底调度：EVE 维护时长不确定（例行 15
    分钟，大型更新 1–2 小时），与其在任务内死等，不如让 cron 在 19–22 点每小时
    触发一次，第一次真正成功后剩下的触发点全部跳过。

    只看上一次的结论（last_exit_code / last_end），不写入状态，因此不会与控制器
    自己的状态更新冲突：

        "guards": [{"type": "daily_success", "since": "19:00"}]

    用 since 而不是「是否同一天」，是为了跨零点的任务不被误判：若任务 23:50
    开始、00:20 结束，次日 19:10 检查时 last_end 已属于「今天」，但早于今天的
    since，因此不会被当成今天已完成。
    """

    def __init__(self, spec, cfg):
        self.since = str((spec or {}).get("since") or "00:00")

    def check(self, ctx):
        item = ctx.state.task(ctx.task.name)
        if item.get("last_exit_code") != 0:
            return True, ""
        last_end = item.get("last_end")
        if not last_end:
            return True, ""
        try:
            hh, mm = parse_hhmm(self.since)
        except (ValueError, AttributeError):
            return True, ""

        now = datetime.now()
        boundary = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if float(last_end) >= boundary.timestamp():
            finished = datetime.fromtimestamp(float(last_end)).strftime("%H:%M")
            return False, f"今日 {self.since} 后已成功完成（{finished}）"
        return True, ""

    def describe(self):
        return f"今日 {self.since} 起已成功则跳过"
