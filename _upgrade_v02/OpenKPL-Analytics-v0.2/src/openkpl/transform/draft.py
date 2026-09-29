import ast, hashlib
import pandas as pd

ROLES=["对抗路","打野","中路","发育路","游走"]

def read_wzry(path):
    last=None
    for enc in ("gb18030","gbk","utf-8-sig","utf-8"):
        try: return pd.read_csv(path,encoding=enc)
        except UnicodeDecodeError as e: last=e
    raise last

def literal(v, field, i):
    try: x=ast.literal_eval(str(v))
    except (ValueError,SyntaxError) as e: raise ValueError(f"{field} row {i}: {e}") from e
    if not isinstance(x,list): raise TypeError(f"{field} row {i} is not a list")
    return x

def boolish(v):
    s=str(v).strip().lower()
    if s in {"true","1"}: return True
    if s in {"false","0"}: return False
    raise ValueError(f"Bad boolean {v!r}")

def phase(seq,n):
    if n!=18: return "NONSTANDARD"
    if seq<=4:return "BAN_1"
    if seq<=10:return "PICK_1"
    if seq<=14:return "BAN_2"
    return "PICK_2"

def build_draft_tables(path):
    df=read_wzry(path)
    req={"team1","team1_win","team2","team2_win","battle_process","BP_process"}
    if req-set(df): raise ValueError(f"Missing columns: {sorted(req-set(df))}")
    games=[]; events=[]; lineups=[]; loadouts=[]; teams=set(); heroes=set()
    for i,r in df.reset_index(drop=True).iterrows():
        gid=f"wzry_{i:06d}"
        bp=literal(r.BP_process,"BP_process",i); battle=literal(r.battle_process,"battle_process",i)
        t1,t2=str(r.team1).strip(),str(r.team2).strip()
        w1,w2=boolish(r.team1_win),boolish(r.team2_win)
        winner=t1 if w1 and not w2 else t2 if w2 and not w1 else None
        teams|={t1,t2}
        bans=sum(str(x.get("ban_or_pick","")).lower()=="ban" for x in bp)
        picks=sum(str(x.get("ban_or_pick","")).lower()=="pick" for x in bp)
        empty_bans=sum(str(x.get("ban_or_pick","")).lower()=="ban" and not str(x.get("hero","")).strip() for x in bp)
        payload="||".join(str(r[c]) for c in ["team1","team1_win","team2","team2_win","battle_process","BP_process"])
        pos=[str(x.get("position","")).strip() or "未知" for x in battle]
        clean=len(battle)==10 and all(pos.count(role)==2 for role in ROLES)
        games.append(dict(
            draft_game_id=gid,source_row=i,source_row_sha256=hashlib.sha256(payload.encode()).hexdigest(),
            team1=t1,team2=t2,team1_win=w1,team2_win=w2,winner_team=winner,
            first_actor=str(bp[0].get("team","")).strip() if bp else None,
            bp_length=len(bp),ban_count=bans,pick_count=picks,empty_ban_count=empty_bans,
            lineup_slots=len(battle),bp_quality_flag="STANDARD_18" if len(bp)==18 and bans==8 and picks==10 else "NONSTANDARD",
            lineup_quality_flag="CLEAN_FIVE_ROLE" if clean else "NONSTANDARD_ROLE_ASSIGNMENT",
            temporal_identity_available=False,source_dataset="HoK-BP-LLM/WZRY.csv"))
        for seq,e in enumerate(bp,1):
            team=str(e.get("team","")).strip(); action=str(e.get("ban_or_pick","")).strip().lower(); hero=str(e.get("hero","")).strip()
            if team: teams.add(team)
            if hero: heroes.add(hero)
            events.append(dict(draft_event_id=f"{gid}_e{seq:02d}",draft_game_id=gid,sequence=seq,
                               phase=phase(seq,len(bp)),acting_team=team,action=action,
                               hero=hero or None,hero_missing=not bool(hero)))
        for slot,e in enumerate(battle,1):
            team=str(e.get("team","")).strip(); hero=str(e.get("hero","")).strip()
            position=str(e.get("position","")).strip() or "未知"; items=e.get("equiplist",[]) or []
            if team: teams.add(team)
            if hero: heroes.add(hero)
            lineups.append(dict(lineup_id=f"{gid}_l{slot:02d}",draft_game_id=gid,slot=slot,team=team,hero=hero,
                                position_raw=position,position_normalized=position,position_known=position!="未知",
                                equipment_count=len(items)))
            for order,item in enumerate(items,1):
                loadouts.append(dict(draft_game_id=gid,team=team,hero=hero,slot=slot,item_order=order,item=str(item).strip()))
    return tuple(map(pd.DataFrame,[games,events,lineups,loadouts,
                                   [{"team_name":x} for x in sorted(teams)],
                                   [{"hero_name":x} for x in sorted(heroes)]]))
