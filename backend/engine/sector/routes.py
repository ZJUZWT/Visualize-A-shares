"""板块研究仪表盘 API 路由"""
from __future__ import annotations

from fastapi import APIRouter, Query
from engine.sector.engine import SectorEngine
from engine.sector.schemas import (
    SectorBoardsResponse, SectorHistoryResponse,
    SectorHeatmapResponse, SectorRotationResponse,
    SectorConstituentsResponse, StockSectorsResponse,
)

router = APIRouter(prefix="/api/v1/sector", tags=["sector"])

_engine: SectorEngine | None = None


def _get_engine() -> SectorEngine:
    global _engine
    if _engine is None:
        _engine = SectorEngine()
    return _engine


@router.get("/boards", response_model=SectorBoardsResponse)
async def get_boards(
    type: str = Query("industry", description="板块类型: industry / concept"),
    date: str = Query("", description="日期 (YYYY-MM-DD)，默认今天"),
):
    """获取板块列表 + 涨跌 + 资金流 + 预测信号"""
    engine = _get_engine()
    return await engine.get_boards(board_type=type, date=date)


@router.get("/heatmap", response_model=SectorHeatmapResponse)
async def get_heatmap(
    type: str = Query("industry"),
    date: str = Query(""),
):
    """获取热力图数据"""
    engine = _get_engine()
    return await engine.get_heatmap(board_type=type, date=date)


@router.get("/rotation", response_model=SectorRotationResponse)
async def get_rotation(
    days: int = Query(10, description="回溯天数"),
    type: str = Query("industry"),
):
    """获取轮动预测"""
    engine = _get_engine()
    return await engine.get_rotation(days=days, board_type=type)


@router.get("/stock-sectors", response_model=StockSectorsResponse)
async def get_stock_sectors(
    code: str = Query("", description="股票代码"),
    name: str = Query("", description="股票名称"),
):
    """反查股票所属的所有板块（行业+概念）"""
    engine = _get_engine()
    return await engine.get_stock_sectors_fast(stock_code=code, stock_name=name)


@router.get("/search-stock")
async def search_stock_in_boards(
    q: str = Query("", description="搜索关键词（股票代码或名称）"),
    type: str = Query("industry"),
):
    """在已加载的板块成分股中搜索股票，返回匹配的板块"""
    engine = _get_engine()
    boards_resp = await engine.get_boards(board_type=type)
    results = []
    q_lower = q.lower().strip()
    if not q_lower:
        return {"results": []}

    for board in boards_resp.boards:
        try:
            cons_resp = await engine.get_constituents(
                board_name=board.board_name, board_code=board.board_code,
            )
            for c in cons_resp.constituents:
                if q_lower in c.code.lower() or q_lower in c.name.lower():
                    results.append({
                        "stock_code": c.code,
                        "stock_name": c.name,
                        "board_code": board.board_code,
                        "board_name": board.board_name,
                        "board_type": type,
                        "stock_pct_chg": c.pct_chg,
                        "board_pct_chg": board.pct_chg,
                    })
        except Exception:
            continue

    return {"results": results[:50]}  # 限制返回数量


@router.post("/fetch")
async def fetch_sector_data(
    type: str = Query("industry"),
):
    """触发板块数据采集"""
    engine = _get_engine()
    return await engine.fetch_and_save(board_type=type)


@router.get("/{board_code}/history", response_model=SectorHistoryResponse)
async def get_history(
    board_code: str,
    board_name: str = Query("", description="板块名称"),
    board_type: str = Query("industry"),
    start: str = Query("", description="开始日期"),
    end: str = Query("", description="结束日期"),
):
    """获取板块历史行情 + 资金流时序"""
    engine = _get_engine()
    return await engine.get_history(
        board_code=board_code, board_name=board_name,
        board_type=board_type,
        start_date=start, end_date=end,
    )


@router.get("/{board_code}/constituents", response_model=SectorConstituentsResponse)
async def get_constituents(
    board_code: str,
    board_name: str = Query("", description="板块名称"),
):
    """获取板块成分股"""
    engine = _get_engine()
    return await engine.get_constituents(
        board_name=board_name, board_code=board_code,
    )
