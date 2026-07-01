"use client";

import { useEffect, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import { EffectComposer } from "@react-three/postprocessing";
import {
  BloomEffect,
  BlendFunction,
  ChromaticAberrationEffect,
  NoiseEffect,
  ToneMappingEffect,
  ToneMappingMode,
  VignetteEffect,
} from "postprocessing";
import * as THREE from "three";

import { POST } from "../intro/constants";
import type { ScalarRef } from "../intro/contract";

export type EffectsFx = { bloom: ScalarRef; aberration: ScalarRef };

/**
 * The composer disables the renderer's built-in tone mapping, so HDR
 * emissive values (> 1) survive into Bloom; ACES filmic is applied
 * explicitly afterwards, then chromatic aberration (zero offset at rest —
 * the intro spikes it on impact), vignette and a whisper of film grain.
 *
 * Effects are constructed imperatively and mounted via <primitive>. This is
 * deliberate: @react-three/postprocessing's wrapper components memoize on
 * JSON.stringify(props), and under React 19 a forwarded `ref` lands in those
 * props — once it resolves to the (circular) effect instance, the stringify
 * throws and crashes the tree. Owning the instances sidesteps that and lets
 * the intro mutate bloom/aberration every frame with zero re-renders.
 */
export function Effects({ fx }: { fx?: EffectsFx }) {
  const effects = useMemo(() => {
    const bloom = new BloomEffect({
      mipmapBlur: true,
      intensity: POST.bloomRest,
      luminanceThreshold: 1,
      luminanceSmoothing: 0.2,
      levels: 7,
    });
    const toneMapping = new ToneMappingEffect({ mode: ToneMappingMode.ACES_FILMIC });
    const aberration = new ChromaticAberrationEffect({
      offset: new THREE.Vector2(0, 0),
      radialModulation: false,
      modulationOffset: 0.15,
    });
    const vignette = new VignetteEffect({
      offset: POST.vignette.offset,
      darkness: POST.vignette.darkness,
    });
    const noise = new NoiseEffect({
      premultiply: true,
      blendFunction: BlendFunction.SCREEN,
    });
    noise.blendMode.opacity.value = POST.grain;
    return { bloom, toneMapping, aberration, vignette, noise };
  }, []);

  useEffect(() => {
    return () => {
      for (const effect of Object.values(effects)) {
        effect.dispose();
      }
    };
  }, [effects]);

  useFrame(() => {
    if (!fx) {
      return;
    }
    effects.bloom.intensity = fx.bloom.value;
    effects.aberration.offset.set(fx.aberration.value, fx.aberration.value * 0.6);
  });

  return (
    <EffectComposer multisampling={4}>
      <primitive object={effects.bloom} />
      <primitive object={effects.toneMapping} />
      <primitive object={effects.aberration} />
      <primitive object={effects.vignette} />
      <primitive object={effects.noise} />
    </EffectComposer>
  );
}
