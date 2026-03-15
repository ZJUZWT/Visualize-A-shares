"""
聚类引擎 API — 核心接口

提供 3D 地形计算和实时更新的 REST + WebSocket 接口。
从 api/routes/terrain.py 迁移而来，使用 data_engine / cluster_engine 门面。
"""

import asyncio
import json
from dataclasses import asdict

import pandas as pd
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from data_engine import get_data_engine
from cluster_engine import get_cluster_engine
from cluster_engine.schemas import TerrainResponse, ComputeRequest, HealthResponse, HistoryRequest, HistoryResponse, HistoryFrame
from quant_engine.factor_backtest import run_ic_backtest_from_store

router = APIRouter(prefix="/api/v1", tags=["terrain"])

# ─── 防止 UMAP/Numba 并发崩溃的锁 ───────────────────
_compute_lock = asyncio.Lock()

# ─── WebSocket 客户端集合 ─────────────────────────────
_ws_clients: set[WebSocket] = set()


# ─── REST 接口 ────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """系统健康检查"""
    de = get_data_engine()

    return HealthResponse(
        status="ok",
        data_sources={s: True for s in de.available_sources},
        stock_count=de.get_stock_count(),
    )


@router.post("/terrain/compute")
async def compute_terrain(req: ComputeRequest = ComputeRequest()):
    """
    全量计算 3D 地形 — SSE 流式进度推送

    流程: 拉取行情 -> 保存快照 -> 特征提取 -> 聚类 -> 降维 -> 插值 -> 返回地形数据

    SSE 事件类型：
    - progress: { step, totalSteps, stepName, message, elapsed }
    - complete: TerrainResponse JSON
    - error: { message }
    """
    logger.info(f"🏔️  收到地形计算请求(SSE): z_metric={req.z_metric}, resolution={req.resolution}")

    # 防止并发 UMAP 计算导致 Numba 崩溃
    if _compute_lock.locked():
        raise HTTPException(
            status_code=429,
            detail="计算正在进行中，请稍后重试"
        )

    async def compute_event_stream():
        import time as _time

        def sse_event(event_type: str, data: dict) -> str:
            return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        async with _compute_lock:
            t0 = _time.time()
            progress_queue: asyncio.Queue = asyncio.Queue()

            try:
                de = get_data_engine()
                ce = get_cluster_engine()
                pipeline = ce.pipeline

                # ─── Step 1: 拉取全市场实时行情 ────────
                yield sse_event("progress", {
                    "step": 1, "totalSteps": 6,
                    "stepName": "拉取行情",
                    "message": "正在拉取全市场实时行情...",
                    "elapsed": 0,
                })

                snapshot = await asyncio.to_thread(de.get_realtime_quotes)
                elapsed = round(_time.time() - t0, 1)

                yield sse_event("progress", {
                    "step": 1, "totalSteps": 6,
                    "stepName": "拉取行情",
                    "message": f"行情拉取完成：{len(snapshot)} 只股票",
                    "elapsed": elapsed,
                })

                # ─── Step 2: 保存快照到 DuckDB ────────
                yield sse_event("progress", {
                    "step": 2, "totalSteps": 6,
                    "stepName": "保存快照",
                    "message": "正在保存数据快照...",
                    "elapsed": elapsed,
                })

                await asyncio.to_thread(de.save_snapshot, snapshot)
                elapsed = round(_time.time() - t0, 1)

                # ─── Step 2.5: 批量获取日线历史（用于技术指标）────
                yield sse_event("progress", {
                    "step": 2, "totalSteps": 6,
                    "stepName": "获取日线历史",
                    "message": "正在从本地获取日线历史数据（计算技术指标）...",
                    "elapsed": elapsed,
                })

                daily_df_map = await asyncio.to_thread(
                    de.get_daily_history_batch, snapshot
                )

                # ─── Step 3-6: 算法流水线（带进度回调）────
                def on_pipeline_progress(step, total, step_name):
                    """算法流水线进度回调"""
                    progress_queue.put_nowait({
                        "step": step + 2,  # 偏移2（前面有拉取行情+保存快照）
                        "totalSteps": total + 2,
                        "stepName": step_name,
                        "message": f"正在{step_name}...",
                        "elapsed": round(_time.time() - t0, 1),
                    })

                # 在后台线程中运行算法流水线
                compute_task = asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: pipeline.compute_full(
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
                        on_progress=on_pipeline_progress,
                        daily_df_map=daily_df_map,
                    ),
                )

                # 异步消费进度队列，同时等待计算完成
                while True:
                    try:
                        progress = progress_queue.get_nowait()
                        yield sse_event("progress", progress)
                    except asyncio.QueueEmpty:
                        pass

                    if compute_task.done():
                        # 排空队列
                        while not progress_queue.empty():
                            try:
                                progress = progress_queue.get_nowait()
                                yield sse_event("progress", progress)
                            except asyncio.QueueEmpty:
                                break
                        break

                    await asyncio.sleep(0.3)

                result = compute_task.result()
                elapsed = round(_time.time() - t0, 1)

                # ─── 推送完整结果 ──────────────────────
                response_data = TerrainResponse(
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

                # v3.0: 追加聚类质量评分
                resp_dict = response_data.model_dump()
                resp_dict["cluster_quality"] = result.cluster_quality

                yield sse_event("complete", resp_dict)

            except HTTPException as he:
                yield sse_event("error", {"message": he.detail})
            except RuntimeError as e:
                logger.error(f"❌ 地形计算失败(数据源): {e}")
                yield sse_event("error", {"message": f"数据源暂时不可用: {str(e)}。请稍后重试。"})
            except Exception as e:
                logger.error(f"❌ 地形计算失败: {e}", exc_info=True)
                yield sse_event("error", {"message": "地形计算异常，请稍后重试。"})

    return StreamingResponse(
        compute_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
        de = get_data_engine()
        ce = get_cluster_engine()
        pipeline = ce.pipeline

        if pipeline.last_result is None:
            # 如果还没有初始计算，先执行全量计算
            return await compute_terrain(ComputeRequest(z_metric=z_metric))

        # 拉取最新行情
        snapshot = await asyncio.to_thread(de.get_realtime_quotes)

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
    ce = get_cluster_engine()
    pipeline = ce.pipeline
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
            de = get_data_engine()

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

            local_snapshots = de.get_snapshot_daily_range(req.days)
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

                # 进度回调 -> SSE 推送（在线程中收集，主协程推送）
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
                                de.save_history_as_snapshots({d: grp})
                    except Exception as e:
                        logger.warning(f"批次持久化失败(非致命): {e}")

                # 在后台线程中运行拉取
                fetch_task = asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: de.get_market_history_streaming(
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
    ce = get_cluster_engine()
    pipeline = ce.pipeline
    results = []

    if pipeline.last_result and pipeline.last_result.stocks:
        q_lower = q.lower()
        for s in pipeline.last_result.stocks:
            if q_lower in s["code"].lower() or q_lower in s["name"].lower():
                results.append(s)
            if len(results) >= 20:
                break

    return {"results": results}


@router.get("/stocks/all")
async def get_all_stocks():
    """返回全量股票（含 cluster_id），来自最近一次地形计算的内存结果"""
    ce = get_cluster_engine()
    pipeline = ce.pipeline
    if pipeline.last_result and pipeline.last_result.stocks:
        return {"results": pipeline.last_result.stocks, "total": len(pipeline.last_result.stocks)}
    return {"results": [], "total": 0}


@router.post("/factor/backtest")
async def run_factor_backtest(
    rolling_window: int = Query(20, description="ICIR 滚动窗口天数"),
    auto_inject: bool = Query(True, description="是否自动注入权重到预测器"),
):
    """
    执行因子 IC 回测 + 自适应权重计算

    从 DuckDB 中读取历史快照数据，计算每个因子的 RankIC 时序，
    再用滚动 ICIR 作为自适应权重注入预测器。

    需要先积累 >=3 天的快照数据（每次「生成3D地形」会自动保存一天）。
    """
    try:
        de = get_data_engine()
        ce = get_cluster_engine()
        pipeline = ce.pipeline

        result = await asyncio.to_thread(
            run_ic_backtest_from_store, de.store, rolling_window
        )

        # 自动注入权重到 v2 预测器
        if auto_inject and result.icir_weights:
            pipeline.predictor_v2.set_icir_weights(result.icir_weights)
            logger.info("✅ ICIR 权重已自动注入到预测器 v2")

        # 构建响应
        factor_list = []
        for name, report in result.factor_reports.items():
            factor_list.append({
                "name": name,
                "ic_mean": report.ic_mean,
                "ic_std": report.ic_std,
                "icir": report.icir,
                "ic_positive_rate": report.ic_positive_rate,
                "t_stat": report.t_stat,
                "p_value": report.p_value,
                "ic_series": report.ic_series[-20:],  # 只返回最近 20 天
                "ic_dates": report.ic_dates[-20:],
            })

        return {
            "status": "ok",
            "backtest_days": result.backtest_days,
            "total_stocks_avg": result.total_stocks_avg,
            "computation_time_ms": round(result.computation_time_ms, 0),
            "data_source": result.data_source,
            "factors": factor_list,
            "icir_weights": result.icir_weights,
            "weights_injected": auto_inject and bool(result.icir_weights),
        }

    except Exception as e:
        logger.error(f"❌ 因子回测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"因子回测失败: {str(e)}")


@router.get("/factor/weights")
async def get_factor_weights():
    """查看当前预测器使用的因子权重"""
    ce = get_cluster_engine()
    pipeline = ce.pipeline
    predictor = pipeline.predictor_v2

    weights = predictor._get_weights()
    source = predictor._weight_source

    from quant_engine.predictor import FACTOR_DEFS
    factor_info = []
    for fdef in FACTOR_DEFS:
        factor_info.append({
            "name": fdef.name,
            "source_col": fdef.source_col,
            "direction": fdef.direction,
            "group": fdef.group,
            "weight": weights.get(fdef.name, 0.0),
            "default_weight": fdef.default_weight,
            "desc": fdef.desc,
        })

    return {
        "weight_source": source,
        "factors": factor_info,
    }


# ─── WebSocket 实时推送 ───────────────────────────────


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
        ce = get_cluster_engine()
        pipeline = ce.pipeline
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
                    de = get_data_engine()
                    snapshot = await asyncio.to_thread(
                        de.get_realtime_quotes
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
