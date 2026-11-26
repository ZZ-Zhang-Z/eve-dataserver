"""施工层：把 config.json 的原始配置装配成 TaskSpec。

这一层是「配置格式」与「插件实现」之间的唯一耦合点。新增插件类型时，
这里不需要改动 —— 它是按名字查注册表的。

兼容旧格式（控制器最初版本）：
    "runner": "path.py"        -> subprocess 执行器
    "script": "path.py"        -> subprocess 执行器
    "skip_windows": [[..]]     -> time_window 闸门
未写 guards / hooks 时，默认给 resources 闸门和 log 钩子，保证行为一致。
"""
from core.context import TaskSpec, coerce_str_dict, normalize_plugin_ref, parse_bool
from core.registry import get
from plugins.schedules import build_schedule


def _build_executor(raw, cfg):
    spec = raw.get("executor")
    if spec:
        kind, opts = normalize_plugin_ref(spec)
        return get("executor", kind)(opts, cfg)

    legacy = raw.get("runner") or raw.get("script")
    if legacy:
        return get("executor", "subprocess")({"runner": legacy}, cfg)

    raise ValueError("任务缺少 executor 字段（或旧格式的 runner / script）")


def _build_guards(raw, cfg):
    refs = raw.get("guards")
    if refs is None:
        guards = [get("guard", "resources")({}, cfg)]
        legacy_windows = raw.get("skip_windows")
        if legacy_windows:
            guards.append(get("guard", "time_window")({"windows": legacy_windows}, cfg))
        return guards

    guards = []
    for item in refs:
        kind, opts = normalize_plugin_ref(item)
        guards.append(get("guard", kind)(opts, cfg))
    return guards


def _build_hooks(raw, cfg):
    refs = raw.get("hooks")
    if refs is None:
        return [get("hook", "log")({}, cfg)]

    hooks = []
    for item in refs:
        kind, opts = normalize_plugin_ref(item)
        hooks.append(get("hook", kind)(opts, cfg))
    return hooks


def build_task(name, raw, cfg):
    if not isinstance(raw, dict):
        raise ValueError(f"任务 {name} 的配置必须是对象")

    schedule_spec = raw.get("schedule")
    if not schedule_spec:
        raise ValueError(f"任务 {name} 缺少 schedule")

    return TaskSpec(
        name=name,
        enabled=parse_bool(raw.get("enabled"), True),
        description=raw.get("desc", ""),
        executor=_build_executor(raw, cfg),
        schedule=build_schedule(schedule_spec, cfg),
        guards=_build_guards(raw, cfg),
        hooks=_build_hooks(raw, cfg),
        timeout_seconds=int(raw.get("timeout_seconds", 600)),
        retry=dict(raw.get("retry") or {}),
        depends_on=list(raw.get("depends_on") or []),
        group=raw.get("group") or "",
        env=coerce_str_dict(raw.get("env")),
        raw=raw,
    )


def _check_cycles(tasks):
    """依赖环检测：成环时扫描会无限递归，必须在启动阶段拦下。"""
    visiting, done = set(), set()

    def visit(name, path):
        if name in done:
            return
        if name in visiting:
            raise ValueError("任务依赖成环：" + " -> ".join(path + [name]))
        visiting.add(name)
        for dep in tasks[name].depends_on:
            visit(dep, path + [name])
        visiting.discard(name)
        done.add(name)

    for name in tasks:
        visit(name, [])


def load_tasks(cfg):
    """把 config['tasks'] 全部装配成 TaskSpec，并校验依赖关系。"""
    raw_tasks = cfg.get("tasks") or {}
    tasks = {name: build_task(name, raw, cfg) for name, raw in raw_tasks.items()}

    for task in tasks.values():
        for dep in task.depends_on:
            if dep not in tasks:
                raise ValueError(f"任务 {task.name} 依赖了不存在的任务 {dep}")
            if dep == task.name:
                raise ValueError(f"任务 {task.name} 不能依赖自己")

    _check_cycles(tasks)
    return tasks
