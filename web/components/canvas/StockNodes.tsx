"use client";

/**
 * StockNodes v3.0 — 股票节点批量渲染
 *
 * v3.0 更新：
 * - 球体拍平动画（flattenBalls 开关 + lerp 过渡）
 * - 历史回放帧间插值（playback frames）
 */

import { useRef, useMemo, useEffect, useCallback } from "react";
import { useFrame, ThreeEvent } from "@react-three/fiber";
import { Html, Billboard } from "@react-three/drei";
import * as THREE from "three";
import type { StockPoint } from "@/types/terrain";
import { useTerrainStore } from "@/stores/useTerrainStore";

interface StockNodesProps {
  stocks: StockPoint[];
  heightScale?: number;
  xScale?: number;
  yScale?: number;
  showLabels?: boolean;
  bounds?: {
    xmin: number; xmax: number;
    ymin: number; ymax: number;
    zmin: number; zmax: number;
  };
}

const tempMatrix = new THREE.Matrix4();
const tempColor = new THREE.Color();
const LERP_SPEED = 0.06;

export default function StockNodes({
  stocks,
  heightScale = 3.0,
  xScale = 1.5,
  yScale = 1.5,
  showLabels = true,
  bounds,
}: StockNodesProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const { selectedStock, hoveredStock, setSelectedStock, setHoveredStock, flattenBalls, playbackFrames, playbackIndex } =
    useTerrainStore();

  const count = stocks.length;

  // 从 bounds 获取 z 轴范围（用于与地形着色器一致的归一化）
  const zMin = bounds?.zmin ?? 0;
  const zMax = bounds?.zmax ?? 1;

  // 存储每个球体的当前动画 Y 值
  const animatedY = useRef<Float32Array>(new Float32Array(0));
  // 存储每个球体的目标 Y 值
  const targetY = useRef<Float32Array>(new Float32Array(0));

  // 计算目标 Y（考虑拍平和回放帧）
  const computeTargetY = useCallback(() => {
    if (count === 0) return;
    
    if (targetY.current.length !== count) {
      targetY.current = new Float32Array(count);
    }

    const zRange = zMax - zMin || 1;
    const zeroLevel = (0 - zMin) / zRange;

    // 回放模式：从回放帧获取 z 值
    const currentFrame = playbackFrames?.[playbackIndex];

    for (let i = 0; i < count; i++) {
      const stock = stocks[i];

      if (flattenBalls) {
        targetY.current[i] = 0.15;
      } else {
        let zVal = stock.z;
        // 回放模式下使用帧数据的 z 值
        if (currentFrame?.stock_z_values) {
          const frameZ = currentFrame.stock_z_values[stock.code];
          if (frameZ !== undefined) zVal = frameZ;
        }
        const normalized = (zVal - zMin) / zRange;
        targetY.current[i] = (normalized - zeroLevel) * heightScale + 0.15;
      }
    }
  }, [stocks, count, flattenBalls, zMin, zMax, heightScale, playbackFrames, playbackIndex]);

  // 初始化位置和颜色
  useEffect(() => {
    if (!meshRef.current || count === 0) return;

    const mesh = meshRef.current;
    const zRange = zMax - zMin || 1;
    const zeroLevel = (0 - zMin) / zRange;

    // 初始化动画 Y 数组
    if (animatedY.current.length !== count) {
      animatedY.current = new Float32Array(count);
    }
    if (targetY.current.length !== count) {
      targetY.current = new Float32Array(count);
    }

    for (let i = 0; i < count; i++) {
      const stock = stocks[i];

      const x = stock.x * xScale;
      const z_pos = stock.y * yScale;

      const normalized = (stock.z - zMin) / zRange;
      const y = flattenBalls ? 0.15 : (normalized - zeroLevel) * heightScale + 0.15;
      
      animatedY.current[i] = y;
      targetY.current[i] = y;

      const scale = 0.08;
      tempMatrix.makeScale(scale, scale, scale);
      tempMatrix.setPosition(x, y, z_pos);
      mesh.setMatrixAt(i, tempMatrix);

      // 模块C: 球体着色始终用涨跌幅 z_pct_chg
      const pctChg = (stock as any).z_pct_chg ?? stock.z;
      if (pctChg > 5) {
        tempColor.setRGB(0.85, 0.12, 0.12);
      } else if (pctChg > 0.3) {
        const t = Math.min(pctChg / 5, 1);
        tempColor.lerpColors(
          new THREE.Color(0.95, 0.55, 0.45),
          new THREE.Color(0.90, 0.20, 0.18),
          t
        );
      } else if (pctChg < -5) {
        tempColor.setRGB(0.05, 0.50, 0.28);
      } else if (pctChg < -0.3) {
        const t = Math.min(Math.abs(pctChg) / 5, 1);
        tempColor.lerpColors(
          new THREE.Color(0.50, 0.85, 0.55),
          new THREE.Color(0.10, 0.65, 0.38),
          t
        );
      } else {
        tempColor.setRGB(0.75, 0.78, 0.84);
      }

      mesh.setColorAt(i, tempColor);
    }

    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [stocks, count, heightScale, zMin, zMax]);

  // 每帧更新：拍平动画 + 回放插值
  useFrame(() => {
    if (!meshRef.current || count === 0) return;

    computeTargetY();

    const mesh = meshRef.current;
    let needsUpdate = false;
    const pos = new THREE.Vector3();
    const quat = new THREE.Quaternion();
    const scl = new THREE.Vector3();

    for (let i = 0; i < count; i++) {
      const target = targetY.current[i];
      const current = animatedY.current[i];
      const diff = Math.abs(target - current);

      if (diff > 0.001) {
        const newY = THREE.MathUtils.lerp(current, target, LERP_SPEED);
        animatedY.current[i] = newY;

        mesh.getMatrixAt(i, tempMatrix);
        tempMatrix.decompose(pos, quat, scl);
        pos.y = newY;
        tempMatrix.compose(pos, quat, scl);
        mesh.setMatrixAt(i, tempMatrix);
        needsUpdate = true;
      }
    }

    if (needsUpdate) {
      mesh.instanceMatrix.needsUpdate = true;
    }
  });

  const handleClick = useCallback(
    (e: ThreeEvent<MouseEvent>) => {
      e.stopPropagation();
      if (e.instanceId !== undefined && e.instanceId < count) {
        setSelectedStock(stocks[e.instanceId]);
      }
    },
    [stocks, count, setSelectedStock]
  );

  const handlePointerOver = useCallback(
    (e: ThreeEvent<PointerEvent>) => {
      e.stopPropagation();
      if (e.instanceId !== undefined && e.instanceId < count) {
        setHoveredStock(stocks[e.instanceId]);
        document.body.style.cursor = "pointer";
      }
    },
    [stocks, count, setHoveredStock]
  );

  const handlePointerOut = useCallback(() => {
    setHoveredStock(null);
    document.body.style.cursor = "default";
  }, [setHoveredStock]);

  if (count === 0) return null;

  return (
    <>
      <instancedMesh
        ref={meshRef}
        args={[undefined, undefined, count]}
        onClick={handleClick}
        onPointerOver={handlePointerOver}
        onPointerOut={handlePointerOut}
      >
        <sphereGeometry args={[1, 12, 12]} />
        <meshPhongMaterial
          shininess={30}
          specular={new THREE.Color(0.3, 0.3, 0.3)}
        />
      </instancedMesh>

      {/* Hover 标签 */}
      {hoveredStock && showLabels && (
        <HoverLabel stock={hoveredStock} heightScale={heightScale} xScale={xScale} yScale={yScale} bounds={bounds} flattenBalls={flattenBalls} />
      )}

      {/* 选中标签 */}
      {selectedStock && (
        <SelectedLabel stock={selectedStock} heightScale={heightScale} xScale={xScale} yScale={yScale} bounds={bounds} flattenBalls={flattenBalls} />
      )}
    </>
  );
}

// ─── v2.0 Hover 浮动标签 — 清爽白色卡片 ──────────────

function HoverLabel({
  stock,
  heightScale,
  xScale = 1.5,
  yScale = 1.5,
  bounds,
  flattenBalls = false,
}: {
  stock: StockPoint;
  heightScale: number;
  xScale?: number;
  yScale?: number;
  bounds?: { zmin: number; zmax: number };
  flattenBalls?: boolean;
}) {
  const zMin = bounds?.zmin ?? 0;
  const zMax = bounds?.zmax ?? 1;
  const zRange = zMax - zMin || 1;
  const zeroLevel = (0 - zMin) / zRange;
  const normalized = (stock.z - zMin) / zRange;
  const y = flattenBalls ? 0.5 : (normalized - zeroLevel) * heightScale + 0.5;

  return (
    <Billboard position={[stock.x * xScale, y, stock.y * yScale]} follow={true}>
      <Html center distanceFactor={15} style={{ pointerEvents: "none" }}>
        <div
          style={{
            background: "rgba(255, 255, 255, 0.95)",
            backdropFilter: "blur(12px)",
            border: "1px solid #E8ECF4",
            borderRadius: "10px",
            padding: "8px 12px",
            whiteSpace: "nowrap",
            boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            fontSize: "12px",
            fontFamily: "Inter, sans-serif",
          }}
        >
          <div style={{ fontWeight: 600, color: "#1A1D26" }}>
            {stock.name}
          </div>
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              color: "#9CA3AF",
              fontSize: "10px",
            }}
          >
            {stock.code}
            {stock.industry && (
              <span style={{ marginLeft: "4px", color: "#6B7BF7" }}>
                · {stock.industry}
              </span>
            )}
          </div>
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontWeight: 700,
              fontSize: "14px",
              marginTop: "2px",
              color: ((stock as any).z_pct_chg ?? stock.z) > 0 ? "#EF4444" : ((stock as any).z_pct_chg ?? stock.z) < 0 ? "#22C55E" : "#9CA3AF",
            }}
          >
            {((stock as any).z_pct_chg ?? stock.z) > 0 ? "+" : ""}
            {((stock as any).z_pct_chg ?? stock.z).toFixed(2)}%
          </div>
        </div>
      </Html>
    </Billboard>
  );
}

// ─── v2.0 选中详情卡片 — 清爽白色卡片 ────────────────

function SelectedLabel({
  stock,
  heightScale,
  xScale = 1.5,
  yScale = 1.5,
  bounds,
  flattenBalls = false,
}: {
  stock: StockPoint;
  heightScale: number;
  xScale?: number;
  yScale?: number;
  bounds?: { zmin: number; zmax: number };
  flattenBalls?: boolean;
}) {
  const zMin = bounds?.zmin ?? 0;
  const zMax = bounds?.zmax ?? 1;
  const zRange = zMax - zMin || 1;
  const zeroLevel = (0 - zMin) / zRange;
  const normalized = (stock.z - zMin) / zRange;
  const y = flattenBalls ? 0.8 : (normalized - zeroLevel) * heightScale + 0.8;

  return (
    <Billboard position={[stock.x * xScale, y, stock.y * yScale]} follow={true}>
      <Html center distanceFactor={12}>
        <div
          style={{
            background: "rgba(255, 255, 255, 0.97)",
            backdropFilter: "blur(16px)",
            border: "1px solid #D0D8E8",
            borderRadius: "12px",
            padding: "12px 16px",
            minWidth: "160px",
            boxShadow:
              "0 0 0 3px rgba(79, 142, 247, 0.15), 0 8px 24px rgba(0,0,0,0.1)",
            fontFamily: "Inter, sans-serif",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "4px",
            }}
          >
            <span style={{ fontWeight: 600, fontSize: "14px", color: "#1A1D26" }}>
              {stock.name}
            </span>
            <span
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: "10px",
                color: "#9CA3AF",
                marginLeft: "8px",
              }}
            >
              {stock.code}
            </span>
          </div>
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: "20px",
              fontWeight: 700,
              color: ((stock as any).z_pct_chg ?? stock.z) > 0 ? "#EF4444" : ((stock as any).z_pct_chg ?? stock.z) < 0 ? "#22C55E" : "#9CA3AF",
            }}
          >
            {((stock as any).z_pct_chg ?? stock.z) > 0 ? "+" : ""}
            {((stock as any).z_pct_chg ?? stock.z).toFixed(2)}%
          </div>
          <div
            style={{
              fontSize: "10px",
              color: "#9CA3AF",
              marginTop: "4px",
            }}
          >
            簇 #{stock.cluster_id === -1 ? "离群" : stock.cluster_id}
            {stock.industry && (
              <span style={{ marginLeft: "6px", color: "#6B7BF7" }}>
                {stock.industry}
              </span>
            )}
          </div>
        </div>
      </Html>
    </Billboard>
  );
}
