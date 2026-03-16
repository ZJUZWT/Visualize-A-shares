# 思考/加载动画改进 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改善辩论页和专家对话页在 LLM 等待阶段的用户体验，消除"卡住"感。

**Architecture:** 纯前端改动。专家对话 ThinkingPanel 将 tool_call/tool_result 合并为单条目并加状态动画；辩论页用三点跳动动画替代静态 Loader2；修复深色主题下文字颜色对比度。

**Tech Stack:** Next.js, React, Tailwind CSS, lucide-react

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `web/types/expert.ts` | ThinkingItem 类型定义 | 修改：tool_call 条目增加 result/status 字段 |
| `web/stores/useExpertStore.ts` | 专家对话状态管理 | 修改：tool_result 合并到对应 tool_call |
| `web/components/expert/ThinkingPanel.tsx` | 思考面板 UI | 修改：合并渲染 + 状态动画 + 颜色修复 |
| `web/components/expert/MessageBubble.tsx` | 专家消息气泡 | 修改：等待状态用 TypingDots |
| `web/components/debate/TranscriptFeed.tsx` | 辩论流式气泡 | 修改：等待状态用 TypingDots |
| `web/app/globals.css` | 全局样式 | 修改：新增 typing-bounce 动画 |

---

## Chunk 1: 基础设施 + 类型 + Store

### Task 1: 新增 TypingDots CSS 动画

**Files:**
- Modify: `web/app/globals.css:221-235`

- [ ] **Step 1: 在 globals.css 的加载动画区域末尾添加 typing-bounce 关键帧**

在 `.animate-spin` 规则之后（line 235）插入：

```css
/* 三点跳动 — AI 思考指示器 */
@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-4px); opacity: 1; }
}
.typing-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  animation: typing-bounce 1.4s ease-in-out infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.15s; }
.typing-dot:nth-child(3) { animation-delay: 0.3s; }
```

- [ ] **Step 2: Commit**

```bash
git add web/app/globals.css
git commit -m "feat: 新增 typing-bounce CSS 动画"
```

<!-- PLAN_PLACEHOLDER_1 -->

### Task 2: 扩展 ThinkingItem 类型

**Files:**
- Modify: `web/types/expert.ts:55-59`

- [ ] **Step 1: 修改 tool_call 分支，增加 result/status 字段**

将：
```typescript
| { type: "tool_call"; data: ToolCallData }
```
替换为：
```typescript
| { type: "tool_call"; data: ToolCallData; result?: ToolResultData; status: "pending" | "done" | "error" }
```

保留 `tool_result` 分支不变（兼容历史数据）。

- [ ] **Step 2: Commit**

```bash
git add web/types/expert.ts
git commit -m "feat: ThinkingItem tool_call 增加 result/status 字段"
```

### Task 3: Store 层 tool_result 合并逻辑

**Files:**
- Modify: `web/stores/useExpertStore.ts:368-383`

- [ ] **Step 1: tool_call 事件初始化 status 字段**

找到 `eventType === "tool_call"` 分支（line 368），在 push 的对象中添加 `status: "pending" as const`。

- [ ] **Step 2: tool_result 事件合并到对应 tool_call**

找到 `eventType === "tool_result"` 分支（line 376），替换为：

```typescript
} else if (eventType === "tool_result") {
  const resultData = data as unknown as ToolResultData;
  const callIdx = msg.thinking.findLastIndex(
    (t) =>
      t.type === "tool_call" &&
      t.data.engine === resultData.engine &&
      t.data.action === resultData.action &&
      t.status === "pending"
  );
  if (callIdx !== -1) {
    const callItem = msg.thinking[callIdx] as Extract<typeof msg.thinking[number], { type: "tool_call" }>;
    msg.thinking = [...msg.thinking];
    msg.thinking[callIdx] = {
      ...callItem,
      result: resultData,
      status: resultData.hasError ? "error" : "done",
    };
  } else {
    msg.thinking = [
      ...msg.thinking,
      { type: "tool_result" as const, data: resultData },
    ];
  }
```

- [ ] **Step 3: Commit**

```bash
git add web/stores/useExpertStore.ts
git commit -m "feat: tool_result 合并到对应 tool_call 条目"
```

<!-- PLAN_PLACEHOLDER_2 -->

## Chunk 2: ThinkingPanel UI 改造

### Task 4: ThinkingPanel 合并渲染 + 状态动画 + 颜色修复

**Files:**
- Modify: `web/components/expert/ThinkingPanel.tsx`

- [ ] **Step 1: 添加 Loader2 到 import**

在 lucide-react import 中添加 `Loader2`。

- [ ] **Step 2: 改造 tool_call 条目渲染**

找到 `if (item.type === "tool_call")` 分支（line 215-248），替换为合并渲染逻辑：
- `status === "pending"` → `Loader2` 转圈（使用 `color` prop 着色）
- `status === "done"` → 绿色 `CheckCircle2`
- `status === "error"` → 红色 `AlertTriangle`
- 如果有 `item.result`，在同一条目内渲染 `ExpertReplyDetail`（默认折叠）
- 非专家工具的 result 显示 summary 文字

- [ ] **Step 3: tool_result 独立渲染加 fallback 注释**

在 `if (item.type === "tool_result")` 分支开头加注释说明这是 fallback（历史数据兼容），逻辑不变。

- [ ] **Step 4: ExpertReplyDetail 内容容器添加显式文字颜色**

找到内容容器 `<div className={...}>` （line 124），添加 `text-[var(--text-primary)]`。

- [ ] **Step 5: ExpertReplyDetail defaultOpen 改为 false**

将参数默认值从 `defaultOpen = true` 改为 `defaultOpen = false`。

- [ ] **Step 6: ThinkingPanel 默认展开**

将 `const [open, setOpen] = useState(false)` 改为 `useState(true)`，让用户能看到工具调用的转圈动画。

- [ ] **Step 7: Commit**

```bash
git add web/components/expert/ThinkingPanel.tsx
git commit -m "feat: ThinkingPanel 合并渲染 + 状态动画 + 颜色修复"
```

## Chunk 3: 等待动画替换

### Task 5: 专家对话 MessageBubble 等待动画

**Files:**
- Modify: `web/components/expert/MessageBubble.tsx:116-117`

- [ ] **Step 1: 替换等待状态为 TypingDots**

将 `isStreaming && !content` 时的 `"正在思考..."` 文字替换为三点跳动 + 文字：

```tsx
<span className="inline-flex items-center gap-1.5 text-[var(--text-tertiary)] text-xs">
  <span className="inline-flex gap-[3px]" style={{ color: expertColor }}>
    <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
  </span>
  正在思考
</span>
```

- [ ] **Step 2: Commit**

```bash
git add web/components/expert/MessageBubble.tsx
git commit -m "feat: 专家对话等待状态用三点跳动动画"
```

### Task 6: 辩论页 StreamingBubble 等待动画

**Files:**
- Modify: `web/components/debate/TranscriptFeed.tsx`

- [ ] **Step 1: 替换 debater 等待状态**

找到 debater 分支无 token 时的 `Loader2` + "思考完毕，正在组织发言..."（line 372-375），替换为：

```tsx
<span className="inline-flex gap-[3px]" style={{ color }}>
  <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
</span>
<span>正在组织发言...</span>
```

- [ ] **Step 2: 替换 observer 等待状态**

找到 observer 分支的 `Loader2` + "思考中..."（line 344-347），同样替换为 typing-dot。

- [ ] **Step 3: 替换 judge 等待状态**

找到 judge 分支的 `Loader2`（line 322-325），替换为 typing-dot，文字改为更简洁的 "正在生成裁决..." / "裁判正在综合各方观点..."。

- [ ] **Step 4: Commit**

```bash
git add web/components/debate/TranscriptFeed.tsx
git commit -m "feat: 辩论页等待状态用三点跳动动画"
```

### Task 7: 验证

- [ ] **Step 1: 验证专家对话页**

打开 http://localhost:3000/expert，发送消息，确认：思考面板默认展开、tool_call 转圈、完成后变绿勾、回复默认折叠可展开、文字颜色清晰。

- [ ] **Step 2: 验证辩论页**

打开 http://localhost:3000/debate，发起辩论，确认：等待时三点跳动、颜色跟随角色、token 流入后动画消失。
