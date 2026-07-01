"use client";

import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { PALETTE } from "../constants";
import type { ShockState } from "../contract";

const VERTEX = /* glsl */ `
varying vec2 vUv;

void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

/**
 * Radial ring: a crisp-but-soft band at the rim (white-hot HDR 3.5 inner
 * edge falling to champagne) over a faint interior haze that drops to
 * near-black just inside the band, suggesting refraction.
 */
const FRAGMENT = /* glsl */ `
uniform float uStrength;
uniform vec3 uChampagne;
varying vec2 vUv;

void main() {
  float d = length(vUv - 0.5) * 2.0;
  float band = smoothstep(0.925, 0.952, d) * (1.0 - smoothstep(0.958, 0.988, d));
  float bandT = clamp((d - 0.925) / 0.063, 0.0, 1.0);
  vec3 rim = mix(vec3(3.5), uChampagne * 1.25, bandT);
  float haze = smoothstep(0.08, 0.5, d) * (1.0 - smoothstep(0.55, 0.88, d));
  vec3 col = rim * band + uChampagne * haze * 0.06;
  float alpha = (band + haze * 0.3) * uStrength;
  gl_FragColor = vec4(col, alpha);
}
`;

export function Shockwave({ shock }: { shock: ShockState }) {
  const { mesh, geometry, material, uniforms } = useMemo(() => {
    const ringUniforms = {
      uStrength: { value: 0 },
      uChampagne: { value: new THREE.Color(PALETTE.champagne) },
    };
    const ringGeometry = new THREE.CircleGeometry(1, 64);
    const ringMaterial = new THREE.ShaderMaterial({
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      uniforms: ringUniforms,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
    });
    const ringMesh = new THREE.Mesh(ringGeometry, ringMaterial);
    ringMesh.frustumCulled = false;
    ringMesh.visible = false;
    return {
      mesh: ringMesh,
      geometry: ringGeometry,
      material: ringMaterial,
      uniforms: ringUniforms,
    };
  }, []);

  useEffect(() => {
    return () => {
      geometry.dispose();
      material.dispose();
    };
  }, [geometry, material]);

  useFrame((state) => {
    const visible = shock.radius.value > 0.01 && shock.strength.value > 0.01;
    mesh.visible = visible;
    if (!visible) return;
    mesh.position.copy(shock.center);
    mesh.scale.setScalar(shock.radius.value);
    mesh.quaternion.copy(state.camera.quaternion);
    uniforms.uStrength.value = shock.strength.value;
  });

  return <primitive object={mesh} />;
}
