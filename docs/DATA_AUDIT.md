# Data Audit Standard

Every source must be audited from the actual files, not inferred from its README.

## Green / Yellow / Red
- **GREEN**: directly usable structured field with clear semantics.
- **YELLOW**: present but requires parsing, ID reconciliation, or semantic verification.
- **RED**: absent / inaccessible / insufficiently documented.

## Required checks
- file inventory and formats
- row/column counts
- year/date coverage
- missingness
- duplicates
- candidate IDs
- team/player/hero naming consistency
- series vs game granularity
- final draft vs sequential draft
- player-game stats
- patch/version field
- time-series/game-state fields
- provenance and collection method

The command `python -m openkpl.cli audit` produces:
- `reports/audit/file_inventory.csv`
- `reports/audit/tabular_profile.csv`
- `reports/audit/sqlite_tables.csv`
- `reports/audit/field_evidence.csv`
