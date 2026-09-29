# Entity hierarchy of the kplow source (v0.4 Phase A)

Evidence: raw responses under `data/raw/roster_discovery/2026-09-29/api_sample/` (`provenance_manifest.csv`),
full 2026 collection (272 series), full 2023 collection (272 series), 12-series samples for every other season.
Labels: VERIFIED / PARTIAL / ABSENT / UNKNOWN only.

## Levels

| Level | Stable source ID | Human-readable name | Parent ID | Timestamp | Historical persistence |
|---|---|---|---|---|---|
| Tournament / competition | VERIFIED `seasonid` (e.g. `KPL2026S1`) | VERIFIED `season_name` | n/a | VERIFIED season start/end epoch | VERIFIED 2016-2026 seasons listed; note KPL2026S2 is *named* 年度总决赛 while holding the summer season |
| Season / stage | VERIFIED `stageid` (cgs1/2/3, kws, jhs, js; Annual Finals lts/tts/tws/zjs) | VERIFIED `stage_name` | VERIFIED `seasonid` | PARTIAL (via series times) | VERIFIED |
| Series (BO5/BO7) | VERIFIED `scheduleid` | VERIFIED title/teams | VERIFIED seasonid, stageid | VERIFIED `start_timestamp` (getScheduleList) | VERIFIED 2022-2026 in temporal dataset |
| Game / map | PARTIAL: positional key `(scheduleid, round)` for 100% of tested games; source `battle_id` only via getSeasonHeroComboMatches (2026 only, 53-59% of games) | n/a | VERIFIED `scheduleid` (+ `schedule_id`/`match_num` on battles) | PARTIAL: no game start time; `battle_id` prefix is a unix epoch whose date equals `schedule_date` on 1070/1070 rows (INFERENCE on semantics) | VERIFIED rows exist 2022-2026; lineups from 2022S2 |
| Team (per season) | VERIFIED slot id `KPL<season>_<code>` (season-scoped, not a club ID) | VERIFIED team_name | VERIFIED seasonid | n/a | PARTIAL: slot IDs change every season; club continuity comes from the reviewed registry, not the source |
| Player | VERIFIED `playerid` (persists across seasons/teams: 23 IDs span 2022S2-2026) | PARTIAL: 2026 short + real names; before 2026 only `"<team>.<handle>"` display strings | VERIFIED team slot per series (series `players[].team_id`) | n/a | VERIFIED IDs persist through transfers; 2 same-handle/different-ID pairs (see player_identity_inventory.csv) |
| Hero | VERIFIED `hero_id` | VERIFIED `hero_name` | VERIFIED per (game, player) | n/a | VERIFIED |

## Explicit answers

| | Question | Answer | Evidence |
|---|---|---|---|
| A | Every BO5/BO7 series has a stable ID | VERIFIED | `scheduleid`; 640/640 tested series accepted by getScheduleDetail, round count = validated score |
| B | Every game has a stable game/battle ID | PARTIAL | `battle_id` only for 306/573 (2026S1) and 329/562 (2026S2) games; none before 2026 via tested endpoints. `(scheduleid, round)` is positional, not a source ID |
| C | Game deterministically connected to parent series | VERIFIED | round_details nested under scheduleid; battles carry `schedule_id`+`match_num`; 0 orphan games of 2679; battle_id↔(scheduleid, match_num) 1:1 on 635 battles |
| D | Participating players recorded per game | VERIFIED (2022S2-2026); ABSENT 2022S1 | `round_details[].players` (10 per game) |
| E | Registered roster vs actually appeared distinguishable | VERIFIED (2026) | getTeamsList registered 156/165 players; only 114/120 appear in any game |
| F | Starters vs substitutes distinguishable | PARTIAL | no starter/substitute flag; game-1 lineup and between-game lineup changes are observable (16 and 15 series with a change in 2026S1/S2) |
| G | Player role/position recorded | PARTIAL | positions 1-5 on 100% of 2026S1 games, 95.2% of 2026S2; all 0 (unlabeled) before 2025S3 |
| H | Player hero assignment recorded | VERIFIED (2022S2-2026) | `players[].hero_id` per game |
| I | Blue/red side recorded | ABSENT (per game) | only team-season aggregates `TeamBlueCount/TeamRedCount` in getTeamsIntro |
| J | Complete ordered BP recorded | PARTIAL | picks with order index for combo-listed 2026 games only; bans ABSENT everywhere |
| K | K/D/A available | PARTIAL | per game: team kill totals only (combo games); per player: season aggregates only (getSeasonPlayerPerf) |
| L | Gold/economy available | PARTIAL | season aggregate gold rate; live-only gold in getBattleDetail; ABSENT per completed game |
| M | Damage available | PARTIAL | season aggregates only |
| N | Objectives available | ABSENT | no tower/dragon/baron fields in any response or site chunk |
| O | Patch/game version available | ABSENT | no patch/version key in any response, KV config or site code |
