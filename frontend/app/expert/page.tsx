"use client";

import { useEffect } from "react";
import NavSidebar from "@/components/ui/NavSidebar";
import { ExpertSidebar } from "@/components/expert/ExpertSidebar";
import { ChatArea } from "@/components/expert/ChatArea";
import { InputBar } from "@/components/expert/InputBar";
import { useExpertStore } from "@/stores/useExpertStore";

export default function ExpertPageRoute() {
  const { fetchProfiles, activeExpert, profiles } = useExpertStore();
  const profile = profiles.find((p) => p.type === activeExpert);

  useEffect(() => {
    fetchProfiles();
  }, [fetchProfiles]);

  return (
    <main
      className="debate-dark relative h-screen flex flex-col"
      style={{
        marginLeft: 48,
        width: "calc(100vw - 48px)",
        background: "var(--bg-primary)",
      }}
    >
      <NavSidebar />

      <div className="flex h-full">
        {/* 左侧专家选择栏 */}
        <ExpertSidebar />

        {/* 右侧对话区 */}
        <div className="flex flex-col flex-1 min-w-0">
          {/* 顶部栏：当前专家信息 */}
          <div className="px-5 py-2.5 border-b border-[var(--border)] shrink-0 flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center text-sm"
              style={{ backgroundColor: (profile?.color ?? "#60A5FA") + "15" }}
            >
              {profile?.icon ?? "📊"}
            </div>
            <div>
              <h1 className="text-sm font-semibold text-[var(--text-primary)]">
                {profile?.name ?? "专家"}
              </h1>
              <p className="text-[10px] text-[var(--text-tertiary)]">
                {profile?.description ?? ""}
              </p>
            </div>

            {/* 能力标签 */}
            <div className="ml-auto flex gap-1.5 items-center">
              {(profile?.description ?? "")
                .split("、")
                .slice(0, 3)
                .map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-0.5 text-[10px] rounded-md"
                    style={{
                      backgroundColor: (profile?.color ?? "#60A5FA") + "12",
                      color: profile?.color ?? "#60A5FA",
                    }}
                  >
                    {tag}
                  </span>
                ))}
            </div>
          </div>

          {/* 对话区 */}
          <ChatArea />

          {/* 输入栏 */}
          <InputBar />
        </div>
      </div>
    </main>
  );
}
