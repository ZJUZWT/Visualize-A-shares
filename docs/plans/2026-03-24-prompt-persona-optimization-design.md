# Prompt Persona Optimization Design

> 编写日期：2026-03-24
> 范围：只收敛 `expert` 对话链路中的两种人格，确保“投资顾问”和“短线专家”在同一问题上能稳定输出不同视角，必要时允许结论冲突。

---

## 1. 背景

当前仓库已经有两套人格入口：

- `rag` / 投资顾问
- `short_term` / 短线专家

对应代码主要集中在：

- `backend/engine/expert/personas.py`
- `backend/engine/expert/agent.py`

现状问题不是“没有两个人格”，而是“两个人格的身份差异仍然不够稳定”：

- `think` 阶段已经有两段独立 prompt，但结构几乎平行，缺少可维护的人格资产层
- `reply` 阶段短线专家已有比较强的角色感，投资顾问则仍然是大段内联字符串，维护成本高
- few-shot 没有被当作第一等 prompt 资产管理
- “同一只票允许结论冲突”还停留在设计意图，没有被明确写入人格行为约束

用户要的本质不是“prompt 更长”，而是：

1. 两个 AI 要像不同风格的真实操盘手
2. 同一问题下，允许他们给出不同意见
3. 这种差异要稳定、可测试、可维护

---

## 2. 目标

本批次完成后，`expert` 对话人格应满足：

1. `rag` 投资顾问的人格稳定体现：
   - 长线视角
   - 基本面锚定
   - 安全边际
   - 仓位管理
   - 不追涨、不做日内交易判断
2. `short_term` 短线专家的人格稳定体现：
   - 节奏、量价、盘口、资金博弈
   - 强调时机和执行
   - 不谈估值中枢、长期持有、三年逻辑
3. 同一问题下，两个 persona 可以合理冲突：
   - 投资顾问偏“值不值、风险收益比、该不该等”
   - 短线专家偏“能不能做、什么时候做、做错怎么撤”
4. 人格差异通过结构化配置和测试固定下来，而不是散落在多段手写字符串中

---

## 3. 非目标

本批次不做：

- `arena` / 辩论人格重构
- `agent` 主脑人格改造
- 前端新增“人格冲突卡片”
- 动态 few-shot 检索
- Clarification Phase / Superpower 深思考模式
- 生产部署、性能优化、多市场扩展

这轮只做 `expert` 对话人格本身。

---

## 4. 设计决策

### 4.1 将人格从“长字符串”升级为“结构化画像 + 渲染函数”

在 `backend/engine/expert/personas.py` 中新增统一的人格配置层，至少包含：

- `label`
- `identity`
- `think_principles`
- `reply_principles`
- `forbidden_topics`
- `conflict_posture`
- `few_shot_examples`
- `recommended_tool_bias`

然后由两个函数统一生成 prompt：

- `build_think_prompt(persona, current_date, graph_context, memory_context)`
- `build_reply_system(persona, current_date, context_blocks)`

这样做的好处：

- 人格资产集中
- few-shot 可测试
- `agent.py` 不再维护多段重复 prompt 分支
- 后续增加第三种 persona 时成本更低

### 4.2 保留现有 persona 路由，不改 API contract

本轮不改 persona 入口：

- `rag` 仍表示投资顾问
- `short_term` 仍表示短线专家

原因：

- 现有前后端和调度代码已经依赖这个枚举
- 用户要的是“人格差异更强”，不是“persona 命名体系重构”

### 4.3 把“允许冲突”写成显式 prompt 规则

冲突不是副作用，而是设计目标。

两种 persona 都明确写入：

- 不需要与另一人格保持一致
- 如果你的分析框架支持相反结论，应直接给出相反结论
- 相同标的可以出现“长线不买、短线可做”的分歧

这样模型不会因为“追求一致”而收敛成同一套答案。

### 4.4 few-shot 用“代表性立场样例”，不做动态检索

每种 persona 放 3-5 个固定 few-shot：

- 投资顾问样例：高估值蓝筹、无安全边际成长股、已有仓位如何控仓
- 短线专家样例：放量突破、缩量回踩、龙头与跟风辨识、止损纪律

few-shot 重点不是覆盖所有问题，而是把“说话方式”和“决策优先级”钉死。

### 4.5 回复风格与思考风格都走统一 builder

本轮同时改：

- `think` prompt
- `reply` prompt

如果只改 reply，不改 think，专家拆题和工具调度仍可能趋同；
如果只改 think，不改 reply，用户看到的回答仍会像“同一个人换模板”。

---

## 5. 实现边界

### 5.1 修改文件

- `backend/engine/expert/personas.py`
- `backend/engine/expert/agent.py`
- `tests/unit/expert/test_personas.py`

必要时可补：

- `tests/unit/expert/test_agent.py` 或现有 expert 相关测试文件

### 5.2 不改文件

- `backend/engine/arena/*`
- `frontend/*`
- `backend/engine/agent/*`

---

## 6. 完成定义

本模块被视为完成的标准：

1. `rag` 与 `short_term` 的 think/reply prompt 均来自统一配置渲染
2. few-shot 已进入 prompt 资产层
3. prompt 中明确体现：
   - 投资顾问的长期框架与禁忌
   - 短线专家的交易框架与禁忌
   - 允许人格冲突
4. 单测能证明两种 persona 的 prompt 在身份、禁忌、决策框架、few-shot 上明显不同
5. 现有 expert persona 相关测试继续通过

---

## 7. 测试策略

优先做 prompt contract 测试，而不是依赖真实 LLM 输出：

- `tests/unit/expert/test_personas.py`

覆盖：

- structured persona profile 是否存在
- 投资顾问 prompt 是否包含安全边际 / 仓位管理 / 禁止追涨
- 短线专家 prompt 是否包含量价 / 节奏 / 止损纪律 / 禁止长期估值叙事
- 两种 persona 的 conflict posture 是否明确写入
- few-shot 是否存在且差异化

如果需要，再补小范围 expert agent 调用链测试，确认 builder 已被接入。

---

## 8. 结论

这一轮不追求“更华丽的 prompt”，而是把人格真正做成可维护的系统资产。

落地方式是：

- 结构化 persona profile
- 统一 prompt builder
- 明确冲突立场
- 固定 few-shot 样例
- 用测试锁住差异

这样才能让两个 AI 持续像“两位不同的人”，而不是“同一个模型的两种语气”。
