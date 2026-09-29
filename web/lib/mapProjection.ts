import calibration from "@/data/map/hokCalibration.json";
import type { Position } from "@/data/teamPresentation";

/**
 * Coordinates on the Canyon of Kings top-down reference (HonorOfKings repo, 5300×4800), normalized to [0, 1].
 * A tracker that reads the in-game minimap can feed its normalized minimap points through projectMinimap().
 */
export interface TrackingPoint {
  x: number;
  y: number;
  role?: Position;
  playerId?: string;
  heroId?: string;
}

export interface TrackingFrame {
  /** Seconds since game start. */
  t: number;
  points: TrackingPoint[];
}

/** "illustration" = hand-authored tactical example; "observed" = derived from real match footage. */
export type TrackingSource = "illustration" | "observed";

export const REFERENCE = calibration.reference;
/** SVG viewBox for overlays: x in [0, 1000], y scaled by the reference aspect ratio. */
export const VIEW_W = 1000;
export const VIEW_H = (VIEW_W * REFERENCE.height) / REFERENCE.width;

export const toView = (p: { x: number; y: number }): [number, number] => [p.x * VIEW_W, p.y * VIEW_H];

const H = calibration.minimapToReference.matrix;

/** Minimap-normalized point -> reference-normalized point (homography fitted on the repo's shared anchors). */
export function projectMinimap(p: TrackingPoint): TrackingPoint {
  const w = H[2][0] * p.x + H[2][1] * p.y + H[2][2];
  const x = (H[0][0] * p.x + H[0][1] * p.y + H[0][2]) / w;
  const y = (H[1][0] * p.x + H[1][1] * p.y + H[1][2]) / w;
  return { ...p, x: Math.min(1, Math.max(0, x)), y: Math.min(1, Math.max(0, y)) };
}

export function anchor(id: string): { x: number; y: number } {
  const a = calibration.anchors.find((k) => k.id === id);
  if (!a) throw new Error(`unknown map anchor ${id}`);
  return { x: a.x, y: a.y };
}
