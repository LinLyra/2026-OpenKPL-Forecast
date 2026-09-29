# Meta / patch data availability

## Patch and version

| Item | Status | Evidence |
|---|---|---|
| patch ID | ABSENT | no `patch`/`version`/`ver`/`game_version`/`patch_id` key and no `版本` token in any of the 748 non-empty saved API JSON responses |
| game version | ABSENT | same; KV config keys are only `kpl_jhs_match`, `kpl_js_match`, `kpl_season_select_list` |
| competition version | ABSENT | none |
| balance patch date | ABSENT | none |
| hero adjustment date | ABSENT | none; site chunks reference hero/skill/equip/rune picture CDNs only |

Candidates that exist but are not patch data:

- Per-season hero statistics from `getHeroRankList` (win_cr, match_count, best player).
- Per-season hero combos from `getSeasonHeroCombo`, 2026 only.
- Hero first-appearance dates, which could be derived from dated game lineups. That would be an observation, not a patch mapping.

No patch mapping was created.

## VOD value, documented only (no OCR, frame extraction, labeling or CV started)

| Missing structured layer | Potential VOD signal | Estimated extraction method | Why uniquely valuable |
|---|---|---|---|
| Bans and full ordered BP, all seasons | draft screen before each game | OCR or template matching of hero portraits on the BP screen | the only kplow-linked route to complete ordered BP; WZRY's BP covers only to ~2024.3 |
| Blue/red side per game | side banner and minimap orientation | template matching on the first frames | side is ABSENT per game in every structured endpoint |
| Game start time and duration (non-combo games) | in-game clock / end screen | OCR of the timer and end screen | battle_id and duration exist for only 53-59% of 2026 games |
| Per-player K/D/A, gold, damage | end-of-game scoreboard | OCR of the scoreboard | per-game boxscore is ABSENT (season aggregates only) |
| Objectives and gold curve (game state) | minimap, top bar | CV over the full video | needed for any game-state model; nothing structured exists |
| Patch identification | client UI version / hero kits | weak; manual | patch is ABSENT everywhere |

Availability: `round_details.vid` is present on 2,675 of 2,679 tested games (the 4 missing are single games in 2023S1, 2023S2, 2024S1 and 2024S3), with per-player vids from 2026-06-24. The video delivery endpoint (`jt {file_ids}`) was not tested.
