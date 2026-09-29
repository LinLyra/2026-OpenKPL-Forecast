# Web Data Binding Audit — 2026 KPL Annual Finals forecast site

Audit date: 2026-09-29. Freeze bound: `v1.0-prospective-freeze-2026-09-29` (content commit `aaf2d280…`, tagged commit
`7f96669a…`). The website is read-only with respect to research artifacts.

## Data flow

```
freeze/v1.0/*, reports/*, config/*.yaml   (frozen, read-only)
        │  web/scripts/build-web-data.mjs  (one-way; parses, never recomputes a probability)
        ▼
web/data/generated/{forecast,teams,matchups,tournament,methodology}.json
        │  each file: source_file[], source_sha256[], generated_at, data
        ▼
React components (import generated JSON only; no component reads a research file)
```

The adapter refuses to build if `PRIMARY_FORECAST.csv` does not match `primary_forecast_sha256` in the freeze manifest.
`npm run data:check` re-hashes every recorded source and fails on any drift.

## Where every displayed number comes from

| Website element | Generated file → field | Research artifact → column | Kind |
|---|---|---|---|
| Championship probability (hero, field, all pages) | `forecast.json` → `teams[].championship_probability` | `freeze/v1.0/PRIMARY_FORECAST.csv` → `championship_probability` | model-derived |
| Final probability | `forecast.json` → `final_probability` | same → `final_probability` | model-derived |
| Direct qualification probability | `forecast.json` → `direct_knockout_probability` | same → `direct_knockout_probability` | model-derived |
| Breakthrough entry / win | `forecast.json` → `breakthrough_probability`, `breakthrough_win_probability` | same | model-derived |
| Stage 1 elimination | `forecast.json` → `stage1_elimination_probability` | same | model-derived |
| Reach knockout | `forecast.json` → `knockout_probability` | same | model-derived |
| Upper semifinal / upper final / drop to lower / lower final | `forecast.json` | same → `upper_semifinal_probability`, `upper_final_probability`, `drop_to_lower_bracket_probability`, `lower_final_probability` | model-derived |
| Monte Carlo SE | `forecast.json` → `mc_se_*` | same → `mc_se_knockout`, `mc_se_final`, `mc_se_champion` | model-derived |
| Frozen strength rating | `forecast.json` → `frozen_b5_rating` | same → `frozen_b5_rating` (equals `pre_tournament_rating` in the frozen strength parquet) | model-derived |
| Upper-final win, champion given knockout, terminal-stage distribution ("path risk") | `tournament.json` → `simulated.teams[]` | `reports/tournament/knockout_forecast.csv` → `p_upper_final_win`, `p_champion_given_knockout`, `p_terminal_*` | model-derived |
| Breakthrough win given entry | `tournament.json` → `p_breakthrough_win_given_entry` | `reports/tournament/breakthrough_scenarios.csv` → `p_bt_win_given_bt__PRIMARY` | model-derived |
| Expected series / BO7 series, champion given direct vs breakthrough, breakthrough elimination risk | `tournament.json` | `reports/tournament/path_metrics.csv` | model-derived |
| Stage 1 group-rank distribution, expected wins / game differential | `teams.json` → `p_group_rank`, `expected_series_wins`, `expected_game_diff` | `reports/tournament/stage1_forecast.csv` | model-derived |
| Head-to-head series win probability (Matchup Lab) | `matchups.json` → `bo5[i][j]` | `reports/tournament/bo5_matchup_matrix.csv` (identical to `bo7_matchup_matrix.csv`; max difference 0) | model-derived |
| Stage 1 fixtures, dates and per-series probability | `matchups.json` → `stage1_ledger[]` | `reports/tournament/PREDICTION_LEDGER_2026.csv` | model-derived probability; dates are a SECONDARY_TRANSCRIPTION of the official schedule image |
| Sensitivity (conservative / aggressive / BO7) championship probabilities | `forecast.json` → `teams[].sensitivity_only` | `PRIMARY_FORECAST.csv` → `championship_probability_conservative/_aggressive/_bo7_sensitivity` | model-derived, SENSITIVITY ONLY, shown only on the methodology page |
| Historical roster usage (players per series, ≥6/≥7-player series) | `teams.json` → `historical_roster_usage_descriptive` | `reports/tournament/master_rotation_readiness.csv` | descriptive history, NOT used in the forecast |
| Unresolved rules and their max probability deltas | `tournament.json` → `unresolved_rules` | `freeze/v1.0/FREEZE_MANIFEST.json` → `unresolved_rules` (from `rule_materiality_v10a.csv`) | model-derived sensitivity |
| B0–B5 benchmark log loss, Brier, accuracy, AUC | `methodology.json` → `benchmark.models` | `reports/benchmark/v2026_09_28/temporal_metrics.csv` | model evaluation |
| Game / draft / series-state / sequential-draft decisions | `methodology.json` → `game_draft_decisions` | `reports/game_draft_model/v06_game_draft_benchmark.md` (Decision table) | research decision |
| BO7 correction decision | `methodology.json` → `bo7_audit_decision` | `reports/bo7_audit/run_summary.json` → `decision` | research decision |
| Player/roster model decision | `methodology.json` → `player_model_recommendation` | `reports/player_model/v05_player_roster_benchmark.md` | research decision |
| Home championship field (v2.1, 1,000 dots) | `forecast.json` → per-team `championship_probability` | `freeze/v1.0/PRIMARY_FORECAST.csv` → `championship_probability` | layout only (largest-remainder dot allocation; legend shows stored values) |
| Methodology spine "1,466 场系列赛" (v2.1) | `forecast.json` → `freeze.data_version` | `freeze/v1.0/FREEZE_MANIFEST.json` → `data_version` | parsed from stored string |
| Tactical map positions (v2.1) | `data/map/tacticalScenarios.ts` (`kind: "illustration"`) | none — authored illustration | not data; labelled 战术示意 / non-tracking |
| 170 / 170 tests, git tag, commits | `forecast.json` → `freeze`, `methodology.json` → `freeze` | `freeze/v1.0/POST_FREEZE_VERIFICATION.json`, `FREEZE_MANIFEST.json` | freeze metadata |
| Freeze ID, cutoff, model version, SHA-256s | `forecast.json` → `freeze` | `freeze/v1.0/FREEZE_MANIFEST.json` | freeze metadata |
| 1,000,000 simulations | `forecast.json` → `teams[].n_simulations` | `PRIMARY_FORECAST.csv` → `n_simulations` | freeze metadata |

## Tournament rules (not model output)

| Website element | Source | Verification status |
|---|---|---|
| Groups, seeds (Master 1–6, Elite 7–12) | `config/2026_annual_finals_rules.yaml` → `teams` (R01) | VERIFIED_OFFICIAL (seed order within group from Wikipedia points table) |
| Stage dates 10-02..10-18 / 10-20..10-22 / 10-27..11-08 / 11-14 | YAML R02 | VERIFIED_OFFICIAL |
| Stage 1 format BO5 cross-group round robin; advancement | YAML R03, R05 | VERIFIED_OFFICIAL |
| Master rotation rule | YAML R07 | VERIFIED_OFFICIAL |
| Breakthrough BO7 single elimination; sequential choice | YAML R08, R09 | VERIFIED_OFFICIAL |
| Breakthrough selection detail | YAML R10 | SECONDARY_INTERPRETATION (unresolved; IMMATERIAL) |
| Knockout BO7 double elimination, draw with M1/M2 seed slots | YAML R11, R13 | VERIFIED_OFFICIAL (seed-slot meaning unresolved) |
| Knockout bracket wiring and match dates | YAML `knockout_bracket` (R12) | SECONDARY_TRANSCRIPTION (unresolved; IMMATERIAL) |
| Final BO7 on 11-14; final venue (成都) | YAML R14 | SECONDARY_TRANSCRIPTION |
| Stage 1 venue 广州体育馆2号馆 | `reports/tournament/rule_source_registry.csv` GATE_A_STAGE1_VENUE | VERIFIED_OFFICIAL_2026 |

## Desired visualization fields that do NOT exist in any frozen artifact

| Field | Status on the site |
|---|---|
| Team logos | not available → generated monogram placeholder; `public/assets/teams/` empty; `ASSET_MANIFEST.example.json` schema provided |
| Team brand colours | not available → neutral palette (Master = gold, Elite = steel); no invented brand colours |
| 2026 Annual Finals rosters (7-player lists), player IDs, real names, portraits, positions | not available → one "unavailable" statement on the Roster tab; no players are shown |
| Starter / substitute / rotation assignments | not available → the Roster tab (`TeamRoster`) states that rosters are unavailable; rotation is never inferred |
| Player positional tracking / map coordinates | does not exist → tactical map is labelled 战术示意 / TACTICAL ILLUSTRATION only |
| Official English team names | not in artifacts → UI transliterations flagged as non-official in `teamPresentation.ts` |
| Team city for KSG | not in the official name → omitted |
| Knockout-stage venue | not in any artifact → not shown |
| Realized knockout bracket / any match result | deliberately absent (post-cutoff, and none had been played at freeze) |
| Per-stage "format win probability" distinct for BO5 vs BO7 | not distinct: B5 is format-agnostic, so the site shows a single series probability |
| Match start times | not modelled (YAML: "times not modeled") → dates only |

## Values requiring external presentation data (future)

Logos, portraits, verified 2026 rosters and positions, official English names, team colours and venue imagery. Each must
be added through `web/data/ASSET_MANIFEST.example.json` (source URL, source type, licence/usage note, retrieval date) and
`web/data/teamPresentation.ts` (`sourceUrls` required per player). None of these can change any probability.

## Guarantees

- No component computes a probability. The Matchup Lab looks up `bo5[i][j]`; nothing is derived from match results.
- No Annual Finals outcome exists in any consumed artifact (freeze checks: 0 Annual Finals rows, 0 post-cutoff rows).
- Sensitivity values appear only in a clearly labelled sensitivity panel on the methodology page.
