"""Normalize raw getScheduleList snapshot bodies into a staging table (no canonicalization).

- start_timestamp is epoch seconds (unambiguous). start_time_raw renders it in
  fixed UTC+8, which reproduces the original crawler's datetime.fromtimestamp
  output (its machine ran at UTC+8: log time 15:40:12 vs SQLite UTC
  update_time 07:40:12 for the same run).
- score_a / score_b are populated only for status == 4; source values are kept
  in source_score_a / source_score_b. No winner is inferred here.
- stage keeps the raw stage_name, even when empty (flagged STAGE_NAME_MISSING).
"""
import hashlib
import json

import pandas as pd

from openkpl.refresh.snapshot import SOURCE_NAME

FINISHED = 4
STATUS_LABELS = {4: "COMPLETED", 1: "SCHEDULED"}
STAGING_COLUMNS = [
    "source_name", "source_competition_id", "source_series_id", "season", "stage", "stage_id",
    "start_timestamp", "start_time_raw", "status", "status_label",
    "raw_team_a", "raw_team_b", "source_team_a_id", "source_team_b_id", "team_a_group", "team_b_group",
    "score_a", "score_b", "source_score_a", "source_score_b", "bo_total", "competition_format",
    "location_name", "arenas", "data_quality_flag", "retrieved_at", "raw_source_file", "raw_record_hash",
]


def record_hash(rec):
    return hashlib.sha256(json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def utc8_string(epoch):
    return (pd.Timestamp(int(epoch), unit="s") + pd.Timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")


def parse_schedule_body(body):
    j = json.loads(body.decode("utf-8"))
    if j.get("result") != 0:
        return None, j
    return (j.get("data") or {}).get("list") or [], j


def normalize_schedules(bodies, seasons=None):
    """bodies: {name: (bytes, request_meta)} from load_snapshot. Returns (staging frame, per-request summary)."""
    rows, summary = [], []
    for name in sorted(bodies):
        if not name.startswith("schedule_"):
            continue
        body, meta = bodies[name]
        comp = meta["query_parameters"].get("seasonid")
        if seasons is not None and comp not in seasons:
            continue
        lst, j = parse_schedule_body(body)
        summary.append({"source_competition_id": comp, "http_status": meta["http_status"],
                        "api_result": j.get("result"), "api_msg": j.get("msg"),
                        "records": None if lst is None else len(lst), "raw_source_file": meta["response_file"],
                        "retrieved_at": meta["retrieved_at"]})
        for rec in lst or []:
            status = int(rec.get("schedule_status")) if str(rec.get("schedule_status", "")).strip() != "" else None
            done = status == FINISHED
            flags = []
            if not str(rec.get("stage_name") or "").strip():
                flags.append("STAGE_NAME_MISSING")
            if done and rec.get("team_a_score") == rec.get("team_b_score"):
                flags.append("COMPLETED_WITHOUT_DECISIVE_SCORE")
            if not done and (rec.get("team_a_score") or rec.get("team_b_score")):
                flags.append("NONZERO_SCORE_BEFORE_COMPLETION")
            rows.append({
                "source_name": SOURCE_NAME, "source_competition_id": comp,
                "source_series_id": rec.get("scheduleid"), "season": rec.get("seasonid"),
                "stage": rec.get("stage_name") or "", "stage_id": rec.get("stageid") or "",
                "start_timestamp": int(rec["start_timestamp"]) if rec.get("start_timestamp") not in (None, "") else None,
                "start_time_raw": utc8_string(rec["start_timestamp"]) if rec.get("start_timestamp") not in (None, "") else None,
                "status": status, "status_label": STATUS_LABELS.get(status, f"NOT_COMPLETED_STATUS_{status}"),
                "raw_team_a": rec.get("team_a_name"), "raw_team_b": rec.get("team_b_name"),
                "source_team_a_id": rec.get("team_a_id"), "source_team_b_id": rec.get("team_b_id"),
                "team_a_group": rec.get("team_a_group"), "team_b_group": rec.get("team_b_group"),
                "score_a": rec.get("team_a_score") if done else None, "score_b": rec.get("team_b_score") if done else None,
                "source_score_a": rec.get("team_a_score"), "source_score_b": rec.get("team_b_score"),
                "bo_total": rec.get("bo_total"), "competition_format": rec.get("competition_format"),
                "location_name": rec.get("location_name"), "arenas": rec.get("arenas"),
                "data_quality_flag": "|".join(flags), "retrieved_at": meta["retrieved_at"],
                "raw_source_file": meta["response_file"], "raw_record_hash": record_hash(rec),
            })
    df = pd.DataFrame(rows, columns=STAGING_COLUMNS)
    for c in ["score_a", "score_b", "source_score_a", "source_score_b", "status", "start_timestamp", "bo_total"]:
        df[c] = pd.array(df[c], dtype="Int64")
    df = df.sort_values(["start_timestamp", "source_series_id"], kind="stable").reset_index(drop=True)
    return df, pd.DataFrame(summary)


def duplicate_source_ids(staging):
    return sorted(staging.source_series_id[staging.source_series_id.duplicated(keep=False)].unique())
