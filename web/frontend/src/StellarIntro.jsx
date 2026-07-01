import React, { useEffect, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";

import { createIntroRefs, scalar } from "./landing/intro/contract";
import { IntroExperience } from "./landing/intro/IntroExperience";
import { detectTier } from "./landing/intro/tier";
import { Effects } from "./landing/scene/effects";

// "Stellar Genesis" opening film, lifted from the CRM landing page. The intro
// plays the cinematic (void → solar system → meteor → impact → genesis flash)
// full-screen over the app, then fades to reveal the transformer UI. The Next
// / motion / audio harness that wrapped it in the CRM is replaced by this
// small host: it owns the <Canvas>, the DOM bridge the timeline writes into,
// and the reveal. Autoplays on load — no "Begin" gate, since we run silent.

/** WebGL + reduced-motion gate. On a "no" the film never mounts. */
function canPlayIntro() {
  if (typeof window === "undefined") return false;
  try {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      return false;
    }
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

/**
 * A WebGL failure inside the Canvas must never take the page down — the app
 * lives underneath this overlay. On any render error we simply drop the film.
 */
class IntroBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError?.();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export default function StellarIntro() {
  // Resolve capability + tier exactly once, before the first paint.
  const [plan] = useState(() => {
    if (!canPlayIntro()) return { play: false, tier: null };
    const tier = detectTier();
    return tier === "low" ? { play: false, tier: null } : { play: true, tier };
  });

  // Shared cinematic state — created once, mutated by the timeline every frame.
  const [cine] = useState(() =>
    plan.play
      ? { refs: createIntroRefs(), fx: { bloom: scalar(1.2), aberration: scalar(0) } }
      : null
  );

  // "playing" → film on screen · "fading" → reveal in progress · "off" → gone.
  const [phase, setPhase] = useState(plan.play ? "playing" : "off");
  const [skipVisible, setSkipVisible] = useState(false);

  const flashRef = useRef(null);
  const skipFnRef = useRef(null);

  // The bridge the timeline writes into (flash overlay, beat/done callbacks).
  const bridgeRef = useRef(null);
  if (bridgeRef.current === null) {
    bridgeRef.current = {
      get flashEl() {
        return flashRef.current;
      },
      onBeat: (beat) => {
        // The void → system boundary is where the skip affordance earns its place.
        if (beat === "system") setSkipVisible(true);
      },
      onDone: () => setPhase("fading"),
      registerSkip: (fn) => {
        skipFnRef.current = fn;
      },
    };
  }

  // Once the film ends, fade the overlay out and then unmount the Canvas.
  useEffect(() => {
    if (phase !== "fading") return undefined;
    const id = window.setTimeout(() => setPhase("off"), 950);
    return () => window.clearTimeout(id);
  }, [phase]);

  // Lock scroll while the film owns the viewport.
  useEffect(() => {
    if (phase === "off") return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [phase]);

  const triggerSkip = () => {
    skipFnRef.current?.();
    setSkipVisible(false);
  };

  // Enter / Esc fast-forward to the handoff.
  useEffect(() => {
    if (phase !== "playing") return undefined;
    const onKey = (event) => {
      if (event.key === "Enter" || event.key === "Escape") triggerSkip();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase]);

  if (phase === "off" || !cine) return null;

  return (
    <div className={`stellar-intro${phase === "fading" ? " fading" : ""}`} aria-hidden="true">
      <IntroBoundary onError={() => setPhase("off")}>
        <Canvas
          dpr={[1, 1.75]}
          gl={{ antialias: true, powerPreference: "high-performance" }}
          camera={{ fov: 35, near: 0.5, far: 90, position: [-4.2, 6.2, 14.5] }}
        >
          <Effects fx={cine.fx} />
          <IntroExperience
            bridge={bridgeRef.current}
            tier={plan.tier}
            refs={cine.refs}
            fx={cine.fx}
          />
        </Canvas>
      </IntroBoundary>

      {/* White impact flash — the timeline writes style.opacity directly. */}
      <div ref={flashRef} className="stellar-flash" />

      <button
        type="button"
        onClick={triggerSkip}
        className={`stellar-skip${skipVisible && phase === "playing" ? " show" : ""}`}
      >
        Skip ⏎
      </button>
    </div>
  );
}
