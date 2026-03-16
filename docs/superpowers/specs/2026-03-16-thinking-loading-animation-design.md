# 思考/加载动画改进设计

## 目标

改善辩论页和专家对话页在 LLM 思考/等待阶段的用户体验，消除"卡住"感。同时修复专家对话中文字颜色对比度问题。

## 范围

三个独立改进点：

1. **专家对话 ThinkingPanel** — tool_call/tool_result 合并为单条目，加转圈→勾/叉状态动画
2. **辩论页等待动画** — 用三点跳动动画替代静态 Loader2 + 文字
3. **文字颜色修复** — MiniMarkdown 容器缺少显式文字颜色

---

## 1. 专家对话 ThinkingPanel 改进

### 当前行为

- `tool_call` SSE 事件 → 新增一个 ThinkingItem 条目（显示 Wrench/Users 图标 + 工具名）
- `tool_result` SSE 事件 → 新增另一个 ThinkingItem 条目（显示 CheckCircle2/AlertTriangle + 摘要）
- 专家回复内容在 `ExpertReplyDetail` 中默认展开，需要用户手动折叠

### 改进方案

**Store 层变更（useExpertStore.ts）：**

当 `tool_result` 到达时，不新增条目，而是找到对应的 `tool_call` 条目并合并：
- 匹配逻辑：`tool_result.data.engine === tool_call.data.engine && tool_result.data.action === tool_call.data.action`
- 合并后的条目类型变为复合类型，包含 call + result 数据

**ThinkingItem 类型扩展（types/expert.ts）：**

```typescript
// 现有 tool_call 条目增加 result 字段
interface ToolCallThinkingItem {
  type: "tool_call";
  data: ToolCallData;
  result?: ToolResultData;  // tool_result 到达后合并进来
  status: "pending" | "done" | "error";  // 新增状态字段
}
```

**ThinkingPanel UI 变更：**

tool_call 条目渲染逻辑：
- `status === "pending"`: 左侧图标为 `Loader2` 转圈动画（替代静态 Wrench/Users）
- `status === "done"`: 左侧图标变为绿色 `CheckCircle2`
- `status === "error"`: 左侧图标变为红色 `AlertTriangle`

回复内容：
- 默认折叠（`defaultOpen={false}`）
- 用户点击可展开查看完整 Markdown 内容
- 展开时如果内容仍在流式传输中，显示逐步加载效果（当前后端是一次性返回 tool_result，所以展开即显示完整内容）

删除独立的 `tool_result` 条目渲染分支 — 所有信息都在合并后的 `tool_call` 条目中展示。

### 涉及文件

- `web/types/expert.ts` — ThinkingItem 类型扩展
- `web/stores/useExpertStore.ts` — tool_result 合并逻辑
- `web/components/expert/ThinkingPanel.tsx` — UI 渲染改造

---

## 2. 辩论页等待动画改进

### 当前行为

- StreamingBubble 无内容时：`Loader2` 转圈 + "思考中..." / "思考完毕，正在组织发言..." 文字
- 数据请求卡片：`Loader2` 转圈

### 改进方案

**新增 TypingDots 组件（共享）：**

三个圆点依次跳动的经典 typing indicator 动画，类似 iMessage/ChatGPT 风格：

```css
@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-4px); opacity: 1; }
}
```

三个点分别延迟 0ms、150ms、300ms，形成波浪效果。

**替换位置：**

1. `StreamingBubble` 中无 token 时的等待状态 → TypingDots + 文字
2. `MessageBubble`（专家对话）中 `isStreaming && !content` 时 → TypingDots

**保留 Loader2 的场景：**
- 数据请求卡片（DataRequestCard）— 这里转圈更合适，表示网络请求
- Facts 压缩 / 行业认知卡片 — 同上

### 涉及文件

- `web/app/globals.css` — 新增 `@keyframes typing-bounce`
- `web/components/debate/TranscriptFeed.tsx` — StreamingBubble 替换
- `web/components/expert/MessageBubble.tsx` — 等待状态替换

---

## 3. 文字颜色修复

### 问题

`ThinkingPanel.tsx` 中 `ExpertReplyDetail` 的 `MiniMarkdown` 渲染容器没有显式设置文字颜色。在 `debate-dark` 主题下，某些 Markdown 元素（如普通段落文字）可能继承到错误的颜色，导致深色文字在深色背景上不可见。

### 修复方案

给 `ExpertReplyDetail` 的内容容器和 `MiniMarkdown` 的根级元素添加显式的 `text-[var(--text-primary)]` 类：

```tsx
// ExpertReplyDetail 内容容器
<div className={`... text-[var(--text-primary)]`}>
  <MiniMarkdown content={cleanContent} />
</div>
```

同时检查 `MiniMarkdown` 中的 `<p>` 组件是否缺少颜色声明，确保所有文本元素都使用 CSS 变量而非硬编码颜色。

### 涉及文件

- `web/components/expert/ThinkingPanel.tsx` — 添加显式文字颜色

---

## 不做的事情

- 不改变后端 SSE 事件结构（纯前端改动）
- 不添加 skeleton loader（当前场景不适合）
- 不添加 token 计数或进度条（过度工程）
- 不改变辩论页 SpeechBubble 的已完成条目样式
