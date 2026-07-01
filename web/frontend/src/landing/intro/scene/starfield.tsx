"use client";

import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { PALETTE, SUN_POSITION } from "../constants";
import type { IntroWorld, ScalarRef, ShockState } from "../contract";

/** Three depth shells so the field parallaxes like a real sky. */
const SHELL_RADII = [34, 48, 64] as const;
/** Radial jitter as a fraction of the shell radius. */
const SHELL_THICKNESS = 0.12;

/** Deterministic PRNG so the sky is identical across mounts. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Per-star twinkle (size + alpha) from the dilated clock, plus the impact
 * shockwave: a gaussian band around the expanding radius pushes stars
 * radially away from the shock center so the wave visibly ripples the sky.
 */
const VERTEX = /* glsl */ `
uniform float uTime;
uniform float uPixelRatio;
uniform vec3 uShockCenter;
uniform float uShockRadius;
uniform float uShockStrength;
attribute float aSize;
attribute float aPhase;
attribute vec3 aTint;
varying vec3 vTint;
varying float vTwinkle;

void main() {
  vec3 toStar = position - uShockCenter;
  float shockDist = length(toStar);
  vec3 shockDir = toStar / max(shockDist, 1e-4);
  float bandDist = shockDist - uShockRadius;
  float band = exp(-bandDist * bandDist * 0.02);
  vec3 displaced = position + shockDir * band * uShockStrength * 4.0;

  float twinkle = 0.5 + 0.5 * sin(uTime * (0.5 + aPhase * 1.3) + aPhase * 6.2831853);

  vec4 mvPosition = modelViewMatrix * vec4(displaced, 1.0);
  float attenuation = clamp(48.0 / max(-mvPosition.z, 1.0), 0.6, 1.5);
  float size = aSize * uPixelRatio * attenuation * (0.85 + 0.3 * twinkle);
  gl_PointSize = max(size, 0.5 * uPixelRatio);

  vTint = aTint;
  vTwinkle = twinkle;
  gl_Position = projectionMatrix * mvPosition;
}
`;

const FRAGMENT = /* glsl */ `
uniform float uOpacity;
varying vec3 vTint;
varying float vTwinkle;

void main() {
  float dist = length(gl_PointCoord - 0.5);
  float disc = smoothstep(0.5, 0.08, dist);
  float alpha = disc * (0.55 + 0.45 * vTwinkle) * uOpacity;
  if (alpha < 0.001) discard;
  gl_FragColor = vec4(vTint * (0.85 + 0.45 * vTwinkle), alpha);
}
`;

export function Starfield({
  world,
  shock,
  opacity,
  count,
}: {
  world: IntroWorld;
  shock: ShockState;
  opacity: ScalarRef;
  count: number;
}) {
  const { points, geometry, material, uniforms } = useMemo(() => {
    const starUniforms = {
      uTime: { value: 0 },
      uOpacity: { value: 0 },
      uPixelRatio: { value: 1 },
      uShockCenter: { value: new THREE.Vector3() },
      uShockRadius: { value: 0 },
      uShockStrength: { value: 0 },
    };

    const positions = new Float32Array(count * 3);
    const tints = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    const phases = new Float32Array(count);

    const rand = mulberry32(0x57a2_f1e1);
    const cream = new THREE.Color(PALETTE.cream);
    const tintPool = [
      new THREE.Color(PALETTE.white).lerp(cream, 0.35),
      cream.clone(),
      new THREE.Color(PALETTE.champagne).lerp(cream, 0.45),
    ];
    const tint = new THREE.Color();

    for (let i = 0; i < count; i += 1) {
      const shell = SHELL_RADII[i % SHELL_RADII.length];
      const u = rand() * 2 - 1;
      const theta = rand() * Math.PI * 2;
      const ring = Math.sqrt(Math.max(0, 1 - u * u));
      const radius = shell * (1 + (rand() - 0.5) * SHELL_THICKNESS);
      positions[i * 3] = ring * Math.cos(theta) * radius + SUN_POSITION[0];
      positions[i * 3 + 1] = u * radius + SUN_POSITION[1];
      positions[i * 3 + 2] = ring * Math.sin(theta) * radius + SUN_POSITION[2];

      tint.copy(tintPool[Math.floor(rand() * tintPool.length)]).lerp(cream, rand() * 0.4);
      tints[i * 3] = tint.r;
      tints[i * 3 + 1] = tint.g;
      tints[i * 3 + 2] = tint.b;

      sizes[i] = 0.5 + rand() * 1.5;
      phases[i] = rand();
    }

    const starGeometry = new THREE.BufferGeometry();
    const positionAttribute = new THREE.BufferAttribute(positions, 3);
    positionAttribute.setUsage(THREE.StaticDrawUsage);
    starGeometry.setAttribute("position", positionAttribute);
    const tintAttribute = new THREE.BufferAttribute(tints, 3);
    tintAttribute.setUsage(THREE.StaticDrawUsage);
    starGeometry.setAttribute("aTint", tintAttribute);
    const sizeAttribute = new THREE.BufferAttribute(sizes, 1);
    sizeAttribute.setUsage(THREE.StaticDrawUsage);
    starGeometry.setAttribute("aSize", sizeAttribute);
    const phaseAttribute = new THREE.BufferAttribute(phases, 1);
    phaseAttribute.setUsage(THREE.StaticDrawUsage);
    starGeometry.setAttribute("aPhase", phaseAttribute);

    const starMaterial = new THREE.ShaderMaterial({
      uniforms: starUniforms,
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const starPoints = new THREE.Points(starGeometry, starMaterial);
    starPoints.frustumCulled = false;
    starPoints.renderOrder = -10;

    return {
      points: starPoints,
      geometry: starGeometry,
      material: starMaterial,
      uniforms: starUniforms,
    };
  }, [count]);

  useEffect(() => {
    return () => {
      geometry.dispose();
      material.dispose();
    };
  }, [geometry, material]);

  useFrame((state) => {
    points.visible = opacity.value > 0.001;
    uniforms.uTime.value = world.time.value;
    uniforms.uOpacity.value = opacity.value;
    uniforms.uPixelRatio.value = state.viewport.dpr;
    uniforms.uShockRadius.value = shock.radius.value;
    uniforms.uShockStrength.value = shock.strength.value;
    uniforms.uShockCenter.value.copy(shock.center);
  });

  return <primitive object={points} />;
}
