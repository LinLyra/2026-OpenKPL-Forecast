"""Post-merge diagnostics for a refreshed benchmark (v0.3.1). Reads benchmark outputs only; fits nothing."""
import json

import numpy as np
import pandas as pd

from openkpl.evaluation.calibration import evaluate
from openkpl.refresh.audit import team_a_tables

ELO_MODELS = ["B2", "B3", "B4", "B5"]
REGULAR = {"cgs1", "cgs2", "cgs3"}
PLAYOFF = {"jhs", "js", "tts", "szz14", "zjs"}
QUALIFYING = {"kws", "lts", "tws"}
TUNED = {"B3": ["k", "scale"], "B4": ["k", "half_life_days"], "B5": ["k", "rho"]}


def _metrics(g):
    e = evaluate(g.actual_team_a_win.to_numpy(float), g.predicted_p_team_a.to_numpy(float))
    return {"n": e["n"], "log_loss": e["log_loss"], "brier": e["brier"], "accuracy": e["accuracy"], "ece": e["ece"],
            "mean_predicted_probability": e["mean_predicted_p"], "observed_team_a_win_rate": e["observed_win_rate"]}


def season_metrics(pred, seasons):
    p = pred[pred.is_development & pred.season.isin(seasons)]
    rows = [{"season": s, "model": m, **_metrics(g)} for (s, m), g in p.groupby(["season", "model_id"], sort=True)]
    return pd.DataFrame(rows)


def common_row_comparison(old_pred, new_pred):
    """Separates 'same rows, re-predicted' from 'new rows added'."""
    o = old_pred[old_pred.is_development]; n = new_pred[new_pred.is_development]
    rows = []
    for m in sorted(set(o.model_id) | set(n.model_id)):
        om, nm = o[o.model_id == m], n[n.model_id == m]
        j = om.merge(nm, on="series_id", suffixes=("_old", "_new"))
        added = nm[~nm.series_id.isin(om.series_id)]
        eo = evaluate(j.actual_team_a_win_old.to_numpy(float), j.predicted_p_team_a_old.to_numpy(float))
        en = evaluate(j.actual_team_a_win_new.to_numpy(float), j.predicted_p_team_a_new.to_numpy(float))
        ea = evaluate(added.actual_team_a_win.to_numpy(float), added.predicted_p_team_a.to_numpy(float))
        rows.append({"model": m, "common_n": len(j),
                     "max_abs_prediction_change_on_common_rows": float((j.predicted_p_team_a_old - j.predicted_p_team_a_new).abs().max()),
                     "labels_changed_on_common_rows": int((j.actual_team_a_win_old != j.actual_team_a_win_new).sum()),
                     "common_old_log_loss": eo["log_loss"], "common_new_log_loss": en["log_loss"],
                     "old_rows_missing_from_new": int((~om.series_id.isin(nm.series_id)).sum()),
                     "added_n": len(added), "added_log_loss": ea["log_loss"], "added_brier": ea["brier"],
                     "added_accuracy": ea["accuracy"]})
    return pd.DataFrame(rows)


PAIRS = [("B1", "B0"), ("B2", "B1"), ("B3", "B2"), ("B4", "B3"), ("B5", "B3"), ("B5", "B4")]


def _series_log_loss(g):
    p = np.clip(g.predicted_p_team_a.to_numpy(float), 1e-6, 1 - 1e-6)
    y = g.actual_team_a_win.to_numpy(float)
    return pd.Series(-(y * np.log(p) + (1 - y) * np.log(1 - p)), index=g.series_id.to_numpy())


def paired_differences(preds, n_boot=2000, seed=0):
    """Per-series log-loss difference (model - reference): mean, iid SE, season-block bootstrap 95% interval."""
    rng = np.random.default_rng(seed)
    rows = []
    for label, pred in preds.items():
        p = pred[pred.is_development]
        season = p.drop_duplicates("series_id").set_index("series_id").season
        ll = {m: _series_log_loss(g) for m, g in p.groupby("model_id")}
        for a, b in PAIRS:
            d = (ll[a] - ll[b]).dropna()
            s = season.loc[d.index]
            blocks = [d[s == x].to_numpy() for x in sorted(s.unique())]
            boot = []
            for _ in range(n_boot):
                pick = rng.integers(0, len(blocks), len(blocks))
                v = np.concatenate([blocks[i] for i in pick])
                boot.append(v.mean())
            lo, hi = np.percentile(boot, [2.5, 97.5])
            rows.append({"dataset": label, "comparison": f"{a} - {b}", "n": len(d), "mean_delta_log_loss": d.mean(),
                         "iid_se": d.std(ddof=1) / np.sqrt(len(d)), "season_block_boot_lo95": lo,
                         "season_block_boot_hi95": hi, "share_of_seasons_favoring_first":
                         float(np.mean([blk.mean() < 0 for blk in blocks])), "n_seasons": len(blocks)})
    return pd.DataFrame(rows)


def hyperparameter_comparison(old_hp, new_hp):
    rows = []
    for m, keys in TUNED.items():
        o, n = old_hp["final_development_selected"][m], new_hp["final_development_selected"][m]
        rows.append({"model": m, "scope": "final_development_selection",
                     **{f"old_{k}": o["selected"].get(k, old_hp["fixed_within_tuned_models"][m].get(k)) for k in keys},
                     **{f"new_{k}": n["selected"].get(k, new_hp["fixed_within_tuned_models"][m].get(k)) for k in keys},
                     "old_inner_n": o.get("inner_n"), "new_inner_n": n.get("inner_n")})
        of = {f["fold_id"]: f for f in old_hp["fold_level_selections"][m]}
        for f in new_hp["fold_level_selections"][m]:
            prev = of.get(f["fold_id"], {})
            rows.append({"model": m, "scope": f"{f['fold_id']}:{f['validation_season']}",
                         **{f"old_{k}": prev.get("selected", {}).get(k, old_hp["fixed_within_tuned_models"][m].get(k) if prev else None) for k in keys},
                         **{f"new_{k}": f["selected"].get(k, new_hp["fixed_within_tuned_models"][m].get(k)) for k in keys},
                         "old_inner_n": prev.get("inner_n"), "new_inner_n": f.get("inner_n")})
    df = pd.DataFrame(rows)
    old_cols = [c for c in df.columns if c.startswith("old_") and not c.endswith("inner_n")]
    df["changed"] = [any(str(r[c]) != str(r["new_" + c[4:]]) for c in old_cols if ("new_" + c[4:]) in df.columns and pd.notna(r[c]))
                     for _, r in df.iterrows()]
    return df


def _k(version):
    return float(json.loads(version.split("|", 2)[2]).get("k", np.nan))


def team_diagnostic(pred, teams):
    """Per team and Elo model: record, first pre-match and final post-match Elo, and prediction quality."""
    p = pred[pred.is_development]
    rows = []
    for team in teams:
        for m in sorted(p.model_id.unique()):
            g = p[(p.model_id == m) & ((p.canonical_team_a_id == team) | (p.canonical_team_b_id == team))].sort_values("start_time")
            if g.empty:
                continue
            is_a = g.canonical_team_a_id == team
            p_team = np.where(is_a, g.predicted_p_team_a, 1 - g.predicted_p_team_a)
            y_team = np.where(is_a, g.actual_team_a_win, 1 - g.actual_team_a_win).astype(float)
            e = evaluate(y_team, p_team)
            row = {"team": team, "model": m, "n": len(g), "wins": int(y_team.sum()), "losses": int(len(g) - y_team.sum()),
                   "mean_predicted_win_probability": float(p_team.mean()), "log_loss_of_predictions": e["log_loss"],
                   "brier_of_predictions": e["brier"], "accuracy": e["accuracy"],
                   "initial_pre_match_elo": np.nan, "final_elo": np.nan, "first_match": str(g.start_time.iloc[0]),
                   "last_match": str(g.start_time.iloc[-1])}
            if m in ELO_MODELS:
                r_pre = np.where(is_a, g.pre_match_rating_a, g.pre_match_rating_b)
                last = g.iloc[-1]
                row["initial_pre_match_elo"] = float(r_pre[0])
                row["final_elo"] = float(r_pre[-1] + _k(last.hyperparameter_version) * (y_team[-1] - p_team[-1]))
            rows.append(row)
    return pd.DataFrame(rows)


def _phase(stage_id):
    if stage_id in REGULAR:
        return "REGULAR_SEASON"
    if stage_id in PLAYOFF:
        return "PLAYOFFS_FINALS"
    if stage_id in QUALIFYING:
        return "PLAY_IN_QUALIFYING"
    return "OTHER"


def team_a_diagnostic(staging, canonical):
    """Descriptive only. Uses the merged dataset's labels and the staging table's source stage_id / venue."""
    lab = canonical[canonical.is_label_eligible][["series_id", "season", "label_team_a_win"]]
    _, _, done = team_a_tables(staging)
    d = lab.merge(done[["source_series_id", "stage_id", "stage", "venue_relation"]].rename(columns={"source_series_id": "series_id"}),
                  on="series_id", how="left")
    d["phase"] = d.stage_id.map(_phase)
    d["y"] = d.label_team_a_win.astype(float)

    def agg(keys, label):
        g = d.groupby(keys, sort=True).y.agg(["size", "sum", "mean"]).reset_index()
        g = g.rename(columns={"size": "n", "sum": "team_a_wins", "mean": "team_a_win_rate"})
        g.insert(0, "breakdown", label)
        return g

    out = [agg(["season"], "season"), agg(["season", "stage_id", "stage"], "season_stage"), agg(["phase"], "phase_all_seasons"),
           agg(["season", "phase"], "season_phase"), agg(["venue_relation"], "venue_all_seasons"),
           agg(["season", "venue_relation"], "season_venue")]
    s26 = d[d.season.str.startswith("KPL2026")]
    g = s26.groupby(["season", "phase", "venue_relation"]).y.agg(["size", "sum", "mean"]).reset_index()
    g = g.rename(columns={"size": "n", "sum": "team_a_wins", "mean": "team_a_win_rate"})
    g.insert(0, "breakdown", "2026_season_phase_venue")
    out.append(g)
    tot = pd.DataFrame([{"breakdown": "all", "n": len(d), "team_a_wins": d.y.sum(), "team_a_win_rate": d.y.mean()}])
    unmatched = int(d.stage_id.isna().sum())
    return pd.concat([tot] + out, ignore_index=True), unmatched
