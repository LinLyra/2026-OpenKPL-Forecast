# 2026 KPL Annual Finals — Post-Tournament Evaluation Plan (PRE-REGISTERED)

Written 2026-09-29, before the first Annual Finals series (2026-10-02). No Annual Finals outcome existed or was
consulted. **This plan must not be modified after any outcome is observed.** Deviations required by events
(e.g. forfeits) are handled only by the rules in §6 and must be reported, never silently applied.

## 1. What is scored

The frozen v1.0 PRIMARY forecast, exactly as stored:

| artifact | identity |
|---|---|
| `reports/tournament/PREDICTION_LEDGER_2026.csv` | 36 Stage 1 series; content SHA-256 (excluding `generated_at`) `dfe42a35d4b9b458928f9ae2c61d3c1a0deacbfcf2ba5a3f7760d4fc47a90638` |
| `data/processed/tournament/frozen_team_strength_2026.parquet` | SHA-256 `49cacffc24c1eca84f78e4c1772e38b4a7be0d9ddca09bbdca78d85d69907dc7` |
| `data/processed/tournament/pairwise_bo7_probabilities.parquet` | frozen pairwise BO7 probabilities (= BO5, raw B5) |
| `reports/tournament/team_forecast_2026.csv` | stage / final / championship probabilities (PRIMARY columns) |
| `reports/tournament/knockout_forecast.csv` | terminal-stage distribution per team |

Before scoring, `openkpl.tournament.lock.check()` must return `[]` and all hashes above must match. If any do not,
the evaluation is reported as **INVALID (artifact modified)** and nothing is scored.

Sensitivity columns (CONSERVATIVE, AGGRESSIVE, BO7_SENSITIVITY) are scored in a separate, clearly labeled
SECONDARY table. They can never replace PRIMARY.

## 2. Series-level metrics

**2a. Stage 1 (primary series evaluation).** Score the 36 ledgered BO5 series with `p_team_a` from the ledger.
The outcome is y = 1 if `team_a` wins the series.

- log loss −[y ln p + (1 − y) ln(1 − p)] (natural log), averaged.
- Brier (p − y)², averaged.
- Accuracy: the favorite (p > 0.5) wins. Report the favorite's mean p next to it.
- Calibration:
  - reliability table with 5 equal-width favorite-probability bins (0.5–0.6, …, 0.9–1.0);
  - calibration intercept and slope from logistic regression of y on logit(p). With n = 36 these are
    descriptive only; report 95% intervals.
- Reference points (not decision rules):
  - coin flip (log loss 0.6931, Brier 0.25);
  - historical out-of-time B5 (log loss 0.6256, Brier 0.2177, accuracy 0.652).
  - 95% interval via bootstrap over series (10,000 resamples, seed 20261115).

**2b. Breakthrough and knockout series (conditional on the realized pairing).** For every BO7 series actually
played, score the frozen pairwise BO7 probability for that pairing. The pairwise matrix was frozen before the
tournament, so this is prospective *conditional on the pairing*. It is reported separately from 2a and
labeled "conditional-on-pairing".

## 3. Stage advancement score

For each of the 12 teams, the realized Stage 1 outcome falls in one of three classes: {direct knockout,
breakthrough, stage 1 elimination}. Masters cannot take the third class.

- multi-class log score: −ln P(realized class), averaged over teams;
- multi-class Brier over the three classes;
- binary Brier and log score for each milestone:
  - P(knockout), P(upper semi-final), P(upper final), P(final), P(champion);
  - using the PRIMARY columns of `team_forecast_2026.csv` / `knockout_forecast.csv`.
- ranked probability score (RPS) over the ordered terminal stages:

  STAGE1 < BREAKTHROUGH < LB_R1 < LB_R2 < LB_SF < LB_F < FINAL < CHAMPION

  This uses the `p_terminal_*` columns. Reference: a uniform "every team equal" forecast computed from the
  same format (the NEUTRAL counterfactual is **not** a reference).

## 4. Championship score

- log score −ln P(realized champion) (PRIMARY);
- 12-team Brier Σ(p_i − 1[i = champion])²;
- reference: uniform 1/12 (log score ln 12 = 2.485);
- the realized champion's rank in the PRIMARY ordering.

A single tournament is **one** observation. No claim of model superiority or inferiority is made from the
championship score alone.

## 5. Structural questions (descriptive)

Record whether:
- the official Stage 1 ranking rule matched T1 (wins → game differential), T2, T3 or none;
- the breakthrough selection pool matched ELITE_2_TO_5;
- the realized draw satisfied K1, K2 and/or K3.

This documents which pre-registered scenario was correct. It does **not** re-score PRIMARY with a different
scenario. Such a re-score may appear only as a labeled SECONDARY table.

## 6. Edge cases (fixed now)

- Forfeit / walkover / series not played: excluded from series metrics and listed. Stage and championship scores
  use the officially recorded advancement.
- Roster changes, loans or rule changes after the cutoff: no adjustment. Scored as-is and listed as a limitation.
- Official schedule changes (dates or order): series are matched by team pair (each Master–Elite pair occurs
  exactly once in Stage 1), never by date.
- If Stage 1 is not a complete 36-series cross-group round robin: score the played ledger series and report the
  structural deviation.

## 7. Outputs (to be created after the tournament)

- `reports/tournament/POST_TOURNAMENT_EVALUATION.md`
- `reports/tournament/post_tournament_series_scores.csv`
- `reports/tournament/post_tournament_stage_scores.csv`

Scoring code must read the frozen artifacts read-only, and the tournament lock must pass before and after scoring.
