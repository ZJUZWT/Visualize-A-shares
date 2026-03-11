"use client";

/**
 * TerrainScene v2.0 — 3D 场景根组件
 *
 * v2.0 风格升级：
 * - 浅色渐变背景（清爽简约）
 * - 海面平面（z=0 半透明蓝色 + 波纹动画）
 * - 柔和光照（无硬阴影）
 * - 轻量后处理（移除暗角）
 */

import { Suspense, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Grid } from "@react-three/drei";
import {
  EffectComposer,
  Bloom,
} from "@react-three/postprocessing";
import * as THREE from "three";

import TerrainMesh from "./TerrainMesh";
import StockNodes from "./StockNodes";
import { useTerrainStore } from "@/stores/useTerrainStore";

/** 海面组件 — z=0 的半透明平面 + 微波纹 */
function SeaPlane({ bounds }: { bounds?: { xmin: number; xmax: number; ymin: number; ymax: number } }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);

  // 计算海面大小 — 要比地形范围大出一圈
  const width = bounds ? (bounds.xmax - bounds.xmin) * 1.6 : 60;
  const height = bounds ? (bounds.ymax - bounds.ymin) * 1.6 : 60;

  const seaVertexShader = /* glsl */ `
    uniform float uTime;
    varying vec2 vUv;
    varying vec3 vWorldPos;
    
    void main() {
      vUv = uv;
      vec3 pos = position;
      
      // 微波纹动画
      float wave = sin(pos.x * 2.0 + uTime * 0.6) * 0.03 +
                   cos(pos.y * 1.5 + uTime * 0.4) * 0.025 +
                   sin((pos.x + pos.y) * 1.0 + uTime * 0.3) * 0.015;
      pos.z += wave;
      
      vWorldPos = pos;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
    }
  `;

  const seaFragmentShader = /* glsl */ `
    uniform float uTime;
    varying vec2 vUv;
    varying vec3 vWorldPos;
    
    void main() {
      // 更鲜明的蓝色渐变
      vec3 shallowColor = vec3(0.60, 0.82, 0.95);  // 浅海蓝
      vec3 deepColor = vec3(0.40, 0.68, 0.90);      // 深海蓝
      vec3 foamColor = vec3(0.85, 0.92, 0.98);       // 浪花白
      
      // 波纹图案
      float pattern1 = sin(vUv.x * 30.0 + uTime * 0.5) * 0.5 + 0.5;
      float pattern2 = sin(vUv.y * 25.0 + uTime * 0.3) * 0.5 + 0.5;
      float pattern = pattern1 * pattern2;
      
      vec3 color = mix(shallowColor, deepColor, pattern * 0.3);
      
      // 加一些浪花高光
      float foam = sin(vUv.x * 40.0 + vUv.y * 35.0 + uTime * 0.8) * 0.5 + 0.5;
      foam = pow(foam, 4.0) * 0.15;
      color = mix(color, foamColor, foam);
      
      // 边缘淡出
      float edgeDist = min(min(vUv.x, 1.0 - vUv.x), min(vUv.y, 1.0 - vUv.y));
      float edgeFade = smoothstep(0.0, 0.12, edgeDist);
      
      // 更高的透明度让海面真正可见
      float alpha = 0.55 * edgeFade;
      
      gl_FragColor = vec4(color, alpha);
    }
  `;

  useFrame((_, delta) => {
    if (materialRef.current) {
      materialRef.current.uniforms.uTime.value += delta;
    }
  });

  return (
    <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, -1, 0]}>
      <planeGeometry args={[width, height, 80, 80]} />
      <shaderMaterial
        ref={materialRef}
        vertexShader={seaVertexShader}
        fragmentShader={seaFragmentShader}
        uniforms={{
          uTime: { value: 0 },
        }}
        transparent
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

export default function TerrainScene() {
  const { terrainData, showGrid, showContours, showLabels, heightScale } =
    useTerrainStore();

  return (
    <div className="canvas-container">
      <Canvas
        camera={{
          position: [0, 15, 18],
          fov: 55,
          near: 0.1,
          far: 200,
        }}
        gl={{
          antialias: true,
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.6,
        }}
        dpr={[1, 2]}
      >
        {/* v2.0: 浅色背景 */}
        <color attach="background" args={["#EEF2F7"]} />

        {/* v2.0: 柔和雾效 — 远处渐隐到浅灰 */}
        <fog attach="fog" args={["#EEF2F7", 30, 65]} />

        <Suspense fallback={null}>
          {/* ─── v2.0: 柔和光照 ──────────────── */}
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
          {/* 底部补光 */}
          <hemisphereLight
            args={["#E6F0FF", "#F0E6FF", 0.4]}
          />

          {/* ─── 海面平面 ──────────────────── */}
          <SeaPlane bounds={terrainData?.bounds} />

          {/* ─── 地形曲面 ──────────────────── */}
          {terrainData && terrainData.terrain_grid.length > 0 && (
            <TerrainMesh
              heightData={terrainData.terrain_grid}
              resolution={terrainData.terrain_resolution}
              bounds={terrainData.bounds}
              heightScale={heightScale}
              showContours={showContours}
            />
          )}

          {/* ─── 股票节点 ──────────────────── */}
          {terrainData && terrainData.stocks.length > 0 && (
            <StockNodes
              stocks={terrainData.stocks}
              heightScale={heightScale}
              showLabels={showLabels}
            />
          )}

          {/* ─── v2.0: 浅色网格 ────────────── */}
          {showGrid && (
            <Grid
              position={[0, -1.05, 0]}
              args={[40, 40]}
              cellSize={1}
              cellColor="#D8E0EC"
              sectionSize={5}
              sectionColor="#C0CCD8"
              fadeDistance={40}
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
            maxDistance={50}
            target={[0, 0, 0]}
          />
        </Suspense>

        {/* ─── v2.0: 轻量后处理 ───────────── */}
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
