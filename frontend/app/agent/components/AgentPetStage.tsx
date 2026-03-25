import type { BrainRun, PetConsoleViewModel } from "../types";

interface AgentPetStageProps {
  viewModel: PetConsoleViewModel;
  activeRun: BrainRun | null;
  suiteRunningMode: "default" | "smoke" | null;
}

const PIXEL_FRAMES: Record<string, string[]> = {
  idle: [
    "0001111000",
    "0012222100",
    "0121221210",
    "0122222210",
    "0123333210",
    "0012332100",
    "0001221000",
    "0010000100",
  ],
  thinking: [
    "0001111000",
    "0012222100",
    "0121221210",
    "0122442210",
    "0123333210",
    "0012332100",
    "0001221000",
    "0010001100",
  ],
  training: [
    "0001111000",
    "0012222100",
    "0121221210",
    "0122552210",
    "0123333210",
    "0012332100",
    "0001221000",
    "0011010100",
  ],
  battle: [
    "0001111000",
    "0012222100",
    "0121221210",
    "0122662210",
    "0123333210",
    "0012332100",
    "0001221000",
    "0011111100",
  ],
  drawdown: [
    "0001111000",
    "0012222100",
    "0121221210",
    "0122772210",
    "0123333210",
    "0012332100",
    "0001221000",
    "0010001000",
  ],
};

const PIXEL_COLORS: Record<string, string> = {
  "0": "transparent",
  "1": "#17151f",
  "2": "#f6bd60",
  "3": "#f28482",
  "4": "#8ecae6",
  "5": "#90be6d",
  "6": "#f94144",
  "7": "#577590",
};

function moodAccent(mood: PetConsoleViewModel["pet"]["mood"]) {
  switch (mood) {
    case "thinking":
      return "from-sky-500/30 via-cyan-400/10 to-transparent";
    case "training":
      return "from-amber-400/25 via-orange-400/10 to-transparent";
    case "battle":
      return "from-red-500/25 via-orange-400/10 to-transparent";
    case "drawdown":
      return "from-slate-400/25 via-blue-400/10 to-transparent";
    default:
      return "from-emerald-400/20 via-teal-400/10 to-transparent";
  }
}

function renderPixelSprite(mood: PetConsoleViewModel["pet"]["mood"]) {
  const frame = PIXEL_FRAMES[mood];
  return (
    <div
      className="grid gap-[3px] rounded-[28px] border border-black/10 bg-[#f6f1e8]/80 p-5 shadow-[0_20px_60px_rgba(0,0,0,0.16)]"
      style={{ gridTemplateColumns: `repeat(${frame[0].length}, minmax(0, 1fr))` }}
    >
      {frame.flatMap((row, rowIndex) =>
        row.split("").map((cell, cellIndex) => (
          <span
            key={`${rowIndex}-${cellIndex}`}
            className="h-4 w-4 rounded-[4px]"
            style={{ backgroundColor: PIXEL_COLORS[cell] }}
          />
        ))
      )}
    </div>
  );
}

export default function AgentPetStage({
  viewModel,
  activeRun,
  suiteRunningMode,
}: AgentPetStageProps) {
  const modeChip =
    suiteRunningMode === "smoke"
      ? "Smoke 训练中"
      : suiteRunningMode === "default"
        ? "训练中"
        : null;

  return (
    <section className="rounded-[28px] border border-black/10 bg-[linear-gradient(180deg,#f6ead6_0%,#f4f0e7_58%,#fffaf1_100%)] p-5 text-slate-900 shadow-[0_28px_90px_rgba(15,23,42,0.16)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Main Agent Pet</div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight">电子宠物主舞台</h2>
          <p className="mt-2 max-w-md text-sm leading-6 text-slate-600">
            在这里看见它的状态、最近动作和当前战斗姿态。
          </p>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <span className="rounded-full border border-black/10 bg-white/70 px-3 py-1 text-xs font-medium text-slate-700">
            {viewModel.pet.statusLabel}
          </span>
          {modeChip && (
            <span className="rounded-full border border-black/10 bg-[#fff3c4] px-3 py-1 text-xs font-medium text-amber-900">
              {modeChip}
            </span>
          )}
        </div>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[220px_minmax(0,1fr)]">
        <div className={`rounded-[30px] bg-gradient-to-br ${moodAccent(viewModel.pet.mood)} p-4`}>
          <div className="flex min-h-[240px] items-center justify-center rounded-[24px] border border-black/10 bg-white/45">
            {renderPixelSprite(viewModel.pet.mood)}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-black/10 bg-white/70 p-4">
            <div className="text-xs uppercase tracking-[0.2em] text-slate-500">状态描述</div>
            <div className="mt-2 text-lg font-semibold text-slate-900">{viewModel.pet.statusLabel}</div>
            <div className="mt-2 text-sm leading-6 text-slate-600">{viewModel.pet.statusMessage}</div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-black/10 bg-white/70 p-4">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">最近动作</div>
              <div className="mt-2 text-sm text-slate-900">
                {activeRun
                  ? `${activeRun.run_type} · ${activeRun.status} · ${activeRun.id.slice(0, 8)}`
                  : "最近还没有新的 brain run"}
              </div>
            </div>
            <div className="rounded-2xl border border-black/10 bg-white/70 p-4">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">出战状态</div>
              <div className="mt-2 text-sm text-slate-900">{viewModel.battle.readinessLabel}</div>
              <div className="mt-1 text-xs leading-5 text-slate-500">{viewModel.battle.statusMessage}</div>
            </div>
          </div>

          <div className="rounded-2xl border border-black/10 bg-[#1f2937] p-4 text-white">
            <div className="text-xs uppercase tracking-[0.2em] text-slate-400">训练快照</div>
            <div className="mt-2 flex items-center gap-3">
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs">{viewModel.training.modeLabel}</span>
              <span className="text-sm font-medium">{viewModel.training.statusTone.toUpperCase()}</span>
            </div>
            <div className="mt-2 text-sm leading-6 text-slate-200">{viewModel.training.summary}</div>
          </div>
        </div>
      </div>
    </section>
  );
}
