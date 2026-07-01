/**
 * Shared GLSL noise library for the intro — the single include every intro
 * shader builds on (simplex, FBM, ridged, cellular, curl). Embedded as a
 * string so no loader config is needed. Simplex implementation after
 * Ashima Arts / Stefan Gustavson (MIT).
 */

export const NOISE_GLSL = /* glsl */ `
vec3 sg_mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 sg_mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 sg_permute(vec4 x) { return sg_mod289(((x * 34.0) + 10.0) * x); }
vec4 sg_taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);

  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);

  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);

  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;

  i = sg_mod289(i);
  vec4 p = sg_permute(sg_permute(sg_permute(
      i.z + vec4(0.0, i1.z, i2.z, 1.0))
    + i.y + vec4(0.0, i1.y, i2.y, 1.0))
    + i.x + vec4(0.0, i1.x, i2.x, 1.0));

  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;

  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);

  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);

  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);

  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);

  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));

  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;

  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);

  vec4 norm = sg_taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x;
  p1 *= norm.y;
  p2 *= norm.z;
  p3 *= norm.w;

  vec4 m = max(0.5 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 105.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}

float fbm(vec3 p, int octaves) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 8; i++) {
    if (i >= octaves) break;
    value += amplitude * snoise(p);
    p = p * 2.02 + vec3(13.7, 7.3, 5.1);
    amplitude *= 0.5;
  }
  return value;
}

float ridged(vec3 p, int octaves) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 8; i++) {
    if (i >= octaves) break;
    value += amplitude * (1.0 - abs(snoise(p)));
    p = p * 2.07 + vec3(3.1, 17.7, 9.2);
    amplitude *= 0.5;
  }
  return value;
}

vec3 sg_cellHash(vec3 p) {
  p = vec3(dot(p, vec3(127.1, 311.7, 74.7)),
           dot(p, vec3(269.5, 183.3, 246.1)),
           dot(p, vec3(113.5, 271.9, 124.6)));
  return fract(sin(p) * 43758.5453123);
}

float cellular(vec3 p) {
  vec3 base = floor(p);
  vec3 frac = fract(p);
  float minDist = 1.0;
  for (int x = -1; x <= 1; x++) {
    for (int y = -1; y <= 1; y++) {
      for (int z = -1; z <= 1; z++) {
        vec3 cell = vec3(float(x), float(y), float(z));
        vec3 point = sg_cellHash(base + cell) * 0.5 + 0.25;
        minDist = min(minDist, length(cell + point - frac));
      }
    }
  }
  return minDist;
}

vec3 curlNoise(vec3 p) {
  const float e = 0.1;
  float nx1 = snoise(p + vec3(0.0, e, 0.0));
  float nx2 = snoise(p - vec3(0.0, e, 0.0));
  float ny1 = snoise(p + vec3(0.0, 0.0, e));
  float ny2 = snoise(p - vec3(0.0, 0.0, e));
  float nz1 = snoise(p + vec3(e, 0.0, 0.0));
  float nz2 = snoise(p - vec3(e, 0.0, 0.0));
  float x = (nx1 - nx2) - (snoise(p + vec3(0.0, 0.0, e) + 31.4) - snoise(p - vec3(0.0, 0.0, e) + 31.4));
  float y = (ny1 - ny2) - (snoise(p + vec3(e, 0.0, 0.0) + 57.1) - snoise(p - vec3(e, 0.0, 0.0) + 57.1));
  float z = (nz1 - nz2) - (snoise(p + vec3(0.0, e, 0.0) + 12.9) - snoise(p - vec3(0.0, e, 0.0) + 12.9));
  return normalize(vec3(x, y, z) / (2.0 * e) + 1e-6);
}
`;
