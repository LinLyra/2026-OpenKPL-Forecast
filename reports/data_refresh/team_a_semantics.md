# team_a semantics (v0.3.1 forensic audit)

## VERIFIED SOURCE SEMANTICS

- The source record has `team_a_*` / `team_b_*` fields (id, name, group, score, logo) and match-level `location_name`, `arenas`, `bo_total`, `competition_format`. No field declares home/away, side (blue/red), seed, or bracket slot. No public documentation of the ordering was found in the source or the site bundle.
- Side (blue/red) is decided per game inside a BO5/BO7 series, so it cannot be a series-level property.
- **Verified meaning of team_a: UNKNOWN.**

## EMPIRICAL PATTERN

- Completed series in staging (2022S1-2026S2): n=1466, team_a wins 804 (54.8%). Per season x stage: `team_a_bias.csv`.
- Venue cross-tab (`team_a_venue_crosstab.csv`): team city = the `location_name` value that prefixes the team name (e.g. 北京WB -> 北京). `location_name` is '0' (not recorded) for every 2022-2025 series, so venue analysis covers 2026 only (home-city venues appear from KPL2026S1).
  - BOTH_SAME_CITY: n=6, team_a win rate 66.7%
  - NEITHER_CITY_HOSTS: n=112, team_a win rate 42.0%
  - TEAM_A_CITY_HOSTS: n=133, team_a win rate 64.7%
  - TEAM_B_CITY_HOSTS: n=21, team_a win rate 42.9%
  - VENUE_NOT_RECORDED: n=1194, team_a win rate 55.1%
- When exactly one team's city hosts, that team is team_a in 86.4% of series.
- 2026 playoffs/finals vs the last group-stage standings (`team_a_playoff_standings_crosstab.csv`): team_a had the better standing in 62.5% of 24 ranked series (ranks compared within the source's group order).

## UNKNOWN / INFERENCE

- Any reading of team_a as 'home', 'host' or 'higher seed' is INFERENCE from the patterns above, not source semantics. For 2022-2025 there is no venue field at all, and in 2026 many series are at venues neither team is named after (NEITHER_CITY_HOSTS); there the order is unexplained.
- The 2026 host pattern and the playoff-standing pattern rest on small samples (host n=154, ranked playoff n=24).
- The win-rate gap alone is not used as evidence of meaning.
- Models must stay symmetric in team_a/team_b unless a side/seed feature is added as a separate, leakage-safe experiment.
