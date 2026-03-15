# 辩论导出 HTML Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 辩论结束后，用户点击"导出"按钮，前端生成一个自包含 HTML 文件并触发下载，包含黑板数据、完整辩论记录和裁判裁决，样式与现有辩论页一致（深色主题）。

**Architecture:** 纯前端实现，无需后端。新增 `exportDebateHtml` 工具函数，从 Zustand store 读取 `transcript`、`judgeVerdict`、`blackboardItems`，生成内联 CSS + 数据的 HTML 字符串，通过 `URL.createObjectURL` + `<a download>` 触发下载。在 `InputBar` 中新增导出按钮，仅在 `status === "completed"` 时显示。

**Tech Stack:** Next.js 15, TypeScript, Zustand, Tailwind CSS v4（导出 HTML 用内联 CSS，不依赖 Tailwind）

---

## 文件结构

**新增：**
- `web/lib/exportDebateHtml.ts` — 生成 HTML 字符串的核心函数

**修改：**
- `web/components/debate/InputBar.tsx` — 新增导出按钮（`status === "completed"` 时显示）
- `web/components/debate/DebatePage.tsx` — 传递 `onExport` 回调给 `InputBar`

---

## Chunk 1: 导出函数 + 按钮接入

### Task 1: `exportDebateHtml` 工具函数

**Files:**
- Create: `web/lib/exportDebateHtml.ts`

- [ ] **Step 1: 确认 `web/lib/` 目录存在，不存在则创建**

```bash
mkdir -p web/lib
```

- [ ] **Step 2: 创建 `web/lib/exportDebateHtml.ts`**

```typescript
import type { BlackboardItem, TranscriptItem } from "@/stores/useDebateStore";
import type { JudgeVerdict } from "@/types/debate";

const ROLE_LABEL: Record<string, string> = {
  bull_expert: "多头专家",
  bear_expert: "空头专家",
  retail_investor: "散户代表",
  smart_money: "主力代表",
  judge: "裁判",
};

const SOURCE_LABEL: Record<string, string> = {
  public: "公用",
  bull_expert: "多头",
  bear_expert: "空头",
};

const SIGNAL_LABEL: Record<string, string> = {
  bullish: "看多 ▲",
  bearish: "看空 ▼",
  neutral: "中性 —",
};

const SIGNAL_COLOR: Record<string, string> = {
  bullish: "#f87171",
  bearish: "#34d399",
  neutral: "#94a3b8",
};

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderBlackboard(items: BlackboardItem[]): string {
  if (items.length === 0) return "<p style='color:#64748b'>无黑板数据</p>";
  return items.map(item => {
    const sourceColor = item.source === "bull_expert" ? "#f87171"
      : item.source === "bear_expert" ? "#34d399" : "#64748b";
    const statusIcon = item.status === "pending" ? "⏳"
      : item.status === "failed" ? "✗" : "✓";
    const statusColor = item.status === "failed" ? "#f87171" : "#34d399";
    const summary = item.result_summary
      ? `<div style='margin-top:6px;padding:8px;background:#0f172a;border-radius:6px;font-size:11px;color:#94a3b8;white-space:pre-wrap;word-break:break-all'>${escapeHtml(item.result_summary)}</div>`
      : "";
    return `<div style='border-bottom:1px solid #1e293b;padding:8px 0'>
      <div style='display:flex;align-items:center;gap:8px'>
        <span style='font-size:10px;padding:2px 6px;border-radius:4px;background:${sourceColor}22;color:${sourceColor}'>${SOURCE_LABEL[item.source] ?? item.source}</span>
        <span style='font-size:12px;color:#94a3b8;flex:1'>${escapeHtml(item.title)}</span>
        <span style='color:${statusColor};font-size:11px'>${statusIcon}</span>
      </div>
      ${summary}
    </div>`;
  }).join("");
}

// 注意：TranscriptItem 还有 "streaming"、"data_request"、"blackboard_data" 变体，
// 这些在导出时均intentionally跳过（返回 ""），因为导出只在 status==="completed" 时触发，
// 此时 streaming 气泡已被替换为 entry，data_request/blackboard_data 不需要出现在导出文件中。
function renderTranscript(transcript: TranscriptItem[]): string {
  return transcript.map(item => {
    if (item.type === "round_divider") {
      return `<div style='text-align:center;padding:12px 0;color:#475569;font-size:12px;border-top:1px solid #1e293b;margin:16px 0'>
        第 ${item.round} 轮${item.is_final ? "（最终轮）" : ""}
      </div>`;
    }
    if (item.type === "system") {
      return `<div style='text-align:center;padding:8px;color:#475569;font-size:12px'>${escapeHtml(item.text)}</div>`;
    }
    if (item.type === "entry") {
      const entry = item.data;
      if (!entry.speak) return "";
      const isBull = entry.role === "bull_expert";
      const isBear = entry.role === "bear_expert";
      const isObserver = entry.role === "retail_investor" || entry.role === "smart_money";
      const roleColor = isBull ? "#f87171" : isBear ? "#34d399" : "#94a3b8";
      const align = isBull ? "flex-start" : isBear ? "flex-end" : "center";
      const stanceText = entry.stance === "concede" ? " · 认输" : entry.stance === "partial_concede" ? " · 部分让步" : "";
      const confidencePct = Math.round(entry.confidence * 100);
      return `<div style='display:flex;justify-content:${align};margin:8px 0'>
        <div style='max-width:70%;background:#1e293b;border-radius:12px;padding:12px 16px;${isObserver ? "max-width:90%;background:#0f172a;border:1px solid #1e293b" : ""}'>
          <div style='font-size:11px;color:${roleColor};margin-bottom:6px;font-weight:600'>
            ${ROLE_LABEL[entry.role] ?? entry.role}${stanceText}
            <span style='color:#475569;font-weight:400;margin-left:8px'>置信度 ${confidencePct}%</span>
          </div>
          <div style='font-size:13px;color:#e2e8f0;line-height:1.6;white-space:pre-wrap'>${escapeHtml(entry.argument)}</div>
          ${entry.challenges?.length ? `<div style='margin-top:8px;padding-top:8px;border-top:1px solid #334155'>
            ${entry.challenges.map(c => `<div style='font-size:11px;color:#64748b;margin-top:4px'>❓ ${escapeHtml(c)}</div>`).join("")}
          </div>` : ""}
        </div>
      </div>`;
    }
    return "";
  }).join("");
}

function renderVerdict(verdict: JudgeVerdict): string {
  const signalColor = verdict.signal ? SIGNAL_COLOR[verdict.signal] : "#94a3b8";
  const signalText = verdict.signal ? SIGNAL_LABEL[verdict.signal] : "—";
  return `<div style='background:#1e293b;border-radius:12px;padding:20px;margin-top:16px'>
    <div style='display:flex;align-items:center;gap:12px;margin-bottom:16px'>
      <span style='font-size:20px;font-weight:700;color:${signalColor}'>${signalText}</span>
      ${verdict.score != null ? `<span style='font-size:13px;color:#64748b'>评分 ${verdict.score.toFixed(2)}</span>` : ""}
      <span style='font-size:11px;color:#475569;margin-left:auto'>${verdict.debate_quality}</span>
    </div>
    <p style='font-size:13px;color:#cbd5e1;line-height:1.7;margin-bottom:16px'>${escapeHtml(verdict.summary)}</p>
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px'>
      <div style='background:#0f172a;border-radius:8px;padding:12px'>
        <div style='font-size:11px;color:#f87171;margin-bottom:6px'>多头核心论点</div>
        <div style='font-size:12px;color:#94a3b8'>${escapeHtml(verdict.bull_core_thesis)}</div>
      </div>
      <div style='background:#0f172a;border-radius:8px;padding:12px'>
        <div style='font-size:11px;color:#34d399;margin-bottom:6px'>空头核心论点</div>
        <div style='font-size:12px;color:#94a3b8'>${escapeHtml(verdict.bear_core_thesis)}</div>
      </div>
    </div>
    ${verdict.risk_warnings?.length ? `<div style='margin-bottom:12px'>
      <div style='font-size:11px;color:#f59e0b;margin-bottom:6px'>风险提示</div>
      ${verdict.risk_warnings.map(w => `<div style='font-size:12px;color:#94a3b8;margin-top:4px'>⚠ ${escapeHtml(w)}</div>`).join("")}
    </div>` : ""}
    <div style='font-size:11px;color:#475569;border-top:1px solid #334155;padding-top:12px'>
      散户情绪：${escapeHtml(verdict.retail_sentiment_note)} ·
      主力资金：${escapeHtml(verdict.smart_money_note)}
    </div>
  </div>`;
}

export function exportDebateHtml(
  target: string,
  transcript: TranscriptItem[],
  blackboardItems: BlackboardItem[],
  judgeVerdict: JudgeVerdict | null,
): void {
  const now = new Date().toLocaleString("zh-CN");
  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>辩论记录 · ${escapeHtml(target)} · ${now}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0a0f1e; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 24px; }
  h1 { font-size: 18px; font-weight: 700; margin-bottom: 4px; }
  h2 { font-size: 13px; font-weight: 600; color: #94a3b8; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
</style>
</head>
<body>
<div style='max-width:960px;margin:0 auto'>
  <div style='margin-bottom:20px'>
    <h1>辩论记录 · ${escapeHtml(target)}</h1>
    <div style='font-size:12px;color:#64748b;margin-top:4px'>导出时间：${now}</div>
  </div>
  <div style='display:grid;grid-template-columns:1fr 240px;gap:20px;align-items:start'>
    <div>
      <div style='background:#111827;border:1px solid #1e293b;border-radius:16px;padding:16px;margin-bottom:16px'>
        <h2>辩论过程</h2>
        ${renderTranscript(transcript)}
      </div>
      ${judgeVerdict ? `<div style='background:#111827;border:1px solid #1e293b;border-radius:16px;padding:16px'>
        <h2>裁判裁决</h2>
        ${renderVerdict(judgeVerdict)}
      </div>` : ""}
    </div>
    <div style='background:#111827;border:1px solid #1e293b;border-radius:16px;padding:16px;position:sticky;top:24px'>
      <h2>黑板数据</h2>
      ${renderBlackboard(blackboardItems)}
    </div>
  </div>
  <div style='margin-top:24px;padding:12px 16px;background:#1e293b;border-radius:8px;font-size:11px;color:#f59e0b;border:1px solid #f59e0b33'>
    ⚠ 本报告由 AI 生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。
  </div>
</div>
</body>
</html>`;

  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const safeTarget = target.replace(/[^a-zA-Z0-9\u4e00-\u9fa5_-]/g, "_");
  a.download = `debate-${safeTarget}-${Date.now()}.html`;
  a.click();
  // 延迟 revoke，确保浏览器有时间启动下载
  setTimeout(() => URL.revokeObjectURL(url), 100);
}
```

- [ ] **Step 2: Commit**

```bash
git add web/lib/exportDebateHtml.ts
git commit -m "feat: 新增 exportDebateHtml 工具函数"
```

---

### Task 2: InputBar 新增导出按钮

**Files:**
- Modify: `web/components/debate/InputBar.tsx`
- Modify: `web/components/debate/DebatePage.tsx`

- [ ] **Step 1: 修改 `InputBar.tsx`，新增 `onExport` prop 和导出按钮**

在 `InputBarProps` 中新增：
```typescript
onExport?: () => void;
```

在组件签名中新增 `onExport`。

在 `</div>` 闭合标签之前（整个 InputBar 容器末尾，在 `{!isReplayMode && ...}` 块之外），新增导出按钮。

注意：导出按钮放在 `{!isReplayMode && ...}` 块外面，因此回放模式下 `status` 也可能是 `"completed"`，导出按钮在回放模式下同样显示——这是预期行为，用户可以导出回放记录。

```tsx
      {status === "completed" && onExport && (
        <button
          onClick={onExport}
          className="h-10 px-4 rounded-lg text-sm font-medium border border-[var(--border)]
                     text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)]
                     flex items-center gap-2 transition-colors shrink-0"
          title="导出 HTML"
        >
          <Download size={15} />
          <span>导出</span>
        </button>
      )}
```

在文件顶部 import 中新增 `Download`：
```typescript
import { Clock, Loader2, Download } from "lucide-react";
```

- [ ] **Step 2: 修改 `DebatePage.tsx`，传入 `onExport` 回调**

确认 `useDebateStore()` 解构中已有 `blackboardItems`、`judgeVerdict`、`currentTarget`、`transcript`——无需修改解构部分。

在文件顶部新增 import：
```typescript
import { exportDebateHtml } from "@/lib/exportDebateHtml";
```

在 `<InputBar>` 调用中新增 prop：
```tsx
onExport={() => exportDebateHtml(
  currentTarget ?? "",
  transcript,
  blackboardItems,
  judgeVerdict,
)}
```

- [ ] **Step 3: 手动验证**

启动前端 `cd web && npm run dev`，跑一次辩论，结束后点击"导出"按钮，确认：
- 下载了 `debate-<code>-<timestamp>.html` 文件
- 双击打开，深色主题，黑板数据在右侧，辩论记录在左侧，裁判裁决在底部
- 黑板数据有来源标签（公用/多头/空头）和结果摘要

- [ ] **Step 4: Commit**

```bash
git add web/components/debate/InputBar.tsx web/components/debate/DebatePage.tsx
git commit -m "feat: 辩论结束后支持导出 HTML 文件"
```

---

## 验收标准

1. `status === "completed"` 时 InputBar 右侧出现"导出"按钮
2. 点击后浏览器下载 `debate-<code>-<timestamp>.html`
3. HTML 文件可离线打开，深色主题，布局：左侧辩论流 + 右侧黑板面板
4. 黑板数据显示来源（公用/多头/空头）、标题、结果摘要（可见）
5. 裁判裁决包含信号、评分、多空核心论点、风险提示
6. 文件底部有免责声明
