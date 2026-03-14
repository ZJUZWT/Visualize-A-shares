"""
导出地形数据快照 — 供 GitHub Pages 静态部署使用

运行方式:
    cd engine
    python -m preprocess.export_snapshot

输出:
    web/public/terrain_snapshot.json
"""

import json
import sys
import time
from pathlib import Path

# 确保 engine 目录在 sys.path 中
ENGINE_DIR = Path(__file__).resolve().parent.parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from data.collector import DataCollector
from algorithm.pipeline import AlgorithmPipeline


def export_snapshot():
    """生成地形计算快照并保存为 JSON"""
    print("=" * 60)
    print("StockTerrain — 导出静态快照")
    print("=" * 60)

    t0 = time.time()

    # 1. 拉取全市场实时行情
    print("\n📡 拉取全市场实时行情...")
    collector = DataCollector()
    snapshot = collector.get_realtime_quotes()
    print(f"   获取到 {len(snapshot)} 只股票行情")

    # 2. 执行算法流水线（使用默认参数）
    print("\n🧮 执行算法流水线...")
    pipeline = AlgorithmPipeline()
    result = pipeline.compute_full(
        snapshot,
        z_column="pct_chg",
        feature_cols=None,
        grid_resolution=128,
        radius_scale=2.0,
        weight_embedding=None,
        weight_industry=None,
        weight_numeric=None,
        pca_target_dim=None,
        embedding_pca_dim=None,
    )

    # 3. 组装输出数据
    output = {
        "stocks": result.stocks,
        "clusters": result.clusters,
        "grids": result.grids,
        "bounds_per_metric": result.bounds_per_metric,
        "terrain_grid": result.terrain_grid,
        "terrain_resolution": result.terrain_resolution,
        "bounds": {
            "xmin": result.bounds.xmin if hasattr(result.bounds, "xmin") else result.bounds["xmin"],
            "xmax": result.bounds.xmax if hasattr(result.bounds, "xmax") else result.bounds["xmax"],
            "ymin": result.bounds.ymin if hasattr(result.bounds, "ymin") else result.bounds["ymin"],
            "ymax": result.bounds.ymax if hasattr(result.bounds, "ymax") else result.bounds["ymax"],
            "zmin": result.bounds.zmin if hasattr(result.bounds, "zmin") else result.bounds["zmin"],
            "zmax": result.bounds.zmax if hasattr(result.bounds, "zmax") else result.bounds["zmax"],
        },
        "stock_count": result.stock_count,
        "cluster_count": result.cluster_count,
        "computation_time_ms": result.computation_time_ms,
        "active_metric": result.active_metric,
    }

    # 4. 保存到 web/public/
    output_dir = ENGINE_DIR.parent / "web" / "public"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "terrain_snapshot.json"

    print(f"\n💾 保存快照到 {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    file_size_mb = output_path.stat().st_size / 1024 / 1024
    elapsed = time.time() - t0

    print(f"\n✅ 导出完成!")
    print(f"   文件大小: {file_size_mb:.2f} MB")
    print(f"   股票数: {result.stock_count}")
    print(f"   聚类数: {result.cluster_count}")
    print(f"   总耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    export_snapshot()
