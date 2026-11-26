# EVE Helper 项目配置说明

## 项目概述
EVE Helper 是一个用于分析 EVE Online 游戏中市场套利机会的工具，包含 Flask 后端和前端分析页面，以及异步数据收集脚本。

## 主要配置参数

### 1. 蹲站交易分析配置 (`scripts/analyze_arbitrage_opportunities_optimized.py`)

模型说明见 `docs/station_trading_profit_model.md`：蹲站 = 单站做市，在同一站挂买单（bid）+ 挂卖单（ask）捕获价差。

| 配置项 | 变量名 | 默认值 | 说明 |
| ------ | ------ | ------ | ---- |
| 交易星域 | REGION_ID | 10000002 | 吉他星域（成交历史取值口径） |
| 交易站点 | JITA_LOCATION_ID | 60003760 | 吉他 4-4 空间站（订单簿取值口径） |
| 历史窗口 | ANALYSIS_DAYS | 30 | 分析过去30天的成交历史 |
| 竞争强度窗口 | CHURN_WINDOW_HOURS | 24 | 改单事件（churn）的统计时间窗；事件先按窗口内快照数归一为「每快照事件数」，再除以日成交量入评分 |
| 最低日成交量 | MIN_DAILY_VOLUME | 50 | 可执行性下限，低于此值的物品被过滤 |
| 价差测算深度 | DEPTH_SHARE | 0.005 | 按日成交量的 0.5% 做小深度 VWAP 定价 |
| 单次工作批 | TRADE_SHARE | 0.01 | 单次批 = 日成交量 × 1% |
| 可执行量下限 | MIN_Q | 1 | 深度计算的最小数量 |
| 垃圾买单阈值 | JUNK_BID_RATIO | 0.5 | 低于 0.5 × 最优卖价的买单视为噪声 |
| 阶梯断裂阈值 | MAX_LEVEL_GAP | 0.10 | 相邻档位价格跳变超过 10% 即停止累计（防「1 个挂单 + 远处 8 倍价挂单」虚增出货价） |
| 偏离上限 | MAX_PRICE_DEVIATION | 0.25 | 累计 VWAP 相对本侧最优价的最大偏离，超出即停止累计 |
| 费用门槛 | FEE_GATE_NET_MARGIN | 0.02 | 扣费后净收益率需 > 2% 才纳入候选 |
| 规划捕获份额 | BASE_SHARE | 0.10 | 日可吃量按日成交量的 10% 规划 |
| 经纪费率 | BROKERAGE_FEE_RATE | 0.0171 | 买/卖各收一次：价格的 1.71% |
| 交易税率 | SALES_TAX_RATE | 0.042 | 仅卖出收取：价格的 4.2% |
| 评分权重 | W_PROFIT / W_CAPITAL / W_VOLUME / W_STABILITY / W_COMPETITION | 0.30 / 0.25 / 0.20 / 0.15 / 0.10 | 净收益率 / 资本效率 / 日成交量 / 价格稳定 / 竞争宽松 |

> 在默认费用参数下，往返毛价差需 **> 8.1%** 才能不亏：`(1+B) / (1-B-T) = 1.0809`。

### 2. 数据库配置 (`database_manager.py` + `paths.py`)

数据库文件路径集中定义在 `paths.py` 的 `DB_FILES`（基于文件位置推导），`database_manager.py` 的 `DB_CONFIG` 直接引用它。

#### 数据库文件路径
| 数据库类型 | 变量名 | 文件路径 |
| ---------- | ------ | -------- |
| 物品数据库 | items | data/eve_items.db |
| 市场订单数据库 | market_orders | data/eve_market_orders.db |
| 市场历史数据库 | market_history | data/eve_market_history.db |
| 宇宙数据数据库 | universe | data/eve_universe.db |
| 缓存数据库 | cache | data/eve_cache.db |
| 钱包数据库 | wallet | data/eve_wallet.db |

#### 表到数据库的映射
| 表名 | 数据库类型 |
| ---- | ---- |
| items | items |
| item_attributes | items |
| item_effects | items |
| market_groups | items |
| market_group_items | items |
| market_orders | market_orders |
| market_history | market_history |
| market_history_monthly | market_history |
| regions | universe |
| region_constellations | universe |
| constellations | universe |
| constellation_systems | universe |
| systems | universe |
| market_tree_cache | cache |
| wallet_transactions | wallet |

### 3. Flask 应用配置 (`app.py` / `webapp/`)

`app.py` 为薄入口；应用装配（`create_app`）、SSO 常量与 `secret_key` 逻辑位于 `webapp/`。

| 配置项 | 值 | 说明 |
| ------ | --- | ---- |
| 调试模式 | debug=True | 开发模式下启用调试 |
| 主机 | host='0.0.0.0' | 允许外部访问 |
| 端口 | port=5000 | 应用运行端口 |

## JSON 配置文件

### 1. `data/trade_goods_groups.json`
包含贸易货物分类的市场组ID，用于过滤掉不需要分析的物品类型：

- `original_trade_goods_groups`: 原始贸易货物分类ID列表
- `all_trade_goods_groups`: 所有贸易货物分类ID列表（包括子分类）
- `group_count`: 分类总数

### 2. `data/output/arbitrage_opportunities.json`
蹲站交易分析结果的输出文件，按综合评分降序排列，结构如下（`data/output/arbitrage_opportunities.csv` 为同一结果的表格版）：

- `type_id`: 物品ID
- `name`: 物品名称
- `lowest_sell_price`: 最优卖价（卖盘一档）
- `highest_buy_price`: 最高买价（垃圾单过滤后买盘一档）
- `acquisition_price`: 收购价（买盘小深度 VWAP，你挂买单的实际成交均价）
- `disposal_price`: 出货价（卖盘小深度 VWAP，你挂卖单的实际成交均价）
- `acquisition_depth_qty` / `disposal_depth_qty`: 两侧实际累计到的数量（受阶梯断裂保护截断）
- `gross_spread_pct`: 毛价差率（出货价 − 收购价）/ 收购价
- `profit_margin`: 扣费后净收益率（= 每单位净利 / 买入成本）
- `profit_per_unit`: 每单位净利（ISK）
- `ideal_profit`: 日可执行利润（ISK，按日成交量 10% 规划）
- `avg_daily_volume`: 平均每日交易量
- `market_size`: 日均市场规模（日成交量 × 日均价）
- `capital_eff`: 资本效率（日利润 / 资金占用），对应前端 `mvp_score`
- `capital`: 单次工作批的资金占用
- `exec_Q` / `executable_daily_units` / `turns_per_day`: 单次批 / 日可吃量 / 每日周转次数
- `price_trend`: 价格趋势（窗口首末日均价变化率）
- `price_volatility`: 价格波动率（日均价变异系数，库存风险代理）
- `price_position`: 当前卖价在窗口价格区间中的位置
- `today_high` / `today_low`: 最新一日最高价 / 最低价
- `avg_7d_high` / `avg_7d_low` / `avg_7d_spread`: 近 7 日均高 / 均低 / 均价差
- `churn_events` / `churn_intensity`: 站点改单事件数 / 每单位成交的改单强度（竞争代理）
- `book_depth` / `depth_volume_ratio`: 盘口挂单总量 / 其与日成交量之比（库存天数）
- `score`: 综合评分（0~100，五项分位归一加权）
- `n_profit` / `n_capital` / `n_volume` / `n_stability` / `n_competition`: 五项归一子分
- `sell_order_count` / `buy_order_count`: 卖单数 / 过滤后买单数
- `strategy`: 策略标识（`station_market_making`）

## 数据收集配置

### 1. 异步市场订单收集器 (`collectors/jita_market_orders_collector_async.py`)

主要配置项：

- `BASE_URL`: EVE Online ESI API 基础URL
- `RATE_LIMIT`: API请求速率限制（每秒请求数）
- `MAX_CONCURRENT_REQUESTS`: 最大并发请求数
- `REGION_ID`: 分析的区域ID（默认：10000002，即新伊甸）
- `SYSTEM_ID`: 分析的星系ID（默认：30000142，即吉他）

### 2. 异步市场历史收集器 (`collectors/jita_market_history_collector_async.py`)

- `HISTORY_KEEP_DAYS`: 历史日线入库窗口（默认 35 天，需覆盖 `ANALYSIS_DAYS=30`；ESI 一次返回全量历史，该值只影响入库量）
- `batch_size`: 每批保存的类型数
- 入库前逐条校验：日期格式/未来日期、`lowest > 0`、`highest >= lowest`、`lowest <= average <= highest`、非负 `order_count`/`volume`；批内按 `(type_id, date)` 去重，非法与超期记录计入日志的「跳过」计数
- TLS 校验保持开启（历史版本曾用 `ssl=False` 关闭证书校验，已移除）

### 3. 订单追踪（`market_orders_tracker`，见 `config.json`）

- `enabled`: 是否启用追踪模式（关闭时每次启动只做一次全量覆盖）
- `interval_minutes`: 采集间隔
- `retention_hours`: `market_order_events` 事件保留窗口（默认 72h，稳态约 130 万行 / 126MB）
- 竞争强度统计使用独立的 24h 窗口（`CHURN_WINDOW_HOURS`），与保留期解耦

## 配置使用说明

### 修改配置参数

1. **套利分析配置**：
   编辑 `scripts/analyze_arbitrage_opportunities_optimized.py` 文件中的配置变量。

2. **数据库配置**：
   编辑 `paths.py` 中的 `DB_FILES`（或 `database_manager.py` 中的 `DB_CONFIG`）修改数据库文件路径。

3. **Flask 应用配置**：
   编辑 `app.py` 文件中的 `app.run()` 函数参数，修改主机、端口等配置；SSO 与 `secret_key` 配置见 `webapp/config.py`。

### 执行分析

1. 启动 Flask 应用：
   ```bash
   python app.py
   ```

2. 执行套利分析：
   ```bash
   python scripts/analyze_arbitrage_opportunities_optimized.py
   ```

3. 运行异步数据收集器：
   ```bash
   python collectors/jita_market_orders_collector_async.py
   ```

## 注意事项

1. **数据库文件**：SQLite 数据库位于 `data/` 目录（路径由 `paths.py` 统一定义）。

2. **API 密钥**：某些 ESI API 请求可能需要认证，确保已正确配置 API 密钥。

3. **性能优化**：
   - 可以调整 `MIN_DAILY_VOLUME` 和 `FEE_GATE_NET_MARGIN` 来控制候选物品数量
   - 可以修改 `ANALYSIS_DAYS` 来调整分析的历史数据范围

4. **费用与技能**：
   - `BROKERAGE_FEE_RATE` / `SALES_TAX_RATE` 随贸易技能与 NPC 声望变化，换号只需改这两个参数
   - 二者越低，费用盈亏平衡门槛（毛价差 8.1%）越低，可交易集合越大

## 更新日志

- 2026-10-14: 交易分析脚本改用「蹲站交易（单站做市）」模型：修正买卖方向、小深度 VWAP 定价、垃圾买单过滤、费用门槛与多因子评分，并新增 CSV 产物
- 2024-12-18: 更新总预期利润评分标准，调整为 6 个等级（最高15分，最低0分）
- 2024-12-18: 修复总预期利润筛选功能，添加 "≤5,000,000 ISK" 选项
- 2024-12-18: 交易分析页面默认不筛选总预期利润
- 2024-12-18: 修复异步数据收集器的模块导入错误