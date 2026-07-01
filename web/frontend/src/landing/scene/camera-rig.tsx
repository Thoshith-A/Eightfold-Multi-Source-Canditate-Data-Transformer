"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { HERO_CAMERA } from "../intro/constants";

const INTRO_DURATION = 2.6;
const DOLLY_START = new THREE.Vector3(-4.2, 6.2, 14.5);
const DOLLY_END = new THREE.Vector3(...HERO_CAMERA.position);
const RIG_TARGET = new THREE.Vector3(...HERO_CAMERA.target);

/** Damped pointer-parallax state shared between rig instances. */
export type ParallaxState = { x: number; y: number };

export const createParallaxState = (): ParallaxState => ({ x: 0, y: 0 });

/** Advances the damped pointer-follow; identical constants everywhere. */
export function dampRigParallax(
  parallax: ParallaxState,
  pointerX: number,
  pointerY: number,
  delta: number
): void {
  parallax.x = THREE.MathUtils.damp(parallax.x, pointerX * 0.5, 2.2, delta);
  parallax.y = THREE.MathUtils.damp(parallax.y, pointerY * 0.28, 2.2, delta);
}

/**
 * The hero camera pose as a pure function of time + parallax state: dolly-in
 * (easeOutQuart), slow ambient drift, pointer offset, fixed look target.
 * Used by the standard CameraRig every frame AND by the intro's handoff
 * blend so the cinematic can land on the live pose with zero pop.
 */
export function computeRigPose(
  elapsedTime: number,
  parallax: ParallaxState,
  outPosition: THREE.Vector3,
  outTarget: THREE.Vector3,
  skipDolly = false
): void {
  const intro = skipDolly ? 1 : Math.min(elapsedTime / INTRO_DURATION, 1);
  const eased = 1 - Math.pow(1 - intro, 4);
  outPosition.lerpVectors(DOLLY_START, DOLLY_END, eased);
  outPosition.x += Math.sin(elapsedTime * 0.06) * 0.4 + parallax.x;
  outPosition.y += Math.cos(elapsedTime * 0.045) * 0.2 - parallax.y;
  outTarget.copy(RIG_TARGET);
}

type CameraRigProps = {
  /** "post-intro" skips the dolly so the rig continues a finished intro. */
  mode?: "standard" | "post-intro";
  /** Optional shared parallax state for seamless handoff from the intro rig. */
  parallax?: ParallaxState;
};

/**
 * Cinematic dolly-in on load (easeOutQuart), then a very slow ambient
 * drift plus damped pointer parallax. No orbit controls; all vectors are
 * allocated once and reused every frame.
 */
export function CameraRig({ mode = "standard", parallax }: CameraRigProps) {
  const pose = useMemo(
    () => ({ position: new THREE.Vector3(), target: new THREE.Vector3() }),
    []
  );
  const internalParallax = useRef<ParallaxState | null>(null);
  if (internalParallax.current === null) {
    internalParallax.current = createParallaxState();
  }
  const parallaxState = parallax ?? internalParallax.current;

  useFrame((state, delta) => {
    dampRigParallax(parallaxState, state.pointer.x, state.pointer.y, delta);
    computeRigPose(
      state.clock.elapsedTime,
      parallaxState,
      pose.position,
      pose.target,
      mode === "post-intro"
    );
    state.camera.position.copy(pose.position);
    state.camera.lookAt(pose.target);
  });

  return null;
}
