"""任务状态持久化。

采用「临时文件 + os.replace」的原子写，避免进程被 kill 时留下半个 JSON。
重启后读取该文件恢复 next_run_ts 与连续失败计数，因此控制器重启不会
把已跑过的轮次重跑一遍，也不会忘记失败历史。
"""
import json
import os
import tempfile
import time

DEFAULT_TASK_STATE = {
    "last_start": None,
    "last_end": None,
    "last_exit_code": None,
    "last_duration": None,
    "peak_rss_mb": None,
    "consecutive_failures": 0,
    "total_runs": 0,
    "next_run_ts": None,
    "last_skip_reason": None,
    "last_message": None,
}


class State:
    def __init__(self, path):
        self.path = path
        self.data = {"version": 1, "tasks": {}, "updated_at": None}
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and isinstance(loaded.get("tasks"), dict):
                self.data = loaded
        except (OSError, ValueError):
            pass  # 首次运行或文件损坏：用空状态

    def task(self, name):
        """返回任务状态的 dict 引用（可直接读）。"""
        tasks = self.data.setdefault("tasks", {})
        item = tasks.setdefault(name, dict(DEFAULT_TASK_STATE))
        for key, value in DEFAULT_TASK_STATE.items():
            item.setdefault(key, value)  # 兼容旧版本字段缺失
        return item

    def update(self, name, **fields):
        item = self.task(name)
        item.update(fields)
        self.save()

    def save(self):
        self.data["updated_at"] = int(time.time())
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".state-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
