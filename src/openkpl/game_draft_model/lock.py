"""v0.6 experiment lock: write-once hashes of every validated artifact v0.6 reads or must not change."""
import datetime as dt
import json
from pathlib import Path

from openkpl.player_model import lock as v05
from openkpl.roster import baseline

LOCK_PATH = "reports/game_draft_model/v06_experiment_lock.json"
PRIOR_LOCKS = v05.PRIOR_LOCKS + [v05.LOCK_PATH]
V05_ARTIFACTS = [
    "data/processed/modeling/player_roster_features.parquet",
    "data/processed/modeling/player_roster_predictions.parquet",
    "reports/player_model/model_metrics.csv",
    "reports/player_model/season_metrics.csv",
    "reports/player_model/bootstrap_deltas.csv",
    "reports/player_model/initial_run_metrics.csv",
    "reports/player_model/v05_player_roster_benchmark.md",
]
DRAFT_INPUTS = [
    "data/processed/features/hero_temporal_features.parquet",
    "data/processed/features/hero_synergy_temporal.parquet",
    "data/processed/features/hero_counter_temporal.parquet",
    "data/processed/features/series_hero_usage.parquet",
]


def verify_prior(root="."):
    root = Path(root)
    return v05.check(root)


def _groups(root):
    code = sorted(str(p.relative_to(root)) for p in (root / "src/openkpl/player_model").glob("*.py"))
    return {"v05_artifacts": V05_ARTIFACTS, "draft_feature_inputs": DRAFT_INPUTS, "v05_source_code": code}


def build(root="."):
    root = Path(root)
    out = root / LOCK_PATH
    if out.exists():
        raise FileExistsError(f"{LOCK_PATH} is write-once")
    if verify_prior(root):
        raise RuntimeError("prior locks do not verify; refusing to lock")
    lock = {"created_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prior_locks": {p: baseline.sha256_file(root / p) for p in PRIOR_LOCKS},
            "groups": {g: {p: baseline.sha256_file(root / p) for p in ps} for g, ps in _groups(root).items()}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    return lock


def check(root="."):
    root = Path(root)
    lock = json.loads((root / LOCK_PATH).read_text())
    bad = [p for p, h in lock["prior_locks"].items() if baseline.sha256_file(root / p) != h]
    for paths in lock["groups"].values():
        bad += [p for p, h in paths.items() if not (root / p).exists() or baseline.sha256_file(root / p) != h]
    return bad + verify_prior(root)


if __name__ == "__main__":
    print({g: len(v) for g, v in build()["groups"].items()})
