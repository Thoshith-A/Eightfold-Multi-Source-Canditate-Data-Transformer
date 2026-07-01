"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import {
  computeRigPose,
  dampRigParallax,
  type ParallaxState,
} from "../../scene/camera-rig";
import { HERO_CAMERA, SHAKE } from "../constants";
import type { IntroCamProxy, IntroHeads } from "../timeline";

/** Deterministic PRNG so the shake phases are stable across mounts. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Incommensurate shake frequencies (Hz-ish) so the sum never loops. */
const SHAKE_FREQ = [13.7, 17.3, 23.9, 29.1, 11.3] as const;
const SHAKE_CUTOFF = 0.0005;

type IntroCameraRigProps = {
  cam: IntroCamProxy;
  heads: IntroHeads;
  parallax: ParallaxState;
};

/**
 * Applies the timeline-authored camera proxies to the real camera every
 * frame: position, blended look target (sun → meteor head), layered
 * decaying sine shake, dutch roll, FOV. During [handoff] it lerps toward
 * the live hero pose (computeRigPose) so blend = 1 is mathematically the
 * standard rig — zero pop when CameraRig takes over.
 */
export function IntroCameraRig({ cam, heads, parallax }: IntroCameraRigProps) {
  const temp = useMemo(() => {
    const rand = mulberry32(0xc1ae_5a17);
    return {
      target: new THREE.Vector3(),
      livePos: new THREE.Vector3(),
      liveTarget: new THREE.Vector3(),
      phases: [
        rand() * Math.PI * 2,
        rand() * Math.PI * 2,
        rand() * Math.PI * 2,
        rand() * Math.PI * 2,
        rand() * Math.PI * 2,
      ] as const,
    };
  }, []);
  const shakeStart = useRef(-1);
  const lastFov = useRef(-1);

  useFrame((state, delta) => {
    const camera = state.camera as THREE.PerspectiveCamera;
    const t = state.clock.elapsedTime;
    const { phases } = temp;

    dampRigParallax(parallax, state.pointer.x, state.pointer.y, delta);

    if (cam.shakeRequest.value > 0.5) {
      shakeStart.current = t;
      cam.shakeRequest.value = 0;
    }

    // Timeline-authored pose.
    camera.position.copy(cam.position);
    temp.target.copy(cam.lookAt);
    const bias = cam.meteorBias.value;
    if (bias > 0) {
      temp.target.lerp(heads.meteorHead, bias);
    }
    let fov = cam.fov.value;

    // Handoff blend toward the live hero rig pose.
    const blend = cam.blend.value;
    if (blend > 0) {
      computeRigPose(t, parallax, temp.livePos, temp.liveTarget, true);
      camera.position.lerp(temp.livePos, blend);
      temp.target.lerp(temp.liveTarget, blend);
      fov += (HERO_CAMERA.fov - fov) * blend;
    }

    // Impact shake: 3 incommensurate sines per axis, exponential decay,
    // faded out by the handoff blend so blend = 1 stays exact.
    if (shakeStart.current >= 0) {
      const age = t - shakeStart.current;
      const amp =
        SHAKE.amplitude * Math.exp(-age / SHAKE.decay) * (1 - blend);
      if (amp > SHAKE_CUTOFF) {
        camera.position.x +=
          (Math.sin(t * SHAKE_FREQ[0] + phases[0]) * 0.5 +
            Math.sin(t * SHAKE_FREQ[2] + phases[2]) * 0.3) *
          amp;
        camera.position.y +=
          (Math.sin(t * SHAKE_FREQ[1] + phases[1]) * 0.5 +
            Math.sin(t * SHAKE_FREQ[3] + phases[3]) * 0.25) *
          amp;
        camera.position.z += Math.sin(t * SHAKE_FREQ[4] + phases[4]) * 0.2 * amp;
      } else {
        shakeStart.current = -1;
      }
    }

    camera.lookAt(temp.target);
    if (cam.dutch.value !== 0) {
      camera.rotation.z += cam.dutch.value;
    }

    if (fov !== lastFov.current) {
      camera.fov = fov;
      camera.updateProjectionMatrix();
      lastFov.current = fov;
    }
  });

  return null;
}
