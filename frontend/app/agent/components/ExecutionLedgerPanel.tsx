import { BrainRun } from "../types";

interface ExecutionLedgerPanelProps {
  run: BrainRun;
}

export default function ExecutionLedgerPanel({ run }: ExecutionLedgerPanelProps) {
  if (!run.plan_ids || run.plan_ids.length === 0) {
    return null;
  }

  return (
    <div className="text-sm text-gray-400">
      生成 {run.plan_ids.length} 个交易计划，
      执行 {run.trade_ids?.length || 0} 笔交易
    </div>
  );
}
