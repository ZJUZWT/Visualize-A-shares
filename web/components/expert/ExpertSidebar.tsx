"use client";

import { useExpertStore } from "@/stores/useExpertStore";
import type { ExpertProfile, ExpertType } from "@/types/expert";
import { Trash2 } from "lucide-react";

export function ExpertSidebar() {
  const { profiles, activeExpert, setActiveExpert, clearChat, chatHistories } =
    useExpertStore();

  return (
    <div className="w-[220px] shrink-0 border-r border-[var(--border)] bg-[var(--bg-primary)] flex flex-col h-full">
      {/* 标题 */}
      <div className="px-4 py-4 border-b border-[var(--border)]">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">专家团队</h2>
        <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5">
          选择领域专家进行对话
        </p>
      </div>

      {/* 专家列表 */}
      <div className="flex-1 overflow-y-auto px-2 py-3 space-y-1.5">
        {profiles.map((profile) => (
          <ExpertCard
            key={profile.type}
            profile={profile}
            isActive={activeExpert === profile.type}
            hasMessages={(chatHistories[profile.type]?.length ?? 0) > 0}
            onClick={() => setActiveExpert(profile.type)}
          />
        ))}
      </div>

      {/* 底部操作 */}
      <div className="px-3 py-3 border-t border-[var(--border)]">
        <button
          onClick={clearChat}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs
                     text-[var(--text-tertiary)] hover:text-[var(--red-stock)]
                     rounded-lg hover:bg-[var(--red-stock)]/5 transition-all duration-150"
        >
          <Trash2 size={12} />
          清除当前对话
        </button>
      </div>
    </div>
  );
}

function ExpertCard({
  profile,
  isActive,
  hasMessages,
  onClick,
}: {
  profile: ExpertProfile;
  isActive: boolean;
  hasMessages: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        w-full text-left px-3 py-2.5 rounded-xl transition-all duration-150
        ${
          isActive
            ? "bg-[var(--accent)]/10 border border-[var(--accent)]/30"
            : "hover:bg-[var(--bg-secondary)] border border-transparent"
        }
      `}
    >
      <div className="flex items-center gap-2.5">
        {/* 图标 */}
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center text-sm shrink-0"
          style={{
            backgroundColor: isActive ? profile.color + "20" : "var(--bg-secondary)",
          }}
        >
          {profile.icon}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span
              className={`text-xs font-medium truncate ${
                isActive ? "text-[var(--accent)]" : "text-[var(--text-primary)]"
              }`}
            >
              {profile.name}
            </span>
            {hasMessages && (
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ backgroundColor: profile.color }}
              />
            )}
          </div>
          <p className="text-[10px] text-[var(--text-tertiary)] truncate mt-0.5">
            {profile.description}
          </p>
        </div>
      </div>
    </button>
  );
}
