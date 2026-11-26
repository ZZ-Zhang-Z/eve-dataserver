"""扩展点注册表。

控制器只认四类扩展点，每类都是「名字 -> 类」的映射：

- executor  如何执行一个任务（子进程 / 内联函数 / HTTP / 容器 ...）
- schedule  何时执行（interval / daily / weekly / monthly / cron ...）
- guard     执行前的准入检查（资源 / 时间窗 / 外部锁 / 令牌余额 ...）
- hook      生命周期回调（before / after / success / failure）

新增能力的方式固定为三步，**不需要修改 controller.py**：

    1. 在 plugins/ 下写一个类；
    2. 用 @register_xxx("名字") 装饰；
    3. config.json 里引用这个名字。

接口契约（鸭子类型，不强制继承，但建议继承 core.task 里的基类以便 IDE 提示）：

    Executor:  __init__(spec, cfg)         run(ctx) -> TaskResult
    Schedule:  __init__(spec, cfg=None)    next_run(after_ts) -> int
                                           describe() -> str
    Guard:     __init__(spec, cfg)         check(ctx) -> (ok: bool, reason: str)
    Hook:      __init__(spec, cfg)         on_before(ctx) / on_after(ctx, result)
                                           （只实现关心的阶段即可）
"""
from typing import Any, Dict, List

_REGISTRY: Dict[str, Dict[str, Any]] = {
    "executor": {},
    "schedule": {},
    "guard": {},
    "hook": {},
}

KINDS = tuple(_REGISTRY)


def register(kind: str, name: str):
    """把类注册到指定扩展点。重复注册立即报错，避免静默覆盖。"""
    if kind not in _REGISTRY:
        raise ValueError(f"未知扩展点类型 {kind}，可选 {list(_REGISTRY)}")

    def decorator(cls):
        bucket = _REGISTRY[kind]
        if name in bucket and bucket[name] is not cls:
            raise ValueError(f"{kind} 名称重复：{name}（已被 {bucket[name].__module__} 占用）")
        bucket[name] = cls
        cls.plugin_kind = kind
        cls.plugin_name = name
        return cls

    return decorator


def register_executor(name):
    return register("executor", name)


def register_schedule(name):
    return register("schedule", name)


def register_guard(name):
    return register("guard", name)


def register_hook(name):
    return register("hook", name)


def get(kind: str, name: str):
    """取已注册的类；不存在时抛出带「可用列表」的错误，便于排查拼写。"""
    bucket = _REGISTRY.get(kind)
    if bucket is None:
        raise LookupError(f"未知扩展点类型 {kind}")
    if name not in bucket:
        avail = ", ".join(sorted(bucket)) or "(空)"
        raise LookupError(f"未注册的 {kind}：{name}；可用：{avail}")
    return bucket[name]


def available(kind: str) -> List[str]:
    return sorted(_REGISTRY.get(kind, {}))


def snapshot() -> Dict[str, List[str]]:
    """所有扩展点的当前快照，供 --list-plugins 与启动日志使用。"""
    return {kind: sorted(bucket) for kind, bucket in _REGISTRY.items()}
