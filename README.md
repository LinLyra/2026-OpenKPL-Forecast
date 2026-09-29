# OpenKPL Analytics

OpenKPL Analytics is a reproducible forecasting and analytics project for the KPL season, focused on transparent model development, time-safe benchmarking, and a clean public-facing forecast product.

## Project goal

This repository brings together three layers:

1. Data quality and audit work on historical KPL records.
2. Temporal modeling and team-strength baselines built on leakage-safe evaluation.
3. A public forecast product that explains the model in a way audiences can understand without exposing sensitive internal parameters.

The project is designed to answer a single practical question:

> Which teams are strongest, how likely are they to progress through the tournament structure, and how certain are we about those probability estimates?

## What is included

- Historical data audit and reconciliation
- Temporal series construction from raw sources
- Canonical team identity tracking and season membership logic
- Elo-based baselines and benchmark model ladder
- Forecast outputs for stage progression and championship probability
- Forecast product UI for overview, tournament path, matchup comparison, and methodology

## What is not included

- Video OCR or computer vision analysis
- Minimap / tactical trajectory reconstruction
- Scrim or private internal match data
- Causal claims about coaching, strategy, or roster chemistry beyond descriptive statistical evidence

## Public model story

The public-facing methodology is intentionally narrow and truthful:

- Historical series results are converted into team strength estimates.
- Strength is adjusted by seasonal regression and temporal validation logic.
- The tournament structure is replayed under repeated Monte Carlo simulations.
- The outputs are stage probabilities, path probabilities, and championship probabilities.

The project keeps the model structure transparent without exposing internal calibration parameters, weighting rules, or tuning details that are intentionally held back for operational control.

## Repository structure

```text
README.md
requirements.txt
pyproject.toml
src/
config/
data/
reports/
figures/
freeze/
docs/
tests/
web/
```

The Python package sits under `src/openkpl`, while the forecast site lives in `web/` and is designed to present the model in an audience-friendly way.

## Setup

```bash
cd OpenKPL-Analytics
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

If local editable installs are hidden by the macOS filesystem, run:

```bash
chflags nohidden .venv/lib/python3.*/site-packages/*.pth
```

## Typical workflow

```bash
openkpl audit
openkpl build-draft
openkpl build-temporal
openkpl quality
openkpl hero-features
openkpl identity-audit
openkpl canonicalize
openkpl temporal-benchmark
python -m unittest discover -s tests -v
```

## Validation and scientific guardrails

- Raw source files are never overwritten.
- Temporal and draft layers are kept separate to avoid leakage.
- Canonicalization is audited before model selection.
- Model comparison is done with out-of-time validation.
- Forecasts are fixed before live events and not rewritten by outcomes.

## Forecast product

The site in `web/` presents the model through a clean set of public outputs:

- Championship field
- Tournament progression flow
- Matchup comparison
- Model methodology explanation

This keeps the product grounded in real predictive variables instead of misleading spatial or tactical visuals that are not part of the active model.

## Documentation

See the project docs for deeper details:

- `docs/METHODOLOGY.md`
- `docs/DATA_AUDIT.md`
- `docs/DATA_DICTIONARY.md`
- `docs/DATA_CARD.md`

## License and project status

This project is an internal research and forecasting effort for KPL analytics. It is not an official KPL publication and is intentionally designed to keep internal model tuning separate from public exposition.
