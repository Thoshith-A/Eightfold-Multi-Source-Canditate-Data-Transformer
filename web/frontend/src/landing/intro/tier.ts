import type { IntroTier } from "./constants";

const SOFTWARE_RENDERER = /swiftshader|llvmpipe|software/i;
const MOBILE_UA = /android|iphone|ipad|ipod|mobile/i;

/**
 * Device heuristic for the cinematic intro. SSR-safe: without a window it
 * reports "low" so the server never commits to the cinematic path
 * (prefers-reduced-motion is handled by the caller before this runs).
 */
export function detectTier(): IntroTier {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return "low";
  }
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    if (!gl) {
      return "low";
    }
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    if (info) {
      const renderer = String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL));
      if (SOFTWARE_RENDERER.test(renderer)) {
        return "low";
      }
    }
  } catch {
    return "low";
  }
  const cores = navigator.hardwareConcurrency ?? 8;
  if (MOBILE_UA.test(navigator.userAgent) || cores <= 4) {
    return "med";
  }
  return "high";
}
