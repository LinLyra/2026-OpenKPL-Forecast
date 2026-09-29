"""Series/game timeline for v0.6 (validated development universe; no Annual Finals, no holdout)."""
import pandas as pd

from openkpl.player_model import data as v05data

BO7_STAGES = {"季后赛", "卡位赛", "总决赛", "突围赛", "决赛", "胜者组四分之一决赛"}
BO5_STAGES = {"常规赛第一轮", "常规赛第二轮", "常规赛第三轮", "擂台赛"}
IDENTIFIED = "data/processed/drafts/identified_draft_games.parquet"


def series_format(stage, score_a, score_b):
    """Format from stage (known pre-series); final score only for the 4 blank-stage series. Returns (fmt, source)."""
    if stage in BO7_STAGES:
        return "BO7", "stage"
    if stage in BO5_STAGES:
        return "BO5", "stage"
    return {2: "BO3", 3: "BO5", 4: "BO7"}[int(max(score_a, score_b))], "final_score (stage blank)"


def build(canonical, games, bench_pred, identified=None, fill_wzry=False):
    """Chronological list of series dicts. Each game has winner_side in {'a','b',None}.
    fill_wzry=True (SENSITIVITY ONLY) fills a missing kplow winner from a uniquely linked WZRY row."""
    c = v05data.dev_universe(canonical)
    b5 = bench_pred[bench_pred.model_id == "B5"].set_index("series_id").predicted_p_team_a
    wz = {}
    if fill_wzry and identified is not None:
        wz = dict(zip(identified.game_key, identified.winner_wzry))
    g = games[games.series_id.isin(c.series_id)].sort_values(["series_id", "game_number"])
    by_series = {s: x for s, x in g.groupby("series_id")}
    out = []
    for r in c.itertuples(index=False):
        fmt, src = series_format(r.stage, r.score_a, r.score_b)
        gl = []
        for x in by_series.get(r.series_id, pd.DataFrame()).itertuples(index=False):
            w, source = x.winner_team_id, "kplow"
            if (w is None or pd.isna(w)) and x.game_key in wz and isinstance(wz[x.game_key], str):
                w, source = wz[x.game_key], "wzry_fill_sensitivity"
            side = "a" if w == r.canonical_team_a_id else "b" if w == r.canonical_team_b_id else None
            gl.append({"game_key": x.game_key, "game_number": int(x.game_number), "winner_side": side,
                       "winner_source": source if side else None})
        out.append({"series_id": r.series_id, "t": r.start_time, "season": r.season, "stage": r.stage,
                    "a": r.canonical_team_a_id, "b": r.canonical_team_b_id, "y": int(r.label_team_a_win),
                    "format": fmt, "format_source": src, "games": gl,
                    "p_b5": float(b5[r.series_id]) if r.series_id in b5.index else None})
    return out


def eligibility(timeline):
    rows = []
    for s in timeline:
        for gm in s["games"]:
            rows.append({"season": s["season"], "eligible": gm["winner_side"] is not None,
                         "source": gm["winner_source"]})
    d = pd.DataFrame(rows)
    return d.groupby("season").agg(games=("eligible", "size"), eligible_games=("eligible", "sum")).reset_index()
