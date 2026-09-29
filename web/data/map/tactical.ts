/**
 * Hand-authored tactical illustration on the real Canyon reference (normalized coordinates).
 * Placed relative to the repo's fixed anchors: blue side = bottom-left base; clash lane = top-left lane by the
 * Overlord, farm lane = bottom-right lane by the Tyrant. Not match tracking.
 */
import type { Position } from "@/data/teamPresentation";
import { anchor, type TrackingPoint } from "@/lib/mapProjection";

export type TacticalState = "early" | "objective" | "teamfight";
export const STATES: TacticalState[] = ["early", "objective", "teamfight"];

type Pt = [number, number];

export const ROLE_COLOR: Record<Position, string> = {
  clash: "#ff9f43",
  jungle: "#43d49a",
  mid: "#b58cff",
  farm: "#ffd166",
  roam: "#4ac6ff",
};

/** Area each role is responsible for, as a thick stroke along lanes / jungle routes. */
export const ROLE_ZONE: Record<Position, Pt[]> = {
  clash: [[0.12, 0.74], [0.12, 0.13], [0.16, 0.07], [0.42, 0.065]],
  jungle: [[0.24, 0.3], [0.21, 0.45], [0.31, 0.46], [0.27, 0.56], [0.39, 0.735], [0.52, 0.73], [0.48, 0.64]],
  mid: [[0.24, 0.76], [0.62, 0.38]],
  farm: [[0.3, 0.885], [0.84, 0.885], [0.875, 0.85], [0.875, 0.6]],
  roam: [[0.26, 0.8], [0.45, 0.7], [0.63, 0.67], [0.72, 0.82]],
};

/** Keyframes: 0 = spawn, then one per state. */
export const KEYFRAMES: Record<Position, Pt>[] = [
  { clash: [0.16, 0.8], jungle: [0.2, 0.79], mid: [0.19, 0.83], farm: [0.17, 0.86], roam: [0.14, 0.83] },
  { clash: [0.12, 0.22], jungle: [0.31, 0.47], mid: [0.46, 0.51], farm: [0.75, 0.885], roam: [0.71, 0.855] },
  { clash: [0.2, 0.4], jungle: [0.56, 0.7], mid: [0.52, 0.6], farm: [0.62, 0.78], roam: [0.6, 0.62] },
  { clash: [0.6, 0.62], jungle: [0.65, 0.64], mid: [0.56, 0.71], farm: [0.53, 0.76], roam: [0.62, 0.7] },
];

/** Example route into each keyframe (first point = previous keyframe). */
export const ROUTES: Record<Position, Pt[]>[] = [
  { clash: [], jungle: [], mid: [], farm: [], roam: [] },
  {
    clash: [[0.16, 0.8], [0.12, 0.7], [0.12, 0.4], [0.12, 0.22]],
    jungle: [[0.2, 0.79], [0.24, 0.62], [0.31, 0.47]],
    mid: [[0.19, 0.83], [0.3, 0.68], [0.46, 0.51]],
    farm: [[0.17, 0.86], [0.35, 0.885], [0.75, 0.885]],
    roam: [[0.14, 0.83], [0.4, 0.86], [0.71, 0.855]],
  },
  {
    clash: [[0.12, 0.22], [0.13, 0.32], [0.2, 0.4]],
    jungle: [[0.31, 0.47], [0.39, 0.735], [0.56, 0.7]],
    mid: [[0.46, 0.51], [0.5, 0.56], [0.52, 0.6]],
    farm: [[0.75, 0.885], [0.66, 0.84], [0.62, 0.78]],
    roam: [[0.71, 0.855], [0.68, 0.74], [0.6, 0.62]],
  },
  {
    clash: [[0.2, 0.4], [0.4, 0.55], [0.6, 0.62]],
    jungle: [[0.56, 0.7], [0.65, 0.64]],
    mid: [[0.52, 0.6], [0.56, 0.71]],
    farm: [[0.62, 0.78], [0.53, 0.76]],
    roam: [[0.6, 0.62], [0.62, 0.7]],
  },
];

/** Where the team's presence concentrates in each keyframe: [x, y, radius, intensity]. */
export const HEAT: [number, number, number, number][][] = [
  [[0.17, 0.83, 0.08, 0.7]],
  [[0.12, 0.24, 0.07, 0.6], [0.46, 0.51, 0.07, 0.6], [0.73, 0.875, 0.09, 0.8], [0.29, 0.5, 0.08, 0.45]],
  [[0.58, 0.7, 0.13, 0.85], [0.2, 0.4, 0.06, 0.4]],
  [[0.61, 0.68, 0.11, 1]],
];

/** Objective the keyframe revolves around (drawn emphasized). */
export const FOCUS: (string | null)[] = [null, null, "tyrant", "tyrant"];

export const OBJECTIVES = [
  { id: "overlord", kind: "overlord" as const, ...anchor("overlord") },
  { id: "tyrant", kind: "tyrant" as const, ...anchor("tyrant") },
  ...["buff_camp_01", "buff_camp_02", "buff_camp_03", "buff_camp_04"].map((id) => ({ id, kind: "buff" as const, ...anchor(id) })),
];

const lerp = (a: Pt, b: Pt, f: number): Pt => [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];

/** Point at fraction f along a polyline (by length). */
export function along(path: Pt[], f: number): Pt {
  if (path.length === 1) return path[0];
  const segs = path.slice(1).map((p, i) => Math.hypot(p[0] - path[i][0], p[1] - path[i][1]));
  let d = Math.max(0, Math.min(1, f)) * segs.reduce((s, v) => s + v, 0);
  for (let i = 0; i < segs.length; i++) {
    if (d <= segs[i] || i === segs.length - 1) return lerp(path[i], path[i + 1], segs[i] ? Math.min(1, d / segs[i]) : 1);
    d -= segs[i];
  }
  return path[path.length - 1];
}

/** Illustration frame at continuous time t in [0, 3] (keyframe index + progress along its route). */
export function frameAt(t: number): TrackingPoint[] {
  const k = Math.min(3, Math.max(0, t));
  const i = Math.ceil(k);
  const f = i === 0 ? 1 : 1 - (i - k);
  return (Object.keys(KEYFRAMES[0]) as Position[]).map((role) => {
    const route = ROUTES[i][role];
    const [x, y] = i === 0 || route.length === 0 ? KEYFRAMES[i][role] : along(route, f);
    return { x, y, role };
  });
}
