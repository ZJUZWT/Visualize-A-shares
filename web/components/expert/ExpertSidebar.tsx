"use client";

import { useEffect } from "react";
import { useExpertStore } from "@/stores/useExpertStore";
import type { ExpertProfile, ExpertType, Session } from "@/types/expert";
import { Trash2, Plus, MessageSquare } from "lucide-react";

export function ExpertSidebar() {
  const {
    profiles,
    activeExpert,
    setActiveExpert,
    clearChat,
    chatHistories,
    sessions,
    activeSessions,
    fetchSessions,
    createSession,
    switchSession,
    deleteSession,
  } = useExpertStore();

  const currentSessions = sessions[activeExpert] || [];
  const activeSessionId = activeSessions[activeExpert];

  // 初始化时加载当前专家的 sessions
  useEffect(() => {
    fetchSessions(activeExpert);
  }, [activeExpert, fetchSessions]);

  return (
    <div className="w-[220px] shrink-0 border-r border-[var(--border)] bg-[var(--bg-primary)] flex flex-col h-full">
      {/* 标题 */}
      <div className="px-4 py-4 border-b border-[var(--border)]">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">
          专家团队
        </h2>
        <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5">
          选择领域专家进行对话
        </p>
      </div>

      {/* 专家列表 */}
      <div className="px-2 py-3 space-y-1.5 border-b border-[var(--border)]">
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

      {/* 对话 Session 列表 */}
      <div className="flex-1 flex flex-col min-h-0">
        <div className="px-3 py-2.5 flex items-center justify-between">
          <span className="text-[10px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider">
            对话记录
          </span>
          <button
            onClick={() => createSession()}
            className="p-1 rounded hover:bg-[var(--bg-secondary)] text-[var(--text-tertiary)] hover:text-[var(--accent)] transition-colors"
            title="新建对话"
          >
            <Plus size={13} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
          {/* 当前对话（未保存） */}
          {!activeSessionId && (chatHistories[activeExpert]?.length ?? 0) > 0 && (
            <div className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-[var(--accent)]/8 border border-[var(--accent)]/20">
              <MessageSquare
                size={12}
                className="shrink-0 text-[var(--accent)]"
              />
              <span className="text-[11px] text-[var(--accent)] truncate font-medium">
                当前对话
              </span>
            </div>
          )}

          {currentSessions.map((session) => (
            <SessionItem
              key={session.id}
              session={session}
              isActive={activeSessionId === session.id}
              onClick={() => switchSession(session.id)}
              onDelete={(e) => {
                e.stopPropagation();
                deleteSession(session.id);
              }}
            />
          ))}

          {currentSessions.length === 0 &&
            (chatHistories[activeExpert]?.length ?? 0) === 0 && (
              <p className="text-[10px] text-[var(--text-tertiary)] text-center py-6 px-2">
                暂无对话记录
                <br />
                发送消息开始新对话
              </p>
            )}
        </div>
      </div>

      {/* 底部操作 */}
      <div className="px-3 py-3 border-t border-[var(--border)]">
        <button
          onClick={clearChat}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs
                     text-[var(--text-tertiary)] hover:text-[var(--red-stock)]
                     rounded-lg hover:bg-[var(--red-stock)]/5 transition-all duration-150"
        >
          <Plus size={12} />
          新建对话
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
        w-full text-left px-3 py-2 rounded-xl transition-all duration-150
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
          className="w-7 h-7 rounded-lg flex items-center justify-center text-xs shrink-0"
          style={{
            backgroundColor: isActive
              ? profile.color + "20"
              : "var(--bg-secondary)",
          }}
        >
          {profile.icon}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span
              className={`text-[11px] font-medium truncate ${
                isActive
                  ? "text-[var(--accent)]"
                  : "text-[var(--text-primary)]"
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
        </div>
      </div>
    </button>
  );
}

function SessionItem({
  session,
  isActive,
  onClick,
  onDelete,
}: {
  session: Session;
  isActive: boolean;
  onClick: () => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onClick(); }}
      className={`
        group w-full text-left px-2.5 py-2 rounded-lg transition-all duration-150 flex items-center gap-2 cursor-pointer
        ${
          isActive
            ? "bg-[var(--accent)]/8 border border-[var(--accent)]/20"
            : "hover:bg-[var(--bg-secondary)] border border-transparent"
        }
      `}
    >
      <MessageSquare
        size={12}
        className={`shrink-0 ${
          isActive ? "text-[var(--accent)]" : "text-[var(--text-tertiary)]"
        }`}
      />
      <div className="flex-1 min-w-0">
        <span
          className={`text-[11px] truncate block ${
            isActive
              ? "text-[var(--accent)] font-medium"
              : "text-[var(--text-secondary)]"
          }`}
        >
          {session.title}
        </span>
        <span className="text-[9px] text-[var(--text-tertiary)]">
          {session.message_count} 条消息
        </span>
      </div>
      <button
        onClick={onDelete}
        className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-[var(--red-stock)]/10 
                   text-[var(--text-tertiary)] hover:text-[var(--red-stock)] transition-all"
        title="删除对话"
      >
        <Trash2 size={11} />
      </button>
    </div>
  );
}
