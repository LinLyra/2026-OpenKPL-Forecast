"""Explicit model freeze. Never run automatically by the benchmark.

The model must be named by the caller. An existing freeze manifest is never
overwritten unless force=True. Freezing refuses to proceed if the data or
registry changed since the benchmark artifacts were produced.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import openkpl
from openkpl.evaluation.benchmark import MODEL_IDS, git_commit, sha256_file


class FreezeExistsError(FileExistsError):
    pass


def freeze(model_id, benchmark_dir, freeze_dir, paths, root, force=False):
    benchmark_dir, freeze_dir = Path(benchmark_dir), Path(freeze_dir)
    target = freeze_dir / "model_freeze_manifest.json"
    if target.exists() and not force:
        raise FreezeExistsError(f"{target} already exists; pass --force to overwrite")
    if model_id not in MODEL_IDS:
        raise ValueError(f"model must be one of {MODEL_IDS}, got {model_id!r}")
    bm = json.loads((benchmark_dir / "benchmark_manifest.json").read_text(encoding="utf-8"))
    hp = json.loads((benchmark_dir / "hyperparameters.json").read_text(encoding="utf-8"))
    metrics = pd.read_csv(benchmark_dir / "temporal_metrics.csv", encoding="utf-8-sig")
    hashes = {"source_dataset": sha256_file(paths["source_db"]), "canonical_series": sha256_file(paths["canonical"]),
              "membership_table": sha256_file(paths["membership"])}
    registry_hash = sha256_file(paths["registry"])
    stale = [k for k, cur, old in [("source_dataset", hashes["source_dataset"], bm["source_dataset_hash"]),
                                   ("canonical_series", hashes["canonical_series"], bm["canonical_series_hash"]),
                                   ("membership_table", hashes["membership_table"], bm["membership_table_hash"]),
                                   ("identity_registry", registry_hash, bm["identity_registry_hash"])] if cur != old]
    if stale:
        raise ValueError(f"benchmark artifacts are stale for: {stale}; rerun canonicalize and temporal-benchmark")
    row = metrics[metrics.model_id == model_id].iloc[0].to_dict()
    manifest = {
        "freeze_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": git_commit(root),
        "data_hashes": hashes,
        "registry_hash": registry_hash,
        "selected_model": model_id,
        "selected_hyperparameters": hp["final_development_selected"][model_id],
        "development_metrics": {k: (None if pd.isna(v) else v) for k, v in row.items()},
        "prospective_holdout_definition": {"model_freeze_date": bm["model_freeze_date"],
                                           "prospective_holdout_start": bm["prospective_holdout_start"],
                                           "rule": bm["prospective_holdout_rule"]},
        "benchmark_version": bm["benchmark_version"],
        "code_version": openkpl.__version__,
    }
    freeze_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    hp_txt = ", ".join(f"{k}={v}" for k, v in manifest["selected_hyperparameters"]["selected"].items()) or "none"
    (freeze_dir / "FREEZE.md").write_text(
        f"# Model freeze\n\n- Frozen at: {manifest['freeze_timestamp']}\n- Model: {model_id}\n"
        f"- Hyperparameters (development-selected): {hp_txt}\n"
        f"- Development OOS log loss: {row['log_loss']:.4f}; Brier: {row['brier']:.4f} (n={int(row['n'])})\n"
        f"- Prospective holdout: start_time >= {bm['prospective_holdout_start']}\n"
        f"- Code version: {openkpl.__version__}; git commit: {manifest['git_commit'] or 'not available'}\n\n"
        "No model, parameter, feature, threshold or calibration change is allowed after this point for the "
        "prospective evaluation.\n", encoding="utf-8")
    return manifest
