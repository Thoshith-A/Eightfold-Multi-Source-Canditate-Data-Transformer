"use client";

import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { METEOR_PATH, PALETTE } from "../constants";
import type { IntroWorld, ScalarRef } from "../contract";
import { NOISE_GLSL } from "../shaders/noise";

/** Deterministic PRNG so the trail layout is stable across mounts. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Component-wise cubic bezier along METEOR_PATH — zero allocations. */
function pathPoint(out: THREE.Vector3, t: number): THREE.Vector3 {
  const u = 1 - t;
  const a = u * u * u;
  const b = 3 * u * u * t;
  const c = 3 * u * t * t;
  const d = t * t * t;
  const { p0, p1, p2, p3 } = METEOR_PATH;
  return out.set(
    a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
    a * p0[2] + b * p1[2] + c * p2[2] + d * p3[2]
  );
}

/** Cubic bezier derivative (velocity direction, unnormalized). */
function pathTangent(out: THREE.Vector3, t: number): THREE.Vector3 {
  const u = 1 - t;
  const a = 3 * u * u;
  const b = 6 * u * t;
  const c = 3 * t * t;
  const { p0, p1, p2, p3 } = METEOR_PATH;
  return out.set(
    a * (p1[0] - p0[0]) + b * (p2[0] - p1[0]) + c * (p3[0] - p2[0]),
    a * (p1[1] - p0[1]) + b * (p2[1] - p1[1]) + c * (p3[1] - p2[1]),
    a * (p1[2] - p0[2]) + b * (p2[2] - p1[2]) + c * (p3[2] - p2[2])
  );
}

const AXIS_X = new THREE.Vector3(1, 0, 0);
const TEMP_HEAD = new THREE.Vector3();
const TEMP_TAIL = new THREE.Vector3();
const TEMP_DIR = new THREE.Vector3();
const TEMP_MID = new THREE.Vector3();
const TEMP_ALIGN = new THREE.Quaternion();
const TEMP_ROLL = new THREE.Quaternion();

const ROCK_VERTEX = /* glsl */ `
${NOISE_GLSL}
varying vec3 vLocal;
varying vec3 vWorldNormal;

void main() {
  vec3 displaced = position + normal * (snoise(position * 3.2) * 0.28);
  vLocal = displaced;
  vWorldNormal = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
}
`;

const ROCK_FRAGMENT = /* glsl */ `
${NOISE_GLSL}
uniform float uTime;
uniform vec3 uVelDir;
uniform vec3 uEmber;
uniform vec3 uHotCore;
varying vec3 vLocal;
varying vec3 vWorldNormal;

void main() {
  vec3 n = normalize(vWorldNormal);
  float heat = pow(max(dot(n, -uVelDir), 0.0), 2.0);
  float flicker = 0.5 + 0.5 * fbm(vLocal * 2.7 + vec3(uTime * 1.9, uTime * 0.7, uTime * 1.3), 3);
  float h = heat * (0.7 + 0.6 * flicker);
  float rocky = 0.5 + 0.5 * fbm(vLocal * 4.1, 3);
  vec3 col = mix(vec3(0.028, 0.024, 0.020), vec3(0.085, 0.071, 0.058), rocky);
  col = mix(col, uEmber, smoothstep(0.04, 0.34, h));
  col = mix(col, uHotCore, smoothstep(0.30, 0.68, h));
  col = mix(col, vec3(1.0), smoothstep(0.64, 1.0, h));
  col *= 1.0 + h * 4.0;
  gl_FragColor = vec4(col, 1.0);
}
`;

const TRAIL_VERTEX = /* glsl */ `
attribute float aIndex;
attribute vec3 aJitter;
uniform float uProgress;
uniform vec3 uP0;
uniform vec3 uP1;
uniform vec3 uP2;
uniform vec3 uP3;
varying float vAge;

vec3 sgBezier(float t) {
  float u = 1.0 - t;
  return u * u * u * uP0 + 3.0 * u * u * t * uP1 + 3.0 * u * t * t * uP2 + t * t * t * uP3;
}

void main() {
  float t = uProgress - aIndex * 0.22;
  if (t < 0.0 || t > uProgress) {
    vAge = 1.0;
    gl_PointSize = 0.0;
    gl_Position = vec4(0.0, 0.0, 2.0, 1.0);
    return;
  }
  float age = clamp((uProgress - t) / 0.22, 0.0, 1.0);
  vAge = age;
  vec3 p = sgBezier(clamp(t, 0.0, 1.0)) + aJitter * age;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = mix(12.0, 1.0, age) * clamp(16.0 / max(-mv.z, 0.1), 0.35, 1.6);
}
`;

const TRAIL_FRAGMENT = /* glsl */ `
uniform vec3 uEmber;
uniform vec3 uDeepAmber;
varying float vAge;

void main() {
  float mask = smoothstep(0.5, 0.12, length(gl_PointCoord - 0.5));
  vec3 col = mix(vec3(3.0), uEmber * 1.4, smoothstep(0.0, 0.45, vAge));
  col = mix(col, uDeepAmber * 0.5, smoothstep(0.4, 1.0, vAge));
  float alpha = mask * (1.0 - vAge);
  gl_FragColor = vec4(col, alpha);
}
`;

const RIBBON_VERTEX = /* glsl */ `
varying vec2 vUv;

void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const RIBBON_FRAGMENT = /* glsl */ `
uniform vec3 uEmber;
uniform vec3 uHotCore;
varying vec2 vUv;

void main() {
  float head = pow(vUv.x, 2.0);
  float vert = sin(vUv.y * 3.14159265);
  vec3 col = mix(uEmber * 0.8, uHotCore * 2.6, head);
  gl_FragColor = vec4(col, head * vert);
}
`;

export function Meteor({
  world,
  progress,
  trailCount,
  headOut,
}: {
  world: IntroWorld;
  progress: ScalarRef;
  trailCount: number;
  headOut: THREE.Vector3;
}) {
  const groupRef = useRef<THREE.Group>(null);

  const {
    rock,
    rockGeometry,
    rockMaterial,
    rockUniforms,
    trail,
    trailGeometry,
    trailMaterial,
    trailUniforms,
    ribbonA,
    ribbonB,
    ribbonGeometry,
    ribbonMaterial,
  } = useMemo(() => {
    const rockUni = {
      uTime: { value: 0 },
      uVelDir: { value: new THREE.Vector3(0, 0, -1) },
      uEmber: { value: new THREE.Color(PALETTE.ember) },
      uHotCore: { value: new THREE.Color(PALETTE.hotCore) },
    };
    const rockGeo = new THREE.IcosahedronGeometry(0.34, 2);
    const rockMat = new THREE.ShaderMaterial({
      vertexShader: ROCK_VERTEX,
      fragmentShader: ROCK_FRAGMENT,
      uniforms: rockUni,
    });
    const rockMesh = new THREE.Mesh(rockGeo, rockMat);

    const trailUni = {
      uProgress: { value: 0 },
      uP0: { value: new THREE.Vector3(...METEOR_PATH.p0) },
      uP1: { value: new THREE.Vector3(...METEOR_PATH.p1) },
      uP2: { value: new THREE.Vector3(...METEOR_PATH.p2) },
      uP3: { value: new THREE.Vector3(...METEOR_PATH.p3) },
      uEmber: { value: new THREE.Color(PALETTE.ember) },
      uDeepAmber: { value: new THREE.Color(PALETTE.deepAmber) },
    };
    const trailGeo = new THREE.BufferGeometry();
    const rand = mulberry32(0x7e3a91);
    const positions = new Float32Array(trailCount * 3);
    const indices = new Float32Array(trailCount);
    const jitter = new Float32Array(trailCount * 3);
    for (let i = 0; i < trailCount; i += 1) {
      indices[i] = trailCount > 1 ? i / (trailCount - 1) : 0;
      jitter[i * 3] = (rand() * 2 - 1) * 0.7;
      jitter[i * 3 + 1] = (rand() * 2 - 1) * 0.7;
      jitter[i * 3 + 2] = (rand() * 2 - 1) * 0.7;
    }
    const positionAttr = new THREE.BufferAttribute(positions, 3);
    positionAttr.setUsage(THREE.StaticDrawUsage);
    const indexAttr = new THREE.BufferAttribute(indices, 1);
    indexAttr.setUsage(THREE.StaticDrawUsage);
    const jitterAttr = new THREE.BufferAttribute(jitter, 3);
    jitterAttr.setUsage(THREE.StaticDrawUsage);
    trailGeo.setAttribute("position", positionAttr);
    trailGeo.setAttribute("aIndex", indexAttr);
    trailGeo.setAttribute("aJitter", jitterAttr);
    const trailMat = new THREE.ShaderMaterial({
      vertexShader: TRAIL_VERTEX,
      fragmentShader: TRAIL_FRAGMENT,
      uniforms: trailUni,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const trailPoints = new THREE.Points(trailGeo, trailMat);
    trailPoints.frustumCulled = false;

    const ribbonGeo = new THREE.PlaneGeometry(1, 1);
    const ribbonMat = new THREE.ShaderMaterial({
      vertexShader: RIBBON_VERTEX,
      fragmentShader: RIBBON_FRAGMENT,
      uniforms: {
        uEmber: { value: new THREE.Color(PALETTE.ember) },
        uHotCore: { value: new THREE.Color(PALETTE.hotCore) },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
    });
    const meshA = new THREE.Mesh(ribbonGeo, ribbonMat);
    const meshB = new THREE.Mesh(ribbonGeo, ribbonMat);

    return {
      rock: rockMesh,
      rockGeometry: rockGeo,
      rockMaterial: rockMat,
      rockUniforms: rockUni,
      trail: trailPoints,
      trailGeometry: trailGeo,
      trailMaterial: trailMat,
      trailUniforms: trailUni,
      ribbonA: meshA,
      ribbonB: meshB,
      ribbonGeometry: ribbonGeo,
      ribbonMaterial: ribbonMat,
    };
  }, [trailCount]);

  useEffect(() => {
    return () => {
      rockGeometry.dispose();
      rockMaterial.dispose();
      trailGeometry.dispose();
      trailMaterial.dispose();
      ribbonGeometry.dispose();
      ribbonMaterial.dispose();
    };
  }, [rockGeometry, rockMaterial, trailGeometry, trailMaterial, ribbonGeometry, ribbonMaterial]);

  useFrame(() => {
    const group = groupRef.current;
    if (!group) return;
    const p = progress.value;
    const clamped = Math.min(Math.max(p, 0), 1);
    pathPoint(TEMP_HEAD, clamped);
    headOut.copy(TEMP_HEAD);

    const visible = p > 0.001 && p < 0.999;
    group.visible = visible;
    if (!visible) return;

    const time = world.time.value;
    rockUniforms.uTime.value = time;
    pathTangent(TEMP_DIR, clamped);
    if (TEMP_DIR.lengthSq() > 1e-8) {
      rockUniforms.uVelDir.value.copy(TEMP_DIR.normalize());
    }
    rock.position.copy(TEMP_HEAD);
    rock.rotation.set(time * 1.9, time * 2.6, time * 1.4);

    trailUniforms.uProgress.value = p;

    pathPoint(TEMP_TAIL, Math.max(clamped - 0.06, 0));
    TEMP_DIR.subVectors(TEMP_HEAD, TEMP_TAIL);
    const length = TEMP_DIR.length();
    if (length < 1e-4) {
      ribbonA.visible = false;
      ribbonB.visible = false;
      return;
    }
    TEMP_DIR.multiplyScalar(1 / length);
    TEMP_MID.addVectors(TEMP_HEAD, TEMP_TAIL).multiplyScalar(0.5);
    TEMP_ALIGN.setFromUnitVectors(AXIS_X, TEMP_DIR);

    ribbonA.visible = true;
    ribbonA.position.copy(TEMP_MID);
    TEMP_ROLL.setFromAxisAngle(AXIS_X, time * 7.3);
    ribbonA.quaternion.copy(TEMP_ALIGN).multiply(TEMP_ROLL);
    ribbonA.scale.set(length, 0.085, 1);

    ribbonB.visible = true;
    ribbonB.position.copy(TEMP_MID);
    TEMP_ROLL.setFromAxisAngle(AXIS_X, time * 7.3 + 2.1);
    ribbonB.quaternion.copy(TEMP_ALIGN).multiply(TEMP_ROLL);
    ribbonB.scale.set(length, 0.055, 1);
  });

  return (
    <group ref={groupRef} visible={false}>
      <primitive object={rock} />
      <primitive object={trail} />
      <primitive object={ribbonA} />
      <primitive object={ribbonB} />
    </group>
  );
}
