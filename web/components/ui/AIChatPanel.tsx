"use client";

/**
 * AI 聊天面板 — 右下角浮动窗口
 *
 * 功能：
 * - 流式对话（SSE 逐 token 输出）
 * - LLM 配置面板（切换厂商/模型/API Key）
 * - 自动注入当前地形数据作为上下文
 * - 支持 Markdown 渲染
 */

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChatStore, PROVIDER_PRESETS } from "@/stores/useChatStore";
import type { ChatMessage, LLMConfig } from "@/stores/useChatStore";

export default function AIChatPanel() {
  const { isPanelOpen, togglePanel } = useChatStore();

  return (
    <>
      {/* 浮动按钮 */}
      <button
        onClick={togglePanel}
        className="overlay fixed bottom-6 right-6 w-12 h-12 rounded-full bg-gradient-to-br from-[#4F8EF7] to-[#7B68EE] shadow-lg hover:shadow-xl transition-all duration-300 flex items-center justify-center text-white text-xl z-50 hover:scale-105 active:scale-95"
        title="AI 智能分析"
      >
        {isPanelOpen ? "✕" : "🤖"}
      </button>

      {/* 聊天面板 */}
      {isPanelOpen && <ChatWindow />}
    </>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 聊天窗口
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function ChatWindow() {
  const {
    messages,
    isStreaming,
    error,
    isConfigOpen,
    llmConfig,
    toggleConfig,
    sendMessage,
    clearMessages,
  } = useChatStore();

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 发送消息
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    await sendMessage(text);
  }, [input, isStreaming, sendMessage]);

  // Enter 发送，Shift+Enter 换行
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const hasApiKey = !!llmConfig.apiKey;

  return (
    <div className="overlay fixed bottom-20 right-6 w-[400px] h-[560px] flex flex-col glass-panel shadow-2xl z-40 overflow-hidden animate-in">
      {/* ─── 顶栏 ─────────────────── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <span className="text-base">🤖</span>
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            AI 智能分析
          </span>
          {hasApiKey && (
            <span className="text-[10px] text-[var(--text-tertiary)] bg-[var(--accent-light)] px-2 py-0.5 rounded-full">
              {llmConfig.model}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={clearMessages}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-[var(--text-tertiary)] transition-colors"
            title="清空对话"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
          <button
            onClick={toggleConfig}
            className={`p-1.5 rounded-lg transition-colors ${
              isConfigOpen
                ? "bg-[var(--accent-light)] text-[var(--accent)]"
                : "hover:bg-gray-100 text-[var(--text-tertiary)]"
            }`}
            title="LLM 设置"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>
      </div>

      {/* ─── 配置面板 / 消息列表 ─── */}
      {isConfigOpen ? (
        <ConfigPanel />
      ) : (
        <>
          {/* 消息列表 */}
          <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-3 space-y-3">
            {messages.length === 0 && !error && (
              <EmptyState hasApiKey={hasApiKey} />
            )}

            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {error && (
              <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 border border-red-100">
                ❌ {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* 输入框 */}
          <div className="px-4 py-3 border-t border-gray-100">
            <div className="flex gap-2 items-end">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  hasApiKey
                    ? "输入问题... (Enter 发送)"
                    : "请先点击 ⚙️ 配置 API Key"
                }
                disabled={!hasApiKey}
                rows={1}
                className="flex-1 resize-none rounded-xl border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]/20 disabled:opacity-50 disabled:cursor-not-allowed max-h-24 bg-white"
                style={{ minHeight: "38px" }}
                onInput={(e) => {
                  const t = e.currentTarget;
                  t.style.height = "38px";
                  t.style.height = Math.min(t.scrollHeight, 96) + "px";
                }}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isStreaming || !hasApiKey}
                className="flex-shrink-0 w-9 h-9 rounded-xl bg-[var(--accent)] text-white flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[var(--accent)]/90 transition-colors"
              >
                {isStreaming ? (
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 消息气泡
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-[var(--accent)] text-white rounded-br-md"
            : "bg-gray-100 text-[var(--text-primary)] rounded-bl-md"
        }`}
      >
        {message.content ? (
          isUser ? (
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          ) : (
            <div className="markdown-body break-words">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // 代码块
                  code({ className, children, ...props }) {
                    const isInline = !className;
                    if (isInline) {
                      return (
                        <code className="bg-black/10 rounded px-1 py-0.5 text-xs font-mono" {...props}>
                          {children}
                        </code>
                      );
                    }
                    return (
                      <div className="my-2 rounded-lg overflow-hidden bg-gray-800 text-gray-100">
                        <div className="flex items-center justify-between px-3 py-1.5 bg-gray-700/50 text-[10px] text-gray-400">
                          <span>{className?.replace("language-", "") || "code"}</span>
                          <button
                            onClick={() => {
                              navigator.clipboard.writeText(String(children));
                            }}
                            className="hover:text-white transition-colors"
                          >
                            复制
                          </button>
                        </div>
                        <pre className="px-3 py-2 overflow-x-auto text-xs">
                          <code className={className} {...props}>{children}</code>
                        </pre>
                      </div>
                    );
                  },
                  // 表格
                  table({ children }) {
                    return (
                      <div className="my-2 overflow-x-auto rounded-lg border border-gray-200">
                        <table className="w-full text-xs">{children}</table>
                      </div>
                    );
                  },
                  th({ children }) {
                    return <th className="px-2 py-1.5 bg-gray-200/50 text-left font-medium border-b border-gray-200">{children}</th>;
                  },
                  td({ children }) {
                    return <td className="px-2 py-1.5 border-b border-gray-100">{children}</td>;
                  },
                  // 段落
                  p({ children }) {
                    return <p className="mb-1.5 last:mb-0">{children}</p>;
                  },
                  // 标题
                  h1({ children }) {
                    return <h1 className="text-base font-bold mb-2 mt-3 first:mt-0">{children}</h1>;
                  },
                  h2({ children }) {
                    return <h2 className="text-sm font-bold mb-1.5 mt-2.5 first:mt-0">{children}</h2>;
                  },
                  h3({ children }) {
                    return <h3 className="text-sm font-semibold mb-1 mt-2 first:mt-0">{children}</h3>;
                  },
                  // 列表
                  ul({ children }) {
                    return <ul className="list-disc list-inside mb-1.5 space-y-0.5">{children}</ul>;
                  },
                  ol({ children }) {
                    return <ol className="list-decimal list-inside mb-1.5 space-y-0.5">{children}</ol>;
                  },
                  // 链接
                  a({ href, children }) {
                    return (
                      <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline hover:text-blue-700">
                        {children}
                      </a>
                    );
                  },
                  // 引用
                  blockquote({ children }) {
                    return <blockquote className="border-l-2 border-gray-300 pl-2 my-1.5 text-gray-600 italic">{children}</blockquote>;
                  },
                  // 分割线
                  hr() {
                    return <hr className="my-2 border-gray-200" />;
                  },
                  // 加粗
                  strong({ children }) {
                    return <strong className="font-semibold">{children}</strong>;
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )
        ) : (
          message.isStreaming ? <TypingDots /> : ""
        )}
        {message.isStreaming && message.content && (
          <span className="inline-block w-1.5 h-4 bg-current opacity-60 animate-pulse ml-0.5 align-text-bottom rounded-sm" />
        )}
      </div>
    </div>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 空状态
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function EmptyState({ hasApiKey }: { hasApiKey: boolean }) {
  const { sendMessage } = useChatStore();

  if (!hasApiKey) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#4F8EF7]/10 to-[#7B68EE]/10 flex items-center justify-center text-3xl mb-4">
          🔑
        </div>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          配置 LLM 服务
        </h3>
        <p className="text-xs text-[var(--text-tertiary)] mb-4">
          点击右上角 ⚙️ 按钮，选择 AI 厂商并填写 API Key
        </p>
        <div className="text-[10px] text-[var(--text-tertiary)] space-y-1">
          <p>支持: OpenAI · DeepSeek · 通义千问 · Kimi · 智谱 · Claude</p>
          <p>大部分厂商只需填 API Key 即可</p>
        </div>
      </div>
    );
  }

  const suggestions = [
    "分析当前市场整体走势",
    "哪些板块今天表现最好？",
    "解读当前聚类分布的含义",
    "给我推荐值得关注的股票",
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#4F8EF7]/10 to-[#7B68EE]/10 flex items-center justify-center text-2xl mb-4">
        🤖
      </div>
      <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">
        AI 分析助手
      </h3>
      <p className="text-xs text-[var(--text-tertiary)] mb-4">
        基于实时地形数据，为你提供市场洞察
      </p>
      <div className="w-full space-y-1.5">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => sendMessage(s)}
            className="w-full text-left px-3 py-2 rounded-xl text-xs text-[var(--text-secondary)] bg-gray-50 hover:bg-[var(--accent-light)] hover:text-[var(--accent)] transition-colors"
          >
            💡 {s}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * LLM 配置面板
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function ConfigPanel() {
  const {
    llmConfig,
    selectedPreset,
    setSelectedPreset,
    updateLLMConfig,
    saveLLMConfig,
    toggleConfig,
  } = useChatStore();

  const [saving, setSaving] = useState(false);
  const [showKey, setShowKey] = useState(false);

  const preset = PROVIDER_PRESETS[selectedPreset];

  const handleSave = async () => {
    setSaving(true);
    await saveLLMConfig();
    setSaving(false);
    toggleConfig();
  };

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 space-y-4">
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">
        LLM 服务配置
      </h3>

      {/* 厂商选择 */}
      <div>
        <label className="text-xs text-[var(--text-secondary)] mb-1.5 block">
          AI 厂商
        </label>
        <div className="grid grid-cols-2 gap-1.5">
          {Object.entries(PROVIDER_PRESETS).map(([key, p]) => (
            <button
              key={key}
              onClick={() => setSelectedPreset(key)}
              className={`text-xs px-3 py-2 rounded-lg transition-colors text-left ${
                selectedPreset === key
                  ? "bg-[var(--accent-light)] text-[var(--accent)] font-medium border border-[var(--accent)]/20"
                  : "bg-gray-50 text-[var(--text-secondary)] hover:bg-gray-100"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* API Key */}
      <div>
        <label className="text-xs text-[var(--text-secondary)] mb-1.5 block">
          API Key
        </label>
        <div className="relative">
          <input
            type={showKey ? "text" : "password"}
            value={llmConfig.apiKey}
            onChange={(e) => updateLLMConfig({ apiKey: e.target.value })}
            placeholder="sk-..."
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 pr-10 focus:outline-none focus:border-[var(--accent)] bg-white"
          />
          <button
            onClick={() => setShowKey(!showKey)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
          >
            {showKey ? "🙈" : "👁️"}
          </button>
        </div>
      </div>

      {/* Base URL */}
      <div>
        <label className="text-xs text-[var(--text-secondary)] mb-1.5 block">
          Base URL
        </label>
        <input
          type="text"
          value={llmConfig.baseUrl}
          onChange={(e) => updateLLMConfig({ baseUrl: e.target.value })}
          placeholder="https://api.openai.com/v1"
          className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-[var(--accent)] bg-white"
        />
        <p className="text-[10px] text-[var(--text-tertiary)] mt-1">
          {selectedPreset !== "custom"
            ? `已自动填充 ${preset?.label} 的地址`
            : "填写你的自定义 API 地址"}
        </p>
      </div>

      {/* 模型 */}
      <div>
        <label className="text-xs text-[var(--text-secondary)] mb-1.5 block">
          模型
        </label>
        {preset && preset.models.length > 0 ? (
          <select
            value={llmConfig.model}
            onChange={(e) => updateLLMConfig({ model: e.target.value })}
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-[var(--accent)] bg-white"
          >
            {preset.models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={llmConfig.model}
            onChange={(e) => updateLLMConfig({ model: e.target.value })}
            placeholder="模型名称"
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-[var(--accent)] bg-white"
          />
        )}
      </div>

      {/* 温度 */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs text-[var(--text-secondary)]">
            温度 (创造性)
          </label>
          <span className="text-xs font-mono text-[var(--accent)]">
            {llmConfig.temperature.toFixed(1)}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={llmConfig.temperature}
          onChange={(e) =>
            updateLLMConfig({ temperature: parseFloat(e.target.value) })
          }
        />
      </div>

      {/* 保存 / 取消 */}
      <div className="flex gap-2 pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary flex-1 text-xs"
        >
          {saving ? "保存中..." : "✓ 保存配置"}
        </button>
        <button
          onClick={toggleConfig}
          className="btn-secondary flex-1 text-xs"
        >
          取消
        </button>
      </div>

      {/* 提示信息 */}
      <div className="text-[10px] text-[var(--text-tertiary)] bg-gray-50 rounded-lg px-3 py-2 space-y-1">
        <p>💡 API Key 仅存储在你的浏览器本地，不会上传到任何第三方。</p>
        <p>
          📡 请求通过后端中转发送到 LLM 厂商。如需直接前端调用（无后端），
          请使用「自定义」模式。
        </p>
      </div>
    </div>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 小组件
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function TypingDots() {
  return (
    <span className="inline-flex gap-1 py-1">
      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: "0ms" }} />
      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: "150ms" }} />
      <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: "300ms" }} />
    </span>
  );
}
