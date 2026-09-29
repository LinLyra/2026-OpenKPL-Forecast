# v0.5 — Player + Roster Prospective Modeling Benchmark

**Primary question.** Does pre-series player strength, roster continuity, bench depth or player-hero
experience add out-of-time predictive information beyond team-level Elo (frozen v0.3.1 B5)?

**Answer on this data: no measurable gain.**

- Every pre-specified model B6–B12 is significantly **worse** than B5 on log loss and Brier. The 95% paired-bootstrap intervals exclude zero for all of them.
- The only models that match B5 are small post-hoc exploratory combinations (X2, X3). They tie B5 but do not beat it: the log-loss CIs are centred on zero.
- Player ratings carry real signal, since player Elo alone roughly matches team Elo. But they are about 0.87 correlated with the B5 logit, so they are largely redundant with team strength.

Nothing is frozen. Rebuild with `.venv/bin/python -m openkpl.player_model.run` (offline; it verifies
`v05_experiment_lock.json` before and after the run).

## Target, population, holdout

- The target is P(team_a wins series), with the same label and the same label-eligible, completed-series universe as v0.3.1.
  `team_a` is not interpreted (not home, not blue side, not seed).
- The prediction unit is the **series**.
- The 1,330 development series with a frozen B5 out-of-time prediction (2022S2–2026S2) are used for training. The 1,194 series in 2023S1–2026S2 are
  **evaluation rows, identical for every model**.
- 2022S1 has no lineups and no B5 prediction, so it is burn-in only.
- The prospective holdout (start_time ≥ 2026-09-28, including the 2026 Annual Finals, KPL2026S3) is filtered out in code and tested.
  The source contains no such rows.

## Information-availability policy

- A series at start_time t sees only series with start_time < t. Series with the same start_time are featurized together, before any of them updates the state.
- **PRE_SERIES_SAFE** features (listed in `feature_dictionary.csv`) use earlier series only. Nothing from the target series is used: not its lineup, heroes, games, rotation or result.
- **RETROSPECTIVE_ONLY** features, prefixed `oracle_`, use the actual target-series lineup.
  - They live only in `reports/player_model/oracle/`.
  - They are refused by `models.assert_deployable`, and a test enforces this.

## B5 input

- B5 predictions are read from the locked `reports/benchmark/v2026_09_28/temporal_predictions.parquet`.
- Each was produced online with hyperparameters selected on data before its validation season, so logit(p_B5) is pre-series safe on training rows too.
- B5 itself is never refit or retuned.

## Player ratings

Equations are also in `src/openkpl/player_model/ratings.py`.

- Every player starts at BASE = 1500 with n = 0.
- The rating used for prediction shrinks toward the league mean: eff = 1500 + (R − 1500)·n/(n + m).
- Team strength is S = mean eff over the lineup.
- **P1 (win Elo):** E_A = 1/(1+10^((1500 − S_A)/400)), and E_B likewise. Each side is judged against a league-average opponent.
- **P2 (opponent-adjusted):** E_A = 1/(1+10^((S_B − S_A)/400)), E_B = 1 − E_A. Beating a strong lineup moves ratings more than beating a weak one.
- The update for each player i in L_A is R_i += K(y_A − E_A) and n_i += 1; B is symmetric.
- **Game mode** updates once per game that has a known winner and both lineups, in game order.
- **Series mode** updates once per series with the series label, over the players who appeared.
- Updates happen only after a series is complete.

Selection, per outer fold:

- The grid is 32 rating configurations: P1/P2 × game/series × K ∈ {8, 16, 32, 64} × m ∈ {0, 10}.
- This is crossed with 4 expected-core methods: FREQ5, DECAY, LAST, HIST.
- The objective is inner log loss of the B7-type model. It is fit on the training seasons except the last, and scored on the last training season.
- 2023S1 has only one earlier lineup season, so it uses the a-priori default (P2, game, K = 16, m = 10, DECAY).
- The selections in `fold_selections.csv` are unstable across folds. That is itself evidence that the signal is weak or redundant.

## Features

All features are computed per team and entered as a team_a − team_b difference. Day counts are differenced as log1p.

- **Expected core.** The pool is players who appeared for the team in its last 10 series (all series for HIST) and whose latest
  appearance anywhere was for this team.
  - FREQ5 ranks by games in the last 5 series.
  - DECAY ranks by games weighted 0.5^(j/3) over the last 20 series.
  - LAST ranks by games in the last series.
  - HIST ranks by games over all earlier series.
  - Ties are broken by DECAY score, then player_id. The core is the top 5, and the bench is ranks 6 and below.
- **PLAYER:**
  - expected_core_strength, top5_player_rating_mean (the 5 highest ratings in the pool) and top5_player_rating_sum;
  - recent_player_rating_mean (players in the last series);
  - player_rating_max/min/std (over the core).
  - The sum is stored but excluded from models, because it is collinear with the mean.
- **ROSTER:**
  - returning_players_from_previous_series, meaning the overlap of the last two series;
  - core5_overlap_previous_series;
  - rolling unique players, lineup changes and rotation rate (share of series with more than 5 players) over the last 5 series;
  - roster_stability_{3,5,10}_series, the share of player-games taken by the 5 most-used players;
  - days since the core players' last appearance, and days since the team's last series;
  - new_player_count and recently_returned_player_count, both about the last series;
  - is_first_series_of_season.
- **BENCH:**
  - player6_rating, player7_rating, bench_mean_rating, bench_gap_to_core;
  - historical_substitution_frequency (last 10 series);
  - historical_performance_when_rotating, a shrunk win rate (w + 2.5)/(n + 5) over series with more than 5 players in the last 20;
  - historical_number_of_players_used.
- **HERO:** built from core players' strictly earlier kplow appearances, with the same logic as `player_hero_temporal` and with missing heroes excluded.
  - player_hero_experience_depth: heroes with at least 3 games.
  - player_hero_diversity: entropy of the hero distribution.
  - weighted_player_hero_winrate: games-weighted, with each hero's win rate shrunk as (w + 2.5)/(d + 5).
  - weighted_player_hero_games.
  - team_hero_depth: heroes with at least 3 games over the team's last 10 series.
  - hero_pool_concentration: HHI of the hero distribution.
  - Roles are not used: positions are 0 before 2025S3.

## Model ladder

Every model uses a pipeline fit on the training fold only: median imputation plus missingness indicators, then clipping to the training 0.5%/99.5% quantiles, then standardization.

| model | content |
|---|---|
| B5 | frozen v0.3.1 prediction |
| B5R | control: logistic on logit(B5) only, i.e. recalibration without new information |
| B6–B10 | B5R + roster / player / player+roster / +bench / +hero; L2 logistic, C = 1 fixed a priori |
| B11 | L2 logistic on all safe features; C selected by inner last-season holdout from {0.01, …, 3} |
| B12 | HistGradientBoosting on the same features (LightGBM and XGBoost are not installed, so no dependency was added); max_iter/max_depth selected by inner holdout |
| X1–X3 | **post-hoc exploratory** (added after the ladder results): X1 player-Elo core strength only; X2 B5 + core strength; X3 fixed 50/50 logit average of B5 and X1 |

## Results

The evaluation set is 1,194 series, 2023S1–2026S2, the same rows for every model. Probabilities are raw.

| Model | LogLoss | Brier | Acc | AUC | ECE | Slope | ΔLL vs B5 [95% CI] | ΔBrier vs B5 [95% CI] |
|---|---|---|---|---|---|---|---|---|
| B5 | 0.6228 | 0.2164 | 0.658 | 0.707 | 0.018 | 0.90 | — | — |
| B5R | 0.6239 | 0.2169 | 0.653 | 0.705 | 0.025 | 0.96 | +0.0010 [−0.0020, +0.0040] | +0.0005 [−0.0007, +0.0017] |
| B6 | 0.6407 | 0.2234 | 0.652 | 0.687 | 0.035 | 0.76 | +0.0179 [+0.0073, +0.0284] | +0.0070 [+0.0028, +0.0113] |
| B7 | 0.6455 | 0.2267 | 0.621 | 0.675 | 0.052 | 0.71 | +0.0227 [+0.0118, +0.0333] | +0.0103 [+0.0056, +0.0148] |
| B8 | 0.6615 | 0.2327 | 0.626 | 0.663 | 0.067 | 0.60 | +0.0387 [+0.0254, +0.0526] | +0.0163 [+0.0107, +0.0221] |
| B9 | 0.7003 | 0.2441 | 0.602 | 0.640 | 0.097 | 0.42 | +0.0775 [+0.0543, +0.1016] | +0.0277 [+0.0198, +0.0357] |
| B10 | 0.7071 | 0.2461 | 0.605 | 0.642 | 0.099 | 0.40 | +0.0842 [+0.0595, +0.1098] | +0.0298 [+0.0213, +0.0384] |
| B11 | 0.6659 | 0.2311 | 0.636 | 0.667 | 0.050 | 0.58 | +0.0430 [+0.0220, +0.0636] | +0.0147 [+0.0075, +0.0213] |
| B12 | 0.6570 | 0.2303 | 0.631 | 0.664 | 0.035 | 0.66 | +0.0341 [+0.0181, +0.0503] | +0.0139 [+0.0073, +0.0203] |
| X1* | 0.6402 | 0.2238 | 0.635 | 0.683 | 0.032 | 0.87 | +0.0174 [+0.0015, +0.0318] | +0.0074 [+0.0010, +0.0136] |
| X2* | 0.6230 | 0.2166 | 0.657 | 0.706 | 0.032 | 0.95 | +0.0002 [−0.0054, +0.0056] | +0.0002 [−0.0021, +0.0024] |
| X3* | 0.6231 | 0.2165 | 0.653 | 0.707 | 0.034 | 1.01 | +0.0002 [−0.0076, +0.0075] | +0.0001 [−0.0031, +0.0032] |

\* Post-hoc exploratory.

- Uncertainty comes from a paired, series-level bootstrap stratified by validation season (2,000 resamples), in `bootstrap_deltas.csv`.
- Slope below 1 on B7–B12 means the added features make predictions over-confident out of time.
- Sensitivity check, descriptive only: excluding 2023S1, whose training data is 2022S2 only, every B6–B12 model is still worse than B5 (B11 +0.017, B6 +0.016). X2 and X3 move to −0.0006 and −0.0002.

Season by season (`season_metrics.csv`), feature models beat B5 only occasionally:

- 2025S3 is best for B8/B9, at 0.479 against 0.495, but it has only 53 series.
- In 2025S2, B11 and B12 score 0.625–0.626 against 0.645.
- In 2026S2, B6 scores 0.637 against 0.644.
- They lose badly in 2023S1 and 2023S2 (small training sets) and in 2026S1.

## Ablation and importance

- Against the team-only control B5R, adding any group worsens log loss:
  - Roster +0.017, Player +0.022, Player+Roster +0.038, +Bench +0.077, +Hero +0.083.
- Leave-one-group-out on B11 shows that removing BENCH improves B11 by 0.023, and removing ROSTER improves it by 0.015. BENCH is the most harmful group; its bench-rating features are frequently missing (teams with fewer than 6 or 7 pool players).
- Grouped permutation importance (within each validation season, 20 repeats) shows that B11 leans heavily on PLAYER and BENCH. Relying on them does not translate into a better out-of-time score.
- For B12, only TEAM (logit B5, +0.061) and to a small degree PLAYER (+0.010) matter.
- Importance is descriptive, not causal.

## Oracle (ORACLE / NON-PROSPECTIVE — not deployable, never on the leaderboard)

| model | LL | Brier | ΔLL vs B5 [95% CI] |
|---|---|---|---|
| O1 B5 + actual player identities (±1 indicators, L2 C = 0.3) | 0.6592 | 0.2313 | +0.036 [+0.019, +0.054] |
| O2 B5 + actual-lineup pre-series ratings | 0.6273 | 0.2180 | +0.005 [−0.006, +0.015] |
| O3 B5 + actual rotation (players used, lineup changes, entrants after game 1) | 0.6277 | 0.2189 | +0.005 [−0.003, +0.012] |

Even perfect knowledge of who plays does not improve on team Elo in this data. That puts a low ceiling on what pre-series lineup announcements could add.

## Calibration

- Calibrators are fit only on a model's own out-of-time predictions from earlier validation seasons.
  - Platt needs at least 1 earlier season.
  - Isotonic needs at least 500 earlier predictions, so it applies from 2024S3.
- The selected method for each season is whichever beat raw on the earlier seasons it covered.
- For B5, Platt on its covered seasons gives 0.6200 against raw 0.6228 on 1,058 rows, but the prospective selection kept raw.
- Platt narrows but does not close the gap for B7–B11.
- Selection-based calibration does not change any conclusion (`calibration_metrics.csv`).

## Failure cases

- **2023S1:** trained on 2022S2 only (136 series). Multi-feature models produce extreme probabilities; the worst series are KPL2023S1M6W5D1 (B11 p = 0.005, team_a won) and KPL2023S1M5W2D2 (p = 0.988, lost).
- **First series of a season** (103 rows): all models do better there than elsewhere, but feature models lose more to B5 (B11 0.607 against B5 0.576).
- **Initial run (pre-robustness), kept in `initial_run_metrics.csv`:** it used raw day counts and no clipping, and extrapolated to p = 3e-5 (B9 log loss 0.79). The log1p and training-quantile clipping fix was introduced after diagnosing that failure. It is the only change made after seeing evaluation results, apart from the labeled exploratory X1–X3.

## Missing data

- `missing_data_by_season.csv` and `missing_data_series.csv` list 795 series with at least one missing difference feature.
- The main causes are structural:
  - player6/player7 are missing when the pool has fewer than 6 or 7 players;
  - features are missing for teams with no earlier lineup history, such as early 2022S2 and new franchises.
- No rows are dropped. Values are median-imputed with indicators, fit on the training fold.

## 2026 rotation readiness (descriptive; `rotation_readiness_2026.csv`)

- 2026S1–S2 teams used more than 5 players in 0–18% of series.
- Bench ratings are often **higher** than core ratings (for example AG, WB, JDG). The pool can include veterans or departed players who have not yet appeared for another team.
- The Annual Finals rotation rule is not encoded or verified, and nothing here predicts it.

## Recommendations (not frozen)

- Keep **B5** as the deployable reference.
- **X2** (B5 + a single player-core-strength term) and **X3** (a fixed 50/50 B5/player-Elo average) are candidates for a prospective ensemble only. They tie B5 and need confirmation on genuinely new data, since they were added post hoc.
- Do not carry B6–B12 forward.
