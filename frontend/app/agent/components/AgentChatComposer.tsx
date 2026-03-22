interface AgentChatComposerProps {
  value: string;
  disabled: boolean;
  isStreaming: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export default function AgentChatComposer({
  value,
  disabled,
  isStreaming,
  onChange,
  onSubmit,
}: AgentChatComposerProps) {
  const canSubmit = value.trim().length > 0 && !disabled && !isStreaming;

  return (
    <div className="border-t border-white/10 bg-[#0d0d14] p-4">
      <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3 shadow-[0_18px_50px_rgba(0,0,0,0.24)]">
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (canSubmit) {
                onSubmit();
              }
            }
          }}
          placeholder="问持仓、行情、下一步策略，或让 Agent 给出结构化交易计划。"
          disabled={disabled || isStreaming}
          rows={4}
          className="w-full resize-none bg-transparent text-sm leading-6 text-white outline-none placeholder:text-gray-500 disabled:cursor-not-allowed"
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="text-xs text-gray-500">
            `Enter` 发送，`Shift + Enter` 换行
          </p>
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit}
            className={`rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
              canSubmit
                ? "bg-white/10 text-white hover:bg-white/20"
                : "bg-white/5 text-gray-500 cursor-not-allowed"
            }`}
          >
            {isStreaming ? "生成中..." : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}
