"use client";

import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { PALETTE } from "../constants";
import type { IntroWorld, ScalarRef } from "../contract";

const SPARK_COUNT = 140;
const TEXTURE_SIZE = 128;

/** Deterministic PRNG so the spark layout is stable across mounts. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Soft-edged hexagonal bokeh sprite: hex path filled with a feathered radial gradient. */
function createHexBokehTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = TEXTURE_SIZE;
  canvas.height = TEXTURE_SIZE;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const center = TEXTURE_SIZE / 2;
    const radius = TEXTURE_SIZE * 0.42;
    const gradient = ctx.createRadialGradient(center, center, 0, center, center, radius * 1.08);
    gradient.addColorStop(0, hexToRgba(PALETTE.hotCore, 0.95));
    gradient.addColorStop(0.4, hexToRgba(PALETTE.champagne, 0.8));
    gradient.addColorStop(0.78, hexToRgba(PALETTE.champagne, 0.28));
    gradient.addColorStop(1, hexToRgba(PALETTE.champagne, 0));
    ctx.filter = "blur(3px)";
    ctx.beginPath();
    for (let i = 0; i < 6; i += 1) {
      const angle = (i / 6) * Math.PI * 2 + Math.PI / 6;
      const x = center + Math.cos(angle) * radius;
      const y = center + Math.sin(angle) * radius;
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/**
 * Lazy sinusoidal drift on the dilated clock plus a per-particle flicker
 * (0.25–0.8) that the fragment stage multiplies by the master intensity.
 */
const VERTEX = /* glsl */ `
uniform float uTime;
uniform float uScale;
attribute float aSize;
attribute float aPhase;
attribute float aFlick;
varying float vFlicker;

void main() {
  float ph = aPhase * 6.2831853;
  vec3 pos = position;
  pos.x += sin(uTime * 0.18 + ph) * 0.6;
  pos.y += sin(uTime * 0.13 + ph * 1.7) * 0.28 + cos(uTime * 0.07 + ph * 0.5) * 0.14;
  pos.z += cos(uTime * 0.11 + ph * 0.8) * 0.4;

  vFlicker = 0.25 + 0.55 * (0.5 + 0.5 * sin(uTime * (0.5 + aFlick * 1.2) + ph * 2.3));

  vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
  gl_PointSize = min(aSize * uScale / max(-mvPosition.z, 0.5), 180.0);
  gl_Position = projectionMatrix * mvPosition;
}
`;

const FRAGMENT = /* glsl */ `
uniform sampler2D uMap;
uniform float uIntensity;
varying float vFlicker;

void main() {
  vec4 tex = texture2D(uMap, gl_PointCoord);
  float alpha = tex.a * vFlicker * uIntensity;
  if (alpha < 0.001) discard;
  gl_FragColor = vec4(tex.rgb * (1.1 + 0.6 * vFlicker), alpha);
}
`;

export function SettlingSparks({ world, intensity }: { world: IntroWorld; intensity: ScalarRef }) {
  const { points, geometry, material, texture, uniforms } = useMemo(() => {
    const bokehTexture = createHexBokehTexture();
    const sparkUniforms = {
      uTime: { value: 0 },
      uScale: { value: 1 },
      uIntensity: { value: 0 },
      uMap: { value: bokehTexture },
    };

    const positions = new Float32Array(SPARK_COUNT * 3);
    const sizes = new Float32Array(SPARK_COUNT);
    const phases = new Float32Array(SPARK_COUNT);
    const flicks = new Float32Array(SPARK_COUNT);

    const rand = mulberry32(0xb0_4e7a);
    for (let i = 0; i < SPARK_COUNT; i += 1) {
      positions[i * 3] = (rand() * 2 - 1) * 8;
      positions[i * 3 + 1] = -0.3 + 2.5 * Math.pow(rand(), 1.7);
      positions[i * 3 + 2] = -2 + rand() * 8;
      sizes[i] = 0.12 + rand() * 0.38;
      phases[i] = rand();
      flicks[i] = rand();
    }

    const sparkGeometry = new THREE.BufferGeometry();
    const positionAttribute = new THREE.BufferAttribute(positions, 3);
    positionAttribute.setUsage(THREE.StaticDrawUsage);
    sparkGeometry.setAttribute("position", positionAttribute);
    const sizeAttribute = new THREE.BufferAttribute(sizes, 1);
    sizeAttribute.setUsage(THREE.StaticDrawUsage);
    sparkGeometry.setAttribute("aSize", sizeAttribute);
    const phaseAttribute = new THREE.BufferAttribute(phases, 1);
    phaseAttribute.setUsage(THREE.StaticDrawUsage);
    sparkGeometry.setAttribute("aPhase", phaseAttribute);
    const flickAttribute = new THREE.BufferAttribute(flicks, 1);
    flickAttribute.setUsage(THREE.StaticDrawUsage);
    sparkGeometry.setAttribute("aFlick", flickAttribute);

    const sparkMaterial = new THREE.ShaderMaterial({
      uniforms: sparkUniforms,
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const sparkPoints = new THREE.Points(sparkGeometry, sparkMaterial);
    sparkPoints.frustumCulled = false;

    return {
      points: sparkPoints,
      geometry: sparkGeometry,
      material: sparkMaterial,
      texture: bokehTexture,
      uniforms: sparkUniforms,
    };
  }, []);

  useEffect(() => {
    return () => {
      geometry.dispose();
      material.dispose();
      texture.dispose();
    };
  }, [geometry, material, texture]);

  useFrame((state) => {
    points.visible = intensity.value > 0.001;
    uniforms.uTime.value = world.time.value;
    uniforms.uIntensity.value = intensity.value;
    const camera = state.camera as THREE.PerspectiveCamera;
    uniforms.uScale.value =
      (state.size.height * state.viewport.dpr) /
      (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) * 0.5));
  });

  return <primitive object={points} />;
}
