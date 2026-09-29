from pathlib import Path
import argparse, json
import pandas as pd
from openkpl.audit.files import inventory, profile_tabular, profile_sqlite, field_evidence
from openkpl.ingestion.normalize import normalize_match_frame
from openkpl.modeling.elo import build_elo
from openkpl.evaluation.metrics import score_binary

ROOT=Path(__file__).resolve().parents[2]
EXT=ROOT/"data/raw/external"
AUD=ROOT/"reports/audit"
PROC=ROOT/"data/processed"
EVAL=ROOT/"evaluation"

def audit():
    AUD.mkdir(parents=True,exist_ok=True)
    inv=inventory(EXT); tab=profile_tabular(EXT); sql=profile_sqlite(EXT)
    ev=field_evidence(tab,sql)
    inv.to_csv(AUD/"file_inventory.csv",index=False)
    tab.to_csv(AUD/"tabular_profile.csv",index=False)
    sql.to_csv(AUD/"sqlite_tables.csv",index=False)
    ev.to_csv(AUD/"field_evidence.csv",index=False)
    print(ev.to_string(index=False))
    print(f"\nAudit written to {AUD}")

def ingest():
    candidates=[]
    for p in EXT.rglob("*.csv"):
        try:
            df=pd.read_csv(p,encoding="utf-8-sig")
        except Exception:
            try: df=pd.read_csv(p,encoding="gb18030")
            except Exception: continue
        try:
            n=normalize_match_frame(df)
            n["source_file"]=str(p.relative_to(EXT))
            candidates.append(n)
        except Exception: pass
    if not candidates:
        print("No automatically recognizable match CSV found. Run audit and map source fields explicitly.")
        return
    out=pd.concat(candidates,ignore_index=True).drop_duplicates()
    PROC.mkdir(parents=True,exist_ok=True)
    out.to_parquet(PROC/"matches_seed.parquet",index=False)
    print(f"Wrote {len(out)} rows to data/processed/matches_seed.parquet")

def baseline():
    p=PROC/"matches_seed.parquet"
    if not p.exists():
        raise SystemExit("Run ingest first.")
    m=pd.read_parquet(p)
    if "winner_team" not in m:
        raise SystemExit("winner_team unavailable; cannot fit Elo baseline.")
    pred=build_elo(m)
    if pred.empty: raise SystemExit("No valid labeled matches.")
    metrics=score_binary(pred.y_a,pred.p_a_elo)
    EVAL.mkdir(parents=True,exist_ok=True)
    pred.to_parquet(EVAL/"elo_predictions.parquet",index=False)
    (EVAL/"elo_metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    print(json.dumps(metrics,indent=2))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("command",choices=["audit","ingest","baseline"])
    args=ap.parse_args()
    {"audit":audit,"ingest":ingest,"baseline":baseline}[args.command]()

if __name__=="__main__": main()
