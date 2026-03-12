"""
地形数据 API — 核心接口

提供 3D 地形计算和实时更新的 REST + WebSocket 接口
"""

import asyncio
import json
from dataclasses import asdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger

from api.schemas import TerrainResponse, ComputeRequest, HealthResponse
from data.collector import DataCollector
from algorithm.pipeline import AlgorithmPipeline
from storage.duckdb_store import DuckDBStore

router = APIRouter(prefix="/api/v1", tags=["terrain"])

# ─── 全局单例 ────────────────────────────────────────
_collector: DataCollector | None = None
_pipeline: AlgorithmPipeline | None = None
_store: DuckDBStore | None = None


def get_collector() -> DataCollector:
    global _collector
    if _collector is None:
        _collector = DataCollector()
    return _collector


def get_pipeline() -> AlgorithmPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = AlgorithmPipeline()
    return _pipeline


def get_store() -> DuckDBStore:
    global _store
    if _store is None:
        _store = DuckDBStore()
    return _store


# ─── REST 接口 ────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """系统健康检查"""
    collector = get_collector()
    store = get_store()

    return HealthResponse(
        status="ok",
        data_sources={s: True for s in collector.available_sources},
        stock_count=store.get_stock_count(),
    )


@router.post("/terrain/compute", response_model=TerrainResponse)
async def compute_terrain(req: ComputeRequest = ComputeRequest()):
    """
    全量计算 3D 地形
    
    流程: 拉取行情 → 特征提取 → 聚类 → 降维 → 插值 → 返回地形数据
    """
    logger.info(f"🏔️  收到地形计算请求: z_metric={req.z_metric}, resolution={req.resolution}")

    try:
        collector = get_collector()
        pipeline = get_pipeline()
        store = get_store()

        # 1. 拉取全市场实时行情
        snapshot = await asyncio.to_thread(collector.get_realtime_quotes)

        # 2. 保存快照到 DuckDB
        await asyncio.to_thread(store.save_snapshot, snapshot)

        # 3. 执行算法流水线 (v3.0: 多指标 + Wendland + 动态权重)
        result = await asyncio.to_thread(
            pipeline.compute_full,
            snapshot,
            z_column=req.z_metric,
            feature_cols=req.features,
            grid_resolution=req.resolution,
            radius_scale=req.radius_scale,
            weight_embedding=req.weight_embedding,
            weight_industry=req.weight_industry,
            weight_numeric=req.weight_numeric,
            pca_target_dim=req.pca_target_dim,
            embedding_pca_dim=req.embedding_pca_dim,
        )

        # 4. 返回地形数据 (v2.0: 包含所有指标网格)
        return TerrainResponse(
            stocks=result.stocks,
            clusters=result.clusters,
            grids=result.grids,
            bounds_per_metric=result.bounds_per_metric,
            terrain_grid=result.terrain_grid,
            terrain_resolution=result.terrain_resolution,
            bounds=result.bounds,
            stock_count=result.stock_count,
            cluster_count=result.cluster_count,
            computation_time_ms=result.computation_time_ms,
            active_metric=result.active_metric,
        )
    except RuntimeError as e:
        logger.error(f"❌ 地形计算失败(数据源): {e}")
        raise HTTPException(
            status_code=503,
            detail=f"数据源暂时不可用: {str(e)}。请稍后重试。"
        )
    except Exception as e:
        logger.error(f"❌ 地形计算失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"地形计算异常: {str(e)}"
        )


@router.get("/terrain/refresh", response_model=TerrainResponse)
async def refresh_terrain(
    z_metric: str = Query("pct_chg", description="Z 轴指标"),
):
    """
    快速刷新 Z 轴（保持 XY 布局不变）
    用于实时行情更新
    """
    try:
        collector = get_collector()
        pipeline = get_pipeline()

        if pipeline.last_result is None:
            # 如果还没有初始计算，先执行全量计算
            return await compute_terrain(ComputeRequest(z_metric=z_metric))

        # 拉取最新行情
        snapshot = await asyncio.to_thread(collector.get_realtime_quotes)

        # 快速更新 Z 轴
        result = await asyncio.to_thread(
            pipeline.update_z_axis, snapshot, z_metric
        )

        if result is None:
            return await compute_terrain(ComputeRequest(z_metric=z_metric))

        return TerrainResponse(
            stocks=result.stocks,
            clusters=result.clusters,
            grids=result.grids,
            bounds_per_metric=result.bounds_per_metric,
            terrain_grid=result.terrain_grid,
            terrain_resolution=result.terrain_resolution,
            bounds=result.bounds,
            stock_count=result.stock_count,
            cluster_count=result.cluster_count,
            computation_time_ms=result.computation_time_ms,
            active_metric=result.active_metric,
        )
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error(f"❌ 刷新失败(数据源): {e}")
        raise HTTPException(
            status_code=503,
            detail=f"数据源暂时不可用: {str(e)}。请稍后重试。"
        )
    except Exception as e:
        logger.error(f"❌ 刷新失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"刷新异常: {str(e)}"
        )


@router.get("/stocks/search")
async def search_stocks(q: str = Query(..., min_length=1)):
    """搜索股票（代码/名称模糊匹配）"""
    pipeline = get_pipeline()
    results = []

    if pipeline.last_result and pipeline.last_result.stocks:
        q_lower = q.lower()
        for s in pipeline.last_result.stocks:
            if q_lower in s["code"].lower() or q_lower in s["name"].lower():
                results.append(s)
            if len(results) >= 20:
                break

    return {"results": results}


# ─── WebSocket 实时推送 ───────────────────────────────

_ws_clients: set[WebSocket] = set()


@router.websocket("/ws/terrain")
async def websocket_terrain(ws: WebSocket):
    """
    WebSocket 实时地形推送
    
    连接后自动推送最新地形数据
    客户端可发送 {"action": "refresh"} 触发更新
    """
    await ws.accept()
    _ws_clients.add(ws)
    logger.info(f"WebSocket 客户端连接: {ws.client}, 当前 {len(_ws_clients)} 个")

    try:
        # 立即推送最新数据
        pipeline = get_pipeline()
        if pipeline.last_result:
            await ws.send_json({
                "type": "terrain_full",
                "data": asdict(pipeline.last_result),
            })

        # 监听客户端消息
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "refresh":
                    z_metric = msg.get("z_metric", "pct_chg")
                    collector = get_collector()
                    snapshot = await asyncio.to_thread(
                        collector.get_realtime_quotes
                    )
                    result = await asyncio.to_thread(
                        pipeline.update_z_axis, snapshot, z_metric
                    )
                    if result:
                        await ws.send_json({
                            "type": "terrain_update",
                            "data": asdict(result),
                        })
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        _ws_clients.discard(ws)
        logger.info(f"WebSocket 客户端断开: {ws.client}")
    except Exception as e:
        _ws_clients.discard(ws)
        logger.error(f"WebSocket 异常: {e}")


async def broadcast_terrain_update(result):
    """广播地形更新给所有 WebSocket 客户端"""
    if not _ws_clients:
        return

    data = json.dumps({
        "type": "terrain_update",
        "data": asdict(result),
    })

    disconnected = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(data)
        except Exception:
            disconnected.add(ws)

    _ws_clients -= disconnected
