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

## Source separation (v0.2)
The WZRY draft corpus and the `kpl_data.db` series backbone are not force-joined. WZRY has no verified date, season, series, or game identity, and repeated team pairs are insufficient linkage evidence. Anything built from WZRY is non-temporal and must not feed a chronological model as if it were dated.

Synthetic `draft_game_id` values (`wzry_000000`, …) are stable row IDs only.

## Data-quality policy
Anomalies are retained and flagged, never silently repaired. `openkpl quality` writes summaries to `reports/data_quality/` and reconciles the draft ETL against the forensic audit (`forensic_reconciliation.json`). A mismatch is a finding to investigate.

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

## M1: chronological series Elo (v0.2)
- Input: `series.parquet` rows with `is_completed_labeled` (status 4 and a decisive score).
- Order: `(start_time, series_id)`. Series that share a `start_time` are all predicted from the ratings that existed before that timestamp; ratings update only after the group.
- Parameters: initial 1500, K = 24, one update per series (series outcome, not games).
- Team identity is the raw name string. Renamed organizations restart at 1500 until an evidence-based alias map exists.
- `baseline` refuses to run until `quality` has produced `temporal_quality_summary.json`. Review that report first.

## Hero features (v0.2, WZRY, descriptive)
- **Role profile**: counts and shares of each hero over the five known roles.
- **Hero Flexibility Index (HFI)**: Shannon entropy of a hero's role shares divided by `log(5)`; 0 = one role, 1 = uniform across all five. Unknown and blank positions are excluded from the shares and reported as `unknown_role_slots`.
- **Synergy**: for each same-team hero pair, `(wins + 0.5·m) / (games + m)` with prior strength `m = 20`.
- **Counter**: for each directed cross-team pair (hero vs opponent hero), the same shrinkage. `shrunk(x vs y) + shrunk(y vs x) = 1`.

These are pooled over an undated corpus spanning multiple patches. They are associations, not causal effects, and not current-meta estimates.

## Evaluation
Primary: Log Loss, Brier Score, calibration.
Secondary: Accuracy, ROC-AUC where appropriate.

## Draft terminology
`post_pick_probability - pre_pick_probability` is a **model-estimated conditional probability change**, not automatically a causal hero/coach effect.
