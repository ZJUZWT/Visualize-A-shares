# 📋 StockScape TODO — 专家系统演进计划

> 最后更新: 2026-03-19
>
> 优先级：🔴 高 🟡 中 🟢 低

---

## 一、🔴 Main Agent 完整系统（独立页面 + 虚拟持仓 + 策略大脑）

> **核心理念**：不是一个聊天机器人，是一个**有自主意志的投资AI**。
> 它有强烈的欲望去获取数据、验证假设、坚持或修正自己的策略。
> 用户要能清晰看见 AI 的**思考过程、策略演化、持仓变动、进化轨迹**。
>
> 前端路由：`/agent` — 独立于 `/expert` 对话页面

### 1.1 前端：Agent 专属页面 (`/agent`)

三栏布局，让 AI 的"大脑"完全透明：

```
┌─────────────────────────────────────────────────────────────────┐
│ NavSidebar │          Main Agent 控制台                          │
│            │                                                     │
│  🏠 首页   │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  │
│  💬 对话   │  │  对话面板  │  │  策略大脑面板  │  │  虚拟持仓面板 │  │
│  🧠 Agent  │  │           │  │              │  │              │  │
│  🔗 产业链 │  │  与AI讨论  │  │ 当前策略状态  │  │ 持仓列表     │  │
│  📊 板块   │  │  策略制定  │  │ 信念图谱     │  │ 实时盈亏     │  │
│  ⚔️ 辩论  │  │  交易指令  │  │ 决策日志     │  │ 交易记录     │  │
│  ⏰ 任务   │  │           │  │ 自我反思     │  │ 操作策略     │  │
│            │  │           │  │              │  │ 收益曲线     │  │
│            │  └──────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

- [ ] **左栏：Agent Chat** — 与 AI 讨论策略
  - 复用 ChatArea 组件但接入 Main Agent（非普通专家）
  - 对话中 AI 提出的操作策略自动解析为"策略卡片"
  - 策略卡片包含：标的、方向、进场价、止损位、止盈位、仓位比例
  - 用户可以一键"采纳"→ 写入虚拟持仓，或"否决"→ AI 记住被否决的原因
- [ ] **中栏：Strategy Brain** — AI 大脑透明化
  - **当前策略状态**：大盘观点（牛/熊/震荡）、仓位水平（轻/中/重）、行业偏好
  - **信念列表**：AI 当前持有的所有信念 + 置信度进度条（可点击看演化历史）
  - **决策日志 Timeline**：每一次买卖决策的完整思考链
    - 触发原因 → 数据依据 → 各专家意见 → 最终判断 → 执行结果
  - **自我反思记录**：AI 定期回顾后生成的反思文本
  - **策略演化图**：时间轴展示 AI 策略的变迁（从"进攻型"到"防御型"等）
- [ ] **右栏：Virtual Portfolio** — 虚拟持仓管理
  - **持仓列表卡片**：每只股票一张卡片，按 holding_type 分组展示
    - 顶部标签：`📅长线` `📊中线` `⚡短线` `🔄做T`
    - 通用：代码/名称、成本、现价、盈亏%、仓位占比
    - 长线卡片重点显示：基本面锚点、产业周期位置、离场条件
    - 中线卡片重点显示：趋势指标、加仓位/减仓位、催化剂
    - 短线卡片重点显示：预计持有天数、次日计划、量能条件
    - 做T卡片重点显示：底仓数量、今日T次数、高抛/低吸价位
    - 策略执行状态指示灯（🟢 正常 🟡 接近阈值 🔴 触发）
  - **交易记录表**：时间 | 操作(买/卖) | 标的 | 价格 | 数量 | 理由
  - **账户概览**：总资产、总盈亏、持仓占比饼图、收益率曲线
  - **历史回溯**：选择某一天，查看当时 AI 给的策略 vs 实际发生了什么

### 1.2 后端：Main Agent 核心 (`backend/engine/agent/`)

> 独立于 `expert/` 目录，是一个更高级别的 Agent。

#### 1.2.1 数据模型

```python
# ── 虚拟持仓 ──
class Position(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    direction: Literal["long", "short"]     # 做多/做空
    holding_type: Literal[                   # ← 核心字段：持仓类型
        "long_term",    # 长线（周期数月~数年，看基本面+产业周期）
        "mid_term",     # 中线（周期数周~数月，看趋势+催化剂）
        "short_term",   # 短线（周期数天，看技术面+资金博弈）
        "day_trade",    # 做T（日内高抛低吸，不改变底仓）
    ]
    entry_price: float                       # 建仓均价
    current_qty: int                         # 当前持有数量
    core_qty: int = 0                        # 底仓数量（做T时不动的部分）
    entry_date: str                          # 建仓日期
    entry_reason: str                        # 买入理由（AI 生成）

class PositionStrategy(BaseModel):
    """AI 对某个持仓的操作策略 — 按持仓类型有完全不同的策略逻辑"""
    position_id: str
    holding_type: str                        # 冗余存一份，方便查询

    # ── 通用字段 ──
    take_profit_price: float | None          # 止盈价
    stop_loss_price: float | None            # 止损价
    reasoning: str                           # 完整策略推理
    created_at: str
    updated_at: str

    # ── 长线策略专属 ──
    # "只要产业逻辑不变就拿着，除非跌破XX或出现行业拐点"
    fundamental_anchor: str | None           # 基本面锚点（"硅料产能出清完成"）
    exit_condition: str | None               # 离场条件（"行业景气见顶信号"）
    rebalance_trigger: str | None            # 调仓触发（"季报低于预期则减仓1/3"）

    # ── 中线策略专属 ──
    # "趋势走好就拿，破趋势就走"
    trend_indicator: str | None              # 跟踪指标（"20日均线" / "MACD周线"）
    add_position_price: float | None         # 加仓价（"回踩XX支撑加仓"）
    half_exit_price: float | None            # 减仓一半的价格
    target_catalyst: str | None              # 期待的催化剂（"Q2业绩超预期"）

    # ── 短线策略专属 ──
    # "打板进、次日竞价不及预期就出"
    hold_days: int | None                    # 预计持有天数
    next_day_plan: str | None                # 次日计划（"高开3%以上减半，低开直接走"）
    volume_condition: str | None             # 量能条件（"缩量则离场"）

    # ── 做T策略专属 ──
    # "底仓不动，日内高抛低吸赚差价"
    t_core_qty: int | None                   # 底仓股数（做T时不卖的部分）
    t_buy_price: float | None                # T的低吸价
    t_sell_price: float | None               # T的高抛价
    t_indicator: str | None                  # 做T参考指标（"分时均线" / "5分钟MACD"）
    t_daily_limit: int | None                # 每日最多做几次T

class Trade(BaseModel):
    """交易记录 — 每笔交易必须有完整理由，禁止无意义操作"""
    id: str
    position_id: str
    action: Literal["buy", "sell", "add", "reduce", "t_buy", "t_sell"]
    price: float
    quantity: int

    # ── 理由链（全部必填，AI 不写清楚就不允许下单）──
    reason: str                              # 一句话理由（"硅料价格企稳，产业拐点确认"）
    thesis: str                              # 交易论点（"为什么现在做这个操作"）
    data_basis: list[str]                    # 数据依据（["硅料价格连续3周持平", "通威Q1预增30%"]）
    risk_note: str                           # 风险提示（"如果硅料再跌10%则论点失效"）
    invalidation: str                        # 什么情况下证明这笔操作是错的

    triggered_by: str                        # "manual" | "strategy" | "agent"
    timestamp: str

    # ── 事后回填（每日复盘时填写）──
    review_result: str | None = None         # "correct" / "wrong" / "pending"
    review_note: str | None = None           # 复盘评语（"买早了，应该等放量确认"）
    review_date: str | None = None           # 复盘日期
    pnl_at_review: float | None = None       # 复盘时的盈亏%

class StrategySnapshot(BaseModel):
    """AI 策略快照 — 某个时间点 AI 的完整策略状态"""
    id: str
    market_view: str                         # "bullish" / "bearish" / "neutral"
    market_view_reasoning: str
    position_level: float                    # 建议仓位水平 0~1
    sector_preferences: list[dict]           # [{sector, weight, reason, cycle_position, waiting_signal}]
    risk_alerts: list[str]                   # 当前风险提醒
    industry_insights: list[dict]            # [{sector, cycle, evidence, next_catalyst}]
    created_at: str

class DecisionLog(BaseModel):
    """决策日志 — 每次买卖决策的完整思考链"""
    id: str
    trigger: str                             # "止盈价到达" / "盘中异动" / "信号触发" / "定时检查"
    industry_context: dict | None            # 产业链上下文（当时查到的上下游关系和周期判断）
    data_gathered: list[dict]                # 收集了哪些数据
    expert_opinions: list[dict]              # 各专家意见
    reasoning: str                           # AI 的完整推理过程
    decision: str                            # 最终决策（"卖出一半" / "继续持有"）
    outcome: str | None                      # 事后回填：决策结果
    created_at: str
```

#### 1.2.2 Main Agent 核心循环

```
定时触发（每10min/30min/每日开盘）
    │
    ▼
┌─ Agent Wake Up ─────────────────────────────────────────┐
│                                                          │
│  1. 检查持仓状态                                         │
│     - 拉取所有持仓标的的最新行情（DataEngine 直接调用）    │
│     - 计算每只票距离止盈/止损/减仓价的距离               │
│                                                          │
│  2. 产业链认知刷新（非每次，每日1-2次或手动触发）         │
│     - 对持仓涉及的行业调用 IndustryEngine.analyze()      │
│     - 判断产业周期位置 → 更新 StrategySnapshot           │
│     - 更新"等待信号清单"（新增/过期/已触发）             │
│                                                          │
│  3. 信号扫描（轻量，每次都做）                            │
│     - 遍历 watch_signals 表中 status='watching' 的信号    │
│     - 用 InfoEngine 快速检索关键词命中                    │
│     - 命中 → 标记 triggered → 进入深度分析               │
│                                                          │
│  4. 主动数据渴求（"我需要知道更多"）                      │
│     - 持仓票有异动？→ 查新闻、查资金流、查技术指标        │
│     - 关注列表有机会？→ 查行业数据、查龙头异动            │
│     - 宏观有变化？→ 查政策、查北向、查汇率                │
│                                                          │
│  5. 策略评估                                              │
│     - 当前策略还成立吗？（用新数据验证之前的逻辑）         │
│     - 产业周期判断有没有变化？                            │
│     - 等待的信号触发了吗？该行动了吗？                    │
│     - 需不需要调整止盈止损位？                            │
│                                                          │
│  6. 决策 & 记录                                           │
│     - 生成 DecisionLog（完整思考链，含产业链上下文）       │
│     - 如果需要操作 → 生成 Trade 建议 → 推送通知           │
│     - 如果不需要 → 记录"继续持有，理由是..."              │
│                                                          │
│  7. 每日复盘（收盘后 15:10 自动触发）                        │
│                                                          │
│     ┌─ 逐笔交易回顾 ──────────────────────────┐          │
│     │                                          │          │
│     │ 遍历今日所有 Trade 记录：                 │          │
│     │                                          │          │
│     │ 对每笔交易，AI 必须回答：                │          │
│     │ ① 这笔操作的论点(thesis)还成立吗？       │          │
│     │ ② 买入/卖出的时机对不对？早了还是晚了？   │          │
│     │ ③ 有没有当时没注意到的信息？              │          │
│     │    - 产业链上有没有遗漏的关联？           │          │
│     │    - 资金面有没有忽略的信号？              │          │
│     │    - 消息面有没有漏看的新闻？              │          │
│     │ ④ 如果重来一次，会做什么不同？            │          │
│     │                                          │          │
│     │ → 回填 Trade.review_result/review_note   │          │
│     └──────────────────────────────────────────┘          │
│                                                          │
│     ┌─ 策略审计 ──────────────────────────────┐          │
│     │                                          │          │
│     │ 审视所有活跃的 PositionStrategy：         │          │
│     │                                          │          │
│     │ ① 止盈止损位设得合不合理？               │          │
│     │    （对比今日实际波动幅度）                │          │
│     │ ② 长线票的基本面锚点有没有变？           │          │
│     │ ③ 中线票跟踪的趋势指标是否失效？         │          │
│     │ ④ 短线票的持有天数超了吗？               │          │
│     │ ⑤ 做T的票今天T成功率如何？               │          │
│     │                                          │          │
│     │ → 需要修改的策略自动生成新版本(version+1)│          │
│     └──────────────────────────────────────────┘          │
│                                                          │
│     ┌─ 认知更新 ──────────────────────────────┐          │
│     │                                          │          │
│     │ AI 自问自答：                             │          │
│     │                                          │          │
│     │ "今天有没有让我意外的事？"                │          │
│     │ → 有 → 分析原因 → 更新信念图谱           │          │
│     │                                          │          │
│     │ "我的产业链认知有没有盲区？"              │          │
│     │ → 比如：没注意到A公司切入了B赛道          │          │
│     │ → 比如：上游原材料价格变化没有跟踪到      │          │
│     │ → 更新关注列表 + WatchSignal              │          │
│     │                                          │          │
│     │ "我的策略体系有没有系统性问题？"          │          │
│     │ → 统计近7天 Trade.review_result          │          │
│     │ → 如果 wrong > 50% → 策略可能有问题      │          │
│     │ → 生成具体的策略修正建议                  │          │
│     │                                          │          │
│     │ → 生成 DailyReflection 写入 reflections 表│         │
│     └──────────────────────────────────────────┘          │
│                                                          │
│  8. 周度深度反思（每周五收盘后）                           │
│     - 本周所有交易的胜率、盈亏比                          │
│     - 各持仓类型(长/中/短/T)分别表现如何                  │
│     - 哪些认知更新是对的？哪些是过度修正？                │
│     - 产业周期判断的准确率                                │
│     - 生成 WeeklyReflection                              │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

#### 1.2.3 产业链认知层 — 让 AI 像交易员一样"懂产业"

> **核心设计原则**：产业链图谱不进长期记忆，而是作为**实时查询工具**。
> AI 不"记住"产业链关系（怕学歪），而是每次需要时**去查**最新的图谱。
> 就像人类交易员手边放着行业研报，但不死记硬背——因为产业格局会变。

```
产业链认知的三层架构：

┌─ Layer 1: 产业链图谱（只读参考，不写入 Agent 记忆）──────────┐
│                                                                │
│  现有的 chain_agent.py 构建的 force-directed graph             │
│  节点：公司、原材料、产品、宏观指标                             │
│  边：upstream/downstream/供应/消耗                              │
│                                                                │
│  Main Agent 通过 IndustryEngine.analyze(sector) 查询           │
│  不缓存结果到知识图谱，每次都查最新的                          │
│                                                                │
└────────────────────────────────────────────────────────────────┘
          │ 查询
          ▼
┌─ Layer 2: 产业周期判断（写入 Agent 策略快照）─────────────────┐
│                                                                │
│  AI 基于产业链数据 + 行业数据，判断：                          │
│                                                                │
│  📍 这个产业目前处于什么位置？                                 │
│     - 景气上行期（量价齐升、订单爆满、扩产加速）               │
│     - 景气顶部（产能过剩苗头、价格涨不动、库存堆积）           │
│     - 景气下行期（价格战、亏损面扩大、企业出清中）             │
│     - 景气底部（出清完成、龙头逆势扩张、等待需求恢复）         │
│                                                                │
│  🎯 当前应该等待什么信号？                                     │
│     - 景气底部 → 等"需求拐点"（如新能源车销量环比回升）        │
│     - 企业出清中 → 等"尾部企业退出"（如光伏小厂破产新闻）     │
│     - 政策预期 → 等"政策落地"（如碳交易细则出台）              │
│     - 技术突破 → 等"量产验证"（如固态电池良率突破）            │
│                                                                │
│  这些判断写入 StrategySnapshot.sector_preferences              │
│  格式：{sector, cycle_position, waiting_signal, trigger_action} │
│                                                                │
└────────────────────────────────────────────────────────────────┘
          │ 监控信号
          ▼
┌─ Layer 3: 信号触发机制（融入盘中循环）────────────────────────┐
│                                                                │
│  Agent 维护一个 "等待信号清单" (WatchList)：                    │
│                                                                │
│  {                                                             │
│    "signal": "光伏硅料价格企稳反弹",                           │
│    "check_method": "info",    ← 通过资讯引擎检测               │
│    "keywords": ["硅料", "价格", "反弹", "企稳"],               │
│    "related_positions": ["通威股份", "隆基绿能"],              │
│    "if_triggered": "考虑建仓光伏龙头，仓位5%",                 │
│    "confidence_threshold": 0.7,                                │
│    "created_at": "2026-03-19",                                 │
│    "status": "watching"     ← watching / triggered / expired   │
│  }                                                             │
│                                                                │
│  盘中轻量检查时：扫描新闻是否命中等待信号的关键词              │
│  命中 → 触发深度分析 → AI 判断是否真的是信号 → 决策            │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**与现有系统的接驳方式**：

- [ ] **查询接口** — Main Agent 的 DataHunger 新增 `query_industry_context(stock_code)`
  - 调用 `IndustryEngine.analyze(sector)` 获取行业分析
  - 调用 `chain_agent.build(subject)` 获取上下游关系（如果已有缓存则用缓存）
  - 返回结构化的产业链上下文，注入 Agent 的 think prompt
- [ ] **产业周期判断 Prompt** — 在 Agent Wake Up 的深度分析阶段：
  ```
  "你持有 [通威股份]，它处于 [光伏] 产业链的 [硅料] 环节。
   上游：工业硅、多晶硅
   下游：电池片、组件
   当前行业数据：硅料价格 XX 元/kg（近3月跌幅 30%）
   
   请判断：
   1. 这个产业当前处于周期的什么位置？
   2. 你需要等待什么信号才能改变当前策略？
   3. 如果信号出现，你的具体操作计划是什么？"
  ```
- [ ] **WatchSignal 表** — DuckDB `agent.watch_signals`
  ```sql
  CREATE TABLE agent.watch_signals (
      id VARCHAR PRIMARY KEY,
      signal_description TEXT NOT NULL,      -- "光伏硅料价格企稳"
      check_engine VARCHAR,                  -- "info" / "data" / "industry"
      keywords TEXT,                         -- JSON array
      related_stocks TEXT,                   -- JSON array of codes
      if_triggered TEXT,                     -- 触发后的行动计划
      sector VARCHAR,                        -- 相关行业
      cycle_context TEXT,                    -- 创建时的产业周期判断
      status VARCHAR DEFAULT 'watching',     -- watching/triggered/expired/cancelled
      created_at TIMESTAMP DEFAULT now(),
      triggered_at TIMESTAMP,
      trigger_evidence TEXT                  -- 什么新闻/数据触发了这个信号
  );
  ```
- [ ] **防学歪机制** — 产业链数据只用不存
  - Agent 的 KnowledgeGraph 中**不存**产业链关系（upstream/downstream 等）
  - 每次需要时通过 IndustryEngine 实时查询
  - Agent 只在 StrategySnapshot 中记录"我对这个产业的判断"（观点），不记录"产业链长什么样"（事实）
  - 如果产业格局变了（比如某公司切入新赛道），下次查询自然会得到新结果

- [ ] **RAG 增强 — 产业链认知回流到所有对话**

  > 这是关键：不只是 Main Agent 受益，普通的 `/expert` 对话也会变聪明。

  **改造 `KnowledgeGraph.recall()` — 新增 Step 4c: 产业链上下文注入**

  ```python
  # knowledge_graph.py recall() 新增步骤

  # Step 4c: 产业链上下文注入（精确匹配到 stock/sector 时触发）
  if entity_matched > 0:
      industry_context_nodes = []
      for nid in matched_ids:
          data = self.graph.nodes[nid]
          if data.get("type") == "stock":
              sector = data.get("industry", "")
              if sector:
                  # 查询产业链上下文（不存图谱，只注入 prompt）
                  chain_ctx = IndustryEngine.analyze(sector)  # 实时查
                  if chain_ctx:
                      # 创建临时的 "context node"（不写入图谱）
                      industry_context_nodes.append({
                          "id": f"_ctx_{sector}",
                          "type": "industry_context",   # 临时类型
                          "sector": sector,
                          "cycle_position": chain_ctx.get("cycle_position"),
                          "upstream": chain_ctx.get("upstream", []),
                          "downstream": chain_ctx.get("downstream", []),
                          "key_drivers": chain_ctx.get("key_drivers", []),
                      })
      # 附加到结果（不占 10 个名额，额外提供）
  ```

  **效果对比**：

  ```
  改造前：用户问"通威股份怎么样"
  RAG 注入 → "通威股份，属于光伏行业，使用硅"
  AI 回答 → 泛泛而谈，像读百科

  改造后：用户问"通威股份怎么样"
  RAG 注入 → "通威股份，属于光伏行业
              产业链位置：硅料+电池片双龙头
              上游：工业硅、多晶硅 | 下游：组件、电站
              行业周期：景气底部（硅料价格跌60%，产能出清中）
              等待信号：尾部企业退出 + 下游需求回暖
              Main Agent 当前观点：持有等待，不加仓"
  AI 回答 → 像一个真正懂行业的分析师
  ```

  **实现方式（两种选一）**：

  - **方案 A（简单）**：改造 `recall()` 返回值，额外附带 `industry_context` 字段
    - 改动小，只改 `knowledge_graph.py` + `personas.py` 的 `format_graph_context()`
    - 但 `recall()` 会变成异步（因为要调 IndustryEngine）
  - **方案 B（更好）**：在 `ExpertAgent.recall_and_think()` 中，recall 之后、think 之前，插入产业链查询
    - 不改 KnowledgeGraph 的接口
    - 在 `agent.py` 的 `recall_and_think()` 里加一步
    - 把产业链上下文拼接到 think prompt 中
    - **推荐这个** — 改动集中、不影响现有 recall 逻辑

#### 1.2.4 "数据渴求" 机制 — 让 AI 主动要数据

> 这是与普通对话式 AI 的核心区别。不是"用户问什么查什么"，
> 而是 AI **自己觉得需要知道什么就去查什么**。

```python
class DataHunger:
    """AI 的数据渴求管理器"""

    async def assess_needs(self, positions, strategy, market_state) -> list[DataRequest]:
        """AI 评估当前需要什么数据
        
        Prompt 示例：
        "你是一个管理以下持仓的投资经理：[持仓列表]
         当前策略：[策略快照]
         上次检查以来的市场变化：[增量数据]
         
         你现在最想知道什么？列出你认为最紧急需要获取的 3-5 条数据。
         格式：{engine: 'data'|'quant'|'info'|'industry', action: '...', params: {...}, urgency: 1-5, reason: '...'}"
        """

    async def execute_and_digest(self, requests: list[DataRequest]) -> str:
        """执行数据请求并让 AI 消化结果"""
        # 并行调用各引擎获取数据
        # 将结果整合后让 AI 分析：
        # "基于你刚获取的新数据，你的策略需要调整吗？"
```

#### 1.2.4 历史数据训练 — 让 AI 从历史中学习

- [ ] **Backtesting Mode** — 回测训练模式
  - 给 AI 一段历史行情（比如 2024 年全年），让它按照自己的策略模拟操作
  - 每个交易日：喂当天行情 → AI 决策 → 记录 → 下一天
  - 最后生成完整的回测报告（收益率、最大回撤、夏普比率）
  - AI 可以看到自己策略的缺陷并自我修正
- [ ] **Replay Learning** — 重放学习
  - 选择一段已有的虚拟持仓历史
  - 让 AI 重新审视当时的决策："如果重来一次，你会怎么做不同？"
  - 对比新旧策略的模拟结果

#### 1.2.5 DuckDB 表设计

```sql
-- 虚拟持仓
CREATE TABLE agent.positions (
    id VARCHAR PRIMARY KEY,
    stock_code VARCHAR NOT NULL,
    stock_name VARCHAR NOT NULL,
    direction VARCHAR DEFAULT 'long',    -- long/short
    entry_price DOUBLE NOT NULL,
    current_qty INTEGER NOT NULL,
    cost_basis DOUBLE NOT NULL,          -- 总成本
    entry_date TIMESTAMP NOT NULL,
    entry_reason TEXT,
    status VARCHAR DEFAULT 'open',       -- open/closed
    closed_at TIMESTAMP,
    closed_reason TEXT
);

-- 操作策略（每个持仓一条，AI 可更新）
CREATE TABLE agent.position_strategies (
    id VARCHAR PRIMARY KEY,
    position_id VARCHAR NOT NULL,
    take_profit DOUBLE,
    stop_loss DOUBLE,
    half_exit_price DOUBLE,
    hold_conditions TEXT,                -- JSON array
    reasoning TEXT NOT NULL,
    version INTEGER DEFAULT 1,           -- 策略版本号（每次修改+1）
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- 交易记录（每笔必须有完整理由，禁止空理由下单）
CREATE TABLE agent.trades (
    id VARCHAR PRIMARY KEY,
    position_id VARCHAR,
    action VARCHAR NOT NULL,             -- buy/sell/add/reduce/t_buy/t_sell
    stock_code VARCHAR NOT NULL,
    stock_name VARCHAR NOT NULL,
    price DOUBLE NOT NULL,
    quantity INTEGER NOT NULL,
    amount DOUBLE NOT NULL,              -- price × quantity
    -- 理由链（全部 NOT NULL，AI 不写清楚就不许操作）
    reason TEXT NOT NULL,                -- 一句话理由
    thesis TEXT NOT NULL,                -- 交易论点
    data_basis TEXT NOT NULL,            -- JSON array: 数据依据
    risk_note TEXT NOT NULL,             -- 风险提示
    invalidation TEXT NOT NULL,          -- 什么情况证明这笔操作是错的
    triggered_by VARCHAR DEFAULT 'agent', -- manual/strategy/agent
    -- 事后回顾（每日复盘时回填）
    review_result VARCHAR,               -- correct/wrong/too_early/too_late/pending
    review_note TEXT,                    -- 复盘评语
    review_date TIMESTAMP,
    pnl_at_review DOUBLE,               -- 复盘时的盈亏%
    created_at TIMESTAMP DEFAULT now()
);

-- 策略快照（AI 大脑状态的时间序列）
CREATE TABLE agent.strategy_snapshots (
    id VARCHAR PRIMARY KEY,
    market_view VARCHAR,                 -- bullish/bearish/neutral
    market_reasoning TEXT,
    position_level DOUBLE,               -- 0~1 建议仓位
    sector_prefs TEXT,                   -- JSON
    risk_alerts TEXT,                    -- JSON array
    total_asset DOUBLE,                  -- 当时的总资产
    total_pnl_pct DOUBLE,               -- 当时的总收益率
    created_at TIMESTAMP DEFAULT now()
);

-- 决策日志（最重要的表 — AI 进化的证据）
CREATE TABLE agent.decision_logs (
    id VARCHAR PRIMARY KEY,
    trigger VARCHAR NOT NULL,            -- timer/price_alert/user_request/anomaly
    positions_snapshot TEXT,             -- 当时的持仓状态 JSON
    data_gathered TEXT,                  -- 收集了什么数据 JSON
    expert_opinions TEXT,               -- 各专家意见 JSON
    reasoning TEXT NOT NULL,             -- 完整推理过程
    decision VARCHAR NOT NULL,           -- 最终决策
    decision_details TEXT,               -- 决策细节 JSON
    outcome TEXT,                        -- 事后回填
    outcome_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT now()
);

-- AI 每日复盘日志（收盘后自动生成）
CREATE TABLE agent.daily_reviews (
    id VARCHAR PRIMARY KEY,
    review_date DATE NOT NULL,
    -- 交易回顾
    trades_count INTEGER,                -- 今日交易笔数
    trades_reviewed TEXT NOT NULL,        -- JSON: 每笔交易的回顾详情
    correct_count INTEGER DEFAULT 0,
    wrong_count INTEGER DEFAULT 0,
    -- 策略审计
    strategies_modified TEXT,             -- JSON: 今日修改了哪些策略，为什么
    -- 认知更新
    surprises TEXT,                       -- "今天让我意外的事"
    blind_spots TEXT,                     -- "我的认知盲区" (如产业链关联遗漏)
    new_watchlist TEXT,                   -- 新增关注的信号/标的
    -- 自我评分
    discipline_score INTEGER,            -- 纪律性评分 1-10（有没有按策略执行）
    judgment_score INTEGER,              -- 判断力评分 1-10（方向对不对）
    -- 汇总
    daily_pnl DOUBLE,                    -- 今日总盈亏
    daily_pnl_pct DOUBLE,               -- 今日收益率
    summary TEXT NOT NULL,               -- 一段话总结今天
    created_at TIMESTAMP DEFAULT now()
);

-- AI 周度深度反思（每周五收盘后自动生成）
CREATE TABLE agent.weekly_reflections (
    id VARCHAR PRIMARY KEY,
    week_start DATE,
    week_end DATE,
    -- 业绩统计
    total_trades INTEGER,
    win_rate DOUBLE,                     -- 胜率
    profit_factor DOUBLE,                -- 盈亏比
    weekly_pnl_pct DOUBLE,              -- 本周收益率
    -- 分类型统计
    long_term_performance TEXT,          -- JSON: 长线持仓本周表现
    mid_term_performance TEXT,
    short_term_performance TEXT,
    day_trade_performance TEXT,
    -- 认知进化
    beliefs_updated TEXT,                -- JSON: 本周更新了哪些信念
    strategy_system_issues TEXT,         -- "策略体系有什么系统性问题"
    industry_cognition_gaps TEXT,        -- "产业链认知哪里有盲区"
    improvement_plan TEXT,               -- 下周改进计划
    created_at TIMESTAMP DEFAULT now()
);
```

#### 1.2.6 API 端点设计

```
# ── 虚拟持仓 ──
GET    /api/v1/agent/portfolio              # 当前持仓概览（持仓列表 + 总资产 + 盈亏）
POST   /api/v1/agent/portfolio/init         # 初始化虚拟账户（设定初始资金）
GET    /api/v1/agent/positions              # 持仓列表（含策略详情）
GET    /api/v1/agent/positions/{id}         # 单个持仓详情
GET    /api/v1/agent/trades                 # 交易记录
POST   /api/v1/agent/trades                 # 手动录入交易（用户执行后告诉 AI）

# ── 策略大脑 ──
GET    /api/v1/agent/strategy/current       # 当前策略状态
GET    /api/v1/agent/strategy/history       # 策略演化时间线
GET    /api/v1/agent/decisions              # 决策日志列表
GET    /api/v1/agent/decisions/{id}         # 单条决策完整详情
GET    /api/v1/agent/reflections            # 反思日志列表

# ── Agent 对话 ──
POST   /api/v1/agent/chat                   # 与 Main Agent 对话（SSE 流式）
POST   /api/v1/agent/adopt-strategy         # 用户采纳 AI 建议的策略
POST   /api/v1/agent/reject-strategy        # 用户否决策略（附理由）

# ── 自动运行 ──
POST   /api/v1/agent/wake                   # 手动触发一次 Agent 醒来检查
GET    /api/v1/agent/schedule               # 查看自动运行计划
PUT    /api/v1/agent/schedule               # 调整运行频率（10min/30min/daily）
GET    /api/v1/agent/wake-log               # Agent 自动运行的历史日志

# ── 回测训练 ──
POST   /api/v1/agent/backtest              # 启动历史回测
GET    /api/v1/agent/backtest/{id}         # 回测进度 & 结果
```

### 1.3 盘中自动调仓循环

> 关键设计：不是每次都完整走 4 专家流程（太慢太贵），
> 而是分**轻量检查**和**深度分析**两档。

```
交易日 9:25（开盘前）
    │
    ▼
┌─ 深度分析 ──────────────────────────────────┐
│ 调用全部 4 专家，生成"今日操作计划"          │
│ 更新 StrategySnapshot                        │
│ 推送到前端 + 通知                             │
└──────────────────────────────────────────────┘
    │
    ▼
每 10~30 分钟（盘中，可配置）
    │
    ▼
┌─ 轻量检查（按持仓类型差异化）────────────────┐
│                                                │
│  遍历所有持仓，按 holding_type 分档检查：       │
│                                                │
│  📅 long_term（长线）— 低频检查               │
│     每日 1-2 次 | 只看重大新闻 + 行业拐点信号   │
│     触发深度分析：行业重大政策 / 季报发布       │
│                                                │
│  📊 mid_term（中线）— 中频检查               │
│     每 30min | 看趋势指标 + 关键价位            │
│     触发深度分析：破趋势线 / 到达加仓位         │
│                                                │
│  ⚡ short_term（短线）— 高频检查              │
│     每 10min | 看量价 + 资金流 + 竞价表现       │
│     触发深度分析：量能萎缩 / 到达目标位         │
│                                                │
│  🔄 day_trade（做T）— 最高频检查             │
│     每 5-10min | 看分时均线 + 5min MACD         │
│     底仓不动，只操作 T 的仓位                   │
│     记录 t_buy / t_sell 交易                    │
│                                                │
│  耗时预估：2-5 秒（无 LLM 调用）              │
└────────────────────────────────────────────────┘
    │ 触发时
    ▼
┌─ 深度分析 ──────────────────────────────────┐
│ 1. 调用相关专家（不一定全部 4 个）            │
│ 2. AI 生成决策 + DecisionLog                 │
│ 3. 如果需要操作 → 更新 PositionStrategy      │
│ 4. 推送通知到前端                             │
└──────────────────────────────────────────────┘
    │
    ▼
15:00（收盘后）
    │
    ▼
┌─ 每日复盘 ──────────────────────────────────┐
│ 1. 计算当日所有持仓的盈亏                    │
│ 2. 记录 StrategySnapshot（收盘版）           │
│ 3. 如果是周五 → 生成周度 Reflection          │
│ 4. 回填之前 DecisionLog 的 outcome            │
└──────────────────────────────────────────────┘
```

### 1.4 实现阶段拆分

```
Phase 1A（1 周）— 地基：数据层 + 基础 API
├── DuckDB 建表（positions, trades, strategies, decisions, snapshots, reflections）
├── Pydantic 模型定义
├── CRUD API（持仓/交易/策略）
├── 前端 /agent 页面骨架（三栏布局 + 空壳组件）
└── 虚拟账户初始化 + 手动建仓流程

Phase 1B（1 周）— Agent 对话 + 策略提取
├── Main Agent Chat（复用 ExpertAgent 但注入持仓上下文）
├── 策略卡片自动提取（reply 后 LLM 额外做一轮结构化提取）
├── "采纳/否决"流程打通
├── 前端 ChatArea 对接
└── 策略大脑面板（当前策略状态 + 信念列表）

Phase 1C（1 周）— 自动运行 + 盘中监控 + 产业链认知
├── 轻量检查循环（APScheduler 每 N 分钟）
├── 深度分析触发机制
├── DataHunger — AI 主动数据获取
├── 产业链认知查询接口（IndustryEngine 接驳）
├── WatchSignal 信号监控表 + 扫描逻辑
├── DecisionLog 记录（含产业链上下文）
├── 前端实时推送（WebSocket / SSE）
└── Agent Wake Log 面板

Phase 1D（1 周）— 反思 + 训练 + 优化
├── 每日复盘逻辑
├── 每周反思生成
├── 策略演化 Timeline 前端
├── 历史回测模式（基础版）
├── 收益曲线图表
└── 性能调优（轻量检查 <5s）
```

---

## 二、🟡 Prompt 人格优化

> **目标**：让投资顾问和短线专家的回复风格有明显差异化，而不是"换了个模板的同一个人"。

**现状**：`personas.py` 定义了 `THINK_SYSTEM_PROMPT`（投资顾问）和 `SHORT_TERM_THINK_PROMPT`（短线专家），
但 reply 阶段的人格差异主要靠 system prompt 文本区分，身份认同不够强烈。

- [ ] **投资顾问人格深化**
  - 强调：长线思维、基本面为锚、安全边际、仓位管理
  - 话术：稳重、有分寸、不轻易推荐、推荐时给足安全边际
  - 禁忌：不追涨、不谈"明天涨停"、不做日内判断
- [ ] **短线专家人格深化**
  - 强调：盘口语言、量价关系、龙头战法、资金博弈
  - 话术：果断、强调节奏和时机、敢于说"现在就进"或"别犹豫出"
  - 禁忌：不谈估值PE、不谈三年规划、不做基本面分析
- [ ] **人格冲突设计** — 两个人格看同一只票可能意见相反
  - 投资顾问说"茅台 PE 40x 太贵了别买"
  - 短线专家说"茅台突破平台放量，短线可以进"
  - 这种冲突是设计目的，让用户获得多维视角
- [ ] **Few-shot 人格校准** — 在 prompt 中加入 3-5 条标杆对话示例
  - 减少 LLM 对 system prompt 的"遗忘"问题
  - 每个人格准备 5 段典型对话作为 few-shot

---

## 三、🟡 Superpower 深度思考模式

> **目标**：类似 Superpower，AI 先自我思考、分解问题、确认理解，然后再发起数据检索。
> 避免"你一问我就查，查完可能查错了方向"的问题。

**现状**：`deep_think` 模式已支持多轮渐进工具调用（think → tools → think_with_results → more tools），
但缺少"先跟用户确认"的环节。

- [ ] **Clarification Phase** — 理解确认阶段
  - 用户输入后，Agent 先做一轮"理解性思考"
  - 解读用户意图 → 列出不确定点 → 提 2-3 个确认问题
  - 用户确认后才进入正式分析流程
  - 可通过前端按钮开启/关闭
- [ ] **Thinking Out Loud** — 思考过程可视化
  - Agent 的 think 阶段输出对用户可见（类似 o1 思考过程）
  - 展示："我在想...这个问题涉及 XX 和 YY..."
- [ ] **Self-Critique** — 自我质疑
  - 分析完成后，Agent 对结论做一轮自我质疑
  - 提升严谨性

**实现路径**：
1. 新增 SSE 事件 `clarification_request`
2. 新增 API `POST /expert/clarify`
3. 前端 ChatPanel 增加"确认卡片"组件

---

## 四、🟢 服务器发布适配

- [ ] Docker multi-stage build
- [ ] `.env.production` 模板
- [ ] Nginx 反向代理 + SSL
- [ ] 数据卷持久化（DuckDB + ChromaDB + expert_kg.json）
- [ ] 健康检查 + 自动重启
- [ ] Cloudflare Tunnel（免公网 IP）

---

## 五、🟡 对话性能优化

**现状**：完整 chat 流程约 30-160s。

- [ ] **并行度提升** — quant 不依赖 data 时直接并行
- [ ] **流式先行** — 数据专家结果到达立刻推送
- [ ] **LLM 分层** — Think 用快模型，Reply 用大模型
- [ ] **预取策略** — 用户输入含股票代码时提前拉数据

---

## 六、🟡 多市场数据源增广

> 从纯 A 股扩展到美股、港股、场外基金、期货。

| 市场 | 数据源 | 难度 |
|------|--------|------|
| 美股 | yfinance / Polygon.io | 🟡 中 |
| 港股 | AKShare `stock_hk_*` | 🟢 低 |
| 场外基金 | AKShare `fund_*` | 🟢 低 |
| 期货 | AKShare `futures_*` | 🟡 中 |

- [ ] **MarketAdapter 抽象层** — 统一接口
- [ ] **跨市场联动分析** — 复用产业链引擎的跨链桥梁能力

---

## 🏗️ 架构约束与待解决问题

> **Brainstorm 审视结论**：功能愿景完整，但缺少三个关键工程约束层——
> **成本约束**（LLM 调用预算 + API 限速）、**数据约束**（分钟线数据源 + 行情缓存 + DuckDB 并发）、**真实性约束**（A股交易规则）。
> 这三个约束不是"后面再优化"的东西，而是**架构决策**——它们影响 Phase 1A 的数据模型和 API 设计。

### 🔴 C1: LLM Token 预算控制

**问题**：盘中检查 + 深度分析 + DataHunger + 每日复盘 + 周度反思，预估日均 40-50 次 LLM 调用，无成本约束会失控。

**方案**：增加 `TokenBudgetManager`

```python
class TokenBudgetManager:
    daily_budget: int = 500_000          # 每日 token 预算
    critical_reserve: float = 0.2        # 20% 保留给复盘和紧急分析
    current_usage: int                   # 今日已用
    priority_levels = ["critical", "high", "normal", "low"]
    
    def can_afford(self, estimated_tokens: int, priority: str) -> bool:
        """critical 可以动用 reserve，low 只在预算宽裕时放行"""
    
    def degrade_strategy(self) -> str:
        """预算紧张时：切便宜模型 → 减少检查频率 → 暂停非必要调用"""
```

**处理时机**：Phase 1A 就设计接口，Phase 1C 实装

### 🔴 C2: 轻量检查的数据源与耗时

**问题**：设计中"轻量检查 2-5秒 无LLM"不现实——做T要 5分钟 MACD（需分钟 K 线），短线要资金流（需 API 调用），真实耗时 7-20 秒。

**方案**：`MarketDataCache` + `PrecomputedIndicators`

```
开盘前（9:15）：
  对所有持仓票一次性预计算：MA5/10/20/60、MACD、布林带、关键支撑阻力位
  → 存入内存缓存（TTL = 当日收盘）

盘中轻量检查：
  只拉最新价格（1次批量 API）→ 与预计算指标对比 → 纯数学判断
  → 真正做到 0 LLM, < 2秒
  
分钟线数据：
  做T票开盘后启动分钟线采集（每分钟1条），缓存在内存中
  5分钟 MACD 可以实时增量计算，无需每次全量拉取
```

**注意**：AKShare 对高频请求有反爬限制，需要做请求速率控制

**处理时机**：Phase 1A 预研数据源可行性，Phase 1C 实装

### 🔴 C3: DuckDB 并发写与连接管理

**问题**：现有专家系统已有连接管理混乱（4 个模块各自 `duckdb.connect()` 无复用）。Main Agent 新增 8 张表 + 盘中高频读写，会严重恶化。DuckDB 是单写者模型，多定时任务并发写 → 冲突。

**方案**：

```
1. Main Agent 独立数据库文件：data/agent.duckdb（不与 expert_chat.duckdb 共用）
2. AgentDB 单例类，持有一个长连接
3. 所有写操作通过 asyncio.Lock 序列化
4. 多表操作用 DuckDB 事务包裹（如：建仓 = 写 positions + 写 trades + 写 strategies → 一个事务）
```

```python
class AgentDB:
    """Main Agent 数据库 — 单例长连接 + 写锁"""
    _instance = None
    _write_lock: asyncio.Lock
    _conn: duckdb.DuckDBPyConnection
    
    async def execute_transaction(self, queries: list[tuple[str, list]]):
        """事务性执行多条 SQL"""
        async with self._write_lock:
            self._conn.begin()
            try:
                for sql, params in queries:
                    self._conn.execute(sql, params)
                self._conn.commit()
            except:
                self._conn.rollback()
                raise
```

**处理时机**：Phase 1A 第一件事

### 🟡 C4: AI 策略评价周期 — 不能用单日快照评判

**问题**：原设计中 `daily_reviews` 的逐笔交易回顾 + `discipline_score`/`judgment_score` 自评存在两个问题：

1. **评价周期太短**：AI 做"滚动建仓"（分 3 天分批买入）是合理策略，但用单日视角看第一天的买入，可能认为"仓位太轻"或"买早了"——实际上 AI 的计划还没执行完。同理，"持有一周等催化剂"这种中线操作，第 1-3 天可能看起来"没操作 = 没作为"，但持有本身就是决策。
2. **AI 自评不客观**：LLM 有讨好倾向，自我评分缺乏锚定标准。

**方案**：交易评价改为**「操作组」维度 + 延迟评判 + 量化指标替代主观评分**

```python
class TradeGroup(BaseModel):
    """一组相关联的交易操作 — 评价的最小单位"""
    id: str
    position_id: str
    group_type: Literal[
        "build_position",    # 建仓组（可能分 1-5 天完成）
        "reduce_position",   # 减仓组
        "close_position",    # 清仓组
        "day_trade_session", # 一天的做T操作
        "rebalance",         # 调仓组（减A加B）
    ]
    trade_ids: list[str]     # 包含的交易 ID
    thesis: str              # 这组操作的整体论点
    planned_duration: str    # 预计执行周期（"3天分批建仓" / "单次操作"）
    status: Literal["executing", "completed", "abandoned"]
    
    # ── 评价（完成后才填写，不是每天填）──
    review_eligible_after: str    # 最早可评价日期（完成后 + N 天观察期）
    review_result: str | None     # correct / wrong / neutral
    review_note: str | None
    actual_pnl_pct: float | None  # 这组操作的整体盈亏
```

```sql
CREATE TABLE agent.trade_groups (
    id VARCHAR PRIMARY KEY,
    position_id VARCHAR NOT NULL,
    group_type VARCHAR NOT NULL,
    trade_ids TEXT NOT NULL,             -- JSON array
    thesis TEXT NOT NULL,
    planned_duration VARCHAR,
    status VARCHAR DEFAULT 'executing',  -- executing/completed/abandoned
    started_at TIMESTAMP DEFAULT now(),
    completed_at TIMESTAMP,
    -- 延迟评价
    review_eligible_after DATE,          -- 完成后 + 观察期才可评价
    review_result VARCHAR,               -- correct/wrong/neutral
    review_note TEXT,
    actual_pnl_pct DOUBLE,
    created_at TIMESTAMP DEFAULT now()
);
```

**评价时机规则**：

| 操作类型 | 评价等待期 | 理由 |
|---------|-----------|------|
| 建仓组 | 完成后 +5 个交易日 | 建仓完成后需要时间验证方向 |
| 减仓/清仓组 | 完成后 +3 个交易日 | 看卖出后的走势是否证明决策正确 |
| 做T组 | 当天收盘即可评价 | 日内操作当天就有结果 |
| 调仓组 | 完成后 +5 个交易日 | 看新持仓 vs 旧持仓的相对表现 |

**每日复盘改为**：
- ✅ 回顾"今日达到评价窗口的操作组"（而非今日所有交易）
- ✅ 检查"执行中操作组"的进度（滚动建仓是否按计划推进）
- ✅ 量化指标自动计算（不让 AI 打分）：
  - `策略执行一致性 = 按策略操作次数 / 总操作次数`
  - `止损纪律 = 触发止损后执行的次数 / 触发止损总次数`
  - `方向准确率 = review_result=correct 的 trade_group 比例`
- ✅ AI 只负责写叙述性 `review_note`（反思文本），不写评分数字

### 🟡 C5: Main Agent 与 ExpertAgent 的架构关系

**问题**：多处设计提到"复用 ExpertAgent"但未定义清楚接口关系。

**方案**：明确分层

```
┌─ MainAgent ──────────────────────────────────────────┐
│                                                        │
│  ┌─ AgentBrain ─┐  ┌─ PortfolioManager ─┐            │
│  │ 策略/信念/   │  │ 持仓/交易/策略     │            │
│  │ 反思/认知    │  │ agent.duckdb       │            │
│  └──────────────┘  └────────────────────┘            │
│                                                        │
│  ┌─ EngineOrchestrator ──────────────────────┐        │
│  │ 封装对 4 引擎的调用（非 SSE，结构化返回） │        │
│  │ 入口：analyze(question, context) → dict    │        │
│  └────────────────────────────────────────────┘        │
│                                                        │
│  复用现有系统（直接调用，不走 HTTP）：                  │
│  - DataEngine.get_*()        → 行情数据                │
│  - IndustryEngine.analyze()  → 产业链查询              │
│  - KnowledgeGraph.recall()   → 图谱召回（共用实例）    │
│  - SkillRegistry.execute()   → 复用 Skill 注册表       │
│                                                        │
│  Main Agent 独有模块：                                  │
│  - 持仓感知的 system prompt                             │
│  - DataHunger 主动数据获取                              │
│  - 定时 wake up 循环                                    │
│  - 复盘/反思系统                                        │
│  - TradeValidator 交易规则校验                          │
│  - TokenBudgetManager 成本控制                          │
└────────────────────────────────────────────────────────┘
```

**关键决策**：
- Main Agent 调 4 引擎走 `EngineOrchestrator`（内部直调 SkillRegistry，非 HTTP/SSE），返回结构化 dict
- Main Agent 与 ExpertAgent 共用 `KnowledgeGraph` 实例（同一个 `expert_kg.json`）
- Main Agent 对话走独立 SSE 端点 `/api/v1/agent/chat`，不复用 `/expert/chat`
- Main Agent 数据库独立 `data/agent.duckdb`，不与 `expert_chat.duckdb` 混用

**处理时机**：Phase 1A 开始前确认

### 🟡 C6: 回测模式成本与可行性

**问题**：模拟一年（245 交易日）× 每天 5+ 次 LLM = 1225+ 次 LLM 调用，纯 LLM 时间 ~2 小时，token 成本可观。且 LLM 有随机性，回测结果不可重现。

**方案**：精简版回测 + 断点续传 + 可重现性

```
Phase 1D 回测 MVP：
├── 只模拟 20 个交易日（一个月），降低成本
├── temperature=0 保证可重现性
├── 每日状态 checkpoint 存 DuckDB（支持中断恢复）
├── 必须有 benchmark 对比线（沪深300 / 等权持有）
├── 输出标准化回测报告（收益率、最大回撤、夏普、Calmar）
└── 后续再逐步扩展到季度/年度回测
```

**处理时机**：Phase 1D

### 🟡 C7: 前端 /agent 状态管理

**问题**：三栏实时联动界面（对话/策略/持仓），数据流复杂，需要全局状态管理。

**方案**：
- 使用 **Zustand**（项目已是 React，Zustand 轻量适配）管理 Agent 页面全局状态
- Agent 事件统一走 SSE，新增事件类型：`portfolio_update`、`decision_new`、`strategy_changed`
- 实时盈亏：**前端每 30 秒轮询** `/api/v1/agent/portfolio`，不引入行情 WebSocket

**处理时机**：Phase 1A 定方案，Phase 1B 实装

### 🟢 C8: 虚拟持仓交易规则校验

**问题**：虚拟盘需要模拟 A 股真实交易规则，否则回测和模拟盘的结果无参考价值。

**方案**：增加 `TradeValidator`

```python
class TradeValidator:
    def validate(self, trade: Trade, position: Position, market_data: dict) -> tuple[bool, str]:
        # 1. T+1 检查（非做T的 sell 必须持有 > 1 天）
        # 2. 涨跌停检查（涨停不能买入，跌停不能卖出）
        # 3. 最小交易单位（100 股/手）
        # 4. 滑点估算（按现价 ± 0.1-0.3% 估算实际成交价）
        # 5. 资金充足检查（虚拟账户余额 ≥ price × quantity）
        # 6. 做T规则（只有底仓部分可以 T+0 卖出）
```

**处理时机**：Phase 1A 同步实现

---

## 📊 执行顺序

```
Phase 1A  ████░░░░  Main Agent 地基（数据层 + API + 页面骨架）     ← START HERE
Phase 1B  ░░████░░  Agent 对话 + 策略提取
Phase 1C  ░░░░████  自动运行 + 盘中监控
Phase 1D  ░░░░░░██  反思 + 训练 + 优化
Phase 2   ░░░░░░██  Prompt 人格 + Superpower
Phase 3   ░░░░░░░░  性能优化 + 多市场 + 服务器
```

**Phase 1A 是起点，随时可以开始。**

---

*This is a living document. 每完成一项就打 ✅ 并记录完成日期。*
