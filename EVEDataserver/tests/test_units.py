"""控制器单元测试：调度计算、维护窗口、资源闸门、状态持久化。

不依赖 pytest，直接运行即可：
    python EVEDataserver/tests/test_units.py
"""
import os
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import monitor  # noqa: E402
import scheduler  # noqa: E402
from state import State  # noqa: E402


def ts(text):
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timestamp())


def hm(epoch):
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def test_interval():
    aligned = {"type": "interval", "minutes": 30, "align": True}
    assert hm(scheduler.compute_next(aligned, ts("2026-11-26 11:07:00"))) == "2026-11-26 11:30"
    # 正好落在边界时，必须严格向后取下一个
    assert hm(scheduler.compute_next(aligned, ts("2026-11-26 11:30:00"))) == "2026-11-26 12:00"
    # 不对齐则单纯累加
    loose = {"type": "interval", "minutes": 30, "align": False}
    assert hm(scheduler.compute_next(loose, ts("2026-11-26 11:07:00"))) == "2026-11-26 11:37"
    # 跨天对齐
    assert hm(scheduler.compute_next(aligned, ts("2026-11-26 23:50:00"))) == "2026-11-27 00:00"


def test_daily():
    spec = {"type": "daily", "at": "08:00"}
    assert hm(scheduler.compute_next(spec, ts("2026-11-26 07:00:00"))) == "2026-11-26 08:00"
    assert hm(scheduler.compute_next(spec, ts("2026-11-26 08:00:00"))) == "2026-11-27 08:00"
    assert hm(scheduler.compute_next(spec, ts("2026-11-26 23:59:00"))) == "2026-11-27 08:00"


def test_weekly():
    spec = {"type": "weekly", "weekday": 6, "at": "09:30"}
    # 2026-11-26 是周四，next 应为 11-29 周日
    assert hm(scheduler.compute_next(spec, ts("2026-11-26 12:00:00"))) == "2026-11-29 09:30"
    # 周日当天已过时间，跳到下周日
    assert hm(scheduler.compute_next(spec, ts("2026-11-29 12:00:00"))) == "2026-12-06 09:30"
    # 周日当天未到时间
    assert hm(scheduler.compute_next(spec, ts("2026-11-29 08:00:00"))) == "2026-11-29 09:30"


def test_monthly():
    spec = {"type": "monthly", "day": 1, "at": "04:30"}
    assert hm(scheduler.compute_next(spec, ts("2026-12-15 00:00:00"))) == "2027-01-01 04:30"
    # 31 号在 2 月不存在，应跳到 3 月 31 日
    spec31 = {"type": "monthly", "day": 31, "at": "04:30"}
    assert hm(scheduler.compute_next(spec31, ts("2026-01-31 05:00:00"))) == "2026-03-31 04:30"
    assert hm(scheduler.compute_next(spec31, ts("2026-03-01 00:00:00"))) == "2026-03-31 04:30"


def test_skip_window():
    normal = {"skip_windows": [["18:55", "19:45"]]}
    assert scheduler.in_window(normal, ts("2026-11-26 19:10:00")) == ("18:55", "19:45")
    assert scheduler.in_window(normal, ts("2026-11-26 18:54:00")) is None
    assert scheduler.in_window(normal, ts("2026-11-26 19:50:00")) is None

    midnight = {"skip_windows": [["23:50", "00:20"]]}
    assert scheduler.in_window(midnight, ts("2026-11-26 23:55:00")) is not None
    assert scheduler.in_window(midnight, ts("2026-11-27 00:10:00")) is not None
    assert scheduler.in_window(midnight, ts("2026-11-27 00:30:00")) is None

    assert scheduler.in_window({}, ts("2026-11-26 12:00:00")) is None


def test_resource_gate():
    limits = {"min_free_mem_mb": 180, "min_free_disk_mb": 2048, "max_load_per_core": 2.0}
    healthy = {"mem_available_mb": 300, "disk_free_mb": 5000, "load1": 0.4, "cpu_count": 2}
    assert monitor.check(healthy, limits)[0] is True

    low_mem = dict(healthy, mem_available_mb=100)
    ok, reason = monitor.check(low_mem, limits)
    assert ok is False and "内存" in reason

    low_disk = dict(healthy, disk_free_mb=512)
    ok, reason = monitor.check(low_disk, limits)
    assert ok is False and "磁盘" in reason

    high_load = dict(healthy, load1=5.0)  # 5.0 > 2.0 × 2 核
    ok, reason = monitor.check(high_load, limits)
    assert ok is False and "load1" in reason

    # 缺失指标（非 Linux）一律放行
    assert monitor.check({"disk_free_mb": None}, limits)[0] is True


def test_state_roundtrip():
    path = os.path.join(tempfile.gettempdir(), "eve_controller_state_test.json")
    for suffix in ("", ".tmp"):
        try:
            os.remove(path + suffix)
        except OSError:
            pass

    first = State(path)
    first.update("orders", next_run_ts=1795661450, total_runs=3)
    assert os.path.exists(path)

    second = State(path)
    item = second.task("orders")
    assert item["next_run_ts"] == 1795661450
    assert item["total_runs"] == 3
    # 新任务自动补全默认字段
    assert second.task("history")["consecutive_failures"] == 0
    os.remove(path)


def main():
    tests = [test_interval, test_daily, test_weekly, test_monthly,
             test_skip_window, test_resource_gate, test_state_roundtrip]
    for fn in tests:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(tests)} 组单元测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
