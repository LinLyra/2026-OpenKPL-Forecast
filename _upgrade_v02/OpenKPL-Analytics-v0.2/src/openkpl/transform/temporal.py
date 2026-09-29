import sqlite3
import pandas as pd
def build_series_table(path):
    con=sqlite3.connect(path)
    try: d=pd.read_sql("SELECT * FROM kpl_matches",con)
    finally: con.close()
    d=d.rename(columns={"id":"series_id","match_time":"start_time"})
    d["start_time"]=pd.to_datetime(d.start_time,errors="coerce")
    d["score_a"]=pd.to_numeric(d.score_a,errors="coerce"); d["score_b"]=pd.to_numeric(d.score_b,errors="coerce")
    d["winner_team"]=pd.NA
    valid=d.score_a.notna()&d.score_b.notna()&(d.score_a!=d.score_b)
    d.loc[valid&(d.score_a>d.score_b),"winner_team"]=d.team_a
    d.loc[valid&(d.score_b>d.score_a),"winner_team"]=d.team_b
    d["is_completed_labeled"]=d.winner_team.notna()
    d["source_dataset"]="PythonMajor-assignment/data/kpl_data.db"
    return d[["series_id","season","stage","start_time","team_a","team_b","score_a","score_b","winner_team","status","update_time","is_completed_labeled","source_dataset"]]
