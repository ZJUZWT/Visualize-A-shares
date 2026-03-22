# Agent Wake DataHunger Design

> 编写日期：2026-03-22
> 范围：为 Main Agent 增加最小自主观察闭环，让 `/agent` 从“可聊天、可记账”推进到“会主动看、会主动消化、会留下证据”。

---

## 1. 背景

当前 Main Agent 已经具备三类能力：

- `agent.chat_*` 与策略采纳/否决，让 `/agent` 可以承载策略讨论
- `agent_state`、`brain_runs`、ledger/read model，让 Agent 的状态、运行和执行结果可见
- `review_records`、`weekly_summaries`、`agent_memories`、`weekly_reflections`，让复盘和经验规则开始形成闭环

但最关键的一层还缺失：Agent 还不会“主动找证据再决策”。

当前 [`backend/engine/agent/brain.py`](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/brain.py) 的核心流程仍是：

1. 合并候选标的
2. 拉少量行情/指标
3. 直接交给 LLM 做决策
4. 写入计划和交易

这导致三个直接问题：

- 没有 `watch_signals`，Agent 无法表达“我在等什么信号”
- 没有 `DataHunger` 层，Agent 无法把新闻、公告、产业链、资金结构消化成稳定证据
- `brain_runs` 虽然有 `thinking_process`，但没有“这次决策到底看了哪些信息”的审计对象

所以现在 `/agent` 更像一个带账本的控制台，不像一个会主动跟踪市场条件的投资代理。

---

## 2. 目标

本批次只做一个最小自主闭环：

1. Agent 可以持久化“等待中的观察信号”
2. Agent 可以在 run 中主动抓取并摘要多源信息
3. Agent 决策 prompt 消费 digest，而不是直接消费生数据
4. `brain_runs` 能追溯本次 run 参考了哪些 digest 和哪些触发信号

闭环打通后，后续能力才有稳定落点：

- 信息免疫 prompt
- 盘中轻量扫描
- 每日信息复盘
- 回测/重放学习
- `/agent` 新增 watch signal 与 digest 面板

---

## 3. 非目标

本阶段不做：

- 新的 `/agent` 大面板改版
- 盘中高频调度和多频 wake 策略
- 完整自治交易代理
- 把产业链事实写入长期 memory 或 KnowledgeGraph
- LLM 分层、prefetch、并行优化的完整落地

这些都依赖先有稳定的观察层对象。

---

## 4. 设计原则

### 4.1 先消化，再决策

`AgentBrain` 不应该直接把原始新闻、公告、行业长文本喂给最终决策 prompt。

先由 `DataHunger` 把多源输入压缩为结构化 digest，再由 `brain` 消费 digest 结果。这样后续才容易做：

- 快模型做 digest
- 大模型做最终决策
- digest 的缓存与复用
- digest 的单独复盘

### 4.2 事实不进长期认知，观点才进长期认知

产业链上下游、行业映射、资金结构是“会变化的事实”。这些事实不应长期写入 Agent memory。

长期保留的应是：

- 经验规则
- 已验证的策略偏好
- 对某行业/某标的的阶段性判断摘要

### 4.3 信号和记忆分离

- `agent_memories` 表示“我从过去学到了什么”
- `watch_signals` 表示“我接下来在等什么发生”

二者不能混用，否则很快会把规则库污染成待办列表。

### 4.4 部分失败可继续

`DataHunger` 对某个标的抓不到部分数据，不应导致整次 run 失败。

只要能明确：

- 哪些源成功
- 哪些源缺失
- 当前 digest 置信度受什么影响

run 就应该继续。

---

## 5. 目标对象

### 5.1 WatchSignal

新增 `agent.watch_signals`，表示 Agent 或用户声明的等待条件。

建议最小字段：

```sql
CREATE TABLE IF NOT EXISTS agent.watch_signals (
    id VARCHAR PRIMARY KEY,
    portfolio_id VARCHAR NOT NULL,
    stock_code VARCHAR,
    sector VARCHAR,
    signal_description TEXT NOT NULL,
    check_engine VARCHAR NOT NULL,
    keywords JSON,
    if_triggered TEXT,
    cycle_context TEXT,
    status VARCHAR DEFAULT 'watching',
    trigger_evidence JSON,
    source_run_id VARCHAR,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    triggered_at TIMESTAMP
);
```

状态机先收敛成：

- `watching`
- `analyzing`
- `triggered`
- `failed`
- `expired`
- `cancelled`

`failed` 不是最终放弃，而是“本次触发后的深度分析失败”，方便后续重试。

### 5.2 InfoDigest

新增 `agent.info_digests`，表示某次 run 对某个标的完成的一次信息消化结果。

建议最小字段：

```sql
CREATE TABLE IF NOT EXISTS agent.info_digests (
    id VARCHAR PRIMARY KEY,
    portfolio_id VARCHAR NOT NULL,
    run_id VARCHAR NOT NULL,
    stock_code VARCHAR NOT NULL,
    digest_type VARCHAR NOT NULL,
    raw_summary JSON,
    structured_summary JSON,
    strategy_relevance TEXT,
    impact_assessment VARCHAR NOT NULL,
    missing_sources JSON,
    created_at TIMESTAMP DEFAULT now()
);
```

这里不追求事件溯源级别细粒度，先保证：

- 一次 run 对一个标的可以产出一个 digest
- digest 能说明“看了什么”和“缺了什么”
- 后续能被 `brain_runs` 和前端读模型引用

### 5.3 BrainRun 扩展

现有 `brain_runs` 继续作为单次运行主对象，但要补充 digest 关联信息。

MVP 推荐新增：

- `info_digest_ids JSON`
- `triggered_signal_ids JSON`

这样现有 run 读模型改动小，不需要第一批就做复杂 join。

后续如果 digest 查询变重，再演进到专门 read model。

---

## 6. 模块边界

### 6.1 `backend/engine/agent/data_hunger.py`

新增模块，负责三件事：

1. `query_industry_context(stock_code)`
2. `scan_watch_signals(portfolio_id)`
3. `execute_and_digest(portfolio_id, run_id, stock_code, triggers)`

这是本批次的新增核心边界。

### 6.2 `backend/engine/agent/brain.py`

职责调整为：

1. 筛选候选
2. 请求 `DataHunger` 产出 digest
3. 用 digest + state + memory 生成决策
4. 把决策交给 execution

不再自己拼“原始情报 + 原始指标 + 决策 prompt”的所有细节。

### 6.3 `backend/engine/agent/service.py`

MVP 中继续承载：

- `watch_signals` CRUD
- `info_digests` 查询
- `brain_runs` 的 digest 关联写入

原因：

- 这批目标是打通闭环，而不是重写 service 边界
- `service.py` 已经是当前 API 门面，先复用能减少迁移成本

后续如果 `watch_signals` 继续膨胀，再单拆模块。

### 6.4 `backend/engine/agent/scheduler.py`

本批次只要求它和 manual run 走相同 wake path。

不新增新的 cron job。

调度策略保持保守：

- 每日 run
- 每日 review
- 每周 review

真正的“盘中轻扫”留到下一批。

---

## 7. 数据流

### 7.1 Run 入口

`AgentBrain.execute(run_id)` 新流程：

1. 读取 `state_before`
2. 读取 active memory rules
3. 扫描 `watch_signals`
4. 合并候选标的
5. 对候选标的执行 `DataHunger.execute_and_digest()`
6. 把 digest 结果写入 `info_digests`
7. 用 digest 摘要生成决策
8. 执行决策
9. 写回 `state_after`、`info_digest_ids`、`triggered_signal_ids`

### 7.2 WatchSignal 扫描

MVP 扫描只支持关键词命中模式：

- `check_engine = info`
- 基于 `news` / `announcements` 标题和摘要
- 命中后从 `watching -> analyzing`
- 深度分析成功且确认有效，再进入 `triggered`

这样能先把对象语义跑通，不必第一批就支持 data/industry 多引擎触发器。

### 7.3 `query_industry_context(stock_code)`

建议行为：

1. 通过 `IndustryEngine.analyze(stock_code)` 取行业认知
2. 通过 `IndustryEngine.get_capital_structure(stock_code)` 补资金结构
3. 归一为一个轻量上下文对象：

```json
{
  "industry": "光伏设备",
  "cycle_position": "...",
  "key_drivers": ["..."],
  "next_catalysts": ["..."],
  "capital_summary": "...",
  "risk_points": ["..."]
}
```

如果行业无法解析，返回 `null` 而不是抛异常。

### 7.4 `execute_and_digest()`

并发抓取：

- `news`
- `announcements`
- `industry_context`
- `capital_structure`
- `daily_history`
- `technical_indicators`

再做一次 digest，总结成：

```json
{
  "summary": "...",
  "key_evidence": ["..."],
  "risk_flags": ["..."],
  "impact_assessment": "none|noted|minor_adjust|reassess",
  "watch_signal_updates": ["..."],
  "missing_sources": ["announcements"]
}
```

这里的 `impact_assessment` 是给最终决策 prompt 用的压缩标签，不是最终交易结论。

---

## 8. Prompt 策略

### 8.1 Digest Prompt

新增一层信息消化 prompt，目标不是生成交易建议，而是回答：

1. 这批新信息里最值得看的是什么
2. 哪些只是噪声
3. 是否动摇已有论点
4. 现在应该继续等待、轻微调整，还是重新评估

这一步后续最适合接“快模型”。

### 8.2 Brain Decision Prompt

`brain` 只消费：

- 当前账户与状态
- active memory rules
- watch signal 命中摘要
- digest 产出的结构化结论

不直接吞所有原始材料。

这会明显降低：

- prompt 膨胀
- 低质量消息对决策的污染
- 后续 LLM 分层的改造难度

---

## 9. API 与读模型

本批次只补最小 API，不做前端大改：

- `GET /api/v1/agent/watch-signals?portfolio_id=...`
- `POST /api/v1/agent/watch-signals`
- `PATCH /api/v1/agent/watch-signals/{id}`
- `GET /api/v1/agent/info-digests?portfolio_id=...&run_id=...`

这样可以先让：

- 手工验证后端行为
- `/agent` 后续增面板时直接复用

不必在第一批就绑进复杂 UI。

---

## 10. 错误处理

### 10.1 数据源失败

单数据源失败时：

- digest 保留成功部分
- `missing_sources` 记录缺失源
- `impact_assessment` 默认保守，不允许假装“确认无事”

### 10.2 信号命中后的深度分析失败

状态迁移为：

- `watching -> analyzing -> failed`

而不是直接变成 `triggered` 或回退无痕。

### 10.3 LLM 未配置

在 `IndustryEngine` 或 digest LLM 不可用时：

- `query_industry_context()` 返回退化对象或 `null`
- `execute_and_digest()` 用规则摘要降级
- 整次 run 仍可继续，但 `impact_assessment` 只能保守

---

## 11. 测试策略

本批次只做后端测试，不碰前端。

最少应覆盖：

- schema：`watch_signals`、`info_digests`、`brain_runs` 扩展字段存在
- service：watch signal CRUD 和状态迁移
- data hunger：产业上下文成功/失败、部分数据源失败降级
- brain：run 会写入 digest 关联和触发信号关联
- routes：watch signal 与 digest 读接口返回稳定 JSON
- scheduler：manual run 和 scheduled run 共用同一 wake path

---

## 12. 分阶段落地

### Phase 1

先实现：

- schema
- `DataHunger` 最小版
- 关键词型 watch signal 扫描
- `brain` digest 注入
- 最小 read API

### Phase 2

再追加：

- digest 进入复盘
- info immunity prompt 完整化
- `/agent` watch signal / digest UI
- 盘中轻扫任务

### Phase 3

最后考虑：

- 快慢模型分层
- digest 缓存与复用
- Replay / Backtesting 学习

---

## 13. 结论

这批不是“再多加几个接口”，而是给 Main Agent 补上缺失的观察层。

只有先建立：

- `watch_signals`
- `info_digests`
- `DataHunger`

后面的复盘、人格、历史训练、性能优化才不会继续绕着一个“直接拿原始数据让 LLM 判断”的脆弱核心反复返工。
