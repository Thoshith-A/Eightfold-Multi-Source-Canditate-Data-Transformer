"use client";

import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { PALETTE, SUN_POSITION } from "../constants";
import type { BlastState, IntroWorld } from "../contract";
import { NOISE_GLSL } from "../shaders/noise";

/** Deterministic PRNG so the debris layout is stable across mounts. */
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
 * Fully stateless instanced shards: position is a pure function of the
 * blast/vortex/condense/fade uniforms — zero CPU simulation.
 */
const VERTEX = /* glsl */ `
${NOISE_GLSL}
attribute vec3 aDir;
attribute float aSpeed;
attribute float aSeed;
attribute float aWave;
attribute vec4 aTumble;
uniform float uTime;
uniform float uBlast;
uniform float uVortex;
uniform float uCondense;
uniform float uFade;
uniform vec3 uOrigin;
uniform vec3 uTarget;
varying float vTemp;
varying float vWave;
varying float vSeed;

mat3 sgAxisRotation(vec3 axis, float angle) {
  float s = sin(angle);
  float c = cos(angle);
  float oc = 1.0 - c;
  return mat3(
    oc * axis.x * axis.x + c,          oc * axis.x * axis.y + axis.z * s, oc * axis.z * axis.x - axis.y * s,
    oc * axis.x * axis.y - axis.z * s, oc * axis.y * axis.y + c,          oc * axis.y * axis.z + axis.x * s,
    oc * axis.z * axis.x + axis.y * s, oc * axis.y * axis.z - axis.x * s, oc * axis.z * axis.z + c
  );
}

void main() {
  vec3 local = sgAxisRotation(aTumble.xyz, uTime * aTumble.w + aSeed * 6.2831853) * position;

  vec3 radial = aDir * aSpeed * (1.0 - exp(-uBlast * 3.0)) * 1.9;
  vec3 pos = uOrigin + radial;

  float waveLocal = clamp(uCondense * 1.45 - aWave * 0.18, 0.0, 1.0);
  vec3 rel = pos - uTarget;
  float radius = length(rel.xz);
  float theta = atan(rel.z, rel.x);
  float y = rel.y;
  theta += uVortex * (3.2 + aSeed * 1.5) * waveLocal * (1.0 + 2.0 / (1.0 + radius));
  radius *= pow(1.0 - waveLocal, 1.45);
  y *= 1.0 - waveLocal * 0.92;
  float wobAmp = (1.0 - waveLocal) * uVortex * 0.5;
  vec3 wobble = vec3(
    snoise(pos * 0.4 + aSeed * 7.0),
    snoise(pos * 0.4 + aSeed * 7.0 + vec3(23.4, 11.9, 31.7)),
    snoise(pos * 0.4 + aSeed * 7.0 + vec3(47.2, 5.3, 17.8))
  ) * wobAmp;
  pos = uTarget + vec3(cos(theta) * radius, y, sin(theta) * radius) + wobble;

  float shardScale = 1.0 - clamp(uFade * (0.6 + aSeed), 0.0, 1.0);

  vTemp = clamp(1.4 - uBlast * (0.5 + aSeed * 0.9), 0.0, 1.4) + waveLocal * 1.2;
  vWave = waveLocal;
  vSeed = aSeed;

  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos + local * shardScale, 1.0);
}
`;

/** Pure emissive cooling ramp — no lighting; that IS the look. */
const FRAGMENT = /* glsl */ `
uniform vec3 uDeepAmber;
uniform vec3 uEmber;
uniform vec3 uChampagne;
uniform vec3 uHotCore;
varying float vTemp;
varying float vWave;
varying float vSeed;

void main() {
  float t = clamp(vTemp, 0.0, 2.6);
  vec3 col = vec3(0.032, 0.027, 0.022);
  col = mix(col, uDeepAmber, smoothstep(0.12, 0.55, t));
  col = mix(col, uEmber, smoothstep(0.5, 1.05, t));
  col = mix(col, uChampagne, smoothstep(1.0, 1.7, t));
  col = mix(col, uHotCore, smoothstep(1.7, 2.35, t));
  float intensity = (0.2 + pow(t / 2.6, 1.5) * 2.4) * (0.92 + vSeed * 0.16 + vWave * 0.05);
  gl_FragColor = vec4(col * intensity, 1.0);
}
`;

export function DebrisField({
  world,
  blast,
  count,
}: {
  world: IntroWorld;
  blast: BlastState;
  count: number;
}) {
  const { mesh, geometry, material, uniforms } = useMemo(() => {
    const shardUniforms = {
      uTime: { value: 0 },
      uBlast: { value: 0 },
      uVortex: { value: 0 },
      uCondense: { value: 0 },
      uFade: { value: 0 },
      uOrigin: { value: new THREE.Vector3(...SUN_POSITION) },
      uTarget: { value: new THREE.Vector3(...SUN_POSITION) },
      uDeepAmber: { value: new THREE.Color(PALETTE.deepAmber) },
      uEmber: { value: new THREE.Color(PALETTE.ember) },
      uChampagne: { value: new THREE.Color(PALETTE.champagne) },
      uHotCore: { value: new THREE.Color(PALETTE.hotCore) },
    };

    const shardGeometry = new THREE.TetrahedronGeometry(0.045);
    shardGeometry.deleteAttribute("normal");
    shardGeometry.deleteAttribute("uv");

    const shardMaterial = new THREE.ShaderMaterial({
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      uniforms: shardUniforms,
    });

    const instanced = new THREE.InstancedMesh(shardGeometry, shardMaterial, count);
    instanced.instanceMatrix.setUsage(THREE.StaticDrawUsage);
    instanced.frustumCulled = false;
    instanced.visible = false;

    const rand = mulberry32(0x9d2c5681);
    const dirs = new Float32Array(count * 3);
    const speeds = new Float32Array(count);
    const seeds = new Float32Array(count);
    const waves = new Float32Array(count);
    const tumbles = new Float32Array(count * 4);

    for (let i = 0; i < count; i += 1) {
      const z = rand() * 2 - 1;
      const angle = rand() * Math.PI * 2;
      const ring = Math.sqrt(Math.max(1 - z * z, 0));
      const dx = Math.cos(angle) * ring;
      const dy = z * 0.38;
      const dz = Math.sin(angle) * ring;
      const inv = 1 / Math.max(Math.hypot(dx, dy, dz), 1e-6);
      dirs[i * 3] = dx * inv;
      dirs[i * 3 + 1] = dy * inv;
      dirs[i * 3 + 2] = dz * inv;

      speeds[i] = 4 + rand() * 10;
      seeds[i] = rand();
      waves[i] = i % 3;

      const tz = rand() * 2 - 1;
      const tAngle = rand() * Math.PI * 2;
      const tRing = Math.sqrt(Math.max(1 - tz * tz, 0));
      tumbles[i * 4] = Math.cos(tAngle) * tRing;
      tumbles[i * 4 + 1] = tz;
      tumbles[i * 4 + 2] = Math.sin(tAngle) * tRing;
      tumbles[i * 4 + 3] = 1.5 + rand() * 4.5;
    }

    const dirAttr = new THREE.InstancedBufferAttribute(dirs, 3);
    dirAttr.setUsage(THREE.StaticDrawUsage);
    const speedAttr = new THREE.InstancedBufferAttribute(speeds, 1);
    speedAttr.setUsage(THREE.StaticDrawUsage);
    const seedAttr = new THREE.InstancedBufferAttribute(seeds, 1);
    seedAttr.setUsage(THREE.StaticDrawUsage);
    const waveAttr = new THREE.InstancedBufferAttribute(waves, 1);
    waveAttr.setUsage(THREE.StaticDrawUsage);
    const tumbleAttr = new THREE.InstancedBufferAttribute(tumbles, 4);
    tumbleAttr.setUsage(THREE.StaticDrawUsage);
    shardGeometry.setAttribute("aDir", dirAttr);
    shardGeometry.setAttribute("aSpeed", speedAttr);
    shardGeometry.setAttribute("aSeed", seedAttr);
    shardGeometry.setAttribute("aWave", waveAttr);
    shardGeometry.setAttribute("aTumble", tumbleAttr);

    return {
      mesh: instanced,
      geometry: shardGeometry,
      material: shardMaterial,
      uniforms: shardUniforms,
    };
  }, [count]);

  useEffect(() => {
    return () => {
      geometry.dispose();
      material.dispose();
    };
  }, [geometry, material]);

  useFrame(() => {
    const visible = blast.blast.value > 0;
    mesh.visible = visible;
    if (!visible) return;
    uniforms.uTime.value = world.time.value;
    uniforms.uBlast.value = blast.blast.value;
    uniforms.uVortex.value = blast.vortex.value;
    uniforms.uCondense.value = blast.condense.value;
    uniforms.uFade.value = blast.fade.value;
  });

  return <primitive object={mesh} />;
}
