import { create } from "zustand";
import {
  type SectorBoardItem, type HeatmapCell, type RotationMatrixRow,
  type SectorHistoryItem, type SectorFundFlowItem, type ConstituentItem,
  type SectorPredictionItem,
  fetchSectorBoards, fetchSectorHeatmap, fetchSectorRotation,
  fetchSectorHistory, fetchSectorConstituents, triggerSectorFetch,
} from "@/lib/sector-api";

type SortField = "pct_chg" | "main_force_net_inflow" | "prediction_score";

interface SectorStore {
  boardType: "industry" | "concept";
  date: string;
  boards: SectorBoardItem[];
  heatmapCells: HeatmapCell[];
  rotationMatrix: RotationMatrixRow[];
  topBullish: SectorPredictionItem[];
  topBearish: SectorPredictionItem[];
  selectedBoard: SectorBoardItem | null;
  history: SectorHistoryItem[];
  fundFlowHistory: SectorFundFlowItem[];
  constituents: ConstituentItem[];
  sortField: SortField;
  sortDesc: boolean;
  loading: boolean;
  detailLoading: boolean;

  setBoardType: (type: "industry" | "concept") => void;
  setDate: (date: string) => void;
  setSortField: (field: SortField) => void;
  selectBoard: (board: SectorBoardItem | null) => void;
  loadBoards: () => Promise<void>;
  loadHeatmap: () => Promise<void>;
  loadRotation: (days?: number) => Promise<void>;
  loadDetail: (board: SectorBoardItem) => Promise<void>;
  fetchData: () => Promise<void>;
}

export const useSectorStore = create<SectorStore>((set, get) => ({
  boardType: "industry",
  date: "",
  boards: [],
  heatmapCells: [],
  rotationMatrix: [],
  topBullish: [],
  topBearish: [],
  selectedBoard: null,
  history: [],
  fundFlowHistory: [],
  constituents: [],
  sortField: "pct_chg",
  sortDesc: true,
  loading: false,
  detailLoading: false,

  setBoardType: (type) => {
    set({ boardType: type, selectedBoard: null, history: [], constituents: [] });
    get().loadBoards();
  },

  setDate: (date) => {
    set({ date });
    get().loadBoards();
  },

  setSortField: (field) => {
    const { sortField, sortDesc } = get();
    if (sortField === field) {
      set({ sortDesc: !sortDesc });
    } else {
      set({ sortField: field, sortDesc: true });
    }
  },

  selectBoard: (board) => {
    set({ selectedBoard: board });
    if (board) get().loadDetail(board);
  },

  loadBoards: async () => {
    const { boardType, date } = get();
    set({ loading: true });
    try {
      const data = await fetchSectorBoards(boardType, date);
      const boards = data.boards || [];
      // 直接从 boards 数据生成 heatmap cells，避免重复请求 AKShare
      const heatmapCells: HeatmapCell[] = boards.map((b) => ({
        board_code: b.board_code,
        board_name: b.board_name,
        pct_chg: b.pct_chg ?? 0,
        main_force_net_inflow: b.main_force_net_inflow ?? 0,
        main_force_net_ratio: b.main_force_net_ratio ?? 0,
      }));
      set({ boards, heatmapCells, loading: false });
    } catch (e) {
      console.error("加载板块列表失败", e);
      set({ loading: false });
    }
  },

  loadHeatmap: async () => {
    const { boardType, date } = get();
    try {
      const data = await fetchSectorHeatmap(boardType, date);
      set({ heatmapCells: data.cells || [] });
    } catch (e) {
      console.error("加载热力图失败", e);
    }
  },

  loadRotation: async (days = 10) => {
    const { boardType } = get();
    try {
      const data = await fetchSectorRotation(days, boardType);
      set({
        rotationMatrix: data.matrix || [],
        topBullish: data.top_bullish || [],
        topBearish: data.top_bearish || [],
      });
    } catch (e) {
      console.error("加载轮动预测失败", e);
    }
  },

  loadDetail: async (board) => {
    set({ detailLoading: true });
    try {
      const [histData, consData] = await Promise.all([
        fetchSectorHistory(board.board_code, board.board_name, board.board_type),
        fetchSectorConstituents(board.board_code, board.board_name),
      ]);
      set({
        history: histData.history || [],
        fundFlowHistory: histData.fund_flow_history || [],
        constituents: consData.constituents || [],
        detailLoading: false,
      });
    } catch (e) {
      console.error("加载板块详情失败", e);
      set({ detailLoading: false });
    }
  },

  fetchData: async () => {
    const { boardType } = get();
    set({ loading: true });
    try {
      await triggerSectorFetch(boardType);
      await get().loadBoards();
    } catch (e) {
      console.error("数据采集失败", e);
      set({ loading: false });
    }
  },
}));
