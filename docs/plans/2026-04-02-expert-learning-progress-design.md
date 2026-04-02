# Expert Learning Progress And Intent Routing Design

## 背景

当前 Expert 页还缺两块关键能力：

1. 用户看不到“专家到底学到了什么”。现有复盘、反思、经验规则主要沉淀在 `agent` 侧，Expert 页没有把这些学习结果外显出来。
2. Expert 对话入口对意图识别不够稳，像“什么是市盈率”“MACD 怎么看”这类概念/教学问题，仍可能进入澄清和选股分析流程，体验僵硬。

用户已经明确了方向：

- 不优先做“宠物成长值”体系。
- 要在 Expert 页右侧做一个中部可折叠卡片，展示“专家学到什么程度了”。
- 学习内容要以复盘/回放后的沉淀为主，而不是一般闲聊记录。
- 概念解释、方法教学类问题要被识别出来，避免误进股票分析工作流。

## 目标

- 在 Expert 页增加右侧可折叠“学习进度卡”，让用户看到当前专家可调用的复盘知识沉淀。
- 学习内容优先来自 `agent` 复盘读模型：`reviews`、`reflections`、`agent_memories`，并补充 Expert 保存的策略卡来源计数。
- 在进入澄清/分析主链前做意图分流，让概念解释、方法教学、轻量市场聊天走“无工具直答”模式。
- 保持现有股票分析、板块分析、交易决策链路不被大改。

## 非目标

- 不在这次把“宠物”系统改造成完整训练面板。
- 不做全新的长期训练任务调度器。
- 不要求 Expert 保存的每一张策略卡都立刻具备真实未来收益回放。
- 不重写现有 `ExpertAgent` / `EngineExpert` 主工作流，只做前置路由和只读聚合。

## 备选方案

### 方案 A：前端直接拼多个 Agent 接口

- 做法：Expert 页直接并发请求 `reviews/stats`、`memories`、`reflections`、`timeline/replay-learning`，由前端自己算分和筛选知识。
- 优点：后端改动少。
- 缺点：前端要复制一套聚合逻辑；不同页面难保持一致；专家侧的“学到什么”没有稳定 read model。

### 方案 B：新增 Expert 学习聚合 read model + 轻量意图路由

- 做法：后端新增 Expert 学习画像聚合接口，同时在 Expert 路由入口前增加意图分类；概念/教学走无工具直答，分析类走现有主链。
- 优点：职责清晰，Expert 页只消费稳定结构；可以显式说明“哪些是已验证知识、哪些是最近新增结论、哪些是常犯错误”；对现有分析链影响最小。
- 缺点：需要同时改后端聚合层和前端侧卡。

### 方案 C：直接做完整“训练中心/宠物成长”系统

- 做法：把复盘、经验、得分、训练日志全收拢到一个新的成长系统，再投射到 Expert 页。
- 优点：长期上限高。
- 缺点：范围明显过大，且用户已明确不希望本轮优先做这条线。

## 选型

采用 **方案 B**。

理由：

- 它能最快把“专家学到什么程度”外显出来。
- 它不依赖宠物系统，也不要求我们先搭完整训练闭环。
- 它可以诚实地区分“共享复盘底座”和“当前专家的解释侧重点”，避免虚构不存在的专家独立训练数据。

## 设计概览

本次方案由四部分组成：

1. Expert 对话入口前的 `intent router`
2. Concept / Teach / Market Chat 的“无工具直答”模式
3. 基于 Agent 复盘数据的 `expert learning profile` 聚合接口
4. Expert 页右侧中部折叠学习卡

## 一、意图分流设计

### Intent 类型

分类结果统一收敛为以下类型：

- `concept_explain`
- `method_teach`
- `market_chat`
- `stock_analysis`
- `sector_analysis`
- `trading_decision`

### 分类策略

采用“两级判断”：

1. **规则优先**：
   - 含明显概念词：`什么是`、`是什么意思`、`怎么看`、`原理`、`区别`、`举例`
   - 含明显标的词：6 位股票代码、个股名、板块/行业名、`能买吗`、`支撑位`、`止损`
   - 含明显交易词：`买入`、`卖出`、`仓位`、`止盈`、`止损`、`短线机会`
2. **LLM 兜底**：
   - 当规则判断不明确时，用一个极短的 JSON 分类 prompt 做补判
   - 仍然使用 `chat_stream()` 收集，遵守项目的流式优先原则

### 分流行为矩阵

- `concept_explain` / `method_teach`
  - 不走 clarification
  - 不启用 trade plan
  - 不触发工具/选股工作流
  - 进入“无工具直答”模式
- `market_chat`
  - 默认不走 clarification
  - 不生成 trade plan
  - 允许专家围绕市场背景做轻量解释，但不主动切入选股流程
- `stock_analysis` / `sector_analysis` / `trading_decision`
  - 保持现有链路
  - 仍可使用 clarification / deep_think / trade_plan

### 无工具直答模式

新增一个轻量 reply path：

- `EngineExpert` 增加 direct reply 流式方法
- `ExpertAgent` 增加 direct reply 流式方法
- 该模式只读取：
  - 当前用户问题
  - 近几轮对话历史
  - 当前专家 persona / system prompt
- 明确禁止：
  - 调工具
  - 进入 clarification
  - 输出交易计划卡片

回复风格要求：

- 用当前专家的角色来解释概念
- 优先讲定义、适用场景、误区
- 如果合适，可以举当前 A 股里的例子
- 但不把例子升级成“完整分析/推荐流程”

## 二、学习画像聚合设计

### 核心原则

Expert 目前没有可靠的“每个专家独立训练日志”。因此本次要诚实地把学习底座定义为：

- **共享复盘底座**：Agent 在复盘后沉淀的已验证经验、反思和稳定性指标
- **专家视角投影**：根据当前专家类型，对共享底座做不同侧重点的组织和排序

### 数据来源

主数据源：

- `agent.review_records`
- `agent.daily_reviews`
- `agent.weekly_reflections`
- `agent.agent_memories`

补充来源：

- `agent.trade_plans` 中 `source_type='expert'` 的计划数量，用于说明“当前有多少 Expert 策略卡待后验验证”

### 新接口

新增 Expert 聚合接口：

- `GET /api/v1/expert/learning/profile`

请求参数：

- `expert_type`
- `portfolio_id`
- `days`，默认 60

返回结构包含：

- `portfolio_id`
- `expert_type`
- `score_cards`
- `verified_knowledge`
- `recent_lessons`
- `common_mistakes`
- `applicability_boundaries`
- `source_summary`
- `pending_plan_summary`

### 分值设计

顶部展示 5 个固定维度：

- `决策质量`
- `风控纪律`
- `复盘沉淀度`
- `近期稳定度`
- `适用边界清晰度`

这些分值不是“绝对真值”，而是可解释的 read model，来源如下：

- `决策质量`
  - 由 `reviews/stats` 的 `win_rate`、`avg_pnl_pct` 综合估算
- `风控纪律`
  - 由亏损占比、最近最差复盘、活跃风险类记忆规则占比估算
- `复盘沉淀度`
  - 由 active memories 数量、`verify_count` 总量、反思条目数量估算
- `近期稳定度`
  - 由最近 N 条复盘的胜率、盈亏波动和连续失误情况估算
- `适用边界清晰度`
  - 由“风险/边界/不做什么”类规则和反思摘要数量估算

每个分值还要带一行短说明，告诉用户为什么是这个分。

### 内容区设计

右侧卡片底部展示四个块：

1. `已验证认知`
   - 来自 `agent_memories`
   - 按 `confidence`、`verify_count` 排序
2. `最近新增复盘结论`
   - 来自最近 `daily_reviews` / `weekly_reflections`
3. `常犯错误`
   - 从最近 loss review 与负向反思摘要中提取
4. `适用边界`
   - 从风险类 memories 和反思摘要中归纳“不适合什么场景”

### 专家视角投影

共享底座进入卡片前，按 `expert_type` 做排序偏置：

- `data`
  - 更偏向证据充分度、数据验证、估值/行情类规则
- `quant`
  - 更偏向信号稳定性、纪律、技术/节奏类规则
- `info`
  - 更偏向信息误导、缺失来源、事件解释边界
- `industry`
  - 更偏向行业周期、板块结构、适用场景边界
- `rag`
  - 平衡展示
- `short_term`
  - 更偏向风控纪律、节奏、执行窗口

这部分只改变呈现优先级，不伪造“每个专家拥有完全不同训练库”。

## 三、Portfolio 上下文设计

### 问题

Expert 页没有 portfolio 切换器，但学习画像需要 `portfolio_id`。

### 方案

采用“本地记忆 + 后端兜底”：

1. Agent 页切换 portfolio 时，把当前 `portfolio_id` 记到 localStorage
2. Expert 页优先读取这个 localStorage
3. 如果不存在或失效，则请求 `/api/v1/agent/portfolio`，自动回落到第一个可用 portfolio

这样避免给 Expert 页再加一整套 portfolio 管理 UI，同时能尽量跟随用户最近在 Agent 页操作的组合。

## 四、Expert 右侧折叠卡设计

### 位置与交互

- 固定在 Expert 页右侧中部
- 默认折叠成一枚窄标签
- 点击后展开为一个窄侧卡
- 切换专家时，卡片内容跟随刷新
- 页面窄宽时保持可折叠，不挤压主聊天区到不可用

### 卡片结构

顶部：

- 标题：`学习进度`
- portfolio 标识
- 最近更新时间

中部：

- 5 个 capability score blocks

底部：

- `已验证认知`
- `最近新增复盘结论`
- `常犯错误`
- `适用边界`
- `待验证策略卡`

### 空状态

如果当前 portfolio 没有复盘数据：

- 展示“当前还没有足够复盘数据”
- 说明需要到 Agent 页产生复盘/经验规则后，这里才会逐渐长出来
- 保留卡片外壳，不让用户误以为是加载失败

## 五、策略卡关联增强

这次不做完整“未来盘面自动复盘每张 Expert 卡片”的后台任务，但做一层可追溯增强：

- Expert 对话里点击“收藏到备忘录”保存策略卡时，补写 `source_conversation_id`
- 同时在学习画像里统计 `source_type='expert'` 的计划数

这样后续如果要继续做“卡片回放 -> 专家学习”，已有来源链路可以直接往下接，不需要重做数据归属。

## 六、测试策略

### 后端 pytest

- Intent classifier 能把“什么是市盈率”判成 `concept_explain`
- Intent classifier 能把“宁德时代现在能买吗”判成 `trading_decision` 或 `stock_analysis`
- `concept_explain` 路径不调用 clarification / tool workflow
- 学习画像聚合能从 review stats / memories / reflections 生成稳定结构

### 前端 node:test

- 学习画像 normalization 能正确处理空态和完整态
- portfolio 选择 helper 能优先读取最近使用的 portfolio
- Expert 学习卡 view model 能按专家类型做不同排序

### 集成回归

- Expert 页输入“什么是市盈率”时，直接进入概念解释模式
- Expert 页输入个股问题时，仍走原分析链路
- Expert 页右侧卡在有复盘数据时展示学习内容，在无数据时展示空状态

## 风险与控制

- 分值是启发式 read model，不是精确训练指标，因此每个分值都要附带来源说明，避免用户误解为量化评级。
- 共享复盘底座不等于专家独立学习记录，因此 UI 文案要诚实表达为“当前专家可调用的复盘沉淀”。
- localStorage 保存最近 portfolio 只是便利机制，失效时必须能自动回落，不得导致 Expert 页卡死。
- 意图分类属于前置守门，误判成本较高，因此规则和 LLM 双保险都要保留，并且分析类请求宁可保守落回主链，也不要大量误拦。
