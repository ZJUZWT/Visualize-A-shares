# Multi-Market Data Expansion Design

> 编写日期：2026-03-24
> 范围：为数据引擎、产业链引擎和专家工具层补齐多市场统一适配能力，覆盖 A 股、港股、美股、场外基金、期货，并提供跨市场联动分析桥接层。

---

## 1. 背景

当前系统虽然已经具备较强的 A 股能力，但数据模型和查询入口都默认“标的 = A 股股票”：

1. `DataEngine` 的核心接口默认面向 A 股快照、本地 DuckDB 和 6 位代码
2. `IndustryEngine` 的行业映射完全来自 A 股公司概况
3. `ExpertTools` 的数据调用只有 `search_stock` / `get_company_profile` / `get_daily_history`
4. API 路由没有“市场类型”这个一等概念

这导致：

- 港股、美股、基金、期货无法统一接入
- 跨市场联动只能靠 prompt 文字描述，缺少结构化桥接
- 如果直接逐市场硬编码，会在 `data` / `industry` / `expert` / `mcpserver` 中复制分支逻辑

用户本轮要求是“一口气做好”，因此必须先补抽象层，再把实际市场接入落下去。

---

## 2. 目标

本模块完成后，应具备：

1. 统一的标的身份模型，可区分 `cn / hk / us / fund / futures`
2. 统一的市场适配器接口，覆盖：
   - 搜索
   - 基础信息
   - 最新报价
   - 日线历史
3. `DataEngine` 和 REST API 能按市场统一查询
4. `IndustryEngine` 能基于桥接规则产出跨市场相关资产
5. `ExpertTools` 能消费统一数据接口，而不是默认只服务 A 股
6. 保持现有 A 股路径兼容，不破坏已有快照、量化、聚类能力

---

## 3. 非目标

本轮不做：

- 全球多市场分钟线统一采集
- 多币种估值换算与组合归因
- 全自动全球产业图谱构建
- 商业级美股行情源接入（如 Polygon 正式集成）
- 统一写入所有非 A 股市场到 DuckDB 的长期缓存体系

本轮目标是“统一接入 + 可用桥接 + 稳定兼容”，不是全球交易终端。

---

## 4. 方案对比

### 方案 A：逐市场硬编码接入

优点：

- 起步快
- 单点改动容易

缺点：

- 逻辑会分散到多个模块
- 以后新增市场会重复 if/else
- 跨市场联动会越来越难维护

不采用。

### 方案 B：AssetIdentity + MarketAdapter + CrossMarketBridge

优点：

- 一次解决统一接入和跨市场联动
- 能兼容现有 A 股体系
- 后续再扩 ETF、加密货币等也有落点

缺点：

- 需要先补几层基础抽象

推荐采用。

### 方案 C：只做数据接入，不做桥接

优点：

- 风险更低

缺点：

- TODO 里的“跨市场联动分析”无法真正完成

不采用。

---

## 5. 核心设计

### 5.1 AssetIdentity

新增统一标的身份模型，至少包含：

- `market`
  - `cn`
  - `hk`
  - `us`
  - `fund`
  - `futures`
- `asset_type`
  - `stock`
  - `fund`
  - `future`
  - `etf`
- `symbol`
- `display_name`
- `currency`
- `exchange`

解析入口由 `AssetResolver` 提供：

- `600519` → `cn/stock`
- `00700` → `hk/stock`
- `AAPL` → `us/stock`
- `161725` → `fund/fund`
- `CL` / `SC` / `AU0` → `futures/future`

如果无法确认市场，则：

1. 优先尝试已有 A 股解析
2. 再返回“未识别市场”的结构化提示

### 5.2 MarketAdapter

定义统一适配器接口，至少支持：

- `search(query, limit)`
- `get_profile(symbol)`
- `get_quote(symbol)`
- `get_daily_history(symbol, start, end)`

五个市场的落地方式：

`CNMarketAdapter`

- 复用现有 `DataEngine`
- 优先使用 DuckDB / Collector / Profiles

`HKMarketAdapter`

- 走 AKShare 港股接口
- 提供港股搜索、基础信息、报价和历史

`USMarketAdapter`

- 优先走 `yfinance`
- 做成可选依赖
- 若运行环境缺少依赖或网络失败，返回结构化降级错误

`FundMarketAdapter`

- 走 AKShare 基金接口
- 重点支持场外基金搜索、净值历史、基础信息

`FuturesMarketAdapter`

- 走 AKShare 期货接口
- 支持常用品种搜索、主力合约基础信息与历史

### 5.3 MarketRegistry

新增注册中心，根据 `market` 选择 adapter：

- `cn` → `CNMarketAdapter`
- `hk` → `HKMarketAdapter`
- `us` → `USMarketAdapter`
- `fund` → `FundMarketAdapter`
- `futures` → `FuturesMarketAdapter`

这样 `DataEngine` 不需要知道每个市场的具体细节，只需要：

1. 解析 `AssetIdentity`
2. 分发给正确 adapter
3. 标准化返回

### 5.4 DataEngine 扩展策略

保留现有 A 股接口不动，同时新增统一入口：

- `resolve_asset(query, market_hint="")`
- `search_assets(query, market="all", limit=20)`
- `get_asset_profile(symbol, market)`
- `get_asset_quote(symbol, market)`
- `get_asset_daily_history(symbol, market, start, end)`

兼容原则：

- 旧的 `get_profile` / `get_daily_history` / `get_snapshot` 保持原行为
- 新接口只在多市场场景下使用

### 5.5 CrossMarketBridge

为产业链引擎和专家系统增加桥接层，先落三类规则：

1. `行业桥`
   - 同行业/同主题跨市场关联
2. `链条桥`
   - 上游原材料、下游应用在不同市场之间的映射
3. `替代桥`
   - 同一投资命题的替代资产

桥接结果统一为：

- `target_asset`
- `bridge_type`
- `reason`
- `related_assets[]`

示例：

- A 股锂电 → 港股锂资源股 → 美股清洁能源 ETF
- 原油期货 → A 股炼化 → 美股能源 ETF
- 黄金期货 → A 股贵金属 → 美股黄金 ETF

### 5.6 IndustryEngine 集成

新增跨市场桥接入口，例如：

- `bridge_market_assets(target, market="", limit=10)`

调用流程：

1. 解析 `AssetIdentity`
2. 若是 A 股股票，继续复用现有行业识别逻辑
3. 若是其他市场标的，优先使用桥接规则推导主题/行业
4. 输出结构化跨市场相关资产列表

这一层不是要替代原有 `IndustryCognition`，而是给它补“跨市场相邻资产”的上下文。

### 5.7 ExpertTools 集成

`ExpertTools` 需要新增多市场动作，例如：

- `search_asset`
- `get_asset_profile`
- `get_asset_quote`
- `get_asset_daily_history`
- `bridge_market_assets`

其中：

- 原有 A 股动作继续保留
- 新动作走 `DataEngine` / `IndustryEngine` 的统一入口

这样专家链路可以在不破坏旧 prompt 的前提下，逐步查询跨市场标的。

### 5.8 API 设计

`/api/v1/data` 新增统一端点：

- `GET /assets/search`
- `GET /assets/profile`
- `GET /assets/quote`
- `GET /assets/daily`

参数核心为：

- `symbol`
- `market`
- `q`

`/api/v1/industry` 新增跨市场桥接端点：

- `GET /bridge/{target}`

返回：

- 标的解析结果
- 桥接类型
- 相关资产列表

---

## 6. 数据源策略

### 6.1 A 股

完全复用现有 `DataEngine` 与 `Collector`。

### 6.2 港股 / 基金 / 期货

优先使用 AKShare，因为：

- 当前仓库已声明依赖
- 引入成本最低
- 与现有数据采集体系一致

### 6.3 美股

优先使用 `yfinance`，但做成“可选依赖 + 显式降级”：

- 环境缺失依赖时，不让整个模块崩溃
- 返回可理解的结构化错误
- 为将来替换 Polygon 等商业源预留 provider 位置

---

## 7. 错误处理与回退

回退原则：

1. 单市场失败不影响其他市场
2. 美股依赖缺失时只降级美股
3. 桥接规则未命中时返回空列表，而不是编造结果
4. 资产解析失败时先尝试 A 股默认逻辑，再返回未识别提示

这能保证：

- 多市场是增量能力，不是脆弱依赖
- 现有 A 股路径继续稳定

---

## 8. 测试策略

重点测试四层：

1. `AssetResolver`
   - 五类市场识别正确
2. `MarketAdapter`
   - 统一 contract 正常返回
   - 美股可选依赖降级正常
3. `CrossMarketBridge`
   - 主题桥 / 链条桥 / 替代桥能产出结果
4. `Routes + ExpertTools`
   - 新 API 可访问
   - 专家工具层可调用多市场统一接口

同时做回归：

- 现有 A 股数据路由不回归
- `ExpertTools` 原有动作不回归
- `IndustryEngine` 现有行业认知能力不回归

---

## 9. 实施结论

采用方案 B：`AssetIdentity + MarketAdapter + CrossMarketBridge`。

本轮优先完成：

1. 统一标的身份和解析器
2. 五类市场 adapter 接入
3. `DataEngine` 统一入口和 REST API
4. `IndustryEngine` 跨市场桥接
5. `ExpertTools` 多市场调用能力

这样可以一次把多市场接入和跨市场联动分析同时补齐，同时保持现有 A 股主链路稳定。
