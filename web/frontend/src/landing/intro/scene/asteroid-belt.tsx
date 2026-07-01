"use client";

import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { BELT, PALETTE, SUN_POSITION } from "../constants";
import type { IntroWorld, ScalarRef } from "../contract";
import { NOISE_GLSL } from "../shaders/noise";

const ROCK_RADIUS = 0.05;
/** snoise domain frequency: 6 cycles per rock radius (6 / ROCK_RADIUS). */
const DEFORM_FREQUENCY = (6 / ROCK_RADIUS).toFixed(1);
/** Displacement amplitude: 35% of the rock radius (0.35 * ROCK_RADIUS). */
const DEFORM_AMPLITUDE = (0.35 * ROCK_RADIUS).toFixed(4);

/** Deterministic PRNG so the belt layout is stable across mounts. */
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
 * Instance matrices are built SUN-LOCAL; the vertex shader spins the whole
 * torus around the sun's Y axis by uTime * 0.05, then re-anchors at uSunPos,
 * after deforming each icosahedron into a rock along its normals.
 */
const BELT_VERTEX = /* glsl */ `
uniform float uTime;
uniform vec3 uSunPos;
attribute float aSeed;
varying vec3 vWorldPos;
varying vec3 vWorldNormal;
varying float vSeed;
${NOISE_GLSL}

void main() {
  vSeed = aSeed;
  vec3 seedOffset = vec3(aSeed * 19.3, aSeed * 47.7, aSeed * 31.1);
  float bump = snoise(position * ${DEFORM_FREQUENCY} + seedOffset);
  vec3 displaced = position + normal * bump * ${DEFORM_AMPLITUDE};
  vec4 rockLocal = instanceMatrix * vec4(displaced, 1.0);
  vec3 rockNormal = normalize(mat3(instanceMatrix) * normal);
  float angle = uTime * 0.05;
  float c = cos(angle);
  float s = sin(angle);
  mat3 orbit = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c);
  vec3 sunLocal = orbit * rockLocal.xyz;
  vec4 worldPos = modelMatrix * vec4(sunLocal + uSunPos, 1.0);
  vWorldPos = worldPos.xyz;
  vWorldNormal = normalize(mat3(modelMatrix) * (orbit * rockNormal));
  gl_Position = projectionMatrix * viewMatrix * worldPos;
}
`;

const BELT_FRAGMENT = /* glsl */ `
uniform vec3 uSunPos;
uniform vec3 uChampagne;
uniform vec3 uRockLow;
uniform vec3 uRockHigh;
uniform float uReveal;
varying vec3 vWorldPos;
varying vec3 vWorldNormal;
varying float vSeed;

void main() {
  vec3 n = normalize(vWorldNormal);
  vec3 l = normalize(uSunPos - vWorldPos);
  float hl = dot(n, l) * 0.5 + 0.5;
  float shade = hl * hl;
  vec3 color = mix(uRockLow, uRockHigh, vSeed) * (0.03 + shade);
  vec3 viewDir = normalize(cameraPosition - vWorldPos);
  float rim = pow(1.0 - clamp(dot(viewDir, n), 0.0, 1.0), 3.0);
  color += uChampagne * rim * 0.4 * shade;
  gl_FragColor = vec4(color * uReveal, 1.0);
}
`;

export function AsteroidBelt({
  world,
  visible,
  count,
  reveal,
}: {
  world: IntroWorld;
  visible: { value: boolean };
  count: number;
  reveal?: ScalarRef;
}) {
  const { group, mesh, geometry, material, uniforms } = useMemo(() => {
    const beltUniforms = {
      uTime: { value: 0 },
      uSunPos: { value: new THREE.Vector3(...SUN_POSITION) },
      uChampagne: { value: new THREE.Color(PALETTE.champagne) },
      uRockLow: { value: new THREE.Color("#241a10") },
      uRockHigh: { value: new THREE.Color("#5a4632") },
      uReveal: { value: 1 },
    };

    const rockGeometry = new THREE.IcosahedronGeometry(ROCK_RADIUS, 0);
    const rockMaterial = new THREE.ShaderMaterial({
      vertexShader: BELT_VERTEX,
      fragmentShader: BELT_FRAGMENT,
      uniforms: beltUniforms,
    });

    const instanced = new THREE.InstancedMesh(rockGeometry, rockMaterial, count);
    instanced.instanceMatrix.setUsage(THREE.StaticDrawUsage);
    instanced.frustumCulled = false;

    const rand = mulberry32(0x5e17_be17);
    const matrix = new THREE.Matrix4();
    const position = new THREE.Vector3();
    const quaternion = new THREE.Quaternion();
    const euler = new THREE.Euler();
    const scale = new THREE.Vector3();
    const seeds = new Float32Array(count);

    for (let i = 0; i < count; i += 1) {
      const angle = rand() * Math.PI * 2;
      const radial = BELT.innerRadius + (rand() * 2 - 1) * BELT.tube;
      position.set(
        Math.cos(angle) * radial,
        (rand() * 2 - 1) * BELT.yJitter,
        Math.sin(angle) * radial
      );
      euler.set(rand() * Math.PI * 2, rand() * Math.PI * 2, rand() * Math.PI * 2);
      quaternion.setFromEuler(euler);
      scale.setScalar(0.5 + rand() * 1.1);
      matrix.compose(position, quaternion, scale);
      instanced.setMatrixAt(i, matrix);
      seeds[i] = rand();
    }

    const seedAttribute = new THREE.InstancedBufferAttribute(seeds, 1);
    seedAttribute.setUsage(THREE.StaticDrawUsage);
    rockGeometry.setAttribute("aSeed", seedAttribute);

    const beltGroup = new THREE.Group();
    beltGroup.add(instanced);

    return {
      group: beltGroup,
      mesh: instanced,
      geometry: rockGeometry,
      material: rockMaterial,
      uniforms: beltUniforms,
    };
  }, [count]);

  useEffect(() => {
    return () => {
      geometry.dispose();
      material.dispose();
      mesh.dispose();
    };
  }, [geometry, material, mesh]);

  useFrame(() => {
    group.visible = visible.value;
    uniforms.uTime.value = world.time.value;
    uniforms.uReveal.value = reveal ? reveal.value : 1;
  });

  return <primitive object={group} />;
}
