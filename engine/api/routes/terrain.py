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

from api.schemas import TerrainResponse, ComputeRequest, HealthResponse, HistoryRequest, HistoryResponse, HistoryFrame
from data.collector import DataCollector
from algorithm.pipeline import AlgorithmPipeline
from storage.duckdb_store import DuckDBStore

router = APIRouter(prefix="/api/v1", tags=["terrain"])

# ─── 全局单例 ────────────────────────────────────────
_collector: DataCollector | None = None
_pipeline: AlgorithmPipeline | None = None
_store: DuckDBStore | None = None

# ─── 防止 UMAP/Numba 并发崩溃的锁 ───────────────────
_compute_lock = asyncio.Lock()


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

    # 防止并发 UMAP 计算导致 Numba 崩溃
    if _compute_lock.locked():
        raise HTTPException(
            status_code=429,
            detail="计算正在进行中，请稍后重试"
        )

    async with _compute_lock:
        try:
            collector = get_collector()
            pipeline = get_pipeline()
            store = get_store()

            # 1. 拉取全市场实时行情
            snapshot = await asyncio.to_thread(collector.get_realtime_quotes)

            # 2. 保存快照到 DuckDB
            await asyncio.to_thread(store.save_snapshot, snapshot)

            # 3. 执行算法流水线 (v4.0: 多指标 + Wendland + 产业链拓扑权重)
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


@router.post("/terrain/history", response_model=HistoryResponse)
async def get_terrain_history(req: HistoryRequest = HistoryRequest()):
    """
    获取最近 N 个交易日的地形快照帧

    前提：必须先执行过 compute_terrain，有缓存的 UMAP 布局
    
    策略：
    1. 优先从 DuckDB 本地每日快照查询（毫秒级）
    2. 如果本地数据不足，则远程拉取（限制 500 只、45 秒超时）
    
    性能优化：
    - 批量构建所有帧的 z_dict 后一起传给插值引擎，共享空间索引
    - 远程拉取加超时保护，防止无限等待
    """
    pipeline = get_pipeline()
    if pipeline._last_embedding is None or pipeline._last_meta_df is None:
        raise HTTPException(
            status_code=400,
            detail="请先执行一次地形计算（点击「生成3D地形」按钮）"
        )

    logger.info(f"📅 收到历史回放请求: days={req.days}, z_metric={req.z_metric}")

    try:
        import numpy as np
        import time as _time
        store = get_store()
        collector = get_collector()

        stock_codes = pipeline._last_meta_df["code"].tolist()
        embedding = pipeline._last_embedding
        interpolation_eng = pipeline.interpolation_eng

        t0 = _time.time()

        # ─── 策略 1: 尝试从 DuckDB 读取本地每日快照 ─────
        local_snapshots = await asyncio.to_thread(store.get_snapshot_daily_range, req.days)
        logger.info(f"📅 本地快照: {len(local_snapshots)} 天")

        # ─── 策略 2: 本地数据不足，远程批量拉取（带超时保护）──
        if len(local_snapshots) < 2:
            logger.info("📅 本地历史快照不足 2 天，尝试远程拉取...")
            try:
                # 限制拉取股票数量为 500 只，避免超时
                limited_codes = stock_codes[:500]
                history_by_date = await asyncio.wait_for(
                    asyncio.to_thread(
                        collector.get_market_history,
                        limited_codes,
                        days=req.days,
                        z_metric=req.z_metric,
                    ),
                    timeout=45.0,  # 45 秒超时
                )
                if history_by_date:
                    local_snapshots = history_by_date
                    logger.info(f"📅 远程拉取成功: {len(history_by_date)} 天")
            except asyncio.TimeoutError:
                logger.warning("📅 远程拉取超时(45s)，使用已有本地数据")
                if not local_snapshots:
                    raise HTTPException(
                        status_code=503,
                        detail="历史数据不足且远程拉取超时。请先多次「生成3D地形」以积累本地数据（每天至少一次）。"
                    )
            except Exception as e:
                logger.warning(f"远程拉取失败: {e}")
                if not local_snapshots:
                    raise HTTPException(
                        status_code=503,
                        detail="历史数据不足且远程拉取失败。请先多次「生成3D地形」以积累本地数据（每天至少一次）。"
                    )

        if not local_snapshots:
            raise HTTPException(
                status_code=503,
                detail="无可用历史数据。请先「生成3D地形」几次（每天至少一次），本地会自动积累快照数据。"
            )

        # ─── 逐日生成地形帧 ──────────────────────────────
        # 先预处理所有天的 z_map，然后批量插值
        sorted_dates = sorted(local_snapshots.keys())
        date_z_maps: list[tuple[str, dict[str, float]]] = []

        for date_str in sorted_dates:
            day_df = local_snapshots[date_str]
            if day_df.empty:
                continue

            z_map: dict[str, float] = {}
            if req.z_metric in day_df.columns:
                for _, row in day_df.iterrows():
                    code = str(row.get("code", ""))
                    val = row.get(req.z_metric, 0.0)
                    try:
                        z_map[code] = float(val) if val == val else 0.0
                    except (TypeError, ValueError):
                        z_map[code] = 0.0

            if z_map:
                date_z_maps.append((date_str, z_map))

        if not date_z_maps:
            raise HTTPException(
                status_code=503,
                detail="无有效历史帧。请先多次「生成3D地形」以积累本地数据。"
            )

        # 批量构建所有帧的 z_dict（一次性传给插值引擎，共享空间索引和带宽计算）
        all_z_dict: dict[str, np.ndarray] = {}
        for date_str, z_map in date_z_maps:
            z_values = np.zeros(len(pipeline._last_meta_df))
            for i, code in enumerate(stock_codes):
                z_values[i] = z_map.get(code, 0.0)
            # 用日期作为 key 区分不同帧
            all_z_dict[date_str] = z_values

        # 一次性计算所有帧的地形（共享 KDTree + 自适应带宽）
        terrain_all = await asyncio.to_thread(
            interpolation_eng.compute_terrain_multi,
            embedding[:, 0],
            embedding[:, 1],
            all_z_dict,
        )

        frames = []
        for date_str, z_map in date_z_maps:
            grid = terrain_all["grids"].get(date_str, [])
            metric_bounds = terrain_all["bounds_per_metric"].get(
                date_str, {"zmin": 0, "zmax": 1}
            )
            frame_bounds = terrain_all["bounds"].copy()
            frame_bounds["zmin"] = metric_bounds["zmin"]
            frame_bounds["zmax"] = metric_bounds["zmax"]

            frames.append(HistoryFrame(
                date=date_str,
                terrain_grid=grid,
                bounds=frame_bounds,
                stock_z_values=z_map,
            ))

        elapsed = _time.time() - t0
        logger.info(f"📅 历史回放数据生成完成: {len(frames)} 帧, 耗时 {elapsed:.1f}s")

        return HistoryResponse(
            frames=frames,
            dates=[f.date for f in frames],
            total_stocks=len(stock_codes),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 历史回放失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="历史回放计算异常，请稍后重试。"
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
