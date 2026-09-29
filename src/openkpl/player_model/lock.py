"""v0.5 experiment lock: write-once hashes of every input the player/roster benchmark reads."""
import datetime as dt
import json
from pathlib import Path

from openkpl.roster import baseline

LOCK_PATH = "reports/player_model/v05_experiment_lock.json"
PRIOR_LOCKS = ["reports/roster_audit/baseline_lock.json", "reports/roster_collection/phase_b_lock.json"]
BENCH = "reports/benchmark/v2026_09_28"
GROUPS = {
    "data_inputs": [
        "data/processed/temporal/v2026_09_28/canonical_series.parquet",
        "data/processed/games/kpl_games.parquet",
        "data/processed/games/player_game_appearances.parquet",
        "data/dimensions/player_identity_registry.csv",
        "data/dimensions/team_identity_registry.csv",
        "data/raw/external/HoK-BP-LLM/王者荣耀KPL历年比赛数据/WZRY.csv",
        "data/processed/drafts/identified_draft_games.parquet",
        "data/processed/drafts/draft_events_identified.parquet",
        "data/processed/drafts/wzry_game_linkage.parquet",
    ],
    "feature_inputs": [
        "data/processed/features/player_hero_temporal.parquet",
        "data/processed/rosters/series_player_usage.parquet",
        "data/processed/rosters/series_rotation_summary.parquet",
    ],
    "benchmark_predictions": [f"{BENCH}/temporal_predictions.parquet"],
    "benchmark_metrics": [f"{BENCH}/temporal_metrics.csv", f"{BENCH}/season_metrics.csv",
                          f"{BENCH}/hyperparameters.json", f"{BENCH}/temporal_folds.csv"],
    "modeling_source_code": None,
}
CODE_FIXTURE = "tests/fixtures/benchmark_code_sha256.json"


def _paths(root):
    code = sorted(json.loads((root / CODE_FIXTURE).read_text())["files"])
    code += sorted(str(p.relative_to(root)) for p in (root / "src/openkpl/history").glob("*.py"))
    return {g: (code if v is None else v) for g, v in GROUPS.items()}


def verify_prior(root="."):
    root = Path(root)
    changed = []
    for p in PRIOR_LOCKS:
        changed += baseline.check_lock(json.loads((root / p).read_text()), root)
    return changed


def build(root="."):
    root = Path(root)
    out = root / LOCK_PATH
    if out.exists():
        raise FileExistsError(f"{LOCK_PATH} is write-once")
    if verify_prior(root):
        raise RuntimeError("prior locks do not verify; refusing to lock")
    lock = {"created_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prior_locks": {p: baseline.sha256_file(root / p) for p in PRIOR_LOCKS}, "groups": {}}
    for g, paths in _paths(root).items():
        lock["groups"][g] = {p: baseline.sha256_file(root / p) for p in paths}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    return lock


def check(root="."):
    """Returns the list of locked paths whose hash changed (empty when intact)."""
    root = Path(root)
    lock = json.loads((root / LOCK_PATH).read_text())
    bad = [p for p, h in lock["prior_locks"].items() if baseline.sha256_file(root / p) != h]
    for paths in lock["groups"].values():
        bad += [p for p, h in paths.items() if not (root / p).exists() or baseline.sha256_file(root / p) != h]
    return bad + verify_prior(root)


if __name__ == "__main__":
    lk = build()
    print({g: len(v) for g, v in lk["groups"].items()})
