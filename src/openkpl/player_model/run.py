"""v0.5 player + roster prospective benchmark. Offline; reads locked inputs only.

    .venv/bin/python -m openkpl.player_model.run
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.player_model import data, experiment as E, features as F, figures, lock, models as M, rotation

OUT = Path("reports/player_model")
ORACLE_OUT = OUT / "oracle"
MODEL_DATA = Path("data/processed/modeling")
FIG = Path("figures/player_model")
ORDER = E.DEPLOYABLE + E.EXPLORATORY
METRIC_COLS = ["model_id", "n", "log_loss", "brier", "accuracy", "roc_auc", "ece", "calibration_intercept",
               "calibration_slope", "mean_predicted_p", "observed_win_rate", "notes"]


def feature_dictionary():
    rows = []
    for g, cols in M.GROUPS.items():
        for c in cols:
            rows.append({"feature": c, "group": g, "class": "PRE_SERIES_SAFE",
                         "in_models": c != "top5_player_rating_sum",
                         "note": "excluded from models: equals 5x top5 mean when the pool has >= 5 players"
                         if c == "top5_player_rating_sum" else ""})
    rows.append({"feature": "logit_b5", "group": "TEAM", "class": "PRE_SERIES_SAFE", "in_models": True,
                 "note": "logit of the frozen v0.3.1 B5 out-of-time prediction"})
    for c in F.ORACLE_RATING + F.ORACLE_ROTATION + ["oracle_players_a", "oracle_players_b"]:
        rows.append({"feature": c, "group": "ORACLE", "class": "RETROSPECTIVE_ONLY", "in_models": False,
                     "note": "uses the target series' actual lineup; oracle models O1-O3 only"})
    return pd.DataFrame(rows)


def missing_tables(feat):
    names = [c for c in feat.columns if c.endswith("_diff")]
    by_season = pd.DataFrame([{"season": s, "feature": c, "n": len(g), "n_missing": int(g[c].isna().sum()),
                               "pct_missing": round(100 * g[c].isna().mean(), 2)}
                              for s, g in feat.groupby("season") for c in names])
    miss = feat[names].isna()
    series = feat.loc[miss.any(axis=1), ["series_id", "season", "team_a", "team_b", "has_lineup"]].copy()
    series["n_missing_features"] = miss.sum(axis=1)[miss.any(axis=1)].values
    series["missing_features"] = [",".join(c for c in names if m[c]) for _, m in miss[miss.any(axis=1)].iterrows()]
    series["handling"] = "median imputation + missingness indicator, fit on the training fold only; row kept"
    return by_season, series


def main():
    bad = lock.check()
    if bad:
        raise SystemExit(f"HARD FAILURE: locked inputs changed before run: {bad}")
    print("lock verified before run")
    canonical, games, apps = data.load()
    tl = data.build_timeline(canonical, games, apps)
    bench = pd.read_parquet(data.BENCH_PRED)
    base = E.base_frame(tl, bench)
    frames, oracles, rankings, hist = E.build_frames(tl, base)
    preds, opreds, sel, fitted, loo = E.run_folds(base, frames, oracles)
    seasons = preds.season.drop_duplicates().tolist()
    OUT.mkdir(parents=True, exist_ok=True); ORACLE_OUT.mkdir(exist_ok=True); MODEL_DATA.mkdir(parents=True, exist_ok=True)

    cfg_by_season = sel[sel.stage == "rating_config_and_core_method"].set_index("validation_season").selected
    lookup = {E.cfg_id(c, m): (c, m) for c in E.RATING_GRID for m in E.METHODS}
    feat_rows, orc_rows = [], []
    for s, g in base.groupby("season", sort=False):
        cid = cfg_by_season.get(s, E.cfg_id(E.RATING_GRID[0], E.METHODS[0]))
        key = lookup[cid]
        role = "validation (fold-selected config)" if s in cfg_by_season.index else "training-only (a-priori default config)"
        feat_rows.append(frames[key].loc[g.index].assign(feature_config=cid, feature_config_role=role))
        o = oracles[key[0]].loc[oracles[key[0]].index.intersection(g.index)].copy()
        o["oracle_players_a"] = o.oracle_players_a.map("|".join)
        o["oracle_players_b"] = o.oracle_players_b.map("|".join)
        orc_rows.append(o.assign(series_id=o.index, season=s, feature_config=cid, label="ORACLE / NON-PROSPECTIVE"))
    feat = pd.concat(feat_rows)
    assert not [c for c in feat.columns if c.startswith("oracle_")]
    feat.reset_index(drop=True).to_parquet(MODEL_DATA / "player_roster_features.parquet", index=False)
    pd.concat(orc_rows).reset_index(drop=True).to_parquet(ORACLE_OUT / "oracle_features.parquet", index=False)

    cal = E.calibrate(preds, seasons)
    cal.to_parquet(MODEL_DATA / "player_roster_predictions.parquet", index=False)
    opreds.to_parquet(ORACLE_OUT / "oracle_predictions.parquet", index=False)

    metrics = E.metric_table(preds).set_index("model_id").loc[ORDER].reset_index()
    metrics["model_class"] = ["frozen v0.3.1 reference", "control: B5 recalibrated, no new features"] + \
        ["pre-specified ladder"] * 7 + ["post-hoc exploratory"] * 3
    metrics[METRIC_COLS + ["model_class"]].to_csv(OUT / "model_metrics.csv", index=False)
    season = E.metric_table(preds, by="season")
    season[["model_id", "season"] + METRIC_COLS[1:]].to_csv(OUT / "season_metrics.csv", index=False)
    d_all = pd.concat([E.deltas(preds, "B5"), E.deltas(preds, "B5", by="season"),
                       E.deltas(preds, "B5R"), E.deltas(preds, "B5R", by="season")], ignore_index=True)
    d_all.to_csv(OUT / "model_deltas.csv", index=False)
    boot = pd.concat([E.paired_bootstrap(preds, "B5"), E.paired_bootstrap(preds, "B5R")], ignore_index=True)
    boot.to_csv(OUT / "bootstrap_deltas.csv", index=False)
    calm = E.calibration_metrics(cal)
    calm.to_csv(OUT / "calibration_metrics.csv", index=False)

    abl_map = {"B5R": "Team only", "B7": "+ Player", "B6": "+ Roster", "B8": "+ Player + Roster",
               "B9": "+ Bench", "B10": "+ Player-Hero"}
    m = metrics.set_index("model_id")
    abl = [{"ablation": lab, "model_id": mid, "groups": "TEAM" + "".join(f"+{g}" for g in M.LADDER[mid]),
            "log_loss": m.loc[mid, "log_loss"], "brier": m.loc[mid, "brier"],
            "delta_log_loss_vs_team_only": m.loc[mid, "log_loss"] - m.loc["B5R", "log_loss"],
            "delta_brier_vs_team_only": m.loc[mid, "brier"] - m.loc["B5R", "brier"]} for mid, lab in abl_map.items()]
    for v, g in loo.groupby("variant"):
        ll, br = M.log_loss(g.y, g.p), float(np.mean((g.p - g.y) ** 2))
        abl.append({"ablation": v, "model_id": "B11-LOGO", "groups": v, "log_loss": ll, "brier": br,
                    "delta_log_loss_vs_team_only": ll - m.loc["B5R", "log_loss"],
                    "delta_brier_vs_team_only": br - m.loc["B5R", "brier"],
                    "delta_log_loss_vs_full_B11": ll - m.loc["B11", "log_loss"]})
    pd.DataFrame(abl).to_csv(OUT / "feature_ablation.csv", index=False)
    imp = E.permutation_importance(fitted)
    imp.to_csv(OUT / "feature_importance.csv", index=False)

    om = E.metric_table(opreds)
    ref = E.metric_table(preds[preds.model_id == "B5"])
    om = pd.concat([ref, om], ignore_index=True)
    om["label"] = ["reference (deployable)"] + ["ORACLE / NON-PROSPECTIVE"] * 3
    om.to_csv(ORACLE_OUT / "oracle_metrics.csv", index=False)
    both = pd.concat([preds[preds.model_id == "B5"], opreds], ignore_index=True)
    E.paired_bootstrap(both, "B5").assign(label="ORACLE / NON-PROSPECTIVE").to_csv(
        ORACLE_OUT / "oracle_bootstrap_vs_b5.csv", index=False)
    E.metric_table(opreds, by="season").to_csv(ORACLE_OUT / "oracle_season_metrics.csv", index=False)

    last_cfg = lookup[cfg_by_season.iloc[-1]]
    elo, trace = rotation.final_ratings(tl, last_cfg[0])
    rot = rotation.readiness(tl, hist, elo, last_cfg[1])
    rot.to_csv(OUT / "rotation_readiness_2026.csv", index=False)

    sel.to_csv(OUT / "fold_selections.csv", index=False)
    feature_dictionary().to_csv(OUT / "feature_dictionary.csv", index=False)
    ms, mser = missing_tables(feat)
    ms.to_csv(OUT / "missing_data_by_season.csv", index=False)
    mser.to_csv(OUT / "missing_data_series.csv", index=False)
    figs = figures.make(FIG, boot, season, preds, trace, rot, ORDER)

    bad = lock.check()
    if bad:
        raise SystemExit(f"HARD FAILURE: locked inputs changed during run: {bad}")
    summary = {"n_eval_series": int(preds[preds.model_id == "B5"].shape[0]), "seasons": seasons,
               "figures": figs, "lock_after_run": "verified", "final_state_config": cfg_by_season.iloc[-1]}
    (OUT / "run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
