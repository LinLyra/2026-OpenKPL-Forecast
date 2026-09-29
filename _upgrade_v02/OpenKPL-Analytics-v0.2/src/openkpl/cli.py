from pathlib import Path
import argparse,json,pandas as pd
from openkpl.transform.draft import build_draft_tables
from openkpl.transform.temporal import build_series_table
from openkpl.features.hero import role_features,synergy,counter
from openkpl.audit.quality import run as quality_run
from openkpl.modeling.elo import build_elo
from openkpl.evaluation.metrics import binary_metrics
ROOT=Path(__file__).resolve().parents[2]; RAW=ROOT/"data/raw/external"; DRAFT=ROOT/"data/processed/draft"; TEMP=ROOT/"data/processed/temporal"
DIMS=ROOT/"data/dimensions"; HERO=ROOT/"features/hero"; REPORT=ROOT/"reports/data_quality"; EVAL=ROOT/"evaluation"
WZRY=RAW/"HoK-BP-LLM"/"王者荣耀KPL历年比赛数据"/"WZRY.csv"; DB=RAW/"PythonMajor-assignment"/"data"/"kpl_data.db"
def need(p):
    if not p.exists(): raise SystemExit(f"Missing source: {p}")
def build_draft():
    need(WZRY); DRAFT.mkdir(parents=True,exist_ok=True); DIMS.mkdir(parents=True,exist_ok=True)
    g,e,l,o,t,h=build_draft_tables(WZRY)
    for df,name in [(g,"draft_games"),(e,"draft_events"),(l,"game_lineups"),(o,"hero_loadouts")]: df.to_parquet(DRAFT/f"{name}.parquet",index=False)
    t.to_parquet(DIMS/"draft_teams.parquet",index=False); h.to_parquet(DIMS/"heroes.parquet",index=False)
    print(f"{len(g):,} games | {len(e):,} BP events | {len(l):,} lineup slots | {len(o):,} item rows")
def build_temporal():
    need(DB); TEMP.mkdir(parents=True,exist_ok=True); s=build_series_table(DB); s.to_parquet(TEMP/"series.parquet",index=False)
    print(f"{len(s):,} series rows | {int(s.is_completed_labeled.sum()):,} labeled")
def quality():
    g=pd.read_parquet(DRAFT/"draft_games.parquet"); e=pd.read_parquet(DRAFT/"draft_events.parquet"); l=pd.read_parquet(DRAFT/"game_lineups.parquet"); s=pd.read_parquet(TEMP/"series.parquet")
    print(json.dumps(quality_run(g,e,l,s,REPORT),ensure_ascii=False,indent=2))
def hero_features():
    g=pd.read_parquet(DRAFT/"draft_games.parquet"); l=pd.read_parquet(DRAFT/"game_lineups.parquet"); HERO.mkdir(parents=True,exist_ok=True)
    r,h=role_features(l); sy=synergy(g,l); co=counter(g,l)
    r.to_parquet(HERO/"hero_role_profile.parquet",index=False); h.to_parquet(HERO/"hero_flexibility.parquet",index=False)
    sy.to_parquet(HERO/"hero_pair_synergy.parquet",index=False); co.to_parquet(HERO/"hero_counter_association.parquet",index=False)
    print(f"{len(h)} heroes with HFI | {len(sy)} synergy pairs | {len(co)} directed counter pairs")
def baseline():
    s=pd.read_parquet(TEMP/"series.parquet"); p=build_elo(s); m=binary_metrics(p.y_team_a,p.p_team_a); EVAL.mkdir(parents=True,exist_ok=True)
    p.to_parquet(EVAL/"elo_series_predictions.parquet",index=False); (EVAL/"elo_metrics.json").write_text(json.dumps(m,indent=2),encoding="utf-8"); print(json.dumps(m,indent=2))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("command",choices=["build-draft","build-temporal","quality","hero-features","baseline"]); a=ap.parse_args()
    {"build-draft":build_draft,"build-temporal":build_temporal,"quality":quality,"hero-features":hero_features,"baseline":baseline}[a.command]()
if __name__=="__main__": main()
