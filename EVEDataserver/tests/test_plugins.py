"""扩展性测试：证明新增能力只需「一个类 + 一个装饰器 + config 引用」。

覆盖：
1. 注册表的错误提示与重复注册保护
2. 五种调度（含 cron 的工作日语义）
3. 旧格式（runner/script/skip_windows）与显式写法等价
4. 依赖环检测
5. 自定义执行器 / 自定义闸门 / 重试 —— 全部不改 controller.py

直接运行：
    python EVEDataserver/tests/test_plugins.py
"""
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, BASE)

import plugins  # noqa: E402

plugins.load_builtin()

import controller  # noqa: E402
from core import registry  # noqa: E402
from core.context import TaskResult  # noqa: E402
from core.registry import register_executor, register_guard  # noqa: E402
from core.task import build_task, load_tasks  # noqa: E402
from plugins.schedules import build_schedule  # noqa: E402
from state import State  # noqa: E402


def hm(epoch):
    import datetime
    return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def ts(text):
    import datetime
    return int(datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timestamp())


def test_registry_errors():
    try:
        registry.get("executor", "no-such-executor")
        raise AssertionError("应当抛出 LookupError")
    except LookupError as exc:
        assert "no-such-executor" in str(exc)
        assert "subprocess" in str(exc)  # 错误信息里要给出可用列表

    try:
        register_executor("subprocess")(type("Dup", (), {}))
        raise AssertionError("重复注册应当报错")
    except ValueError as exc:
        assert "重复" in str(exc)

    snap = registry.snapshot()
    assert "subprocess" in snap["executor"]
    assert "interval" in snap["schedule"]
    assert "resources" in snap["guard"]
    assert "log" in snap["hook"]


def test_cron():
    every_10 = build_schedule({"type": "cron", "expr": "*/10 * * * *"})
    assert hm(every_10.next_run(ts("2026-11-26 11:03:00"))) == "2026-11-26 11:10"
    assert hm(every_10.next_run(ts("2026-11-26 11:10:00"))) == "2026-11-26 11:20"

    daily_2 = build_schedule({"type": "cron", "expr": "0 2 * * *"})
    assert hm(daily_2.next_run(ts("2026-11-26 11:00:00"))) == "2026-11-27 02:00"

    # 工作日 9 点：11-26 是周四，次个应为 11-27 周五
    workday = build_schedule({"type": "cron", "expr": "0 9 * * 1-5"})
    assert hm(workday.next_run(ts("2026-11-26 12:00:00"))) == "2026-11-27 09:00"
    # 周五中午 -> 下周一
    assert hm(workday.next_run(ts("2026-11-27 12:00:00"))) == "2026-11-30 09:00"

    # 每月 1 日 0 点
    monthly = build_schedule({"type": "cron", "expr": "0 0 1 * *"})
    assert hm(monthly.next_run(ts("2026-11-26 11:00:00"))) == "2026-12-01 00:00"


def test_legacy_and_explicit_equivalent():
    cfg = {"_root": BASE, "resources": {}}
    schedule = {"type": "interval", "minutes": 30, "align": True}

    legacy = build_task("a", {
        "runner": "EVEDataserver/runners/orders_once.py",
        "schedule": schedule,
        "skip_windows": [["18:55", "19:45"]],
    }, cfg)
    explicit = build_task("b", {
        "executor": {"type": "subprocess",
                     "command": ["{python}", "-u", "EVEDataserver/runners/orders_once.py"]},
        "schedule": schedule,
        "guards": [{"type": "resources"},
                   {"type": "time_window", "windows": [["18:55", "19:45"]]}],
        "hooks": [{"type": "log"}],
    }, cfg)

    assert legacy.executor.plugin_name == "subprocess"
    assert [g.plugin_name for g in legacy.guards] == ["resources", "time_window"]
    assert [h.plugin_name for h in legacy.hooks] == ["log"]
    assert [g.plugin_name for g in explicit.guards] == ["resources", "time_window"]
    assert legacy.schedule.describe() == explicit.schedule.describe()


def test_dependency_cycle():
    schedule = {"type": "interval", "minutes": 30}
    cfg = {"_root": BASE, "resources": {}, "tasks": {
        "a": {"script": "x.py", "schedule": schedule, "depends_on": ["b"]},
        "b": {"script": "x.py", "schedule": schedule, "depends_on": ["a"]},
    }}
    try:
        load_tasks(cfg)
        raise AssertionError("成环应当报错")
    except ValueError as exc:
        assert "成环" in str(exc)

    cfg["tasks"]["b"]["depends_on"] = []
    cfg["tasks"]["a"]["depends_on"] = ["nope"]
    try:
        load_tasks(cfg)
        raise AssertionError("依赖不存在的任务应当报错")
    except ValueError as exc:
        assert "不存在" in str(exc)


@register_executor("counting_test")
class CountingExecutor:
    """测试用执行器：只计数，不真跑进程。"""
    calls = 0
    last_retention = None

    def __init__(self, spec, cfg):
        self.spec = spec or {}

    def run(self, ctx):
        CountingExecutor.calls += 1
        return TaskResult(exit_code=0, duration=0.01, peak_rss_mb=12.0)


@register_executor("flaky_test")
class FlakyExecutor:
    """前两次失败、第三次成功，用于验证 retry。"""

    def __init__(self, spec, cfg):
        self.fail_times = int((spec or {}).get("fail_times", 2))
        self.calls = 0

    def run(self, ctx):
        self.calls += 1
        code = 1 if self.calls <= self.fail_times else 0
        return TaskResult(exit_code=code, duration=0.01)


@register_guard("blocking_test")
class BlockingGuard:
    """测试用闸门：始终拦截并给出原因。"""

    def __init__(self, spec, cfg):
        self.reason = (spec or {}).get("reason", "测试拦截")

    def check(self, ctx):
        return False, self.reason

    def describe(self):
        return "始终拦截"


def _temp_state():
    path = os.path.join(tempfile.gettempdir(), "eve_plugin_test_state.json")
    try:
        os.remove(path)
    except OSError:
        pass
    return State(path)


def test_custom_executor_via_config():
    """自定义执行器通过 config 名字引用即可生效，controller 无需改动。"""
    CountingExecutor.calls = 0
    cfg = {"_root": BASE, "resources": {}}
    task = build_task("custom", {
        "executor": {"type": "counting_test"},
        "schedule": {"type": "interval", "minutes": 30},
    }, cfg)
    state = _temp_state()
    executed, reason = controller.run_task(task, cfg, state, threading.Event())
    assert executed is True, reason
    assert CountingExecutor.calls == 1
    assert state.task("custom")["last_exit_code"] == 0
    assert state.task("custom")["peak_rss_mb"] == 12.0


def test_guard_blocks_and_records_reason():
    cfg = {"_root": BASE, "resources": {}}
    task = build_task("blocked", {
        "executor": {"type": "counting_test"},
        "schedule": {"type": "interval", "minutes": 30},
        "guards": [{"type": "blocking_test", "reason": "内存不够"}],
    }, cfg)
    state = _temp_state()
    executed, reason = controller.run_task(task, cfg, state, threading.Event())
    assert executed is False
    assert "内存不够" in reason


def test_retry():
    cfg = {"_root": BASE, "resources": {}}
    task = build_task("retry", {
        "executor": {"type": "flaky_test", "fail_times": 2},
        "schedule": {"type": "interval", "minutes": 30},
        "retry": {"max_attempts": 3, "delay_seconds": 0},
    }, cfg)
    state = _temp_state()
    executed, _ = controller.run_task(task, cfg, state, threading.Event())
    assert executed is True
    assert state.task("retry")["last_exit_code"] == 0
    assert task.executor.calls == 3


def test_dependency_gate():
    cfg = {"_root": BASE, "resources": {}}
    schedule = {"type": "interval", "minutes": 30}
    upstream = build_task("up", {"executor": {"type": "counting_test"}, "schedule": schedule}, cfg)
    downstream = build_task("down", {"executor": {"type": "counting_test"},
                                     "schedule": schedule, "depends_on": ["up"]}, cfg)
    state = _temp_state()

    executed, reason = controller.run_task(downstream, cfg, state, threading.Event())
    assert executed is False and "依赖未完成" in reason

    controller.run_task(upstream, cfg, state, threading.Event())
    executed, reason = controller.run_task(downstream, cfg, state, threading.Event())
    assert executed is True, reason


def main():
    tests = [test_registry_errors, test_cron, test_legacy_and_explicit_equivalent,
             test_dependency_cycle, test_custom_executor_via_config,
             test_guard_blocks_and_records_reason, test_retry, test_dependency_gate]
    for fn in tests:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(tests)} 组扩展性测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
