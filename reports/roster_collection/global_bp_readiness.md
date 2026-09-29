# Global BP readiness (v0.4 Phase B)

Status: **PARTIAL — descriptive usage table built; competition rule NOT independently verified.**

## What was built

`data/processed/features/series_hero_usage.parquet` (11,150 team-games), one row per
(series_id, game_number, team_id):

- `heroes_used_current_game`: the team's heroes in this game, from kplow getScheduleDetail lineups.
- `heroes_used_previous_games`: heroes the same team used in earlier games of the same series.
- `distinct_heroes_used_before_game`: the size of that set.
- Also included: both-team previous heroes, plus `repeats_own_previous` / `repeats_any_previous` indicators.

Only strictly earlier games of the same series are used. The table does **not** include a
"remaining legal hero pool"; that would require the rule text.

Excluded:

- Appearances with a missing hero (9 games in 2022S2, series KPL2022S2M10W1D1, M2W4D1 and M3W1D1, where the source has an empty
  `hero_name`) are excluded rather than repaired; the games carry `HERO_MISSING`.
- 2022S1 is lineup-unsupported (no players returned), so it has no rows.

## Empirical observations (not a rule verification)

Own-team repeats come from `global_bp_repeat_by_season.csv` and `global_bp_own_repeat_by_game_number.csv`:

| season | team-games after G1 | repeat own earlier hero | repeat any earlier series hero |
|---|---|---|---|
| 2022S2 | 852 | 6 (all game 7) | 67.7% |
| 2023S1 | 886 | 14 (all game 7) | 63.2% |
| 2023S2 | 850 | 2 (all game 7) | 68.6% |
| 2024S1 | 836 | 6 (all game 7) | 68.8% |
| 2024S2 | 874 | 6 (all game 7) | 67.7% |
| 2024S3 | 374 | 8 (all game 7) | 61.2% |
| 2025S1 | 876 | 4 (all game 7) | 57.4% |
| 2025S2 | 852 | 6 (all game 7) | 61.3% |
| 2025S3 | 368 | 8 (all game 7) | 62.2% |
| 2026S1 | 874 | 8 (all game 7) | 62.8% |
| 2026S2 | 852 | 10 (all game 7) | 65.9% |

- Across every lineup-supported season, no team reuses one of its own earlier heroes in games 2–6.
  Own-repeats happen only in game 7.
- Heroes used earlier by the **opponent** are reused frequently (57–69% of team-games).
- This pattern is **consistent with** a per-team global-BP restriction that lifts in the deciding game 7.
  It is observational only. The rule text, and whether it applies to every stage (e.g. Annual Finals), has not been verified, so no legality
  constraint is encoded.

## Before using as a legality constraint

1. Obtain and cite the official KPL rule per season/stage.
2. Confirm the game-7 exception and whether bans count toward the pool.
3. Only then derive `remaining_legal_hero_pool`.
