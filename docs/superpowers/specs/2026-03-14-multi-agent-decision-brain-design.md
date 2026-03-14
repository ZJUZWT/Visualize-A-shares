# Multi-Agent 智能投研决策大脑 — 架构设计 Spec

> **定位：** 本 spec 是 StockTerrain 平台的 AI 决策层设计，覆盖 Agent 编排、引擎扩展、Memory 系统、MCP 工具扩展。
> **前置依赖：** `2026-03-14-multi-engine-roadmap.md`（四引擎路线图）、`2026-03-14-data-cluster-engine-separation-design.md`（Data/Cluster 分离）
> **架构模式：** 渐进式并行聚合 — 预检短路 + 三维度并行分析 + 加权聚合 + 可选专家层

---

## 1. 系统分层

```
┌─────────────────────────────────────────────────┐
│  触发层 Trigger                                    │
│  用户主动 · 定时批量 · 事件驱动                       │
└─────────────────┬───────────────────────────────┘
                  │ AnalysisRequest
                  ▼
┌─────────────────────────────────────────────────┐
│  Agent 编排层 Orchestrator                         │
│  PreScreen → 并行(基本面/消息面/技术面) → 聚合 → 专家  │
└─────────────────┬───────────────────────────────┘
                  │ MCP Tool 调用
                  ▼
┌─────────────────────────────────────────────────┐
│  MCP 工具层                                       │
│  18 tools（现有 10 + 新增 8）                       │
│  按 Agent 角色白名单限制可访问工具                     │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  引擎层 Engines                                    │
│  DataEngine · ClusterEngine · InfoEngine · QuantEngine │
│  每个引擎绑定独立 DuckDB schema                      │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  存储层 Storage                                    │
│  DuckDB (结构化事实) + ChromaDB (Agent 推理记忆)     │
│  逻辑隔离: 每引擎独立 schema / collection             │
└─────────────────────────────────────────────────┘
```

## 2. Agent 角色定义

### 2.1 六个 Agent

| Agent | 职责 | 触发条件 | 输出 |
|-------|------|---------|------|
| PreScreen | 读取最新消息 + 快照，判断是否有重大事件需短路 | 每次分析请求的第一步 | `PreScreenResult` |
| Fundamental | 基本面分析：财务健康、估值、盈利质量 | PreScreen 放行后并行 | `AgentVerdict` |
| Info | 消息面分析：新闻情感、公告影响、舆情 | PreScreen 放行后并行 | `AgentVerdict` |
| Quant | 技术面分析：指标信号、多因子评分、动量 | PreScreen 放行后并行 | `AgentVerdict` |
| Aggregator | 加权聚合三份 Verdict，冲突检测，生成报告 | 三个分析 Agent 完成后 | `AggregatedReport` |
| Expert | 深度解读，交叉引用全部数据 | 用户点击"深度解读"（可选） | 个性化报告 |

### 2.2 Agent 人格定义

```python
AGENT_PERSONAS = {
    "fundamental": {
        "role": "基本面分析师",
        "perspective": "价值投资视角，关注财务健康、盈利质量、估值合理性",
        "bias": "偏保守，高 P/E 会降低信心",
        "risk_tolerance": 0.3,         # 0-1，越低越保守
        "confidence_calibration": 0.8, # 历史准确率校准系数（动态更新）
        "forbidden_factors": ["舆情", "技术指标", "资金流向"],
    },
    "info": {
        "role": "消息面分析师",
        "perspective": "事件驱动视角，关注信息不对称和市场预期差",
        "bias": "对利空敏感，宁可错杀不可放过",
        "risk_tolerance": 0.5,
        "confidence_calibration": 0.6,
        "forbidden_factors": ["PE", "ROE", "MACD"],
    },
    "quant": {
        "role": "量化技术分析师",
        "perspective": "纯数据驱动，关注统计规律和动量",
        "bias": "中性，只看数字",
        "risk_tolerance": 0.7,
        "confidence_calibration": 0.7,
        "forbidden_factors": ["新闻", "公告", "行业政策"],
    },
}
```

### 2.3 人格稳定性三板斧

1. **无状态调用** — 每次分析请求创建新的 LLM 调用，完整重注入 system prompt + persona，杜绝对话累积导致的人格漂移
2. **Memory 隔离** — 每个 Agent 只能读写自己的 ChromaDB collection，不被其他角色的推理记忆交叉污染
3. **Tool 白名单** — 每个 Agent 只能调用被允许的 MCP tools，物理上隔离信息来源，防止角色越界

## 3. 接口契约

### 3.1 请求与响应

```python
class AnalysisRequest:
    trigger_type: Literal["user", "schedule", "event"]
    target: str                    # "600519" or "白酒"
    target_type: Literal["stock", "sector", "market"]
    depth: Literal["quick", "standard", "deep"]
    user_context: dict | None      # 用户附加上下文
    event_payload: dict | None     # 事件驱动时的事件数据

class AgentVerdict:
    agent_role: str                # "fundamental" | "info" | "quant"
    signal: Literal["bullish", "bearish", "neutral"]
    score: float                   # -1.0 ~ 1.0
    confidence: float              # 0.0 ~ 1.0
    evidence: list[Evidence]       # 支撑论据（含多空双方）
    risk_flags: list[str]          # 风险提示
    metadata: dict                 # 扩展字段

class Evidence:
    factor: str                    # 因子名称
    value: str                     # 当前值描述
    impact: Literal["positive", "negative", "neutral"]
    weight: float                  # 该因子权重

class AggregatedReport:
    target: str
    overall_signal: Literal["bullish", "bearish", "neutral"]
    overall_score: float           # 加权综合评分
    verdicts: list[AgentVerdict]   # 三份原始 Verdict
    conflicts: list[str]           # 多空冲突描述
    summary: str                   # 一段话总结
    risk_level: Literal["low", "medium", "high"]
    timestamp: datetime

class PreScreenResult:
    should_continue: bool          # False = 短路，直接输出
    reason: str | None             # 短路原因
    critical_events: list[dict]    # 重大事件列表
    fast_verdict: AggregatedReport | None  # 短路时的快速报告
```

### 3.2 Agent 输出规范

每个分析 Agent 的 Verdict 必须**同时包含多头和空头论据**（取代独立牛熊辩论机制）。`evidence` 列表中，`impact: "positive"` 为看多因素，`impact: "negative"` 为看空因素。Aggregator 通过对比各 Agent 的 signal 方向和 confidence 进行冲突检测。

## 4. Memory 与存储架构

### 4.1 设计原则

- **逻辑隔离，物理共享** — 一个 DuckDB 文件用 schema 隔离，一个 ChromaDB 实例用 collection 隔离
- 好处：部署简单（单文件），但各引擎/Agent 数据互不干扰
- 聚合层只读取各引擎的输出表，不碰引擎内部 Memory

### 4.2 DuckDB Schema 布局

```
stockterrain.duckdb
├── shared.                      # 跨引擎共享
│   ├── analysis_requests        # 分析请求日志
│   ├── analysis_reports         # 聚合报告存档
│   └── agent_performance        # 各 Agent 历史准确率（驱动 calibration）
├── data.                        # DataEngine（已有）
│   ├── stock_daily
│   ├── stock_snapshot
│   └── stock_features
├── cluster.                     # ClusterEngine（已有）
│   └── cluster_results
├── info.                        # InfoEngine（新建）
│   ├── news_articles            # 财经新闻
│   ├── announcements            # 公司公告
│   └── event_impacts            # 事件影响评估缓存
└── quant.                       # QuantEngine（新建）
    ├── technical_indicators     # 技术指标时序
    ├── factor_scores            # 多因子打分
    └── signal_history           # 历史信号记录
```

### 4.3 ChromaDB Collection 布局

```
ChromaDB (embedded, persist_directory="data/chromadb/")
├── memory_fundamental           # 基本面 Agent 推理记忆
├── memory_info                  # 消息面 Agent 推理记忆
├── memory_quant                 # 量化 Agent 推理记忆
├── memory_aggregator            # 聚合 Agent 决策记忆
└── memory_expert                # 专家 Agent 深度分析记忆
```

每条记忆的 metadata 结构：

```python
{
    "agent_role": "fundamental",
    "target": "600519",
    "signal": "bullish",
    "confidence": 0.82,
    "timestamp": "2026-03-14T10:30:00",
    "was_correct": None,         # T+N 后回填
    "calibration_weight": 0.8,   # 动态调整
}
```

### 4.4 Agent Performance 追踪（人格校准闭环）

`shared.agent_performance` 表：

```sql
CREATE TABLE shared.agent_performance (
    id                INTEGER PRIMARY KEY,
    agent_role        VARCHAR,       -- fundamental / info / quant
    target            VARCHAR,       -- 股票代码
    signal            VARCHAR,       -- bullish / bearish / neutral
    score             DOUBLE,        -- -1.0 ~ 1.0
    confidence        DOUBLE,        -- 0.0 ~ 1.0
    created_at        TIMESTAMP,
    -- T+N 回填字段
    actual_return_1d  DOUBLE,        -- 次日实际涨跌幅
    actual_return_5d  DOUBLE,        -- 5日涨跌幅
    was_correct       BOOLEAN,       -- signal 方向是否正确
    calibration_score DOUBLE         -- 校准分 = 历史滚动准确率
);
```

Aggregator 每次聚合时读取各 Agent 近 30 天 `calibration_score`，作为加权系数。准确率低的 Agent 权重自动降低。

## 5. Engine 接口与 MCP 扩展

### 5.1 引擎统一基类

```python
class BaseEngine:
    def __init__(self, db: DuckDBStore, schema: str):
        """每个引擎绑定自己的 DuckDB schema"""

    async def health_check(self) -> bool
    async def refresh(self, targets: list[str]) -> dict
        """拉取/更新数据，返回 {updated: int, failed: int}"""
```

### 5.2 四引擎查询接口

```
DataEngine (data.*)
├── get_stock_info(code) → 基础信息
├── get_daily_history(code, days) → K线数据
└── get_latest_snapshot(code) → 实时快照

ClusterEngine (cluster.*)
├── get_cluster_for_stock(code) → 所属聚类
├── get_cluster_members(cluster_id) → 同类股票
└── get_terrain_data() → 3D地形全量

InfoEngine (info.*)                ← 新建
├── get_news(code, days) → 相关新闻
├── get_announcements(code, days) → 公司公告
└── assess_event_impact(code, event) → 事件影响评估

QuantEngine (quant.*)              ← 新建
├── get_technical_indicators(code) → MACD/RSI/布林等
├── get_factor_scores(code) → 多因子评分
└── get_signal_history(code, days) → 历史信号
```

### 5.3 MCP Tool 扩展（10 → 18）

现有 10 个 tools 保持不变，新增 8 个：

| Tool | 引擎 | 用途 |
|------|------|------|
| `get_news` | InfoEngine | 获取个股/行业相关新闻 |
| `get_announcements` | InfoEngine | 获取上市公司公告 |
| `assess_event_impact` | InfoEngine | 评估事件对股价的潜在影响 |
| `get_technical_indicators` | QuantEngine | 获取技术指标 |
| `get_factor_scores` | QuantEngine | 获取多因子评分 |
| `get_signal_history` | QuantEngine | 获取历史买卖信号 |
| `submit_analysis_request` | Orchestrator | 提交分析请求，触发 Agent 流水线 |
| `get_analysis_history` | Orchestrator | 查询历史分析报告 |

### 5.4 Agent ↔ Tool 白名单

```python
AGENT_TOOL_ACCESS = {
    "prescreen":    ["get_news", "get_announcements", "get_latest_snapshot"],
    "fundamental":  ["get_stock_info", "get_daily_history", "get_factor_scores"],
    "info":         ["get_news", "get_announcements", "assess_event_impact"],
    "quant":        ["get_technical_indicators", "get_factor_scores",
                     "get_signal_history", "get_cluster_for_stock"],
    "aggregator":   ["get_analysis_history"],
    "expert":       ["get_stock_info", "get_daily_history", "get_latest_snapshot",
                     "get_news", "get_announcements", "assess_event_impact",
                     "get_technical_indicators", "get_factor_scores",
                     "get_signal_history", "get_cluster_for_stock",
                     "get_cluster_members", "get_analysis_history"],
}
```

## 6. 编排流程

### 6.1 Orchestrator 主流程

```
orchestrator.analyze(request: AnalysisRequest)
│
├─ 1. 构建上下文
│     读 shared.agent_performance → 各 Agent 近30天准确率
│     读 ChromaDB memory_aggregator → 该股近期分析记忆
│
├─ 2. PreScreen（短路检查）
│     注入: persona + [get_news, get_announcements, get_latest_snapshot]
│     输出: PreScreenResult
│     if not should_continue → 直接返回 fast_verdict, 结束
│
├─ 3. 并行分析（asyncio.gather）
│     ┌─ Fundamental Agent
│     │   注入: persona + calibration_weight + 专属 tools
│     │   读: data.* + memory_fundamental
│     │   输出: AgentVerdict
│     ├─ Info Agent
│     │   注入: persona + calibration_weight + 专属 tools
│     │   读: info.* + memory_info
│     │   输出: AgentVerdict
│     └─ Quant Agent
│         注入: persona + calibration_weight + 专属 tools
│         读: quant.* + memory_quant
│         输出: AgentVerdict
│
├─ 4. 聚合
│     Aggregator 接收三份 AgentVerdict
│     加权: score × confidence × calibration_weight
│     冲突检测: 若多空分歧 > 阈值 → 标记 conflicts
│     输出: AggregatedReport
│
├─ 5. 持久化
│     写 shared.analysis_reports ← 报告存档
│     写 shared.agent_performance ← 各 Agent 本次预测记录
│     写 ChromaDB memory_* ← 各 Agent 推理记忆
│
├─ 6. 返回结果
│     默认: AggregatedReport → 前端渲染
│     若用户请求深度解读:
│       Expert Agent 读 AggregatedReport + 全部只读 tools
│       输出: 个性化深度报告
│
└─ 7. T+N 回填（异步定时任务）
      检查历史预测 vs 实际涨跌
      更新 was_correct, calibration_score
      动态调整各 Agent 的 calibration_weight
```

### 6.2 三种触发模式

```
用户主动触发（Phase 1 首先实现）
├── 前端点击"AI 分析" → POST /api/analysis
├── MCP tool: submit_analysis_request
└── 参数: target, depth="standard"

定时批量触发（Phase 2）
├── APScheduler / cron
├── 每日收盘后扫描自选股列表
└── 参数: target_list, depth="quick"

事件驱动触发（Phase 3）
├── InfoEngine 检测到重大公告/异动
├── 自动触发相关个股分析
└── 参数: target, depth="standard", event_payload={...}
```

三种模式共用同一个 `orchestrator.analyze()` 入口，只是 `trigger_type` 不同。

### 6.3 SSE 流式推送

分析过程通过 SSE 实时推送前端：

```
event: phase       → {"step": "prescreen", "status": "running"}
event: phase       → {"step": "prescreen", "status": "done", "result": "continue"}
event: phase       → {"step": "parallel_analysis", "status": "running",
                       "agents": ["fundamental", "info", "quant"]}
event: agent_done  → {"agent": "quant", "signal": "bullish", "confidence": 0.75}
event: agent_done  → {"agent": "fundamental", "signal": "neutral", "confidence": 0.6}
event: agent_done  → {"agent": "info", "signal": "bearish", "confidence": 0.8}
event: phase       → {"step": "aggregation", "status": "running"}
event: result      → {"report": { ...AggregatedReport... }}
```

## 7. LLM 调用策略

- **单 provider，prompt 切角色** — 所有 Agent 共用一个 LLM API，通过 system prompt 区分角色
- **无状态调用** — 每次分析请求创建新的 LLM 调用，不维护对话历史
- **Tool 注册按白名单** — 每个 Agent 调用 LLM 时只注册被允许的 tools
- **JSON mode 输出** — 所有 Agent 要求返回结构化 JSON（AgentVerdict / PreScreenResult）
- **temperature 设置** — 分析 Agent 用低温（0.1-0.3）保持一致性，Expert 用中温（0.5-0.7）增加可读性

## 8. 实施分期

### Phase 1 — MVP（最小可用）

- QuantEngine 实现（技术指标 + 多因子评分）
- Orchestrator 编排核心（PreScreen + 并行 + 聚合）
- Agent Persona 定义 + Tool 白名单
- ChromaDB Memory 基础读写
- 用户主动触发 → SSE 流式返回
- 前端"AI 分析"按钮 + 结果渲染
- **交付标准：** 点击按钮 → 3-5s 内返回三维度聚合报告

### Phase 2 — 信息引擎 + 记忆闭环

- InfoEngine 实现（新闻爬取 + 公告解析）
- PreScreen 短路逻辑生效
- T+N 回填任务 → calibration_weight 动态调整
- 定时批量触发（自选股列表）
- **交付标准：** 系统能自主学习哪个 Agent 更准

### Phase 3 — 高级功能

- 事件驱动触发
- Expert Agent 深度解读
- 前端多轮对话式交互
- **交付标准：** 重大公告自动推送分析

## 9. YAGNI 边界（不做的事）

- 不做多 LLM provider 切换 — 单 provider，prompt 切角色
- 不做实时行情 WebSocket — 现有快照轮询够用
- 不做用户权限系统 — 单用户场景
- 不做 Agent 对话式辩论 — 用结构化 Verdict 含多空论据替代
- 不做独立微服务部署 — 全部跑在一个 FastAPI 进程内
- 不做独立牛熊 Agent — 每个分析 Agent 自身同时输出多空论据
