# Agent Decision Quality Loop Design

> 编写日期：2026-03-22
> 范围：收紧 Main Agent 的决策提示词、信息免疫、自我质疑和执行门禁，让已有的 wake/data-hunger 能力真正提升决策质量，而不是只增加更多上下文。

---

## 1. 背景

当前 Main Agent 已具备：

- 候选筛选、基础分析、自动执行
- `watch_signals` / `info_digests`
- `thinking_process`、`state_before/after`、`execution_summary`
- 每日/每周复盘骨架

但真正的决策环节仍然过于原始。当前 [brain.py](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/brain.py) 的 `_make_decisions()` 基本是：

1. 把账户、候选分析、digest 文本拼成一段 user prompt
2. 让模型直接输出交易 JSON
3. 只做 JSON 解析，不做高质量审查

这会导致三个问题：

- digest 被“看见了”，但没有变成明确的信息免疫框架
- LLM 没有强制做自我质疑，容易把弱证据包装成强决策
- 决策输出没有执行前门禁，低质量动作仍可能落到 execution

所以现在系统虽然比之前“知道更多”，但并没有形成“知道更多以后更谨慎、更可审计”的闭环。

---

## 2. 目标

本批次只做决策质量闭环，不扩新页面、不扩新表：

1. 把决策提示词拆成稳定结构：`system + decision context + output contract`
2. 把 DataHunger 的信息免疫原则显式注入决策流程
3. 要求模型先做自我质疑，再给可执行动作
4. 在执行前加一个最小门禁，过滤证据不足或字段不完整的动作
5. 把 critique / follow-up / gating 结果落进 `thinking_process`

---

## 3. 非目标

本批次不做：

- 新数据库表
- 新前端 panel
- 完整多轮 clarification conversation
- digest 级别复盘表
- expert 侧 RAG / belief 系统接入 Main Agent

这些都依赖先把单次决策质量闭环打稳。

---

## 4. 方案对比

### 方案 A：只改现有大 prompt

做法：

- 在原 prompt 里追加几段规则
- 保持单次 JSON 输出

优点：

- 改动最小

缺点：

- `brain.py` 会继续膨胀
- prompt 与解析、门禁、审计混在一起
- 很难单测

### 方案 B：抽出决策规范层，并做单次“先质疑后决策”的结构化输出

做法：

- 抽出 prompt builder / response parser / decision gate
- system prompt 固化人格和信息原则
- user prompt 只提供运行上下文
- 要求模型输出：
  - `assessment`
  - `self_critique`
  - `follow_up_questions`
  - `decisions`
- 执行前由 gate 过滤不可执行动作

优点：

- 最小重构就能显著提高可维护性
- 可针对 prompt、parse、gate 写单测
- 不需要多一次 LLM 调用，成本可控

缺点：

- 仍然是单轮推理，不是真正的多阶段 planner

### 方案 C：两段式 LLM 流程（分析器 + 决策器）

做法：

- 第一段只做 evidence assessment / critique
- 第二段基于第一段结构化结论输出交易动作

优点：

- 质量上限更高

缺点：

- 调用成本和时延都增加
- 现在还没有必要

本批次采用方案 B。

---

## 5. 核心设计

### 5.1 决策输出改为“分析 + 质疑 + 动作”一体结构

模型不再直接返回一个交易数组，而是返回：

```json
{
  "assessment": {
    "market_posture": "neutral",
    "evidence_quality": "mixed"
  },
  "self_critique": [
    "公告信息不足以单独改变策略"
  ],
  "follow_up_questions": [
    "是否已经看到量价确认？"
  ],
  "decisions": [
    {
      "stock_code": "600519",
      "action": "buy",
      "confidence": 0.72,
      "price": 1750,
      "quantity": 100,
      "take_profit": 1820,
      "stop_loss": 1690,
      "reasoning": "..."
    }
  ]
}
```

`decisions` 仍是 execution 唯一输入，但现在它前面必须有一层自我解释。

### 5.2 信息免疫框架进入 system prompt

system prompt 收敛四类原则：

- 默认怀疑消息面，不因为单条消息直接改变策略
- 优先相信 Tier 1 证据：行情、成交、财报原文、交易所数据
- digest 只能辅助，不足以替代价格/仓位纪律
- 证据不足时应输出空动作，并给出 follow-up questions

这里不做可配置 prompt 系统，先用常量和 builder 固化。

### 5.3 决策门禁

LLM 输出的动作在进入 execution 前增加 gate：

- 必填字段缺失：丢弃
- `confidence` 低于阈值：丢弃
- 缺 `take_profit` / `stop_loss`：丢弃
- `price <= 0` / `quantity <= 0`：丢弃
- `self_critique` 明确指出“证据不足且需等待确认”时：全部动作丢弃

gate 的目标不是“证明动作一定正确”，而是拦掉明显不该执行的动作。

### 5.4 `thinking_process` 扩展但不改 schema

继续复用现有 JSON 字段，补充：

- `system_prompt`
- `decision_context`
- `raw_output`
- `parsed_payload`
- `gate_result`
- `self_critique`
- `follow_up_questions`

这样前端和 DB schema 暂时都不用变。

---

## 6. 模块边界

### 6.1 新增 `backend/engine/agent/decision_quality.py`

职责：

- 构建 system prompt
- 构建 decision context
- 解析 LLM JSON payload
- 执行决策门禁

这部分尽量保持纯函数，方便单测。

### 6.2 `backend/engine/agent/brain.py`

职责调整为：

- 收集 portfolio / analysis / digest / memory
- 调用 decision quality builder 组装 prompt
- 调用 LLM
- 调用 parser + gate
- 持久化审计结果
- 只把 gate 后的动作交给 execution

`brain.py` 不再自己直接拼接整段巨型 prompt。

---

## 7. 错误处理

- LLM 输出解析失败：记录 `raw_output`，返回空动作
- critique / decisions 字段缺失：按空列表处理
- gate 全部拦截：run 仍然视为成功完成，只是 `decision_count=0`
- 不因为 prompt builder 或 gate 的局部异常让整次 run 失败；失败则退化为空动作

---

## 8. 测试策略

重点做后端单测，不做 UI 改动：

1. prompt builder 测试
   - system prompt 包含信息免疫原则
   - decision context 包含 digest / signal / memory
2. parser 测试
   - fenced JSON / plain JSON / malformed JSON
3. gate 测试
   - critique 明示证据不足时清空动作
   - 缺字段、低 confidence、非法价格数量时剔除
4. brain 回归测试
   - `thinking_process` 包含 critique / follow-up / gate_result
   - 被 gate 拦截时不生成 plan/trade

---

## 9. 后续衔接

这个批次做完之后，下一步才值得继续：

- 把 `info_digests` 复盘接进 `ReviewEngine`
- 把 `follow_up_questions` 变成 wake/watch signal 建议
- 再考虑两段式 LLM 或模型分层

如果现在直接做“更多数据源”或“更多人格”，只会放大当前决策环节的噪音。
