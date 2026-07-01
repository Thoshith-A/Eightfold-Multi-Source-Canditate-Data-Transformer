"use client";

import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { PALETTE, SUN_POSITION, SUN_RADIUS } from "../constants";
import type { IntroWorld, ScalarRef } from "../contract";
import { NOISE_GLSL } from "../shaders/noise";

const GLOW_SIZE = 256;
const GLOW_SCALE = 6.5;
const GLOW_OPACITY = 0.55;

const SUN_VERTEX = /* glsl */ `
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
 * Boiling photosphere: 4-octave fbm granulation over a slowly rotating
 * sample domain, ramped deepAmber -> ember -> hotCore with the hottest 15%
 * pushed to HDR (~2.8x) so the granules bloom, plus a champagne fresnel
 * corona at the limb (~2.0 HDR).
 */
const SUN_FRAGMENT = /* glsl */ `
uniform float uTime;
uniform vec3 uDeepAmber;
uniform vec3 uEmber;
uniform vec3 uHotCore;
uniform vec3 uChampagne;
uniform float uReveal;
varying vec3 vObjPos;
varying vec3 vWorldPos;
varying vec3 vWorldNormal;
${NOISE_GLSL}

void main() {
  float spin = uTime * 0.04;
  float c = cos(spin);
  float s = sin(spin);
  vec3 p = vObjPos * 2.2;
  p = vec3(c * p.x - s * p.z, p.y, s * p.x + c * p.z);
  p += vec3(uTime * 0.05, uTime * 0.03, 0.0);
  float n = clamp(fbm(p, 4) * 0.5 + 0.5, 0.0, 1.0);

  vec3 color = mix(uDeepAmber, uEmber, smoothstep(0.18, 0.55, n));
  color = mix(color, uHotCore, smoothstep(0.55, 0.82, n));
  color *= 1.0 + smoothstep(0.85, 1.0, n) * 1.8;

  vec3 viewDir = normalize(cameraPosition - vWorldPos);
  vec3 worldNormal = normalize(vWorldNormal);
  float rim = pow(1.0 - clamp(dot(viewDir, worldNormal), 0.0, 1.0), 2.5);
  color += mix(uChampagne, uHotCore, rim) * rim * 2.0;

  gl_FragColor = vec4(color * uReveal, 1.0);
}
`;

/** Raw hex -> rgba string (bypasses THREE.Color so no working-space shift). */
function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Soft radial halo, painted at runtime — no image assets. */
function makeGlowTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = GLOW_SIZE;
  canvas.height = GLOW_SIZE;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const half = GLOW_SIZE / 2;
    const gradient = ctx.createRadialGradient(half, half, 0, half, half, half);
    gradient.addColorStop(0, hexToRgba(PALETTE.hotCore, 1));
    gradient.addColorStop(0.22, hexToRgba(PALETTE.champagne, 0.5));
    gradient.addColorStop(0.55, hexToRgba(PALETTE.champagne, 0.12));
    gradient.addColorStop(1, hexToRgba(PALETTE.champagne, 0));
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, GLOW_SIZE, GLOW_SIZE);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export function ProtoSun({
  world,
  visible,
  reveal,
}: {
  world: IntroWorld;
  visible: { value: boolean };
  reveal?: ScalarRef;
}) {
  const { group, geometry, material, glowMaterial, glowTexture, uniforms } =
    useMemo(() => {
      const sunUniforms = {
        uTime: { value: 0 },
        uDeepAmber: { value: new THREE.Color(PALETTE.deepAmber) },
        uEmber: { value: new THREE.Color(PALETTE.ember) },
        uHotCore: { value: new THREE.Color(PALETTE.hotCore) },
        uChampagne: { value: new THREE.Color(PALETTE.champagne) },
        uReveal: { value: 1 },
      };

      const sunGeometry = new THREE.SphereGeometry(SUN_RADIUS, 96, 64);
      const sunMaterial = new THREE.ShaderMaterial({
        vertexShader: SUN_VERTEX,
        fragmentShader: SUN_FRAGMENT,
        uniforms: sunUniforms,
      });
      const sunMesh = new THREE.Mesh(sunGeometry, sunMaterial);

      const texture = makeGlowTexture();
      const spriteMaterial = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        opacity: GLOW_OPACITY,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        fog: false,
      });
      const glow = new THREE.Sprite(spriteMaterial);
      glow.scale.set(GLOW_SCALE, GLOW_SCALE, 1);

      const sunGroup = new THREE.Group();
      sunGroup.position.set(...SUN_POSITION);
      sunGroup.add(sunMesh);
      sunGroup.add(glow);

      return {
        group: sunGroup,
        geometry: sunGeometry,
        material: sunMaterial,
        glowMaterial: spriteMaterial,
        glowTexture: texture,
        uniforms: sunUniforms,
      };
    }, []);

  useEffect(() => {
    return () => {
      geometry.dispose();
      material.dispose();
      glowMaterial.dispose();
      glowTexture.dispose();
    };
  }, [geometry, material, glowMaterial, glowTexture]);

  useFrame(() => {
    group.visible = visible.value;
    uniforms.uTime.value = world.time.value;
    const r = reveal ? reveal.value : 1;
    uniforms.uReveal.value = r;
    glowMaterial.opacity = GLOW_OPACITY * r;
  });

  return <primitive object={group} />;
}
