"""执行上下文与结果对象。

ctx 是插件能拿到的全部运行时信息：任务定义、运行 id、状态存储、项目根、
停止信号、日志器。插件不应直接访问控制器的全局状态，一切通过 ctx。
"""
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskResult:
    """一次执行的结论。exit_code 沿用进程语义，0 表示成功。"""
    exit_code: int = 0
    duration: float = 0.0
    peak_rss_mb: float = 0.0
    message: str = ""
    artifacts: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass
class TaskSpec:
    """config.json 里一个任务的解析结果（由 core.task 构造）。"""
    name: str
    enabled: bool = True
    description: str = ""
    executor: Any = None
    schedule: Any = None
    guards: List[Any] = field(default_factory=list)
    hooks: List[Any] = field(default_factory=list)
    timeout_seconds: int = 600
    retry: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    group: str = ""
    env: Dict[str, str] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskContext:
    """传给 executor / guard / hook 的运行时上下文。"""
    task: TaskSpec
    run_id: str
    root: str
    state: Any
    stop_event: threading.Event
    logger: logging.Logger
    started_at: float = field(default_factory=time.time)
    scratch: Dict[str, Any] = field(default_factory=dict)  # 同一次运行内 hook 之间传递数据

    @staticmethod
    def new(task, root, state, stop_event, logger) -> "TaskContext":
        run_id = f"{task.name}-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        return TaskContext(task=task, run_id=run_id, root=root, state=state,
                           stop_event=stop_event, logger=logger)

    def log(self, msg, *args, level=logging.INFO):
        self.logger.log(level, "[%s] " + str(msg), self.task.name, *args)


def coerce_str_dict(value) -> Dict[str, str]:
    """把 config 里的 env 字段统一成 str->str。"""
    if not value:
        return {}
    return {str(k): str(v) for k, v in dict(value).items()}


def parse_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def normalize_plugin_ref(item, default_type: Optional[str] = None):
    """把插件引用统一成 (type, spec)。

    支持两种写法：
        "resources"                            -> ("resources", {})
        {"type": "resources", "min_free_mb": 200}  -> ("resources", {"min_free_mb": 200})
    """
    if isinstance(item, str):
        return item, {}
    if isinstance(item, dict):
        spec = dict(item)
        name = spec.pop("type", None) or spec.pop("name", None) or default_type
        if not name:
            raise ValueError(f"插件配置缺少 type 字段：{item}")
        return name, spec
    raise ValueError(f"无法解析插件配置：{item!r}")
