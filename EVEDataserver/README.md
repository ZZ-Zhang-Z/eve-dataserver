# EVEDataserver — 采集控制器

服务器端唯一常驻进程。统一调度所有采集任务，做资源闸门与状态记录。
只用 Python 标准库，无额外依赖。

## 目录结构

**本目录是自包含的**：任务实际用到的代码（采集器、`esi_client`、`database_manager`、
`paths`、月度聚合脚本）都有一份副本在内部，不依赖项目根目录的同名文件。数据与
`config.json` 仍位于项目根，位置不变。

```
EVEDataserver/
├── controller.py           主循环：算时间、查依赖、过闸门、调执行器
├── paths.py                路径常量（BASE_DIR 取上一级 → 数据仍在项目根）
├── database_manager.py     数据库连接管理（副本）
├── collectors/             采集器副本（runner 与 sde 任务实际引用这里）
│   ├── esi_client.py
│   ├── jita_market_orders_collector_async.py
│   ├── jita_market_history_collector_async.py
│   └── item_sde_collector.py
├── scripts/
│   └── aggregate_monthly_history.py   月度聚合（副本，sys.path 指向本目录）
├── core/
│   ├── registry.py         扩展点注册表（executor/schedule/guard/hook）
│   ├── context.py          TaskResult / TaskSpec / TaskContext
│   └── task.py             配置 → 任务对象装配，含旧格式兼容与依赖环检测
├── plugins/
│   ├── executors.py        subprocess、inline
│   ├── schedules.py        interval、daily、weekly、monthly、cron
│   ├── guards.py           resources、time_window、always
│   └── hooks.py            log、command、webhook
├── runners/
│   ├── orders_once.py      订单采集单轮
│   └── history_once.py     历史采集单轮
├── scheduler.py            旧 API 兼容层（新代码请用 plugins.schedules）
├── monitor.py              资源采样（内存/磁盘/负载/子进程 RSS）
├── state.py                任务状态原子持久化
├── config.json             调度与资源阈值
├── eve-controller.service  systemd 单元
├── logrotate-eve           子进程日志轮转
├── healthcheck.sh          健康检查
└── tests/
    ├── test_units.py       调度/闸门/状态 7 组
    └── test_plugins.py     扩展性 8 组
```

### 副本与项目根的关系

`collectors/`、`database_manager.py` 是项目根同名文件的副本，两者行为一致
（`paths.py` 是唯一例外：它的 `BASE_DIR` 指向 EVEDataserver 的上一级，保证
`data/`、`logs/`、`config.json` 仍解析到项目根）。

因此：

- **改采集器逻辑时，根目录和 `EVEDataserver/collectors/` 两处都要改**，
  否则服务器用的还是旧副本；
- 只想快速同步，可直接 `cp collectors/*.py EVEDataserver/collectors/`，
  但**不要覆盖 `EVEDataserver/paths.py`**（它的 BASE_DIR 与非副本不同）。

## 扩展模型

主循环只依赖四个抽象接口，任何「怎么做」都是可替换的插件：

| 扩展点 | 决定什么 | 内置实现 |
|---|---|---|
| executor | 任务怎么跑 | `subprocess`、`inline` |
| schedule | 何时跑 | `interval`、`daily`、`weekly`、`monthly`、`cron` |
| guard | 能不能跑 | `resources`、`time_window`、`always` |
| hook | 跑前后做什么 | `log`、`command`、`webhook` |

**新增能力的成本是固定的**：写一个类 → 加装饰器 → config 引用名字。`controller.py` 一行不用改。

### 示例：加一个「每 15 分钟探测 ESI 可用性」的任务

在 `plugins/executors.py` 末尾追加（或放到你自己的模块，见下文）：

```python
@register_executor("http_probe")
class HttpProbeExecutor:
    def __init__(self, spec, cfg):
        self.url = spec["url"]

    def run(self, ctx):
        import time, urllib.request
        start = time.time()
        try:
            with urllib.request.urlopen(self.url, timeout=10) as resp:
                return TaskResult(exit_code=0 if resp.status < 400 else 1,
                                  duration=time.time() - start)
        except Exception as exc:
            return TaskResult(exit_code=1, duration=time.time() - start, message=str(exc))
```

`config.json` 的 tasks 里加：

```json
"health_probe": {
  "executor": { "type": "http_probe", "url": "https://esi.evetech.net/status" },
  "schedule": { "type": "cron", "expr": "*/15 * * * *" },
  "hooks": [ { "type": "webhook", "url": "https://your-hook", "only_on": "failure" } ]
}
```

`kill -HUP <pid>` 热重载即可生效，不用重启进程。

### 不改本仓库：加载外部插件

把插件模块放到任意可导入位置，然后：

```json
"plugin_modules": ["mycompany.eve_plugins"]
```

`load_external()` 会在启动时 import 它们，注册随模块导入自动完成。

### 已支持但尚未用到的能力

- **依赖**：`"depends_on": ["history"]`，上游最近一次成功才执行（`monthly` 已启用）。
- **重试**：`"retry": {"max_attempts": 2, "delay_seconds": 120, "on_exit_codes": [2]}`。
- **收尾命令**：`{"type": "command", "command": ["/bin/bash","-c","..."], "only_on": "success"}`，可用于任务后备份、清理。
- **失败告警**：`{"type": "webhook", "url": "...", "only_on": "failure"}`。

## 调度表（config.json 当前值）

| 任务 | 触发 | 超时 | 说明 |
|---|---|---|---|
| orders | 每 30 分钟，对齐整点/半点 | 300s | 跳过 18:55–19:45（EVE 维护窗），失败重试 2 次 |
| history | 每日 08:00 | 7200s | 15216 个 type，约 40 分钟，独占令牌额度 |
| sde | 每周日 09:30 | 1800s | 95MB 下载，通常命中 ETag |
| monthly | 每月 1 日 04:30 | 3600s | 依赖 history 最近一次成功 |

**串行执行**：同一时刻只有一个任务。08:00 的历史采集不会与订单轮询抢令牌额度
（两者叠加需要 32104 令牌，而 40 分钟只有 32000 的补充量，正好卡在会触发 429 的边界）。

**时间对齐**：`interval` 用 `(now // step + 1) * step` 取下一次，而不是相对睡眠。
采集器自身 `sleep(1800)` 每轮多出的 35 秒一天会累积成 28 分钟漂移。

## 为什么采集器跑子进程

采集器大量使用模块级全局（`db_conn`、`error_count`、单例连接），同进程反复调用会互相污染；
更重要的是，418 页全量抓取的峰值约 284MB，**进程退出是最彻底的内存回收方式**。

## 命令行

```bash
python EVEDataserver/controller.py                 # 前台常驻（systemd 用这个）
python EVEDataserver/controller.py --status        # 任务状态表
python EVEDataserver/controller.py --dry-run       # 未来若干次调度 + 生效的闸门
python EVEDataserver/controller.py --list-plugins  # 已注册的扩展点及说明
python EVEDataserver/controller.py --once orders   # 立即手动跑一次（调试）
kill -HUP $(pgrep -f controller.py)                # 热重载 config.json
```

`--dry-run` 会顺带打印每个任务实际生效的闸门，用于确认 `skip_windows` 是否挂上：

```
orders      每 30 分钟（对齐边界）  内存≥180MB，磁盘≥2048MB，load≤2.0×核数 | 跳过 18:55-19:45
            11-26 11:30:00 | 11-26 12:00:00
monthly     每月 1 日 04:30  依赖 history | 内存≥180MB...
```

## 退出码约定

| 码 | 含义 | 控制器行为 |
|---|---|---|
| 0 | 成功 | 记录耗时与峰值 RSS |
| 2 | 快照不完整，保留旧数据 | 记失败，等下一轮 |
| 3 | 未取到订单 | 同上 |
| 4 | 写库被拒（规模骤降/重复） | 同上 |
| 5 | 历史错误超预算 | 同上 |
| -9 | 超时被终止 | 记失败 |
| -15 | 控制器停止时终止 | 记失败，不影响重启 |

`--once` 会把负值按 POSIX 惯例映射为 `128+n`（137/143），避免 shell 显示成 127。

## 部署

```bash
sudo cp ~/eve_helper/EVEDataserver/eve-controller.service /etc/systemd/system/
sudo cp ~/eve_helper/EVEDataserver/logrotate-eve /etc/logrotate.d/eve-helper
sudo systemctl daemon-reload
sudo systemctl enable --now eve-controller
journalctl -u eve-controller -f
```

> 不要与 `deploy/` 下的旧单元同时启用，否则同一份数据会被采集两次。

## 配置：两种写法

简洁写法（推荐日常使用，等价于 subprocess + 默认闸门 + log 钩子）：

```json
"orders": {
  "runner": "EVEDataserver/runners/orders_once.py",
  "schedule": { "type": "interval", "minutes": 30 },
  "skip_windows": [["18:55","19:45"]]
}
```

完整写法（需要换执行器、加钩子、单独调阈值时）：

```json
"orders": {
  "executor": { "type": "subprocess", "command": ["{python}", "-u", "路径.py"] },
  "schedule": { "type": "cron", "expr": "*/30 * * * *" },
  "guards": [ { "type": "resources", "min_free_mem_mb": 220 },
              { "type": "time_window", "windows": [["18:55","19:45"]] } ],
  "hooks": [ { "type": "log" },
             { "type": "webhook", "url": "...", "only_on": "failure" } ],
  "timeout_seconds": 300
}
```

未写 `guards` / `hooks` 时自动补 `resources` 与 `log`，所以简洁写法不会失去保护。

## 已知限制

1. **订单采集的内存取决于采集器实现**。`orders_once.py` 目前调用
   `get_all_market_orders()`，仍会聚合全量（峰值约 284MB）。采集器完成「逐页写
   staging」改造并暴露 `run_tracking_once()` 后，该封装会自动切换，控制器无需改动。
2. `state.json` 只保留最近一次运行结果。历史趋势看
   `logs/collectors/<task>.log` 中每轮的「峰值RSS」行。
3. 单实例锁基于 pidfile；异常断电后残留时删除 `EVEDataserver/.controller.lock`。
4. `inline` 执行器与控制器同进程，插件异常虽被捕获，但内存泄漏会累积，
   只建议用于毫秒级的维护逻辑，不要用来跑采集。
5. 控制器不负责数据备份，`data/*.db` 的离线拷贝请用 `command` 钩子或单独的定时任务。
