"""v0.6.1 experiment lock: write-once hashes of prior validated work plus the pre-registered promotion rule."""
import datetime as dt
import json
from pathlib import Path

from openkpl.game_draft_model import lock as v06
from openkpl.roster import baseline

LOCK_PATH = "reports/bo7_audit/v061_experiment_lock.json"
RULE_PATH = "reports/bo7_audit/PROMOTION_RULE.md"
PRIOR_LOCKS = v06.PRIOR_LOCKS + [v06.LOCK_PATH]
V06_DATA = [
    "data/processed/modeling/game_strength_predictions.parquet",
    "data/processed/modeling/series_strength_predictions_v06.parquet",
    "data/processed/modeling/draft_model_features.parquet",
    "data/processed/modeling/draft_predictions.parquet",
    "data/processed/modeling/sequential_draft_predictions.parquet",
]


def verify_prior(root="."):
    return v06.check(Path(root))


def _groups(root):
    rep = sorted(str(p.relative_to(root)) for p in (root / "reports/game_draft_model").iterdir()
                 if p.is_file() and p.name != Path(v06.LOCK_PATH).name)
    code = sorted(str(p.relative_to(root)) for p in (root / "src/openkpl/game_draft_model").glob("*.py"))
    return {"v06_reports": rep, "v06_data": V06_DATA, "v06_source_code": code, "promotion_rule": [RULE_PATH]}


def build(root="."):
    root = Path(root)
    out = root / LOCK_PATH
    if out.exists():
        raise FileExistsError(f"{LOCK_PATH} is write-once")
    if not (root / RULE_PATH).exists():
        raise RuntimeError("promotion rule must be written before locking")
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
