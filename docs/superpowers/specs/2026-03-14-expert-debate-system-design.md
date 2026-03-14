# 专家辩论系统 — 架构设计 Spec

> **定位：** 在现有 Multi-Agent 决策大脑的基础上，为 Expert 层引入多角色辩论机制，替代原有的单 Agent 深度解读。
> **前置依赖：** `2026-03-14-multi-agent-decision-brain-design.md`（三层 Worker + Orchestrator 架构）
> **变更说明：** 本 spec 推翻原 spec 第 9 节 YAGNI 边界中"不做 Agent 对话式辩论"的决定，升级为 Blackboard 模式的结构化多专家辩论。

---

## 1. 系统定位

```
┌──────────────────────────────────────────────────────────┐
│  Orchestrator.analyze()                                  │
│                                                          │
│  Phase 1: PreScreen                                      │
│  Phase 2: Worker 并行分析（基本面 / 消息面 / 技术面）        │
│  Phase 3: 聚合 → AggregatedReport                        │
│  Phase 4: 【本 spec】专家辩论 → JudgeVerdict              │  ← 新增
└──────────────────────────────────────────────────────────┘
```

专家辩论是 Phase 4，**每次分析都触发**。辩论基于 Phase 2/3 已收集的数据，但允许辩论过程中向引擎下发补充数据请求。裁判最终输出 `JudgeVerdict`，作为面向用户的最终报告。

---

## 2. 角色定义

### 2.1 辩论者（必须每轮发言）

| 角色 | ID | 视角 | 行为特征 |
|------|-----|------|---------|
| 多头专家 | `bull_expert` | 金融专业者，价值发现视角 | 坚定看多，主动寻找上涨依据，极度乐观但必须基于证据。认输意味着真的找不到看多理由 |
| 空头专家 | `bear_expert` | 金融专业者，风险识别视角 | 坚定看空，主动寻找下跌风险，极度悲观但必须基于证据。认输意味着真的找不到看空理由 |

**人格约束：**
- 两者都是金融专业人士，论据必须专业、有据可查
- 强烈坚持立场是默认行为，不允许轻易被说服
- `concede`（认输）是强信号，说明对方论据已压倒性，此时继续坚持是不诚实的

### 2.2 观察员（每轮自主决定是否发言）

| 角色 | ID | 视角 | 行为特征 |
|------|-----|------|---------|
| 散户代表 | `retail_investor` | 市场情绪、行为金融 | 追涨杀跌倾向，容易受近因效应影响，代表大众情绪。发言时提供情绪面信息，不强制选边 |
| 主力代表 | `smart_money` | 资金流向、筹码分布 | 关注大单交易、北向资金、融资融券等资金行为。发言时提供资金面信息，不强制选边 |

**观察员特性：**
- 不需要持有 bullish/bearish 立场，只提供视角信息
- 无认输机制，他们只是补充信息的提供者
- 每轮通过 `speak: bool` 声明是否发言，沉默也是一种有效选择
- 散户代表是**反向参考**——当散户极度乐观时可能是见顶信号
- 主力代表是**正向参考**——聪明钱的方向有更高参考价值

### 2.3 裁判（只在最后总结）

| 角色 | ID | 职责 |
|------|-----|------|
| 裁判 | `judge` | 全程旁观，辩论结束后读完整 Blackboard，综合所有角色的发言、散户情绪、主力动向、Worker 原始 verdicts，输出最终汇总报告 |

**裁判特性：**
- 不干预辩论过程，不引导讨论方向
- 不强制给出 bullish/bearish 结论，可以只做信息汇总
- 给出结论时需说明置信度和核心依据
- 最后一轮结束后才开始工作

---

## 3. 数据结构

### 3.1 Blackboard（辩论共享状态）

```python
class Blackboard(BaseModel):
    """辩论共享状态 — 所有参与者读写的中心桌面"""

    # 标的
    target: str

    # ── 事实层（Phase 2/3 产出，只读）──
    facts: dict[str, Any] = {}           # engine_name → 引擎数据
    worker_verdicts: list[AgentVerdict] = []   # 三个 Worker 的初步判断
    conflicts: list[str] = []            # 聚合器检测到的多空分歧

    # ── 辩论层 ──
    transcript: list[DebateEntry] = []   # 完整对话记录，按时间序

    # ── 数据请求层 ──
    data_requests: list[DataRequest] = []  # 所有历史数据请求（含已完成）

    # ── 控制层 ──
    round: int = 0
    max_rounds: int = 3                  # 可配置，默认 3
    status: Literal[
        "debating",      # 正常辩论中
        "final_round",   # 最后一轮（倒数第一轮开始时设置）
        "judging",       # 辩论结束，裁判工作中
        "completed",     # 裁判总结完毕
    ] = "debating"
    termination_reason: Literal[
        "bull_conceded",
        "bear_conceded",
        "both_conceded",
        "max_rounds",
    ] | None = None


class DebateEntry(BaseModel):
    """单条辩论发言"""
    role: str                            # bull_expert / bear_expert / retail_investor / smart_money
    round: int

    # 辩论者专属字段
    stance: Literal["insist", "partial_concede", "concede"] | None = None
    # insist: 坚持原立场
    # partial_concede: 承认对方部分论据，但整体立场不变
    # concede: 认输，承认自己的核心论据不成立

    # 观察员专属字段
    speak: bool = True                   # False = 本轮选择沉默

    # 发言内容
    argument: str = ""                   # speak=False 时为空
    challenges: list[str] = []          # 质疑对方的具体论据（观察员可为空）
    data_requests: list["DataRequest"] = []  # 需要补充的数据
    confidence: float = 0.5             # 0-1，当前信心水平


class DataRequest(BaseModel):
    """专家向引擎下发的数据补充请求"""
    requested_by: str                    # 提出请求的角色 ID
    engine: str                          # "data" | "quant" | "info"
    action: str                          # 具体操作名，如 "get_block_trade"
    params: dict = {}
    result: Any = None                   # 执行结果，初始 None
    status: Literal["pending", "done", "failed"] = "pending"
    round: int = 0                       # 提出请求时的轮次


class JudgeVerdict(BaseModel):
    """裁判最终总结"""
    target: str
    summary: str                         # 完整汇总分析，面向用户的自然语言
    signal: Literal["bullish", "bearish", "neutral"] | None = None  # 可以不给
    score: float | None = None           # -1.0 ~ 1.0，可以不给

    key_arguments: list[str]             # 各方关键论点提炼
    bull_core_thesis: str                # 多头核心逻辑一句话总结
    bear_core_thesis: str                # 空头核心逻辑一句话总结

    retail_sentiment_note: str           # 散户情绪总结
    smart_money_note: str                # 主力动向总结

    risk_warnings: list[str]             # 风险提示
    debate_quality: Literal[
        "consensus",          # 辩论中一方认输，形成共识
        "strong_disagreement", # 双方强烈分歧，max_rounds 到达
        "one_sided",          # 一方明显占优
    ]
    termination_reason: str              # 辩论终止原因说明
    timestamp: datetime
```

### 3.2 数据请求白名单

辩论者可以请求的数据操作，受角色白名单限制：

```python
DEBATE_DATA_WHITELIST: dict[str, list[str]] = {
    "bull_expert": [
        "get_stock_info", "get_daily_history", "get_factor_scores",
        "get_news", "get_announcements", "get_technical_indicators",
        "get_cluster_for_stock",
    ],
    "bear_expert": [
        "get_stock_info", "get_daily_history", "get_factor_scores",
        "get_news", "get_announcements", "get_technical_indicators",
        "get_cluster_for_stock",
    ],
    "retail_investor": [
        "get_news",          # 散户只看新闻和情绪类数据
    ],
    "smart_money": [
        "get_technical_indicators", "get_factor_scores",  # 资金面数据
    ],
}

# 每轮每个角色最多发起的数据请求数
MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND = 2

# 最后一轮禁止数据请求
FINAL_ROUND_ALLOW_DATA_REQUESTS = False
```

---

## 4. 辩论流程

### 4.1 主循环伪代码

```python
async def run_debate(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    data_fetcher: DataFetcher,
) -> JudgeVerdict:

    while blackboard.round < blackboard.max_rounds:
        blackboard.round += 1
        is_final = (blackboard.round == blackboard.max_rounds)
        is_pre_final = (blackboard.round == blackboard.max_rounds - 1)

        # 进入最后一轮时更新状态
        if is_final:
            blackboard.status = "final_round"

        # ── 1. 多头发言（必须）──
        bull_entry = await speak(
            role="bull_expert",
            blackboard=blackboard,
            llm=llm,
            memory=memory,
            is_final_round=is_final,
        )
        blackboard.transcript.append(bull_entry)
        yield sse_event("debate_entry", bull_entry)

        # ── 2. 空头发言（必须）──
        bear_entry = await speak(
            role="bear_expert",
            blackboard=blackboard,
            llm=llm,
            memory=memory,
            is_final_round=is_final,
        )
        blackboard.transcript.append(bear_entry)
        yield sse_event("debate_entry", bear_entry)

        # ── 3. 观察员发言（可选）──
        for observer in ["retail_investor", "smart_money"]:
            entry = await speak(
                role=observer,
                blackboard=blackboard,
                llm=llm,
                memory=memory,
                is_final_round=is_final,
            )
            blackboard.transcript.append(entry)
            if entry.speak:
                yield sse_event("debate_entry", entry)

        # ── 4. 执行数据请求 ──
        pending = [r for r in blackboard.data_requests if r.status == "pending"]
        if pending:
            yield sse_event("data_fetching", {"count": len(pending)})
            await fulfill_data_requests(pending, data_fetcher)
            yield sse_event("data_ready", {"count": len(pending)})

        # ── 5. 轮次控制 ──
        bull_conceded = any(
            e.role == "bull_expert" and e.stance == "concede"
            for e in blackboard.transcript
        )
        bear_conceded = any(
            e.role == "bear_expert" and e.stance == "concede"
            for e in blackboard.transcript
        )

        if bull_conceded and bear_conceded:
            blackboard.termination_reason = "both_conceded"
            break
        elif bull_conceded:
            blackboard.termination_reason = "bull_conceded"
            break
        elif bear_conceded:
            blackboard.termination_reason = "bear_conceded"
            break
        elif is_final:
            blackboard.termination_reason = "max_rounds"
            break

    # ── 6. 裁判总结 ──
    blackboard.status = "judging"
    yield sse_event("debate_end", {
        "reason": blackboard.termination_reason,
        "rounds_completed": blackboard.round,
    })

    judge_verdict = await judge_summarize(blackboard, llm, memory)
    blackboard.status = "completed"
    yield sse_event("judge_verdict", judge_verdict.model_dump())

    # ── 7. 持久化 ──
    await persist_debate(blackboard, judge_verdict)

    return judge_verdict
```

### 4.2 发言函数

每个角色发言时读取 Blackboard 完整状态，构建 prompt，调用 LLM，解析返回的 `DebateEntry`：

```python
async def speak(
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    is_final_round: bool,
) -> DebateEntry:

    # 读取该角色的历史记忆
    memory_ctx = memory.recall(role, f"辩论 {blackboard.target}", top_k=3)

    # 构建 prompt（详见 Section 5）
    messages = build_debate_prompt(role, blackboard, memory_ctx, is_final_round)

    raw = await llm.chat(messages)
    entry = parse_debate_entry(role, blackboard.round, raw)

    # 将数据请求写入 Blackboard
    if not is_final_round:
        validated_requests = validate_data_requests(role, entry.data_requests)
        blackboard.data_requests.extend(validated_requests)

    return entry
```

### 4.3 认输后的行为

当某方 `stance == "concede"` 时：
- **当轮剩余角色仍正常发言**（不立即中断）
- 认输方在之后的轮次不再出现（如果还有轮次的话，但认输会触发退出）
- 认输本身会出现在 `transcript` 中，裁判会读到并在总结中引用

### 4.4 final_round 机制

当 `round == max_rounds` 时，`is_final_round=True` 传入所有角色的 prompt 构建函数。prompt 中注入额外段落：

> "这是最后一轮辩论。请发表你的最终观点，总结你认为最核心的论据。本轮结束后裁判将做出最终裁决。"

同时最后一轮禁止提出新的数据请求（`FINAL_ROUND_ALLOW_DATA_REQUESTS = False`）。

---

## 5. Prompt 设计

### 5.1 多头专家 System Prompt

```
你是一位资深金融专业人士，在本次辩论中扮演多头（看多）角色。

## 你的使命
你必须为看多{target}寻找并捍卫一切有据可查的理由。你的立场是坚定的，
不轻易被说服。只有当对方的论据真正压倒性、你找不到任何有效反驳时，
才可以选择认输（concede）。轻易认输是不诚实的表现。

## 行为规范
- 论据必须基于数据和金融逻辑，不允许无根据的乐观
- 每轮必须针对空头的核心论点提出具体反驳
- 如果需要更多数据支撑你的论点，可以通过 data_requests 请求
- partial_concede 表示你承认对方某个具体论点，但整体仍看多

## 输出格式（严格 JSON）
{
  "stance": "insist" | "partial_concede" | "concede",
  "argument": "你的核心发言内容",
  "challenges": ["你质疑对方的具体论据1", "..."],
  "confidence": 0.0-1.0,
  "data_requests": [
    {"engine": "quant", "action": "get_factor_scores", "params": {"code": "xxx"}}
  ]
}
```

### 5.2 空头专家 System Prompt

结构与多头对称，立场改为坚定看空，寻找风险和下跌依据。

### 5.3 散户代表 System Prompt

```
你是市场散户的代表，代表大众投资者的情绪和行为视角。

## 你的视角
- 关注市场热度、论坛讨论、追涨杀跌行为
- 你的情绪往往是反向指标（极度乐观时可能见顶）
- 你不需要选边站，只提供你观察到的市场情绪信息

## 发言决策
如果当前辩论中缺乏市场情绪视角的信息，或你有重要的情绪面信息要补充，
选择发言（speak: true）。否则可以选择沉默（speak: false）。

## 输出格式（严格 JSON）
{
  "speak": true | false,
  "argument": "你的观察（speak=false 时为空字符串）",
  "data_requests": []
}
```

### 5.4 主力代表 System Prompt

结构与散户对称，视角改为资金流向和筹码分布。关注大单、北向资金、融资融券动向。

### 5.5 裁判 System Prompt

```
你是一位资深金融专业人士，担任本次辩论的裁判。

## 你的职责
综合以下所有信息，为用户提供一份客观、专业的投资参考报告：
- 三位 Worker 分析师的初步判断（基本面/消息面/技术面）
- 多头专家和空头专家的完整辩论记录
- 散户代表的情绪面观察
- 主力代表的资金面观察

## 输出要求
- summary: 面向普通用户的完整分析，语言清晰易懂
- 不强制给出 bullish/bearish 结论，可以只汇总信息
- 给出结论时，需说明核心依据和置信度
- 明确标注散户情绪的反向参考价值
- 风险提示必须具体，不允许泛泛而谈
```

---

## 6. SSE 事件扩展

在现有 Orchestrator SSE 事件基础上，新增辩论阶段事件：

```
# 辩论开始
event: debate_start
data: { "target": "600519", "max_rounds": 3, "participants": ["bull_expert", "bear_expert", "retail_investor", "smart_money", "judge"] }

# 每条发言（speak=false 的观察员不推送）
event: debate_entry
data: { "role": "bull_expert", "round": 1, "stance": "insist", "speak": true, "argument": "...", "challenges": [...], "confidence": 0.82 }

# 专家请求补充数据
event: data_fetching
data: { "requested_by": "bear_expert", "engine": "quant", "action": "get_factor_scores", "count": 2 }

# 数据到位
event: data_ready
data: { "count": 2, "result_summary": "获取到因子评分数据" }

# 辩论结束
event: debate_end
data: { "reason": "bear_conceded", "rounds_completed": 2 }

# 裁判总结
event: judge_verdict
data: { "summary": "...", "signal": "bullish", "score": 0.65, "key_arguments": [...], ... }
```

---

## 7. MCP 工具暴露

新增 4 个 MCP tools，允许通过 MCP 触发和查询辩论：

| Tool | 描述 | 参数 |
|------|------|------|
| `start_debate` | 对指定股票发起专家辩论 | `code: str`, `max_rounds: int = 3` |
| `get_debate_status` | 查询辩论进度 | `debate_id: str` |
| `get_debate_transcript` | 获取辩论记录 | `debate_id: str`, `round: int = None`, `role: str = None` |
| `get_judge_verdict` | 获取裁判最终总结 | `debate_id: str` |

---

## 8. 存储设计

### 8.1 新增 DuckDB 表

```sql
-- 辩论记录存档（Blackboard 序列化）
CREATE TABLE shared.debate_records (
    id              VARCHAR PRIMARY KEY,   -- debate_id = target + timestamp
    target          VARCHAR,
    max_rounds      INTEGER,
    rounds_completed INTEGER,
    termination_reason VARCHAR,
    blackboard_json TEXT,                  -- 完整 Blackboard JSON
    judge_verdict_json TEXT,               -- JudgeVerdict JSON
    created_at      TIMESTAMP,
    completed_at    TIMESTAMP,
);
```

`JudgeVerdict` 同时写入现有 `shared.analysis_reports` 表，与普通分析报告统一存档。

### 8.2 ChromaDB 新增 Collections

```
memory_bull_expert      ← 多头专家推理记忆
memory_bear_expert      ← 空头专家推理记忆
memory_retail_investor  ← 散户代表观察记忆
memory_smart_money      ← 主力代表观察记忆
memory_judge            ← 裁判历史决策记忆
```

与现有 Worker 的 collection 隔离，互不污染。90 天保留策略与现有一致。

---

## 9. 对现有代码的影响

| 文件/模块 | 变动类型 | 说明 |
|-----------|---------|------|
| `engine/agent/orchestrator.py` | 修改 | `analyze()` 末尾追加 Phase 4 调用 `run_debate()` |
| `engine/agent/schemas.py` | 修改 | 新增 `Blackboard`、`DebateEntry`、`DataRequest`、`JudgeVerdict` |
| `engine/agent/personas.py` | 修改 | 新增 `bull_expert`、`bear_expert`、`retail_investor`、`smart_money`、`judge` 五个人格定义 |
| `engine/agent/data_fetcher.py` | 修改 | 新增 `fetch_by_request(DataRequest)` 方法，按 action 名动态路由 |
| `engine/agent/memory.py` | 不改动 | 直接复用现有 `store()`/`recall()`，新角色自动创建对应 collection |
| `engine/agent/debate.py` | 新增文件 | 辩论主循环、`speak()`、`judge_summarize()`、`fulfill_data_requests()` |
| `engine/mcpserver/` | 修改 | 新增 4 个 debate tools |

**不涉及的模块：**
- `runner.py` — Worker 层不变
- `aggregator.py` — 聚合逻辑不变
- `llm/` — LLM 层不变
- 前端 — 暂不实现，前端 UI 中留 TODO 注释

---

## 10. 实施分期

### Phase 1（本 spec 范围）
- `debate.py` 核心辩论循环
- `schemas.py` 新增数据结构
- `personas.py` 新增 5 个角色人格
- `orchestrator.py` 接入 Phase 4
- `data_fetcher.py` 新增动态路由
- MCP 4 个新 tools
- DuckDB `shared.debate_records` 表
- ChromaDB 5 个新 collections

### Phase 2（后续）
- 前端辩论对话 UI（实时流式渲染）
- 辩论历史回放
- 辩论质量评估（与真实涨跌对比）

---

## 11. YAGNI 边界

- 不做超过 max_rounds 的辩论控制以外的复杂调度
- 不做辩论者之间的直接点名互动（通过 challenges 列表间接引用即可）
- 不做辩论中途暂停/恢复
- 不做多标的同时辩论
- 不做辩论结果对 Worker calibration_weight 的反馈（属于后续优化）
- 前端实现暂不在本 spec 范围内
