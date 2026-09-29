import pandas as pd
def expected(a,b): return 1/(1+10**((b-a)/400))
def build_elo(series,initial=1500.,k=24.):
    d=series[series.is_completed_labeled].sort_values(["start_time","series_id"],kind="stable")
    rating={}; rows=[]
    for _,r in d.iterrows():
        a,b=str(r.team_a),str(r.team_b); ra,rb=rating.get(a,initial),rating.get(b,initial); p=expected(ra,rb)
        y=1. if r.winner_team==a else 0.
        rows.append({"series_id":r.series_id,"start_time":r.start_time,"team_a":a,"team_b":b,"winner_team":r.winner_team,
                     "elo_a_pre":ra,"elo_b_pre":rb,"elo_delta_pre":ra-rb,"p_team_a":p,"y_team_a":y})
        rating[a]=ra+k*(y-p); rating[b]=rb+k*((1-y)-(1-p))
    return pd.DataFrame(rows)
