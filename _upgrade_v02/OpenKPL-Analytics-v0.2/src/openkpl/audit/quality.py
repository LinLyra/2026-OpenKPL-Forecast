import json
def run(games,events,lineups,series,out):
    out.mkdir(parents=True,exist_ok=True)
    dq={"draft_games":len(games),"standard_18_games":int((games.bp_quality_flag=="STANDARD_18").sum()),
        "nonstandard_bp_games":int((games.bp_quality_flag!="STANDARD_18").sum()),
        "clean_five_role_games":int((games.lineup_quality_flag=="CLEAN_FIVE_ROLE").sum()),
        "nonstandard_role_games":int((games.lineup_quality_flag!="CLEAN_FIVE_ROLE").sum()),
        "draft_events":len(events),"missing_hero_events":int(events.hero_missing.sum()),
        "lineup_slots":len(lineups),"unique_drafted_heroes":int(events.hero.dropna().nunique()),
        "winner_missing":int(games.winner_team.isna().sum()),"duplicate_source_rows":int(games.source_row_sha256.duplicated().sum())}
    tq={"series_rows":len(series),"unique_series_ids":int(series.series_id.nunique()),
        "duplicate_series_ids":int(series.series_id.duplicated().sum()),"completed_labeled":int(series.is_completed_labeled.sum()),
        "missing_start_time":int(series.start_time.isna().sum()),"min_start_time":str(series.start_time.min()),"max_start_time":str(series.start_time.max())}
    (out/"draft_quality_summary.json").write_text(json.dumps(dq,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"temporal_quality_summary.json").write_text(json.dumps(tq,ensure_ascii=False,indent=2),encoding="utf-8")
    games[(games.bp_quality_flag!="STANDARD_18")|(games.empty_ban_count>0)|(games.lineup_quality_flag!="CLEAN_FIVE_ROLE")].to_csv(out/"draft_anomalies.csv",index=False,encoding="utf-8-sig")
    return {"draft":dq,"temporal":tq}
