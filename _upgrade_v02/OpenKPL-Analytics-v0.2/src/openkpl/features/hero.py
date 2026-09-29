import math
from collections import defaultdict
import numpy as np, pandas as pd
ROLES=["对抗路","打野","中路","发育路","游走"]
def role_features(lineups):
    k=lineups[lineups.position_normalized.isin(ROLES)]
    p=k.groupby(["hero","position_normalized"]).size().rename("n").reset_index()
    p["share"]=p.n/p.groupby("hero").n.transform("sum")
    rows=[]
    for h,g in p.groupby("hero"):
        q=g.share.to_numpy(float); ent=float(-(q*np.log(q)).sum())
        rows.append({"hero":h,"known_role_slots":int(g.n.sum()),"roles_observed":len(g),
                     "role_entropy":ent,"hero_flexibility_index":ent/math.log(len(ROLES))})
    return p,pd.DataFrame(rows)
def synergy(games,lineups,prior=20.0):
    winners=games.set_index("draft_game_id").winner_team.to_dict(); acc=defaultdict(lambda:[0,0])
    for (gid,team),g in lineups.groupby(["draft_game_id","team"]):
        hs=sorted(set(g.hero.dropna())); won=winners.get(gid)==team
        for i in range(len(hs)):
            for j in range(i+1,len(hs)):
                acc[(hs[i],hs[j])][0]+=1; acc[(hs[i],hs[j])][1]+=int(won)
    rows=[]
    for (a,b),(n,w) in acc.items():
        s=(w+prior*.5)/(n+prior)
        rows.append({"hero_a":a,"hero_b":b,"games":n,"wins":w,"raw_win_rate":w/n,"shrunk_win_rate":s,"prior_strength":prior})
    return pd.DataFrame(rows).sort_values("games",ascending=False)
def counter(games,lineups,prior=20.0):
    winners=games.set_index("draft_game_id").winner_team.to_dict(); acc=defaultdict(lambda:[0,0])
    for gid,g in lineups.groupby("draft_game_id"):
        ts=list(g.team.dropna().unique())
        if len(ts)!=2: continue
        a,b=ts; ha=set(g.loc[g.team==a,"hero"]); hb=set(g.loc[g.team==b,"hero"]); w=winners.get(gid)
        for x in ha:
            for y in hb:
                acc[(x,y)][0]+=1; acc[(x,y)][1]+=int(w==a)
                acc[(y,x)][0]+=1; acc[(y,x)][1]+=int(w==b)
    rows=[]
    for (h,o),(n,w) in acc.items():
        s=(w+prior*.5)/(n+prior)
        rows.append({"hero":h,"opponent_hero":o,"games":n,"wins":w,"raw_win_rate":w/n,
                     "shrunk_win_rate":s,"association_vs_0_5":s-.5,"prior_strength":prior})
    return pd.DataFrame(rows).sort_values("games",ascending=False)
