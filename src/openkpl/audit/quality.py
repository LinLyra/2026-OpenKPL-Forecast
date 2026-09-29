"""Data-quality summaries and reconciliation against the forensic audit.

Expected values come from reports/audit/hok_bp_deep_audit.md (2026-09-28).
A reconciliation mismatch is reported, never auto-corrected.
"""
import json

import pandas as pd

# Verified figures from reports/audit/hok_bp_deep_audit.md
FORENSIC_EXPECTED = {
    "draft_games": 5586,
    "draft_events": 100531,
    "ban_events": 44674,
    "pick_events": 55857,
    "lineup_slots": 55860,
    "standard_18_games": 5579,
    "nonstandard_bp_games": 7,
    "clean_five_role_games": 3007,
    "nonstandard_role_games": 2579,
    "missing_hero_events": 23,
    "missing_hero_ban_events": 23,
    "unique_drafted_heroes": 118,
    "unique_lineup_heroes": 117,
    "unknown_position_slots": 286,
    "blank_position_slots": 22,
    "games_with_unknown_position": 144,
    "games_with_blank_position": 18,
    "pick_lineup_mismatch_games": 2,
    "first_actor_is_team1_games": 5586,
    "team1_wins": 2815,
    "team2_wins": 2771,
    "winner_missing": 0,
    "duplicate_source_rows": 0,
    "unique_teams": 45,
}


def _reconcile(observed, expected):
    rows = []
    for k, v in expected.items():
        o = observed.get(k)
        rows.append({"metric": k, "forensic_audit": v, "etl": o, "match": o == v})
    return rows


def run(games, events, lineups, series, out):
    out.mkdir(parents=True, exist_ok=True)
    teams = set(games.team1) | set(games.team2)
    dq = {
        "draft_games": len(games),
        "standard_18_games": int((games.bp_quality_flag == "STANDARD_18").sum()),
        "nonstandard_bp_games": int((games.bp_quality_flag != "STANDARD_18").sum()),
        "clean_five_role_games": int((games.lineup_quality_flag == "CLEAN_FIVE_ROLE").sum()),
        "nonstandard_role_games": int((games.lineup_quality_flag != "CLEAN_FIVE_ROLE").sum()),
        "draft_events": len(events),
        "ban_events": int((events.action == "ban").sum()),
        "pick_events": int((events.action == "pick").sum()),
        "missing_hero_events": int(events.hero_missing.sum()),
        "missing_hero_ban_events": int((events.hero_missing & (events.action == "ban")).sum()),
        "missing_hero_pick_events": int((events.hero_missing & (events.action == "pick")).sum()),
        "lineup_slots": len(lineups),
        "missing_hero_lineup_slots": int(lineups.hero_missing.sum()),
        "unique_drafted_heroes": int(events.hero.dropna().nunique()),
        "unique_lineup_heroes": int(lineups.hero.dropna().nunique()),
        "unknown_position_slots": int(games.unknown_position_slots.sum()),
        "blank_position_slots": int(games.blank_position_slots.sum()),
        "games_with_unknown_position": int((games.unknown_position_slots > 0).sum()),
        "games_with_blank_position": int((games.blank_position_slots > 0).sum()),
        "pick_lineup_mismatch_games": int((~games.pick_set_matches_lineup).sum()),
        "first_actor_is_team1_games": int(games.first_actor_is_team1.sum()),
        "team1_wins": int(games.team1_win.sum()),
        "team2_wins": int(games.team2_win.sum()),
        "winner_missing": int(games.winner_team.isna().sum()),
        "duplicate_source_rows": int(games.source_row_sha256.duplicated().sum()),
        "unique_teams": len(teams),
        "all_ids_synthetic": bool(games.draft_game_id_is_synthetic.all()
                                  and games.draft_game_id.str.fullmatch(r"wzry_\d{6}").all()),
        "temporal_identity_available_any": bool(games.temporal_identity_available.any()),
    }
    recon = _reconcile(dq, FORENSIC_EXPECTED)
    dq["reconciliation_all_match"] = all(r["match"] for r in recon)

    s = series.sort_values(["start_time", "series_id"], kind="stable")
    labeled = s[s.is_completed_labeled]
    ts_groups = labeled.groupby("start_time").size()
    tq = {
        "series_rows": len(series),
        "unique_series_ids": int(series.series_id.nunique()),
        "duplicate_series_ids": int(series.series_id.duplicated().sum()),
        "status_counts": {str(k): int(v) for k, v in series.status.value_counts(dropna=False).sort_index().items()},
        "label_flag_counts": {str(k): int(v) for k, v in series.label_flag.value_counts().sort_index().items()},
        "completed_labeled": int(series.is_completed_labeled.sum()),
        "status_score_conflict_series": series.loc[series.label_flag == "STATUS_SCORE_CONFLICT", "series_id"].tolist(),
        "missing_start_time": int(series.start_time.isna().sum()),
        "epoch_fallback_start_time": int(series.start_time_is_epoch_fallback.sum()),
        "min_start_time": str(series.start_time.min()),
        "max_start_time": str(series.start_time.max()),
        "min_labeled_start_time": str(labeled.start_time.min()),
        "max_labeled_start_time": str(labeled.start_time.max()),
        "labeled_series_sharing_start_time": int(ts_groups[ts_groups > 1].sum()),
        "update_time_min": str(series.update_time.min()),
        "update_time_max": str(series.update_time.max()),
        "labeled_after_crawl_time": int((labeled.start_time > pd.to_datetime(series.update_time, errors="coerce").max()).sum()),
        "seasons": {str(k): int(v) for k, v in series.season.value_counts().sort_index().items()},
        "unique_teams": int(len(set(series.team_a) | set(series.team_b))),
        "start_time_timezone": "unrecorded_crawler_local",
    }
    draft_ids = set(games.draft_game_id)
    tq["id_overlap_with_draft_corpus"] = int(len(draft_ids & set(series.series_id)))

    (out / "draft_quality_summary.json").write_text(json.dumps(dq, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "temporal_quality_summary.json").write_text(json.dumps(tq, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / "forensic_reconciliation.json").write_text(json.dumps(recon, ensure_ascii=False, indent=2), encoding="utf-8")
    anomalies = games[(games.bp_quality_flag != "STANDARD_18") | games.has_missing_hero
                      | (games.lineup_quality_flag != "CLEAN_FIVE_ROLE") | ~games.pick_set_matches_lineup]
    anomalies.to_csv(out / "draft_anomalies.csv", index=False, encoding="utf-8-sig")
    series[series.label_flag != "COMPLETED"].to_csv(out / "temporal_unlabeled_series.csv", index=False, encoding="utf-8-sig")
    return {"draft": dq, "temporal": tq, "reconciliation": recon}
