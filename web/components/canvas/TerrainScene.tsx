"use client";

/**
 * TerrainScene — 3D 场景根组件
 *
 * v5.0: 支持历史回放 — 切换帧数据
 * - 地形和股票统一使用 xyScale 放大
 * - 回放模式下使用 playback frame 数据
 */

import { Suspense, useMemo, useEffect, useRef } from "react";
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

/** 回放自动播放 timer */
function PlaybackTimer() {
  const { isPlaying, playbackSpeed, playbackFrames, playbackIndex, setPlaybackIndex } =
    useTerrainStore();
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isPlaying && playbackFrames && playbackFrames.length > 0) {
      timerRef.current = setInterval(() => {
        const { playbackIndex: idx, playbackFrames: frames } = useTerrainStore.getState();
        if (!frames) return;
        const next = idx + 1;
        if (next >= frames.length) {
          // 循环播放：回到第一帧
          setPlaybackIndex(0);
        } else {
          setPlaybackIndex(next);
        }
      }, playbackSpeed * 1000);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, playbackSpeed, playbackFrames]);

  return null;
}

export default function TerrainScene() {
  const { terrainData, showGrid, showContours, showLabels, heightScale, xyScale, xScaleRatio, yScaleRatio, playbackFrames, playbackIndex } =
    useTerrainStore();

  // 计算实际的 X/Y 缩放（整体缩放 × 各轴比例因子）
  const xScale = xyScale * xScaleRatio;
  const yScale = xyScale * yScaleRatio;

  // 回放模式下，使用帧数据覆盖 heightData 和 bounds
  const activeHeightData = useMemo(() => {
    if (playbackFrames && playbackFrames[playbackIndex]) {
      return playbackFrames[playbackIndex].terrain_grid;
    }
    return terrainData?.terrain_grid ?? [];
  }, [playbackFrames, playbackIndex, terrainData]);

  const activeBounds = useMemo(() => {
    if (playbackFrames && playbackFrames[playbackIndex]) {
      return playbackFrames[playbackIndex].bounds;
    }
    return terrainData?.bounds ?? { xmin: -10, xmax: 10, ymin: -10, ymax: 10, zmin: 0, zmax: 1 };
  }, [playbackFrames, playbackIndex, terrainData]);

  return (
    <div className="canvas-container">
      {/* 回放自动播放 timer（在 Canvas 外） */}
      <PlaybackTimer />
      
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
          {terrainData && activeHeightData.length > 0 && (
            <TerrainMesh
              heightData={activeHeightData}
              resolution={terrainData.terrain_resolution}
              bounds={activeBounds}
              heightScale={heightScale}
              xScale={xScale}
              yScale={yScale}
              showContours={showContours}
            />
          )}

          {/* ─── 股票节点 ──────────────────── */}
          {terrainData && terrainData.stocks.length > 0 && (
            <StockNodes
              stocks={terrainData.stocks}
              heightScale={heightScale}
              xScale={xScale}
              yScale={yScale}
              showLabels={showLabels}
              bounds={activeBounds}
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
