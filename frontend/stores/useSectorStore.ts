import { create } from "zustand";
import {
  type SectorBoardItem, type HeatmapCell, type RotationMatrixRow,
  type SectorHistoryItem, type SectorFundFlowItem, type ConstituentItem,
  type SectorPredictionItem, type StockSearchResult,
  fetchSectorBoards, fetchSectorHeatmap, fetchSectorRotation,
  fetchSectorHistory, fetchSectorConstituents, triggerSectorFetch,
  searchStockInBoards,
} from "@/lib/sector-api";

type SortField = "pct_chg" | "main_force_net_inflow" | "prediction_score";

/** 一个打开的详情面板的状态 */
interface DetailPanel {
  id: string;
  board: SectorBoardItem;
  history: SectorHistoryItem[];
  fundFlowHistory: SectorFundFlowItem[];
  constituents: ConstituentItem[];
  loading: boolean;
}

interface SectorStore {
  boardType: "industry" | "concept";
  date: string;
  boards: SectorBoardItem[];
  heatmapCells: HeatmapCell[];
  rotationMatrix: RotationMatrixRow[];
  topBullish: SectorPredictionItem[];
  topBearish: SectorPredictionItem[];
  /** 已废弃，保持兼容：单个选中面板 */
  selectedBoard: SectorBoardItem | null;
  /** 新：多个打开的详情面板 */
  openPanels: DetailPanel[];
  history: SectorHistoryItem[];
  fundFlowHistory: SectorFundFlowItem[];
  constituents: ConstituentItem[];
  sortField: SortField;
  sortDesc: boolean;
  loading: boolean;
  detailLoading: boolean;
  /** 股票搜索 */
  stockSearchQuery: string;
  stockSearchResults: StockSearchResult[];
  stockSearchLoading: boolean;

  setBoardType: (type: "industry" | "concept") => void;
  setDate: (date: string) => void;
  setSortField: (field: SortField) => void;
  selectBoard: (board: SectorBoardItem | null) => void;
  /** 打开一个新的详情面板（堆叠，不替换） */
  openPanel: (board: SectorBoardItem) => void;
  /** 关闭指定面板 */
  closePanel: (panelId: string) => void;
  loadBoards: () => Promise<void>;
  loadHeatmap: () => Promise<void>;
  loadRotation: (days?: number) => Promise<void>;
  loadDetail: (board: SectorBoardItem) => Promise<void>;
  fetchData: () => Promise<void>;
  /** 搜索股票 */
  searchStock: (query: string) => Promise<void>;
  clearStockSearch: () => void;
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
  openPanels: [],
  history: [],
  fundFlowHistory: [],
  constituents: [],
  sortField: "pct_chg",
  sortDesc: true,
  loading: false,
  detailLoading: false,
  stockSearchQuery: "",
  stockSearchResults: [],
  stockSearchLoading: false,

  setBoardType: (type) => {
    set({ boardType: type, selectedBoard: null, openPanels: [], history: [], constituents: [] });
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

  openPanel: (board) => {
    const panelId = `panel-${board.board_code}-${Date.now()}`;
    const panel: DetailPanel = {
      id: panelId,
      board,
      history: [],
      fundFlowHistory: [],
      constituents: [],
      loading: true,
    };
    set((s) => ({
      selectedBoard: board,
      openPanels: [...s.openPanels, panel],
    }));

    // 加载详情数据
    Promise.all([
      fetchSectorHistory(board.board_code, board.board_name, board.board_type),
      fetchSectorConstituents(board.board_code, board.board_name),
    ]).then(([histData, consData]) => {
      set((s) => ({
        openPanels: s.openPanels.map((p) =>
          p.id === panelId
            ? {
                ...p,
                history: histData.history || [],
                fundFlowHistory: histData.fund_flow_history || [],
                constituents: consData.constituents || [],
                loading: false,
              }
            : p
        ),
        // 同时更新旧的 constituents（兼容）
        constituents: consData.constituents || [],
        history: histData.history || [],
        fundFlowHistory: histData.fund_flow_history || [],
        detailLoading: false,
      }));
    }).catch((e) => {
      console.error("加载面板详情失败", e);
      set((s) => ({
        openPanels: s.openPanels.map((p) =>
          p.id === panelId ? { ...p, loading: false } : p
        ),
        detailLoading: false,
      }));
    });
  },

  closePanel: (panelId) => {
    set((s) => {
      const newPanels = s.openPanels.filter((p) => p.id !== panelId);
      return {
        openPanels: newPanels,
        selectedBoard: newPanels.length > 0 ? newPanels[newPanels.length - 1].board : null,
      };
    });
  },

  loadBoards: async () => {
    const { boardType, date } = get();
    set({ loading: true });
    try {
      const data = await fetchSectorBoards(boardType, date);
      const rawBoards = data.boards || [];
      // 前端去重（按基础名——去掉末尾罗马数字Ⅰ/Ⅱ/Ⅲ，保留第一个）
      const seenBase = new Set<string>();
      const boards = rawBoards.filter((b: SectorBoardItem) => {
        const base = b.board_name.replace(/[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+$/, "").trim();
        if (seenBase.has(base)) return false;
        seenBase.add(base);
        return true;
      });
      // 直接从 boards 数据生成 heatmap cells，避免重复请求 AKShare
      const heatmapCells: HeatmapCell[] = boards.map((b: SectorBoardItem) => ({
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

  searchStock: async (query: string) => {
    if (!query.trim()) {
      set({ stockSearchQuery: "", stockSearchResults: [], stockSearchLoading: false });
      return;
    }
    const { boardType } = get();
    set({ stockSearchQuery: query, stockSearchLoading: true });
    try {
      const data = await searchStockInBoards(query, boardType);
      set({ stockSearchResults: data.results || [], stockSearchLoading: false });
    } catch (e) {
      console.error("搜索股票失败", e);
      set({ stockSearchLoading: false });
    }
  },

  clearStockSearch: () => {
    set({ stockSearchQuery: "", stockSearchResults: [], stockSearchLoading: false });
  },
}));
