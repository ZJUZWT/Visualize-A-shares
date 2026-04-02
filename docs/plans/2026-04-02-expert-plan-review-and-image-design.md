# Expert Plan Review And Image Grounding Design

## 背景

当前 Expert 对话链已经支持上传图片、生成策略卡片、保存策略卡片，但还有两个关键断点：

1. 图片虽然从前端传到了后端请求体，但在 Expert 主链路进入 `ContextGuard` 后，消息被压成只剩 `role/content`，`images` 实际丢失，导致最终 LLM 往往根本没有收到图片。
2. 策略卡片虽然能保存到 `agent.trade_plans`，但现有 `ReviewEngine` 的日复盘 / 周复盘只围绕 `agent.trades` 与 `agent.review_records` 运转，没有“计划复盘”这条独立链路，因此 Expert 无法对自己的建议做后验复盘，也无法把这些结果回流成可见学习内容。

用户已经明确本轮方向：

- 要修 Expert 图片理解，让 Agent 真正知道图片里是什么、用户想让它看什么。
- 要让策略卡片可以在后续盘面中被 Expert 复盘，并把这些结果回流给 Expert 自己。
- 本轮不做自动调度版的全自动复盘，后续留给“宠物”系统。

## 目标

- 修复 Expert 链路中的图片丢失问题，保证多模态消息可以真正到达最终 LLM。
- 为图片增加一层轻量“结构化说明”，让 Agent 不只是看到图，还知道图的类别、关键信息和用户关注点。
- 为 Expert 策略卡片新增“可复盘记录”，支持用户手动触发复盘。
- 将策略卡复盘结果纳入 Expert 页右侧学习栏，并在 Expert 后续回答时作为经验摘要回流。

## 非目标

- 不做计划复盘自动调度器，不做 T+1 / T+3 / 到期自动跑批。
- 不把 Expert 策略卡直接转成真实交易，也不改 Main Agent 交易执行主流程。
- 不把“计划复盘”强行塞进现有 `review_records`，避免污染真实交易复盘语义。
- 不做完整的多图 OCR / 图像理解训练框架，只做足够稳的轻量结构化摘要。

## 备选方案

### 方案 A：只修图片链路 + 卡片手动弹窗复盘

- 做法：修复 `images` 丢失问题；卡片增加一个“复盘这张卡”按钮，点了以后只返回一次性结果，不入库，不进入学习栏。
- 优点：实现最快，最小改动。
- 缺点：复盘结果是一次性的，Expert 后续仍然学不到；学习进度卡还是看不到“策略卡后来怎么样”。

### 方案 B：修图片链路 + 新增计划复盘记录 + 学习回流

- 做法：修复多模态链路；增加图片结构化摘要；保存策略卡时补足来源信息；新增 `plan review` 记录表与手动复盘接口；学习栏消费这些结果；Expert prompt 注入近期策略卡复盘摘要。
- 优点：形成完整但受控的闭环，用户能看，Expert 也能用。
- 缺点：需要同时改数据库、服务层、Expert 聚合层和前端卡片。

### 方案 C：直接做全自动计划复盘调度

- 做法：到期、T+1、T+3 自动跑复盘，并自动更新 memory / reflection。
- 优点：长期最强。
- 缺点：时序复杂度、状态机复杂度、误触发风险都明显更高，不适合本轮。

## 选型

采用 **方案 B**。

理由：

- 它同时解决“图片没理解”和“卡片没学习”两个断点。
- 它能形成真正可见的闭环，又不会把范围扩到调度系统。
- 它对现有真实交易复盘链影响最小，语义上清晰。

## 设计概览

本次方案分为四个部分：

1. Expert 图片链路修复
2. 图片结构化说明生成
3. 策略卡计划复盘数据模型与接口
4. 学习回流与 UI 展示

## 一、图片链路修复

### 当前问题

当前 `ExpertAgent` 在 `_reply_stream()`、`direct_reply()` 等路径中，先构造了带 `images` 的 `ChatMessage`，但随后做上下文保护时：

- 先把消息压成 `{"role": ..., "content": ...}`
- 再从压缩结果重建 `ChatMessage`

这个过程把 `images` 彻底丢掉了。

### 修复策略

- `ContextGuard` 继续负责裁剪消息，但要保留用户消息里的 `images` 字段。
- 重建 `ChatMessage` 时把 `images` 一并带回去。
- 仅保留用户消息的图片，不为 assistant / system 注入无意义图片字段。

### 影响范围

- `ExpertAgent._reply_stream()`
- `ExpertAgent.direct_reply()`
- 如果有其它走 `ContextGuard` 的多模态路径，也统一修复。

## 二、图片结构化说明

### 核心原则

不依赖重型 OCR pipeline，不追求完美识别，而是先把“图片大意”稳定地表达出来，辅助 Expert 理解用户意图。

### 结构化说明字段

新增一个轻量图片摘要结果：

- `image_kind`
  - `kline_chart`
  - `intraday_chart`
  - `portfolio_screenshot`
  - `announcement_or_report`
  - `chat_screenshot`
  - `other`
- `detected_entities`
  - 股票名 / 代码
  - 周期
  - 指标词
  - 明显价格 / 仓位 / 百分比
- `user_focus`
  - 趋势 / 支撑阻力
  - 原因分析
  - 仓位建议
  - 概念解释
- `summary`
  - 一段给 Expert 看的短摘要

### 生成方式

- 如果请求带图片，先走一个非常短的多模态说明 prompt，输出严格 JSON。
- 不把它做成独立前端功能，只在后端内部生成。
- 失败时降级为空摘要，不阻断主链路。

### 最终注入方式

Expert 最终回复 prompt 中看到的是：

- 用户原问题
- 图片结构化说明
- 原始图片

这样模型既有视觉输入，也有我们人为压好的解释锚点。

## 三、策略卡计划复盘

### 当前问题

现在策略卡保存时只进入 `agent.trade_plans`，主要保存的是建议本身：

- 标的
- 买卖方向
- 进出场价格
- 理由 / 风险 / 失效条件

但没有独立的“计划复盘记录”，也没有和 Expert 消息形成稳定绑定。

### 数据模型

本次新增两部分：

1. 为 `agent.trade_plans` 补齐来源字段：
   - `source_message_id`
2. 新增 `agent.plan_reviews`

`plan_reviews` 记录建议后来表现如何，建议字段：

- `id`
- `plan_id`
- `source_type`
- `source_conversation_id`
- `source_message_id`
- `review_date`
- `review_window`
- `entry_hit`
- `take_profit_hit`
- `stop_loss_hit`
- `invalidation_hit`
- `max_gain_pct`
- `max_drawdown_pct`
- `close_price`
- `outcome_label`
  - `useful`
  - `misleading`
  - `incomplete`
  - `pending`
- `summary`
- `lesson_summary`
- `evidence_json`
- `created_at`

### 复盘逻辑

本轮只做“手动触发复盘”：

- 用户点卡片上的“复盘这张卡”
- 后端读取对应计划
- 拉取计划生成日之后的一段历史行情
- 依据计划字段生成后验判断：
  - 建议价是否触发
  - 后续是否先止盈 / 先止损
  - 最大浮盈 / 最大回撤
  - 若无足够行情则标记 `pending`

这次先不依赖 LLM 生成结论，优先用确定性规则计算，再拼出一段结构化 summary，避免结果不稳定。

### 为什么不直接复用 `review_records`

- `review_records` 语义是“真实交易复盘”
- `plan_reviews` 语义是“建议后验验证”
- 两者混在一起会让胜率、盈亏、训练指标失真

因此必须分表。

## 四、学习回流

### 用户可见层

Expert 右侧学习栏增加对 `plan_reviews` 的消费：

- “最近新增复盘结论”优先混排最近反思和最近策略卡复盘
- 待验证策略卡数量继续保留
- 已复盘的卡能显示：
  - 结论标签
  - 简短总结
  - 复盘日期

### Expert 可见层

在 Expert prompt 中新增一段轻量“近期策略卡复盘经验”摘要，包含：

- 最近验证有效的建议模式
- 最近被证伪的建议模式
- 最近触发的失效边界

这层回流只做“摘要注入”，不直接修改 `agent_memories`，避免本轮把范围扩展成自动知识演化系统。

## 五、前端交互

### 卡片内交互

`TradePlanCard` 增加：

- `复盘这张卡` 按钮
- 复盘中 loading 状态
- 复盘结果展开区

展开区展示：

- `useful / misleading / incomplete / pending`
- 命中情况
- 最大浮盈 / 最大回撤
- 一句 lesson

### 右侧学习栏

保持现有右侧中部折叠形态，不新增独立页面。

优先把这次新增的“计划复盘结论”放进：

- `最近新增复盘结论`

必要时在底部待验证区继续显示：

- `待验证策略卡 N 张`

## 六、测试策略

### 后端

- `tests/unit/expert/test_agent.py`
  - 锁住图片在 `ContextGuard` 后不丢
  - 锁住有图片时会生成结构化摘要并进入最终消息
- `tests/unit/test_trade_plans.py`
  - 锁住 `source_message_id` 可保存
  - 锁住 `plan_reviews` CRUD / 复盘生成
- `tests/unit/test_agent_review_memory.py`
  - 锁住计划复盘不会污染真实交易复盘
- `tests/unit/expert/test_routes.py`
  - 锁住 Expert 学习画像会带出计划复盘结论

### 前端

- 卡片复盘结果解析与状态映射测试
- 学习画像 normalizer 测试
- 右侧学习栏 view model 测试

## 风险与兜底

### 风险 1：图片摘要失败

- 兜底：不阻断主链路，直接继续原始图片 + 原始问题

### 风险 2：历史行情不足，无法复盘

- 兜底：返回 `pending`，并在 UI 中显示“当前还没有足够后验行情”

### 风险 3：计划复盘结果与真实交易复盘概念混淆

- 兜底：独立表、独立接口、独立标签，绝不写入 `review_records`

### 风险 4：Expert prompt 回流过重

- 兜底：只注入最近少量策略卡复盘摘要，保持简短，避免挤占主上下文

## 验收标准

- 上传图片后，Expert 最终调用链能保留 `images`。
- 图片会生成一段结构化摘要，Expert 回答能显式引用图中信息。
- 保存策略卡后，用户可以手动触发复盘。
- 复盘结果会写入独立 `plan_reviews` 记录。
- 右侧学习栏能显示最近策略卡复盘结论。
- Expert 后续回答能看到近期策略卡复盘摘要，而不是只看到旧的 reviews / memories。
