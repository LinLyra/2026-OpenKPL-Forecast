# OpenKPL Analytics v0.2

Reproducible data engineering + analytics benchmark for professional Honor of Kings (KPL).

## Scope
1. Audit public historical KPL data from the actual files, not their READMEs.
2. Preserve raw facts separately from derived features and predictions.
3. Build a verified historical draft layer and a dated series layer.
4. Build temporal, leakage-safe team-strength baselines.
5. Prepare a prospective 2026 KPL annual-finals evaluation workflow.

**Not in scope:** video OCR, minimap CV, scrim data, causal claims about coaches.

## Two evidence regimes (never force-joined)

| | Historical Draft Corpus | Temporal Series Backbone |
| --- | --- | --- |
| Source | `HoK-BP-LLM/王者荣耀KPL历年比赛数据/WZRY.csv` | `PythonMajor-assignment/data/kpl_data.db` |
| Grain | one game per row (5,586) | one series per row (1,284) |
| Has | ordered BP, 10-slot lineups, positions, items, winner | series ID, season, stage, start time, teams, score, status |
| Lacks | date, season, stage, series/game ID, patch, players, KDA/gold/damage | drafts, per-game results, players |
| Use | retrospective, non-temporal draft/hero analysis | chronological team-strength baselines |

WZRY rows have no verified temporal or game identity. Repeated team pairs are not linkage evidence (see `reports/audit/hok_bp_deep_audit.md`). The two layers are built and analyzed separately.

## Setup (macOS / Cursor)

```bash
cd OpenKPL-Analytics
python3.11 -m venv .venv          # Python >= 3.10 required
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

The project lives in iCloud Drive, which can mark `.pth` files hidden; Python then skips the editable install. If `import openkpl` fails after install, run `chflags nohidden .venv/lib/python3.*/site-packages/*.pth`.

Source repositories go under `data/raw/external/` (read-only):

```bash
git clone https://github.com/taitai66/PythonMajor-assignment.git data/raw/external/PythonMajor-assignment
git clone https://github.com/YuWangyin/HoK-BP-LLM.git data/raw/external/HoK-BP-LLM
```

## Commands

Each command works as `python -m openkpl.cli <cmd>` or `openkpl <cmd>` (or `make <cmd>`).

| Command | What it does |
| --- | --- |
| `audit` | v0.1 file inventory / tabular / SQLite profile / field evidence → `reports/audit/` |
| `ingest` | v0.1 heuristic CSV normalizer (exploratory, not chronological) |
| `build-draft` | WZRY → draft tables (GB18030, `ast.literal_eval`, quality flags) |
| `build-temporal` | `kpl_data.db` → `series.parquet` (status-aware labels) |
| `quality` | quality summaries + reconciliation against the forensic audit |
| `hero-features` | role profile, Hero Flexibility Index, synergy, counter |
| `identity-audit` | team-name inventory, season presence, rename candidates, coexistence checks → `reports/identity/`; creates/extends the UNREVIEWED registry `data/dimensions/team_identity_registry.csv` (never overwrites reviewed rows) |
| `baseline` | v0.2 legacy chronological series Elo on raw team names; requires `quality`. Superseded by `temporal-benchmark`. |
| `canonicalize` | raw names → VERIFIED canonical team IDs → `data/processed/temporal/canonical_series.parquet` (raw names kept, unresolved rows flagged not dropped); creates `data/dimensions/team_season_membership.csv` if absent; audit → `reports/benchmark/canonicalization_audit.csv` |
| `temporal-benchmark` | B0–B5 model ladder with nested season-level temporal CV → `reports/benchmark/`, `figures/benchmark/`. Excludes the prospective holdout (start_time ≥ 2026-09-28). Refuses to run if canonicalization is not clean. |
| `refresh-snapshot [--snapshot-date YYYY-MM-DD]` | read-only fetch of the original source (`kplow` endpoints) into a new, write-once `data/raw/snapshots/<date>/` with `SNAPSHOT_MANIFEST.json` (SHA256 per body); refuses if the date already exists |
| `refresh-audit [--snapshot-date ...]` | verifies snapshot hashes, stages `data/staging/2026_temporal_refresh*.parquet`, writes inventory / diff / coverage / missing manifest / team_a audit and the decision gate → `reports/data_refresh/` |
| `refresh-merge --data-version vYYYY_MM_DD` | versioned merge into `data/processed/temporal/<version>/`; refuses unless the refresh gate allows it (no blocking diffs, no unresolved identities) |
| `temporal-benchmark --data-version <version>` | reruns the unchanged benchmark on a merged version → `reports/benchmark/<version>/` + `benchmark_before_after.csv` |
| `refresh-analysis --data-version <version>` | diagnostics only (fits nothing): per-season 2026 metrics, common-row vs added-row comparison, paired model differences with season-block bootstrap, hyperparameters old vs new, SYG/WST diagnostic, team_a descriptive tables → `reports/data_refresh/` |
| `freeze --model <ID> [--force]` | writes `reports/freeze/model_freeze_manifest.json` + `FREEZE.md` for an explicitly chosen model; refuses to overwrite without `--force`. Never run automatically. |

Typical order:

```bash
openkpl audit
openkpl build-draft
openkpl build-temporal
openkpl quality          # review reports/data_quality/ before the baseline
openkpl hero-features
openkpl identity-audit
openkpl canonicalize        # stop if the audit is not clean
openkpl temporal-benchmark
python -m unittest discover -s tests -v
```

## Outputs

```text
reports/audit/                  forensic audit + `audit` command outputs (v0.2 commands do not write here)
data/processed/draft/           draft_games, draft_events, game_lineups, hero_loadouts (.parquet)
data/processed/temporal/        series.parquet
data/dimensions/                draft_teams.parquet, heroes.parquet
features/hero/                  hero_role_profile, hero_flexibility, hero_pair_synergy, hero_counter_association
reports/data_quality/           draft/temporal summaries, forensic_reconciliation.json, anomaly CSVs
evaluation/                     elo_series_predictions.parquet, elo_metrics.json
```

## Data contract

```text
data/raw/              immutable source material
data/processed/        normalized factual tables
features/              derived variables
predictions/           model outputs with model_version + timestamp
evaluation/            rolling validation / calibration / prospective scores
```

## Scientific guardrails

- Raw files are never modified. `kpl_data.db` is opened read-only.
- Nested WZRY cells are parsed with `ast.literal_eval`, never `eval`.
- `draft_game_id` (`wzry_000000`, …) is a synthetic row ID, never an official KPL game ID.
- WZRY rows receive no fabricated date, season, patch, or player.
- Anomalies are retained and flagged, not repaired (see `docs/DATA_CARD.md`).
- Synergy/counter outputs are descriptive shrinkage associations, not causal effects or current-meta estimates.

## Prospective protocol

Before the target competition:
1. Freeze dataset snapshot.
2. Freeze model/version/config.
3. Generate timestamped predictions.
4. Commit predictions before matches.
5. Never overwrite historical predictions.
6. Score with log loss, Brier score, calibration and accuracy.

See `docs/DATA_CARD.md`, `docs/METHODOLOGY.md`, `docs/DATA_AUDIT.md`, and `docs/DATA_DICTIONARY.md`.
