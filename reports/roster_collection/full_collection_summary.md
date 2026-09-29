# v0.4 Phase B — Full historical game/player collection summary

Data engineering only. No outcome model was built.

- Rebuild with `.venv/bin/python -m openkpl.history.run` (offline; it reads only stored raw responses).
- Quality metrics are in `full_collection_quality.csv`; per-season coverage is in `season_coverage.csv`.

## Collection

- 1,466 / 1,466 validated series fetched via kplow getScheduleDetail.
  - 826 were collected in this phase, into `data/raw/roster_collection/2026-09-29/schedule_detail/`; the rest came from the Phase A store.
  - 7 series needed one retry (stored as separate `_retryN` artifacts); 0 failed.
- Game count equals series score for 1,466 / 1,466.
- The raw store is write-once with SHA256 per artifact (`raw_provenance.csv`); failed attempts are preserved.
- 2022S1 (136 series, 554 games): the endpoint answers but returns no lineups and no winners.
  These series are counted as fetched but lineup-unsupported, and nothing is inferred for them.

## Games (`kpl_games.parquet`, 6,140 rows)

- The key is `game_key = "{series_id}#G{game_number}"`, a deterministic, non-source identifier.
- `source_battle_id_if_available` is filled only for the 635 games in 2026 hero-combo responses and is never fabricated.
- 6,133 games have a video id.

Anomalies are flagged, not repaired:

| anomaly | games | detail |
|---|---|---|
| no lineup | 556 | |
| missing winner | 719 | 163 of them have lineups: 153 in 2022S2, 9 in 2023S1, 1 in 2024S1 |
| repeated hero in game | 35 | all in game 7 |
| `HERO_MISSING` | 9 | 2022S2; empty source `hero_name` |
| not 5v5 | 29 | 25 in 2025S1 across 7 series and 4 in 2023S2; one player row has no player id and no team slot |
| roles unknown | 4,443 | position 0 before 2025S3; not manufactured |
| roles not 1–5 | 64 | |

## Players and identity

- 55,840 appearance rows; 332 source player ids; 411 derived display handles.
- 128 players appear with more than one canonical team.
- 82 handles keep a prefix that does not equal the source team name.
- `player_identity_registry.csv` is keyed by source `player_id`.
  - 328 are `SOURCE_ID_STABLE` and 4 are `REVIEW_REQUIRED`: the two cross-ID pairs below.
  - No ids were merged.

| pair | id A (active) | id B (active) | overlap / same day / same series / same game | assessment |
|---|---|---|---|---|
| 归期 | 60011676 (2023-06-14 → 2026-09-01, RW/Wolves, 481 games) | 70010275 (2023-04-02 → 2023-04-19, Wolves, 6 games) | none / 0 / 0 / 0 | source-ID migration plausible; not merged |
| 无双 | 60011747 (2024-02-01 → 2026-09-06, JDG/RW, 520 games) | 70010439 (2023-07-23 → 2023-08-19, RW, 38 games) | none / 0 / 0 / 0 | source-ID migration plausible; not merged |

- In both pairs, the id with the later and longer career carries the same team-and-handle name that the short-lived id used on the same team.
- The newer ids' name variants include a real-name suffix (双小钧 and 胡家荣).
- No new cases were found in the full universe.

## Rosters (from actual appearances only)

- `series_player_usage.parquet` has 13,738 rows; 446 player-series rows entered after game 1.
- `series_rotation_summary.parquet` has 2,660 team-series.
  - 10.8% of team-series have at least one lineup change; 10.7% used more than 5 players.

`roster_continuity_score` is defined as follows. For a team-series with lineups L_1..L_N (sets of player ids per game),

    continuity = mean_{g=2..N} |L_g ∩ L_1| / |L_1|    (1.0 if N == 1)

The mean is 0.978 and the minimum is 0.30. The score is fixed a priori and not tuned against outcomes.

`lineup_changes` counts games g ≥ 2 whose lineup differs from game g−1.

## Temporal features

Ordering uses `(series_start_time, chronological_order, game_number)`. Features are computed
before the state is updated with the current game.

- `*_prior_*`: all strictly earlier games, including earlier games of the same series.
- `*_preseries_*`: games in strictly earlier series only.
- Win rates are computed over decided games only, using the kplow winner. WZRY winners are never substituted.
  Games without a winner count in `games` but not in `decided`.
- Shrunk win rate is `(wins + K·p0) / (decided + K)` with K = 10 and p0 = 0.5.
- `meets_min_sample` means decided ≥ 5.
- K, p0 and MIN_SAMPLE are fixed metadata, not optimized.
- Appearances with `HERO_MISSING` update player-level stats only, not hero-keyed stats.

Feature tables:

| file | rows | content |
|---|---|---|
| `player_hero_temporal.parquet` | 55,811 | player×hero, player, hero, team×hero (kplow lineups) |
| `hero_temporal_features.parquet` | 34,951 | per draft event: hero pick/ban counts, games/wins, team×hero, player×hero (identified games) |
| `hero_synergy_temporal.parquet` | 38,836 | unordered same-team hero pairs |
| `hero_counter_temporal.parquet` | 97,090 | directed (hero, opponent_hero) |

## WZRY linkage (WZRY.csv read-only; 5,586 rows)

Matching uses exact registry names to map teams to canonical ids and exact hero names. The candidate universe is one global
index over all 5,584 kplow games that have complete 5v5 lineups. Neither the winner nor row order is used as a key.

Fingerprint levels:

- F1: unordered team pair.
- F2: F1 plus each team's unordered five heroes.
- F3: F2 with team-specific assignment.
- F4 (hero-role): **not applicable**. Positions exist only from 2025S3 onward, and WZRY ends in 2024S1.

| status | rows |
|---|---|
| UNIQUE_EXACT_MATCH | 1,942 (2022S2 506, 2023S1 569, 2023S2 555, 2024S1 312) |
| MULTIPLE_EXACT_MATCHES | 0 |
| NO_MATCH | 3,314 |
| UNRESOLVED_TEAM_IDENTITY | 330 |
| SOURCE_CONFLICT | 0 |

- F1 alone never gives uniqueness.
- All 1,942 unique rows are first unique at F2, and F3 confirms them.
- NO_MATCH breakdown: 77 rows have a team pair absent from the universe. The other 3,237 have the pair but no exact hero match; these are
  expected to be WZRY games from 2020–2022S1, where kplow has no lineups.
- Winner validation: 1,799 AGREE, 143 KPL_WINNER_MISSING, 0 WZRY_WINNER_MISSING, **0 CONTRADICTION**.

## Identified drafts

- `identified_draft_games.parquet` has 1,942 rows and keeps the original `battle_process` / `BP_process` text.
- `draft_events_identified.parquet` has 34,951 events: 19,419 picks and 15,532 bans over 104 hero ids.
  - Phases are derived only for the standard 18-slot shape (4B-6P-4B-4P).
  - 31 events in non-standard shapes have no phase.
- Hero name→id uses only one-to-one exact mappings observed in kplow lineups and the hero-rank data.
  - 6 events have an unmapped hero (blank name in WZRY) and keep a null id.
  - 1 WZRY-internal inconsistency: BP picks differ from battle heroes in KPL2023S2M6W2D1#G1.

## Immutability

- `phase_b_lock.json` covers 835 locked artifacts.
- They were verified before and after the build; WZRY.csv and the v0.3 benchmark artifacts are byte-identical (see the tests).
