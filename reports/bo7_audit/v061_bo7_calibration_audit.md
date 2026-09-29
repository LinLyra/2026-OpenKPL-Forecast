# v0.6.1 — Pre-registered BO7 calibration sensitivity audit

**Decision: REJECT_BO7_CORRECTION.** Raw B5 is retained for BO7.

- The rule (`PROMOTION_RULE.md`) was written and hashed into `v061_experiment_lock.json` at 00:57:29Z. The run started at 00:58:16Z, and the rule was unchanged.
- No Annual Finals outcome is used, nothing is frozen, and no tournament is simulated.
- To rebuild: `.venv/bin/python -m openkpl.bo7_audit.run`.

## Sample

- There are 178 historical BO7 series with frozen B5 probabilities, covering 2022S2–2026S2 (16–17 per season).
- Out-of-time validation uses 162 BO7 series across 10 folds, 2023S1–2026S2.
- Four 2026S2 BO7 series have a blank stage, so their format comes from the final score (as in v0.6).

| validation season | BO7 train n | BO7 validation n | β raw (C1) | C2 | C3 | C4 | CSEL chose | β used | OOT LL | B5 LL | Δ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023S1 | 16 | 16 | 0.999 | 1.000 | 1.000 | 1.000 | C4 (default) | 1.000 | 0.643 | 0.643 | 0.000 |
| 2023S2 | 32 | 16 | 1.402 | 1.143 | 1.040 | 1.009 | C0 | 1.000 | 0.621 | 0.621 | 0.000 |
| 2024S1 | 48 | 16 | 1.400 | 1.207 | 1.072 | 1.017 | C1 | 1.400 | 0.495 | 0.535 | −0.040 |
| 2024S2 | 64 | 16 | 1.936 | 1.523 | 1.202 | 1.051 | C1 | 1.936 | 0.565 | 0.611 | −0.045 |
| 2024S3 | 80 | 17 | 2.151 | 1.667 | 1.268 | 1.069 | C1 | 2.151 | 0.480 | 0.568 | −0.088 |
| 2025S1 | 97 | 16 | 2.490 | 1.889 | 1.373 | 1.099 | C1 | 2.490 | 0.439 | 0.514 | −0.075 |
| 2025S2 | 113 | 16 | 2.510 | 1.982 | 1.452 | 1.128 | C1 | 2.510 | **0.844** | 0.674 | **+0.170** |
| 2025S3 | 129 | 17 | 1.951 | 1.704 | 1.366 | 1.112 | C1 | 1.951 | 0.378 | 0.478 | −0.100 |
| 2026S1 | 146 | 16 | 2.141 | 1.865 | 1.470 | 1.151 | C1 | 2.141 | 0.644 | 0.619 | +0.024 |
| 2026S2 | 162 | 16 | 2.006 | 1.795 | 1.456 | 1.154 | C1 | 2.006 | 0.614 | 0.624 | −0.010 |

## Out-of-time BO7 results (162 series; Δ vs B5 on identical series; paired season-stratified series bootstrap, 2,000 resamples)

| model | LL | Brier | ECE | cal. slope | ΔLL [95% CI] | P(ΔLL<0) | ΔBrier [95% CI] |
|---|---|---|---|---|---|---|---|
| B5 / C0 | 0.5879 | 0.2006 | 0.080 | 2.04 | — | — | — |
| C1 unregularized | 0.5699 | 0.1948 | 0.053 | 0.96 | −0.0179 [−0.0508, +0.0162] | 0.86 | −0.0058 [−0.0178, +0.0062] |
| C2 weak (λ=2) | 0.5706 | 0.1950 | 0.032 | 1.17 | −0.0173 [−0.0396, +0.0052] | 0.93 | −0.0057 [−0.0144, +0.0030] |
| C3 moderate (λ=10) | 0.5765 | 0.1967 | 0.059 | 1.51 | −0.0113 [−0.0220, −0.0004] | 0.98 | −0.0039 [−0.0084, +0.0006] |
| C4 strong (λ=50) | 0.5838 | 0.1991 | 0.078 | 1.85 | −0.0041 [−0.0073, −0.0007] | 0.99 | −0.0015 [−0.0029, −0.0001] |
| **CSEL (pre-registered candidate)** | 0.5705 | 0.1948 | 0.050 | 0.98 | **−0.0174 [−0.0498, +0.0160]** | **0.85** | −0.0059 [−0.0177, +0.0061] |
| SECONDARY CSEL_A (with intercept) | 0.5960 | 0.2043 | 0.056 | 1.32 | +0.0081 [−0.0087, +0.0271] | 0.19 | +0.0036 |

- Accuracy is unchanged at 0.698 for all zero-intercept models, because the slope never flips the favorite.
- SECONDARY is worse than the primary CSEL: +0.0256 [+0.0047, +0.0445]. It stays secondary.

The fixed-strength candidates C3 and C4 have CIs below zero. The pre-registered candidate, however, is CSEL: shrinkage chosen per fold from earlier folds only. That procedure chose the unregularized C1 from 2024S1 onward. Choosing C3 or C4 now, after seeing the aggregate, would be exactly the selection the rule forbids. It is recorded here as an observation, not a result.

## Leave-one-season-out pooled β (all 178 BO7 series)

- The all-season β̂ is 1.980 unregularized (1.789, 1.465 and 1.161 under weak, moderate and strong shrinkage).
- Removing any one season moves β̂ by between −0.160 and +0.118, except for **2025S2: +0.343, which triggers HIGH_INSTABILITY** (threshold 0.30).
- 2025S2 is also the fold where the correction lost badly out of time (+0.170): favorites lost several BO7s.

## Favorite-strength bins (descriptive, all B5 seasons; no bin corrections)

| bin | BO7 n | predicted | observed | BO5 n | predicted | observed |
|---|---|---|---|---|---|---|
| 0.50–0.60 | 89 | 0.547 | 0.573 | 419 | 0.547 | 0.547 |
| 0.60–0.70 | 62 | 0.648 | 0.710 | 342 | 0.648 | 0.661 |
| 0.70–0.80 | 22 | 0.738 | 0.955 | 220 | 0.745 | 0.686 |
| 0.80+ | 5 | 0.835 | 1.000 | 171 | 0.856 | 0.819 |

## BO5 negative control (1,032 series, fitted on BO5 only)

- The BO5 β̂_raw is 0.85–0.90 at every cutoff after the first (1.34 on 120 series). The all-season value is 0.854, and leave-one-season-out moves it by at most 0.038.
- BO5 predictions are therefore mildly **over**-confident, the opposite direction to BO7, and very stable.
- CSEL on BO5: ΔLL +0.0001 [−0.0014, +0.0015]. The best fixed-strength candidate, C4, gives −0.0007 [−0.0024, +0.0009]. There is no gain.
- Conclusion: the BO7 slope is **format-specific**, not generic B5 miscalibration. But it is estimated from about 16 series per season and dominated by a few playoff upsets or non-upsets.

## Promotion rule result

| criterion | result |
|---|---|
| 1 OOT LL improves over B5 | PASS (−0.0174) |
| 2 Brier not materially worse | PASS (−0.0059) |
| 3 ≥95% of bootstrap resamples below zero | **FAIL (0.85)** |
| 4 β direction stable across cutoffs | **FAIL** (first cutoff, 16 series: β̂ = 0.999 < 1; all later cutoffs are 1.40–2.51) |
| 5a no single validation season drives it | PASS (dropping any one: −0.008 to −0.038) |
| 5b no HIGH_INSTABILITY | **FAIL (2025S2: +0.343)** |
| 6 calibration not worse | PASS (ECE 0.050 vs 0.080; slope 0.98 vs 2.04) |

- Criterion 4 fails only mechanically: 0.999 is indistinguishable from 1 on 16 series.
- The decision would still be REJECT if criterion 4 passed, because criteria 3 and 5b fail on their own.

**REJECT_BO7_CORRECTION — retain raw B5 for BO7.**

## Interpretation and prospective method

- The direction of the BO7 effect is consistent from the second cutoff onward: B5 is under-confident in BO7.
- However, its magnitude is too uncertain and too dependent on individual seasons to justify a prospective correction under the pre-registered standard.
- For the 2026 prospective model, BO7 series probability = raw frozen B5 (no slope, no intercept).
- The BO7 under-confidence should be documented as a known limitation and carried as a sensitivity scenario, not as the primary forecast. An example scenario is the C4-strength β ≈ 1.15 from all historical BO7.
