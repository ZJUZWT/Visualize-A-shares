"use client";

/**
 * TerrainScene — 3D 场景根组件
 *
 * - 地形和股票统一使用 xyScale 放大
 * - 相机参数适配放大后的场景
 */

import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Grid } from "@react-three/drei";
import {
  EffectComposer,
  Bloom,
} from "@react-three/postprocessing";
import * as THREE from "three";

import TerrainMesh from "./TerrainMesh";
import StockNodes from "./StockNodes";
import { useTerrainStore } from "@/stores/useTerrainStore";

// 全局 XY 缩放因子
const XY_SCALE = 1.5;

export default function TerrainScene() {
  const { terrainData, showGrid, showContours, showLabels, heightScale } =
    useTerrainStore();

  return (
    <div className="canvas-container">
      <Canvas
        camera={{
          position: [0, 22, 28],
          fov: 55,
          near: 0.1,
          far: 300,
        }}
        gl={{
          antialias: true,
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.6,
        }}
        dpr={[1, 2]}
      >
        {/* 浅色背景 */}
        <color attach="background" args={["#EEF2F7"]} />

        {/* 柔和雾效 — 远处渐隐到浅灰 */}
        <fog attach="fog" args={["#EEF2F7", 45, 100]} />

        <Suspense fallback={null}>
          {/* ─── 柔和光照 ──────────────── */}
          <ambientLight intensity={0.7} color="#FFFFFF" />
          <directionalLight
            position={[10, 25, 10]}
            intensity={1.0}
            color="#FFF5E6"
          />
          <directionalLight
            position={[-8, 15, -8]}
            intensity={0.3}
            color="#E6F0FF"
          />
          <hemisphereLight
            args={["#E6F0FF", "#F0E6FF", 0.4]}
          />

          {/* ─── 地形曲面 ──────────────────── */}
          {terrainData && terrainData.terrain_grid.length > 0 && (
            <TerrainMesh
              heightData={terrainData.terrain_grid}
              resolution={terrainData.terrain_resolution}
              bounds={terrainData.bounds}
              heightScale={heightScale}
              xyScale={XY_SCALE}
              showContours={showContours}
            />
          )}

          {/* ─── 股票节点 ──────────────────── */}
          {terrainData && terrainData.stocks.length > 0 && (
            <StockNodes
              stocks={terrainData.stocks}
              heightScale={heightScale}
              xyScale={XY_SCALE}
              showLabels={showLabels}
              bounds={terrainData.bounds}
            />
          )}

          {/* ─── 浅色网格 ────────────── */}
          {showGrid && (
            <Grid
              position={[0, -0.05, 0]}
              args={[60, 60]}
              cellSize={2}
              cellColor="#D8E0EC"
              sectionSize={10}
              sectionColor="#C0CCD8"
              fadeDistance={60}
              fadeStrength={1.5}
              infiniteGrid
            />
          )}

          {/* ─── 相机控制 ──────────────────── */}
          <OrbitControls
            enableDamping
            dampingFactor={0.05}
            maxPolarAngle={Math.PI / 2.2}
            minDistance={5}
            maxDistance={80}
            target={[0, 0, 0]}
          />
        </Suspense>

        {/* ─── 轻量后处理 ───────────── */}
        <EffectComposer>
          <Bloom
            intensity={0.15}
            luminanceThreshold={0.8}
            luminanceSmoothing={0.9}
            mipmapBlur
          />
        </EffectComposer>
      </Canvas>
    </div>
  );
}
