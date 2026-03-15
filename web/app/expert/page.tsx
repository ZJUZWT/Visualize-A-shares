/**
 * 投资专家 Agent 页面
 */

"use client";

import { ChatArea } from "@/components/expert/ChatArea";
import { InputBar } from "@/components/expert/InputBar";

export default function ExpertPage() {
  return (
    <div className="flex h-screen bg-white">
      <div className="flex-1 flex flex-col">
        {/* 顶部标题栏 */}
        <div className="border-b border-gray-200 bg-white px-6 py-4">
          <h1 className="text-2xl font-bold text-gray-900">投资专家 Agent</h1>
          <p className="text-sm text-gray-600 mt-1">
            基于知识图谱和多因子分析的智能投资顾问
          </p>
        </div>

        {/* 聊天区域 */}
        <ChatArea />

        {/* 输入栏 */}
        <InputBar />
      </div>
    </div>
  );
}
