"""兼容层：保留旧函数式 API。

控制器已改为使用 plugins.schedules 里的调度对象，这里仅为旧脚本与既有测试
继续可用。新代码请直接：

    from plugins.schedules import build_schedule
    build_schedule({"type": "interval", "minutes": 30}).next_run(now)
"""
from plugins.schedules import build_schedule, in_window, parse_hhmm  # noqa: F401


def compute_next(spec, after_ts):
    return build_schedule(spec).next_run(after_ts)


def describe(spec):
    return build_schedule(spec).describe()
