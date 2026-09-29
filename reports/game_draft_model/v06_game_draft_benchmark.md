# v0.6 — Game-level strength, series probability and draft information

Nothing is frozen, no tournament is simulated, and no Annual Finals outcome is present (filtered in code and tested).

- Rebuild with `.venv/bin/python -m openkpl.game_draft_model.run`. It verifies `v06_experiment_lock.json`, which includes the v0.3/v0.3.1, Phase A/B and v0.5 locks, before and after the run.
- No POST_HOC model or feature was added. Every model below was specified before its results were seen.

## Experiment A — game-level team strength

**Eligibility:** games with a deterministic parent series, both teams known and a known **kplow** winner.

| season | games | eligible |
|---|---|---|
| 2022S1 | 554 | 0 (no source winners) |
| 2022S2 | 571 | 416 |
| 2023S1 | 579 | 570 |
| 2023S2 | 561 | 561 |
| 2024S1 | 554 | 553 |
| 2024S2 | 573 | 573 |
| 2024S3 | 240 | 240 |
| 2025S1 | 574 | 574 |
| 2025S2 | 562 | 562 |
| 2025S3 | 237 | 237 |
| 2026S1 | 573 | 573 |
| 2026S2 | 562 | 562 |

- The evaluation set is the 5,005 games in 2023S1–2026S2.
- Folds are expanding by season. Hyperparameters are chosen by online PRE-SERIES game log loss over training games only.

**Modes:**
- **PRE-SERIES** freezes ratings at series start, so no game of the current series is used.
- **LIVE-SERIES** uses games 1..k−1 of the current series.

Equations are in `src/openkpl/game_draft_model/elo.py`.

Out-of-time game log loss; Δ is against G1 in the same mode, with a series-clustered paired bootstrap (2,000 resamples):

| model | PRE LL | Δ vs G1 [95% CI] | LIVE LL | params |
|---|---|---|---|---|
| G0 0.5 | 0.6931 | +0.021 | 0.6931 | 0 |
| G1 vanilla | 0.6718 | — | 0.6703 | 1 (K) |
| G2 decay | 0.6707 | −0.0011 [−0.0030, +0.0009] | 0.6694 | 2 |
| G3 season reversion | **0.6698** | −0.0020 [−0.0039, −0.0001] | **0.6686** | 2 |
| G4 series-aware | 0.6700 | −0.0018 [−0.0038, +0.0003] | 0.6700 | 2 |
| G* per-fold best | 0.6712 | −0.0006 [−0.0024, +0.0013] | 0.6706 | 1–2 |
| G5 G* + B5 (game-converted) | 0.6707 | −0.0012 [−0.0036, +0.0013] | 0.6701 | 3 |

- LIVE mode gains only about 0.001–0.0015 over PRE mode (G1: −0.0015 [−0.0025, −0.0004]).
- Choosing a family per fold (G*) is unstable and does no better than fixing G3.
- A sensitivity run that fills missing kplow winners with WZRY winners changes game log loss by less than 0.0006. It is labeled separately in `game_model_metrics.csv` and not used in any primary result.

## Series probability (1,194 series; Δ vs B5 with a series-level bootstrap)

The exact best-of-(2n−1) formula, P = Σ_{k=n}^{2n−1} C(2n−1,k) p^k (1−p)^{2n−1−k}, is implemented for BO3, BO5 and BO7. It is tested against brute-force enumeration.

| model | LL | Brier | AUC | slope | ΔLL vs B5 [95% CI] |
|---|---|---|---|---|---|
| S0 B5 | 0.6228 | 0.2164 | 0.707 | 0.90 | — |
| S1 game Elo → constant-p exact | 0.6231 | 0.2163 | 0.708 | 0.89 | +0.0003 [−0.0101, +0.0107] |
| S2 + game-number effects | 0.6247 | 0.2172 | 0.706 | 0.90 | +0.0019 [−0.0087, +0.0126] |
| S3 + series-state transitions (exact recursion) | 0.6241 | 0.2171 | 0.705 | 0.96 | +0.0013 [−0.0092, +0.0115] |
| S4 B5 + S1 hybrid | 0.6234 | 0.2164 | 0.707 | 0.89 | +0.0006 [−0.0038, +0.0053] |
| S1F S1 recalibrated by format | 0.6268 | 0.2190 | 0.697 | 0.94 | +0.0040 [−0.0075, +0.0160] |

- The game-level route **ties** B5 at series level.
- Adding series state or game-number structure makes things slightly worse.

## BO5 vs BO7

| format | series | games | game favorite predicted / observed | B5 series favorite predicted / observed | S1 predicted / observed | slope S0 / S1 |
|---|---|---|---|---|---|---|
| BO5 | 1,032 | 4,107 | 0.592 / 0.583 | 0.668 / 0.651 | 0.663 / 0.648 | 0.83 / 0.81 |
| BO7 | 162 | 898 | 0.563 / 0.588 | 0.617 / 0.698 | 0.629 / 0.691 | 2.04 / 1.90 |

- In BO7 (playoff) series, favorites win more often than both B5 and the constant-p mapping predict.
- The interaction term logit(S1) × BO7 is +1.09 (SE 0.34, p = 0.001; in-sample on out-of-time predictions).
- BO5 predictions are slightly over-confident, with slope about 0.8.
- Format-specific recalibration (S1F) did **not** help out of time. There are only about 16 BO7 series per season, so early folds estimate the BO7 terms from very few series, and BO7 log loss went from S1's 0.575 to 0.586.
- For the tournament simulator: **a BO7 is not a longer BO5**, but the correction cannot yet be estimated reliably.

## Series-state analysis (association, not causal)

In-sample, with PRE-SERIES strength as the control and series-clustered standard errors:
- score difference: +0.108 per game of lead (p = 0.0002);
- match point difference: +0.148 (p = 0.007). This is the mirror image of elimination difference;
- game number, previous-game winner and decider × strength: not significant.

Out of time, every variable set's 95% CI for Δ log loss includes zero:
- score_diff −0.0014 [−0.0031, +0.0004];
- ALL +0.0011.

All are **DISCARDED** per the pre-registered rule. The in-sample score effect largely reflects PRE-SERIES strength being stale within a series, which LIVE mode captures directly.

## Experiment B — draft information (1,942 identified games; primary target is the kplow winner, 1,799 games)

- WZRY's winner is never a feature or a target (tested).
- Evaluation covers 1,426 games in 2023S1 (560), 2023S2 (555) and 2024S1 (311).

| fold | training games | notes |
|---|---|---|
| 2023S1 | 373 | shrinkage, recency and C fall back to a-priori defaults (single training season) |
| 2023S2 | 933 | |
| 2024S1 | 1,488 | |

- **D0:** each fold picks, by training log loss, among the raw pre-draft probabilities: B5 converted to game probability, G* PRE, and G* LIVE. B5 converted to game probability was selected in every fold.
- **Shrinkage (K, min_n):** selected per fold as (10, 0) default, then (2, 5), then (2, 0).
- **Recency half-life:** inf, then 60 days, then inf.

| model | features | params | LL | Brier | ΔLL vs D0 [95% CI] | P(beats D0) |
|---|---|---|---|---|---|---|
| D0 pre-draft | 0 | 0 | 0.6706 | 0.2389 | — | — |
| D0R recalibrated control | 1 | 2 | 0.6719 | 0.2395 | +0.0013 [−0.0008, +0.0034] | 0.11 |
| D1 + hero strength | 4 | 5 | 0.6697 | 0.2384 | −0.0009 [−0.0039, +0.0020] | 0.74 |
| D1R recency-weighted hero strength | 4 | 5 | 0.6707 | 0.2389 | +0.0001 [−0.0029, +0.0032] | 0.48 |
| D2 + team×hero familiarity | 6 | 7 | 0.6705 | 0.2387 | −0.0001 [−0.0050, +0.0045] | 0.53 |
| D3 + synergy | 8 | 9 | 0.6712 | 0.2391 | +0.0006 [−0.0056, +0.0066] | 0.44 |
| D4 + counter | 9 | 10 | 0.6723 | 0.2395 | +0.0016 [−0.0048, +0.0078] | 0.32 |
| D5 regularized, all | 10 | 11 | 0.6723 | 0.2395 | +0.0017 [−0.0047, +0.0080] | 0.33 |
| D6 gradient boosting | 10 | up to 595 | 0.6879 | 0.2464 | **+0.0173 [+0.0054, +0.0295]** | 0.00 |

- The feature counts exclude missingness indicators, which the parameter counts include.
- Against the recalibrated control D0R, D1 improves by −0.0022 [−0.0044, +0.0000], which beats D0R in 97% of resamples. That is borderline, not established.
- By season (log loss):

  | model | 2023S1 | 2023S2 | 2024S1 |
  |---|---|---|---|
  | D0 | 0.6757 | 0.6691 | 0.6643 |
  | D1 | 0.6782 | 0.6666 | 0.6599 |
  | D5 | 0.6812 | 0.6729 | 0.6552 |

  The richer models D2–D5 beat D0 only in 2024S1, the fold with the most training data (1,488 games).
- This is **consistent with, not proof of**, draft signal that needs more data. The draft data ends in 2024S1.

**Draft Information Gain** (D5 against D0; positive means the draft improved the forecast):
- Overall −0.0017; by season −0.0056, −0.0038, +0.0091.
- BO7 +0.0089 against BO5 −0.0031.
- By game number: positive for games 3–4, negative for games 1, 5 and 6.
- Team-level draft residuals are in `draft_information_by_team.csv`. They are **exploratory only and are not coach quality or coach draft value.**

**Sequential draft** (1,424 standard 4B-6P-4B-4P drafts; step j sees only events 1..j, tested; hero statistics come from earlier games only):
- PRE_DRAFT 0.6719; AFTER_FIRST_BAN_PHASE 0.6719; AFTER_FIRST_PICK_PHASE 0.6746; AFTER_SECOND_BAN_PHASE 0.6746; FINAL_DRAFT 0.6718.
- In this format, AFTER_SECOND_PICK_PHASE is the same point as FINAL_DRAFT.
- No step differs from pre-draft beyond noise. The best step, 17, is −0.0022 [−0.0073, +0.0029].

## Patch / meta limitation (applies to every draft conclusion)

- There are no verified patch IDs. Season and date are only a temporal proxy.
- Recency weighting was tested as a patch proxy (D1R) and did not help.
- The draft data covers 2022S2–2024S1 only. **A historical draft model is not a verified 2026 meta model.**

## Decision

| layer | decision |
|---|---|
| Game-level team strength | KEEP_AS_RESEARCH_ONLY: G3 is a small, significant gain over vanilla game Elo, but ties B5 at series level |
| Series format model (BO5/BO7) | KEEP_AS_RESEARCH_ONLY: the exact mapping is correct and ties B5; the BO7 under-confidence is real in-sample, but its correction does not validate out of time |
| Series-state model | REJECT |
| Static draft model | KEEP_AS_RESEARCH_ONLY: D1 is borderline; richer models tie D0, D6 overfits; there is a late-fold trend but the data is too short |
| Sequential draft model | REJECT for now: no step gains information beyond noise |
