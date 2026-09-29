# WZRY.csv linkage feasibility (diagnostic; WZRY.csv not modified)

## Question

Can the 5,586 anonymous `WZRY.csv` game rows (team names, win flag, per-team heroes, ordered BP, equipment; no date/season/series/game key) be assigned real kplow game identities `(scheduleid, round)`?

## Method

- WZRY side: `battle_process` parsed with `ast.literal_eval` (read-only) into one hero set per team; winner from `team1_win/team2_win`.
- kplow side: `getScheduleDetail` game lineups; team of each player from the series roster slot; slot → team name from `getTeamsIntro.team_list` (same source).
- Team names map to canonical IDs **only** through exact `observed_name` rows of `data/dimensions/team_identity_registry.csv`. Hero names compared byte-exactly. No fuzzy matching, no similarity scores.
- Candidate universe = every kplow game with a lineup collected in this audit: 2,627 games = full 2023S1 + 2023S2, full 2026S1 + 2026S2, and 12-series samples of 2022S2, 2024S1, 2024S2, 2024S3, 2025S1, 2025S2, 2025S3. 2022S1 has no lineups in the source, and 2020-2021 is not in the temporal dataset.
- A match is "unique" only if exactly one universe game carries the identical fingerprint.
- Code: `src/openkpl/roster/wzry_link.py`, run via `python -m openkpl.roster.run`. Counts: `wzry_linkage_counts.csv`. Row-level candidates: `wzry_linkage_sample.csv`.

## Fingerprints, strictest last (WZRY → kplow)

| Fingerprint | rows tested | unique exact | multiple | no match |
|---|---|---|---|---|
| F1 team pair | 5,256 | 0 | 5,000 | 256 |
| F2 team pair + final 10 heroes | 5,256 | 1,194 | 0 | 4,062 |
| F3 team pair + team-specific hero sets | 5,256 | 1,194 | 0 | 4,062 |
| F3W F3 + winner | 5,256 | 1,168 | 0 | 4,088 |
| F4 team pair + ordered BP | not testable | – | – | – |
| F5 F4 + final hero assignments | not testable | – | – | – |
| Diagnostic D1 10 heroes, no teams | 5,586 | 1,194 | 0 | 4,392 |
| Diagnostic D2 per-team hero sets, no teams | 5,586 | 1,194 | 0 | 4,392 |

- 330 WZRY rows contain a team name absent from the registry, so F1-F3W can't be computed for them. The 24 names include CW, DQ, EMC, ESG, GOG, HH, HI, HJG, MD, NOVA, ROX, TLG, TY, VSG, Wkk, YYG, 东莞Wz, 喵鱼, 嵊州SZG, 斗鱼XHW, 无锡JXG, 昆山SC, 虎牙小当家 and 镇江VTG. These look like non-KPL teams, which is an INFERENCE; none is merged or guessed.
- F4/F5 can't be tested for two reasons. kplow has no ban records anywhere. Its pick order exists only through `getSeasonHeroComboMatches`, which covers the 2026 seasons only, outside the WZRY window. Equipment is also absent from kplow.
- Within WZRY, 2 rows share the same diagnostic hero fingerprint. They are left as they are.

## Reverse check against the complete 2023 universe (kplow → WZRY)

| Fingerprint | 2023 kplow games tested | unique exact in WZRY | multiple | no match |
|---|---|---|---|---|
| F3 team pair + team hero sets | 1,136 | 1,124 (98.9%) | 0 | 12 |
| F3W + winner | 1,127 | 1,115 | 0 | 12 |

Of the 2023 games, 4 are excluded from the universe because the source has a blank player ID, which makes them not 5v5.

## Consistency of the 1,194 unique F3 matches

- Winner: 1,168 agree. The other 26 are games where kplow's `win_team` is blank; WZRY supplies a winner there. There are **0 contradictions**. The blank kplow winners stay blank and are not repaired.
- Matches by season: 569 in 2023S1, 555 in 2023S2, 43 in 2022S2 (from 45 sampled games), 27 in 2024S1 (from 50 sampled games).
- No matches in the 2024S2-2026 universe (1,396 games). This is consistent with the README's "2020 至 2024.3" window.
- WZRY row order is not chronological. The Spearman correlation between row number and match time is 0.37, and only 0.17% of consecutive matched rows are in time order. Row position can't be used to date unmatched rows.

## Assessment

- **POSSIBLE, and demonstrated for 2023.** 1,194 WZRY rows now have a unique real game identity at F3. For the complete 2023 universe, 98.9% of kplow games are found in WZRY.
- The remaining rows fall into three groups:
  - 330 have non-registry teams.
  - Rows from 2022S2 and 2024S1 were not linkable because only 12-series samples were collected. The samples match 43 of 45 and 27 of 50 games. Those rates are sample-based and are **not** extrapolated here.
  - Rows from 2020 to 2022S1 have no lineup data in kplow and cannot be linked through this source.
- Uniqueness is proven within the collected universe only. Adding the rest of 2022S2 and 2024S1 could, in principle, create collisions. No collision occurred within 2,627 games at F2 or stricter.
- Ordered BP (F4) can't be verified against kplow. Once a row is linked by F3, its WZRY `BP_process` becomes a dated draft record, but that draft order is WZRY's own claim and has not been cross-verified.
