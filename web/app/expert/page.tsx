"use client";

import NavSidebar from "@/components/ui/NavSidebar";
import { ChatArea } from "@/components/expert/ChatArea";
import { InputBar } from "@/components/expert/InputBar";

export default function ExpertPageRoute() {
  return (
    <main
      className="relative h-screen bg-[var(--bg-primary)] flex flex-col"
      style={{ marginLeft: 48, width: "calc(100vw - 48px)" }}
    >
      <NavSidebar />
      <div className="flex flex-col h-full">
        <div className="px-5 py-4 border-b border-[var(--border)] shrink-0">
          <h1 className="text-base font-semibold text-[var(--text-primary)]">投资专家</h1>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">
            有自己世界观、会主动查资料、能被你说服的 A 股投资专家
          </p>
        </div>
        <ChatArea />
        <InputBar />
      </div>
    </main>
  );
}
