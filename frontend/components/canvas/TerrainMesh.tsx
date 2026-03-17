"use client";

/**
 * TerrainMesh v3.0 — 3D 地形曲面渲染组件
 *
 * v3.0 修复：
 * - 使用自建 BufferGeometry 替代 planeGeometry + rotation
 *   直接在 XZ 平面上构建网格，Y 轴为高度
 *   避免旋转导致的坐标翻转问题
 * - 高度零点 = 数据中 0 值对应的归一化位置
 *   海面始终在 Y=0
 * - 红涨绿跌颜色渐变 + 中间透明
 * - XY 使用 xyScale 放大
 */

import { useRef, useMemo, useEffect } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

interface TerrainMeshProps {
  heightData: number[];
  resolution: number;
  bounds: {
    xmin: number; xmax: number;
    ymin: number; ymax: number;
    zmin: number; zmax: number;
  };
  heightScale?: number;
  xScale?: number;
  yScale?: number;
  showContours?: boolean;
}

export default function TerrainMesh({
  heightData,
  resolution,
  bounds,
  heightScale = 3.0,
  xScale = 1.5,
  yScale = 1.5,
  showContours = true,
}: TerrainMeshProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const animProgress = useRef(0);

  const zMin = bounds.zmin;
  const zMax = bounds.zmax;
  const zRange = zMax - zMin || 1;
  // 数据中 0 值在 [0,1] 归一化空间的位置 → 这就是海面零线
  const zeroLevel = (0 - zMin) / zRange;

  // ─── 自建 XZ 平面 BufferGeometry，Y 轴为高度 ────────
  const geometry = useMemo(() => {
    if (!heightData || heightData.length === 0) return null;

    const res = resolution;
    const xExtent = (bounds.xmax - bounds.xmin || 20) * xScale;
    const zExtent = (bounds.ymax - bounds.ymin || 20) * yScale;
    const xCenter = (bounds.xmin + bounds.xmax) / 2;
    const zCenter = (bounds.ymin + bounds.ymax) / 2;

    const vertCount = res * res;
    const positions = new Float32Array(vertCount * 3);
    const uvs = new Float32Array(vertCount * 2);
    const normals = new Float32Array(vertCount * 3);
    // 存归一化高度到自定义属性
    const heightAttr = new Float32Array(vertCount);

    for (let iy = 0; iy < res; iy++) {
      for (let ix = 0; ix < res; ix++) {
        const idx = iy * res + ix;
        const u = ix / (res - 1);
        const v = iy / (res - 1);

        // XZ 对齐后端 UMAP 坐标空间 × xScale/yScale
        const worldX = (bounds.xmin + u * (bounds.xmax - bounds.xmin)) * xScale;
        const worldZ = (bounds.ymin + v * (bounds.ymax - bounds.ymin)) * yScale;

        // 归一化高度 [0,1]
        const rawZ = heightData[idx] ?? 0;
        const h = Math.max(0, Math.min(1, (rawZ - zMin) / zRange));
        heightAttr[idx] = h;

        // Y = 0 代表海面 → (h - zeroLevel) * heightScale
        // 动画在 shader 中做
        positions[idx * 3] = worldX;
        positions[idx * 3 + 1] = 0; // shader 会覆盖
        positions[idx * 3 + 2] = worldZ;

        uvs[idx * 2] = u;
        uvs[idx * 2 + 1] = v;

        normals[idx * 3] = 0;
        normals[idx * 3 + 1] = 1;
        normals[idx * 3 + 2] = 0;
      }
    }

    // 构建索引 (CCW 缠绕 — Three.js 默认正面)
    const indices: number[] = [];
    for (let iy = 0; iy < res - 1; iy++) {
      for (let ix = 0; ix < res - 1; ix++) {
        const a = iy * res + ix;
        const b = a + 1;
        const c = a + res;
        const d = c + 1;
        // CCW: 从上方(+Y)看为逆时针
        indices.push(a, b, c);
        indices.push(b, d, c);
      }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
    geo.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
    geo.setAttribute("aHeight", new THREE.BufferAttribute(heightAttr, 1));
    geo.setIndex(indices);

    return geo;
  }, [heightData, resolution, bounds, xScale, yScale, zMin, zRange, zeroLevel]);

  // ─── 顶点着色器 ─────────────────────────────────────
  const vertexShader = useMemo(() => /* glsl */ `
    attribute float aHeight;
    uniform float uHeightScale;
    uniform float uAnimProgress;
    uniform float uZeroLevel;

    varying float vHeight;
    varying vec2 vUv;
    varying vec3 vNormal;
    varying vec3 vWorldPos;

    void main() {
      vUv = uv;
      vHeight = aHeight;

      vec3 displaced = position;
      // Y = (aHeight - zeroLevel) * heightScale * animProgress
      // 当 aHeight == zeroLevel → Y = 0 → 海面
      float animatedY = (aHeight - uZeroLevel) * uHeightScale * uAnimProgress;
      displaced.y = animatedY;

      vWorldPos = displaced;

      // 法线（近似 — 用 dFdx/dFdy 不行，手动用相邻差分）
      vNormal = normal; // 会在 fragment 中做近似

      gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
    }
  `, []);

  // ─── 片段着色器 — 红涨绿跌 + 中间透明 ─────────────────
  const fragmentShader = useMemo(() => /* glsl */ `
    uniform float uZeroLevel;
    uniform float uShowContours;
    uniform float uTime;

    varying float vHeight;
    varying vec2 vUv;
    varying vec3 vNormal;
    varying vec3 vWorldPos;

    void main() {
      // centered: >0 = 涨 (高于海面), <0 = 跌 (低于海面)
      float diff = vHeight - uZeroLevel;
      // 归一化到 [-1, 1]，按涨跌最大幅度
      float maxRange = max(1.0 - uZeroLevel, uZeroLevel);
      maxRange = max(maxRange, 0.001);
      float centered = clamp(diff / maxRange, -1.0, 1.0);

      // 涨跌颜色：涨→红，跌→绿
      vec3 deepRed   = vec3(0.75, 0.08, 0.08);
      vec3 brightRed = vec3(0.92, 0.22, 0.18);
      vec3 lightRed  = vec3(0.95, 0.55, 0.45);
      vec3 deepGreen = vec3(0.04, 0.50, 0.28);
      vec3 green     = vec3(0.10, 0.70, 0.40);
      vec3 lightGreen= vec3(0.50, 0.85, 0.55);

      vec3 color;
      float absCentered = abs(centered);

      if (centered > 0.0) {
        if (absCentered < 0.4) {
          color = mix(lightRed, brightRed, absCentered / 0.4);
        } else {
          color = mix(brightRed, deepRed, (absCentered - 0.4) / 0.6);
        }
      } else {
        if (absCentered < 0.4) {
          color = mix(lightGreen, green, absCentered / 0.4);
        } else {
          color = mix(green, deepGreen, (absCentered - 0.4) / 0.6);
        }
      }

      // 柔和光照
      // 用屏幕空间导数近似法线
      vec3 dx = dFdx(vWorldPos);
      vec3 dz = dFdy(vWorldPos);
      vec3 N = normalize(cross(dx, dz));
      // 确保法线指向观察者（双面渲染时背面法线需要翻转）
      if (!gl_FrontFacing) N = -N;

      vec3 lightDir = normalize(vec3(0.3, 1.0, 0.5));
      float NdotL = max(dot(N, lightDir), 0.0);
      float toonShade = floor(NdotL * 4.0 + 0.5) / 4.0;
      float diffuse = mix(NdotL, toonShade, 0.3) * 0.3 + 0.70;
      color *= diffuse;

      // 等高线
      if (uShowContours > 0.5) {
        float contourFreq = 10.0;
        float contour = fract(vHeight * contourFreq);
        float line = smoothstep(0.0, 0.03, contour) * smoothstep(0.06, 0.03, contour);
        color = mix(color, vec3(1.0), line * 0.15);
      }

      // 透明度: |centered| 越小 → 越透明
      float alphaByChange = smoothstep(0.0, 0.15, absCentered);
      alphaByChange = mix(0.06, 0.95, alphaByChange);

      // 边缘渐隐
      float edgeDist = min(min(vUv.x, 1.0 - vUv.x), min(vUv.y, 1.0 - vUv.y));
      float edgeFade = smoothstep(0.0, 0.04, edgeDist);

      float alpha = alphaByChange * edgeFade;

      gl_FragColor = vec4(color, alpha);
    }
  `, []);

  const uniforms = useMemo(
    () => ({
      uHeightScale: { value: heightScale },
      uTime: { value: 0 },
      uAnimProgress: { value: 0 },
      uZeroLevel: { value: zeroLevel },
      uShowContours: { value: showContours ? 1.0 : 0.0 },
    }),
    []
  );

  useEffect(() => {
    if (materialRef.current) {
      materialRef.current.uniforms.uHeightScale.value = heightScale;
      materialRef.current.uniforms.uZeroLevel.value = zeroLevel;
      materialRef.current.uniforms.uShowContours.value = showContours ? 1.0 : 0.0;
      animProgress.current = 0;
    }
  }, [heightData, bounds, heightScale, showContours, zeroLevel]);

  useFrame((_, delta) => {
    if (materialRef.current) {
      animProgress.current = Math.min(animProgress.current + delta * 1.5, 1.0);
      materialRef.current.uniforms.uAnimProgress.value =
        easeOutCubic(animProgress.current);
      materialRef.current.uniforms.uTime.value += delta;
    }
  });

  if (!geometry) return null;

  return (
    <mesh ref={meshRef} geometry={geometry}>
      <shaderMaterial
        ref={materialRef}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        transparent
        side={THREE.DoubleSide}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        extensions={{ derivatives: true } as any}
      />
    </mesh>
  );
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}
