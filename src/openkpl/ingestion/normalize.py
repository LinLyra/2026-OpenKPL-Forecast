from pathlib import Path
import pandas as pd

TEAM_A = ["team_a","teama","home_team","left_team","主队","战队a","team1"]
TEAM_B = ["team_b","teamb","away_team","right_team","客队","战队b","team2"]
WINNER = ["winner","winner_team","胜者","获胜队伍","win_team"]
DATE = ["date","start_time","match_time","比赛时间","时间"]

def _find(cols, candidates):
    m={str(c).strip().lower():c for c in cols}
    for x in candidates:
        if x.lower() in m: return m[x.lower()]
    return None

def normalize_match_frame(df: pd.DataFrame) -> pd.DataFrame:
    a,b,w,d = (_find(df.columns,x) for x in (TEAM_A,TEAM_B,WINNER,DATE))
    if not a or not b:
        raise ValueError("Could not identify two team columns.")
    out=pd.DataFrame({"team_a":df[a].astype(str),"team_b":df[b].astype(str)})
    if w: out["winner_team"]=df[w].astype(str)
    if d: out["start_time"]=pd.to_datetime(df[d], errors="coerce")
    out["source_row"]=df.index
    return out
