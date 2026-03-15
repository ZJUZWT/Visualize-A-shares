/**
 * 思考面板 — 每条专家消息内嵌的可折叠思考过程
 */

"use client";

import { useState } from "react";
import type { ThinkingItem } from "@/types/expert";

interface ThinkingPanelProps {
  thinking: ThinkingItem[];
}

export function ThinkingPanel({ thinking }: ThinkingPanelProps) {
  const [open, setOpen] = useState(false);

  if (thinking.length === 0) return null;

  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
      >
        <span>{open ? "▼" : "▶"}</span>
        <span>思考过程 ({thinking.length} 步)</span>
      </button>

      {open && (
        <div className="mt-2 space-y-2 border-l-2 border-gray-200 pl-3">
          {thinking.map((item, i) => {
            if (item.type === "graph_recall") {
              return (
                <div key={i} className="text-xs">
                  <span className="font-medium text-blue-600">图谱召回</span>
                  {item.nodes.length === 0 ? (
                    <span className="text-gray-400 ml-1">（无相关节点）</span>
                  ) : (
                    <ul className="mt-1 space-y-0.5">
                      {item.nodes.map((n) => (
                        <li key={n.id} className="text-gray-600">
                          <span className="text-gray-400">[{n.type}]</span>{" "}
                          {n.label}
                          {n.confidence != null && (
                            <span className="text-gray-400 ml-1">
                              ({(n.confidence * 100).toFixed(0)}%)
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            }

            if (item.type === "tool_call") {
              return (
                <div key={i} className="text-xs">
                  <span className="font-medium text-orange-600">调用引擎</span>
                  <span className="ml-1 text-gray-600">
                    {item.data.engine}.{item.data.action}
                  </span>
                  {Object.keys(item.data.params).length > 0 && (
                    <span className="ml-1 text-gray-400">
                      {JSON.stringify(item.data.params)}
                    </span>
                  )}
                </div>
              );
            }

            if (item.type === "tool_result") {
              return (
                <div key={i} className="text-xs">
                  <span className="font-medium text-green-600">引擎结果</span>
                  <span className="ml-1 text-gray-600">
                    {item.data.engine}.{item.data.action}
                  </span>
                  <p className="mt-0.5 text-gray-500 break-words">
                    {item.data.summary.slice(0, 120)}
                    {item.data.summary.length > 120 && "…"}
                  </p>
                </div>
              );
            }

            if (item.type === "belief_updated") {
              return (
                <div key={i} className="text-xs">
                  <span className="font-medium text-purple-600">信念更新</span>
                  <div className="mt-1 space-y-0.5 text-gray-600">
                    <p>
                      <span className="text-gray-400">旧:</span>{" "}
                      {item.data.old.content}
                      <span className="text-gray-400 ml-1">
                        ({(item.data.old.confidence * 100).toFixed(0)}%)
                      </span>
                    </p>
                    <p>
                      <span className="text-gray-400">新:</span>{" "}
                      {item.data.new.content}
                      <span className="text-gray-400 ml-1">
                        ({(item.data.new.confidence * 100).toFixed(0)}%)
                      </span>
                    </p>
                    <p className="text-gray-400 italic">{item.data.reason}</p>
                  </div>
                </div>
              );
            }

            return null;
          })}
        </div>
      )}
    </div>
  );
}
