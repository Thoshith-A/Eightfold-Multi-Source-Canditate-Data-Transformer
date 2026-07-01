"use client";

import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { PALETTE } from "../constants";
import type { IntroWorld, ScalarRef } from "../contract";
import { NOISE_GLSL } from "../shaders/noise";

const PLANE_SIZE = [140, 90] as const;
const PLANE_POSITION = [0, 6, -55] as const;

const VERTEX = /* glsl */ `
varying vec2 vUv;

void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

/**
 * Domain-warped FBM haze: the sample point drifts on the dilated clock and
 * is warped by a second FBM pass, ramping deep amber into ember at the
 * brightest wisps. A slow sine "breathing" rides on the master opacity,
 * and a UV-edge falloff hides the plane's rectangular silhouette.
 */
const FRAGMENT = /* glsl */ `
uniform float uTime;
uniform float uOpacity;
uniform vec3 uDeepAmber;
uniform vec3 uEmber;
varying vec2 vUv;

${NOISE_GLSL}

void main() {
  vec3 p = vec3(vUv * vec2(3.4, 2.2), uTime * 0.02);
  vec3 warp = vec3(
    fbm(p + vec3(2.7, 11.4, 0.0), 3),
    fbm(p + vec3(9.1, 4.3, 0.0), 3),
    0.0
  );
  float haze = fbm(p + warp * 1.4, 4);
  haze = smoothstep(-0.1, 0.9, haze);

  vec2 edge = vUv * (1.0 - vUv);
  float falloff = smoothstep(0.0, 0.09, edge.x) * smoothstep(0.0, 0.12, edge.y);

  float breathe = 0.85 + 0.15 * sin(uTime * 0.07);
  vec3 color = mix(uDeepAmber * 0.55, uEmber, haze * haze);
  float alpha = haze * falloff * breathe * uOpacity;
  gl_FragColor = vec4(color, alpha);
}
`;

export function NebulaHaze({ world, opacity }: { world: IntroWorld; opacity: ScalarRef }) {
  const { mesh, geometry, material, uniforms } = useMemo(() => {
    const hazeUniforms = {
      uTime: { value: 0 },
      uOpacity: { value: 0 },
      uDeepAmber: { value: new THREE.Color(PALETTE.deepAmber) },
      uEmber: { value: new THREE.Color(PALETTE.ember) },
    };

    const hazeGeometry = new THREE.PlaneGeometry(PLANE_SIZE[0], PLANE_SIZE[1]);
    const hazeMaterial = new THREE.ShaderMaterial({
      uniforms: hazeUniforms,
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const hazeMesh = new THREE.Mesh(hazeGeometry, hazeMaterial);
    hazeMesh.position.set(PLANE_POSITION[0], PLANE_POSITION[1], PLANE_POSITION[2]);
    hazeMesh.frustumCulled = false;
    hazeMesh.renderOrder = -9;

    return {
      mesh: hazeMesh,
      geometry: hazeGeometry,
      material: hazeMaterial,
      uniforms: hazeUniforms,
    };
  }, []);

  useEffect(() => {
    return () => {
      geometry.dispose();
      material.dispose();
    };
  }, [geometry, material]);

  useFrame(() => {
    mesh.visible = opacity.value > 0.0005;
    uniforms.uTime.value = world.time.value;
    uniforms.uOpacity.value = opacity.value;
  });

  return <primitive object={mesh} />;
}
