# OpenKPL Analytics v0.2

High-standard, reproducible KPL data engineering and analytics benchmark.

## Evidence regimes

**Historical Draft Corpus** (`HoK-BP-LLM/.../WZRY.csv`): 5,586 verified rows with ordered BP and 10-slot battle lineups, but no recoverable date/game/player identifiers. It is treated as retrospective and non-temporal.

**Temporal Series Backbone** (`PythonMajor-assignment/data/kpl_data.db`): dated series metadata and scores. It is used for leakage-safe chronological team-strength baselines.

The two sources are **not force-joined**.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e .
```

Clone sources if needed:

```bash
git clone https://github.com/taitai66/PythonMajor-assignment.git data/raw/external/PythonMajor-assignment
git clone https://github.com/YuWangyin/HoK-BP-LLM.git data/raw/external/HoK-BP-LLM
```

## Build

```bash
openkpl build-draft
openkpl build-temporal
openkpl quality
openkpl hero-features
openkpl baseline
python -m unittest discover -s tests -v
```

## Outputs

- `data/processed/draft/draft_games.parquet`
- `data/processed/draft/draft_events.parquet`
- `data/processed/draft/game_lineups.parquet`
- `data/processed/draft/hero_loadouts.parquet`
- `data/processed/temporal/series.parquet`
- `features/hero/hero_role_profile.parquet`
- `features/hero/hero_flexibility.parquet`
- `features/hero/hero_pair_synergy.parquet`
- `features/hero/hero_counter_association.parquet`
- `reports/data_quality/*.json/csv`
- `evaluation/elo_series_predictions.parquet`
- `evaluation/elo_metrics.json`

## Scientific guardrails

Raw files are immutable. `ast.literal_eval` is used instead of `eval`. Synthetic `draft_game_id` values are row identifiers only, never official KPL IDs. WZRY rows receive no fabricated date/season/patch/player. Synergy/counter outputs are descriptive shrinkage associations, not causal effects or automatically current-meta estimates.
