"use client";

import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { PALETTE } from "../constants";
import type { ScalarRef } from "../contract";

/**
 * Paints the anamorphic bar once: a very wide thin horizontal gradient
 * (white-hot center line → champagne → transparent) multiplied by a soft
 * vertical falloff via destination-in compositing.
 */
function paintStreak(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const horizontal = ctx.createLinearGradient(0, 0, 512, 0);
    horizontal.addColorStop(0, `${PALETTE.champagne}00`);
    horizontal.addColorStop(0.16, `${PALETTE.champagne}38`);
    horizontal.addColorStop(0.4, `${PALETTE.hotCore}c8`);
    horizontal.addColorStop(0.5, PALETTE.white);
    horizontal.addColorStop(0.6, `${PALETTE.hotCore}c8`);
    horizontal.addColorStop(0.84, `${PALETTE.champagne}38`);
    horizontal.addColorStop(1, `${PALETTE.champagne}00`);
    ctx.fillStyle = horizontal;
    ctx.fillRect(0, 0, 512, 64);

    const vertical = ctx.createLinearGradient(0, 0, 0, 64);
    vertical.addColorStop(0, "rgba(0, 0, 0, 0)");
    vertical.addColorStop(0.5, "rgba(0, 0, 0, 1)");
    vertical.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.globalCompositeOperation = "destination-in";
    ctx.fillStyle = vertical;
    ctx.fillRect(0, 0, 512, 64);
  }
  return canvas;
}

export function LensStreak({
  intensity,
  anchor,
}: {
  intensity: ScalarRef;
  anchor: THREE.Vector3;
}) {
  const { sprite, material, texture } = useMemo(() => {
    const streakTexture = new THREE.CanvasTexture(paintStreak());
    streakTexture.colorSpace = THREE.SRGBColorSpace;
    const streakMaterial = new THREE.SpriteMaterial({
      map: streakTexture,
      transparent: true,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
      opacity: 0,
    });
    // HDR push so the white-hot center line crosses the bloom threshold.
    streakMaterial.color.setScalar(2.2);
    const streakSprite = new THREE.Sprite(streakMaterial);
    streakSprite.renderOrder = 50;
    streakSprite.frustumCulled = false;
    streakSprite.visible = false;
    streakSprite.scale.set(13, 0.55, 1);
    return { sprite: streakSprite, material: streakMaterial, texture: streakTexture };
  }, []);

  useEffect(() => {
    return () => {
      texture.dispose();
      material.dispose();
    };
  }, [texture, material]);

  useFrame(() => {
    const value = intensity.value;
    const visible = value > 0.001;
    sprite.visible = visible;
    if (!visible) return;
    sprite.position.copy(anchor);
    sprite.scale.set(13 * (0.9 + value * 0.25), 0.55, 1);
    material.opacity = value * 0.9;
  });

  return <primitive object={sprite} />;
}
