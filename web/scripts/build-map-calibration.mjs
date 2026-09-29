#!/usr/bin/env node
/**
 * Map reference for the tactical board, from the open-source HonorOfKings minimap-analysis repository
 * (https://github.com/dayelianxisheng/HonorOfKings), checked out sparsely at ../.vendor/HonorOfKings.
 *
 * - public/assets/map/hok-top.webp: its 5300×4800 top-down reference (王者峡谷_顶视图.png), downscaled.
 *   Local prototype only (the repo ships no licence and the artwork belongs to the game); not for deployment.
 * - data/map/hokCalibration.json: the 40 fixed anchors (configs/full_map_anchors.json) in normalized
 *   reference coordinates, plus a minimap -> reference homography fitted on the anchors shared with the
 *   minimap detection configs, mirroring MinimapReferenceTransform.from_configs.
 */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(ROOT, "../.vendor/HonorOfKings");
const read = async (p) => JSON.parse(await fs.readFile(path.join(REPO, p), "utf8"));

const full = await read("configs/full_map_anchors.json");
const { width: W, height: H } = full.reference_size;
const anchors = Object.entries(full.anchors).map(([id, a]) => ({
  id, category: a.category, x: a.reference_position.x / W, y: a.reference_position.y / H,
}));

const minimap = {};
for (const f of ["structure_detection", "objective_detection", "monster_detection"]) {
  for (const a of (await read(`configs/${f}.json`)).anchors ?? []) minimap[a.id] = [a.x, a.y];
}
const shared = anchors.filter((a) => minimap[a.id]);

// Least-squares DLT with h33 = 1: solve (AᵀA) h = Aᵀb.
function fitHomography(pairs) {
  const A = [], b = [];
  for (const [[x, y], [u, v]] of pairs) {
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
  }
  const n = 8, M = Array.from({ length: n }, (_, i) => [
    ...Array.from({ length: n }, (_, j) => A.reduce((s, r) => s + r[i] * r[j], 0)),
    A.reduce((s, r, k) => s + r[i] * b[k], 0),
  ]);
  for (let c = 0; c < n; c++) {
    const p = M.slice(c).reduce((best, r, k) => (Math.abs(r[c]) > Math.abs(M[best][c]) ? c + k : best), c);
    [M[c], M[p]] = [M[p], M[c]];
    for (let r = 0; r < n; r++) if (r !== c) {
      const f = M[r][c] / M[c][c];
      for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
    }
  }
  const h = M.map((r, i) => r[n] / r[i]);
  return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
}
const project = (Hm, x, y) => {
  const w = Hm[2][0] * x + Hm[2][1] * y + Hm[2][2];
  return [(Hm[0][0] * x + Hm[0][1] * y + Hm[0][2]) / w, (Hm[1][0] * x + Hm[1][1] * y + Hm[1][2]) / w];
};

const Hm = fitHomography(shared.map((a) => [minimap[a.id], [a.x, a.y]]));
const errors = shared.map((a) => {
  const [u, v] = project(Hm, ...minimap[a.id]);
  return Math.hypot((u - a.x) * W, (v - a.y) * H);
}).sort((p, q) => p - q);

const round = (v) => Math.round(v * 1e6) / 1e6;
await fs.mkdir(path.join(ROOT, "data/map"), { recursive: true });
await fs.writeFile(path.join(ROOT, "data/map/hokCalibration.json"), JSON.stringify({
  source: "github.com/dayelianxisheng/HonorOfKings · configs/full_map_anchors.json, configs/*_detection.json",
  reference: { image: "/assets/map/hok-top.webp", width: W, height: H },
  anchors: anchors.map((a) => ({ ...a, x: round(a.x), y: round(a.y) })),
  minimapToReference: {
    matrix: Hm.map((r) => r.map((v) => Number(v.toPrecision(10)))),
    anchorCount: shared.length,
    meanErrorPx: Math.round(errors.reduce((s, e) => s + e, 0) / errors.length),
    p95ErrorPx: Math.round(errors[Math.floor(errors.length * 0.95)]),
  },
}, null, 2) + "\n");

await fs.mkdir(path.join(ROOT, "public/assets/map"), { recursive: true });
await sharp(path.join(REPO, "assets/maps/full_map/reference/王者峡谷_顶视图.png"))
  .resize({ width: 2400 }).webp({ quality: 80 }).toFile(path.join(ROOT, "public/assets/map/hok-top.webp"));
console.log(`anchors ${anchors.length}, homography on ${shared.length} shared anchors, mean error ${Math.round(errors.reduce((s, e) => s + e, 0) / errors.length)}px`);
