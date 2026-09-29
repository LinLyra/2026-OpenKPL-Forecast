"""Temporal series ETL from PythonMajor-assignment/data/kpl_data.db.

One row per scheduled series (not per game). The source is opened read-only.
A series is a labeled result only when status == 4 (finished) and the score is
decisive. Rows whose status is not 4 but whose score is decisive are retained
and flagged STATUS_SCORE_CONFLICT; they receive no winner label.

`start_time` is naive. The crawler converted `start_timestamp` with
`datetime.fromtimestamp`, i.e. the crawling machine's local time zone, which is
not recorded in the database.
"""
import sqlite3

import pandas as pd

SOURCE_DATASET = "PythonMajor-assignment/data/kpl_data.db"
FINISHED_STATUS = 4


def build_series_table(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        d = pd.read_sql("SELECT * FROM kpl_matches", con)
    finally:
        con.close()
    d = d.rename(columns={"id": "series_id", "match_time": "start_time"})
    d["start_time_raw"] = d["start_time"]
    d["start_time"] = pd.to_datetime(d.start_time, errors="coerce")
    d["score_a"] = pd.to_numeric(d.score_a, errors="coerce")
    d["score_b"] = pd.to_numeric(d.score_b, errors="coerce")
    d["status"] = pd.to_numeric(d.status, errors="coerce")

    decisive = d.score_a.notna() & d.score_b.notna() & (d.score_a != d.score_b)
    finished = d.status == FINISHED_STATUS
    labeled = decisive & finished

    d["winner_team"] = pd.Series(pd.NA, index=d.index, dtype="object")
    d.loc[labeled & (d.score_a > d.score_b), "winner_team"] = d.team_a
    d.loc[labeled & (d.score_b > d.score_a), "winner_team"] = d.team_b
    d["is_completed_labeled"] = labeled

    d["label_flag"] = "NOT_FINISHED"
    d.loc[labeled, "label_flag"] = "COMPLETED"
    d.loc[finished & ~decisive, "label_flag"] = "FINISHED_NO_DECISIVE_SCORE"
    d.loc[~finished & decisive, "label_flag"] = "STATUS_SCORE_CONFLICT"
    d["start_time_is_epoch_fallback"] = d.start_time_raw.astype(str).str.startswith("1970-01-01")
    d["start_time_timezone"] = "unrecorded_crawler_local"
    d["source_dataset"] = SOURCE_DATASET
    return d[["series_id", "season", "stage", "start_time", "start_time_raw", "start_time_timezone",
              "start_time_is_epoch_fallback", "team_a", "team_b", "score_a", "score_b", "status",
              "winner_team", "is_completed_labeled", "label_flag", "update_time", "source_dataset"]]
