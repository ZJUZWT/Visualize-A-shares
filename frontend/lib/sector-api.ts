const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface SectorBoardItem {
  board_code: string;
  board_name: string;
  board_type: string;
  close: number;
  pct_chg: number;
  volume: number;
  amount: number;
  turnover_rate: number;
  total_mv: number;
  rise_count: number;
  fall_count: number;
  leading_stock: string;
  leading_pct_chg: number;
  main_force_net_inflow: number | null;
  main_force_net_ratio: number | null;
  prediction_score: number | null;
  prediction_signal: string | null;
}

export interface SectorHistoryItem {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  pct_chg: number;
  volume: number;
  amount: number;
  turnover_rate: number;
}

export interface SectorFundFlowItem {
  date: string;
  board_code: string;
  board_name: string;
  main_force_net_inflow: number;
  main_force_net_ratio: number;
  super_large_net_inflow: number;
  large_net_inflow: number;
  medium_net_inflow: number;
  small_net_inflow: number;
}

export interface ConstituentItem {
  code: string;
  name: string;
  price: number;
  pct_chg: number;
  volume: number;
  amount: number;
  turnover_rate: number;
  pe_ttm: number | null;
  pb: number | null;
}

export interface HeatmapCell {
  board_code: string;
  board_name: string;
  pct_chg: number;
  main_force_net_inflow: number;
  main_force_net_ratio: number;
}

export interface RotationMatrixRow {
  board_code: string;
  board_name: string;
  daily_flows: number[];
  daily_dates: string[];
  trend_signal: string;
}

export interface SectorPredictionItem {
  board_code: string;
  board_name: string;
  probability: number;
  signal: string;
}

export async function fetchSectorBoards(type: string, date = "") {
  const params = new URLSearchParams({ type });
  if (date) params.set("date", date);
  const res = await fetch(`${API_BASE}/api/v1/sector/boards?${params}`);
  return res.json();
}

export async function fetchSectorHistory(
  boardCode: string, boardName: string,
  boardType = "industry", start = "", end = ""
) {
  const params = new URLSearchParams({ board_name: boardName, board_type: boardType });
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const res = await fetch(`${API_BASE}/api/v1/sector/${boardCode}/history?${params}`);
  return res.json();
}

export async function fetchSectorConstituents(boardCode: string, boardName: string) {
  const params = new URLSearchParams({ board_name: boardName });
  const res = await fetch(`${API_BASE}/api/v1/sector/${boardCode}/constituents?${params}`);
  return res.json();
}

export async function fetchSectorHeatmap(type: string, date = "") {
  const params = new URLSearchParams({ type });
  if (date) params.set("date", date);
  const res = await fetch(`${API_BASE}/api/v1/sector/heatmap?${params}`);
  return res.json();
}

export async function fetchSectorRotation(days = 10, type = "industry") {
  const params = new URLSearchParams({ days: String(days), type });
  const res = await fetch(`${API_BASE}/api/v1/sector/rotation?${params}`);
  return res.json();
}

export async function triggerSectorFetch(type: string) {
  const res = await fetch(`${API_BASE}/api/v1/sector/fetch?type=${type}`, { method: "POST" });
  return res.json();
}
