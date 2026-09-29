"""Versioned production merge of an audited refresh (v0.3.1). Never overwrites a previous dataset."""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.evaluation.benchmark import sha256_file
from openkpl.identity.membership import build_membership
from openkpl.identity.reviewed_membership import apply_reviewed_membership
from openkpl.refresh.audit import REFRESH_SEASONS_PREFIX, staging_as_series
from openkpl.transform.canonical import build_canonical_series

SERIES_COLUMNS = ["series_id", "season", "stage", "start_time", "start_time_raw", "team_a", "team_b", "score_a",
                  "score_b", "status", "label_flag", "start_time_is_epoch_fallback", "provenance"]


class MergeRefusedError(RuntimeError):
    pass


def mask_prospective(series, holdout_start):
    """Rows at/after the prospective boundary never carry results: scores nulled, flagged PROSPECTIVE_SCHEDULED."""
    s = series.copy()
    future = pd.to_datetime(s.start_time) >= holdout_start
    s.loc[future, ["score_a", "score_b"]] = float("nan")
    s.loc[future, "label_flag"] = "PROSPECTIVE_SCHEDULED"
    return s


def build_merged_series(existing_series, staging, holdout_start, prefix=REFRESH_SEASONS_PREFIX):
    new = staging_as_series(staging[staging.season.str.startswith(prefix)]).drop(columns=["stage_id_src"])
    new["provenance"] = "refresh:" + staging.loc[staging.season.str.startswith(prefix), "raw_source_file"].values
    old = existing_series[~existing_series.season.str.startswith(prefix)].copy()
    old["start_time"] = pd.to_datetime(old.start_time)
    old["score_a"] = old.score_a.astype(float); old["score_b"] = old.score_b.astype(float)
    old["status"] = old.status.astype(float)
    old["provenance"] = "previous:" + old.get("source_dataset", pd.Series("kpl_data.db", index=old.index)).astype(str)
    merged = pd.concat([old[SERIES_COLUMNS], new[SERIES_COLUMNS]], ignore_index=True)
    merged = mask_prospective(merged, holdout_start)
    merged["is_completed_labeled"] = merged.label_flag.eq("COMPLETED")
    merged["winner_team"] = np.where(merged.is_completed_labeled,
                                     np.where(merged.score_a > merged.score_b, merged.team_a, merged.team_b), None)
    return merged.sort_values(["start_time", "series_id"], kind="stable").reset_index(drop=True)


def merge_refresh(existing_series, staging, registry, diff, gate, out_dir, previous_canonical_path, holdout_start):
    if not gate.get("merge_allowed"):
        raise MergeRefusedError(f"refresh audit does not allow merge: {gate.get('decision')} {gate.get('merge_blockers')}")
    out = Path(out_dir)
    if out.exists():
        raise MergeRefusedError(f"{out} already exists; versioned datasets are never overwritten")
    merged = build_merged_series(existing_series, staging, holdout_start)
    canon, audit, checks = build_canonical_series(merged, registry)
    if audit["unresolved_series"] or audit["conflicted_series"] or not all(checks.values()):
        raise MergeRefusedError(f"merged dataset fails canonicalization: {audit} {checks}")
    if (canon[canon.is_label_eligible].start_time >= holdout_start).any():
        raise MergeRefusedError("a label exists at or after the prospective holdout start")
    out.mkdir(parents=True)
    merged.to_parquet(out / "series.parquet", index=False)
    canon.to_parquet(out / "canonical_series.parquet", index=False)
    apply_reviewed_membership(build_membership(canon, registry)).to_csv(out / "team_season_membership.csv", index=False, encoding="utf-8-sig")
    scope = diff[diff.season.astype(str).str.startswith(REFRESH_SEASONS_PREFIX)]
    lab = canon[canon.is_label_eligible]
    record = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "previous_dataset": str(previous_canonical_path),
        "previous_dataset_hash": sha256_file(previous_canonical_path),
        "new_dataset": str(out / "canonical_series.parquet"),
        "new_dataset_hash": sha256_file(out / "canonical_series.parquet"),
        "rows_added": int((scope.diff_class == "NEW_SERIES").sum()),
        "rows_updated": int(scope.diff_class.isin(["RESULT_UPDATED", "STATUS_UPDATED"]).sum()),
        "total_series": int(len(canon)), "label_eligible_series": int(len(lab)),
        "latest_completed_match_date": lab.start_time.max().strftime("%Y-%m-%d %H:%M:%S") if len(lab) else None,
        "canonicalization_audit": audit, "checks": checks, "prospective_holdout_start": str(holdout_start),
    }
    (out / "MERGE_RECORD.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def benchmark_before_after(old_metrics, new_metrics):
    o = old_metrics.set_index("model_id"); n = new_metrics.set_index("model_id")
    rows = []
    for m in o.index.union(n.index, sort=False):
        g = lambda df, c: df.loc[m, c] if m in df.index and c in df.columns else float("nan")  # noqa: E731
        row = {"model": m, "old_n": g(o, "n"), "new_n": g(n, "n")}
        for metric in ["log_loss", "brier", "accuracy", "ece"]:
            row[f"old_{metric}"], row[f"new_{metric}"] = g(o, metric), g(n, metric)
            row[f"delta_{metric}"] = row[f"new_{metric}"] - row[f"old_{metric}"]
        rows.append(row)
    return pd.DataFrame(rows)
