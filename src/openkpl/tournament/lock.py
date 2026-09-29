"""v1.0 lock: write-once hashes of all prior validated work, tournament structure inputs and frozen strength."""
import datetime as dt
import json
from pathlib import Path

from openkpl.bo7_audit import lock as v061
from openkpl.roster import baseline
from openkpl.tournament import strength as S

LOCK_PATH = "reports/tournament/v10_experiment_lock.json"
PRIOR_LOCKS = v061.PRIOR_LOCKS + [v061.LOCK_PATH]
CAPTURES = "data/raw/tournament_structure/2026-09-29"


def verify_prior(root="."):
    return v061.check(Path(root))


def _groups(root):
    bo7 = sorted(str(p.relative_to(root)) for p in (root / "reports/bo7_audit").iterdir()
                 if p.is_file() and p.name != Path(v061.LOCK_PATH).name)
    code = sorted(str(p.relative_to(root)) for p in (root / "src/openkpl/bo7_audit").glob("*.py"))
    caps = sorted(str(p.relative_to(root)) for p in (root / CAPTURES).iterdir() if p.is_file())
    return {"v061_outputs": bo7, "v061_source_code": code,
            "b5_inputs": [S.CANONICAL, S.HYPER, S.BENCH_PRED, S.REGISTRY,
                          "src/openkpl/modeling/temporal/season_reset.py", "src/openkpl/modeling/temporal/elo.py",
                          "src/openkpl/modeling/temporal/base.py"],
            "tournament_structure": [S.RULES] + caps,
            "frozen_strength": [S.STRENGTH_FILE, S.STRENGTH_HASH, S.TEAMS_FILE]}


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


CANDIDATE_MANIFEST = "reports/tournament/v10_candidate_manifest.json"


def write_candidate_manifest(gate, decision, root="."):
    """Write-once record of every v1.0 output hash and the freeze-gate outcome (does NOT freeze anything)."""
    root = Path(root)
    out = root / CANDIDATE_MANIFEST
    files = sorted(p for d in ("reports/tournament", "figures/tournament") for p in (root / d).iterdir()
                   if p.is_file() and p.name != Path(CANDIDATE_MANIFEST).name)
    files += [root / S.OUT_DIR / f for f in ("pairwise_bo5_probabilities.parquet", "pairwise_bo7_probabilities.parquet")]
    m = {"created_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "status": "PRE-TOURNAMENT FREEZE CANDIDATE (not frozen)", "freeze_gate": gate, "decision": decision,
         "files": {str(p.relative_to(root)): baseline.sha256_file(p) for p in files}}
    with open(out, "x", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    return m


if __name__ == "__main__":
    print({g: len(v) for g, v in build()["groups"].items()})
