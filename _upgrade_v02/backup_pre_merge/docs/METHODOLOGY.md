# Methodology

## Research layers
1. Team strength
2. Roster/player adjustment
3. Player × hero proficiency
4. Static draft
5. Sequential draft
6. Global-BP depletion
7. Prospective evaluation

## Leakage policy
Any feature used for match `t` must be computable using information available strictly before `t`.

Never place model estimates (Elo, win probability, Draft WPA) inside raw factual tables.

## Baseline ladder
- M0: constant / empirical prior
- M1: Elo
- M2: time-decayed / rolling form
- M3: roster-adjusted
- M4: player-hero
- M5: static draft
- M6: sequential draft
- M7: global-BP
- M8: calibrated ensemble

Only promote a model if rolling temporal validation improves probabilistic metrics.

## Evaluation
Primary: Log Loss, Brier Score, calibration.
Secondary: Accuracy, ROC-AUC where appropriate.

## Draft terminology
`post_pick_probability - pre_pick_probability` is a **model-estimated conditional probability change**, not automatically a causal hero/coach effect.
