"""Baseline lock: hashes of validated v0.3 / v0.3.1 artifacts that v0.4 must not modify."""
import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

TEMPORAL = "data/processed/temporal/v2026_09_28"
LOCKED = [
    (f"{TEMPORAL}/series.parquet", "v0.3.1 merged series (all statuses)"),
    (f"{TEMPORAL}/canonical_series.parquet", "v0.3.1 canonical series (validated temporal dataset)"),
    (f"{TEMPORAL}/team_season_membership.csv", "v0.3.1 team-season membership"),
    (f"{TEMPORAL}/MERGE_RECORD.json", "v0.3.1 merge record"),
    ("data/processed/temporal/series.parquet", "v0.3 Phase B series"),
    ("data/processed/temporal/canonical_series.parquet", "v0.3 Phase B canonical series"),
    ("data/dimensions/team_identity_registry.csv", "team identity registry"),
    ("data/dimensions/team_season_membership.csv", "v0.3 membership"),
    ("reports/benchmark/temporal_predictions.parquet", "v0.3 Phase B predictions"),
    ("reports/benchmark/temporal_metrics.csv", "v0.3 Phase B metrics"),
    ("reports/benchmark/hyperparameters.json", "v0.3 Phase B hyperparameters"),
    ("reports/benchmark/v2026_09_28/temporal_predictions.parquet", "v0.3.1 refreshed predictions"),
    ("reports/benchmark/v2026_09_28/temporal_metrics.csv", "v0.3.1 refreshed metrics"),
    ("reports/benchmark/v2026_09_28/hyperparameters.json", "v0.3.1 refreshed hyperparameters"),
    ("data/raw/external/HoK-BP-LLM/王者荣耀KPL历年比赛数据/WZRY.csv", "external WZRY dataset (read-only)"),
]
SNAPSHOT_DIR = "data/raw/snapshots/2026-09-28"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rows(p):
    if p.suffix == ".parquet":
        return int(len(pd.read_parquet(p)))
    if p.suffix == ".csv":
        try:
            return int(len(pd.read_csv(p)))
        except UnicodeDecodeError:
            return int(len(pd.read_csv(p, encoding="gb18030")))
    return None


def locked_paths(root="."):
    root = Path(root)
    items = list(LOCKED)
    snap = root / SNAPSHOT_DIR
    if snap.exists():
        items += [(str(p.relative_to(root)), "v0.3.1 raw snapshot") for p in sorted(snap.rglob("*")) if p.is_file()]
    return items


def verify_state(root="."):
    c = pd.read_parquet(Path(root) / TEMPORAL / "canonical_series.parquet")
    done = c[c.data_quality_flag == "COMPLETED"]
    return {
        "completed_series": int(len(done)),
        "latest_completed_start_time": str(done.start_time.max()),
        "KPL2026S1_completed": int((done.season == "KPL2026S1").sum()),
        "KPL2026S2_completed": int((done.season == "KPL2026S2").sum()),
        "KPL2026_annual_finals_completed": int((done.season == "KPL2026S3").sum()),
    }


def build_lock(root="."):
    root = Path(root)
    arts = []
    for rel, note in locked_paths(root):
        p = root / rel
        if not p.exists():
            arts.append({"artifact": p.name, "path": rel, "sha256": None, "row_count_if_applicable": None,
                         "modified_time": None, "notes": f"{note}; MISSING"})
            continue
        arts.append({
            "artifact": p.name, "path": rel, "sha256": sha256_file(p),
            "row_count_if_applicable": _rows(p) if "snapshots" not in rel else None,
            "modified_time": dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
            "notes": note,
        })
    return {"created_at": dt.datetime.now().isoformat(timespec="seconds"), "state": verify_state(root), "artifacts": arts}


def check_lock(lock, root="."):
    """Return list of paths whose current hash differs from the lock."""
    root = Path(root)
    bad = []
    for a in lock["artifacts"]:
        if a["sha256"] and (not (root / a["path"]).exists() or sha256_file(root / a["path"]) != a["sha256"]):
            bad.append(a["path"])
    return bad


if __name__ == "__main__":
    lock = build_lock()
    out = Path("reports/roster_audit/baseline_lock.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lock, ensure_ascii=False, indent=2))
    print(json.dumps(lock["state"], indent=2), len(lock["artifacts"]))
