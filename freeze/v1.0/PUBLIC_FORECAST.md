# 2026 KPL Annual Finals — OpenKPL-Analytics Prospective Forecast (v1.0)

**Frozen 2026-09-29, before the first match (2026-10-02). Information cutoff: 2026-09-28 00:00 Asia/Shanghai.**
Freeze tag: `v1.0-prospective-freeze-2026-09-29`.

## Method in brief

- **Team strength:** a single Elo-style rating per team (the "B5" model: season-reset Elo, K = 48, ρ = 0.9), fitted
  only on KPL series played before the cutoff. It was chosen in advance on out-of-time validation.
- **Series probabilities:** taken directly from the rating difference (raw B5). No adjustments for BO7, rosters, player
  form, drafts or momentum.
- **Tournament:** the officially published 2026 format, simulated 1,000,000 times. The stages are: Stage 1 (Master vs
  Elite BO5 round robin), the breakthrough round (BO7 single elimination), and the 8-team BO7 double-elimination
  knockout with M1/M2 seed slots. Ratings are not updated during the tournament.

## Primary forecast (all 12 teams)

Probabilities are rounded here for readability. Unrounded values are in `freeze/v1.0/PRIMARY_FORECAST.csv`. Monte Carlo
standard error on championship probability is ≤ 0.0005.

| Team | Group | Direct to knockout | Via breakthrough | Out in Stage 1 | Reach knockout | Reach final | Champion |
|---|---|---|---|---|---|---|---|
| 重庆狼队 | Master | 93.0% | 7.0% | 0.0% | 99.3% | 64.6% | **42.2%** |
| 广州TTG | Master | 88.5% | 11.5% | 0.0% | 98.5% | 51.4% | **27.7%** |
| 北京JDG | Master | 79.0% | 21.0% | 0.0% | 96.4% | 32.6% | **14.2%** |
| 成都AG超玩会 | Master | 62.8% | 37.2% | 0.0% | 91.3% | 17.2% | **6.1%** |
| 北京WB | Master | 56.0% | 44.0% | 0.0% | 88.6% | 13.4% | **4.3%** |
| 长沙TES.A | Elite | 34.4% | 61.7% | 4.0% | 70.1% | 8.0% | **2.4%** |
| 上海EDG.M | Elite | 31.6% | 63.9% | 4.5% | 67.7% | 7.0% | **2.0%** |
| KSG | Master | 20.8% | 79.2% | 0.0% | 64.9% | 2.3% | **0.47%** |
| 济南RW侠 | Elite | 13.0% | 74.7% | 12.3% | 41.9% | 1.6% | **0.32%** |
| 杭州LGD.NBW | Elite | 10.1% | 74.4% | 15.5% | 37.9% | 1.1% | **0.20%** |
| 南通Hero久竞 | Elite | 9.1% | 73.9% | 17.0% | 32.9% | 0.8% | **0.14%** |
| 深圳DYG | Elite | 1.9% | 51.4% | 46.7% | 10.5% | 0.05% | **0.005%** |

"Direct to knockout" = top 4 Master or top Elite; "Via breakthrough" = entering the breakthrough round (not winning it).
Master teams cannot be eliminated in Stage 1.

## Uncertainty

- The forecast is a probability distribution, not a pick. The favourite, 重庆狼队, is more likely **not** to win
  (57.8%).
- Monte Carlo error is negligible (≤ 0.05 points). The dominant uncertainty is model uncertainty: one rating per team
  cannot see roster changes, form or draft strategy.
- Historically, B5 series probabilities were slightly over-confident (calibration slope ≈ 0.83–0.90), so the true
  spread between teams is probably somewhat narrower than shown.

## Sensitivity scenarios (NOT the forecast)

These are stress tests. None replaces the primary forecast above.

| Team | Primary | Conservative (λ = 0.85) | Aggressive (λ = 1.15) | BO7-correction sensitivity |
|---|---|---|---|---|
| 重庆狼队 | 42.2% | 38.4% | 45.7% | 45.8% |
| 广州TTG | 27.7% | 26.4% | 28.6% | 28.6% |
| 北京JDG | 14.2% | 14.8% | 13.5% | 13.4% |
| 成都AG超玩会 | 6.1% | 7.2% | 5.0% | 5.0% |
| 北京WB | 4.3% | 5.4% | 3.4% | 3.4% |
| others | ≤ 2.4% each | ≤ 3.1% each | ≤ 1.8% each | ≤ 1.7% each |

- "Conservative" and "aggressive" shrink or stretch the series probabilities.
- The BO7 correction was evaluated historically and rejected for the primary forecast.
- Unpublished procedural rules (tiebreak, breakthrough selection pool, seed-slot meaning, lower-bracket wiring) change
  any team's championship probability by at most 0.0037 across all tested interpretations.

## Known limitations

- There are no player, roster, substitution or "Master rotation" effects, although the rotation rule forces every Master
  roster player to appear in each Stage 1 series.
- There are no draft or meta effects and no in-tournament updating.
- Stage 1 per-series dates come from a secondary transcription of an official image; this does not affect probabilities.
- Four procedural rules were unpublished at freeze time (see above); all were found immaterial to championship odds.
- Series outcomes are simulated as independent given the frozen ratings.

## Prospective evaluation

This forecast is locked by hash and git tag and will not be changed after play begins. Match results will be scored in a
separate evaluation layer against the frozen ledger: log loss and Brier score on the 36 Stage 1 series, calibration, and
tournament-level scores for knockout, final and championship probabilities. The metrics, baselines and reporting rules
were pre-registered in `reports/tournament/POST_TOURNAMENT_EVALUATION_PLAN.md`. A single tournament is a small sample;
the evaluation plan says how results will be interpreted without over-reading one outcome.
