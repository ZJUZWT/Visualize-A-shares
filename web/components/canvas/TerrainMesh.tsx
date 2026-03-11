"use client";

/**
 * TerrainMesh v2.0 — 3D 地形曲面渲染组件
 *
 * v2.0 更新：
 * - 清爽简约配色（薄荷→天蓝→薰衣草渐变）
 * - 卡通着色风格（阶梯色带）
 * - 柔和光照，无 PBR 真实感
 * - 海面以下不渲染（alpha=0）
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
  showContours?: boolean;
}

// ─── 顶点着色器 ──────────────────────────────────────
const vertexShader = /* glsl */ `
  uniform sampler2D uHeightMap;
  uniform float uHeightScale;
  uniform float uAnimProgress;

  varying float vHeight;
  varying float vRawHeight;
  varying vec2 vUv;
  varying vec3 vNormal;
  varying vec3 vWorldPos;

  void main() {
    vUv = uv;
    
    float height = texture2D(uHeightMap, uv).r;
    vRawHeight = height;
    vHeight = height;
    
    vec3 displaced = position;
    // 将归一化高度 [0,1] 映射为有符号偏移 [-1, 1]
    // 这样跌的（低值）会低于海面，涨的（高值）会高于海面
    float signedHeight = (height - 0.5) * 2.0;
    float animatedHeight = signedHeight * uHeightScale * uAnimProgress;
    displaced.z = animatedHeight;
    
    // 法线计算
    float eps = 1.0 / 128.0;
    float hL = texture2D(uHeightMap, uv - vec2(eps, 0.0)).r * uHeightScale;
    float hR = texture2D(uHeightMap, uv + vec2(eps, 0.0)).r * uHeightScale;
    float hD = texture2D(uHeightMap, uv - vec2(0.0, eps)).r * uHeightScale;
    float hU = texture2D(uHeightMap, uv + vec2(0.0, eps)).r * uHeightScale;
    vNormal = normalize(vec3(hL - hR, hD - hU, 2.0));
    
    vWorldPos = displaced;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
  }
`;

// ─── 片段着色器 — 高饱和度 + 强对比度 ─────────────────
const fragmentShader = /* glsl */ `
  uniform float uZMin;
  uniform float uZMax;
  uniform float uShowContours;
  uniform float uTime;

  varying float vHeight;
  varying float vRawHeight;
  varying vec2 vUv;
  varying vec3 vNormal;
  varying vec3 vWorldPos;

  // 高饱和度配色 — 绿(跌)→白(平)→红(涨)
  vec3 colorDeepGreen = vec3(0.05, 0.55, 0.30);   // 深绿 (大跌)
  vec3 colorGreen     = vec3(0.10, 0.72, 0.42);   // 鲜绿 (跌)
  vec3 colorLightGreen= vec3(0.55, 0.85, 0.60);   // 浅绿 (小跌)
  vec3 colorNeutral   = vec3(0.92, 0.93, 0.95);   // 极浅灰白 (平)
  vec3 colorLightRed  = vec3(0.95, 0.60, 0.50);   // 浅红 (小涨)
  vec3 colorRed       = vec3(0.90, 0.25, 0.20);   // 鲜红 (涨)
  vec3 colorHot       = vec3(0.75, 0.10, 0.10);   // 深红 (涨停)

  void main() {
    float range = uZMax - uZMin;
    float t = range > 0.001 ? (vHeight - uZMin) / range : 0.5;
    t = clamp(t, 0.0, 1.0);
    
    // 使用 pow 拉伸对比度 — 让中间区域变窄，两端更明显
    // 先映射到 [-1, 1] 然后用 sign-preserving pow
    float centered = t * 2.0 - 1.0; // [-1, 1]
    float stretched = sign(centered) * pow(abs(centered), 0.7); // 增强两端
    t = (stretched + 1.0) * 0.5; // 回到 [0, 1]
    
    // 七段式高饱和度配色
    vec3 color;
    if (t < 0.12) {
      color = mix(colorDeepGreen, colorGreen, t / 0.12);
    } else if (t < 0.30) {
      color = mix(colorGreen, colorLightGreen, (t - 0.12) / 0.18);
    } else if (t < 0.45) {
      color = mix(colorLightGreen, colorNeutral, (t - 0.30) / 0.15);
    } else if (t < 0.55) {
      color = colorNeutral;
    } else if (t < 0.70) {
      color = mix(colorNeutral, colorLightRed, (t - 0.55) / 0.15);
    } else if (t < 0.88) {
      color = mix(colorLightRed, colorRed, (t - 0.70) / 0.18);
    } else {
      color = mix(colorRed, colorHot, (t - 0.88) / 0.12);
    }
    
    // 光照 — 柔和漫反射 + 微弱高光
    vec3 lightDir = normalize(vec3(0.3, 0.5, 1.0));
    float NdotL = max(dot(vNormal, lightDir), 0.0);
    // 柔和阶梯（4级）
    float toonShade = floor(NdotL * 4.0 + 0.5) / 4.0;
    float diffuse = mix(NdotL, toonShade, 0.3) * 0.3 + 0.70;
    color *= diffuse;
    
    // 等高线 — 更明显
    if (uShowContours > 0.5) {
      float contourFreq = 10.0;
      float contour = fract(vRawHeight * contourFreq);
      float line = smoothstep(0.0, 0.03, contour) * smoothstep(0.06, 0.03, contour);
      color = mix(color, vec3(1.0), line * 0.15);
    }
    
    // 海面以下区域（rawHeight 接近 0）→ 透明
    float absHeight = abs(vRawHeight);
    float seaMask = smoothstep(0.0, 0.03, absHeight);
    
    // 边缘渐隐
    float edgeDist = min(min(vUv.x, 1.0 - vUv.x), min(vUv.y, 1.0 - vUv.y));
    float edgeFade = smoothstep(0.0, 0.04, edgeDist);
    
    float alpha = 0.95 * edgeFade * seaMask;
    
    gl_FragColor = vec4(color, alpha);
  }
`;

export default function TerrainMesh({
  heightData,
  resolution,
  bounds,
  heightScale = 3.0,
  showContours = true,
}: TerrainMeshProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const animProgress = useRef(0);

  // 创建高度图纹理
  const heightTexture = useMemo(() => {
    if (!heightData || heightData.length === 0) return null;

    const size = resolution;
    const data = new Float32Array(size * size);

    const zMin = bounds.zmin;
    const zMax = bounds.zmax;
    const range = zMax - zMin || 1;

    for (let i = 0; i < Math.min(heightData.length, size * size); i++) {
      data[i] = (heightData[i] - zMin) / range;
    }

    const texture = new THREE.DataTexture(
      data,
      size,
      size,
      THREE.RedFormat,
      THREE.FloatType
    );
    texture.needsUpdate = true;
    texture.magFilter = THREE.LinearFilter;
    texture.minFilter = THREE.LinearFilter;
    texture.wrapS = THREE.ClampToEdgeWrapping;
    texture.wrapT = THREE.ClampToEdgeWrapping;

    return texture;
  }, [heightData, resolution, bounds]);

  const uniforms = useMemo(
    () => ({
      uHeightMap: { value: heightTexture },
      uHeightScale: { value: heightScale },
      uTime: { value: 0 },
      uAnimProgress: { value: 0 },
      uZMin: { value: bounds.zmin },
      uZMax: { value: bounds.zmax },
      uShowContours: { value: showContours ? 1.0 : 0.0 },
    }),
    []
  );

  useEffect(() => {
    if (materialRef.current && heightTexture) {
      materialRef.current.uniforms.uHeightMap.value = heightTexture;
      materialRef.current.uniforms.uZMin.value = bounds.zmin;
      materialRef.current.uniforms.uZMax.value = bounds.zmax;
      materialRef.current.uniforms.uHeightScale.value = heightScale;
      materialRef.current.uniforms.uShowContours.value = showContours ? 1.0 : 0.0;
      animProgress.current = 0;
    }
  }, [heightTexture, bounds, heightScale, showContours]);

  useFrame((_, delta) => {
    if (materialRef.current) {
      animProgress.current = Math.min(animProgress.current + delta * 1.5, 1.0);
      materialRef.current.uniforms.uAnimProgress.value =
        easeOutCubic(animProgress.current);
      materialRef.current.uniforms.uTime.value += delta;
    }
  });

  if (!heightTexture) return null;

  const width = bounds.xmax - bounds.xmin || 20;
  const height = bounds.ymax - bounds.ymin || 20;

  return (
    <mesh
      ref={meshRef}
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, -1, 0]}
    >
      <planeGeometry args={[width, height, resolution - 1, resolution - 1]} />
      <shaderMaterial
        ref={materialRef}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        transparent
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}
