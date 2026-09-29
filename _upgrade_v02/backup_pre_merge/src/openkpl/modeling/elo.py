import math
import pandas as pd

def expected(ra, rb):
    return 1/(1+10**((rb-ra)/400))

def build_elo(matches: pd.DataFrame, k=24, initial=1500):
    ratings={}
    rows=[]
    sort_cols=[c for c in ["start_time","source_row"] if c in matches.columns]
    data=matches.sort_values(sort_cols) if sort_cols else matches.copy()
    for idx,r in data.iterrows():
        a,b=str(r.team_a),str(r.team_b)
        ra,rb=ratings.get(a,initial),ratings.get(b,initial)
        p=expected(ra,rb)
        winner=str(r.get("winner_team",""))
        if winner not in (a,b): continue
        y=1.0 if winner==a else 0.0
        rows.append({"row_id":idx,"team_a":a,"team_b":b,
                     "elo_a_pre":ra,"elo_b_pre":rb,"elo_delta_pre":ra-rb,
                     "p_a_elo":p,"y_a":y})
        ratings[a]=ra+k*(y-p)
        ratings[b]=rb+k*((1-y)-(1-p))
    return pd.DataFrame(rows)
