# v0.6.1 BO7 calibration audit — PRE-REGISTERED PROMOTION RULE

Written before any BO7 calibration model was fitted. Its SHA-256 is recorded in
`reports/bo7_audit/v061_experiment_lock.json`, which is created before the run. The run refuses to start if this
file is missing or its hash changed, and the lock check fails if it changes afterwards.
**This rule must not be changed after seeing results.**

## Question

Does historical evidence justify a simple, strongly constrained BO7 probability adjustment beyond frozen B5?

## Data (fixed)

- Frozen B5 series probabilities from `reports/benchmark/v2026_09_28/temporal_predictions.parquet` (model_id B5).
  Validated development universe only: start_time < 2026-09-28, no KPL2026S3, no Annual Finals outcomes.
- Format from stage, as in v0.6. Blank stages fall back to the final score (4 series in 2026S2).
- Seasons with B5 predictions are 2022S2–2026S2.

## Models (fixed)

z = logit(p_B5), with p clipped to [1e-6, 1 − 1e-6].

**PRIMARY: zero intercept, one parameter.** p' = sigmoid(β·z), fitted on BO7 series only.
Penalized maximum likelihood, minimizing Σ NLL(β) + (λ/2)(β − 1)², with shrinkage centered at β = 1.

| candidate | λ |
|---|---|
| C0 no correction | ∞ (β = 1) |
| C1 unregularized | 0 |
| C2 weak | 2 |
| C3 moderate | 10 |
| C4 strong | 50 |

For scale, one BO7 series carries about 0.05 units of Fisher information on β, so one season carries about 1.

**CSEL, the promotion candidate:** the shrinkage strength is selected per validation season v, from {C0, C1, C2, C3, C4}.
- The selected candidate minimizes summed out-of-time log loss over the validation seasons strictly before v. Each of those predictions was itself fitted only on seasons before its own season.
- Ties go to the stronger shrinkage.
- The first validation season has no earlier out-of-time folds, so it uses C4.

**SECONDARY sensitivity: intercept.** p' = sigmoid(α + β·z), in canonical team_a orientation.
- The penalty is (λ/2)[α² + (β − 1)²], with the same λ grid and the same per-fold selection (CSEL_A).
- It may replace the primary only if it passes all six criteria itself **and** is better than CSEL in at least 95% of paired bootstrap resamples.

## Temporal validation (fixed)

- Strict expanding window over seasons in chronological order.
- For validation season v, the fit uses only BO7 series from seasons before v.
- Validation seasons are 2023S1–2026S2 (10 folds). No random cross-validation.

## Metrics (fixed)

- Primary: log loss and Brier. Secondary: accuracy, ECE, calibration intercept and slope.
- Every candidate is compared with unmodified B5 on identical BO7 series.
- Paired bootstrap: 2,000 resamples of series, stratified by season, seed 20260929.

## BO5 negative control

The identical procedure is run on BO5 series only, with its own fits and selection. BO5 outcomes never enter any BO7
fit or selection. The control is interpretive only.

## Promotion rule

Promote the BO7 correction (CSEL) ONLY IF ALL of the following hold:

1. **OOT log loss improves over B5:** mean ΔLL (CSEL − B5) over all BO7 validation series < 0.
2. **OOT Brier improves or does not materially worsen:** mean ΔBrier ≤ +0.0010.
3. **The paired 95% CI for ΔLL is predominantly below zero:** at least 95% of the 2,000 paired bootstrap resamples have ΔLL < 0.
4. **β direction is stable across historical cutoffs:** sign(β̂_raw − 1), from the C1 fit, is the same at every training cutoff.
5. **The improvement is not driven by a single season:**
   - (a) removing any one validation season leaves the aggregate ΔLL < 0; **and**
   - (b) no HIGH_INSTABILITY in the leave-one-season-out analysis.

   HIGH_INSTABILITY means that some leave-one-season-out pooled β̂_raw (C1, all BO7 seasons minus one) differs from the all-season pooled β̂_raw by more than 0.30, or lies on the other side of 1.
6. **Calibration does not materially deteriorate:** OOT BO7 ECE(CSEL) ≤ ECE(B5) + 0.02 **and** |slope(CSEL) − 1| ≤ |slope(B5) − 1| + 0.10.

Otherwise: **REJECT correction and retain raw B5 for BO7.**

The favorite-strength bins are descriptive only. No bin-specific correction is allowed.
