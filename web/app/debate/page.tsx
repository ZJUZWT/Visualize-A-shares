"use client";

import NavSidebar from "@/components/ui/NavSidebar";

export default function DebatePage() {
  return (
    <main className="relative w-screen h-screen overflow-hidden bg-[var(--bg-primary)] ml-12">
      <NavSidebar />
      <div className="flex items-center justify-center h-full">
        <p className="text-[var(--text-tertiary)]">辩论页面加载中...</p>
      </div>
    </main>
  );
}
