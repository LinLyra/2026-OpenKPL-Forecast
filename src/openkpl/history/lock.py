"""Phase B immutability lock: Phase A baseline artifacts + Phase A reports + Phase A raw manifests."""
import datetime as dt
import json
from pathlib import Path

from openkpl.roster import baseline

PHASE_A_LOCK = "reports/roster_audit/baseline_lock.json"
PHASE_A_DIRS = ["reports/roster_audit", "data/raw/roster_discovery/2026-09-29/site",
                "data/raw/roster_discovery/2026-09-29/api_sample"]
EXTRA = ["tests/fixtures/benchmark_code_sha256.json"]


def build(root="."):
    root = Path(root)
    base = json.loads((root / PHASE_A_LOCK).read_text())
    arts = [{"path": a["path"], "sha256": a["sha256"], "group": "phase_a_baseline"} for a in base["artifacts"]]
    for d in PHASE_A_DIRS:
        for p in sorted((root / d).rglob("*")):
            if p.is_file():
                arts.append({"path": str(p.relative_to(root)), "sha256": baseline.sha256_file(p), "group": d})
    for rel in EXTRA:
        arts.append({"path": rel, "sha256": baseline.sha256_file(root / rel), "group": "benchmark_fixture"})
    return {"created_at": dt.datetime.now().isoformat(timespec="seconds"), "artifacts": arts}


if __name__ == "__main__":
    out = Path("reports/roster_collection/phase_b_lock.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise SystemExit(f"{out} exists; lock is write-once")
    lock = build()
    problems = baseline.check_lock(json.loads(Path(PHASE_A_LOCK).read_text()))
    if problems:
        raise SystemExit(f"HARD FAILURE: Phase A baseline mutated: {problems}")
    out.write_text(json.dumps(lock, ensure_ascii=False, indent=1))
    print(len(lock["artifacts"]), "artifacts locked")
