"""调度插件：决定任务何时运行。

内置 interval / daily / weekly / monthly / cron 五种。
新增调度方式的模板：

    @register_schedule("lunar")
    class LunarSchedule(BaseSchedule):
        def __init__(self, spec, cfg=None):
            self.spec = spec
        def next_run(self, after_ts):
            ...
        def describe(self):
            return "每个农历初一"
"""
from datetime import datetime, time as dtime, timedelta

from core.registry import get, register_schedule


def parse_hhmm(text):
    hh, mm = text.split(":")
    return int(hh), int(mm)


class BaseSchedule:
    """调度插件基类，仅用于标注接口。"""

    def __init__(self, spec, cfg=None):
        self.spec = spec or {}
        self.cfg = cfg or {}

    def next_run(self, after_ts):
        raise NotImplementedError

    def describe(self):
        raise NotImplementedError


@register_schedule("interval")
class IntervalSchedule(BaseSchedule):
    """固定间隔。align=True 时对齐到间隔的整数倍边界。

    对齐的意义：采集器自身若用 sleep(1800)，每轮多出的 35 秒会累积，
    一天下来偏移约 28 分钟。控制器按边界触发则不会漂移。
    """

    def __init__(self, spec, cfg=None):
        super().__init__(spec, cfg)
        self.step = int(float(self.spec["minutes"]) * 60)
        if self.step <= 0:
            raise ValueError("interval.minutes 必须为正数")
        self.align = bool(self.spec.get("align", True))

    def next_run(self, after_ts):
        if not self.align:
            return int(after_ts) + self.step
        return (int(after_ts) // self.step + 1) * self.step

    def describe(self):
        unit = f"{self.spec['minutes']} 分钟"
        return f"每 {unit}" + ("（对齐边界）" if self.align else "")


@register_schedule("daily")
class DailySchedule(BaseSchedule):
    """每日固定时刻，如 {"type": "daily", "at": "08:00"}。"""

    def __init__(self, spec, cfg=None):
        super().__init__(spec, cfg)
        self.hh, self.mm = parse_hhmm(self.spec["at"])

    def next_run(self, after_ts):
        target = datetime.fromtimestamp(after_ts).replace(
            hour=self.hh, minute=self.mm, second=0, microsecond=0)
        if target.timestamp() <= after_ts:
            target += timedelta(days=1)
        return int(target.timestamp())

    def describe(self):
        return f"每日 {self.spec['at']}"


@register_schedule("weekly")
class WeeklySchedule(BaseSchedule):
    """每周固定星期与时刻，weekday 0=周一、6=周日。"""

    WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    def __init__(self, spec, cfg=None):
        super().__init__(spec, cfg)
        self.hh, self.mm = parse_hhmm(self.spec["at"])
        self.weekday = int(self.spec["weekday"]) % 7  # 0=周一

    def next_run(self, after_ts):
        base = datetime.fromtimestamp(after_ts)
        target = base.replace(hour=self.hh, minute=self.mm, second=0, microsecond=0)
        target += timedelta(days=(self.weekday - base.weekday()) % 7)
        if target.timestamp() <= after_ts:
            target += timedelta(days=7)
        return int(target.timestamp())

    def describe(self):
        return f"每{self.WEEKDAYS[self.weekday]} {self.spec['at']}"


@register_schedule("monthly")
class MonthlySchedule(BaseSchedule):
    """每月固定日号；该月不存在该日（如 2 月 31 日）时自动顺延到下个月。"""

    def __init__(self, spec, cfg=None):
        super().__init__(spec, cfg)
        self.hh, self.mm = parse_hhmm(self.spec["at"])
        self.day = int(self.spec["day"])

    def next_run(self, after_ts):
        base = datetime.fromtimestamp(after_ts)
        year, month = base.year, base.month
        for _ in range(13):
            try:
                target = base.replace(year=year, month=month, day=self.day,
                                      hour=self.hh, minute=self.mm, second=0, microsecond=0)
            except ValueError:
                target = None  # 该月没有这一天（如 2 月 31 日）
            if target is not None and target.timestamp() > after_ts:
                return int(target.timestamp())
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        raise ValueError("无法计算月度调度时间")

    def describe(self):
        return f"每月 {self.day} 日 {self.spec['at']}"


def _parse_field(text, low, high):
    """解析 cron 单字段：* / 5 / 1-5 / */10 / 1,3,5 / 9-17/2。"""
    values = set()
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(part)
        values.update(range(start, end + 1, step))
    return values


@register_schedule("cron")
class CronSchedule(BaseSchedule):
    """标准 5 字段 cron：分 时 日 月 周（0=周日，7 也视为周日）。

    实现按天/小时/分钟逐级跳过，避免逐分钟全量扫描。
    dom 与 dow 同时被指定时按 cron 惯例取「或」关系。
    """

    def __init__(self, spec, cfg=None):
        super().__init__(spec, cfg)
        expr = str(self.spec["expr"]).split()
        if len(expr) != 5:
            raise ValueError(f"cron 表达式需要 5 个字段：{self.spec['expr']}")
        minute, hour, dom, month, dow = expr
        self.minutes = _parse_field(minute, 0, 59)
        self.hours = _parse_field(hour, 0, 23)
        self.doms = _parse_field(dom, 1, 31)
        self.months = _parse_field(month, 1, 12)
        raw_dow = _parse_field(dow, 0, 7)
        self.dows = {0 if d == 7 else d for d in raw_dow}
        self.dom_any = dom.strip() == "*"
        self.dow_any = dow.strip() == "*"
        self.expr = self.spec["expr"]

    def _day_matches(self, day):
        dom_ok = day.day in self.doms
        dow_ok = (day.weekday() + 1) % 7 in self.dows  # Python 周一是 0，cron 周日是 0
        if self.dom_any and self.dow_any:
            return True
        if self.dom_any:
            return dow_ok
        if self.dow_any:
            return dom_ok
        return dom_ok or dow_ok

    def next_run(self, after_ts):
        current = datetime.fromtimestamp(after_ts).replace(second=0, microsecond=0)
        current += timedelta(minutes=1)
        limit = current + timedelta(days=366)
        while current < limit:
            if current.month not in self.months:
                current = (current.replace(day=1) + timedelta(days=32)).replace(
                    day=1, hour=0, minute=0)
                continue
            if not self._day_matches(current):
                current = (current + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if current.hour not in self.hours:
                current = (current + timedelta(hours=1)).replace(minute=0)
                continue
            if current.minute not in self.minutes:
                current += timedelta(minutes=1)
                continue
            return int(current.timestamp())
        raise ValueError(f"cron 在 366 天内没有匹配时间：{self.expr}")

    def describe(self):
        return f"cron [{self.expr}]"


def build_schedule(spec, cfg=None):
    """按 spec.type 构造调度对象。"""
    if not spec:
        raise ValueError("缺少 schedule 配置")
    kind = spec.get("type") or spec.get("name")
    if not kind:
        raise ValueError(f"schedule 缺少 type：{spec}")
    return get("schedule", kind)(spec, cfg)


def in_window(windows, ts):
    """判断 ts 是否落在任一 [start, end) 窗口内（本地时间，支持跨午夜）。

    兼容两种入参：
        in_window([["18:55", "19:45"]], ts)      # 新写法：窗口列表
        in_window({"skip_windows": [[...]]}, ts)  # 旧写法：spec 字典
    """
    if isinstance(windows, dict):
        windows = windows.get("skip_windows") or windows.get("windows") or []
    if not windows:
        return None
    now = datetime.fromtimestamp(ts).time()
    for item in windows:
        sh, sm = parse_hhmm(item[0])
        eh, em = parse_hhmm(item[1])
        start, end = dtime(sh, sm), dtime(eh, em)
        if start <= end:
            if start <= now < end:
                return item[0], item[1]
        elif now >= start or now < end:
            return item[0], item[1]
    return None
