# 专家辩论系统 — 架构设计 Spec

> **定位：** 在现有 Multi-Agent 决策大脑的基础上，为 Expert 层引入多角色辩论机制，替代原有的单 Agent 深度解读。
> **前置依赖：** `2026-03-14-multi-agent-decision-brain-design.md`（三层 Worker + Orchestrator 架构）
> **变更说明：** 本 spec 推翻原 spec 第 9 节 YAGNI 边界中"不做 Agent 对话式辩论"的决定，升级为 Blackboard 模式的结构化多专家辩论。原 spec Section 9 该条目已作废，以本 spec 为准。

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

`run_debate()` 是一个 **async generator**，与 `orchestrator.analyze()` 保持相同模式：通过 `yield` 推送 SSE 事件，`JudgeVerdict` 通过最后一个 `judge_verdict` SSE 事件的 payload 传递给调用方，不使用 `return` 返回值。

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
| 主力代表 | `smart_money` | 资金流向、技术面资金信号 | 关注量价关系、大单方向、筹码分布等可从 QuantEngine 获取的资金行为信号。发言时提供资金面视角，不强制选边 |

**注意：** `smart_money` 的数据来源限定为 QuantEngine 已有的技术指标和因子评分（`get_technical_indicators`、`get_factor_scores`）。大宗交易、北向资金等外部资金数据源暂未接入，属于后续扩展范围。

**观察员特性：**
- 不需要持有 bullish/bearish 立场，只提供视角信息
- 无认输机制，他们只是补充信息的提供者
- 每轮通过 `speak: bool` 声明是否发言，沉默也是一种有效选择
- 散户代表是**反向参考**——当散户极度乐观时可能是见顶信号
- 主力代表是**正向参考**——资金信号的方向有更高参考价值

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
    debate_id: str       # 格式: "{target}_{YYYYMMDDHHMMSS}"，由 orchestrator 在初始化时生成

    # ── 事实层（Phase 2/3 产出，只读）──
    facts: dict[str, Any] = {}                   # engine_name → 引擎数据
    worker_verdicts: list[AgentVerdict] = []     # 三个 Worker 的初步判断
    conflicts: list[str] = []                    # 聚合器检测到的多空分歧

    # ── 辩论层 ──
    transcript: list[DebateEntry] = []           # 完整对话记录，按时间序

    # ── 数据请求层 ──
    data_requests: list[DataRequest] = []        # 所有历史数据请求（含已完成）

    # ── 控制层 ──
    round: int = 0
    max_rounds: int = 3                          # 可配置，默认 3
    bull_conceded: bool = False                  # 多头是否已认输（本轮 append 后立即更新）
    bear_conceded: bool = False                  # 空头是否已认输（本轮 append 后立即更新）
    status: Literal[
        "debating",      # 正常辩论中
        "final_round",   # 最后一轮（round == max_rounds 时设置）
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
    role: str           # bull_expert / bear_expert / retail_investor / smart_money
    round: int

    # 辩论者专属字段（观察员为 None）
    stance: Literal["insist", "partial_concede", "concede"] | None = None
    # insist: 坚持原立场
    # partial_concede: 承认对方部分论据，但整体立场不变
    # concede: 认输，承认自己的核心论据不成立

    # 观察员专属字段
    speak: bool = True                   # False = 本轮选择沉默

    # 发言内容
    argument: str = ""                   # speak=False 时为空
    challenges: list[str] = []          # 质疑对方的具体论据（观察员可为空）
    data_requests: list["DataRequest"] = []
    confidence: float = 0.5             # 0-1，当前信心水平（观察员可不填）
    retail_sentiment_score: float | None = None
    # 仅 retail_investor 填写：+1.0 = 极度乐观，-1.0 = 极度悲观，0 = 中性
    # 供裁判作反向参考使用


class DataRequest(BaseModel):
    """专家向引擎下发的数据补充请求"""
    requested_by: str                    # 提出请求的角色 ID
    engine: str                          # "data" | "quant" | "info"
    action: str                          # 具体操作名，如 "get_technical_indicators"
    params: dict = {}
    result: Any = None                   # 执行结果，初始 None
    status: Literal["pending", "done", "failed"] = "pending"
    round: int = 0                       # 提出请求时的轮次


class JudgeVerdict(BaseModel):
    """裁判最终总结"""
    target: str
    debate_id: str
    summary: str                         # 完整汇总分析，面向用户的自然语言
    signal: Literal["bullish", "bearish", "neutral"] | None = None  # 可以不给
    score: float | None = None           # -1.0 ~ 1.0，可以不给

    key_arguments: list[str]             # 各方关键论点提炼
    bull_core_thesis: str                # 多头核心逻辑一句话总结
    bear_core_thesis: str                # 空头核心逻辑一句话总结

    retail_sentiment_note: str           # 散户情绪总结（含反向指标解读）
    smart_money_note: str                # 主力动向总结

    risk_warnings: list[str]             # 风险提示（必须具体，不允许泛泛）
    debate_quality: Literal[
        "consensus",            # 一方认输，形成共识
        "strong_disagreement",  # max_rounds 到达，双方均未认输，分歧持续
        "one_sided",            # 一方 confidence 持续下降但未正式认输，裁判判断明显占优
    ]
    # debate_quality 判定规则：
    # - "consensus": termination_reason in ("bull_conceded", "bear_conceded", "both_conceded")
    # - "strong_disagreement": termination_reason == "max_rounds" AND
    #                          最后一轮双方 confidence 差值 < 0.3
    # - "one_sided": termination_reason == "max_rounds" AND
    #                最后一轮一方 confidence < 0.35 且另一方 > 0.65
    termination_reason: str
    timestamp: datetime
```

### 3.2 数据请求白名单与路由表

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
        "get_news",
    ],
    "smart_money": [
        "get_technical_indicators", "get_factor_scores",
    ],
}

MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND = 2  # 每轮每角色最多请求数
FINAL_ROUND_ALLOW_DATA_REQUESTS = False    # 最后一轮禁止请求
```

**`fetch_by_request` 路由表**（`DataFetcher.fetch_by_request` 的内部 dispatch）：

```python
ACTION_DISPATCH: dict[str, tuple[str, str]] = {
    # action_name → (engine_module, method_name)
    "get_stock_info":           ("data_engine",  "get_profile"),
    "get_daily_history":        ("data_engine",  "get_daily_history"),
    "get_technical_indicators": ("quant_engine", "compute_indicators"),
    "get_factor_scores":        ("quant_engine", "get_factor_scores"),
    "get_news":                 ("info_engine",  "get_news"),
    "get_announcements":        ("info_engine",  "get_announcements"),
    "get_cluster_for_stock":    ("cluster_engine", "get_cluster_for_stock"),
}
# 白名单之外的 action 直接拒绝，抛出 ValueError
```

---

## 4. 辩论流程

### 4.1 主循环（async generator）

`run_debate` 是 async generator，通过 `yield` 推送 SSE 事件。`JudgeVerdict` 包含在最后一个 `judge_verdict` 事件的 payload 中，调用方（`orchestrator.analyze()`）从该事件中解析并存储。

```python
async def run_debate(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    data_fetcher: DataFetcher,
) -> AsyncGenerator[dict, None]:

    yield sse_event("debate_start", {
        "debate_id": blackboard.debate_id,
        "target": blackboard.target,
        "max_rounds": blackboard.max_rounds,
        "participants": ["bull_expert", "bear_expert", "retail_investor", "smart_money", "judge"],
    })

    while blackboard.round < blackboard.max_rounds:
        blackboard.round += 1
        is_final = (blackboard.round == blackboard.max_rounds)

        if is_final:
            blackboard.status = "final_round"

        yield sse_event("debate_round_start", {
            "round": blackboard.round,
            "is_final": is_final,
        })

        # ── 1. 多头发言（必须）──
        bull_entry = await speak(
            role="bull_expert", blackboard=blackboard,
            llm=llm, memory=memory, is_final_round=is_final,
        )
        blackboard.transcript.append(bull_entry)
        if bull_entry.stance == "concede":
            blackboard.bull_conceded = True
        yield sse_event("debate_entry", bull_entry.model_dump())

        # ── 2. 空头发言（必须）──
        bear_entry = await speak(
            role="bear_expert", blackboard=blackboard,
            llm=llm, memory=memory, is_final_round=is_final,
        )
        blackboard.transcript.append(bear_entry)
        if bear_entry.stance == "concede":
            blackboard.bear_conceded = True
        yield sse_event("debate_entry", bear_entry.model_dump())

        # ── 3. 观察员发言（可选）──
        for observer in ["retail_investor", "smart_money"]:
            entry = await speak(
                role=observer, blackboard=blackboard,
                llm=llm, memory=memory, is_final_round=is_final,
            )
            blackboard.transcript.append(entry)
            if entry.speak:
                yield sse_event("debate_entry", entry.model_dump())

        # ── 4. 执行数据请求 ──
        pending = [r for r in blackboard.data_requests if r.status == "pending"]
        if pending and not is_final:
            for req in pending:
                yield sse_event("data_fetching", {
                    "requested_by": req.requested_by,
                    "engine": req.engine,
                    "action": req.action,
                })
            await fulfill_data_requests(pending, data_fetcher)
            yield sse_event("data_ready", {
                "count": len(pending),
                "result_summary": f"已获取 {len(pending)} 条补充数据",
            })

        # ── 5. 轮次控制（使用 Blackboard 上的 bool 标志，不扫描 transcript）──
        if blackboard.bull_conceded and blackboard.bear_conceded:
            blackboard.termination_reason = "both_conceded"
            break
        elif blackboard.bull_conceded:
            blackboard.termination_reason = "bull_conceded"
            break
        elif blackboard.bear_conceded:
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

    # JudgeVerdict 通过 judge_verdict 事件传递，调用方从此事件中解析
    yield sse_event("judge_verdict", judge_verdict.model_dump(mode="json"))

    # ── 7. 持久化 ──
    await persist_debate(blackboard, judge_verdict)
```

### 4.2 发言函数（含错误处理）

```python
async def speak(
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    is_final_round: bool,
) -> DebateEntry:

    memory_ctx = memory.recall(role, f"辩论 {blackboard.target}", top_k=3)
    messages = build_debate_prompt(role, blackboard, memory_ctx, is_final_round)

    try:
        raw = await asyncio.wait_for(llm.chat(messages), timeout=45.0)
        entry = parse_debate_entry(role, blackboard.round, raw)
    except asyncio.TimeoutError:
        logger.warning(f"辩论角色 [{role}] LLM 调用超时，使用默认发言")
        entry = _fallback_entry(role, blackboard.round, reason="timeout")
    except Exception as e:
        logger.warning(f"辩论角色 [{role}] LLM 调用失败: {e}，使用默认发言")
        entry = _fallback_entry(role, blackboard.round, reason=str(e))

    # 默认发言规则：
    # - 辩论者（bull/bear）：stance="insist"，argument="（暂无发言）"，confidence 维持上一轮
    # - 观察员：speak=False

    if not is_final_round:
        validated = validate_data_requests(role, entry.data_requests)
        blackboard.data_requests.extend(validated)

    return entry
```

**错误处理策略：** 辩论者（`bull_expert`/`bear_expert`）失败时使用 `stance="insist"` 的默认条目，确保辩论不中断。观察员失败时默认 `speak=False`。失败信息记录到 Loguru 日志，不向前端暴露。

**`validate_data_requests` 行为契约：**
- 过滤掉不在 `DEBATE_DATA_WHITELIST[role]` 中的 action，记录 warning 日志
- 超出 `MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND` 的请求静默截断（保留前 N 条）
- 返回通过验证的 `list[DataRequest]`，不抛出异常

**`fulfill_data_requests` 行为契约：**
- 对每条 `DataRequest` 调用 `DataFetcher.fetch_by_request(req)`
- 将结果写入 `req.result`，更新 `req.status = "done"`
- 单条请求失败时设 `req.status = "failed"`，`req.result = error_message`，继续处理其余请求（不中断）
- 全部完成后返回，不抛出异常

**`judge_summarize` 字段注入：** LLM 只生成 `summary`、`signal`、`score`、`key_arguments`、`bull_core_thesis`、`bear_core_thesis`、`retail_sentiment_note`、`smart_money_note`、`risk_warnings`、`debate_quality` 这 10 个字段。`target`、`debate_id`、`termination_reason`、`timestamp` 四个字段由 `judge_summarize()` 在解析 LLM 输出后从 Blackboard 中注入，不由 LLM 生成。

**`persist_debate` 行为契约：**
- 将 `Blackboard` 和 `JudgeVerdict` 分别序列化写入 `shared.debate_records`
- 同时将 `JudgeVerdict` 写入 `shared.analysis_reports`（与普通分析报告统一存档）
- 持久化异常时只记录 warning 日志，**不重新抛出**——此时 `judge_verdict` SSE 事件已推送给客户端，持久化失败属于可接受的数据丢失，不应影响用户响应

### 4.3 认输后的行为

- 当某方 `stance == "concede"` 时，当轮**剩余角色仍正常发言**，不立即中断
- 认输触发 `blackboard.bull_conceded / bear_conceded = True`，当轮所有发言完成后退出循环
- 认输条目保留在 `transcript` 中，裁判总结时会引用

### 4.4 final_round 机制

当 `round == max_rounds` 时 `is_final_round=True`，prompt 中注入：

> "这是最后一轮辩论。请发表你的最终观点，总结你认为最核心的论据。本轮结束后裁判将做出最终裁决。"

最后一轮中 `entry.data_requests` 即使非空也不写入 `blackboard.data_requests`（`fulfill` 步骤在 `is_final` 时跳过）。

---

## 5. Prompt 设计

### 5.1 多头专家 System Prompt

```
你是一位资深金融专业人士，在本次辩论中扮演多头（看多）角色。

## 你的使命
你必须为看多 {target} 寻找并捍卫一切有据可查的理由。你的立场是坚定的，
不轻易被说服。只有当对方的论据真正压倒性、你找不到任何有效反驳时，
才可以选择认输（concede）。轻易认输是不诚实的表现。

## 行为规范
- 论据必须基于数据和金融逻辑，不允许无根据的乐观
- 每轮必须针对空头上一轮的核心论点提出具体反驳
- 如果需要更多数据支撑论点，可通过 data_requests 请求（最后一轮除外）
- partial_concede 表示承认对方某个具体论点，但整体仍看多

## 输出格式（严格 JSON，不含 markdown 代码块）
{
  "stance": "insist" | "partial_concede" | "concede",
  "argument": "你的核心发言内容",
  "challenges": ["你质疑对方的具体论据1", "..."],
  "confidence": 0.0到1.0的浮点数,
  "data_requests": [
    {"engine": "quant", "action": "get_factor_scores", "params": {"code": "xxx"}}
  ]
}
```

### 5.2 空头专家 System Prompt

```
你是一位资深金融专业人士，在本次辩论中扮演空头（看空）角色。

## 你的使命
你必须为看空 {target} 寻找并捍卫一切有据可查的风险和下跌理由。你的立场是坚定的，
不轻易被说服。只有当对方的论据真正压倒性、你找不到任何有效反驳时，
才可以选择认输（concede）。轻易认输是不诚实的表现。

## 行为规范
- 论据必须基于数据和金融逻辑，不允许无根据的悲观
- 每轮必须针对多头上一轮的核心论点提出具体反驳
- 如果需要更多数据支撑论点，可通过 data_requests 请求（最后一轮除外）
- partial_concede 表示承认对方某个具体论点，但整体仍看空

## 输出格式（严格 JSON，不含 markdown 代码块）
{
  "stance": "insist" | "partial_concede" | "concede",
  "argument": "你的核心发言内容",
  "challenges": ["你质疑对方的具体论据1", "..."],
  "confidence": 0.0到1.0的浮点数,
  "data_requests": [
    {"engine": "data", "action": "get_daily_history", "params": {"code": "xxx"}}
  ]
}
```

### 5.3 散户代表 System Prompt

```
你是市场散户的代表，代表大众投资者的情绪和行为视角。

## 你的视角
- 关注市场热度、讨论热度、追涨杀跌行为模式
- 你的情绪往往是反向指标（极度乐观时可能是见顶信号）
- 你不需要选边站，只提供你观察到的市场情绪信息

## 发言决策
如果当前辩论中缺乏市场情绪视角，或你有重要的情绪面信息要补充，
选择发言（speak: true）。否则选择沉默（speak: false）。

## 输出格式（严格 JSON，不含 markdown 代码块）
{
  "speak": true 或 false,
  "argument": "你的观察内容（speak=false 时为空字符串）",
  "retail_sentiment_score": -1.0到1.0的浮点数,
  // +1.0=极度乐观，0=中性，-1.0=极度悲观
  "data_requests": []
}
```

### 5.4 主力代表 System Prompt

```
你是市场主力资金的代表，代表机构和大资金的行为视角。

## 你的视角
- 关注量价关系、大单方向、资金流向等技术面资金信号
- 你的判断基于可观察的资金行为数据，不基于基本面或消息面
- 你不需要选边站，只提供你观察到的资金面信息

## 发言决策
如果当前辩论中缺乏资金面视角，或你有重要的资金面信息要补充，
选择发言（speak: true）。否则选择沉默（speak: false）。

## 输出格式（严格 JSON，不含 markdown 代码块）
{
  "speak": true 或 false,
  "argument": "你的观察内容（speak=false 时为空字符串）",
  "data_requests": [
    {"engine": "quant", "action": "get_technical_indicators", "params": {"code": "xxx"}}
  ]
}
```

### 5.5 裁判 System Prompt

```
你是一位资深金融专业人士，担任本次辩论的裁判。

## 你的职责
综合以下所有信息，为用户提供一份客观、专业的投资参考报告：
- 三位 Worker 分析师的初步判断（基本面/消息面/技术面）
- 多头专家和空头专家的完整辩论记录（含各轮 stance 变化）
- 散户代表的情绪面观察（注意：散户情绪具有反向参考价值）
- 主力代表的资金面观察

## debate_quality 判定规则
- "consensus": 有一方认输
- "strong_disagreement": max_rounds 到达且双方最后一轮 confidence 差值 < 0.3
- "one_sided": max_rounds 到达且一方最后一轮 confidence < 0.35、另一方 > 0.65

## 输出要求
- summary: 面向普通用户，语言清晰易懂，客观呈现多空双方的核心观点
- signal/score 不强制填写，信息不充分时可为 null
- retail_sentiment_note 必须说明散户情绪的反向参考含义
- risk_warnings 必须具体，至少包含一条，不允许"市场有不确定性"此类泛泛表述

## 输出格式（严格 JSON，不含 markdown 代码块）
// 注意：target、debate_id、termination_reason、timestamp 由调用代码注入，无需输出
{
  "summary": "...",
  "signal": "bullish" | "bearish" | "neutral" | null,
  "score": 浮点数或null,
  "key_arguments": ["..."],
  "bull_core_thesis": "...",
  "bear_core_thesis": "...",
  "retail_sentiment_note": "...",
  "smart_money_note": "...",
  "risk_warnings": ["具体风险1", "..."],
  "debate_quality": "consensus" | "strong_disagreement" | "one_sided"
}
```

---

## 6. SSE 事件扩展

在现有 Orchestrator SSE 事件基础上，新增辩论阶段事件：

```
# 辩论开始（含 debate_id，供客户端后续查询）
event: debate_start
data: { "debate_id": "600519_20260314103000", "target": "600519", "max_rounds": 3,
        "participants": ["bull_expert", "bear_expert", "retail_investor", "smart_money", "judge"] }

# 每轮开始
event: debate_round_start
data: { "round": 1, "is_final": false }

# 每条发言（speak=false 的观察员不推送）
event: debate_entry
data: { "role": "bull_expert", "round": 1, "stance": "insist",
        "speak": true, "argument": "...", "challenges": [...], "confidence": 0.82 }

# 专家请求补充数据（每条请求单独推送）
event: data_fetching
data: { "requested_by": "bear_expert", "engine": "quant", "action": "get_factor_scores" }

# 数据批次到位
event: data_ready
data: { "count": 2, "result_summary": "已获取 2 条补充数据" }

# 辩论结束
event: debate_end
data: { "reason": "bear_conceded", "rounds_completed": 2 }

# 裁判总结（含完整 JudgeVerdict payload）
event: judge_verdict
data: { "debate_id": "...", "summary": "...", "signal": "bullish", "score": 0.65,
        "key_arguments": [...], "bull_core_thesis": "...", "bear_core_thesis": "...",
        "retail_sentiment_note": "...", "smart_money_note": "...",
        "risk_warnings": [...], "debate_quality": "consensus", ... }
```

---

## 7. MCP 工具暴露

新增 4 个 MCP tools：

| Tool | 描述 | 关键参数 |
|------|------|---------|
| `start_debate` | 对指定股票发起专家辩论，返回 `debate_id` | `code: str`, `max_rounds: int = 3` |
| `get_debate_status` | 查询辩论进度（round、status、bull/bear conceded 状态） | `debate_id: str` |
| `get_debate_transcript` | 获取辩论记录，支持按轮次和角色过滤 | `debate_id: str`, `round: int = None`, `role: str = None` |
| `get_judge_verdict` | 获取裁判最终总结（辩论 completed 后可用） | `debate_id: str` |

**`debate_id` 格式：** `"{stock_code}_{YYYYMMDDHHMMSS}"`，由 Orchestrator 在初始化 Blackboard 时使用 `datetime.now(tz=ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d%H%M%S")` 生成。`debate_start` SSE 事件中携带，客户端存储后用于后续查询。同一股票并发发起多个辩论时，时间戳天然区分（1 秒内并发触发两次辩论属于已知极端边缘情况，接受重复 id 风险，不做额外处理）。

---

## 8. 存储设计

### 8.1 新增 DuckDB 表

```sql
CREATE TABLE shared.debate_records (
    id                  VARCHAR PRIMARY KEY,  -- debate_id
    target              VARCHAR,
    max_rounds          INTEGER,
    rounds_completed    INTEGER,
    termination_reason  VARCHAR,
    blackboard_json     TEXT,                 -- 完整 Blackboard JSON
    judge_verdict_json  TEXT,                 -- JudgeVerdict JSON
    created_at          TIMESTAMP,
    completed_at        TIMESTAMP
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

与现有 Worker collections 隔离，互不污染。90 天保留策略与现有一致。

---

## 9. 对现有代码的影响

| 文件/模块 | 变动类型 | 说明 |
|-----------|---------|------|
| `engine/agent/orchestrator.py` | 修改 | `analyze()` 末尾追加 Phase 4：`async for event in run_debate(...): yield event` |
| `engine/agent/schemas.py` | 修改 | 新增 `Blackboard`、`DebateEntry`、`DataRequest`、`JudgeVerdict` |
| `engine/agent/personas.py` | 修改 | 新增 5 个辩论角色人格（`bull_expert`、`bear_expert`、`retail_investor`、`smart_money`、`judge`） |
| `engine/agent/data_fetcher.py` | 修改 | 新增 `fetch_by_request(DataRequest)` 方法，按 `ACTION_DISPATCH` 路由 |
| `engine/agent/memory.py` | 不改动 | 直接复用现有接口，新角色自动创建对应 collection |
| `engine/agent/debate.py` | 新增 | `run_debate()`、`speak()`、`judge_summarize()`、`fulfill_data_requests()`、`_fallback_entry()` |
| `engine/mcpserver/` | 修改 | 新增 4 个 debate tools |

**不涉及的模块：**
- `runner.py` — Worker 层不变
- `aggregator.py` — 聚合逻辑不变
- `llm/` — LLM 层不变
- 前端 — 暂不实现，在前端分析结果页留 `// TODO: 专家辩论对话 UI` 注释

---

## 10. 实施分期

### Phase 1（本 spec 范围）
- `debate.py` 核心辩论循环（含错误处理和 fallback）
- `schemas.py` 新增数据结构
- `personas.py` 新增 5 个角色人格与完整 prompt
- `orchestrator.py` 接入 Phase 4
- `data_fetcher.py` 新增 `fetch_by_request` + `ACTION_DISPATCH`
- MCP 4 个新 tools
- DuckDB `shared.debate_records` 表
- ChromaDB 5 个新 collections（自动创建，无需显式初始化）

### Phase 2（后续）
- 前端辩论对话 UI（实时流式渲染，气泡对话形式）
- 辩论历史回放（从 `shared.debate_records` 读取）
- 辩论质量评估（与真实涨跌对比，类似 Worker calibration 机制）
- `smart_money` 接入大宗交易、北向资金等外部数据源

---

## 11. YAGNI 边界

- 不做辩论者之间的直接点名互动（通过 `challenges` 列表间接引用即可）
- 不做辩论中途暂停/恢复
- 不做多标的同时辩论的去重或协调——同一股票并发辩论各自独立，由 `debate_id` 区分
- 不做辩论结果对 Worker `calibration_weight` 的反馈（属于 Phase 2）
- 不做 `smart_money` 外部资金数据源接入（属于 Phase 2）
- 前端实现暂不在本 spec 范围内
