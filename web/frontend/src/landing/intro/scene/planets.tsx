"use client";

import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { PALETTE, PLANETS, SUN_POSITION, type PlanetSpec } from "../constants";
import type { IntroWorld, ScalarRef } from "../contract";
import { NOISE_GLSL } from "../shaders/noise";

const ORBIT_SEGMENTS = 128;
const DEG2RAD = Math.PI / 180;
/** Self-rotation rates (rad/s of world time), inner fast -> outer slow. */
const SPIN_RATES = [0.6, 0.45, 0.3, 0.22, 0.16] as const;
/** Slow orbit-plane precession rates, alternating sense per planet. */
const PRECESS_RATES = [0.014, -0.011, 0.009, -0.007, 0.006] as const;
/** Ring orientations: lie in the orbital plane with a modest axial tilt. */
const RING_TILTS = [
  [-Math.PI / 2 + 0.32, 0, 0.18],
  [-Math.PI / 2 - 0.26, 0, -0.12],
] as const;

const PLANET_VERTEX = /* glsl */ `
varying vec3 vObjPos;
varying vec3 vWorldPos;
varying vec3 vWorldNormal;

void main() {
  vObjPos = position;
  vec4 worldPos = modelMatrix * vec4(position, 1.0);
  vWorldPos = worldPos.xyz;
  vWorldNormal = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * viewMatrix * worldPos;
}
`;

/**
 * Shared fragment scaffold: every planet is lit by a hand-rolled
 * half-lambert terminator from the proto-sun (no scene lights), squared so
 * the far side falls to near-black.
 */
function planetFragment(uniformsDecl: string, body: string): string {
  return /* glsl */ `
uniform float uTime;
uniform vec3 uSunPos;
uniform float uReveal;
${uniformsDecl}
varying vec3 vObjPos;
varying vec3 vWorldPos;
varying vec3 vWorldNormal;
${NOISE_GLSL}

float sgShade() {
  vec3 n = normalize(vWorldNormal);
  vec3 l = normalize(uSunPos - vWorldPos);
  float hl = dot(n, l) * 0.5 + 0.5;
  return hl * hl;
}

void main() {
${body}
  gl_FragColor.rgb *= uReveal;
}
`;
}

const KIND_FRAGMENTS: Record<PlanetSpec["kind"], string> = {
  gas: planetFragment(
    /* glsl */ `
uniform vec3 uDeepAmber;
uniform vec3 uChampagne;
uniform vec3 uCream;`,
    /* glsl */ `
  vec3 sp = normalize(vObjPos);
  float warp = fbm(sp * 3.0 + vec3(0.0, uTime * 0.04, 0.0), 4);
  float band = sin(asin(clamp(sp.y, -1.0, 1.0)) * 9.0 + warp * 2.4);
  float t = band * 0.5 + 0.5;
  vec3 color = mix(uDeepAmber, uChampagne, smoothstep(0.15, 0.62, t));
  color = mix(color, uCream, smoothstep(0.74, 0.95, t));
  gl_FragColor = vec4(color * (0.03 + sgShade()), 1.0);`
  ),
  cratered: planetFragment(
    /* glsl */ `
uniform vec3 uLow;
uniform vec3 uHigh;`,
    /* glsl */ `
  vec3 sp = normalize(vObjPos);
  float cell = cellular(sp * 4.0);
  float crater = 1.0 - smoothstep(0.08, 0.4, cell);
  float blotch = clamp(fbm(sp * 5.0, 3) * 0.5 + 0.5, 0.0, 1.0);
  vec3 color = mix(uLow, uHigh, blotch);
  color *= 1.0 - crater * 0.55;
  gl_FragColor = vec4(color * (0.03 + sgShade()), 1.0);`
  ),
  molten: planetFragment(
    /* glsl */ `
uniform vec3 uCrust;
uniform vec3 uEmber;
uniform vec3 uHotCore;`,
    /* glsl */ `
  vec3 sp = normalize(vObjPos);
  float r = ridged(sp * 3.5 + vec3(uTime * 0.06, 0.0, uTime * 0.04), 4);
  float crack = smoothstep(0.78, 0.88, r);
  float core = smoothstep(0.88, 0.95, r);
  float blotch = clamp(fbm(sp * 2.0, 3) * 0.5 + 0.5, 0.0, 1.0);
  vec3 crust = uCrust * (0.6 + 0.8 * blotch);
  vec3 emissive = mix(uEmber, uHotCore, core) * crack * 2.2;
  gl_FragColor = vec4(crust * (0.03 + sgShade()) + emissive, 1.0);`
  ),
  dusty: planetFragment(
    /* glsl */ `
uniform vec3 uLow;
uniform vec3 uHigh;`,
    /* glsl */ `
  vec3 sp = normalize(vObjPos);
  float blotch = clamp(fbm(sp * 3.0 + vec3(uTime * 0.01), 4) * 0.5 + 0.5, 0.0, 1.0);
  float fine = clamp(fbm(sp * 7.0 + vec3(3.7), 3) * 0.5 + 0.5, 0.0, 1.0);
  vec3 color = mix(uLow, uHigh, smoothstep(0.25, 0.75, blotch));
  color *= 0.85 + 0.3 * fine;
  gl_FragColor = vec4(color * (0.03 + sgShade()), 1.0);`
  ),
  veined: planetFragment(
    /* glsl */ `
uniform vec3 uBase;
uniform vec3 uChampagne;`,
    /* glsl */ `
  vec3 sp = normalize(vObjPos);
  float r = ridged(sp * 4.5, 4);
  float vein = smoothstep(0.82, 0.88, r);
  gl_FragColor = vec4(uBase * (0.03 + sgShade()) + uChampagne * vein * 1.6, 1.0);`
  ),
};

const RING_VERTEX = /* glsl */ `
varying vec3 vObjPos;

void main() {
  vObjPos = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const RING_FRAGMENT = /* glsl */ `
uniform float uTime;
uniform vec3 uChampagne;
uniform float uInner;
uniform float uOuter;
uniform float uReveal;
varying vec3 vObjPos;
${NOISE_GLSL}

void main() {
  float rad = length(vObjPos.xy);
  float t = clamp((rad - uInner) / (uOuter - uInner), 0.0, 1.0);
  float bands = clamp(fbm(vec3(rad * 14.0, 0.0, uTime * 0.05), 3) * 0.5 + 0.5, 0.0, 1.0);
  float edge = smoothstep(0.0, 0.12, t) * (1.0 - smoothstep(0.72, 1.0, t));
  gl_FragColor = vec4(uChampagne, bands * edge * 0.5 * uReveal);
}
`;

const colorUniform = (hex: string): THREE.IUniform<THREE.Color> => ({
  value: new THREE.Color(hex),
});

function kindColorUniforms(
  kind: PlanetSpec["kind"]
): Record<string, THREE.IUniform<THREE.Color>> {
  switch (kind) {
    case "gas":
      return {
        uDeepAmber: colorUniform(PALETTE.deepAmber),
        uChampagne: colorUniform(PALETTE.champagne),
        uCream: colorUniform(PALETTE.cream),
      };
    case "cratered":
      return { uLow: colorUniform("#4a3a2c"), uHigh: colorUniform("#8c6a4c") };
    case "molten":
      return {
        uCrust: colorUniform("#171008"),
        uEmber: colorUniform(PALETTE.ember),
        uHotCore: colorUniform(PALETTE.hotCore),
      };
    case "dusty":
      return { uLow: colorUniform("#786048"), uHigh: colorUniform("#b89a78") };
    case "veined":
      return {
        uBase: colorUniform("#1c1714"),
        uChampagne: colorUniform(PALETTE.champagne),
      };
  }
}

type PlanetRig = {
  precess: THREE.Group;
  holder: THREE.Group;
  mesh: THREE.Mesh;
  semiMajor: number;
  semiMinor: number;
  angularSpeed: number;
  phase: number;
  spinRate: number;
  precessRate: number;
};

export function Planets({
  world,
  visible,
  reveal,
}: {
  world: IntroWorld;
  visible: { value: boolean };
  reveal?: ScalarRef;
}) {
  const { root, rigs, uTime, uReveal, orbitMaterial, geometries, materials } =
    useMemo(() => {
    const sharedTime: THREE.IUniform<number> = { value: 0 };
    const sharedReveal: THREE.IUniform<number> = { value: 1 };
    const sharedSun: THREE.IUniform<THREE.Vector3> = {
      value: new THREE.Vector3(...SUN_POSITION),
    };

    const rootGroup = new THREE.Group();
    rootGroup.position.set(...SUN_POSITION);

    const orbitLineMaterial = new THREE.LineBasicMaterial({
      color: PALETTE.champagne,
      transparent: true,
      opacity: 0.06,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      fog: false,
    });

    const geometryList: THREE.BufferGeometry[] = [];
    const materialList: THREE.Material[] = [orbitLineMaterial];
    const rigList: PlanetRig[] = [];
    let ringIndex = 0;

    PLANETS.forEach((spec, index) => {
      const semiMajor = spec.orbitRadius;
      const semiMinor = spec.orbitRadius * (1 - spec.eccentricity);

      const precess = new THREE.Group();
      const incline = new THREE.Group();
      incline.rotation.x = spec.inclinationDeg * DEG2RAD;
      precess.add(incline);
      rootGroup.add(precess);

      const linePositions = new Float32Array(ORBIT_SEGMENTS * 3);
      for (let s = 0; s < ORBIT_SEGMENTS; s += 1) {
        const angle = (s / ORBIT_SEGMENTS) * Math.PI * 2;
        linePositions[s * 3] = Math.cos(angle) * semiMajor;
        linePositions[s * 3 + 1] = 0;
        linePositions[s * 3 + 2] = Math.sin(angle) * semiMinor;
      }
      const lineGeometry = new THREE.BufferGeometry();
      const lineAttribute = new THREE.BufferAttribute(linePositions, 3);
      lineAttribute.setUsage(THREE.StaticDrawUsage);
      lineGeometry.setAttribute("position", lineAttribute);
      incline.add(new THREE.LineLoop(lineGeometry, orbitLineMaterial));
      geometryList.push(lineGeometry);

      const holder = new THREE.Group();
      incline.add(holder);

      const planetGeometry = new THREE.SphereGeometry(spec.radius, 48, 32);
      const planetMaterial = new THREE.ShaderMaterial({
        vertexShader: PLANET_VERTEX,
        fragmentShader: KIND_FRAGMENTS[spec.kind],
        uniforms: {
          uTime: sharedTime,
          uSunPos: sharedSun,
          uReveal: sharedReveal,
          ...kindColorUniforms(spec.kind),
        },
      });
      const planetMesh = new THREE.Mesh(planetGeometry, planetMaterial);
      holder.add(planetMesh);
      geometryList.push(planetGeometry);
      materialList.push(planetMaterial);

      if (spec.hasRing) {
        const tilt = RING_TILTS[ringIndex % RING_TILTS.length];
        const inner = spec.radius * 1.4;
        const outer = spec.radius * 2.2;
        const ringGeometry = new THREE.RingGeometry(inner, outer, 64, 1);
        const ringMaterial = new THREE.ShaderMaterial({
          vertexShader: RING_VERTEX,
          fragmentShader: RING_FRAGMENT,
          uniforms: {
            uTime: sharedTime,
            uChampagne: colorUniform(PALETTE.champagne),
            uInner: { value: inner },
            uOuter: { value: outer },
            uReveal: sharedReveal,
          },
          transparent: true,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          side: THREE.DoubleSide,
        });
        const ringMesh = new THREE.Mesh(ringGeometry, ringMaterial);
        ringMesh.rotation.set(tilt[0], tilt[1], tilt[2]);
        holder.add(ringMesh);
        geometryList.push(ringGeometry);
        materialList.push(ringMaterial);
        ringIndex += 1;
      }

      rigList.push({
        precess,
        holder,
        mesh: planetMesh,
        semiMajor,
        semiMinor,
        angularSpeed: spec.angularSpeed,
        phase: spec.phase,
        spinRate: SPIN_RATES[index % SPIN_RATES.length],
        precessRate: PRECESS_RATES[index % PRECESS_RATES.length],
      });
    });

    return {
      root: rootGroup,
      rigs: rigList,
      uTime: sharedTime,
      uReveal: sharedReveal,
      orbitMaterial: orbitLineMaterial,
      geometries: geometryList,
      materials: materialList,
    };
  }, []);

  useEffect(() => {
    return () => {
      for (const geometry of geometries) {
        geometry.dispose();
      }
      for (const material of materials) {
        material.dispose();
      }
    };
  }, [geometries, materials]);

  useFrame(() => {
    root.visible = visible.value;
    const t = world.time.value;
    uTime.value = t;
    const r = reveal ? reveal.value : 1;
    uReveal.value = r;
    orbitMaterial.opacity = 0.06 * r;
    for (const rig of rigs) {
      rig.precess.rotation.y = t * rig.precessRate;
      const theta = rig.phase + t * rig.angularSpeed;
      rig.holder.position.set(
        Math.cos(theta) * rig.semiMajor,
        0,
        Math.sin(theta) * rig.semiMinor
      );
      rig.mesh.rotation.y = t * rig.spinRate;
    }
  });

  return <primitive object={root} />;
}
