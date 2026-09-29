# Roster semantics — what the kplow source proves

| Concept | Source field | What it proves | What it does NOT prove | Availability |
|---|---|---|---|---|
| REGISTERED_ROSTER | `getTeamsList {seasonid}` → `player_list` (playerid, position, openid, names) | the player was on the team's season registration list **as served on 2026-09-29** | that the player ever played; the registration date; that the list was identical at any earlier date | KPL2026S1, KPL2026S2 only (historical season IDs rejected, result 10020001) |
| SERIES_ROSTER | `getScheduleDetail` → `data.players` (10-13 per series) | players the source attaches to the series; in 2026 every one of them appears in ≥1 game lineup of that series | order/starting status | 2022S2-2026 |
| GAME_LINEUP | `getScheduleDetail` → `round_details[r].players` (10 per game) | the 5 players per team who played game r, with hero and (2025S3+) position | side, BP order | 2022S2-2026; empty 2022S1 |
| STARTING_FIVE | derived: GAME_LINEUP of round 1 | who started game 1 | an official starter designation — no starter flag exists | derivable wherever GAME_LINEUP exists |
| SUBSTITUTE_APPEARANCE | derived: player in GAME_LINEUP of round r>1 but not round 1 for the same team | an in-series substitution between games | reason (tactical/injury), or in-game swaps (not a concept in HoK) | 2026: 16/136 (Spring) and 15/136 (Summer) series show a lineup change |
| PLAYER_ACTUALLY_PLAYED | GAME_LINEUP only | playerid played game (scheduleid, round) for team slot | nothing is inferred from REGISTERED_ROSTER or SERIES_ROSTER | 2022S2-2026 |

## Evidence

- 2026 registered players: 156 (Spring), 165 (Summer). Players appearing in any game lineup: 114 and 120. Every game-lineup player is on the registered list (0 exceptions), so registration ⊇ participation, not equality.
- Registered rosters are 7-12 players per team; no coach rows (positions only 1-5).
- The series roster equals the union of game lineups in 136/136 series of each of 2026S1, 2026S2, 2023S1, 2023S2; series with >10 listed players are exactly the series with a between-game lineup change (2026: 16 and 15; 2023: 40 and 35). The series roster is therefore a participation list, not a registration list.
- 4 game-player rows (2023S2) have an empty `playerid`/team, making those games not 5v5 in the source — left unrepaired (`data_quality.csv`).

## Rules

- Only GAME_LINEUP establishes PLAYER_ACTUALLY_PLAYED.
- A seven-player registered roster is not evidence that seven players appeared.
- REGISTERED_ROSTER was retrieved after the season; using it as a pre-match feature would leak future roster decisions unless the list is re-snapshotted before each event.
