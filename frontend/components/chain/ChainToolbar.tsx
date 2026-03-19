"use client";

import { useState, useCallback } from "react";
import { Search, Plus, RotateCcw, Brain, Trash2, Globe, X, Link2 } from "lucide-react";
import { useChainStore } from "@/stores/useChainStore";

export default function ChainToolbar() {
  const {
    parseAndBuild, addNode, expandAll, reindexLinks, simulate, reset, clearAllShocks,
    status, subject, shocks,
    expandDepth, setExpandDepth,
  } = useChainStore();
  const [input, setInput] = useState("");
  const [showAddNode, setShowAddNode] = useState(false);
  const [addNodeInput, setAddNodeInput] = useState("");

  const handleBuild = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed) return;
    parseAndBuild(trimmed);
    setInput("");
  }, [input, parseAndBuild]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleBuild();
      }
    },
    [handleBuild],
  );

  const handleAddNode = useCallback(() => {
    const trimmed = addNodeInput.trim();
    if (!trimmed) return;
    addNode(trimmed);
    setAddNodeInput("");
    setShowAddNode(false);
  }, [addNodeInput, addNode]);

  const isAdding = status === "building" || status === "adding";
  const isSimulating = status === "simulating";
  const hasNodes = useChainStore((s) => s.nodes.length > 0);
  const hasShocks = shocks.size > 0;

  return (
    <div
      className="flex items-center gap-3 px-5 py-3 border-b border-[var(--border)]"
      style={{ background: "var(--bg-secondary)" }}
    >
      {/* 搜索输入 */}
      <div className="flex items-center flex-1 gap-2 px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
        <Search size={16} className="text-[var(--text-secondary)] shrink-0" />
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入任意主体（如：中泰化学、黄金与石油的关系），回车添加"
          className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder-[var(--text-secondary)] outline-none"
          disabled={isAdding || isSimulating}
        />
      </div>

      {/* 添加按钮 */}
      <button
        onClick={handleBuild}
        disabled={isAdding || isSimulating || !input.trim()}
        className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium
                   bg-[var(--accent)] text-white hover:opacity-90
                   disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
      >
        <Plus size={14} />
        {isAdding ? "添加中..." : "添加"}
      </button>

      {/* 全局扩展 + 深度选择 */}
      <div className="flex items-center">
        <button
          onClick={() => expandAll()}
          disabled={isAdding || isSimulating || !hasNodes}
          className="flex items-center gap-1.5 px-3 py-2 rounded-l-lg text-sm font-medium
                     bg-[var(--bg-primary)] border border-[var(--border)] text-[var(--text-primary)]
                     hover:bg-[var(--border)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="展开所有末端/源头节点"
        >
          <Globe size={14} />
          全局扩展
        </button>
        {/* 深度快选 */}
        <div className="flex border border-l-0 border-[var(--border)] rounded-r-lg overflow-hidden">
          {[1, 2, 3].map((d) => (
            <button
              key={d}
              onClick={() => setExpandDepth(d)}
              className="px-2 py-2 text-xs font-medium transition-all border-r border-[var(--border)] last:border-r-0"
              style={{
                background: expandDepth === d ? "var(--accent)" : "var(--bg-primary)",
                color: expandDepth === d ? "#fff" : "var(--text-secondary)",
              }}
              title={`展开深度 ${d} 层`}
            >
              {d}
            </button>
          ))}
        </div>
      </div>

      {/* 重整关系 */}
      <button
        onClick={() => reindexLinks()}
        disabled={isAdding || isSimulating || !hasNodes}
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium
                   bg-[var(--bg-primary)] border border-[var(--border)] text-[var(--text-primary)]
                   hover:bg-[var(--border)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        title="审视全图，补全缺失的关系边"
      >
        <Link2 size={14} />
        重整关系
      </button>

      {/* 手动添加节点 */}
      <div className="relative">
        <button
          onClick={() => setShowAddNode(!showAddNode)}
          disabled={isAdding || isSimulating || !hasNodes}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium
                     bg-[var(--bg-primary)] border border-[var(--border)] text-[var(--text-primary)]
                     hover:bg-[var(--border)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="手动添加节点"
        >
          <Plus size={14} />
          添加节点
        </button>
        {showAddNode && (
          <div
            className="absolute top-full left-0 mt-1 p-2 rounded-lg border border-[var(--border)] z-20
                       flex items-center gap-2 shadow-xl"
            style={{ background: "var(--bg-secondary)", width: 240 }}
          >
            <input
              type="text"
              value={addNodeInput}
              onChange={(e) => setAddNodeInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleAddNode(); }}
              placeholder="节点名称（如：黄金）"
              className="flex-1 px-2 py-1.5 rounded bg-[var(--bg-primary)] text-sm text-[var(--text-primary)]
                         placeholder-[var(--text-secondary)] outline-none border border-[var(--border)]"
              autoFocus
            />
            <button
              onClick={handleAddNode}
              disabled={!addNodeInput.trim()}
              className="px-2 py-1.5 rounded bg-[var(--accent)] text-white text-sm
                         disabled:opacity-40 transition-opacity"
            >
              加入
            </button>
            <button
              onClick={() => { setShowAddNode(false); setAddNodeInput(""); }}
              className="p-1 rounded hover:bg-[var(--bg-primary)] text-[var(--text-secondary)]"
            >
              <X size={14} />
            </button>
          </div>
        )}
      </div>

      {/* AI 深度解读 */}
      <button
        onClick={() => simulate()}
        disabled={isSimulating || !hasShocks}
        className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium
                   bg-amber-600 text-white hover:opacity-90
                   disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
        title={hasShocks ? `AI 解读 ${shocks.size} 个冲击` : "请先在节点上设置涨/跌"}
      >
        <Brain size={14} />
        {isSimulating
          ? "解读中..."
          : hasShocks
            ? `AI 深度解读 (${shocks.size})`
            : "设置冲击后解读"}
      </button>

      {hasShocks && (
        <button
          onClick={clearAllShocks}
          disabled={isSimulating}
          className="p-2 rounded-lg hover:bg-[var(--bg-primary)] text-[var(--text-secondary)] transition-colors"
          title="清除所有冲击"
        >
          <Trash2 size={16} />
        </button>
      )}

      {/* 当前主体标签 */}
      {subject && (
        <div className="text-xs text-[var(--text-secondary)] px-2 py-1 rounded bg-[var(--bg-primary)] border border-[var(--border)]">
          🔗 {subject}
        </div>
      )}

      {/* 重置 */}
      <button
        onClick={reset}
        className="p-2 rounded-lg hover:bg-[var(--bg-primary)] text-[var(--text-secondary)] transition-colors"
        title="重置"
      >
        <RotateCcw size={16} />
      </button>
    </div>
  );
}
