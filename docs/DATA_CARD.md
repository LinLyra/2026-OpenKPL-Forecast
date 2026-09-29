# Data Card (v0.2)

Figures below are from `openkpl quality` on 2026-09-28 and reconcile 24/24 with `reports/audit/hok_bp_deep_audit.md`.

## Historical Draft Corpus

Source: `data/raw/external/HoK-BP-LLM/王者荣耀KPL历年比赛数据/WZRY.csv` (GB18030; SHA256 `4654834e…9e8f`). Committed as a finished file in HoK-BP-LLM commit `5ca05a5`; no generator script exists in that repository.

### Verified content

| Table | Rows | Grain |
| --- | ---: | --- |
| `draft_games` | 5,586 | one source row |
| `draft_events` | 100,531 | one ban/pick (44,674 bans, 55,857 picks) |
| `game_lineups` | 55,860 | one hero slot (10 per game) |
| `hero_loadouts` | 331,613 | one item in one hero's item list |
| `draft_teams` / `heroes` | 45 / 118 | dimension |

### Verified absent

Match/game ID, date, season, stage, tournament, series number, game number, side, patch, player name/ID, kills, deaths, assists, gold, damage.

### Identifiers

`draft_game_id = wzry_{source_row:06d}` with `draft_game_id_is_synthetic = True` and `temporal_identity_available = False` on every row. These are row IDs only. `source_row_sha256` hashes the six raw cell strings.

### Quality flags (retained, not repaired)

| Flag | Count | Meaning |
| --- | ---: | --- |
| `bp_quality_flag = STANDARD_18` | 5,579 | 18 events, 8 bans, 10 picks |
| `bp_quality_flag = NONSTANDARD` | 7 | shorter sequences (rows 103, 869, 1731, 1779, 2118, 2746, 4698) |
| `lineup_quality_flag = CLEAN_FIVE_ROLE` | 3,007 | each team has each of the 5 roles exactly once |
| `lineup_quality_flag = NONSTANDARD_ROLE_ASSIGNMENT` | 2,579 | duplicate lanes, `未知`, or blank positions |
| `has_missing_hero` | 23 games | 23 ban events with an empty hero string; no empty picks |
| `pick_set_matches_lineup = False` | 2 | rows 869 and 1731 |
| `unknown_position_slots` / `blank_position_slots` | 286 / 22 | `position_raw` keeps the original; blanks normalize to `未知` |

`winner_team` is never missing; `team1_win` and `team2_win` are always complementary (2,815 / 2,771). `team1` is the first actor in every BP list; the file does not say whether that is blue or red side.

### Permitted uses

Descriptive draft analysis, role flexibility, composition analysis, retrospective draft classification, sequence modelling explicitly labelled non-temporal.

Do not make temporal, patch-specific, player-level, or causal coach claims from this corpus. Do not join it to the series backbone on team names.

## Temporal Series Backbone

Source: `data/raw/external/PythonMajor-assignment/data/kpl_data.db`, table `kpl_matches` (SHA256 `8f963127…e29ca`). Crawled 2026-02-04 from the KPL `getScheduleList` endpoint.

### Verified content

1,284 series, 1,284 unique IDs (`KPL{year}S{n}M{m}W{w}D{d}`), 11 seasons from `KPL2022S1` to `KPL2026S1`, start times 2022-02-09 to 2026-03-01, 35 team-name strings. No missing or epoch-fallback start times. No two series share a start time.

Regular seasons have 136 series each (45 + 45 + 30 regular, 11 playoff, 4 qualifier, 1 final); `S3` annual-finals seasons have 53. This is the league format, not truncation: every completed season ends with its final.

### Labels

| `label_flag` | Count | Labeled |
| --- | ---: | --- |
| `COMPLETED` (status 4, decisive score) | 1,239 | yes |
| `NOT_FINISHED` (status 1, 0–0) | 44 | no |
| `STATUS_SCORE_CONFLICT` (status 3, 2–0) | 1 (`KPL2026S1M4W1D1`) | no |

The conflict row was in progress when crawled. v0.2's original code labeled it a completed 南通Hero久竞 win; the merged code does not.

### Known limitations

- `start_time` is naive. The crawler used the machine's local time zone. The crawl log timestamps are 8 hours ahead of SQLite's UTC `update_time`, so the times are most likely China Standard Time (inference).
- No `KPL2022S3`, `KPL2023S3`, or 2020–2021 data: the endpoint returned 0 rows for those seasons.
- Team names are raw strings. Renames split one organization into several names (for example `南京Hero久竞` → `Hero久竞` → `南通Hero久竞`, `苏州KSG` → `KSG`, `杭州LGD大鹅` → `杭州LGD.NBW`, `佛山GK` → `佛山DRG.GK` → `佛山DRG`, `情久` → `桐乡情久`, `TCG` → `无锡TCG`, `MTG` → `郑州MTG`). No alias map is applied.
- Series grain only: no per-game results, drafts, or players.
