# EVE Helper

本地 EVE Online 在线市场套利分析工具：从 ESI 与官方 SDE 采集市场 / 宇宙 / 物品数据，落地 SQLite，并提供 Web 界面做套利机会、钱包收支与数据采集管理。

---

## 功能概览

| 页面 | 路径 | 说明 |
|---|---|---|
| 首页工作台 | `/` | 运行状态、数据时效总览、市场分组/订单浏览 |
| 套利分析 | `/analysis` | 读取分析产物，展示跨站买卖价差与利润率 |
| 钱包收支 | `/wallet` | 导入钱包交易流水，统计收支与走势 |
| 采集控制台 | `/collectors` | 一键启动 / 停止各采集与维护任务，查看进度、日志与数据时效 |
| 登录 | `/login` → `/callback` | EVE SSO（OAuth2 + PKCE）授权登录 |

---

## 快速开始

```powershell
# 1. 安装依赖
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 配置 ESI 应用凭据（必填）
#    将 client_id / client_secret / callback_url / scopes 写入 esi_credentials.json

# 3. （可选）配置环境变量
copy .env.example .env

# 4. 启动（任选其一）
.venv\Scripts\python.exe app.py
# 或双击 start.bat（关闭窗口 / 按 Ctrl+C 会自动停止服务器）
```

启动后访问 `http://localhost:5000`（监听 `0.0.0.0:5000`，`debug=True`）。

---

## 技术栈

- **后端**：Flask 3 + flask-cors，应用工厂模式（`webapp/` 包 + 分域 Blueprint）
- **采集**：aiohttp 异步并发 + 线程池、tqdm 进度
- **存储**：SQLite（多库分离，WAL 模式）
- **前端**：原生 HTML/CSS/JS，无外部 CDN 依赖（Chart.js 已本地内置），以白色为主的浅色主题
- **数据源**：EVE ESI（REST）、EVE 官方 SDE（静态数据导出 zip）

---

## 目录结构

| 路径 | 说明 |
|---|---|
| `app.py` | Flask 入口（薄入口，仅调用 `create_app()` 后启动） |
| `start.bat` | 一键启动脚本（关闭窗口 / Ctrl+C 时自动结束整棵进程树） |
| `webapp/` | 应用包：`create_app()`、SSO/密钥配置、各域路由 |
| `webapp/routes/` | Blueprint 路由：`pages` / `wallet` / `analysis` / `market` / `sso` / `collectors` |
| `webapp/static/` | 前端静态资源（`css/app.css`、`js/app.js`、本地化 Chart.js） |
| `collectors/` | ESI/SDE 采集器；公共模块 `esi_client.py`（限流 / 退避 / ETag 缓存） |
| `scripts/` | 手动维护脚本：`analysis/`、`cache_management/`、`database_maintenance/` |
| `tests/` | 测试脚本 |
| `templates/` | 页面模板（`base.html` + 各页面） |
| `docs/` | 文档：`APIs.md`、`config_description.md`、`esi_api_reference.md`、`wall.md`、`plans/`、`prototypes/` |
| `data/` | 所有 SQLite 数据库、SDE 缓存与产物（非源码） |
| `logs/` | 采集器运行日志（`logs/collectors/*.log`） |
| `_backup_pre_refactor/` | 重构前文件备份（回滚用，未纳入版本管理） |

---

## 采集控制台

控制台条目定义于 [webapp/routes/collectors.py](file:///d:/CODE/EVE_helper/webapp/routes/collectors.py) 的 `COLLECTORS`，前端自动渲染，无需改模板。当前共 5 个条目：

| key | 名称 | 脚本 | 类型 |
|---|---|---|---|
| `market_orders` | 市场订单（吉他） | `collectors/jita_market_orders_collector_async.py` | 全量分页采集 |
| `market_history` | 市场历史 | `collectors/jita_market_history_collector_async.py` | 活跃物品类型 + 近 35 天日线（逐条校验） |
| `items_sde` | 静态数据（SDE 导入） | `collectors/item_sde_collector.py` | 一次性导入 |
| `analysis_arbitrage` | 交易分析 | `scripts/analyze_arbitrage_opportunities_optimized.py` | 手动维护（生成分析数据） |
| `history_monthly` | 月度数据压缩 | `scripts/cache_management/aggregate_monthly_history.py` | 手动维护 |

> 采集器脚本默认相对 `collectors/` 解析；带 `path` 字段的按项目根目录解析（用于 `scripts/` 下的手动脚本）。

启动方式：子进程以 `sys.executable -u` 运行，`cwd` 为项目根目录，并强制 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`，避免中文 Windows 下日志按 GBK 写入导致乱码。

### SDE 导入通道

`static data export`（SDE）通道用一次下载替代数万次逐条 ESI 请求，大幅降低配额消耗：

- **来源**：`https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip`（302 跳转到带 build 号的固定地址）
- **缓存**：`data/sde/sde_latest.zip` + `sde_latest.meta.json`；按 ETag 条件请求，未变更（304）时复用本地 zip
- **导入内容**（jsonl 成员 → 表）：
  - `types.jsonl` → `items`；`typeDogma.jsonl` → `item_attributes` / `item_effects`
  - `marketGroups.jsonl` → `market_groups`、`market_group_items`（由 `items.market_group_id` 派生）
  - `mapRegions.jsonl` → `regions` / `region_constellations`
  - `mapConstellations.jsonl` → `constellations` / `constellation_systems`
  - `mapSolarSystems.jsonl` → `systems`
- **文本字段**为多语言字典，取 `zh`，缺失回退 `en`
- 导入按批提交且幂等（重复导入行数不变）

---

## 后端接口一览

**页面**：`/`、`/analysis`、`/wallet`、`/collectors`；SSO：`/login`、`/callback`

**数据 API**

| 接口 | 说明 |
|---|---|
| `/api/market_groups` | 市场分组树（含缓存于 `eve_cache.db`） |
| `/api/market_items/<group_id>` | 某市场分组下的物品（直接查 `items`） |
| `/api/market_orders/<type_id>` | 某物品的订单 |
| `/api/market_history/<type_id>` | 某物品的历史 |
| `/api/analysis` | 套利分析产物（读 `data/output/arbitrage_opportunities.json`） |
| `/api/wallet/import` (POST) | 导入钱包流水 |
| `/api/wallet/stats` / `/chart-data` / `/records` | 钱包统计 / 图表 / 明细 |
| `/api/wallet/clear` (DELETE) | 清空钱包数据 |

**采集控制台 API**

| 接口 | 说明 |
|---|---|
| `/api/collectors` | 各采集器状态（运行 / PID / 进度 / 末行日志） |
| `/api/collectors/<key>/start` (POST) | 启动 |
| `/api/collectors/<key>/stop` (POST) | 停止 |
| `/api/collectors/<key>/log` | 增量读取日志 |
| `/api/data-freshness` | 各数据集行数与最近更新时间 |

---

## 数据存储

数据库路径统一由 [paths.py](file:///d:/CODE/EVE_helper/paths.py) 基于文件位置解析，`database_manager` 按表名路由到对应库：

| 文件 | 主要表 |
|---|---|
| `data/eve_items.db` | `items`、`item_attributes`、`item_effects`、`market_groups`、`market_group_items` |
| `data/eve_universe.db` | `regions`、`region_constellations`、`constellations`、`constellation_systems`、`systems` |
| `data/eve_market_orders.db` | `market_orders` |
| `data/eve_market_history.db` | `market_history`（月度压缩后增加 `market_history_monthly`） |
| `data/eve_cache.db` | `http_cache`（ETag 条件请求缓存）、`market_tree_cache` |
| `data/eve_wallet.db` | `wallet_transactions` |

分析产物：`data/output/arbitrage_opportunities.json`（分析页数据源）与 `data/output/arbitrage_opportunities.csv`（同结果的表格版）。

---

## 配置

| 文件 | 说明 |
|---|---|
| `esi_credentials.json` | EVE SSO 应用凭据：`client_id` / `client_secret` / `callback_url` / `scopes`（**敏感，切勿提交**） |
| `config.json` | ESI 兼容日期配置：`X-Compatibility-Date`（热读取，改动后采集器下次请求即生效） |
| `.env` / 环境变量 | `EVE_HELPER_SECRET_KEY`：Flask session 加密密钥（未设置时按 client_secret 派生） |
| `data/trade_goods_groups.json` | 交易商品分组清单 |

> `.env` 需安装 `python-dotenv` 才会被 Flask 自动加载；否则请直接在系统环境变量中设置。

---

## 工程约定与注意事项

- **ESI 规范**：所有请求携带规范 `User-Agent`；按官方计费规则（2xx=2、3xx=1、4xx=5、5xx=0 令牌）使用独立令牌桶限流；429 优先按 `Retry-After` 退避；实现 ETag 条件请求缓存。**请勿绕过限流与缓存**，否则可能触发官方封禁。
- **公共模块**：限流 / 退避 / 错误率监控 / 分页一致性校验 / ETag 缓存统一封装在 `collectors/esi_client.py`。
- **订单快照完整性**：订单采集器只有拿到「无失败页 / 无空页 / 无跨代页，且订单数不低于 (总页数-1)×1000」的快照才会写库；三次整体重拉仍不满足时抛 `IncompleteSnapshotError`，**保留上一份完整数据**。写库前另有规模兜底：新快照低于库内行数的 90%（`MIN_SNAPSHOT_RATIO`）即拒绝覆盖，追踪模式同时跳过 diff（避免缺页被误记为 `delete` 事件污染 churn 统计）。
- **错误限流保护**：分页抓取改为有界工作池；连续 20 页请求失败（`MAX_CONSECUTIVE_FAILURES`）立即中止本轮，剩余页不再派发、已进入重试的请求也不再重试，并**跳过整体重拉**（系统性故障时重拉只会把错误风暴放大成 ESI 的 100 errors/60s 封禁）。
- **写库前一致性校验**：快照内出现重复 `order_id`（分页跨代混页的典型症状）一律视为不可用——快照层先整体重拉，两个写库入口（全量 / 追踪）再各兜一道，避免 staging 主键冲突中断进程。追踪循环的异常已下沉到单轮：单轮失败只跳过该轮，连续 5 轮（`MAX_CYCLE_ERRORS`）才停止循环。
- **历史数据窗口**：`HISTORY_KEEP_DAYS = 35`（须覆盖分析脚本的 30 天窗口），入库前逐条校验价格区间/日期/非负值并做批内去重；历史采集的 TLS 校验保持开启。
- **竞争强度口径**：`CHURN_WINDOW_HOURS = 24` 固定窗口 + 站点过滤 + 按窗口内快照数归一（`churn_per_snapshot`），使竞争分不随采集频率或保留期漂移；窗口内无事件时竞争分退化为中性并打印警告。
- **路径**：统一使用 `paths.py`，不依赖启动时的工作目录；请在项目根目录运行脚本。
- **数据库性能**：连接启用 `PRAGMA journal_mode=WAL; synchronous=NORMAL`。
- **回滚**：重构前文件保留在 `_backup_pre_refactor/`；本项目未使用 git 初始化。
- **本地数据**：`data/`、`logs/`、`.venv/`、`esi_credentials.json` 等不属于源码，已被 `.gitignore` 忽略。
