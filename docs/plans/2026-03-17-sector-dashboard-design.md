# 板块研究仪表盘（Sector Dashboard）设计文档

> 日期: 2026-03-17
> 状态: 已确认

## 目标

新增前端 `/sector` 页面 — 仪表盘式板块研究工具，支持行业板块/概念板块切换、板块涨跌排行、资金流热力图、成分股穿透、日期选择历史查看、板块级多因子预测和轮动预测。

## 需求摘要

- **仪表盘式交互**：一屏纵览，非对话式
- **行业板块 + 概念板块**：顶部 Tab 切换，行业为主视图
- **完整量化预测**：板块级因子系统 + 轮动预测模型
- **数据采集走现有数据引擎**：扩展 DataEngine / DataCollector / AKShareSource / DuckDBStore
- **网格热力图**：行=板块，颜色=涨跌幅，亮度=资金流强度
- **成分股穿透**：点击板块查看其下所有个股
- **日期选择器**：查看历史任意日期的板块数据
- **列表纵览**：排行列表可切换排序维度

## 架构

### 数据流

```
AKShare 板块 API
    │
    ▼
AKShareSource (扩展)          ← data/sources/akshare_source.py
    │
    ▼
DataCollector (编排)           ← data/collector.py
    │
    ▼
DataEngine (门面)              ← data/engine.py
    │
    ├──► DuckDBStore            ← data/store.py (新增 sector schema)
    │     · sector.board_daily
    │     · sector.fund_flow_daily
    │
    ▼
SectorEngine                   ← sector/engine.py (新增)
    │
    ├──► SectorPredictor        ← sector/predictor.py (新增)
    │     · 10 因子多因子模型
    │     · 轮动预测
    │
    ▼
FastAPI Routes                 ← sector/routes.py (新增)
    │
    ▼
前端 /sector 页面               ← app/sector/page.tsx (新增)
```

### 后端文件结构

```
backend/engine/sector/            ← 新增板块引擎
├── __init__.py
├── engine.py                     # SectorEngine — 核心（调用 DataEngine）
├── predictor.py                  # SectorPredictor — 多因子 + 轮动
├── schemas.py                    # Pydantic 模型
└── routes.py                     # FastAPI 路由

backend/engine/data/              ← 现有数据引擎扩展
├── engine.py                     # + get_sector_boards(), get_sector_history(),
│                                 #   get_sector_fund_flow(), get_sector_cons()
├── collector.py                  # + 板块数据编排方法
├── store.py                      # + sector.board_daily, sector.fund_flow_daily
└── sources/akshare_source.py     # + 6 个板块 AKShare API 封装
```

### AKShare 板块 API

| API | 用途 |
|-----|------|
| `stock_board_industry_name_em()` | 行业板块列表 + 实时行情 |
| `stock_board_concept_name_em()` | 概念板块列表 + 实时行情 |
| `stock_board_industry_hist_em(symbol, start_date, end_date)` | 行业板块历史 K 线 |
| `stock_board_concept_hist_em(symbol, start_date, end_date)` | 概念板块历史 K 线 |
| `stock_sector_fund_flow_rank(indicator, sector_type)` | 板块资金流排行 |
| `stock_board_industry_cons_em(symbol)` | 行业板块成分股 |

### DuckDB 新增表

```sql
CREATE TABLE IF NOT EXISTS sector.board_daily (
    board_code VARCHAR,
    board_name VARCHAR,
    board_type VARCHAR,        -- 'industry' / 'concept'
    date DATE,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    pct_chg DOUBLE,
    volume DOUBLE,
    amount DOUBLE,
    turnover_rate DOUBLE,
    PRIMARY KEY (board_code, date)
);

CREATE TABLE IF NOT EXISTS sector.fund_flow_daily (
    board_code VARCHAR,
    board_name VARCHAR,
    board_type VARCHAR,
    date DATE,
    main_force_net_inflow DOUBLE,
    main_force_net_ratio DOUBLE,
    super_large_net_inflow DOUBLE,
    large_net_inflow DOUBLE,
    medium_net_inflow DOUBLE,
    small_net_inflow DOUBLE,
    PRIMARY KEY (board_code, date)
);
```

### 板块级因子系统（10 因子）

| # | 因子名 | 来源 | 方向 | Group | 说明 |
|---|--------|------|------|-------|------|
| 1 | sector_reversal_1d | board_daily | -1 | momentum | 昨日涨幅极端→今日反转 |
| 2 | sector_momentum_5d | board_daily | +1 | momentum | 5日板块涨幅动量 |
| 3 | sector_momentum_20d | board_daily | +1 | momentum | 20日板块动量 |
| 4 | sector_volume_surge | board_daily | +1 | liquidity | 成交量/20日均量 比值 |
| 5 | sector_turnover_zscore | board_daily | -1 | liquidity | 换手率 Z-Score |
| 6 | main_force_flow_ratio | fund_flow | +1 | capital_flow | 当日主力净流入占比 |
| 7 | main_force_flow_5d_avg | fund_flow | +1 | capital_flow | 5日主力净流入均值 |
| 8 | main_force_flow_trend | fund_flow | +1 | capital_flow | 连续净流入天数 (+N/-N) |
| 9 | super_large_flow_ratio | fund_flow | +1 | capital_flow | 超大单净流入占比 |
| 10 | sector_ma_dev_10 | board_daily | -1 | technical | 10日均线偏离度 |

预测管道与 `StockPredictorV2` 同架构：MAD去极值 → Z-Score → 施密特正交化 → ICIR加权 → 正态CDF概率。

### API 设计

```
GET  /api/v1/sector/boards?type=industry&date=2026-03-17
     → 板块列表 + 涨跌 + 资金流 + 预测信号

GET  /api/v1/sector/{board_code}/history?start=2026-01-01&end=2026-03-17
     → 板块历史行情 + 资金流时序

GET  /api/v1/sector/{board_code}/constituents?date=2026-03-17
     → 成分股列表 + 各股涨跌 + 资金流

GET  /api/v1/sector/heatmap?type=industry&date=2026-03-17
     → 热力图数据

GET  /api/v1/sector/rotation?days=10&type=industry
     → 轮动预测矩阵 + 预测排名

POST /api/v1/sector/fetch?type=industry
     → 触发数据采集
```

### 前端页面布局

```
┌──NavSidebar──┬───────────────────────────────────────────────┐
│  🏔 地形图    │  [行业板块] [概念板块]     📅 日期选择器        │
│  ⚖ 专家辩论  ├───────────────────┬───────────────────────────┤
│  🧠 投资专家  │  板块排行列表       │     网格热力图             │
│  📊 板块研究  │  (涨跌幅/资金流/    │     (行=板块, 颜色=涨跌幅,  │
│              │   预测信号 排序)    │      亮度=资金流强度)       │
│              ├───────────────────┴───────────────────────────┤
│              │  点击板块 → 展开详情面板                         │
│              │  ┌────────────────┬───────────────────────────┤
│              │  │ 板块趋势图      │  成分股列表                 │
│              │  │ K线 + 资金流    │  代码  名称  涨跌  主力流入  │
│              │  │ 叠加 + 预测标注  │                           │
│              │  └────────────────┴───────────────────────────┤
│              │  板块轮动预测面板                                │
│              │  热力矩阵 + 预测 Top5 看涨/看跌                  │
│              └───────────────────────────────────────────────┘
└──────────────┘
```

**前端文件结构**:

```
frontend/
├── app/sector/page.tsx                # 板块页面入口
├── components/sector/
│   ├── SectorDashboard.tsx            # 仪表盘容器
│   ├── SectorRankTable.tsx            # 排行列表
│   ├── SectorHeatMap.tsx              # 网格热力图
│   ├── SectorDetailPanel.tsx          # 点击展开详情
│   ├── SectorTrendChart.tsx           # 趋势图（K线+资金流）
│   ├── ConstituentTable.tsx           # 成分股列表
│   ├── SectorRotationPanel.tsx        # 轮动预测面板
│   ├── BoardTypeTab.tsx               # 行业/概念切换 Tab
│   └── DatePicker.tsx                 # 日期选择器
└── stores/useSectorStore.ts           # Zustand store
```

**NavSidebar 新增**:
```typescript
{ href: "/sector", icon: TrendingUp, label: "板块研究" }
```

## 开发计划（6 Chunks）

| Chunk | 内容 | 涉及文件数 |
|-------|------|-----------|
| 1 | 数据引擎扩展：AKShare 板块 API 封装 + DuckDB 表 + DataEngine/Collector 扩展 | ~4 文件修改 |
| 2 | SectorEngine 核心 + schemas + routes | ~5 文件新增 |
| 3 | SectorPredictor 因子系统 + 轮动预测 | ~1 文件新增 |
| 4 | 前端页面框架 + 排行列表 + 热力图 | ~6 文件新增 |
| 5 | 前端详情面板 + 成分股 + 轮动面板 | ~4 文件新增 |
| 6 | 联调 + 日期选择 + 排序切换 + NavSidebar | ~3 文件修改 |

## 约束

- 数据采集必须走 DataEngine，不允许绕过
- 遵守项目铁律：LLM/API 原始数据不做截断
- 所有关键调用需有 ⏱️ 耗时统计
- 前端使用 Next.js App Router 文件系统路由
