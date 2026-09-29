# Forecast Model Card — OpenKPL v1.0, 2026 KPL Annual Finals (PRE-TOURNAMENT FREEZE CANDIDATE, not frozen)

| field | value |
|---|---|
| model | frozen raw **B5** = season-reset Elo (`SeasonResetElo`, K = 48, ρ = 0.9, scale 400) |
| predicted quantity | P(team i wins a series vs team j); identical for BO5 and BO7 |
| tournament layer | vectorized Monte Carlo of the official 4-stage format (`openkpl.tournament.engine`), 1,000,000 simulations per scenario, seed 20261002 |
| information cutoff | 2026-09-28 00:00:00 Asia/Shanghai (exclusive); last training series 2026-09-12 |
| strength artifact | `data/processed/tournament/frozen_team_strength_2026.parquet`, SHA-256 `49cacffc…907dc7` (write-once) |
| status | freeze candidate; the freeze gate returned NOT_READY_TO_FREEZE (see the forecast report §13) |

## What the model knows

- The outcome of every label-eligible KPL series from 2022S2 to 2026S2 (1,466 series), processed online in time order.
- One season reset (ρ = 0.9 toward 1500) for the Annual Finals season label, exactly as B5 does at every
  season change.
- The tournament structure in `config/2026_annual_finals_rules.yaml`: official posts from 2026-09-20/21 plus
  secondary transcriptions. All of it was retrieved 2026-09-29 and is flagged POST_CUTOFF_STRUCTURE_INFORMATION.
  It contains structure only, no competitive outcome.

## What the model does not know

- Any Annual Finals result, game, BP, roster usage or standing. None existed when this was generated.
- Players, rosters, loans (e.g. the Fly loan to 重庆狼队), the Master 7-player rule, hero pools, patches or meta.
- Draft, side, map or game-state information.
- Within-tournament form: ratings are **frozen** and do not update between Annual Finals series.
- The unpublished rules: Stage 1 tiebreak, seed-slot meaning, and whether the bracket wiring is official.
  These are handled only through bounded scenarios.

## Why B5

B5 had the best out-of-time series performance in the validated v0.3 temporal benchmark (1,330 series,
expanding window, 2022S2–2026S2):

| metric | B5 | coin flip |
|---|---|---|
| log loss | 0.6256 | 0.6931 |
| Brier | 0.2177 | 0.25 |
| accuracy | 0.652 | — |
| AUC | 0.702 | — |
| ECE | 0.020 | — |
| calibration slope | 0.91 | — |

The locked F11 predictions (136 series, 2026S2) are reproduced exactly: maximum absolute difference 0.0.

## Why player/roster information was rejected (v0.5)

- Every pre-specified player or roster model (B6–B12) was significantly **worse** than B5 out of time; the
  paired-bootstrap log-loss intervals exclude zero.
- Player ratings are about 0.87 correlated with the B5 logit, so they are largely redundant.
- No roster adjustment is applied. The Master rotation profile is reported descriptively only.

## Why draft information was not used (v0.6)

- Draft models tied the no-draft reference (D1 borderline; richer models tied D0 or overfit).
- The sequential draft carried no information beyond noise.
- Draft data covers only 2022S2–2024S1, and no verified patch IDs exist.
- The series-state model was rejected.

## Why the BO7 correction was rejected (v0.6.1)

- The pre-registered promotion rule returned **REJECT_BO7_CORRECTION**. The out-of-time ΔLL was −0.017 with a
  95% interval of [−0.050, +0.016]; leave-one-season-out was HIGH_INSTABILITY (dropping 2025S2 changes β by 0.34);
  and the rule's criteria 3 and 5b failed.
- β = 1.161 (the strong-shrinkage full-sample estimate) appears only as the labeled BO7_SENSITIVITY scenario and
  never replaces PRIMARY.

## Information cutoff

- 2026-09-28 00:00:00 Asia/Shanghai, exclusive. This is stricter than 2026-09-28 23:59:59 and equivalent in
  content, since no KPL series was played between 2026-09-13 and 2026-10-01.
- Rules were retrieved after the cutoff but published before it (2026-09-20/21). They are structure, not outcome.
- Enforced in code (`strength.replay_b5` asserts no post-cutoff rows and excludes `KPL2026S3`) and by tests
  (`tests/test_tournament.py`), including an injection test with fake Annual Finals and post-cutoff rows.

## Data coverage

| team | historical eligible series |
|---|---|
| 北京JDG | 81 |
| 深圳DYG | 123 |
| other ten teams | 142–209 |

- Most recent eligible series per team: 2026-07-26 (深圳DYG) to 2026-09-12 (重庆狼队, 广州TTG).
- All 12 teams resolve by exact match to VERIFIED identity-registry rows. KSG resolves to TEAM_KSG via its alias row.

## Validation

- **Historical (series):** the v0.3 temporal benchmark above; v0.6 confirmed the BO5/BO7 mapping ties B5.
- **Engine:**
  - All 2^14 winner patterns of the double-elimination bracket are enumerated with deterministic artificial
    winners.
  - Wiring matches the config.
  - Re-entry is rejected.
  - Tiebreak, selection legality and draw constraints each have tests.
  - Every simulation asserts 5 direct / 6 breakthrough / 1 eliminated / 3 breakthrough winners / 8 knockout /
    2 finalists / 1 champion, plus exact terminal-stage counts.
- **Monte Carlo:**
  - The largest change from 500k to 1M simulations is 0.0010 (tolerance 0.002).
  - Agreement with an independent seed is within 2.7 SE.

## Limitations

1. Frozen ratings: the historical validation was one-step-ahead online, but the tournament uses static
   ratings for about 7 weeks. Uncertainty grows along the bracket.
2. B5 is format-agnostic: BO5 and BO7 use the same probability. The historical BO7 under-confidence is not
   corrected (see v0.6.1).
3. Unverified structure:
   - R06 tiebreak (UNRESOLVED)
   - R04 dates (secondary)
   - R10 selection detail (secondary interpretation)
   - R12 bracket wiring (secondary)
   - R13 seed-slot meaning (unpublished)
4. Strategic behavior is idealized. OPTIMAL selection means picking the weakest legal opponent by frozen rating.
   Real teams may choose differently (RANDOM_LEGAL and ADVERSARIAL bound this).
5. No roster, loan, rotation-rule, patch or venue effects. The final in Chengdu is treated as neutral.
6. Game scores (used only for the game-differential tiebreak) come from a constant per-game probability implied
   by the series probability.
7. Calibration of the extreme matchups (p > 0.9) rests on a thin historical sample.

## Prospective test design

The pre-registered evaluation plan (`POST_TOURNAMENT_EVALUATION_PLAN.md`) scores:
- the 36 ledgered Stage 1 BO5 series (log loss, Brier, accuracy, calibration);
- BO7 series conditional on the realized pairing;
- stage advancement (multi-class log score, Brier, RPS);
- the championship (log score, Brier).

All artifacts are hash-verified before scoring, and nothing may be modified after outcomes.
