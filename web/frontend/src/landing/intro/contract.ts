import * as THREE from "three";

/**
 * The shared contract between the master timeline (which TWEENS these
 * objects) and every scene module (which READS them, usually as shader
 * uniforms). All are stable mutable references — never replaced, only
 * their `.value`s change — so GSAP can tween them and R3F never re-renders.
 */

/** Uniform-shaped scalar GSAP can tween and shaders can consume directly. */
export type ScalarRef = { value: number };

export const scalar = (value: number): ScalarRef => ({ value });

/**
 * Dilated world clock. IntroExperience advances `time` every frame by
 * `delta * timeScale.value`; ALL intro scene motion (orbits, noise, trails)
 * derives from `time` so slow-motion is global and perfectly coherent.
 */
export type IntroWorld = {
  time: ScalarRef;
  timeScale: ScalarRef;
};

/** Expanding impact shockwave; the starfield also reads this to refract. */
export type ShockState = {
  center: THREE.Vector3;
  radius: ScalarRef;
  strength: ScalarRef;
};

/** Debris lifecycle: explosion → vortex pull → condensation into the star. */
export type BlastState = {
  /** 0→1 outward blast progress (drives ballistic phase). */
  blast: ScalarRef;
  /** 0→1 curl-noise swirl strength (gravity reversal). */
  vortex: ScalarRef;
  /** 0→1 convergence of every shard onto the core position. */
  condense: ScalarRef;
  /** 0→1 global debris fade as the star ignites. */
  fade: ScalarRef;
};

/** Reveal levers for the EXISTING hero scene during [genesis]/[handoff]. */
export type RevealState = {
  /** Brand core scale: 0 → 1.06 overshoot → 1. */
  coreScale: ScalarRef;
  /** Per-ring arc draw-on, 0..1 of the full circle. */
  ringProgress: readonly [ScalarRef, ScalarRef, ScalarRef];
  /** Audience field rise-in (0 hidden below floor → 1 in place). */
  audienceReveal: ScalarRef;
  /** Studio key-light fade (spot/ambient multiplier). */
  lights: ScalarRef;
};

/** Everything the timeline drives that lives outside the scene graph. */
export type IntroDomBridge = {
  /** White flash overlay (style.opacity written directly). */
  flashEl: HTMLDivElement | null;
  /** Called as the playhead crosses each beat label. */
  onBeat: (beat: string) => void;
  /** Called once when the handoff completes — hero UI may stagger in. */
  onDone: () => void;
};

export type IntroRefs = {
  world: IntroWorld;
  shock: ShockState;
  blast: BlastState;
  reveal: RevealState;
  /** Meteor flight progress 0..1 along METEOR_PATH. */
  meteorProgress: ScalarRef;
  /** Anamorphic lens-streak intensity 0..1 (flares during omen/impact). */
  streak: ScalarRef;
  /** Nebula haze opacity (≤ 0.08). */
  nebulaOpacity: ScalarRef;
  /** Starfield master opacity (fades to ~0.12 during [void]). */
  starfieldOpacity: ScalarRef;
  /** Settling bokeh sparks intensity (genesis tail). */
  sparks: ScalarRef;
  /** Solar-system visibility flip (planets/belt/sun swap to debris). */
  systemVisible: { value: boolean };
  /** Solar-system brightness ramp: 0 at the [void] open → 1 once revealed. */
  systemReveal: ScalarRef;
};

export function createIntroRefs(): IntroRefs {
  return {
    world: { time: scalar(0), timeScale: scalar(1) },
    shock: {
      center: new THREE.Vector3(0, 2.3, 0),
      radius: scalar(0),
      strength: scalar(0),
    },
    blast: {
      blast: scalar(0),
      vortex: scalar(0),
      condense: scalar(0),
      fade: scalar(0),
    },
    reveal: {
      coreScale: scalar(0),
      ringProgress: [scalar(0), scalar(0), scalar(0)],
      audienceReveal: scalar(0),
      lights: scalar(0),
    },
    meteorProgress: scalar(0),
    streak: scalar(0),
    nebulaOpacity: scalar(0),
    starfieldOpacity: scalar(0),
    sparks: scalar(0),
    systemVisible: { value: true },
    systemReveal: scalar(0),
  };
}
