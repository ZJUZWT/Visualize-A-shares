# 评委每轮评估系统设计

## 背景

当前辩论系统中，专家的 confidence 和裁判最终 score 完全由 LLM 自由发挥，缺乏数据驱动。导致：
- 每次辩论的 confidence 变化模式高度相似（多头 0.85→0.75→0.45，空头 0.85→0.85→0.95）
- 最终 score 总是落在 -0.6 到 -0.75 区间，没有区分度
- 无法判断专家是"有理有据"还是"嘴硬"

## 目标

引入评委每轮评估机制，用三维 confidence 体系替代现有的单一自评 confidence，让数据有实际意义。

## 设计

### 1. 三维 Confidence 体系

每轮每个辩论专家（多头/空头）有三个 confidence：

| 维度 | 来源 | 含义 |
|------|------|------|
| `self_confidence` | 专家公开宣称 | 可能嘴硬 |
| `inner_confidence` | 专家内心真实想法 | prompt 要求诚实反映是否被说服 |
| `judge_confidence` | 评委客观评估 | 基于论据质量、数据引用、反驳有效性 |

示例解读：
- 公开 0.85 / 内心 0.55 / 评委 0.40 → 明显在嘴硬
- 公开 0.85 / 内心 0.80 / 评委 0.82 → 有理有据

### 2. 专家内心 Confidence（inner_confidence）

在 `extract_structure` 的 prompt 中新增 `inner_confidence` 字段：

> "stance 是你的公开立场（可以嘴硬），inner_confidence 是你内心的真实想法——如果对方的某个论据确实让你动摇了，这里要诚实反映。"

`self_confidence` 沿用现有的 `confidence` 字段（专家公开宣称的）。

### 3. 评委每轮小评（RoundEval）

每轮末尾，评委基于以下信息做一次小评：
- 本轮多头发言 + 空头发言
- 本轮观察员发言（散户情绪 + 主力资金）
- 黑板上已有的数据（因子评分、技术指标、资金流向等）
- 前几轮的评估历史（confidence 变化趋势）

#### 输出结构（RoundEval）

```python
class RoundEvalSide(BaseModel):
    self_confidence: float      # 专家公开宣称
    inner_confidence: float     # 专家内心真实
    judge_confidence: float     # 评委客观评估

class RoundEval(BaseModel):
    round: int
    bull: RoundEvalSide
    bear: RoundEvalSide
    bull_reasoning: str         # 评委对多头本轮的简评
    bear_reasoning: str         # 评委对空头本轮的简评
    data_utilization: dict      # 双方对黑板数据的引用情况
```

#### 辩论流程变化

现有流程：
```
每轮: 多头发言 → 空头发言 → 观察员发言 → 数据请求
```

新流程：
```
每轮: 多头发言 → 空头发言 → 观察员发言 → 数据请求 → 评委小评
```

评委小评作为新的 SSE 事件 `judge_round_eval` 推送给前端。

#### 存储

`Blackboard` 新增字段 `round_evals: list[RoundEval]`。

### 4. 对最终裁决 Score 的影响

最终 score 由数据驱动，不再完全依赖 LLM 自由发挥：

```python
# 取最后一轮的评委 confidence
bull_final = round_evals[-1].bull.judge_confidence
bear_final = round_evals[-1].bear.judge_confidence

# score = 多头可信度 - 空头可信度，归一化到 [-1, 1]
calculated_score = bull_final - bear_final

# 裁判 LLM 的主观 score 作为参考
final_score = calculated_score * 0.7 + llm_score * 0.3
```

### 5. SSE 事件

新增事件 `judge_round_eval`：

```json
{
  "event": "judge_round_eval",
  "data": {
    "round": 2,
    "bull": { "self_confidence": 0.85, "inner_confidence": 0.55, "judge_confidence": 0.40 },
    "bear": { "self_confidence": 0.85, "inner_confidence": 0.80, "judge_confidence": 0.82 },
    "bull_reasoning": "多头本轮引用了PE数据，但未能反驳毛利率质疑",
    "bear_reasoning": "空头用财报数据有效拆解了成长叙事",
    "data_utilization": { "bull": ["get_stock_info"], "bear": ["get_financials", "get_technical_indicators"] }
  }
}
```

### 6. 前端变化

- `useDebateStore` 新增 `roundEvals` 状态，处理 `judge_round_eval` 事件
- `RoleCard` 的 confidence 显示改为评委给的 `judge_confidence`
- 可选：RoleCard 展示三维 confidence 对比（公开/内心/评委）
- 收到 `judge_round_eval` 后更新 `roleState` 中的 confidence

### 7. 涉及文件

| 文件 | 改动 |
|------|------|
| `engine/agent/schemas.py` | 新增 `RoundEval`、`RoundEvalSide`；`Blackboard` 加 `round_evals` |
| `engine/agent/debate.py` | 新增 `judge_round_eval()` 函数；`run_debate` 每轮末尾调用；`extract_structure` prompt 加 `inner_confidence` |
| `engine/agent/personas.py` | 新增评委小评 prompt 模板 |
| `web/stores/useDebateStore.ts` | 处理 `judge_round_eval` 事件，更新 roleState |
| `web/types/debate.ts` | 新增 `RoundEval` 类型 |
| `web/components/debate/RoleCard.tsx` | 展示三维 confidence |
