import type { ExpertMessage, ExpertProfile, ThinkingItem } from "@/types/expert";

/* ──────────────── 工具函数 ──────────────── */

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ──────────────── CSS 样式（完全复刻网页组件） ──────────────── */

const STYLES = `
  * { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg-primary: #0f172a;
    --bg-secondary: #1e293b;
    --bg-card: #1e293b;
    --border: #334155;
    --border-hover: #475569;
    --text-primary: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-tertiary: #64748b;
    --accent: #60a5fa;
  }

  body {
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
    -webkit-font-smoothing: antialiased;
    padding: 0; margin: 0;
    line-height: 1.6;
  }

  /* ─── 页面布局 ─── */
  .page-wrap {
    max-width: 100%;
    margin: 0 auto;
    padding: 24px 48px;
  }

  /* ─── 顶栏：复刻 page.tsx 中的专家信息栏 ─── */
  .top-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 0;
    background: var(--bg-primary);
  }
  .top-bar .avatar {
    width: 32px; height: 32px;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px;
    flex-shrink: 0;
  }
  .top-bar .info h1 {
    font-size: 14px; font-weight: 600; color: var(--text-primary);
    margin: 0;
  }
  .top-bar .info p {
    font-size: 10px; color: var(--text-tertiary); margin: 0;
  }
  .top-bar .tags {
    margin-left: auto;
    display: flex; gap: 6px; flex-wrap: wrap;
  }
  .top-bar .tag {
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 10px;
  }

  /* ─── 对话区：复刻 ChatArea.tsx 的间距 ─── */
  .chat-area {
    padding: 24px 24px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    background: var(--bg-primary);
  }

  /* ─── 用户消息气泡：复刻 MessageBubble.tsx ─── */
  .msg-user {
    display: flex;
    justify-content: flex-end;
    align-items: flex-end;
    gap: 8px;
  }
  .msg-user .bubble {
    max-width: 72%;
    padding: 10px 16px;
    border-radius: 16px 16px 4px 16px;
    color: #fff;
    font-size: 14px;
    line-height: 1.6;
    word-break: break-word;
  }

  /* ─── 专家消息：复刻 MessageBubble.tsx ─── */
  .msg-expert {
    display: flex;
    justify-content: flex-start;
    gap: 12px;
  }
  .msg-expert .avatar {
    flex-shrink: 0;
    width: 28px; height: 28px;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px;
    margin-top: 2px;
  }
  .msg-expert .body {
    flex: 1;
    min-width: 0;
    max-width: 80%;
  }

  /* ─── 思考面板：复刻 ThinkingPanel.tsx ─── */
  .thinking-panel {
    margin-bottom: 8px;
  }
  .thinking-header {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--text-tertiary);
    margin-bottom: 4px;
  }
  .thinking-header .count {
    padding: 2px 6px;
    border-radius: 9999px;
    background: var(--bg-primary);
    font-size: 10px;
  }
  .thinking-header .error-badge {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    padding: 2px 6px;
    border-radius: 9999px;
    background: rgba(239, 68, 68, 0.1);
    color: #f87171;
    font-size: 10px;
  }
  .thinking-list {
    border-radius: 12px;
    border: 1px solid var(--border);
    background: var(--bg-primary);
    overflow: hidden;
    font-size: 12px;
  }
  .thinking-item {
    padding: 8px 12px;
    display: flex;
    gap: 8px;
    border-bottom: 1px solid var(--border);
  }
  .thinking-item:last-child {
    border-bottom: none;
  }
  .thinking-item .icon {
    flex-shrink: 0;
    margin-top: 2px;
    font-size: 13px;
    width: 16px;
    text-align: center;
  }
  .thinking-item .content {
    flex: 1; min-width: 0;
  }
  .thinking-item .label {
    font-weight: 500;
    color: var(--text-secondary);
  }
  .thinking-item .error-tag {
    font-size: 9px;
    padding: 1px 4px;
    border-radius: 4px;
    background: rgba(239, 68, 68, 0.1);
    color: #f87171;
    margin-left: 6px;
  }
  .thinking-item .sub-text {
    margin-top: 2px;
    font-size: 10px;
    color: var(--text-tertiary);
    line-height: 1.5;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .thinking-item .sub-text.error-text {
    color: #f87171;
  }
  .thinking-item .node-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
  }
  .thinking-item .node-tag {
    padding: 2px 6px;
    border-radius: 6px;
    font-size: 10px;
  }

  /* 专家回复详情（折叠）：复刻 ExpertReplyDetail */
  .expert-reply-detail {
    margin-top: 6px;
  }
  .expert-reply-detail summary {
    font-size: 10px;
    color: var(--text-tertiary);
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;
    user-select: none;
  }
  .expert-reply-detail summary:hover {
    color: var(--text-secondary);
  }
  .expert-reply-detail summary::marker,
  .expert-reply-detail summary::-webkit-details-marker {
    display: none;
  }
  .expert-reply-detail summary::before {
    content: "▸";
    font-size: 9px;
  }
  .expert-reply-detail[open] summary::before {
    content: "▾";
  }
  .expert-reply-inner {
    margin-top: 4px;
    padding: 10px;
    border-radius: 8px;
    font-size: 11px;
    line-height: 1.7;
    color: var(--text-primary);
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    max-height: 400px;
    overflow-y: auto;
  }
  .expert-reply-inner.has-error {
    background: rgba(239, 68, 68, 0.05);
    border-color: rgba(239, 68, 68, 0.2);
  }

  /* ─── Markdown 内容：复刻 MarkdownContent + MiniMarkdown ─── */
  .md-content {
    font-size: 14px;
    color: var(--text-primary);
    line-height: 1.7;
    word-break: break-word;
  }
  .md-content p { margin-bottom: 8px; }
  .md-content p:last-child { margin-bottom: 0; }
  .md-content ul { list-style: disc; padding-left: 20px; margin-bottom: 8px; }
  .md-content ul ul { margin-bottom: 0; }
  .md-content ol { list-style: decimal; padding-left: 20px; margin-bottom: 8px; }
  .md-content ol ol { margin-bottom: 0; }
  .md-content li { line-height: 1.6; margin-bottom: 4px; }
  .md-content li:last-child { margin-bottom: 0; }
  .md-content strong { font-weight: 600; color: var(--text-primary); }
  .md-content em { font-style: italic; }
  .md-content h1 { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
  .md-content h2 { font-size: 14px; font-weight: 700; margin-bottom: 6px; }
  .md-content h3 { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
  .md-content code {
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
    background: var(--bg-primary);
    font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
  }
  .md-content pre {
    background: #0a0f1e;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    margin: 8px 0;
    overflow-x: auto;
    font-size: 12px;
    line-height: 1.5;
    font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
  }
  .md-content pre code {
    padding: 0;
    background: none;
    font-size: 12px;
    color: var(--text-secondary);
  }
  .md-content blockquote {
    border-left: 3px solid var(--accent);
    padding-left: 12px;
    margin: 8px 0;
    color: var(--text-tertiary);
    font-style: italic;
  }
  .md-content hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 12px 0;
  }

  /* 表格 */
  .md-content table {
    font-size: 12px;
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0;
    overflow-x: auto;
    display: block;
  }
  .md-content thead {
    border-bottom: 1px solid var(--border);
  }
  .md-content th {
    padding: 6px 8px;
    text-align: left;
    color: var(--text-secondary);
    font-weight: 500;
  }
  .md-content td {
    padding: 6px 8px;
    color: var(--text-primary);
  }
  .md-content tr {
    border-bottom: 1px solid var(--border);
  }
  .md-content tr:last-child {
    border-bottom: none;
  }

  /* ─── 迷你 Markdown（用于思考面板内的专家回复） ─── */
  .md-mini {
    font-size: 11px;
    line-height: 1.7;
    color: var(--text-primary);
  }
  .md-mini p { margin-bottom: 6px; }
  .md-mini p:last-child { margin-bottom: 0; }
  .md-mini ul { list-style: disc; padding-left: 16px; margin-bottom: 6px; }
  .md-mini ol { list-style: decimal; padding-left: 16px; margin-bottom: 6px; }
  .md-mini li { line-height: 1.6; margin-bottom: 2px; }
  .md-mini strong { font-weight: 600; color: var(--text-primary); }
  .md-mini code {
    padding: 1px 4px;
    border-radius: 4px;
    font-size: 10px;
    background: var(--bg-primary);
    font-family: monospace;
  }
  .md-mini pre {
    background: #0a0f1e;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px;
    margin: 4px 0;
    overflow-x: auto;
    font-size: 10px;
  }
  .md-mini pre code { padding: 0; background: none; font-size: 10px; color: var(--text-secondary); }
  .md-mini table { font-size: 10px; border-collapse: collapse; width: 100%; margin: 4px 0; }
  .md-mini th, .md-mini td { padding: 3px 6px; border-bottom: 1px solid var(--border); }
  .md-mini th { color: var(--text-secondary); font-weight: 500; text-align: left; }
  .md-mini td { color: var(--text-primary); }
  .md-mini blockquote {
    border-left: 2px solid var(--accent);
    padding-left: 8px;
    margin: 4px 0;
    color: var(--text-tertiary);
    font-style: italic;
  }
  .md-mini hr { border: none; border-top: 1px solid var(--border); margin: 6px 0; }

  /* ─── 页脚 ─── */
  .footer-disclaimer {
    margin-top: 24px;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
    font-size: 11px;
    color: #f59e0b;
    border: 1px solid rgba(245, 158, 11, 0.2);
  }
  .export-info {
    margin-bottom: 16px;
  }
  .export-info h1 {
    font-size: 18px; font-weight: 700; margin-bottom: 4px;
  }
  .export-info .meta {
    display: flex; gap: 16px; font-size: 11px; color: var(--text-tertiary); margin-top: 4px;
  }

  /* 滚动条 */
  ::-webkit-scrollbar { width: 5px; height: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  @media print {
    body { background: #fff; color: #1e293b; }
    :root {
      --bg-primary: #f8f9fa; --bg-secondary: #fff; --bg-card: #fff;
      --border: #e5e7eb; --text-primary: #1e293b; --text-secondary: #6b7280;
      --text-tertiary: #9ca3af;
    }
    .msg-user .bubble { color: #fff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  }
`;

/* ──────────────── 渲染思考过程（复刻 ThinkingPanel.tsx） ──────────────── */

function renderThinking(thinking: ThinkingItem[], color: string): string {
  if (thinking.length === 0) return "";

  const errorCount = thinking.filter(
    item =>
      (item.type === "tool_result" && item.data.hasError) ||
      (item.type === "tool_call" && item.status === "error")
  ).length;

  const items = thinking.map(item => {
    /* ─ graph_recall ─ */
    if (item.type === "graph_recall") {
      const nodes = (item.nodes ?? []).map(n =>
        `<span class="node-tag" style="background:${color}15;color:${color}">${esc(n.label)}</span>`
      ).join("");
      return `<div class="thinking-item">
        <span class="icon" style="color:${color}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="3"/><line x1="12" y1="8" x2="12" y2="16"/><circle cx="6" cy="19" r="3"/><circle cx="18" cy="19" r="3"/><line x1="12" y1="16" x2="6" y2="16"/><line x1="12" y1="16" x2="18" y2="16"/></svg>
        </span>
        <div class="content">
          <span class="label">图谱召回</span>
          ${nodes
            ? `<div class="node-tags">${nodes}</div>`
            : '<span style="color:var(--text-tertiary);margin-left:4px">无相关节点</span>'}
        </div>
      </div>`;
    }

    if (item.type === "clarification_request") {
      const options = item.data.options.map(option =>
        `<div class="node-tag" style="background:${color}15;color:${color}">${esc(option.label)}. ${esc(option.title)}</div>`
      ).join("");
      const selection = item.selectedOption
        ? `<p class="sub-text" style="margin-top:4px">已选择：${esc(item.selectedOption.label)}. ${esc(item.selectedOption.title)}</p>`
        : "";
      return `<div class="thinking-item">
        <span class="icon" style="color:${color}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.82 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        </span>
        <div class="content">
          <span class="label">方向确认</span>
          <p class="sub-text">${esc(item.data.question_summary)}</p>
          <div class="node-tags">${options}</div>
          ${selection}
        </div>
      </div>`;
    }

    if (item.type === "reasoning_summary") {
      return `<div class="thinking-item">
        <span class="icon" style="color:${color}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 11V7a4 4 0 0 0-8 0v4"/><rect width="18" height="12" x="3" y="11" rx="2"/><path d="M7 15h10"/></svg>
        </span>
        <div class="content">
          <span class="label">拆题摘要</span>
          <p class="sub-text">${esc(item.data.summary)}</p>
        </div>
      </div>`;
    }

    /* ─ tool_call ─ */
    if (item.type === "tool_call") {
      const isExpert = item.data.engine === "expert";
      const st = item.status ?? "pending";
      const hasError = st === "error";
      const iconColor = hasError ? "#f87171" : (isExpert ? "#ec4899" : "#34d399");
      // SVG icons matching lucide
      const iconSvg = st === "pending"
        ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>`
        : hasError
        ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`
        : `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
      const label = item.data.label || `${item.data.engine}.${item.data.action}`;

      let detail = "";
      if (isExpert && item.data.params?.question) {
        detail += `<p class="sub-text">&ldquo;${esc(String(item.data.params.question))}&rdquo;</p>`;
      }
      if (item.result) {
        if (isExpert && item.result.content) {
          const clean = item.result.content.replace(/^\[.*?专家工具链\].*?\n/, "");
          const replyLabel = esc(item.result.label || item.data.label || "专家");
          detail += `<details class="expert-reply-detail">
            <summary>展开${replyLabel}回复</summary>
            <div class="expert-reply-inner${item.result.hasError ? ' has-error' : ''}">
              <div class="md-mini" data-md>${esc(clean)}</div>
            </div>
          </details>`;
        } else if (!isExpert) {
          detail += `<p class="sub-text${item.result.hasError ? ' error-text' : ''}">${esc(item.result.summary || "")}</p>`;
        }
      }

      return `<div class="thinking-item">
        <span class="icon">${iconSvg}</span>
        <div class="content">
          <span class="label">${esc(label)}</span>
          ${hasError ? '<span class="error-tag">调用失败</span>' : ''}
          ${detail}
        </div>
      </div>`;
    }

    /* ─ tool_result ─ */
    if (item.type === "tool_result") {
      const isExpert = item.data.engine === "expert";
      const hasError = item.data.hasError;
      const iconColor = hasError ? "#f87171" : (isExpert ? "#ec4899" : "#34d399");
      const iconSvg = hasError
        ? `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`
        : `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
      const label = isExpert ? (item.data.label || "专家已回复") : "返回结果";

      let detail = "";
      if ((!isExpert || hasError) && item.data.summary) {
        detail += `<p class="sub-text${hasError ? ' error-text' : ''}">${esc(item.data.summary)}</p>`;
      }
      if (isExpert && item.data.content) {
        const clean = item.data.content.replace(/^\[.*?专家工具链\].*?\n/, "");
        const replyLabel = esc(item.data.label || "专家");
        detail += `<details class="expert-reply-detail"${!hasError ? ' open' : ''}>
          <summary>展开${replyLabel}回复</summary>
          <div class="expert-reply-inner${hasError ? ' has-error' : ''}">
            <div class="md-mini" data-md>${esc(clean)}</div>
          </div>
        </details>`;
      }

      return `<div class="thinking-item">
        <span class="icon">${iconSvg}</span>
        <div class="content">
          <span class="label" ${hasError ? 'style="color:#f87171"' : ''}>${esc(label)}</span>
          ${hasError ? '<span class="error-tag">调用失败</span>' : ''}
          ${detail}
        </div>
      </div>`;
    }

    /* ─ belief_updated ─ */
    if (item.type === "belief_updated") {
      return `<div class="thinking-item">
        <span class="icon" style="color:#a855f7">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
        </span>
        <div class="content">
          <span class="label">信念更新</span>
          <p class="sub-text">${esc(item.data.new.content)}</p>
          <p class="sub-text" style="margin-top:2px;font-size:9px">置信度: ${Math.round((item.data.old.confidence ?? 0) * 100)}% → ${Math.round((item.data.new.confidence ?? 0) * 100)}%</p>
        </div>
      </div>`;
    }

    if (item.type === "self_critique") {
      return `<div class="thinking-item">
        <span class="icon" style="color:#f59e0b">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        </span>
        <div class="content">
          <span class="label">自我质疑</span>
          <p class="sub-text">${esc(item.data.summary)}</p>
          ${item.data.counterpoints?.length ? `<p class="sub-text" style="margin-top:2px">反方观点：${esc(item.data.counterpoints.join("；"))}</p>` : ""}
          ${item.data.risks?.length ? `<p class="sub-text" style="margin-top:2px">风险：${esc(item.data.risks.join("；"))}</p>` : ""}
        </div>
      </div>`;
    }

    return "";
  }).join("");

  return `<div class="thinking-panel">
    <div class="thinking-header">
      <span>▾</span>
      <span>思考过程</span>
      <span class="count">${thinking.length}</span>
      ${errorCount > 0 ? `<span class="error-badge">⚠ ${errorCount} 项失败</span>` : ""}
    </div>
    <div class="thinking-list">${items}</div>
  </div>`;
}

/* ──────────────── 渲染单条消息 ──────────────── */

function renderMessage(msg: ExpertMessage, profile: ExpertProfile): string {
  const color = profile.color || "#60A5FA";

  if (msg.role === "user") {
    return `<div class="msg-user">
      <div class="bubble" style="background-color:${color}">${esc(msg.content)}</div>
    </div>`;
  }

  // expert 消息
  const thinkingHtml = renderThinking(msg.thinking, color);
  const contentHtml = msg.content
    ? `<div class="md-content" data-md>${esc(msg.content)}</div>`
    : "";

  return `<div class="msg-expert">
    <div class="avatar" style="background-color:${color}20">${profile.icon}</div>
    <div class="body">
      ${thinkingHtml}
      ${contentHtml}
    </div>
  </div>`;
}

/* ──────────────── 渲染顶部栏（复刻 page.tsx 中的信息栏） ──────────────── */

function renderTopBar(profile: ExpertProfile): string {
  const color = profile.color || "#60A5FA";
  const tags = (profile.description || "").split("、").slice(0, 3).map(tag =>
    `<span class="tag" style="background:${color}12;color:${color}">${esc(tag)}</span>`
  ).join("");

  return `<div class="top-bar">
    <div class="avatar" style="background-color:${color}15">${profile.icon}</div>
    <div class="info">
      <h1>${esc(profile.name)}</h1>
      <p>${esc(profile.description)}</p>
    </div>
    <div class="tags">${tags}</div>
  </div>`;
}

/* ──────────────── 主导出函数 ──────────────── */

/**
 * 导出对话为 HTML 文件
 * 使用 marked (CDN) 渲染 Markdown，CSS 完全复刻网页组件样式
 */
export function exportChatHtml(
  messages: ExpertMessage[],
  profile: ExpertProfile,
  sessionTitle?: string,
): void {
  if (messages.length === 0) return;

  const now = new Date().toLocaleString("zh-CN");
  const title = sessionTitle || `${profile.name}对话`;
  const userCount = messages.filter(m => m.role === "user").length;
  const expertCount = messages.filter(m => m.role === "expert").length;

  const messagesHtml = messages.map(msg => renderMessage(msg, profile)).join("");

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(title)} · ${esc(now)}</title>
<style>${STYLES}</style>
<!-- marked CDN: 用于 Markdown → HTML 渲染 -->
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"><\/script>
</head>
<body>
<div class="page-wrap">
  <div class="export-info">
    <h1>${esc(title)}</h1>
    <div class="meta">
      <span>导出时间：${now}</span>
      <span>共 ${messages.length} 条消息（${userCount} 问 ${expertCount} 答）</span>
    </div>
  </div>

  ${renderTopBar(profile)}

  <div class="chat-area">
    ${messagesHtml}
  </div>

  <div class="footer-disclaimer">
    ⚠ 本报告由 AI 生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。
  </div>
</div>

<script>
// 使用 marked 将所有 data-md 元素的转义文本渲染为 Markdown HTML
(function() {
  if (typeof marked === 'undefined') return;
  marked.setOptions({
    breaks: true,
    gfm: true,
  });
  document.querySelectorAll('[data-md]').forEach(function(el) {
    // 获取转义后的纯文本，先解码 HTML 实体
    var txt = el.textContent || '';
    el.innerHTML = marked.parse(txt);
  });
})();
<\/script>
</body>
</html>`;

  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const safeName = (profile.name || "chat").replace(/[^a-zA-Z0-9\u4e00-\u9fa5_-]/g, "_");
  a.download = `chat-${safeName}-${Date.now()}.html`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 100);
}
