# OpenKPL 2026 Annual Finals — Web Build Report

Status: **Visual Asset & Real Map Integration Pass** — presentation layer only. Frozen forecast files, model outputs, probabilities, tournament engine, rules, prediction ledger and source data are untouched (SHA-256 of the six frozen files re-verified; git HEAD `24a3fbf`; nothing committed).

- Stack: Next.js 16.3.6 (App Router, static prerender), React 19, TypeScript, Tailwind CSS 4, Framer Motion, d3-shape, `next/image`.
- Data flow (one-way, unchanged): frozen artifacts → `scripts/build-web-data.mjs` → `data/generated/*.json` → `lib/data.ts` → components. See `DATA_BINDING_AUDIT.md`.

## 1. Design

Dark "Honor of Kings broadcast" theme (`app/globals.css`): ink-navy canvas (`#060912`), gold accents (`#d9b36a` / `#f3dca4`) with gradient numerals (`.gold-num`), blue/red side colours for the two camps, hairline gold panels. Fewer elements, larger visuals; the LLyra signature stays in header and footer.

- **Home** — broadcast hero: 重庆狼队 official team photo, logo, name, 42.2% as the single mega numeral; contenders #2–#5 as logo cards; "12 支战队夺冠概率" logo field (logo size ∝ √P); three entry cards. The dot matrix is gone.
- **Matchup** — VS composition: two large official logos, names, 56.7% VS 43.3% in camp colours, a blue/red split line, rating A : B, rating gap, Stage 1 meeting. No scale, gauge or bar chart.
- **Teams** — logo grid per group; team pages share a logo switcher, an overview banner (official photo, logo, slogan, P(champion) + three figures) and tabs 概览 / 赛程 / 夺冠路径 / 阵容 / 战术地图. Roster shows the official 7-player list with official portraits.
- **Tactical map** — see §3.
- **Methodology** — four sections only: 战队实力模型, B0–B5 模型选择, 时间外验证 (11 folds × 12 seasons grid), 1,000,000 次赛事模拟; plus one sentence that predictions were fixed before the first match. No freeze ID, test counts, file names, paths, hashes or provenance.
- Frozen/cutoff/model-version/status badges are no longer repeated anywhere. The Chinese site is fully Chinese apart from Elo, B5, BO5, BO7 (and proper names: KPL, team names).

Removed from the codebase (not hidden): `FrozenBadge`, `ProvenancePanel`, `SourceTag`, `TeamCrest` (generated placeholder crests), `RaceChart`, the balance/scale matchup, the dot-matrix field, the abstract SVG map (`components/map/*Layer`, `ArenaMap`, `TacticalBoard`, `data/map/{arenaGeometry,structures,objectives,tacticalScenarios,types}.ts`), the methodology appendix routes, the old screenshot folders and visual-QA notes.

## 2. Official assets

| Field | Source | Status |
|---|---|---|
| `teamLogo`, `teamLogoAlt` | KPL 官网 API `kplow/getTeamsList` (`team_logo`, `team_logo_2`) | 12 / 12 |
| `teamPhoto` | same (`img`, 2026 年度总决赛 key visual) | 12 / 12 |
| `playerPortrait` + player name / real name / position | same (`player_list`), season KPL2026S3 | 12 × 7 |
| `slogan` | `kplow/getTeamsIntro` | where published |
| `teamHeroImage`, `coachPortrait` | not published by the API | `null` → section hidden |

- Fetcher: `npm run assets:fetch` (`scripts/fetch-kpl-assets.mjs`) → `public/assets/kpl/{team}/…` and `data/assets/kpl-official.json`. Nothing is invented; a missing asset hides its section (`TeamLogo` renders nothing, roster returns `null`).
- Position codes (from the API `position_cn` of earlier seasons): 1 对抗路, 2 中路, 3 发育路, 4 打野, 5 游走.

## 3. Real map + tracking renderer

Source: [dayelianxisheng/HonorOfKings](https://github.com/dayelianxisheng/HonorOfKings), sparse checkout in `../.vendor/HonorOfKings` limited to `assets/maps/full_map/reference/`, `configs/full_map_anchors.json`, `configs/*_detection.json`, `src/hok_minimap/`, `README.md`.

- Verified: `王者峡谷_顶视图.png` (5300 × 4800, cropped from a 9704 × 5459 original), 40 named anchors in normalised reference coordinates, and the projection in `src/hok_minimap` (`MinimapReferenceTransform`: `cv2.findHomography` over anchors shared between minimap detection configs and the reference map).
- `npm run map:calibrate` (`scripts/build-map-calibration.mjs`) re-implements that fit (least-squares DLT, 40 shared anchors, mean error 37 px / p95 111 px on the 5300 px reference) → `data/map/hokCalibration.json`, and writes a 2400 px WebP of the reference map to `public/assets/map/hok-top.webp`.
- `components/map/TacticalMap.tsx`: the real map is the background (`next/image`), SVG is overlay only — role zone highlight + dimming, heat, objectives (主宰 / 暴君 / buffs), animated routes, player markers, state tabs 对线期 / 资源布置 / 团战 with tweened transitions, role buttons 对抗路 / 打野 / 中路 / 发育路 / 游走, layer toggles, play/scrub timeline. Label once: "战术示意 · 非真实比赛轨迹".
- Tracking API (`lib/mapProjection.ts`): `TrackingPoint { x, y, role?, playerId?, heroId? }` in normalised reference coordinates, `TrackingFrame { t, points }`. `projectMinimap()` converts minimap-normalised detections (as produced by the HonorOfKings pipeline) through the homography. `<TacticalMap observed={frames} portraits={…} />` switches the source to `"observed"` and drops the illustration label and synthetic routes; the built-in keyframes are always labelled as illustration.

## 4. Licensing limitation

The HonorOfKings repository has no LICENSE file and the map artwork is Tencent's; team logos, photos and player portraits belong to the clubs / KPL. They are used **for the local prototype only**: `public/assets/map/` and `public/assets/kpl/` are git-ignored (`web/.gitignore`) and must be regenerated locally with the two scripts above. Public deployment needs permission or replacement assets. `../.vendor/` (29 MB, untracked) is only needed to rerun `map:calibrate` and can be deleted afterwards.

## 5. Validation

`npm run typecheck`, `npm run lint`, `npm run build`, `npm run data:check` pass. `BASE_URL=… npm run smoke`: every zh/en route at 1440 and 390 px with no console errors or horizontal overflow; the real map image loads on the tactical page; role/state controls respond; matchup swap and pick behave. Screenshots: `docs/screenshots/`.
