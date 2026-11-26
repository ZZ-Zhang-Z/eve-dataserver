"""资源采样与闸门。

只用标准库。Linux 下读 /proc 与 statvfs；其它平台缺失的指标返回 None，
闸门对 None 一律放行（便于在开发机上跑 --dry-run / --status）。
"""
import os
import shutil
import time


def _meminfo_mb():
    """返回 {字段: MB}，非 Linux 返回 None。"""
    path = "/proc/meminfo"
    if not os.path.exists(path):
        return None
    out = {}
    try:
        with open(path, encoding="ascii", errors="ignore") as f:
            for line in f:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts and parts[0].isdigit():
                    out[key.strip()] = int(parts[0]) // 1024
    except OSError:
        return None
    return out or None


def sample(root):
    """采集一次资源快照。"""
    data = {"ts": int(time.time())}

    mem = _meminfo_mb()
    if mem:
        data["mem_total_mb"] = mem.get("MemTotal")
        data["mem_available_mb"] = mem.get("MemAvailable")

    try:
        usage = shutil.disk_usage(root)
        data["disk_total_mb"] = usage.total // 1048576
        data["disk_free_mb"] = usage.free // 1048576
    except OSError:
        data["disk_free_mb"] = None

    try:
        data["load1"] = round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        # 部分平台（或精简构建）没有 getloadavg，闸门对 None 放行
        data["load1"] = None

    data["cpu_count"] = os.cpu_count() or 1
    return data


def check(data, limits):
    """判断资源是否允许启动新任务，返回 (ok, reason)。"""
    limits = limits or {}

    floor_mem = limits.get("min_free_mem_mb")
    avail_mem = data.get("mem_available_mb")
    if floor_mem is not None and avail_mem is not None and avail_mem < floor_mem:
        return False, f"可用内存 {avail_mem}MB < 阈值 {floor_mem}MB"

    floor_disk = limits.get("min_free_disk_mb")
    free_disk = data.get("disk_free_mb")
    if floor_disk is not None and free_disk is not None and free_disk < floor_disk:
        return False, f"可用磁盘 {free_disk}MB < 阈值 {floor_disk}MB"

    per_core = limits.get("max_load_per_core")
    load1 = data.get("load1")
    if per_core is not None and load1 is not None:
        cap = float(per_core) * int(data.get("cpu_count") or 1)
        if load1 > cap:
            return False, f"load1 {load1} > {cap:.1f}"

    return True, ""


def read_rss_mb(pid):
    """读取进程 RSS（MB）。进程已退出或非 Linux 返回 None。"""
    path = f"/proc/{pid}/status"
    try:
        with open(path, encoding="ascii", errors="ignore") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        return None
    return None
