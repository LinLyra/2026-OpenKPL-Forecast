# Freeze Record — v1.0-prospective-freeze-2026-09-29

> **THIS FORECAST WAS FROZEN BEFORE THE FIRST MATCH OF THE 2026 KPL ANNUAL FINALS.**
>
> The first match (广州TTG vs 深圳DYG) is scheduled for 2026-10-02 in Guangzhou; this freeze was executed on 2026-09-29.

| | |
|---|---|
| Freeze ID | `v1.0-prospective-freeze-2026-09-29` |
| Information cutoff | **2026-09-28 00:00 Asia/Shanghai** (exclusive): no competitive result at or after this instant is used |
| Freeze date | **2026-09-29** |
| Status | **PROVISIONAL_PROSPECTIVE_FREEZE** |
| Model | frozen raw B5 SeasonResetElo (K = 48, ρ = 0.9, scale 400); no BO7, roster, draft or state adjustment |
| Data | v2026_09_28 canonical series (1,466 development series, last played 2026-09-12) |
| Git tag | `v1.0-prospective-freeze-2026-09-29` |
| Machine-readable manifest | `freeze/v1.0/FREEZE_MANIFEST.json` |

## What "provisional" means

"Provisional" refers **only** to tournament procedural details that KPL had not published by the freeze date:

1. the Stage 1 (擂台赛) tiebreak procedure,
2. the breakthrough (突围赛) selection pool / selector detail,
3. the meaning of the knockout "seed slot" (种子签位) for Master #1 and #2,
4. the lower-bracket wiring of the knockout stage.

Each is documented with bounded alternative interpretations. None of them moves any team's championship probability by
0.005 or more (largest: 0.0037). See `reports/tournament/RULE_PROVENANCE_AUDIT.md`.

"Provisional" does **NOT** mean:

- that model parameters are provisional (B5 is frozen; strength SHA-256 `49cacffc…`);
- that team ratings are provisional;
- that championship probabilities may be retuned;
- that predictions may be rewritten after matches begin.

## Frozen artifacts

- `freeze/v1.0/PRIMARY_FORECAST.csv`: byte-identical copy of `reports/tournament/team_forecast_2026.csv` (all 12 teams).
- `reports/tournament/PREDICTION_LEDGER_2026.csv`: the 36 Stage 1 series probabilities. Its `git_commit` column reads
  "N/A (workspace is not a git repository)" because it was written before this repository existed. That value is part of
  the frozen content and is deliberately not edited; the commit is recorded in the freeze manifest instead.
- `data/processed/tournament/`: frozen strength table and pairwise BO5/BO7 probability matrices.
- `reports/tournament/v10_experiment_lock.json` and `v10_candidate_manifest.json`: v1.0 locks (33 files hashed).
- Rule provenance: `rule_source_registry.csv`, `rule_materiality_v10a.csv`, `RULE_PROVENANCE_AUDIT.md`.
- `reports/tournament/POST_TOURNAMENT_EVALUATION_PLAN.md`: pre-registered evaluation plan (hashed in the manifest).

## Reproducing

`.venv/bin/python -m unittest discover -s tests` verifies the locks, the strength hash, the ledger content, and an exact B5
replay from `data/processed/temporal/v2026_09_28/canonical_series.parquet`. Third-party raw sources under
`data/raw/external/` (HoK-BP-LLM, including WZRY.csv) are not redistributed in this repository; the processed canonical
series needed to replay B5 is committed.

## Governing policies

- Rule-only updates: `freeze/v1.0/RULE_UPDATE_POLICY.md`.
- After the tournament starts, predictions are never altered. Observed outcomes live in a separate evaluation layer and
  the prospective ledger stays immutable (`POST_TOURNAMENT_EVALUATION_PLAN.md`).

## Git procedure (two-step, documented)

1. **Content commit.** All source, data, reports and these freeze documents, with `FREEZE_MANIFEST.json` carrying
   `git_commit: null`.
2. **Metadata commit.** Only `FREEZE_MANIFEST.json` changes: `git_commit` is set to the content-commit SHA and the step-1
   manifest hash is recorded. The annotated tag points to this commit.
3. `POST_FREEZE_VERIFICATION.json` is generated after tagging and committed on top. The tag is not moved.
