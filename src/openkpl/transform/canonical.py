"""Canonical temporal series (v0.3 Phase B).

Maps observed team names to canonical team IDs using VERIFIED rows of the
human-reviewed identity registry. Raw names are always preserved. Rows that
cannot be safely canonicalized are retained and flagged, never dropped.

Labels (`label_team_a_win`) exist only for status == 4 series with a decisive
score whose two teams are both resolved and not in conflict. League-slot
metadata (team_season_membership.csv) is deliberately NOT used here.
"""
import pandas as pd

CANONICAL_COLUMNS = [
    "series_id", "start_time_raw", "start_time", "chronological_order", "season", "stage", "status",
    "raw_team_a", "raw_team_b", "canonical_team_a_id", "canonical_team_b_id",
    "canonical_team_a_name", "canonical_team_b_name", "score_a", "score_b",
    "winner_canonical_team_id", "label_team_a_win", "is_label_eligible",
    "identity_resolution_status", "data_quality_flag",
]
RESOLVED, UNRESOLVED, CONFLICT = "RESOLVED", "UNRESOLVED", "CONFLICT"
FINISHED_STATUS = 4


def verified_mapping(registry):
    v = registry[(registry.review_status == "VERIFIED") & (registry.canonical_team_id != "")]
    return (dict(zip(v.observed_name, v.canonical_team_id)),
            dict(zip(v.canonical_team_id, v.canonical_name)))


def _alias_interleaving(d):
    """Series IDs where two raw names of one canonical team have overlapping active date ranges."""
    long = pd.concat([
        d[["series_id", "start_time", "raw_team_a", "canonical_team_a_id"]].set_axis(["series_id", "t", "raw", "cid"], axis=1),
        d[["series_id", "start_time", "raw_team_b", "canonical_team_b_id"]].set_axis(["series_id", "t", "raw", "cid"], axis=1),
    ]).dropna(subset=["cid"])
    bad = set()
    for cid, g in long.groupby("cid"):
        spans = g.groupby("raw").t.agg(["min", "max"]).sort_values("min")
        if len(spans) < 2:
            continue
        rows = list(spans.itertuples())
        for i, x in enumerate(rows):
            for y in rows[i + 1:]:
                if x.min <= y.max and y.min <= x.max:
                    bad |= set(g[g.raw.isin([x.Index, y.Index])].series_id)
    return bad


def build_canonical_series(series, registry):
    """Returns (canonical DataFrame, audit dict, checks dict)."""
    name_to_id, id_to_name = verified_mapping(registry)
    d = series.copy()
    d["start_time"] = pd.to_datetime(d.start_time)
    d = d.sort_values(["start_time", "series_id"], kind="stable").reset_index(drop=True)
    d["chronological_order"] = range(1, len(d) + 1)
    d = d.rename(columns={"team_a": "raw_team_a", "team_b": "raw_team_b"})
    d["canonical_team_a_id"] = d.raw_team_a.map(name_to_id)
    d["canonical_team_b_id"] = d.raw_team_b.map(name_to_id)
    d["canonical_team_a_name"] = d.canonical_team_a_id.map(id_to_name)
    d["canonical_team_b_name"] = d.canonical_team_b_id.map(id_to_name)

    resolved = d.canonical_team_a_id.notna() & d.canonical_team_b_id.notna()
    self_play = resolved & (d.canonical_team_a_id == d.canonical_team_b_id)
    long = pd.concat([d[["series_id", "start_time", "canonical_team_a_id"]].set_axis(["sid", "t", "cid"], axis=1),
                      d[["series_id", "start_time", "canonical_team_b_id"]].set_axis(["sid", "t", "cid"], axis=1)]).dropna()
    dup = long[long.duplicated(["t", "cid"], keep=False)]
    simultaneous = d.series_id.isin(set(dup.sid))
    interleaved = d.series_id.isin(_alias_interleaving(d))
    conflict = self_play | simultaneous | interleaved

    d["identity_resolution_status"] = UNRESOLVED
    d.loc[resolved, "identity_resolution_status"] = RESOLVED
    d.loc[conflict, "identity_resolution_status"] = CONFLICT

    reasons = pd.Series([[] for _ in range(len(d))], index=d.index)
    for mask, tag in [(self_play, "SELF_PLAY_AFTER_CANONICALIZATION"), (simultaneous, "CANONICAL_TEAM_SIMULTANEOUS"),
                      (interleaved, "ALIAS_DATE_RANGES_OVERLAP"), (~resolved, "UNRESOLVED_TEAM_NAME")]:
        for i in d.index[mask]:
            reasons[i].append(tag)
    decisive = d.score_a.notna() & d.score_b.notna() & (d.score_a != d.score_b)
    completed = (d.status == FINISHED_STATUS) & decisive
    base_flag = d["label_flag"] if "label_flag" in d else pd.Series("", index=d.index)
    d["data_quality_flag"] = [
        "|".join([str(f)] + r + (["EPOCH_FALLBACK_TIME"] if e else []))
        for f, r, e in zip(base_flag, reasons, d.get("start_time_is_epoch_fallback", pd.Series(False, index=d.index)))
    ]

    eligible = completed & (d.identity_resolution_status == RESOLVED) & d.start_time.notna()
    d["is_label_eligible"] = eligible
    d["winner_canonical_team_id"] = pd.Series(pd.NA, index=d.index, dtype="object")
    d.loc[eligible & (d.score_a > d.score_b), "winner_canonical_team_id"] = d.canonical_team_a_id
    d.loc[eligible & (d.score_b > d.score_a), "winner_canonical_team_id"] = d.canonical_team_b_id
    d["label_team_a_win"] = pd.array([pd.NA] * len(d), dtype="Int8")
    d.loc[eligible, "label_team_a_win"] = (d.loc[eligible, "score_a"] > d.loc[eligible, "score_b"]).astype("int8")
    out = d[CANONICAL_COLUMNS].copy()

    lab = out[out.is_label_eligible]
    src = series[["series_id", "team_a", "team_b"]].drop_duplicates("series_id").set_index("series_id")
    kept = out.drop_duplicates("series_id").set_index("series_id")[["raw_team_a", "raw_team_b"]]
    checks = {
        "no_self_play_after_canonicalization": bool(not self_play.any()),
        "no_duplicate_series_id": bool(not out.series_id.duplicated().any()),
        "no_label_from_status_not_4": bool((lab.status == FINISHED_STATUS).all()),
        "winner_is_one_of_two_canonical_teams": bool(
            ((lab.winner_canonical_team_id == lab.canonical_team_a_id) |
             (lab.winner_canonical_team_id == lab.canonical_team_b_id)).all()),
        "no_simultaneous_alias_ambiguity": bool(not (simultaneous | interleaved).any()),
        "raw_names_preserved": bool(len(out) == len(series) and
                                    (kept.raw_team_a == src.team_a.reindex(kept.index)).all() and
                                    (kept.raw_team_b == src.team_b.reindex(kept.index)).all()),
    }
    audit = {
        "total_series": int(len(out)),
        "completed_series": int(completed.sum()),
        "resolved_series": int((out.identity_resolution_status == RESOLVED).sum()),
        "unresolved_series": int((out.identity_resolution_status == UNRESOLVED).sum()),
        "conflicted_series": int((out.identity_resolution_status == CONFLICT).sum()),
        "excluded_series": int((~out.is_label_eligible).sum()),
        "label_eligible_series": int(out.is_label_eligible.sum()),
        "completed_but_excluded_series": int((completed & ~out.is_label_eligible).sum()),
        "canonical_team_count": int(pd.concat([out.canonical_team_a_id, out.canonical_team_b_id]).dropna().nunique()),
    }
    return out, audit, checks
