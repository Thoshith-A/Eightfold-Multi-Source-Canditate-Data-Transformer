import { gsap } from "gsap";
import * as THREE from "three";

import {
  BEATS,
  HERO_CAMERA,
  INTRO_FOV,
  METEOR_PATH,
  PALETTE,
  POST,
  SHAKE,
  SUN_POSITION,
  TIMESCALE,
  type BeatLabel,
} from "./constants";
import type { IntroDomBridge, IntroRefs, ScalarRef } from "./contract";

/** Every timeline label, in playback order (exact BEATS keys). */
export type IntroTimelineLabel = BeatLabel;

const LABELS: readonly IntroTimelineLabel[] = [
  "void",
  "system",
  "omen",
  "impact",
  "genesis",
  "handoff",
];

/** Camera proxy the timeline tweens and IntroCameraRig applies per frame. */
export type IntroCamProxy = {
  position: THREE.Vector3;
  lookAt: THREE.Vector3;
  /** 0..1 lerp of the look target toward the live meteor head. */
  meteorBias: ScalarRef;
  fov: ScalarRef;
  /** 0..1 handoff lerp toward the live hero rig pose. */
  blend: ScalarRef;
  /** Dutch-roll kick in radians, applied after lookAt. */
  dutch: ScalarRef;
  /** Set to 1 on the hit frame; the rig consumes it and starts the shake. */
  shakeRequest: ScalarRef;
};

export type IntroFxProxy = { bloom: ScalarRef; aberration: ScalarRef };

export type IntroAtmosphereProxy = {
  background: THREE.Color;
  fogColor: THREE.Color;
  fogNear: ScalarRef;
  fogFar: ScalarRef;
};

export type IntroHeads = { meteorHead: THREE.Vector3 };

export type IntroTimelineCtx = {
  refs: IntroRefs;
  cam: IntroCamProxy;
  fx: IntroFxProxy;
  atmosphere: IntroAtmosphereProxy;
  dom: IntroDomBridge;
  heads: IntroHeads;
};

const DEG2RAD = Math.PI / 180;
const FOV_VOID = 38;
export const INTRO_FOG_START = { near: 60, far: 160 } as const;
const FOG_END = { near: 16, far: 52 } as const;

/** Where the void dolly begins (sun framed center, ~18 units out). */
const CAM_VOID_START = [-3.2, 5.2, 17.5] as const;

/**
 * [system] sweep: ~39 degrees around the sun's Y axis, dolly closing from
 * ~16.8 to ~11.3 units with a gentle height drop. Every point stays well
 * outside the outermost orbit (radius 7.5, inclined up to 9 degrees).
 */
const SYSTEM_PATH: readonly (readonly [number, number, number])[] = [
  [-2.6, 4.8, 16.4],
  [0.4, 4.3, 15.2],
  [2.9, 3.9, 13.3],
  [4.6, 3.6, 11.4],
  [5.6, 3.4, 9.7],
];

/** Off-center look target so the sun sits on a lower-left thirds line. */
const SYSTEM_LOOK = [1.1, 2.9, 0] as const;
const OMEN_PUSH = [4.9, 3.15, 8.6] as const;
const IMPACT_RECOIL = [5.9, 3.7, 10.6] as const;
const GENESIS_DRIFT = [4.0, 3.3, 10.2] as const;
const FOV_GENESIS = 33;

/**
 * Builds the ONE master timeline for the film. It is created paused; the
 * orchestrator plays it. Every tween targets shared mutable proxies or
 * ScalarRefs — never React state, never R3F-owned three objects. The build
 * also synchronously writes the frame-zero state of every proxy so the rig
 * renders a correct first frame before the first GSAP tick.
 */
export function buildIntroTimeline(ctx: IntroTimelineCtx): gsap.core.Timeline {
  const { refs, cam, fx, atmosphere, dom, heads } = ctx;

  // --- Frame-zero state (also makes strict-mode rebuilds restart cleanly).
  refs.world.time.value = 0;
  refs.world.timeScale.value = 1;
  refs.shock.center.set(SUN_POSITION[0], SUN_POSITION[1], SUN_POSITION[2]);
  refs.shock.radius.value = 0;
  refs.shock.strength.value = 0;
  refs.blast.blast.value = 0;
  refs.blast.vortex.value = 0;
  refs.blast.condense.value = 0;
  refs.blast.fade.value = 0;
  refs.reveal.coreScale.value = 0;
  for (const ring of refs.reveal.ringProgress) {
    ring.value = 0;
  }
  refs.reveal.audienceReveal.value = 0;
  refs.reveal.lights.value = 0;
  refs.meteorProgress.value = 0;
  refs.streak.value = 0;
  refs.nebulaOpacity.value = 0;
  refs.starfieldOpacity.value = 0;
  refs.sparks.value = 0;
  refs.systemVisible.value = true;
  refs.systemReveal.value = 0;
  cam.position.set(CAM_VOID_START[0], CAM_VOID_START[1], CAM_VOID_START[2]);
  cam.lookAt.set(SUN_POSITION[0], SUN_POSITION[1], SUN_POSITION[2]);
  cam.meteorBias.value = 0;
  cam.fov.value = FOV_VOID;
  cam.blend.value = 0;
  cam.dutch.value = 0;
  cam.shakeRequest.value = 0;
  fx.bloom.value = 1.2;
  fx.aberration.value = 0;
  atmosphere.background.set(PALETTE.void);
  atmosphere.fogColor.set(PALETTE.void);
  atmosphere.fogNear.value = INTRO_FOG_START.near;
  atmosphere.fogFar.value = INTRO_FOG_START.far;
  heads.meteorHead.set(METEOR_PATH.p0[0], METEOR_PATH.p0[1], METEOR_PATH.p0[2]);

  // --- Precomputed camera sweep (arc-length cache warmed once).
  const curve = new THREE.CatmullRomCurve3(
    SYSTEM_PATH.map((p) => new THREE.Vector3(p[0], p[1], p[2])),
    false,
    "centripetal"
  );
  curve.getLength();
  const sweep: ScalarRef = { value: 0 };
  const flash: ScalarRef = { value: 0 };
  const studio = new THREE.Color(PALETTE.studioVoid);
  const applyFlash = (): void => {
    const el = dom.flashEl;
    if (el) {
      el.style.opacity = flash.value.toFixed(3);
    }
  };

  const tl = gsap.timeline({ paused: true });

  for (const label of LABELS) {
    tl.addLabel(label, BEATS[label]);
    tl.call(() => dom.onBeat(label), undefined, BEATS[label]);
  }

  // ---- [void 0–0.8] black void, sky fades up, slow forward dolly.
  tl.to(refs.starfieldOpacity, { value: 0.12, duration: 0.8, ease: "sine.inOut" }, BEATS.void);
  tl.to(refs.nebulaOpacity, { value: 0.08, duration: 0.8, ease: "sine.inOut" }, BEATS.void);
  tl.to(
    cam.position,
    { x: SYSTEM_PATH[0][0], y: SYSTEM_PATH[0][1], z: SYSTEM_PATH[0][2], duration: 0.8, ease: "sine.inOut" },
    BEATS.void
  );
  // Emerge from black: the solar system is unlit at the open and brightens
  // in as the camera begins its sweep, so [void] reads as deep space.
  tl.to(refs.systemReveal, { value: 1, duration: 1.5, ease: "power2.in" }, 0.3);

  // ---- [system 0.8–2.6] CatmullRom sweep around the sun, FOV to 32.
  tl.to(
    sweep,
    {
      value: 1,
      duration: BEATS.omen - BEATS.system,
      ease: "power1.inOut",
      onUpdate: () => {
        curve.getPointAt(Math.min(Math.max(sweep.value, 0), 1), cam.position);
      },
    },
    BEATS.system
  );
  tl.to(
    cam.lookAt,
    { x: SYSTEM_LOOK[0], y: SYSTEM_LOOK[1], z: SYSTEM_LOOK[2], duration: 1.2, ease: "sine.inOut" },
    BEATS.system
  );
  tl.to(cam.fov, { value: INTRO_FOV.system, duration: 1.4, ease: "power1.inOut" }, BEATS.system);

  // ---- [omen 2.6–3.4] meteor flight, whip-pan, global slow-motion.
  tl.to(
    refs.meteorProgress,
    { value: 1, duration: BEATS.impact - BEATS.omen, ease: "power2.in" },
    BEATS.omen
  );
  tl.to(cam.meteorBias, { value: 1, duration: 0.55, ease: "power3.inOut" }, BEATS.omen);
  tl.to(cam.fov, { value: INTRO_FOV.omen, duration: 0.8, ease: "power2.inOut" }, BEATS.omen);
  tl.to(
    cam.position,
    { x: OMEN_PUSH[0], y: OMEN_PUSH[1], z: OMEN_PUSH[2], duration: 0.8, ease: "sine.inOut" },
    BEATS.omen
  );
  tl.to(refs.world.timeScale, { value: TIMESCALE.omen, duration: 0.7, ease: "power1.inOut" }, BEATS.omen);
  tl.to(refs.world.timeScale, { value: TIMESCALE.hold, duration: 0.1, ease: "power2.in" }, 3.3);
  tl.to(refs.streak, { value: 0.85, duration: 0.2, ease: "power2.in" }, 3.0);
  tl.to(refs.streak, { value: 0.3, duration: 0.15, ease: "power2.out" }, 3.2);

  // ---- [impact 3.4–3.95] the slow-mo → realtime cut IS the punch.
  tl.set(refs.world.timeScale, { value: 1 }, BEATS.impact);
  tl.set(refs.systemVisible, { value: false }, BEATS.impact);
  tl.set(refs.shock.strength, { value: 1 }, BEATS.impact);
  tl.set(cam.dutch, { value: SHAKE.dutchDeg * DEG2RAD }, BEATS.impact);
  tl.call(
    () => {
      cam.shakeRequest.value = 1;
    },
    undefined,
    BEATS.impact
  );
  tl.to(refs.blast.blast, { value: 1, duration: 0.55, ease: "power4.out" }, BEATS.impact);
  tl.to(flash, { value: 1, duration: 0.04, ease: "power1.out", onUpdate: applyFlash }, BEATS.impact);
  tl.to(flash, { value: 0, duration: 0.13, ease: "power2.in", onUpdate: applyFlash }, 3.49);
  tl.to(refs.shock.radius, { value: 30, duration: 1.1, ease: "power2.out" }, BEATS.impact);
  tl.to(refs.shock.strength, { value: 0, duration: 1.1, ease: "power1.out" }, BEATS.impact);
  tl.to(cam.dutch, { value: 0, duration: 1.0, ease: "power2.out" }, BEATS.impact);
  tl.to(
    cam.position,
    { x: IMPACT_RECOIL[0], y: IMPACT_RECOIL[1], z: IMPACT_RECOIL[2], duration: 0.6, ease: "power2.out" },
    BEATS.impact
  );
  tl.to(fx.bloom, { value: POST.bloomImpact, duration: 0.06, ease: "power1.out" }, BEATS.impact);
  tl.to(fx.bloom, { value: POST.bloomSettle, duration: 0.84, ease: "power2.inOut" }, 3.46);
  tl.to(fx.aberration, { value: POST.aberrationSpike, duration: 0.05, ease: "power1.out" }, BEATS.impact);
  tl.to(fx.aberration, { value: POST.aberrationSettle, duration: 0.95, ease: "power2.out" }, 3.45);
  tl.to(refs.streak, { value: 0, duration: 0.3, ease: "power1.out" }, 3.45);

  // ---- [genesis 3.95–5.6] vortex, condensation, star ignition, reveals.
  tl.to(refs.blast.vortex, { value: 1, duration: 0.65, ease: "power2.inOut" }, BEATS.genesis);
  tl.to(refs.blast.condense, { value: 1, duration: 1.1, ease: "power3.inOut" }, 4.25);
  tl.to(refs.blast.fade, { value: 1, duration: 0.65, ease: "power1.inOut" }, 5.05);
  tl.to(refs.reveal.coreScale, { value: 1, duration: 0.65, ease: "back.out(1.2)" }, 4.9);
  refs.reveal.ringProgress.forEach((ring, index) => {
    tl.to(ring, { value: 1, duration: 0.5, ease: "power2.inOut" }, 5.05 + index * 0.12);
  });
  tl.to(refs.sparks, { value: 0.7, duration: 0.5, ease: "sine.inOut" }, 4.7);
  tl.to(refs.sparks, { value: 0, duration: 0.5, ease: "sine.inOut" }, 5.9);
  tl.to(refs.reveal.audienceReveal, { value: 1, duration: 1.2, ease: "power2.inOut" }, 5.15);
  tl.to(refs.reveal.lights, { value: 1, duration: 1.0, ease: "sine.inOut" }, 5.2);
  tl.to(fx.bloom, { value: 2.3, duration: 0.5, ease: "sine.inOut" }, 5.3);
  tl.to(fx.bloom, { value: POST.bloomRest, duration: 0.7, ease: "sine.inOut" }, 5.8);
  tl.to(refs.nebulaOpacity, { value: 0, duration: 0.85, ease: "sine.inOut" }, 5.6);
  tl.to(refs.starfieldOpacity, { value: 0, duration: 0.85, ease: "sine.inOut" }, 5.6);
  tl.to(cam.meteorBias, { value: 0, duration: 0.4, ease: "sine.inOut" }, BEATS.genesis);
  tl.to(
    cam.position,
    { x: GENESIS_DRIFT[0], y: GENESIS_DRIFT[1], z: GENESIS_DRIFT[2], duration: 1.6, ease: "sine.inOut" },
    4.0
  );
  tl.to(cam.fov, { value: FOV_GENESIS, duration: 1.4, ease: "sine.inOut" }, BEATS.genesis);

  // ---- [handoff 5.6–6.5] atmosphere to studio + blend onto the live rig.
  tl.to(
    atmosphere.background,
    { r: studio.r, g: studio.g, b: studio.b, duration: 0.9, ease: "sine.inOut" },
    BEATS.handoff
  );
  tl.to(
    atmosphere.fogColor,
    { r: studio.r, g: studio.g, b: studio.b, duration: 0.9, ease: "sine.inOut" },
    BEATS.handoff
  );
  tl.to(atmosphere.fogNear, { value: FOG_END.near, duration: 0.9, ease: "sine.inOut" }, BEATS.handoff);
  tl.to(atmosphere.fogFar, { value: FOG_END.far, duration: 0.9, ease: "sine.inOut" }, BEATS.handoff);
  tl.to(cam.blend, { value: 1, duration: BEATS.end - BEATS.handoff, ease: "power3.inOut" }, BEATS.handoff);
  tl.to(cam.fov, { value: HERO_CAMERA.fov, duration: 0.9, ease: "power2.inOut" }, BEATS.handoff);
  tl.to(
    cam.position,
    {
      x: HERO_CAMERA.position[0],
      y: HERO_CAMERA.position[1],
      z: HERO_CAMERA.position[2],
      duration: 0.9,
      ease: "power3.inOut",
    },
    BEATS.handoff
  );
  tl.to(
    cam.lookAt,
    {
      x: HERO_CAMERA.target[0],
      y: HERO_CAMERA.target[1],
      z: HERO_CAMERA.target[2],
      duration: 0.9,
      ease: "power3.inOut",
    },
    BEATS.handoff
  );

  tl.call(dom.onDone, undefined, BEATS.end);

  return tl;
}
