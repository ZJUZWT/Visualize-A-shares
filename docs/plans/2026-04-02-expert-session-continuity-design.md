# Expert Session Continuity Design

## 背景

当前 Expert 聊天已经支持：

- 流式回复中断后把已生成内容落库为 `partial`
- 用户点击“继续生成”后通过 `/api/v1/expert/chat/resume` 续写
- 用户对疑似截断、load failed 等问题提交反馈

但真实使用里还有两个关键缺口：

1. **同一专家内切换 session 会主动中断当前请求**。这与“后台继续生成、切回原对话还能看到结果”的预期冲突。
2. **中断原因分类过粗**。现在前端只能明确识别本地 `AbortError`，后端只能看到 `CancelledError` 或普通异常，无法稳定区分用户主动停止、客户端断连、上游 provider 异常等原因。

本次设计目标是在不推倒现有 Expert SSE 架构的前提下，补齐“会话级连续性”和“中断原因可追踪性”。

## 目标

- 同一专家下切换到另一个 session 时，原 session 的生成任务继续在后台完成
- 后台继续生成的 token 和最终结果只写回原 session，不串到当前查看的 session
- 用户主动点击停止时，后端能记录明确的取消原因，而不是与断网/切页混在一起
- 对话因断连或异常中断时，服务端仍能保留 `partial` 消息，方便后续 resume
- 为后续“问题反馈 → 后台排查”提供更明确的中断上下文

## 非目标

- 不做全新的任务队列/消息总线
- 不把 Expert 聊天改成全局 server-side job 订阅模型
- 不在本次内扩展到 Agent 页或其他 SSE 页面

## 现状根因

### 1. 前端流状态按 expertType 维护，而不是按 session 维护

当前 `useExpertStore` 里的：

- `_abortMap`
- `chatHistories`
- `pendingClarifications`
- `statusMap`

都主要围绕 `expertType` 运作。这样一来，同一专家下面切换 session 时，系统只知道“当前 data 专家有一个流”，不知道“这个流属于哪个 session”。

结果就是：

- 切换 session 时为了避免写错 UI，代码直接 `abort`
- 即便不 abort，后续 token 也可能落进当前显示的那组消息

### 2. 后端只能看到“客户端没了”，看不到“为什么没了”

后端路由在 SSE 生成里区分：

- `asyncio.CancelledError`
- 其他 `Exception`

但对后端来说，以下场景都可能变成 `CancelledError`：

- 用户主动点击停止
- 浏览器标签页关闭
- 网络断开
- 同页切换 session 触发前端 abort

所以如果前端不显式告诉后端“这是用户取消”，后端无法可靠区分原因。

### 3. partial 保存目前是追加写入，不带中断元数据

当前 `_save_partial_message(...)` 会新增一条 `expert.messages` 记录并标记为 `partial`。这能兜住已生成内容不丢，但它没有记录：

- 中断原因
- 是否为用户取消
- 是否为 provider 侧错误
- 是否是 resume 再次中断

这会削弱后续排查和运营反馈的价值。

## 方案选择

### 方案 A：仅移除 session 切换时的 abort

优点：

- 改动最小

缺点：

- 现有前端状态仍按 expertType 存，会导致 token 串 session
- 无法稳定支持后台继续生成

结论：不采用。

### 方案 B：会话级流状态 + 显式取消上报

优点：

- 保留现有 SSE / resume 架构
- 能支持“后台继续跑完”
- 能清晰区分用户取消和其他断连
- 改动范围可控

缺点：

- 需要调整前端 store 的流式状态模型
- 需要补一条取消 API 和消息元数据

结论：**采用此方案。**

### 方案 C：完全任务化，前端只订阅结果

优点：

- 理论上最强

缺点：

- 架构改动过大
- 会波及整个 Expert 页面事件模型

结论：本次不采用。

## 方案设计

### 一、前端改成“会话级连续性”

新增或重构以下概念：

- `streamControllersBySession`: 用 `sessionId` 追踪请求控制器
- `streamingMessageRef`: 记录某个 `sessionId` 下正在流式写入的 `expertMessageId`
- `pendingClarificationsBySession`: 澄清状态与原 session 绑定

核心原则：

- **发送消息后，流与 `sessionId` 绑定**
- **切换 session 只切 UI，不动流**
- **停止生成只停止当前正在查看 session 的流**

这样同一专家下：

- session A 正在生成
- 用户切到 session B 看历史
- A 的流继续，B 不受影响
- 切回 A 时能看到更新后的内容

### 二、后端增加显式取消入口

新增一个轻量 API，例如：

- `POST /api/v1/expert/chat/cancel`

请求体包含：

- `session_id`
- `message_id`
- `expert_type`
- `reason`，固定枚举值如 `user_cancelled`

作用：

- 用户点击“停止生成”时，前端先上报取消，再执行本地 abort
- 后端把这次消息标成 `partial`，并记录中断原因

这样后端就能把：

- 用户主动取消
- 客户端断开
- 服务器异常

分开落库，而不是都混成 `CancelledError`

### 三、为 expert 消息补中断元数据

在 `expert.messages` 上新增可兼容字段：

- `interruption_reason`
- `interruption_detail`
- `last_stream_event_at`

推荐原因枚举：

- `user_cancelled`
- `client_disconnected`
- `server_error`
- `provider_error`
- `resume_interrupted`
- `unknown_interrupted`

行为约定：

- 正常完成：`status=completed`，中断字段为空
- 中断保存：`status=partial`，写入原因
- resume 再次中断：保留 `partial`，原因改为 `resume_interrupted`

### 四、统一 partial 持久化入口

把当前的 `_save_partial_message(...)` 提升成统一的中断收口函数，例如：

- 支持新增 partial 消息
- 支持更新已有 partial 消息
- 支持写入 interruption metadata

这样主回复流和 resume 流都走同一套逻辑，不再分散处理。

### 五、错误分类策略

后端路由层先做保守分类：

- 显式 cancel API → `user_cancelled`
- `asyncio.CancelledError` 且未收到显式 cancel → `client_disconnected`
- 普通 `Exception`：
  - message / type 命中 provider 关键字 → `provider_error`
  - 否则 → `server_error`

这里不追求 100% 绝对精确，但至少把“用户主动停止”和“其他断连”拆开。

### 六、前端展示策略

Expert 消息下方继续保留 `PartialBanner`，但文案可更明确：

- 用户停止：`已停止生成`
- 连接中断：`回复未完成`
- provider / server error：`生成中断，可继续补全`

同时反馈面板默认 issue type 可根据 `interruption_reason` 预选：

- `provider_error` / `server_error` → `load_failed`
- `client_disconnected` / `unknown_interrupted` → `llm_truncated`

## 数据流

### 正常生成

1. 前端发送消息，并把 user message 立即落库
2. 创建与 `sessionId` 绑定的 SSE 流
3. token 按 session 写回对应消息
4. 正常完成后落库 `completed`

### 用户主动停止

1. 前端点击停止
2. 先请求 `/chat/cancel`
3. 后端把当前消息保存/更新为 `partial + user_cancelled`
4. 前端再本地 abort

### 客户端断连 / 切页 / 网络异常

1. 后端收到 `CancelledError`
2. 若没有 cancel 标记，则保存为 `partial + client_disconnected`

### 上游异常

1. 路由层捕获 `Exception`
2. 保存为 `partial + provider_error/server_error`
3. 向前端发 `event:error`

### resume 续写

1. 前端点击继续生成
2. 后端先检查已有内容是否完整
3. 若不完整则调用 `resume_reply`
4. 若 resume 再次中断，更新原消息为 `partial + resume_interrupted`

## 测试策略

### 后端

- `CancelledError` 时保存 `partial + client_disconnected`
- 显式 cancel 时保存 `partial + user_cancelled`
- resume 中断时更新原消息而非新建脏记录
- provider/server error 分类至少覆盖基本路径

### 前端

- 同一专家切 session 时不再 abort 原流
- token 只更新原 session 的消息，不写入当前查看 session
- 停止生成只影响当前 session 绑定的流

### 回归

- 现有 feedback、resume、learning profile 流程保持可用
- clarification 不因 session 绑定改动而串状态

## 风险与控制

### 风险 1：会话级状态改动导致串消息

控制：

- 所有流更新都基于 `sessionId + messageId`
- 切换 session 后只有 `activeSessions` 改，流对象不改

### 风险 2：取消和断连竞态

控制：

- 后端 cancel 标记写入时间戳
- `CancelledError` 发生时优先读取最近 cancel 状态判定原因

### 风险 3：旧数据兼容

控制：

- 新列采用可空字段
- 前端缺少 `interruption_reason` 时回退到现有 `partial/completed` 逻辑

## 验收标准

- 同一专家下切换 session 不会打断原 session 正在进行的请求
- 原 session 生成完成后，切回可看到完整消息
- 用户点击停止后，服务器端保留 partial 内容，且原因标记为用户取消
- 非用户取消的断连也会保留 partial，不再出现“对话没有返回、数据库里也没保存”
- resume、feedback、clarification 相关回归测试通过
