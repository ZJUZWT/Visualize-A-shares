"""
空间插值引擎 — Wendland C2 核密度场

职责：
将离散的 (x, y, z) 股票点插值为 3D 地形高度网格

核心算法：
    terrain[x][y] = Σ stock_i.z_value × W(distance, r_i)
    
    W = Wendland C2 紧支撑核：
        W(d, r) = ((1 - d/r)^4) × (4d/r + 1)   当 d < r
                = 0                                当 d >= r
    
    r_i = k × dist_to_5th_neighbor(stock_i)  自适应影响半径

优势：
    - 紧支撑：超出影响半径贡献为 0，空白区域自然为海面
    - 自适应：密集区高分辨率，稀疏区影响范围自动扩大
    - 保留剧变：涨停/跌停股票在地形中保持尖峰/深谷
"""

import numpy as np
from loguru import logger
from scipy.spatial import cKDTree

from config import settings


class InterpolationEngine:
    """Wendland C2 核密度地形引擎"""

    def __init__(self):
        self._grid = None
        self._bounds = None
        self._kdtree = None
        self._adaptive_radii = None

    @staticmethod
    def wendland_c2(d: np.ndarray, r: np.ndarray) -> np.ndarray:
        """
        Wendland C2 紧支撑核函数 (向量化)
        
        W(d, r) = max(0, (1 - d/r))^4 × (4d/r + 1)
        
        - d: 距离数组
        - r: 影响半径数组
        - 超出半径贡献为 0
        """
        q = np.clip(d / r, 0, 1)
        # 超出半径的点贡献为 0
        mask = d < r
        result = np.zeros_like(d)
        result[mask] = ((1 - q[mask]) ** 4) * (4 * q[mask] + 1)
        return result

    def _compute_adaptive_radii(
        self,
        points: np.ndarray,
        k_neighbors: int = 5,
        radius_scale: float = 2.0,
        min_radius: float = 0.3,
        max_radius: float = 5.0,
    ) -> np.ndarray:
        """
        计算每个点的自适应影响半径
        
        r_i = radius_scale × dist_to_kth_neighbor(point_i)
        
        密集区 → 半径小 → 地形细节丰富
        稀疏区 → 半径大 → 单只股票也能撑起地形
        """
        n_points = len(points)
        k = min(k_neighbors + 1, n_points)  # +1 因为自身也在 KNN 结果中
        
        self._kdtree = cKDTree(points)
        distances, _ = self._kdtree.query(points, k=k)
        
        # 取第 k 近邻的距离（跳过自身，index 0）
        kth_dist = distances[:, -1]
        
        radii = radius_scale * kth_dist
        radii = np.clip(radii, min_radius, max_radius)
        
        logger.debug(
            f"自适应半径: min={radii.min():.3f}, max={radii.max():.3f}, "
            f"mean={radii.mean():.3f}, median={np.median(radii):.3f}"
        )
        
        return radii

    def compute_terrain(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        resolution: int | None = None,
        radius_scale: float = 2.0,
    ) -> dict:
        """
        从离散股票点生成 Wendland C2 核密度地形
        
        Args:
            x: (N,) UMAP X 坐标
            y: (N,) UMAP Y 坐标
            z: (N,) Z 轴值 (涨跌幅 / 成交量 / 其他指标)
            resolution: 网格分辨率
            radius_scale: 影响半径缩放因子（前端滑块控制）
            
        Returns:
            包含地形网格、坐标、边界等的字典
        """
        cfg = settings.interpolation
        if resolution is None:
            resolution = cfg.grid_resolution

        logger.info(
            f"Wendland C2 核密度地形开始: {len(x)} 个散布点 → "
            f"{resolution}×{resolution} 网格 | "
            f"radius_scale={radius_scale}"
        )

        # ─── 处理有效数据 ──────────────────────
        valid_mask = ~np.isnan(z) & ~np.isnan(x) & ~np.isnan(y)
        if valid_mask.sum() < 10:
            logger.warning("有效散布点不足 10 个，生成零平面")
            return self._zero_terrain(x, y, resolution)

        x_valid = x[valid_mask]
        y_valid = y[valid_mask]
        z_valid = z[valid_mask]
        points = np.column_stack([x_valid, y_valid])

        # ─── 计算边界 ──────────────────────────
        padding = cfg.bounds_padding
        x_range = x_valid.max() - x_valid.min()
        y_range = y_valid.max() - y_valid.min()

        xmin = x_valid.min() - x_range * padding
        xmax = x_valid.max() + x_range * padding
        ymin = y_valid.min() - y_range * padding
        ymax = y_valid.max() + y_range * padding

        # ─── 自适应影响半径 ────────────────────
        radii = self._compute_adaptive_radii(
            points,
            k_neighbors=5,
            radius_scale=radius_scale,
        )
        self._adaptive_radii = radii

        # ─── 构建规则网格 ─────────────────────
        grid_x = np.linspace(xmin, xmax, resolution)
        grid_y = np.linspace(ymin, ymax, resolution)
        mesh_x, mesh_y = np.meshgrid(grid_x, grid_y)
        grid_points = np.column_stack([mesh_x.ravel(), mesh_y.ravel()])

        # ─── 核密度场计算 ─────────────────────
        grid_z = self._compute_density_field(
            points, z_valid, radii, grid_points
        )
        grid = grid_z.reshape(resolution, resolution)

        # ─── 计算边界 ─────────────────────────
        self._bounds = {
            "xmin": float(xmin),
            "xmax": float(xmax),
            "ymin": float(ymin),
            "ymax": float(ymax),
            "zmin": float(np.nanmin(grid)) if np.any(grid != 0) else 0.0,
            "zmax": float(np.nanmax(grid)) if np.any(grid != 0) else 1.0,
        }

        logger.info(
            f"Wendland C2 核密度地形完成: 网格 {grid.shape}, "
            f"Z范围 [{self._bounds['zmin']:.2f}, {self._bounds['zmax']:.2f}]"
        )

        return self._pack_result(grid, grid_x, grid_y)

    def compute_terrain_multi(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z_dict: dict[str, np.ndarray],
        resolution: int | None = None,
        radius_scale: float = 2.0,
    ) -> dict:
        """
        一次性计算多个 Z 轴指标的地形网格
        
        Args:
            x: (N,) UMAP X 坐标
            y: (N,) UMAP Y 坐标  
            z_dict: {metric_name: z_values} 多个指标
            resolution: 网格分辨率
            radius_scale: 影响半径缩放因子
            
        Returns:
            {
                "grids": { metric_name: flat_grid_list },
                "bounds_per_metric": { metric_name: {zmin, zmax} },
                "grid_x": ...,
                "grid_y": ...,
                "bounds": { xmin, xmax, ymin, ymax },
                "resolution": int,
            }
        """
        cfg = settings.interpolation
        if resolution is None:
            resolution = cfg.grid_resolution

        # 用第一个指标的有效点来建立空间索引
        first_z = next(iter(z_dict.values()))
        valid_mask = ~np.isnan(first_z) & ~np.isnan(x) & ~np.isnan(y)
        
        if valid_mask.sum() < 10:
            logger.warning("有效散布点不足 10 个，生成零平面")
            empty_grids = {name: [0.0] * (resolution * resolution) for name in z_dict}
            return {
                "grids": empty_grids,
                "bounds_per_metric": {name: {"zmin": 0.0, "zmax": 1.0} for name in z_dict},
                "grid_x": np.linspace(-10, 10, resolution).tolist(),
                "grid_y": np.linspace(-10, 10, resolution).tolist(),
                "bounds": {"xmin": -10, "xmax": 10, "ymin": -10, "ymax": 10},
                "resolution": resolution,
            }

        x_valid = x[valid_mask]
        y_valid = y[valid_mask]
        points = np.column_stack([x_valid, y_valid])

        # 计算边界
        padding = cfg.bounds_padding
        x_range = x_valid.max() - x_valid.min()
        y_range = y_valid.max() - y_valid.min()
        xmin = x_valid.min() - x_range * padding
        xmax = x_valid.max() + x_range * padding
        ymin = y_valid.min() - y_range * padding
        ymax = y_valid.max() + y_range * padding

        # 自适应影响半径（所有指标共享同一空间布局）
        radii = self._compute_adaptive_radii(
            points, k_neighbors=5, radius_scale=radius_scale
        )

        # 构建网格
        grid_x = np.linspace(xmin, xmax, resolution)
        grid_y = np.linspace(ymin, ymax, resolution)
        mesh_x, mesh_y = np.meshgrid(grid_x, grid_y)
        grid_points = np.column_stack([mesh_x.ravel(), mesh_y.ravel()])

        # 为每个指标计算地形
        grids = {}
        bounds_per_metric = {}
        
        logger.info(f"批量计算 {len(z_dict)} 个指标的地形网格...")
        
        for metric_name, z_values in z_dict.items():
            z_valid = z_values[valid_mask]
            
            # 核密度场计算
            grid_z = self._compute_density_field(points, z_valid, radii, grid_points)
            grid = grid_z.reshape(resolution, resolution)
            
            grids[metric_name] = grid.ravel().tolist()
            bounds_per_metric[metric_name] = {
                "zmin": float(np.nanmin(grid)) if np.any(grid != 0) else 0.0,
                "zmax": float(np.nanmax(grid)) if np.any(grid != 0) else 1.0,
            }
            
            logger.debug(
                f"  {metric_name}: Z范围 "
                f"[{bounds_per_metric[metric_name]['zmin']:.2f}, "
                f"{bounds_per_metric[metric_name]['zmax']:.2f}]"
            )

        self._bounds = {
            "xmin": float(xmin), "xmax": float(xmax),
            "ymin": float(ymin), "ymax": float(ymax),
        }

        return {
            "grids": grids,
            "bounds_per_metric": bounds_per_metric,
            "grid_x": grid_x.tolist(),
            "grid_y": grid_y.tolist(),
            "bounds": self._bounds,
            "resolution": resolution,
        }

    def _compute_density_field(
        self,
        points: np.ndarray,
        z_values: np.ndarray,
        radii: np.ndarray,
        grid_points: np.ndarray,
    ) -> np.ndarray:
        """
        计算 Wendland C2 核密度场
        
        对每个网格点，累加所有在其影响范围内的股票的加权贡献
        使用 KDTree 加速近邻查询，避免 O(N×M) 暴力计算
        """
        n_grid = len(grid_points)
        grid_z = np.zeros(n_grid)
        weight_sum = np.zeros(n_grid)
        
        max_radius = float(radii.max())
        
        # 用 KDTree 查询每个网格点附近的股票
        grid_tree = cKDTree(grid_points)
        
        # 对每个股票点，找到其影响范围内的网格点
        for i in range(len(points)):
            r_i = radii[i]
            # 找到半径 r_i 内的所有网格点
            nearby_indices = grid_tree.query_ball_point(points[i], r=r_i)
            
            if len(nearby_indices) == 0:
                continue
            
            nearby_indices = np.array(nearby_indices)
            # 计算距离
            dists = np.sqrt(np.sum((grid_points[nearby_indices] - points[i]) ** 2, axis=1))
            
            # Wendland C2 权重
            r_arr = np.full_like(dists, r_i)
            weights = self.wendland_c2(dists, r_arr)
            
            # 累加加权 Z 值
            grid_z[nearby_indices] += z_values[i] * weights
            weight_sum[nearby_indices] += weights
        
        # 归一化：加权平均
        nonzero = weight_sum > 1e-10
        grid_z[nonzero] /= weight_sum[nonzero]
        
        return grid_z

    def _zero_terrain(self, x, y, resolution):
        """生成零平面"""
        xmin, xmax = float(np.nanmin(x)) - 1, float(np.nanmax(x)) + 1
        ymin, ymax = float(np.nanmin(y)) - 1, float(np.nanmax(y)) + 1
        grid = np.zeros((resolution, resolution))
        grid_x = np.linspace(xmin, xmax, resolution)
        grid_y = np.linspace(ymin, ymax, resolution)
        self._bounds = {
            "xmin": xmin, "xmax": xmax,
            "ymin": ymin, "ymax": ymax,
            "zmin": 0.0, "zmax": 1.0,
        }
        return self._pack_result(grid, grid_x, grid_y)

    def _pack_result(
        self,
        grid: np.ndarray,
        grid_x: np.ndarray,
        grid_y: np.ndarray,
    ) -> dict:
        """打包插值结果"""
        self._grid = grid
        return {
            "grid": grid,
            "grid_x": grid_x,
            "grid_y": grid_y,
            "bounds": self._bounds,
            "flat_grid": grid.ravel().tolist(),
            "resolution": grid.shape[0],
        }

    @property
    def grid(self) -> np.ndarray | None:
        return self._grid

    @property
    def bounds(self) -> dict | None:
        return self._bounds
