"""
地形数据 API — 核心接口

提供 3D 地形计算和实时更新的 REST + WebSocket 接口
"""

import asyncio
import json
from dataclasses import asdict

import pandas as pd
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
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


@router.post("/terrain/history")
async def get_terrain_history(req: HistoryRequest = HistoryRequest()):
    """
    获取最近 N 个交易日的地形快照帧 — SSE 流式推送

    前提：必须先执行过 compute_terrain，有缓存的 UMAP 布局

    SSE 事件类型：
    - progress: { phase, done, total, success, failed, elapsed, message }
    - complete: { frames, dates, total_stocks }
    - error: { message }
    """
    pipeline = get_pipeline()
    if pipeline._last_embedding is None or pipeline._last_meta_df is None:
        raise HTTPException(
            status_code=400,
            detail="请先执行一次地形计算（点击「生成3D地形」按钮）"
        )

    logger.info(f"📅 收到历史回放请求(SSE): days={req.days}, z_metric={req.z_metric}")

    async def event_stream():
        import numpy as np
        import time as _time

        def sse_event(event_type: str, data: dict) -> str:
            return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        try:
            store = get_store()
            collector = get_collector()

            stock_codes = pipeline._last_meta_df["code"].tolist()
            embedding = pipeline._last_embedding
            interpolation_eng = pipeline.interpolation_eng

            t0 = _time.time()

            # ─── Phase 1: 检查本地快照 ────────────────────
            yield sse_event("progress", {
                "phase": "checking",
                "message": "正在检查本地缓存...",
                "done": 0, "total": 0, "success": 0, "failed": 0, "elapsed": 0,
            })

            local_snapshots = store.get_snapshot_daily_range(req.days)
            logger.info(f"📅 本地快照: {len(local_snapshots)} 天 (需要 {req.days} 天)")

            # ─── Phase 2: 需要远程拉取 ───────────────────
            if len(local_snapshots) < req.days:
                needed = req.days - len(local_snapshots)
                total_stocks = len(stock_codes)
                yield sse_event("progress", {
                    "phase": "fetching",
                    "message": f"本地快照不足（{len(local_snapshots)}/{req.days}天），开始拉取 {total_stocks} 只股票...",
                    "done": 0, "total": total_stocks,
                    "success": 0, "failed": 0, "elapsed": 0,
                })

                # 进度回调 → SSE 推送（在线程中收集，主协程推送）
                progress_queue: asyncio.Queue = asyncio.Queue()

                def on_progress(done, total, success, failed, elapsed):
                    progress_queue.put_nowait({
                        "phase": "fetching",
                        "message": f"拉取中 {done}/{total}（成功 {success}，失败 {failed}）",
                        "done": done, "total": total,
                        "success": success, "failed": failed,
                        "elapsed": round(elapsed, 1),
                    })

                def on_batch_done(batch_records):
                    """每批完成立即写入 DuckDB"""
                    try:
                        batch_df = pd.DataFrame(batch_records)
                        if "date" in batch_df.columns:
                            batch_df["date"] = batch_df["date"].astype(str)
                            for d, grp in batch_df.groupby("date"):
                                store.save_history_as_snapshots({d: grp})
                    except Exception as e:
                        logger.warning(f"批次持久化失败(非致命): {e}")

                # 在后台线程中运行拉取
                fetch_task = asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: collector.get_market_history_streaming(
                        stock_codes,
                        days=req.days,
                        on_progress=on_progress,
                        on_batch_done=on_batch_done,
                    ),
                )

                # 异步消费进度队列，同时等待拉取完成
                history_by_date = None
                while True:
                    # 尝试获取进度事件
                    try:
                        progress = progress_queue.get_nowait()
                        yield sse_event("progress", progress)
                    except asyncio.QueueEmpty:
                        pass

                    # 检查拉取是否完成
                    if fetch_task.done():
                        # 排空队列
                        while not progress_queue.empty():
                            try:
                                progress = progress_queue.get_nowait()
                                yield sse_event("progress", progress)
                            except asyncio.QueueEmpty:
                                break
                        history_by_date = fetch_task.result()
                        break

                    await asyncio.sleep(0.3)

                if history_by_date:
                    # 合并远程数据
                    for date_str, day_df in history_by_date.items():
                        if date_str not in local_snapshots or local_snapshots[date_str].empty:
                            local_snapshots[date_str] = day_df
                    logger.info(f"📅 远程拉取完成并已持久化: {len(history_by_date)} 天")

            if not local_snapshots:
                yield sse_event("error", {"message": "无可用历史数据。请先「生成3D地形」以积累本地数据。"})
                return

            # ─── Phase 3: 计算地形帧 ─────────────────────
            yield sse_event("progress", {
                "phase": "computing",
                "message": f"正在计算 {len(local_snapshots)} 天的地形帧...",
                "done": 0, "total": len(local_snapshots),
                "success": 0, "failed": 0,
                "elapsed": round(_time.time() - t0, 1),
            })

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
                yield sse_event("error", {"message": "无有效历史帧。请先「生成3D地形」以积累本地数据。"})
                return

            all_z_dict: dict[str, np.ndarray] = {}
            for date_str, z_map in date_z_maps:
                z_values = np.zeros(len(pipeline._last_meta_df))
                for i, code in enumerate(stock_codes):
                    z_values[i] = z_map.get(code, 0.0)
                all_z_dict[date_str] = z_values

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

                frames.append({
                    "date": date_str,
                    "terrain_grid": grid,
                    "bounds": frame_bounds,
                    "stock_z_values": z_map,
                })

            elapsed = _time.time() - t0
            logger.info(f"📅 历史回放数据生成完成: {len(frames)} 帧, 耗时 {elapsed:.1f}s")

            # ─── Phase 4: 推送完整结果 ────────────────────
            yield sse_event("complete", {
                "frames": frames,
                "dates": [f["date"] for f in frames],
                "total_stocks": len(stock_codes),
            })

        except HTTPException as he:
            yield sse_event("error", {"message": he.detail})
        except Exception as e:
            logger.error(f"❌ 历史回放 SSE 失败: {e}", exc_info=True)
            yield sse_event("error", {"message": "历史回放计算异常，请稍后重试。"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
