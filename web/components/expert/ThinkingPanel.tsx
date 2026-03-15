/**
 * 思考面板组件 — 显示信念、立场和知识图谱统计
 */

import { useExpertStore } from "@/stores/useExpertStore";
import { useEffect } from "react";

export function ThinkingPanel() {
  const { beliefs, stances, kgStats, fetchBeliefs, fetchStances, fetchKGStats } =
    useExpertStore();

  useEffect(() => {
    fetchBeliefs();
    fetchStances();
    fetchKGStats();
  }, [fetchBeliefs, fetchStances, fetchKGStats]);

  return (
    <div className="w-80 border-l border-gray-200 bg-gray-50 overflow-y-auto">
      {/* 信念部分 */}
      <div className="p-4 border-b border-gray-200">
        <h3 className="font-semibold text-sm mb-3 text-gray-900">信念系统</h3>
        <div className="space-y-2">
          {beliefs.length === 0 ? (
            <p className="text-xs text-gray-500">暂无信念</p>
          ) : (
            beliefs.slice(0, 3).map((belief) => (
              <div key={belief.id} className="text-xs bg-white p-2 rounded">
                <p className="text-gray-700 mb-1">{belief.content}</p>
                <div className="flex justify-between items-center">
                  <span className="text-gray-500">置信度</span>
                  <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500"
                      style={{ width: `${belief.confidence * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 立场部分 */}
      <div className="p-4 border-b border-gray-200">
        <h3 className="font-semibold text-sm mb-3 text-gray-900">投资立场</h3>
        <div className="space-y-2">
          {stances.length === 0 ? (
            <p className="text-xs text-gray-500">暂无立场</p>
          ) : (
            stances.slice(0, 3).map((stance) => (
              <div key={stance.id} className="text-xs bg-white p-2 rounded">
                <div className="flex justify-between items-center mb-1">
                  <span className="font-medium text-gray-700">{stance.target}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-white text-xs font-semibold ${
                      stance.signal === "bullish"
                        ? "bg-green-500"
                        : stance.signal === "bearish"
                        ? "bg-red-500"
                        : "bg-gray-500"
                    }`}
                  >
                    {stance.signal === "bullish"
                      ? "看多"
                      : stance.signal === "bearish"
                      ? "看空"
                      : "中立"}
                  </span>
                </div>
                <div className="flex justify-between text-gray-600">
                  <span>评分: {stance.score.toFixed(1)}</span>
                  <span>置信度: {(stance.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 知识图谱统计 */}
      <div className="p-4">
        <h3 className="font-semibold text-sm mb-3 text-gray-900">知识图谱</h3>
        {kgStats ? (
          <div className="space-y-2 text-xs">
            <div className="flex justify-between bg-white p-2 rounded">
              <span className="text-gray-600">节点数</span>
              <span className="font-semibold text-gray-900">
                {kgStats.num_nodes}
              </span>
            </div>
            <div className="flex justify-between bg-white p-2 rounded">
              <span className="text-gray-600">边数</span>
              <span className="font-semibold text-gray-900">
                {kgStats.num_edges}
              </span>
            </div>
            {Object.entries(kgStats.node_types).length > 0 && (
              <div className="bg-white p-2 rounded">
                <p className="text-gray-600 mb-1">节点类型</p>
                <div className="space-y-1">
                  {Object.entries(kgStats.node_types).map(([type, count]) => (
                    <div key={type} className="flex justify-between text-gray-700">
                      <span>{type}</span>
                      <span>{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-gray-500">加载中...</p>
        )}
      </div>
    </div>
  );
}
