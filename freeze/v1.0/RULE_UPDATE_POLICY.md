# Rule Update Policy — after v1.0-prospective-freeze-2026-09-29

## Absolute rules

- **MODEL CHANGES ARE FORBIDDEN.**
- **COMPETITIVE DATA UPDATES ARE FORBIDDEN.**
- **v1.0 IS NEVER OVERWRITTEN.** The v1.0 ledger, primary forecast, manifest, locks and tag are immutable.

## Rule-only versions

If KPL later publishes official evidence for a procedural rule that is unresolved in v1.0, a new rule-only version is
created: `v1.0a`, then `v1.0b`, and so on. Each lives in its own directory (`freeze/v1.0a/`, …) and output files, with its own
tag. It is compared against v1.0 and never replaces v1.0.

### Allowed changes (only when supported by newly published official evidence)

| Area | Unresolved in v1.0 | v1.0 PRIMARY implementation |
|---|---|---|
| Stage 1 tiebreak implementation | yes | series wins → game differential → lot |
| Breakthrough legal-selection set | yes | M5 then M6 choose from Elite #2–#5 (optimal choice); last two meet |
| Seed-slot interpretation | yes | M1 and M2 in opposite halves (K1) |
| Bracket wiring | yes | LB1 = L(QF1)–L(QF3), L(QF2)–L(QF4); LB2 = W(LB1A)–L(SF1), W(LB1B)–L(SF2) |

"Official" means Tier 1 (KPL / 王者荣耀赛事 official site, official KPL Weibo/WeChat, Tencent announcements) or Tier 2
(official club / organizer reposts). Tier 3 (media, wikis, community) never justifies a rule change. The realized
bracket or any match outcome is not evidence of a rule.

### Forbidden changes (in any version)

- B5 parameters
- team ratings
- historical training data
- probability calibration
- player / roster adjustments
- draft adjustments
- post-match performance information (any Annual Finals result)

### Required report for every rule-only update

1. official source (publisher, title, URL, tier) and a write-once capture with SHA-256
2. publication timestamp (as shown by the source)
3. retrieval timestamp
4. old rule (v1.0 implementation)
5. new rule (as published)
6. probability delta from v1.0 for every team: knockout, final and championship, with Monte Carlo SE
7. whether the rule was published before or after any affected match was played

Rule-only versions reuse the frozen v1.0 strength file and pairwise matrices unchanged (hash-verified) and the same
simulation seed and count, so every difference from v1.0 is attributable to the rule change alone.

If a rule is published after some matches have been played, the rule-only version still conditions on **no** outcomes:
it is a re-run of the pre-tournament forecast under the corrected rule, clearly labeled with its creation date. It is
never presented as having been available before its creation date.
