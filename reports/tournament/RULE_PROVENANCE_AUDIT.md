# v1.0a Rule Provenance Audit — 2026 KPL Annual Finals

Audit date: 2026-09-29. Scope: source verification of tournament-structure rules only. The forecast model (B5 SeasonResetElo,
frozen strength SHA-256 `49cacffc…907dc7`), every probability, the PRIMARY scenario, the Monte Carlo engine and the
prediction ledger are unchanged. No Annual Finals outcome was used or seen.

Evidence registry: `reports/tournament/rule_source_registry.csv` (29 rows). Write-once captures:
`data/raw/tournament_structure/2026-09-29_provenance/` (SHA-256 manifest). Sensitivity: `rule_proxy_sensitivity.csv`,
`rule_materiality_v10a.csv` (module `src/openkpl/tournament/provenance.py`, 1,000,000 simulations, seed 20261002, compared
against the stored PRIMARY rows of `sensitivity.csv`; the main forecast was not rerun).

Status vocabulary: `VERIFIED_OFFICIAL_2026` (Tier 1, 2026, explicit) · `VERIFIED_OFFICIAL_2026_IMPLIED` (logically implied by
Tier 1 text) · `OFFICIAL_IMAGE_NOT_TEXT_RETRIEVABLE` · `HISTORICAL_RULE_PROXY` (official 2024/2025 rule; sensitivity evidence
only, never treated as 2026) · `SECONDARY_TRANSCRIPTION` / `SECONDARY_INTERPRETATION` (Tier 3; never upgraded) · `NOT_FOUND`.

## Search result for a 2026 Annual Finals rulebook

No 2026 Annual Finals rulebook has been published as of 2026-09-29 (the 2025 rulebook appeared 2025-09-18, ten days
before that event). `https://pvp.qq.com/cp/kpl2026/index.html` returns 404. The 2026 official texts are the 2026-09-20
format post (QQ and Weibo), the 2026-09-20 ticketing post and the 2026-09-09 loan-rule notice. None of them states that the
2025 rules are unchanged, so no historical rule is promoted to 2026.

## Gate A — Stage 1 dates, venue and schedule: RESOLVED

| Item | Status | Source |
|---|---|---|
| Stage 1 10-02..10-18; breakthrough 10-20..10-22 | VERIFIED_OFFICIAL_2026 | KPL official Weibo, 2026-09-20 13:55 |
| Guangzhou, 广州体育馆2号馆 | VERIFIED_OFFICIAL_2026 | KPL official Weibo ticketing post, 2026-09-20 14:00 |
| 36 series = 6 Masters × 6 Elites, BO5 | VERIFIED_OFFICIAL_2026_IMPLIED | official format text 组外单循环BO5 |
| Per-series dates / order | official image; text via SECONDARY_TRANSCRIPTION (Wikipedia) | cross-checked with the guide and ticket ranges |

Series dates do not affect any probability (no within-tournament updating), so the image-only schedule is not a gate risk.

## Gate B — Stage 1 ranking and tiebreak: 2026 rule UNKNOWN

The 2026 rule has not been published. HISTORICAL_RULE_PROXY (identical in the official 2024 and 2025 rulebooks, §4.1(C) and
§4.5.1): win = 1 point; ties by 净胜分 (game differential); remaining ties by 加赛 (BO1 playoffs; the 2025-10-11 committee
notice confirms BO1s for ties that affect later pairings). 2024 realized standings show game differential separating
3-3 teams. The 2026 KPL league rulebook (not the Annual Finals) also uses 净胜分 as the second criterion.

Relation to the engine: PRIMARY T1 (wins, game differential, lot) matches the proxy on its first two criteria; its lot
fallback stands in for the playoff, which T3 (strength-weighted playoff proxy) approximates. No contradiction with a
verified rule. Materiality: T2 0.0010, T3 0.0002 → IMMATERIAL.

## Gate C — Breakthrough selection: principle VERIFIED, detail UNKNOWN

VERIFIED_OFFICIAL_2026: entrants M5, M6, E2–E5; BO7 single elimination; "高顺位队伍依次挑选对手".
Not published for 2026: which teams select, the eligible pool, whether selectors may meet.

HISTORICAL_RULE_PROXY: the 2025 rulebook §4.2(C) has M5, M6 and E2 choose in rank order from E3, E4 and E5; the 2024 rulebook
used a protected seed draw in which M5, M6 and E2 cannot meet. The protection is stable across both years; the
mechanism changed (draw → choice). The 2026 short-form wording is the same as the 2025 short-form announcement, which is
suggestive but does not state the rule is unchanged.

Difference from the engine: PRIMARY `ELITE_2_TO_5` lets M5/M6 pick E2 and E2 does not select. Because this is a
difference from a historical proxy, not from a verified 2026 rule, the engine is not changed. Quantified instead:

| Scenario (protected selectors M5→M6→E2 from E3–E5) | max Δ champion | max Δ final | max Δ knockout |
|---|---|---|---|
| OPTIMAL choice (2025 proxy, PRIMARY behaviour) | 0.0007 | 0.0022 | 0.0194 |
| RANDOM (= 2024 protected draw) | 0.0016 | 0.0026 | 0.0360 |
| ADVERSARIAL choice | 0.0017 | 0.0048 | 0.0783 |
| Combined proxy (T3 tiebreak + protected OPTIMAL) | 0.0008 | 0.0024 | 0.0224 |

Under the 2025 proxy (OPTIMAL), 长沙TES.A gains the most knockout probability (+0.019) and KSG loses the most (−0.014). Championship
changes are all under 0.001.

## Gate D — Knockout draw and bracket: structure VERIFIED, seed meaning and wiring UNKNOWN

VERIFIED_OFFICIAL_2026: 8 teams; BO7 throughout; double elimination; pairings by draw; M1 and M2 hold 种子签位.
Not published: what a seed slot means (half separation, pots, restrictions) and the lower-bracket wiring. The guide
(Tier 3) says seeds "won't meet in the first round" and the draw is on 10-22, after the breakthrough.

History cannot proxy the seed meaning: 2024 and 2025 used a fully random draw with "不设种子池"; 2026 introduced seeds.
The v1.0 bounds stand: K2 0.0018, K3 0.0037 → IMMATERIAL. Draw timing is immaterial under K1/K2, because
non-seeded teams are exchangeable.

Wiring HISTORICAL_RULE_PROXY: the realized 2024 and 2025 brackets both match the engine exactly (LB1 = L(QF1)–L(QF3),
L(QF2)–L(QF4); LB2 = W(LB1A)–L(SF1), W(LB1B)–L(SF2); LBF = L(UBF)–W(LBSF); Final = W(UBF)–W(LBF), BO7, no reset). The
alternative wiring (same-half LB1, crossed LB2) gives 0.0008 champion change → IMMATERIAL. The final's first-game side
choice for the upper-bracket champion (2025 §4.4(E)) is not modelled; B5 has no side information.

The realized post-cutoff 2026 bracket was not consulted.

## Materiality of every unresolved rule (descriptive; championship thresholds 0.005 / 0.02)

| Rule | Scenario | max Δ champion | max Δ final | max Δ knockout | Class |
|---|---|---|---|---|---|
| Stage 1 tiebreak | T2 wins then lot | 0.0010 | 0.0026 | 0.0194 | IMMATERIAL |
| Stage 1 tiebreak | T3 strength playoff | 0.0002 | 0.0004 | 0.0040 | IMMATERIAL |
| Breakthrough pool | POOL_ANY (optimal) | 0.0000 | 0.0000 | 0.0000 | IMMATERIAL |
| Breakthrough pool | POOL_ANY random | 0.0016 | 0.0037 | 0.0811 | IMMATERIAL |
| Breakthrough pool | POOL_ANY adversarial | 0.0034 | 0.0073 | 0.1583 | IMMATERIAL |
| Breakthrough pool | protected (2025/2024 proxy), 3 behaviours | ≤ 0.0017 | ≤ 0.0048 | ≤ 0.0783 | IMMATERIAL |
| Selection behaviour (not a rule) | random / adversarial | ≤ 0.0033 | ≤ 0.0050 | ≤ 0.1772 | IMMATERIAL |
| Seed-slot meaning | K2 / K3 | ≤ 0.0037 | ≤ 0.0060 | 0.0000 | IMMATERIAL |
| Lower-bracket wiring | alternative | 0.0008 | 0.0008 | 0.0000 | IMMATERIAL |
| All proxies combined | T3 + protected optimal | 0.0008 | 0.0024 | 0.0224 | IMMATERIAL |

Largest championship change across all 14 scenarios: 0.0037 (K3, 重庆狼队). Knockout-qualification probabilities for
breakthrough teams are sensitive to the selection rules (up to 0.18), which is documented but outside the
championship-based freeze criterion.

## Contradictions with the implemented engine

None with any verified 2026 rule. One difference from a HISTORICAL_RULE_PROXY (E2 as a protected selector) is
quantified above as IMMATERIAL for championship probability. No engine code, scenario or probability was changed.

## Model freeze vs tournament-rule freeze

- **Model freeze (`v1.0-model-freeze`):** B5 strength, the pairwise BO5/BO7 matrices, PRIMARY probabilities and
  `PREDICTION_LEDGER_2026.csv` are frozen and immutable (ledger content SHA-256 `dfe42a35…a90638`).
- **Rule freeze:** Stage 1 tiebreak detail, breakthrough selector/pool detail, seed-slot meaning and lower-bracket
  wiring remain unresolved. If KPL publishes any of them, the model stays frozen. Only the tournament engine is updated,
  under `v1.0a-rule-resolution`, in a new output file that records the rule's publication date and the update timestamp.
  The original ledger is never overwritten or backdated.

## Integrity verification (2026-09-29)

- Frozen strength SHA-256 `49cacffc24c1eca84f78e4c1772e38b4a7be0d9ddca09bbdca78d85d69907dc7`: unchanged.
- Ledger content SHA-256 (excluding `generated_at`) `dfe42a35d4b9b458928f9ae2c61d3c1a0deacbfcf2ba5a3f7760d4fc47a90638`: unchanged.
- `lock.check()` = `[]`. All 33 files in `v10_candidate_manifest.json` match.
- Engine, run, strength, lock, figures and rotation modules, the rules YAML and the pairwise parquets: SHA-256 identical to the pre-audit baseline.
- Annual Finals rows in canonical data: 0. Post-cutoff rows: 0. Strength last match is before the cutoff.
- Full test suite: 170 tests, OK (158 existing + 12 new in `tests/test_rule_provenance.py`).

## Freeze readiness

**PROVISIONAL_PROSPECTIVE_FREEZE_READY.** The model is locked; all published 2026 rules are encoded; every unresolved rule
is documented, with every interpretation changing championship probability by less than 0.005 (maximum 0.0037); no outcomes
are used; tests and locks pass. STRICT_FREEZE_READY is not attainable because the tiebreak, selection detail, seed-slot
meaning and wiring lack primary 2026 evidence. This audit does not execute a freeze.
