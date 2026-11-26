"""闸门插件：任务启动前的准入检查。

任一闸门不通过，本轮就跳过并记录原因，等下一轮再试。
新增闸门的模板：

    @register_guard("token_balance")
    class TokenGuard:
        def __init__(self, spec, cfg): ...
        def check(self, ctx) -> (bool, str): ...
"""
import time

import monitor
from core.registry import register_guard
from plugins.schedules import in_window


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
