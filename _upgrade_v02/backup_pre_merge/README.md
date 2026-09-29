# OpenKPL Analytics

Reproducible data engineering + analytics benchmark for professional Honor of Kings (KPL).

## Current scope (V1)
1. Audit and ingest public historical KPL data.
2. Preserve raw facts separately from derived features/predictions.
3. Build temporal, leakage-safe team-strength baselines.
4. Normalize match/game/draft/player tables when source fields permit.
5. Prepare a prospective 2026 KPL annual-finals evaluation workflow.

**Not in V1:** video OCR, minimap CV, scrim data, causal claims about coaches.

## Quick start (macOS / Cursor)

```bash
cd OpenKPL-Analytics
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Put downloaded source repos/files under:
# data/raw/external/

python -m openkpl.cli audit
python -m openkpl.cli ingest
python -m openkpl.cli baseline
```

For convenience:

```bash
make setup
make audit
make ingest
make baseline
```

## Recommended seed sources
- `taitai66/PythonMajor-assignment` — KPL schedule/score crawler; useful as an ingestion/API seed.
- `YuWangyin/HoK-BP-LLM` — historical KPL/BP-oriented corpus; useful as a BP seed.
- Do not assume README claims equal verified field coverage. Run `audit` on the actual files.

Place cloned/downloaded repositories like:

```text
data/raw/external/
├── PythonMajor-assignment/
└── HoK-BP-LLM/
```

## Data contract

Raw observations, derived features, and model outputs are kept separate:

```text
data/raw/              immutable source material
data/processed/        normalized factual tables
features/              pre-match / pre-draft derived variables
predictions/           model outputs with model_version + timestamp
evaluation/            rolling validation / calibration / prospective scores
```

## Target canonical tables

- tournaments
- series
- games
- teams
- players
- heroes
- player_games
- drafts
- draft_events
- global_bp_state (derived)

The pipeline only creates tables supported by discovered source fields. It does **not** fabricate unavailable telemetry.

## Prospective protocol

Before the target competition:
1. Freeze dataset snapshot.
2. Freeze model/version/config.
3. Generate timestamped predictions.
4. Commit predictions before matches.
5. Never overwrite historical predictions.
6. Score with log loss, Brier score, calibration and accuracy.

See `docs/METHODOLOGY.md` and `docs/DATA_AUDIT.md`.
