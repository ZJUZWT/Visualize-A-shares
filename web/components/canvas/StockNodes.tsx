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

/**
 * 用股票自身的 z 值（涨跌幅等）计算球体 Y 高度
 * 找到所有 stocks 中 z 的 min/max 做归一化，以 0 为基准面
 */
function computeStockY(
  stockZ: number,
  stockZMin: number,
  stockZMax: number,
  heightScale: number,
): number {
  const range = stockZMax - stockZMin || 1;
  const zeroLevel = (0 - stockZMin) / range;
  const normalized = (stockZ - stockZMin) / range;
  return (normalized - zeroLevel) * heightScale + 0.15;
}

export default function StockNodes({
  stocks,
  heightScale = 3.0,
  xScale = 1.5,
  yScale = 1.5,
  showLabels = true,
  bounds,
}: StockNodesProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const { selectedStock, hoveredStock, setSelectedStock, setHoveredStock, flattenBalls, showDropLines, playbackFrames, playbackIndex } =
    useTerrainStore();

  const count = stocks.length;

  // 用股票自身 z 值的 min/max 做归一化（不是地形 bounds）
  const { stockZMin, stockZMax } = useMemo(() => {
    if (count === 0) return { stockZMin: 0, stockZMax: 1 };
    let mn = Infinity, mx = -Infinity;
    for (const s of stocks) {
      if (s.z < mn) mn = s.z;
      if (s.z > mx) mx = s.z;
    }
    return { stockZMin: mn, stockZMax: mx };
  }, [stocks, count]);

  // 存储每个球体的当前动画 Y 值
  const animatedY = useRef<Float32Array>(new Float32Array(0));
  // 存储每个球体的目标 Y 值
  const targetY = useRef<Float32Array>(new Float32Array(0));

  // 计算目标 Y — 直接用 stock.z
  const computeTargetY = useCallback(() => {
    if (count === 0) return;
    
    if (targetY.current.length !== count) {
      targetY.current = new Float32Array(count);
    }

    // 回放模式：可能覆盖 z 值
    const currentFrame = playbackFrames?.[playbackIndex];

    for (let i = 0; i < count; i++) {
      const stock = stocks[i];

      if (flattenBalls) {
        targetY.current[i] = 0.15;
      } else {
        let zVal = stock.z;
        if (currentFrame?.stock_z_values) {
          const frameZ = currentFrame.stock_z_values[stock.code];
          if (frameZ !== undefined) zVal = frameZ;
        }
        targetY.current[i] = computeStockY(zVal, stockZMin, stockZMax, heightScale);
      }
    }
  }, [stocks, count, flattenBalls, stockZMin, stockZMax, heightScale, playbackFrames, playbackIndex]);

  // 初始化位置和颜色
  useEffect(() => {
    if (!meshRef.current || count === 0) return;

    const mesh = meshRef.current;

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

      const y = flattenBalls ? 0.15 : computeStockY(stock.z, stockZMin, stockZMax, heightScale);
      
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
  }, [stocks, count, heightScale, stockZMin, stockZMax, flattenBalls]);

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

  // 垂线几何体 — 每个球体到 Y=0 的线段
  const dropLinesGeo = useMemo(() => {
    if (!showDropLines || count === 0) return null;
    const positions: number[] = [];
    const colors: number[] = [];
    const tmpClr = new THREE.Color();

    for (let i = 0; i < count; i++) {
      const stock = stocks[i];
      const x = stock.x * xScale;
      const z_pos = stock.y * yScale;
      const y = flattenBalls ? 0.15 : computeStockY(stock.z, stockZMin, stockZMax, heightScale);

      // 球体颜色（与球体着色逻辑一致）
      const pctChg = (stock as any).z_pct_chg ?? stock.z;
      if (pctChg > 5) {
        tmpClr.setRGB(0.85, 0.12, 0.12);
      } else if (pctChg > 0.3) {
        const t = Math.min(pctChg / 5, 1);
        tmpClr.lerpColors(new THREE.Color(0.95, 0.55, 0.45), new THREE.Color(0.90, 0.20, 0.18), t);
      } else if (pctChg < -5) {
        tmpClr.setRGB(0.05, 0.50, 0.28);
      } else if (pctChg < -0.3) {
        const t = Math.min(Math.abs(pctChg) / 5, 1);
        tmpClr.lerpColors(new THREE.Color(0.50, 0.85, 0.55), new THREE.Color(0.10, 0.65, 0.38), t);
      } else {
        tmpClr.setRGB(0.75, 0.78, 0.84);
      }

      // 线段：从球体位置到 Y=0
      positions.push(x, y, z_pos); // 球体位置
      positions.push(x, 0, z_pos); // Y=0 地面

      colors.push(tmpClr.r, tmpClr.g, tmpClr.b);
      colors.push(tmpClr.r, tmpClr.g, tmpClr.b);
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    return geo;
  }, [stocks, count, xScale, yScale, heightScale, stockZMin, stockZMax, flattenBalls, showDropLines]);

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

      {/* 垂线：球体到 Y=0 */}
      {showDropLines && dropLinesGeo && (
        <lineSegments geometry={dropLinesGeo}>
          <lineBasicMaterial vertexColors transparent opacity={0.5} />
        </lineSegments>
      )}

      {/* Hover 标签 */}
      {hoveredStock && showLabels && (
        <HoverLabel stock={hoveredStock} heightScale={heightScale} xScale={xScale} yScale={yScale} stocks={stocks} flattenBalls={flattenBalls} />
      )}

      {/* 选中标签 */}
      {selectedStock && (
        <SelectedLabel stock={selectedStock} heightScale={heightScale} xScale={xScale} yScale={yScale} stocks={stocks} flattenBalls={flattenBalls} />
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
  stocks,
  flattenBalls = false,
}: {
  stock: StockPoint;
  heightScale: number;
  xScale?: number;
  yScale?: number;
  stocks: StockPoint[];
  flattenBalls?: boolean;
}) {
  const { stockZMin, stockZMax } = useMemo(() => {
    let mn = Infinity, mx = -Infinity;
    for (const s of stocks) {
      if (s.z < mn) mn = s.z;
      if (s.z > mx) mx = s.z;
    }
    return { stockZMin: mn, stockZMax: mx };
  }, [stocks]);

  const y = flattenBalls ? 0.5 : computeStockY(stock.z, stockZMin, stockZMax, heightScale) + 0.35;

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
  stocks,
  flattenBalls = false,
}: {
  stock: StockPoint;
  heightScale: number;
  xScale?: number;
  yScale?: number;
  stocks: StockPoint[];
  flattenBalls?: boolean;
}) {
  const { stockZMin, stockZMax } = useMemo(() => {
    let mn = Infinity, mx = -Infinity;
    for (const s of stocks) {
      if (s.z < mn) mn = s.z;
      if (s.z > mx) mx = s.z;
    }
    return { stockZMin: mn, stockZMax: mx };
  }, [stocks]);

  const y = flattenBalls ? 0.8 : computeStockY(stock.z, stockZMin, stockZMax, heightScale) + 0.65;

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
