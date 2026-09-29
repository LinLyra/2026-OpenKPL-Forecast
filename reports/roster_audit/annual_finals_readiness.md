# 2026 Annual Finals roster / rotation readiness

## RULE INFORMATION (what the source says about the competition; no participation implied)

- Season list (snapshot 2026-09-28, `000_season_list.json`): `KPL2026S2` has `season_name` = "2026年KPL年度总决赛", `season_time_desc` = "10月2日至11月14日", `is_cur_season` = 1. All 136 completed KPL2026S2 series are the June–September summer regular season, play-in, playoffs and final (stages cgs1/2/3, kws, jhs, js). `KPL2026S3` returns "season not found". **No 2026 Annual Finals schedule was published at snapshot time.**
- Historical Annual Finals format, from the source's own stage IDs: 2025S3 had 擂台赛 (lts, 36), 淘汰赛 (tts, 13), 突围赛 (tws, 3) and 总决赛 (zjs, 1). That's 53 series, 2025-09-28 to 2025-11-08. 2024S3 also had 53 series.
- The HomeView chunk states that the 2026 prize money is settled per game won (单局结算) in the regular season and playoffs.
- No mandatory roster-appearance rule was found in any tested endpoint or site chunk. **UNKNOWN**; it would need an official rulebook (not collected).

## OBSERVED PARTICIPATION DATA (what can be proven from game-level evidence)

| Capability | Status | Evidence |
|---|---|---|
| Current registered roster | PARTIAL | getTeamsList KPL2026S2 (retrieved 2026-09-29). The registration date is unknown, and no Annual-Finals-specific list exists yet |
| Starting five | YES (derived) | round-1 GAME_LINEUP, 100% of 2026 games |
| Substitute appearance | YES (derived) | between-game lineup changes: 16 (Spring) and 15 (Summer) series |
| Per-game player participation | YES | 10-player lineups on 100% of 2026 games |
| Role | YES for 2026S1 (100%); PARTIAL for 2026S2 (95.2%) | 27 Summer games have position labels outside {1..5} |
| Player transfer history | PARTIAL | persistent playerid; canonical team sequence for 2022S2-2026 (112 players with observed transfers). Pre-2026 data is sampled except 2023 |
| Roster continuity | YES for 2026S1→S2 | same playerid in both seasons |
| Bench strength | PARTIAL | the registered list minus appeared players is observable; the quality of unplayed players is not |
| Series-level rotation | YES | per-series lineup sets |
| Game-to-game lineup changes | YES | per-round lineups |

## Tracking a roster-appearance requirement once the Finals start

Feasible **if** getScheduleDetail keeps its 2026 schema for the Annual Finals season ID. Each completed game gives the 10 playerids and hero picks, so appearance counts per registered player can be computed game by game. That requires a registered-roster snapshot taken **before** the event, via getTeamsList for the Finals season ID once it exists. It must be stored write-once so later roster edits can't leak into pre-match features.

## Constraints

- No future lineups are invented. No Annual Finals outcome is used; none exists in the dataset (`baseline_lock.json`: `KPL2026_annual_finals_completed` = 0).
- Registered rosters retrieved after the fact (2026S1/S2) are not safe pre-match features for past games.
