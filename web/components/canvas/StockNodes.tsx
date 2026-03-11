"use client";

/**
 * StockNodes v2.0 — 股票节点批量渲染
 *
 * v2.0 更新：
 * - 浅色主题适配
 * - 清爽标签卡片样式
 * - 柔和颜色编码
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
  showLabels?: boolean;
}

const tempMatrix = new THREE.Matrix4();
const tempColor = new THREE.Color();

export default function StockNodes({
  stocks,
  heightScale = 3.0,
  showLabels = true,
}: StockNodesProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const { selectedStock, hoveredStock, setSelectedStock, setHoveredStock } =
    useTerrainStore();

  const count = stocks.length;

  useEffect(() => {
    if (!meshRef.current || count === 0) return;

    const mesh = meshRef.current;

    for (let i = 0; i < count; i++) {
      const stock = stocks[i];

      const x = stock.x;
      const z_pos = stock.y;
      // 与 TerrainMesh shader 一致: signedHeight = (normalized - 0.5) * 2.0 * heightScale
      // 但节点直接用原始 z 值来定位（在海面 y=-1 的基础上偏移）
      const y = stock.z * (heightScale / 10) - 1 + 0.15;

      const scale = 0.08;
      tempMatrix.makeScale(scale, scale, scale);
      tempMatrix.setPosition(x, y, z_pos);
      mesh.setMatrixAt(i, tempMatrix);

      // v2.0: 清爽配色
      const pctChg = stock.z;
      if (pctChg > 5) {
        // 大涨：深红
        tempColor.setRGB(0.90, 0.28, 0.28);
      } else if (pctChg > 0.5) {
        // 小涨：暖珊瑚
        const t = Math.min(pctChg / 5, 1);
        tempColor.lerpColors(
          new THREE.Color(0.95, 0.65, 0.50),
          new THREE.Color(0.90, 0.35, 0.35),
          t
        );
      } else if (pctChg < -5) {
        // 大跌：深绿
        tempColor.setRGB(0.15, 0.60, 0.40);
      } else if (pctChg < -0.5) {
        // 小跌：薄荷绿
        const t = Math.min(Math.abs(pctChg) / 5, 1);
        tempColor.lerpColors(
          new THREE.Color(0.45, 0.82, 0.60),
          new THREE.Color(0.20, 0.65, 0.45),
          t
        );
      } else {
        // 平：浅灰蓝
        tempColor.setRGB(0.70, 0.75, 0.82);
      }

      mesh.setColorAt(i, tempColor);
    }

    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [stocks, count, heightScale]);

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
        <HoverLabel stock={hoveredStock} heightScale={heightScale} />
      )}

      {/* 选中标签 */}
      {selectedStock && (
        <SelectedLabel stock={selectedStock} heightScale={heightScale} />
      )}
    </>
  );
}

// ─── v2.0 Hover 浮动标签 — 清爽白色卡片 ──────────────

function HoverLabel({
  stock,
  heightScale,
}: {
  stock: StockPoint;
  heightScale: number;
}) {
  const y = stock.z * (heightScale / 10) - 1 + 0.5;

  return (
    <Billboard position={[stock.x, y, stock.y]} follow={true}>
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
              color: stock.z > 0 ? "#EF4444" : stock.z < 0 ? "#22C55E" : "#9CA3AF",
            }}
          >
            {stock.z > 0 ? "+" : ""}
            {stock.z.toFixed(2)}%
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
}: {
  stock: StockPoint;
  heightScale: number;
}) {
  const y = stock.z * (heightScale / 10) - 1 + 0.8;

  return (
    <Billboard position={[stock.x, y, stock.y]} follow={true}>
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
              color: stock.z > 0 ? "#EF4444" : stock.z < 0 ? "#22C55E" : "#9CA3AF",
            }}
          >
            {stock.z > 0 ? "+" : ""}
            {stock.z.toFixed(2)}%
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
