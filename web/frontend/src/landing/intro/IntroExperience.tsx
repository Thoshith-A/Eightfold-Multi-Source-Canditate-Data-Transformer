"use client";

import { useEffect, useMemo, useState } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

import { CameraRig, createParallaxState } from "../scene/camera-rig";
import {
  BEATS,
  COUNTS,
  HERO_CAMERA,
  METEOR_PATH,
  PALETTE,
  SKIP_TWEEN,
  SUN_POSITION,
  type BeatLabel,
} from "./constants";
import { scalar, type IntroDomBridge, type IntroRefs } from "./contract";
import { IntroCameraRig } from "./rig/intro-camera";
import { AsteroidBelt } from "./scene/asteroid-belt";
import { DebrisField } from "./scene/debris-field";
import { LensStreak } from "./scene/lens-streak";
import { Meteor } from "./scene/meteor";
import { NebulaHaze } from "./scene/nebula";
import { Planets } from "./scene/planets";
import { Shockwave } from "./scene/shockwave";
import { SettlingSparks } from "./scene/sparks";
import { Starfield } from "./scene/starfield";
import { ProtoSun } from "./scene/sun";
import {
  buildIntroTimeline,
  INTRO_FOG_START,
  type IntroAtmosphereProxy,
  type IntroCamProxy,
  type IntroFxProxy,
  type IntroHeads,
} from "./timeline";

/** The DOM-side contract plus the skip hook hero.tsx registers into. */
export type IntroBridge = IntroDomBridge & {
  registerSkip: (fn: () => void) => void;
};

type IntroExperienceProps = {
  bridge: IntroBridge;
  tier: "high" | "med";
  refs: IntroRefs;
  fx: IntroFxProxy;
};

const TEARDOWN_DELAY_MS = 600;
const MAX_DELTA = 1 / 30;
const SCRUB_LABELS: readonly BeatLabel[] = [
  "void",
  "system",
  "omen",
  "impact",
  "genesis",
  "handoff",
];

/** Reads ?introT=<seconds> once (dev scrub for screenshots). */
function readScrubTime(): number | null {
  const raw = new URLSearchParams(window.location.search).get("introT");
  if (raw === null) {
    return null;
  }
  const t = Number.parseFloat(raw);
  return Number.isFinite(t) ? Math.min(Math.max(t, 0), BEATS.end) : null;
}

/**
 * The cinematic orchestrator inside the Canvas: owns the world clock, the
 * camera/atmosphere proxies and the master timeline; renders every
 * intro-only node and unmounts them ~0.6s after the handoff completes,
 * swapping the intro rig for the standard rig (mode "post-intro").
 */
export function IntroExperience({ bridge, tier, refs, fx }: IntroExperienceProps) {
  const scene = useThree((state) => state.scene);
  const [phase, setPhase] = useState<"cinematic" | "done">("cinematic");

  const shared = useMemo(() => {
    const cam: IntroCamProxy = {
      position: new THREE.Vector3(),
      lookAt: new THREE.Vector3(SUN_POSITION[0], SUN_POSITION[1], SUN_POSITION[2]),
      meteorBias: scalar(0),
      fov: scalar(HERO_CAMERA.fov),
      blend: scalar(0),
      dutch: scalar(0),
      shakeRequest: scalar(0),
    };
    const atmosphere: IntroAtmosphereProxy = {
      background: new THREE.Color(PALETTE.void),
      fogColor: new THREE.Color(PALETTE.void),
      fogNear: scalar(INTRO_FOG_START.near),
      fogFar: scalar(INTRO_FOG_START.far),
    };
    const heads: IntroHeads = {
      meteorHead: new THREE.Vector3(METEOR_PATH.p0[0], METEOR_PATH.p0[1], METEOR_PATH.p0[2]),
    };
    const fog = new THREE.Fog(PALETTE.void, INTRO_FOG_START.near, INTRO_FOG_START.far);
    fog.color = atmosphere.fogColor;
    return { cam, atmosphere, heads, fog, parallax: createParallaxState() };
  }, []);

  // The intro owns the scene atmosphere (StudioEnvironment has
  // manageAtmosphere = false); the final studio values persist after done.
  useEffect(() => {
    const previousBackground = scene.background;
    const previousFog = scene.fog;
    scene.background = shared.atmosphere.background;
    scene.fog = shared.fog;
    return () => {
      scene.background = previousBackground;
      scene.fog = previousFog;
    };
  }, [scene, shared]);

  useEffect(() => {
    let teardownId = 0;
    let skipped = false;
    let done = false;

    const dom: IntroDomBridge = {
      get flashEl() {
        return bridge.flashEl;
      },
      onBeat: (beat: string) => bridge.onBeat(beat),
      onDone: () => {
        if (done) {
          return;
        }
        done = true;
        bridge.onDone();
        teardownId = window.setTimeout(() => setPhase("done"), TEARDOWN_DELAY_MS);
      },
    };

    const tl = buildIntroTimeline({
      refs,
      cam: shared.cam,
      fx,
      atmosphere: shared.atmosphere,
      dom,
      heads: shared.heads,
    });

    const scrubTime = readScrubTime();
    if (scrubTime !== null) {
      // Dev scrub: park the playhead (zero-duration sets still render),
      // replay beat callbacks manually, never auto-play.
      tl.pause(scrubTime);
      refs.world.time.value = scrubTime;
      for (const label of SCRUB_LABELS) {
        if (BEATS[label] <= scrubTime) {
          dom.onBeat(label);
        }
      }
      if (scrubTime >= BEATS.end - 0.05) {
        dom.onDone();
      }
    } else {
      tl.play(0);
    }

    bridge.registerSkip(() => {
      if (skipped || done || scrubTime !== null) {
        return;
      }
      skipped = true;
      tl.tweenTo("handoff", {
        duration: SKIP_TWEEN,
        ease: "power2.inOut",
        onComplete: () => tl.play(),
      });
    });

    const onVisibility = (): void => {
      if (done || skipped || scrubTime !== null) {
        return;
      }
      if (document.hidden) {
        tl.pause();
      } else {
        tl.play();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.clearTimeout(teardownId);
      tl.kill();
    };
  }, [bridge, refs, fx, shared]);

  useFrame((_, delta) => {
    refs.world.time.value += Math.min(delta, MAX_DELTA) * refs.world.timeScale.value;
    shared.fog.near = shared.atmosphere.fogNear.value;
    shared.fog.far = shared.atmosphere.fogFar.value;
  });

  if (phase === "done") {
    return <CameraRig mode="post-intro" parallax={shared.parallax} />;
  }

  const counts = COUNTS[tier];
  return (
    <>
      <Starfield
        world={refs.world}
        shock={refs.shock}
        opacity={refs.starfieldOpacity}
        count={counts.starfield}
      />
      <NebulaHaze world={refs.world} opacity={refs.nebulaOpacity} />
      <ProtoSun world={refs.world} visible={refs.systemVisible} reveal={refs.systemReveal} />
      <Planets world={refs.world} visible={refs.systemVisible} reveal={refs.systemReveal} />
      <AsteroidBelt
        world={refs.world}
        visible={refs.systemVisible}
        reveal={refs.systemReveal}
        count={counts.belt}
      />
      <Meteor
        world={refs.world}
        progress={refs.meteorProgress}
        trailCount={counts.trail}
        headOut={shared.heads.meteorHead}
      />
      <Shockwave shock={refs.shock} />
      <DebrisField world={refs.world} blast={refs.blast} count={counts.debris} />
      <LensStreak intensity={refs.streak} anchor={shared.heads.meteorHead} />
      <SettlingSparks world={refs.world} intensity={refs.sparks} />
      <IntroCameraRig cam={shared.cam} heads={shared.heads} parallax={shared.parallax} />
    </>
  );
}
