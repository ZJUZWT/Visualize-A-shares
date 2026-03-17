"""
空间插值引擎 — 高斯核密度叠加 (KDE)

职责：
将离散的 (x, y, z) 股票点插值为 3D 地形高度网格

核心算法（KDE 叠加模式，非加权平均）：
    terrain[x][y] = Σ stock_i.z_value × G(distance, σ_i)
    
    G = 归一化高斯核：
        G(d, σ) = 1/(2πσ²) × exp(-d² / (2σ²))   当 d < 3σ
                = 0                                 当 d >= 3σ
    
    σ_i = radius_scale × dist_to_5th_neighbor(stock_i) / 3  自适应带宽

关键区别（vs 加权平均）：
    - 不做 /Σw 归一化 → 中心高、边缘指数衰减 → 自然形成山峰/山谷
    - 归一化高斯核（1/(2πσ²)前缀）→ 不同 σ 的核积分面积相同 → 公平叠加
    - σ/3 → 截断半径 = radius_scale × kth_dist，兼顾集中与平滑
"""

import numpy as np
from loguru import logger
from scipy.spatial import cKDTree

from config import settings


class InterpolationEngine:
    """高斯核密度叠加 (KDE) 地形引擎"""

    def __init__(self):
        self._grid = None
        self._bounds = None
        self._kdtree = None
        self._adaptive_radii = None

    @staticmethod
    def gaussian_kernel(d: np.ndarray, sigma: np.ndarray) -> np.ndarray:
        """
        归一化高斯核函数 (向量化，截断在 3σ)
        
        G(d, σ) = 1/(2πσ²) × exp(-d² / (2σ²))    当 d < 3σ
                = 0                                  当 d >= 3σ
        
        归一化保证：∫∫ G(d,σ) dA ≈ 1（2D 高斯核的积分面积为 1）
        这样不同 σ 大小的核，对地形的贡献是公平的。
        """
        cutoff = 3.0 * sigma
        mask = d < cutoff
        result = np.zeros_like(d)
        s = sigma[mask]
        norm = 1.0 / (2.0 * np.pi * s * s)
        result[mask] = norm * np.exp(-0.5 * (d[mask] / s) ** 2)
        return result

    def _compute_adaptive_radii(
        self,
        points: np.ndarray,
        k_neighbors: int = 5,
        radius_scale: float = 2.0,
        min_radius: float = 0.1,
        max_radius: float = 5.0,
    ) -> np.ndarray:
        """
        计算每个点的自适应高斯带宽 σ
        
        σ_i = radius_scale × dist_to_kth_neighbor(point_i) / 3
        
        除以 3 → 截断半径 3σ = radius_scale × kth_dist
        radius_scale 作为用户控制：
            - 小值(0.5): 窄核 → 山峰集中
            - 默认(2.0): 适度宽度 → 相邻点山峰自然融合
            - 大值(6.0): 宽核 → 平滑连续的山丘
        """
        n_points = len(points)
        k = min(k_neighbors + 1, n_points)
        
        self._kdtree = cKDTree(points)
        distances, _ = self._kdtree.query(points, k=k)
        
        kth_dist = distances[:, -1]
        
        # σ = radius_scale × kth_dist / 3
        # 截断半径 3σ = radius_scale × kth_dist
        sigmas = radius_scale * kth_dist / 3.0
        sigmas = np.clip(sigmas, min_radius, max_radius)
        
        logger.debug(
            f"自适应高斯带宽 σ: min={sigmas.min():.4f}, max={sigmas.max():.4f}, "
            f"mean={sigmas.mean():.4f}, median={np.median(sigmas):.4f} | "
            f"截断半径 3σ: [{3*sigmas.min():.4f}, {3*sigmas.max():.4f}]"
        )
        
        return sigmas

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
            f"高斯核密度地形开始: {len(x)} 个散布点 → "
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

        # ─── 自适应高斯带宽 ────────────────────
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
            f"高斯核密度地形完成: 网格 {grid.shape}, "
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

        # 自适应高斯带宽（所有指标共享同一空间布局）
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
        sigmas: np.ndarray,
        grid_points: np.ndarray,
    ) -> np.ndarray:
        """
        KDE 叠加模式：terrain[g] = Σ_i z_i × G(d(g, p_i), σ_i)
        
        不做归一化（不除以 Σw）！
        每个股票在其周围产生一个高斯形状的小山峰/山谷，
        多个股票的贡献直接叠加 → 自然形成平滑地形。
        
        归一化的高斯核保证每个点不管 σ 大小，积分面积都是 1，
        所以叠加是公平的。
        """
        n_grid = len(grid_points)
        grid_z = np.zeros(n_grid)
        
        grid_tree = cKDTree(grid_points)
        
        for i in range(len(points)):
            sigma_i = sigmas[i]
            cutoff = 3.0 * sigma_i
            
            nearby_indices = grid_tree.query_ball_point(points[i], r=cutoff)
            
            if len(nearby_indices) == 0:
                continue
            
            nearby_indices = np.array(nearby_indices)
            dists = np.sqrt(np.sum((grid_points[nearby_indices] - points[i]) ** 2, axis=1))
            
            sigma_arr = np.full_like(dists, sigma_i)
            weights = self.gaussian_kernel(dists, sigma_arr)
            
            # KDE 叠加：直接累加 z × G(d,σ)，不做归一化
            grid_z[nearby_indices] += z_values[i] * weights
        
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
