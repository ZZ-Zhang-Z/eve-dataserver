# eve-dataserver

EVE Online 市场数据长期采集服务。一个常驻控制器统一调度订单快照、成交历史、
SDE 静态数据与月度聚合，做资源闸门、失败重试与状态记录；数据落在本地 SQLite，
供分析端消费。

面向小内存服务器设计（实测峰值 70–120MB，1 核 1GB 也能跑）。

## 特性

- **插件化调度**：执行方式、调度方式、准入闸门、生命周期钩子都是注册表里的扩展点，
  新增能力只写一个类，主循环不改。
- **串行执行**：同一时刻只跑一个任务，天然避免多个采集器同时抢 ESI 令牌额度。
- **时间对齐**：`interval` 按 `(now // step + 1) * step` 计算下次触发，不是相对睡眠，
  长期运行不会累积漂移。
- **快照完整性保护**：订单采集有五道闸（页级完整、数量下限、去重、规模兜底、连续失败中止），
  任何一道不过都只会「少采一轮」，不会写出残缺数据或伪造的变更事件。
- **错误限流保护**：连续 20 页失败立即中止本轮，避免把 ESI 的 `100 errors/60s` 打满。
- **热重载**：`kill -HUP` 重读配置，运行中的任务不受影响。

## 快速开始

```bash
git clone git@github.com:ZZ-Zhang-Z/eve-dataserver.git
cd eve-dataserver

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 采集器运行时配置（项目根必须有 config.json，否则走代码兜底值）
cp config.collector.example.json config.json
# 编辑：把 user_agent 改成自己的邮箱；需要 churn 数据就把 tracker.enabled 设为 true

.venv/bin/python controller.py --dry-run    # 先看调度计划，不启动
.venv/bin/python controller.py              # 前台常驻
```

首次运行会自动创建 `data/`、`logs/`、`logs/collectors/`，不需要手工建目录。

## 目录结构

```
.
├── controller.py           主循环：算时间、查依赖、过闸门、调执行器
├── controller.json         调度表与资源阈值（控制器用）
├── config.json             采集器运行时配置（由 example 生成，不入库）
├── config.collector.example.json
├── paths.py                路径常量；BASE_DIR 可用 EVE_BASE_DIR 覆盖
├── database_manager.py     SQLite 连接管理（WAL + 线程本地连接）
├── collectors/             ESI 采集器
│   ├── esi_client.py       限流/退避/ETag 缓存/分页一致性校验
│   ├── jita_market_orders_collector_async.py     订单快照与变更事件
│   ├── jita_market_history_collector_async.py    成交历史
│   └── item_sde_collector.py                     SDE 静态数据导入
├── scripts/
│   └── aggregate_monthly_history.py   历史月度聚合与压缩
├── runners/                单轮封装（子进程入口，带退出码语义）
├── core/                   注册表、任务装配、上下文
├── plugins/                内置 executor / schedule / guard / hook
├── tests/                  控制器单元与扩展性测试
├── eve-controller.service  systemd 单元
├── logrotate-eve           子进程日志轮转
└── healthcheck.sh          健康检查
```

## 调度表（`controller.json`）

| 任务 | 触发 | 超时 | 说明 |
|---|---|---|---|
| orders | 每 30 分钟，对齐整点/半点 | 300s | 跳过 18:55–19:45（EVE 维护窗），失败重试 2 次 |
| history | 每日 08:00 | 7200s | 15216 个 type，约 40 分钟，独占令牌额度 |
| sde | 每周日 09:30 | 1800s | 95MB 下载，通常命中 ETag |
| monthly | 每月 1 日 04:30 | 3600s | 依赖 history 最近一次成功 |

**为什么串行**：08:00 的历史采集需要 30432 令牌（15216×2），订单轮询一轮 836；
两者叠加 32104，而 40 分钟只能补充约 32000，正好卡在会触发 429 的边界。串行之后
这个问题不存在，代价是历史采集期间订单少跑 1–2 轮。

## 命令行

```bash
python controller.py                 # 前台常驻（systemd 用这个）
python controller.py --status        # 任务状态表
python controller.py --dry-run       # 未来若干次调度 + 实际生效的闸门
python controller.py --list-plugins  # 已注册的扩展点及说明
python controller.py --once orders   # 立即手动跑一次（调试）
kill -HUP $(pgrep -f controller.py)  # 热重载 controller.json
```

`--dry-run` 会顺带打印每个任务实际生效的闸门，用于确认 `skip_windows` 是否挂上：

```
orders      每 30 分钟（对齐边界）  内存≥180MB，磁盘≥2048MB，load≤2.0×核数 | 跳过 18:55-19:45
            11-26 12:00:00
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

`controller.json` 的 tasks 里加：

```json
"health_probe": {
  "executor": { "type": "http_probe", "url": "https://esi.evetech.net/status" },
  "schedule": { "type": "cron", "expr": "*/15 * * * *" },
  "hooks": [ { "type": "webhook", "url": "https://your-hook", "only_on": "failure" } ]
}
```

热重载即可生效，不用重启进程。

### 不改本仓库：加载外部插件

把插件模块放到任意可导入位置，然后：

```json
"plugin_modules": ["mycompany.eve_plugins"]
```

`load_external()` 会在启动时 import 它们，注册随模块导入自动完成。

### 已支持但尚未用到的能力

- **依赖**：`"depends_on": ["history"]`，上游最近一次成功才执行（`monthly` 已启用）。
- **重试**：`"retry": {"max_attempts": 2, "delay_seconds": 120, "on_exit_codes": [2]}`。
- **收尾命令**：`{"type": "command", "command": ["/bin/bash","-c","..."], "only_on": "success"}`。
- **失败告警**：`{"type": "webhook", "url": "...", "only_on": "failure"}`。

旧格式（`"runner"`、`"script"`、`"skip_windows"`）仍然可用，会自动映射为
`subprocess` 执行器 + `resources`/`time_window` 闸门 + `log` 钩子。

## 两个配置文件不要混

| 文件 | 谁读 | 内容 |
|---|---|---|
| `controller.json` | 控制器 | 任务调度、资源阈值、日志与状态路径 |
| `config.json` | 采集器（`esi_client` 等） | ESI 版本头、`user_agent`、`market_orders_tracker` 开关 |

采集器按 `paths.BASE_DIR/config.json` 读取，所以 `config.json` 必须放在项目根，
且**不要**把它改名或塞进子目录。

## 数据位置

默认都在项目内（`data/`、`logs/`）。如果希望把数据放到别处——例如与主项目的
分析脚本共用同一份数据库——用环境变量覆盖：

```bash
EVE_BASE_DIR=/home/admin/eve_helper python controller.py
```

`paths.BASE_DIR` 会随之改变，`data/`、`logs/`、`config.json` 都在该目录下查找。

## 部署

```bash
# 1) 代码与依赖
git clone git@github.com:ZZ-Zhang-Z/eve-dataserver.git ~/eve_helper
cd ~/eve_helper
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.collector.example.json config.json   # 编辑 user_agent 等

# 2) 安装常驻服务（注意按实际路径改 User/WorkingDirectory/ExecStart）
sudo cp eve-controller.service /etc/systemd/system/
sudo cp logrotate-eve /etc/logrotate.d/eve-helper
sudo systemctl daemon-reload
sudo systemctl enable --now eve-controller
journalctl -u eve-controller -f

# 3) 健康检查（建议 cron 每 10 分钟）
bash healthcheck.sh
```

`eve-controller.service` 里的 `MemoryHigh=350M / MemoryMax=500M` 是 cgroup 护栏：
万一出现未预料的分配，让子进程自己被杀并由控制器记下退出码，而不是拖死整机。

## 更新代码

```bash
cd ~/eve_helper && git pull
sudo systemctl restart eve-controller   # 仅控制器/插件代码变动时需要
```

## 与其他项目的关系

本仓库是服务器端的独立发行版。开发主项目（含 Web 前端与分析脚本）时，`collectors/`
下的采集器会同步到这里；同步时注意 `paths.py` 不随采集器一起覆盖——它的
`BASE_DIR` 语义针对本项目（自身目录）而定。

## 已知限制

- 订单采集的「逐页落盘」改造尚未做：418 页仍会聚合进内存，峰值约 284MB。
  systemd 单元的 `MemoryMax=500M` 是为它留的余量，改造后可降到 300M。
- `cron` 调度只支持 5 字段的常见写法（`*/n`、`a-b`、`a-b/n`、逗号列表），
  不支持 `L`、`W`、`#`。
- `group` 字段预留但未启用：当前严格串行，若将来需要并行，按 group 做资源互斥即可。
