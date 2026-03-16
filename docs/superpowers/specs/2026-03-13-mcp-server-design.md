# StockTerrain MCP Server 设计方案

> 日期: 2026-03-13
> 状态: Reviewed

## 目标

将 StockTerrain 后端的数据能力暴露为 MCP (Model Context Protocol) Server，使 Claude Code 等 AI 工具可以直接查询全量市场数据、聚类结构、因子分析、历史回放等，无需通过前端 UI。

## 核心问题

当前 LLM 集成（`engine/llm/context.py`）只向 AI 提供极度压缩的上下文（涨跌前 5 + 8 个簇摘要），而后端实际拥有：

- 5000+ 只股票的完整特征矩阵（12 维数值 + 768 维语义嵌入）
- HDBSCAN 聚类完整结构（特征画像、质量评分、全部成员）
- 13 因子预测模型完整输出（每股上涨概率 + 因子贡献分解）
- ICIR 因子回测结果（IC 时序、显著性、自适应权重）
- DuckDB 多天历史快照
- 跨簇相似度关系图

MCP Server 让 AI 直接触及这些原始数据。

## 架构

```
Claude Code (用户) ←─ MCP (stdio) ─→ StockTerrain MCP Server
                                            │
                      ┌─────────────────────┼─────────────────────┐
                      ▼                     ▼                     ▼
               FastAPI REST API      DuckDB Read-Only        Engine Modules
              (后端在线时优先)       (后端离线时兜底)       (Pipeline/Predictor)
```

### 混合数据访问策略

1. **启动时探测**：MCP Server 启动时 `GET /api/v1/health` 检测后端是否在线
2. **在线模式**：后端运行中 → 通过 REST API 获取运行时数据（聚类结果、UMAP 缓存、预测输出）
3. **离线模式**：后端未运行 → 直接读 DuckDB 历史快照 + 复用 engine 模块做本地计算
4. **自动切换**：在线状态缓存 30 秒，API 调用失败时立即降级为离线模式并重置缓存

### 并发与 DuckDB 安全

- MCP Server 的 DuckDB 连接始终使用 **`read_only=True`** 模式，避免与 FastAPI 后端的写入冲突
- 在线模式下所有写操作（compute_terrain）通过 REST API 委托给后端
- 离线模式为纯只读分析，不修改任何数据

## MCP Tools 定义（10 个 Tool）

### 1. `query_market_overview`

全市场概览快照。

**参数**: 无

**返回**:
- 股票总数、涨跌家数统计（上涨/下跌/平盘）、平均涨跌幅
- 全部聚类列表（cluster_id / size / 语义标签 / 代表股票 Top 3）
- 聚类质量评分（Silhouette / Calinski-Harabasz / 噪声率）
- 涨幅前 10 / 跌幅前 10

**数据源**:
- 在线：`GET /api/v1/health` + 内部新增端点 `GET /api/v1/terrain/summary`（从 Pipeline.last_result 提取）
- 离线：DuckDB 最近一天快照聚合 + `cluster_results` 表

### 2. `search_stocks`

股票搜索（模糊匹配代码或名称）。

**参数**: `query: str`

**返回**: 匹配的股票列表（code / name / 行业 / 涨跌幅 / 所属聚类），最多 20 条

**数据源**:
- 在线：`GET /api/v1/stocks/search?q=xxx`
- 离线：DuckDB 最近快照 `WHERE code LIKE '%xxx%' OR name LIKE '%xxx%'`

### 3. `query_cluster`

查询指定聚类的完整信息。

**参数**: `cluster_id: int`

**返回**: 簇内全部成员股票（code/name/行业/涨跌幅/PE/PB/预测概率）、特征画像（原始特征均值+标准差）、自动语义标签、行业分布 Top 5、簇内 KDTree 邻居关系

**数据源**:
- 在线：从 Pipeline.last_result.clusters + stocks 过滤
- 离线：DuckDB `cluster_results` + `stock_snapshots` 最近快照 + `company_profiles.json`

**错误处理**: cluster_id 不存在 → 返回 "聚类 #{id} 不存在。使用 query_market_overview 查看全部聚类列表。"

### 4. `query_stock`

单股全维度分析。

**参数**: `code: str`

**返回**: 基础行情（价格/涨跌幅/成交量/换手率/PE/PB/市值）、所属聚类 ID + 标签、13 因子分值分解（在线模式）、明日上涨概率 + 置信度（在线模式）、同簇关联 Top 5 + 跨簇相似 Top 5（在线模式）、近 20 日历史数据

**数据源**:
- 在线：Pipeline.last_result 中该股票全部字段
- 离线：DuckDB 最近快照 + 日线历史（注：离线模式无因子分解和预测概率，会明确标注 "离线模式，无法获取预测数据"）

**错误处理**: code 不存在 → 返回 "未找到股票 {code}。可使用 search_stocks 搜索。"

### 5. `query_factor_analysis`

因子体系全景。

**参数**: `factor_name: str | None`（可选，不传返回全部因子概览）

**返回**: 13 因子定义（名称/方向/分组/描述）、当前权重（ICIR 自适应 or 默认）、权重来源标记（"ICIR自适应" / "默认权重"）

**数据源**:
- 在线：`GET /api/v1/factor/weights`（只读，不触发回测计算）
- 离线：从 `predictor_v2.py` 的 `FACTOR_DEFS` 常量读取默认定义

**说明**: 不自动触发 `POST /api/v1/factor/backtest`。如需运行因子回测，使用 `run_backtest` tool。

### 6. `find_similar_stocks`

跨簇相似股票搜索。

**参数**: `code: str`, `top_k: int = 10`

**返回**: 最相似的 top_k 只股票，含距离分数、所属簇、行业、涨跌幅

**数据源**:
- 在线：Pipeline.last_result 中的 similar_stocks + related_stocks 字段（基于 PCA 后的完整特征矩阵，含语义嵌入+数值+技术指标）
- 离线：从 `stock_embeddings.npz` 加载 BGE 嵌入向量 + 余弦相似度搜索（**注意：离线模式仅基于语义嵌入，不含财务/技术特征，结果为近似值**）

**与 `query_stock` 的区别**: `query_stock` 内嵌返回 Top 5 关联+相似预览；`find_similar_stocks` 是专用深度搜索工具，支持自定义 top_k。

### 7. `query_history`

历史行情数据。

**参数**: `code: str`, `days: int = 60`

**返回**: 日线数据（日期/开高低收/成交量/成交额/涨跌幅/换手率）

**数据源**: DuckDB `stock_daily` 表直接查询（在线离线均可，DuckDB read-only 连接）

**错误处理**: 无历史数据 → 返回 "股票 {code} 无本地历史数据。需先运行 compute_terrain 积累数据。"

### 8. `run_screen`

条件选股筛选。

**参数**:
- `filters: dict` — 筛选条件
- `sort_by: str = "pct_chg"` — 排序字段
- `sort_desc: bool = True` — 是否降序
- `limit: int = 20` — 最大返回数（上限 50）

**Filter DSL**:
```
精确匹配:  {"cluster_id": 5}
范围过滤:  {"pe_ttm": {"min": 5, "max": 30}}
集合匹配:  {"cluster_id": {"in": [1, 3, 5]}}

可用字段: code, name, cluster_id, pct_chg, turnover_rate, volume,
         amount, pe_ttm, pb, total_mv, circ_mv, rise_prob, industry
```

**返回**: 满足条件的股票列表（Markdown 表格），含指定排序

**数据源**:
- 在线：Pipeline.last_result.stocks 内存过滤
- 离线：DuckDB 最近快照 SQL 查询

**错误处理**: 无匹配结果 → 返回 "无满足条件的股票。当前筛选条件: {filters}"

### 9. `run_backtest`

触发因子 IC 回测（需要后端在线或 DuckDB 有 ≥3 天历史数据）。

**参数**: `rolling_window: int = 20`, `auto_inject: bool = False`

**返回**: 各因子 IC 均值 / 标准差 / ICIR / 正比率 / t 统计量 / p 值、最近 20 天 IC 时序、ICIR 自适应权重

**数据源**:
- 在线：`POST /api/v1/factor/backtest?auto_inject=false`（默认不注入权重，避免副作用）
- 离线：复用 `engine/algorithm/factor_backtest.py` + DuckDB 历史快照本地计算

**说明**: `auto_inject=False` 默认不修改预测器权重。设为 True 时会将 ICIR 权重注入后端预测器（仅在线模式有效）。

### 10. `compute_terrain`

触发全量地形计算（仅在线模式）。

**参数**: `z_metric: str = "pct_chg"`, `radius_scale: float = 2.0`

**返回**: 计算完成摘要（股票数 / 聚类数 / 耗时 / 聚类质量评分），不返回网格数据

**实现细节**: 调用 `POST /api/v1/terrain/compute`，该端点返回 SSE 流。MCP tool 消费整个 SSE 流，提取 `complete` 事件中的摘要数据，丢弃网格和 progress 事件。

**数据源**: `POST /api/v1/terrain/compute`

**错误处理**:
- 离线模式 → 返回 "后端未运行，无法触发计算。请先启动 engine: `python main.py`"
- 后端返回 429 → 返回 "计算正在进行中，请稍后重试"

## 离线模式能力矩阵

| Tool | 在线 | 离线 | 离线限制 |
|------|------|------|----------|
| query_market_overview | 完整 | 部分 | 无聚类质量评分 |
| search_stocks | 完整 | 完整 | — |
| query_cluster | 完整 | 部分 | 无特征画像/语义标签 |
| query_stock | 完整 | 部分 | 无因子分解/预测概率/相似股票 |
| query_factor_analysis | 完整 | 仅默认定义 | 无 ICIR 自适应权重 |
| find_similar_stocks | 完整(PCA特征) | 近似(BGE嵌入) | 仅语义相似度，无财务特征 |
| query_history | 完整 | 完整 | — |
| run_screen | 完整 | 部分 | 缺少 rise_prob/cluster_id |
| run_backtest | 完整 | 完整(≥3天数据) | — |
| compute_terrain | 完整 | 不可用 | 需后端在线 |

每个 tool 在离线模式下返回数据不完整时，会在输出开头标注 `[离线模式] 部分数据不可用`。

## 错误处理规范

所有 tool 统一错误格式，返回可读文本而非 JSON：

```
❌ [错误类型] 描述
💡 建议操作
```

错误类型:
- `NOT_FOUND`: 资源不存在（附建议：使用 search_stocks 搜索）
- `OFFLINE`: 功能需要后端在线（附建议：启动 engine）
- `NO_DATA`: 无可用数据（附建议：先运行 compute_terrain）
- `BUSY`: 计算进行中（附建议：稍后重试）
- `INVALID_PARAM`: 参数错误（附正确用法示例）

## 文件结构

```
engine/
  mcpserver/              # 命名为 mcpserver 避免与 mcp SDK 包名冲突
    __init__.py
    __main__.py         # python -m mcpserver 入口
    server.py           # MCP Server 主入口（stdio transport）
    tools.py            # 10 个 Tool 实现
    data_access.py      # 混合数据访问层（httpx client + DuckDB read-only）
    formatters.py       # 输出格式化（Markdown 表格 + 摘要文本）
```

## 数据访问层设计

```python
class DataAccess:
    """混合数据访问 — 自动选择 API 或 DuckDB"""

    def __init__(self, api_base: str = "http://localhost:8000"):
        self._api_base = api_base
        self._is_online: bool | None = None  # None = 未检测
        self._online_checked_at: float = 0   # 上次检测时间戳
        self._online_cache_ttl: float = 30.0 # 在线状态缓存 30 秒
        self._store: DuckDBStore | None = None  # read_only=True

    def _ensure_store(self) -> DuckDBStore:
        """懒初始化 DuckDB read-only 连接"""
        if self._store is None:
            self._store = DuckDBStore(read_only=True)
        return self._store

    def is_online(self) -> bool:
        """检查后端是否在线（带 30s 缓存）"""
        now = time.time()
        if self._is_online is not None and (now - self._online_checked_at) < self._online_cache_ttl:
            return self._is_online
        try:
            resp = httpx.get(f"{self._api_base}/api/v1/health", timeout=3.0)
            self._is_online = resp.status_code == 200
        except Exception:
            self._is_online = False
        self._online_checked_at = now
        return self._is_online

    def _on_api_error(self):
        """API 调用失败时重置在线状态缓存"""
        self._is_online = False
        self._online_checked_at = 0
```

**注**: DataAccess 使用同步方法。MCP SDK (stdio transport) 在同步事件循环中运行，DuckDB 也是同步的。httpx 使用同步 client。

## 输出格式化

MCP Tool 返回的内容需要 AI 友好，不是原始 JSON dump。格式化规则：

1. **表格优先**：股票列表用 Markdown 表格
2. **关键数字突出**：涨跌幅带 ± 号和语义标注（"大涨 +8.2%"、"微跌 -0.3%"）
3. **摘要在前**：先给结论性摘要，再给详细数据
4. **数据量控制**：单次返回不超过 50 只股票详情，超出提示用 filter/limit 缩小范围
5. **离线标注**：离线模式下缺失数据明确标注

## 配置

MCP Server 配置写入项目 `.mcp.json` 或用户全局 `~/.claude/settings.json`：

```json
{
  "mcpServers": {
    "stockterrain": {
      "command": "python",
      "args": ["-m", "mcpserver"],
      "cwd": "/path/to/Visualize-A-shares/engine"
    }
  }
}
```

## 依赖

- `mcp` Python SDK（添加到 pyproject.toml dependencies）
- 已有的 engine 模块（DuckDBStore, DataCollector, AlgorithmPipeline 等）
- `httpx`（已在 pyproject.toml 中）

## 不做的事情

- **不**返回地形网格数据（那是给前端 WebGL 渲染的，AI 不需要）
- **不**改动前端 AIChatPanel（那是另一个独立需求）
- **不**做 WebSocket 实时推送（MCP 是请求-响应模式）
- **不**重复实现已有算法逻辑（复用 engine 模块）
- **不**支持 MCP 写入 DuckDB（MCP 侧始终 read-only）
