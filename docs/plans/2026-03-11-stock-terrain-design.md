# 🏔️ StockTerrain — A股多维聚类3D地形可视化平台

## 技术落地实施方案 v1.0

> **产品定位**：全球首款将 A股 5000+ 支股票映射为实时动态 3D 地形图的金融可视化平台
> **设计哲学**：Data is the terrain. Market is the landscape.
> **编写日期**：2026-03-11

---

## 一、产品与技术架构总览

### 1.1 系统全景架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │   React 19   │  │  Zustand     │  │  React Three Fiber (R3F)  │ │
│  │   Next.js 15 │  │  State Mgmt  │  │  + drei + postprocessing  │ │
│  │   TailwindCSS│  │              │  │  + custom shaders (GLSL)  │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬───────────────┘ │
│         │                 │                       │                 │
│         └────────────┬────┘───────────────────────┘                 │
│                      │  WebSocket (实时行情流)                       │
│                      │  REST API   (批量查询)                       │
└──────────────────────┼──────────────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          │     API GATEWAY         │
          │   (FastAPI + Uvicorn)   │
          │   - REST endpoints      │
          │   - WebSocket hub       │
          │   - Rate limiting       │
          │   - JWT Auth            │
          └─────┬──────────┬────────┘
                │          │
    ┌───────────┴──┐  ┌────┴──────────────┐
    │ DATA ENGINE  │  │ ALGORITHM ENGINE   │
    │ (Python)     │  │ (Python)           │
    │              │  │                    │
    │ • Collector  │  │ • Clustering       │
    │ • Cleaner    │  │   (HDBSCAN)        │
    │ • Scheduler  │  │ • Dimensionality   │
    │ • Cache Mgr  │  │   Reduction (UMAP) │
    │              │  │ • Interpolation    │
    │              │  │   (RBF/Kriging)    │
    └──────┬───────┘  └────────┬───────────┘
           │                   │
    ┌──────┴───────────────────┴──────┐
    │         STORAGE LAYER           │
    │  ┌─────────┐  ┌──────────────┐  │
    │  │ SQLite / │  │   Redis      │  │
    │  │ DuckDB   │  │ (Hot Cache)  │  │
    │  │ (持久化)  │  │ (实时行情)    │  │
    │  └─────────┘  └──────────────┘  │
    └─────────────────────────────────┘
```

### 1.2 核心设计原则

| 原则 | 说明 |
|------|------|
| **引擎分离** | Data Engine 与 Rendering Engine 通过 API 契约完全解耦，可独立部署/替换 |
| **数据源冗余** | 至少 3 个数据源互为 fallback，单源故障不影响服务 |
| **算法可插拔** | 聚类/降维/插值算法通过 Strategy Pattern 注册，可热切换 |
| **渲染分层** | 2D 股票节点层 + 3D 地形曲面层 + UI 覆盖层，各层独立更新 |
| **离线优先** | 本地 SQLite/DuckDB 存储历史数据，断网时仍可分析 |

---

## 二、数据引擎方案 (Data Engine) — 核心重点

### 2.1 数据源深度对比与选型

> **核心挑战**：A股数据源生态碎片化严重，没有单一完美数据源。
> **解决思路**：构建「多源聚合 + 智能降级」数据中台。

#### 数据源矩阵

| 维度 | AKShare ⭐主力 | BaoStock 备选 | Tushare Pro 补充 | 东方财富直连 应急 |
|------|-------------|------------|---------------|--------------|
| **费用** | 完全免费开源 | 完全免费 | 积分制(120基础) | 免费(非官方) |
| **实时行情** | ✅ `stock_zh_a_spot_em` 全量5000+股 | ❌ 仅日频T+1 | ⚠️ 高积分才有 | ✅ 东方财富推送 |
| **分钟级K线** | ✅ 1/5/15/30/60分钟 | ✅ 5/15/30/60分钟 | ✅ 全频次 | ✅ |
| **日线历史** | ✅ 1990年至今 | ✅ 1990年至今 | ✅ 全量 | ✅ |
| **财务数据** | ✅ 季频/年频 | ✅ 季频(2007至今) | ✅ 最全面 | ⚠️ 需爬取 |
| **限频** | 无硬性限制 | 无限制,可多进程 | 严格(0.3s/次) | 需控制频率 |
| **注册门槛** | 无需注册 | 匿名可用 | 需注册+积分 | 无需注册 |
| **数据质量** | ⭐⭐⭐⭐ 东财源 | ⭐⭐⭐⭐ 证交所源 | ⭐⭐⭐⭐⭐ 最优 | ⭐⭐⭐⭐ |
| **维护活跃度** | ⭐⭐⭐⭐⭐ 社区活跃 | ⭐⭐⭐ 更新较慢 | ⭐⭐⭐⭐ 商业维护 | N/A |
| **稳定性** | ⭐⭐⭐ 依赖东财接口 | ⭐⭐⭐⭐ 独立服务 | ⭐⭐⭐⭐⭐ 最稳定 | ⭐⭐ 可能被封 |

#### 🏆 最终选型策略：三级数据源架构

```
Level 1 (Primary)  : AKShare     → 实时行情 + 日线 + 基本面（免费、全量、快速）
Level 2 (Secondary): BaoStock    → 历史K线 + 财务报表（免费、稳定、无限制）
Level 3 (Premium)  : Tushare Pro → 高质量财务 + 特色指标（需积分，数据最精准）
Fallback           : 东方财富直连 → AKShare 挂掉时的应急降级方案
```

**为什么 AKShare 是主力？**
1. **零门槛**：无需注册、无需积分、无需 API Key，即开即用
2. **实时行情能力**：`stock_zh_a_spot_em()` 一次拉取全市场 5000+ 股票的实时快照（价格、涨跌幅、成交量、换手率等 20+ 字段）
3. **数据源可靠**：底层数据来自东方财富，A股最大的散户金融门户
4. **开源社区活跃**：GitHub 16k+ stars，issue 响应迅速，接口更新及时
5. **全品种覆盖**：股票、ETF、期货、期权、宏观经济、行业数据一应俱全

**BaoStock 为什么做备选？**
1. **独立数据源**：数据直接来源于证交所，与 AKShare(东财源) 形成交叉验证
2. **无任何限制**：可同时运行多个 Python 进程并行拉取，速度极快
3. **财务数据结构化好**：利润表/资产负债表/现金流量表接口规范

**Tushare Pro 为什么做补充？**
1. **数据质量最高**：金融数据专业团队维护，偏差最小
2. **特色指标独有**：复权因子(adj_factor)、龙虎榜、大宗交易等
3. **缺点明确**：积分门槛高(5000分起)、频率限制严格(0.3s/次)

### 2.2 数据维度设计

系统需要采集和计算的多维数据，用于后续的聚类分析：

#### A. 基本面维度 (Fundamental)
```python
FUNDAMENTAL_FEATURES = {
    # 估值指标
    "pe_ttm":        "市盈率(TTM)",
    "pb":            "市净率",
    "ps_ttm":        "市销率(TTM)",
    "pcf_ttm":       "市现率(TTM)",
    
    # 盈利能力
    "roe":           "净资产收益率",
    "roa":           "总资产收益率",
    "gross_margin":  "毛利率",
    "net_margin":    "净利率",
    
    # 成长性
    "revenue_yoy":   "营收同比增长率",
    "profit_yoy":    "净利润同比增长率",
    "roe_yoy":       "ROE同比变化",
    
    # 规模
    "total_mv":      "总市值(亿)",
    "circ_mv":       "流通市值(亿)",
}
```

#### B. 技术面维度 (Technical)
```python
TECHNICAL_FEATURES = {
    "volatility_20d":   "20日波动率",
    "volatility_60d":   "60日波动率",
    "beta":             "Beta系数(相对沪深300)",
    "rsi_14":           "RSI(14日)",
    "macd_signal":      "MACD信号",
    "ma_deviation_20":  "20日均线偏离度",
    "ma_deviation_60":  "60日均线偏离度",
    "atr_14":           "ATR(14日)",
    "momentum_20d":     "20日动量",
}
```

#### C. 资金面维度 (Money Flow)
```python
MONEY_FLOW_FEATURES = {
    "turnover_rate":    "换手率",
    "volume_ratio":     "量比",
    "net_mf_amount":    "主力净流入额",
    "northbound_pct":   "北向资金持仓占比",
    "concentration":    "筹码集中度",
}
```

### 2.3 数据采集架构

```python
# 核心设计：多源采集器 + 智能降级 + 自动修复

class DataCollectorOrchestrator:
    """
    数据采集编排器 — 三级数据源 + 智能降级
    
    设计原则：
    1. Primary 优先，失败自动降级到 Secondary
    2. 采集结果自动交叉校验（相同字段的数据偏差 > 5% 告警）
    3. 所有数据统一进入 Unified Schema 后再入库
    """
    
    采集流程:
    ┌─────────────┐     ┌────────────┐     ┌──────────────┐
    │ AKShare      │────▶│ Unified    │────▶│ SQLite/DuckDB│
    │ (Primary)    │     │ Schema     │     │ (Persistent) │
    └──────┬──────┘     │ Converter  │     └──────────────┘
           │ fail       └─────┬──────┘              │
    ┌──────▼──────┐          │              ┌───────▼──────┐
    │ BaoStock     │──────────┘              │ Redis        │
    │ (Secondary)  │                         │ (Hot Cache)  │
    └──────┬──────┘                         └──────────────┘
           │ fail
    ┌──────▼──────┐
    │ Tushare Pro  │
    │ (Tertiary)   │
    └─────────────┘
```

### 2.4 数据刷新策略

| 数据类型 | 刷新频率 | 数据源 | 缓存策略 |
|---------|---------|--------|---------|
| **实时行情快照** | 盘中每 30 秒 | AKShare `stock_zh_a_spot_em` | Redis TTL=30s |
| **日线行情** | 每日 17:30 后 | AKShare → BaoStock 校验 | SQLite 永久 |
| **分钟线K线** | 每日 20:30 后 | BaoStock `query_history_k_data_plus` | SQLite 永久 |
| **财务报表** | 季报披露后 | BaoStock → Tushare 校验 | SQLite 永久 |
| **技术指标** | 日线更新后计算 | 本地 Python 计算 | Redis TTL=24h |
| **聚类/降维结果** | 每日盘后重算 | 算法引擎 | Redis TTL=24h |

### 2.5 存储方案

#### 为什么选 DuckDB + Redis 而非 PostgreSQL？

| 对比项 | DuckDB ⭐ | PostgreSQL | SQLite |
|-------|---------|-----------|--------|
| **部署复杂度** | 零依赖，嵌入式 | 需独立部署 | 零依赖 |
| **列式分析性能** | ⭐⭐⭐⭐⭐ OLAP极强 | ⭐⭐⭐ | ⭐⭐ |
| **金融时序查询** | 原生窗口函数极快 | 需优化 | 一般 |
| **文件大小** | 单文件 | 需管理 | 单文件 |
| **Python集成** | 完美 (import duckdb) | 需驱动 | 完美 |
| **适合场景** | 分析型(本产品核心) | OLTP | 轻量存储 |

**最终选择**：
- **DuckDB**：持久化存储 + 高性能分析查询（单机可处理 5000 股 × 10 年日线 ≈ 1200 万行，亚秒级响应）
- **Redis**：热数据缓存（实时行情、当日聚类结果、用户会话）

---

## 三、算法引擎方案 (Algorithm Engine)

### 3.1 多维聚类算法选型

#### 为什么选 HDBSCAN 而非 K-Means？

| 对比项 | HDBSCAN ⭐ | K-Means | DBSCAN | GMM |
|-------|---------|---------|--------|-----|
| **需预设簇数** | ❌ 自动发现 | ✅ 必须 | ❌ | ✅ |
| **处理噪声** | ✅ 优秀 | ❌ 差 | ✅ 中等 | ❌ |
| **非球形簇** | ✅ 任意形状 | ❌ 仅球形 | ✅ | ⚠️ |
| **层次结构** | ✅ 天然层级 | ❌ | ❌ | ❌ |
| **大数据集性能** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **金融适用性** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |

**HDBSCAN 对本产品的独特优势**：
1. **自动发现板块聚类**：无需人工指定"分几个行业"，算法自动从数据中发现自然聚类
2. **噪声识别**：自动标记"离群股"（概念独特、难以归类的个股），这本身就是有价值的分析信息
3. **层次聚类树**：可生成从粗粒度到细粒度的聚类层级（大行业 → 子行业 → 概念板块），完美匹配 LOD 需求
4. **簇稳定性评分**：每个聚类有 persistence 分数，可用于判断聚类质量

#### 聚类流水线

```
原始多维特征 (26维)
       │
       ▼
┌─────────────────┐
│ 1. 数据预处理     │  StandardScaler → 处理缺失值 → 离群值截断 (Winsorize 1%/99%)
└────────┬────────┘
         ▼
┌─────────────────┐
│ 2. 特征选择/降噪  │  PCA 保留 95% 方差 (26维 → ~12维) → 去除共线性
└────────┬────────┘
         ▼
┌─────────────────┐
│ 3. HDBSCAN 聚类  │  min_cluster_size=20, min_samples=10, metric='euclidean'
└────────┬────────┘
         ▼
┌─────────────────┐
│ 4. 聚类后处理     │  标记噪声点 → 簇标签 → 簇内统计 → 簇间距离矩阵
└─────────────────┘
```

### 3.2 降维算法选型：2D 平面投影

#### 为什么选 UMAP 而非 t-SNE？

| 对比项 | UMAP ⭐ | t-SNE | PCA | MDS |
|-------|------|-------|-----|-----|
| **保留全局结构** | ✅ 优秀 | ❌ 仅局部 | ✅ 线性 | ✅ |
| **保留局部结构** | ✅ 优秀 | ✅ 最好 | ❌ | ⚠️ |
| **计算速度** | ⭐⭐⭐⭐⭐ 极快 | ⭐⭐ 慢 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **可增量更新** | ✅ transform() | ❌ 需全量重算 | ✅ | ❌ |
| **超参数敏感** | 中等 | 高 | 低 | 低 |
| **5000个点耗时** | ~2秒 | ~30秒 | <0.1秒 | ~5秒 |

**UMAP 是本产品的最优选择**：
1. **全局+局部都保留**：相似股票靠近的同时，不同板块之间的相对位置也有意义
2. **增量更新能力**：新股上市或用户自定义股票池时，无需全量重新计算，`transform()` 即可
3. **速度极快**：5000 只股票 2 秒完成降维，支持盘中实时刷新
4. **与 HDBSCAN 天然配合**：两者同出自同一理论体系（拓扑数据分析），结合效果最佳

#### UMAP 核心参数调优指南

```python
UMAP_CONFIG = {
    "n_neighbors": 30,       # 局部邻域大小：30 对5000股票平衡局部/全局
    "min_dist": 0.3,         # 点间最小距离：0.3 避免过度拥挤
    "n_components": 2,       # 降至 2D
    "metric": "euclidean",   # 欧氏距离（标准化后的特征空间）
    "random_state": 42,      # 可复现性
    "n_epochs": 500,         # 优化迭代次数
    "spread": 1.0,           # 控制嵌入空间的尺度
}
```

### 3.3 3D 曲面插值算法

#### 核心问题

5000 个离散的 (x, y, z) 股票点 → 平滑连续的 3D 曲面 z = f(x, y)

其中：
- `(x, y)` = UMAP 降维后的 2D 坐标
- `z` = 今日涨幅（或其他实时指标）

#### 插值算法对比

| 算法 | 平滑度 | 速度 | 外推能力 | 物理直觉 | 适用场景 |
|-----|-------|------|---------|---------|---------|
| **RBF (径向基函数)** ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ 良好 | 中等 | **本产品首选** |
| 普通克里金 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ✅ 最佳 | ⭐⭐⭐⭐⭐ | 地理统计学 |
| IDW (反距离加权) | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ❌ 差 | 简单 | 快速预览 |
| 三角剖分 + 线性 | ⭐⭐ | ⭐⭐⭐⭐⭐ | ❌ | 简单 | 基础展示 |
| 自然邻点 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ❌ | 好 | 规则网格 |

#### 🏆 最终方案：RBF 插值 + 自适应网格

**为什么选 RBF？**
1. **平滑度最佳**：生成的曲面自然流畅，没有三角剖分的锯齿感
2. **计算速度快**：`scipy.interpolate.RBFInterpolator` 对 5000 点在 100×100 网格上插值 < 0.5 秒
3. **支持多种核函数**：`thin_plate_spline`（薄板样条）最适合金融地形，曲面最自然
4. **外推合理**：边缘区域不会出现剧烈震荡

```python
# 3D 曲面生成流水线
INTERPOLATION_CONFIG = {
    "method": "RBF",
    "kernel": "thin_plate_spline",   # 薄板样条 → 最自然的地形曲面
    "grid_resolution": 128,           # 128×128 网格 = 16384 个曲面点
    "smoothing": 0.1,                 # 轻微平滑，避免过拟合噪声
    "bounds_padding": 0.1,            # 边界扩展 10%
}

# 流程：
# 1. 取 UMAP 的 (x,y) 和实时涨幅 z
# 2. RBF 插值生成 128×128 高度网格
# 3. 序列化为 Float32Array → 传给前端 WebGL
# 4. 前端用 PlaneGeometry + displacementMap 渲染地形
```

### 3.4 算法引擎 API 设计

```
POST /api/v1/cluster
  Body: { features: ["pe_ttm", "roe", "volatility_20d", ...], stock_pool: "all" | [codes] }
  Response: { clusters: [{id, label, stocks, center, size}], noise_stocks: [...] }

POST /api/v1/projection
  Body: { stock_pool: [codes], method: "umap", params: {...} }
  Response: { points: [{code, name, x, y}], bounds: {xmin, xmax, ymin, ymax} }

GET /api/v1/terrain?z_metric=pct_chg&resolution=128
  Response: { 
    grid: Float32Array (128×128),  // 高度图数据
    bounds: {xmin, xmax, ymin, ymax, zmin, zmax},
    stocks: [{code, name, x, y, z, cluster_id}]  // 离散股票点
  }

WebSocket /ws/realtime
  Push: { type: "terrain_update", grid: Float32Array, stocks: [...] }  // 每30秒推送
```

---

## 四、渲染引擎方案 (Rendering Engine)

### 4.1 技术栈选型

```
┌─────────────────────────────────────────────────────────┐
│                  RENDERING STACK                        │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ React 19     │  │ Next.js 15   │  │ TailwindCSS 4 │  │
│  │ (UI框架)     │  │ (SSR/路由)    │  │ (样式系统)     │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────────┘  │
│         │                │                              │
│  ┌──────▼────────────────▼──────────────────────────┐   │
│  │        React Three Fiber (R3F) v9                │   │
│  │        ┌─────────────────────────────────┐       │   │
│  │        │  @react-three/drei              │       │   │
│  │        │  (工具组件: OrbitControls, Text, │       │   │
│  │        │   Html, Float, Billboard, etc.) │       │   │
│  │        └─────────────────────────────────┘       │   │
│  │        ┌─────────────────────────────────┐       │   │
│  │        │  @react-three/postprocessing    │       │   │
│  │        │  (后处理: Bloom, SSAO, Vignette)│       │   │
│  │        └─────────────────────────────────┘       │   │
│  │        ┌─────────────────────────────────┐       │   │
│  │        │  Custom GLSL Shaders            │       │   │
│  │        │  (地形着色、热力图、动态高度)      │       │   │
│  │        └─────────────────────────────────┘       │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Zustand (全局状态管理)                            │   │
│  │  • 股票选择状态  • 聚类结果  • 视角控制             │   │
│  │  • 实时行情流    • UI 面板状态                      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 4.2 为什么选 React Three Fiber？

| 对比项 | R3F ⭐ | 原生 Three.js | ECharts-GL | Babylon.js |
|-------|------|-------------|-----------|-----------|
| **React 生态融合** | ⭐⭐⭐⭐⭐ 原生 | ❌ 命令式 | ❌ 配置式 | ❌ |
| **声明式开发** | ✅ JSX描述场景 | ❌ | ⚠️ option式 | ❌ |
| **生态丰富度** | ⭐⭐⭐⭐⭐ drei/pmndrs | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **自定义着色器** | ✅ extend机制 | ✅ 原生 | ❌ 受限 | ✅ |
| **性能** | ⭐⭐⭐⭐⭐ 零开销封装 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **社区活跃度** | ⭐⭐⭐⭐⭐ pmndrs团队 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **适合产品开发** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ 难维护 | ⭐⭐ 不灵活 | ⭐⭐⭐⭐ |

### 4.3 3D 地形渲染方案

#### 核心渲染架构 (三层叠加)

```
Layer 3 (最上层): UI Overlay      — HTML 面板、股票卡片、图表
                                    使用 drei <Html> 组件

Layer 2 (中间层): Stock Nodes     — 离散股票点（发光粒子/标记物）
                                    使用 InstancedMesh (5000+点)

Layer 1 (底层)  : Terrain Surface — 3D 地形曲面
                                    使用 PlaneGeometry + vertex shader
                                    + 自定义热力图着色
```

#### 地形曲面渲染核心技术

```glsl
// 顶点着色器 — 地形高度位移
uniform sampler2D heightMap;      // 128×128 高度纹理 (来自RBF插值)
uniform float heightScale;         // 高度缩放因子
uniform float time;                // 动画时间

varying float vHeight;
varying vec2 vUv;

void main() {
    vUv = uv;
    
    // 从高度图采样
    float height = texture2D(heightMap, uv).r;
    vHeight = height;
    
    // 顶点位移
    vec3 displaced = position;
    displaced.z = height * heightScale;
    
    // 平滑过渡动画
    displaced.z = mix(displaced.z, height * heightScale, 
                      smoothstep(0.0, 1.0, time));
    
    gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
}
```

```glsl
// 片段着色器 — 涨跌热力图着色
varying float vHeight;
varying vec2 vUv;

uniform float zMin;   // 最大跌幅
uniform float zMax;   // 最大涨幅
uniform float zMid;   // 零点

// 股市经典配色：红涨绿跌（A股惯例）
vec3 colorNegative = vec3(0.1, 0.7, 0.3);  // 深绿 (跌)
vec3 colorNeutral  = vec3(0.15, 0.15, 0.2); // 暗灰 (平)
vec3 colorPositive = vec3(0.9, 0.15, 0.15); // 深红 (涨)
vec3 colorHot      = vec3(1.0, 0.3, 0.05);  // 橙红 (涨停)

void main() {
    float t = (vHeight - zMin) / (zMax - zMin); // 归一化到 [0, 1]
    
    vec3 color;
    if (t < 0.45) {
        color = mix(colorNegative, colorNeutral, t / 0.45);
    } else if (t < 0.55) {
        color = colorNeutral;
    } else if (t < 0.9) {
        color = mix(colorNeutral, colorPositive, (t - 0.55) / 0.35);
    } else {
        color = mix(colorPositive, colorHot, (t - 0.9) / 0.1);
    }
    
    // 等高线效果
    float contour = fract(vHeight * 20.0);
    contour = smoothstep(0.0, 0.05, contour) * smoothstep(0.1, 0.05, contour);
    color = mix(color, vec3(1.0), contour * 0.15);
    
    gl_FragColor = vec4(color, 0.95);
}
```

### 4.4 性能优化策略

#### 问题：5000+ 股票节点 + 动态 3D 曲面 = 性能瓶颈

| 优化技术 | 解决问题 | 实现方式 | 性能提升 |
|---------|---------|---------|---------|
| **InstancedMesh** | 5000 个股票节点 | 单 DrawCall 渲染全部节点 | 100x |
| **BufferGeometry** | 地形网格更新 | 直接操作顶点 buffer | 10x |
| **DataTexture** | 高度图传输 | GPU 端直接采样纹理 | 避免CPU瓶颈 |
| **LOD (Level of Detail)** | 远距离细节 | 近处128×128 → 远处32×32 | 4x |
| **Frustum Culling** | 视锥外的节点 | R3F 内置 + 手动标签裁剪 | 2-3x |
| **requestAnimationFrame 节流** | 数据更新频率 | 行情30s刷新，渲染60fps | 稳定帧率 |
| **Web Worker** | 插值计算 | 后台线程计算高度图 | 不阻塞主线程 |
| **Transferable Objects** | Worker 通信 | Float32Array 零拷贝传输 | 消除序列化开销 |

#### InstancedMesh 核心实现思路

```typescript
// 5000 个股票点 → 1 个 DrawCall
// 每个点：位置(x,y,z) + 颜色(涨跌) + 大小(市值) + 透明度(成交量)

// 伪代码示意
<instancedMesh args={[geometry, material, 5000]}>
  {stocks.map((stock, i) => {
    // 通过 matrix 设置每个实例的位置和缩放
    tempMatrix.setPosition(stock.x, stock.y, stock.z);
    tempMatrix.scale(stock.marketCapScale);
    instancedMesh.setMatrixAt(i, tempMatrix);
    
    // 通过 color buffer 设置每个实例的颜色
    instancedMesh.setColorAt(i, getStockColor(stock.pctChg));
  })}
</instancedMesh>
```

### 4.5 视觉设计语言

```
┌─────────────────────────────────────────────────────┐
│                  DESIGN SYSTEM                       │
│                                                      │
│  主题：Dark Mode 为主 (金融终端风格)                    │
│  字体：JetBrains Mono (数据) + Inter (UI文字)          │
│  配色：                                               │
│    背景:    #0A0A0F (深邃太空黑)                        │
│    涨(红):   #E53935 → #FF6D00 (红到橙渐变)             │
│    跌(绿):   #00C853 → #1B5E20 (亮绿到深绿渐变)         │
│    平(灰):   #37474F                                   │
│    强调色:   #00BCD4 (科技青) — 用于选中/交互            │
│    网格线:   #1A1A2E (极暗线条)                         │
│                                                      │
│  3D 地形风格：                                         │
│    - 微发光效果 (Bloom) — 涨停板区域发出暖光              │
│    - 等高线 (Contour Lines) — 半透明白色细线             │
│    - 雾效 (Fog) — 远处地形渐隐，突出焦点区域             │
│    - 环境光遮蔽 (SSAO) — 增强曲面立体感                 │
│                                                      │
│  股票节点：                                            │
│    - 发光粒子球体 (市值越大，球越大)                     │
│    - Hover 时弹出浮动信息卡 (drei <Html>)              │
│    - 涨停 = 金色脉冲发光动画                            │
│    - 跌停 = 深绿色缓慢呼吸动画                          │
└─────────────────────────────────────────────────────┘
```

---

## 五、完整技术栈清单

### 5.1 后端 (Python)

```toml
# pyproject.toml 核心依赖
[project]
name = "stockterrain-engine"
requires-python = ">=3.11"
dependencies = [
    # Web 框架
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "websockets>=13.0",
    
    # 数据采集
    "akshare>=1.14.0",          # 主力数据源
    "baostock>=0.8.8",          # 备选数据源
    "tushare>=1.4.0",           # 补充数据源
    
    # 数据处理
    "pandas>=2.2.0",
    "numpy>=1.26.0",
    "duckdb>=1.1.0",            # 嵌入式分析数据库
    
    # 机器学习/算法
    "scikit-learn>=1.5.0",      # 标准化、PCA
    "hdbscan>=0.8.38",          # 聚类
    "umap-learn>=0.5.6",        # 降维
    "scipy>=1.14.0",            # RBF 插值
    
    # 缓存
    "redis>=5.0.0",
    
    # 调度
    "apscheduler>=3.10.0",      # 定时采集任务
    
    # 工具
    "pydantic>=2.9.0",          # 数据验证
    "loguru>=0.7.0",            # 日志
    "httpx>=0.27.0",            # HTTP 客户端
]
```

### 5.2 前端 (TypeScript + React)

```json
{
  "dependencies": {
    // 核心框架
    "react": "^19.0.0",
    "next": "^15.1.0",
    
    // 3D 渲染
    "@react-three/fiber": "^9.0.0",
    "@react-three/drei": "^10.0.0",
    "@react-three/postprocessing": "^3.0.0",
    "three": "^0.170.0",
    
    // 状态管理
    "zustand": "^5.0.0",
    
    // UI
    "tailwindcss": "^4.0.0",
    "@radix-ui/react-*": "latest",
    "framer-motion": "^11.0.0",
    "lucide-react": "latest",
    
    // 数据
    "swr": "^2.3.0",
    "@tanstack/react-query": "^5.0.0",
    
    // 工具
    "d3-scale": "^4.0.0",
    "d3-interpolate": "^3.0.0"
  }
}
```

---

## 六、演进路线图 (Roadmap)

### Phase 0 — 技术验证 (MVP-0) 「2周」

> **目标**：证明核心技术路径可行

- [ ] AKShare 拉取全 A 股实时行情 → DuckDB 落盘
- [ ] UMAP 对 500 只股票降维到 2D → 控制台输出坐标
- [ ] RBF 插值生成 64×64 高度网格 → 保存为 JSON
- [ ] R3F 渲染一个静态 3D 地形 + 500 个粒子点
- [ ] 手动触发刷新，验证数据 → 渲染完整链路

### Phase 1 — MVP 最小可用产品 「6周」

> **目标**：一个可以日常使用的单用户桌面工具

**核心功能**：
- 全 A 股 5000+ 支股票的 3D 地形可视化
- 自动聚类 + 降维布局，相似股票自然聚合
- Z 轴 = 今日涨幅，实时更新（盘中 30s 刷新）
- 鼠标 hover 显示股票详情卡片
- 点击股票节点查看 K 线弹窗
- 地形旋转/缩放/平移 (OrbitControls)
- 聚类着色（不同板块不同底色区域）

**非核心（不做）**：
- 多用户/账户系统
- 移动端适配
- 历史回溯播放

### Phase 2 — 产品化 (v2.0) 「3个月」

> **目标**：一个值得分享的在线产品

**杀手级功能**：
- 🎬 **时光回溯**：拖动时间轴，地形像波浪一样演绎任意历史日期的涨跌起伏
- 🎯 **自选股宇宙**：用户可自定义股票池，生成专属的 3D 地形
- 📊 **多维切换**：Z 轴可切换为成交量、换手率、资金净流入等指标
- 🏷️ **智能标注**：地形上自动标注"涨停山脉"、"跌停峡谷"等区域
- 🔍 **搜索定位**：搜索股票代码，镜头自动飞行定位到该股票位置
- 📱 **响应式 UI**：侧边栏面板、底部控制条、顶部行情条

### Phase 3 — 平台化 (v3.0) 「6个月+」

> **目标**：成为金融从业者的日常工具

**进阶功能**：
- 🌊 **实时地形动画**：盘中地形持续"呼吸"，像活的地形一样实时形变
- 🤖 **AI 辅助分析**：接入 LLM，对当前地形进行自然语言解读（"今日金融板块形成高原，说明..."）
- 📡 **多市场支持**：港股、美股、ETF、期货等多品种地形图
- 🔗 **因子回测**：自定义聚类因子，回测历史收益
- 🌐 **协作功能**：分享地形快照、标注讨论
- 📊 **专业指标**：Level-2 数据、龙虎榜热力图、北向资金流向河流
- ⚡ **WebGPU 升级**：当 WebGPU 全面普及后，计算着色器在 GPU 端完成插值
- 🏔️ **VR/AR 模式**：WebXR 支持，沉浸式股市地形漫游

---

## 七、项目目录结构

```
stockterrain/
├── README.md
├── docker-compose.yml
│
├── engine/                          # 🔧 后端引擎 (Python)
│   ├── pyproject.toml
│   ├── main.py                      # FastAPI 入口
│   ├── config.py                    # 全局配置
│   │
│   ├── data/                        # 数据引擎
│   │   ├── __init__.py
│   │   ├── collector.py             # 多源数据采集器
│   │   ├── sources/
│   │   │   ├── akshare_source.py    # AKShare 数据源
│   │   │   ├── baostock_source.py   # BaoStock 数据源
│   │   │   ├── tushare_source.py    # Tushare 数据源
│   │   │   └── base.py              # 数据源基类
│   │   ├── cleaner.py               # 数据清洗器
│   │   ├── cache.py                 # Redis 缓存管理
│   │   └── scheduler.py             # 定时采集调度
│   │
│   ├── algorithm/                   # 算法引擎
│   │   ├── __init__.py
│   │   ├── features.py              # 特征工程
│   │   ├── clustering.py            # HDBSCAN 聚类
│   │   ├── projection.py            # UMAP 降维
│   │   ├── interpolation.py         # RBF 曲面插值
│   │   └── pipeline.py              # 算法编排流水线
│   │
│   ├── api/                         # API 层
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── stocks.py            # 股票数据 API
│   │   │   ├── cluster.py           # 聚类 API
│   │   │   ├── terrain.py           # 地形数据 API
│   │   │   └── websocket.py         # WebSocket 实时推送
│   │   ├── schemas.py               # Pydantic 数据模型
│   │   └── dependencies.py          # 依赖注入
│   │
│   ├── storage/                     # 存储层
│   │   ├── __init__.py
│   │   ├── duckdb_store.py          # DuckDB 持久化
│   │   └── redis_cache.py           # Redis 缓存
│   │
│   └── tests/
│       ├── test_collector.py
│       ├── test_algorithm.py
│       └── test_api.py
│
├── web/                             # 🎨 前端渲染引擎 (Next.js)
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   │
│   ├── app/                         # Next.js App Router
│   │   ├── layout.tsx
│   │   ├── page.tsx                 # 主页（3D 地形视图）
│   │   └── globals.css
│   │
│   ├── components/
│   │   ├── canvas/                  # 3D 场景组件
│   │   │   ├── TerrainScene.tsx     # 场景根组件
│   │   │   ├── TerrainMesh.tsx      # 3D 地形曲面
│   │   │   ├── StockNodes.tsx       # 股票节点(InstancedMesh)
│   │   │   ├── StockLabel.tsx       # 股票标签(Billboard)
│   │   │   ├── GridHelper.tsx       # 坐标网格
│   │   │   ├── Atmosphere.tsx       # 环境(光照/雾/天空)
│   │   │   └── CameraController.tsx # 相机控制
│   │   │
│   │   ├── ui/                      # UI 组件
│   │   │   ├── Sidebar.tsx          # 左侧面板
│   │   │   ├── StockCard.tsx        # 股票详情卡片
│   │   │   ├── ClusterLegend.tsx    # 聚类图例
│   │   │   ├── TimelineSlider.tsx   # 时间轴滑块
│   │   │   ├── MetricSelector.tsx   # Z轴指标选择器
│   │   │   └── SearchBar.tsx        # 股票搜索
│   │   │
│   │   └── charts/                  # 2D 图表组件
│   │       ├── MiniKLine.tsx        # 迷你K线
│   │       └── ClusterRadar.tsx     # 聚类雷达图
│   │
│   ├── shaders/                     # GLSL 着色器
│   │   ├── terrain.vert.glsl        # 地形顶点着色器
│   │   ├── terrain.frag.glsl        # 地形片段着色器
│   │   └── stock-node.frag.glsl     # 股票节点发光
│   │
│   ├── stores/                      # Zustand 状态管理
│   │   ├── useStockStore.ts         # 股票数据状态
│   │   ├── useTerrainStore.ts       # 地形状态
│   │   └── useUIStore.ts            # UI 状态
│   │
│   ├── hooks/                       # 自定义 Hooks
│   │   ├── useRealtimeData.ts       # WebSocket 实时数据
│   │   ├── useTerrainCompute.ts     # Web Worker 计算
│   │   └── useStockSearch.ts        # 搜索
│   │
│   ├── workers/                     # Web Workers
│   │   └── terrain.worker.ts        # 高度图计算 Worker
│   │
│   ├── lib/                         # 工具库
│   │   ├── api.ts                   # API 客户端
│   │   ├── interpolation.ts         # 前端插值(应急)
│   │   └── colors.ts                # 颜色映射
│   │
│   └── types/                       # TypeScript 类型
│       ├── stock.ts
│       └── terrain.ts
│
└── data/                            # 📦 本地数据存储
    ├── stockterrain.duckdb          # DuckDB 数据库文件
    └── cache/                       # 文件缓存
```

---

## 八、关键风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|-----|------|------|---------|
| AKShare 接口变动/失效 | 中 | 高 | 三级数据源降级；监控告警；定期回归测试 |
| 东方财富反爬封 IP | 中 | 中 | AKShare 作为中间层已处理；BaoStock 独立源兜底 |
| 5000 节点渲染卡顿 | 低 | 高 | InstancedMesh + LOD + 视锥裁剪 |
| UMAP 降维结果不稳定 | 低 | 中 | 固定 random_state；增量 transform 保持一致性 |
| RBF 插值边缘震荡 | 低 | 低 | smoothing 参数调优；边界 padding |
| 实时数据延迟 | 中 | 中 | Redis 缓存 + 乐观 UI 更新 + 最后更新时间提示 |

---

## 九、第一步：立即可执行的启动计划

```
Day 1-2:  搭建项目脚手架 (monorepo: engine + web)
Day 3-5:  Data Engine: AKShare 全量采集 → DuckDB 落盘 → 特征计算
Day 6-7:  Algorithm: HDBSCAN 聚类 + UMAP 降维 → JSON 输出
Day 8-9:  Algorithm: RBF 插值 → 128×128 高度网格生成
Day 10-12: Rendering: R3F 场景搭建 → 地形曲面渲染 → 自定义着色器
Day 13-14: Integration: FastAPI ↔ R3F 联调 → WebSocket 实时推送
```

---

*"When you can visualize the market as a landscape, you see patterns that numbers alone can never reveal."*

**— StockTerrain 产品哲学**
