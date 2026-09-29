from pathlib import Path
import sqlite3, json
import pandas as pd

TABULAR = {".csv", ".xlsx", ".xls", ".json", ".jsonl", ".parquet"}

def inventory(root: Path) -> pd.DataFrame:
    rows = []
    for p in root.rglob("*"):
        if p.is_file():
            rows.append({
                "path": str(p.relative_to(root)),
                "suffix": p.suffix.lower(),
                "size_bytes": p.stat().st_size,
            })
    return pd.DataFrame(rows)

def _read_table(path: Path):
    s = path.suffix.lower()
    if s == ".csv":
        for enc in ("utf-8-sig","utf-8","gb18030"):
            try: return pd.read_csv(path, encoding=enc)
            except Exception: pass
    elif s in (".xlsx",".xls"): return pd.read_excel(path)
    elif s == ".parquet": return pd.read_parquet(path)
    elif s == ".json":
        try: return pd.read_json(path)
        except Exception:
            obj=json.loads(path.read_text(encoding="utf-8"))
            return pd.json_normalize(obj)
    elif s == ".jsonl": return pd.read_json(path, lines=True)
    return None

def profile_tabular(root: Path) -> pd.DataFrame:
    rows=[]
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in TABULAR:
            try:
                df=_read_table(p)
                if df is None: continue
                for c in df.columns:
                    rows.append({
                        "file": str(p.relative_to(root)),
                        "rows": len(df),
                        "columns": len(df.columns),
                        "column": str(c),
                        "dtype": str(df[c].dtype),
                        "missing_pct": round(float(df[c].isna().mean()*100),3),
                        "n_unique": int(df[c].nunique(dropna=True)),
                    })
            except Exception as e:
                rows.append({"file":str(p.relative_to(root)),"error":repr(e)})
    return pd.DataFrame(rows)

def profile_sqlite(root: Path) -> pd.DataFrame:
    rows=[]
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".db",".sqlite",".sqlite3"):
            try:
                con=sqlite3.connect(p)
                tables=pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'",con)["name"].tolist()
                for t in tables:
                    info=pd.read_sql(f"PRAGMA table_info('{t}')",con)
                    n=con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                    for _,r in info.iterrows():
                        rows.append({"file":str(p.relative_to(root)),"table":t,"rows":n,
                                     "column":r["name"],"type":r["type"],"pk":r["pk"]})
                con.close()
            except Exception as e:
                rows.append({"file":str(p.relative_to(root)),"error":repr(e)})
    return pd.DataFrame(rows)

KEYWORDS = {
 "series":["series","match","比赛","赛事","bo5","bo7"],
 "game":["game","局","小局","round"],
 "team":["team","战队","队伍"],
 "player":["player","选手","队员"],
 "hero":["hero","英雄"],
 "draft":["draft","pick","ban","bp","选用","禁用"],
 "patch":["patch","version","版本"],
 "kills":["kill","击杀"],
 "deaths":["death","死亡"],
 "assists":["assist","助攻"],
 "gold":["gold","经济"],
 "damage":["damage","伤害"],
 "timestamp":["time","date","timestamp","时间","日期"],
}

def field_evidence(tabular: pd.DataFrame, sqlite: pd.DataFrame) -> pd.DataFrame:
    cols=[]
    for source,df in (("tabular",tabular),("sqlite",sqlite)):
        if not df.empty and "column" in df:
            for _,r in df.dropna(subset=["column"]).iterrows():
                cols.append((source, r.get("file",""), r.get("table",""), str(r["column"])))
    out=[]
    for concept,kws in KEYWORDS.items():
        hits=[x for x in cols if any(k.lower() in x[3].lower() for k in kws)]
        out.append({"concept":concept,"status":"GREEN" if hits else "RED",
                    "evidence_count":len(hits),
                    "examples":" | ".join([f"{a}:{b}:{c}:{d}" for a,b,c,d in hits[:5]])})
    return pd.DataFrame(out)
