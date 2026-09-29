"""v0.6 game-level strength, series probability and draft information benchmark (offline).

    .venv/bin/python -m openkpl.game_draft_model.run
"""
import json
from pathlib import Path

import pandas as pd

from openkpl.game_draft_model import draft as D
from openkpl.game_draft_model import experiment_a as A
from openkpl.game_draft_model import experiment_b as B
from openkpl.game_draft_model import figures, games as GM, lock
from openkpl.player_model import data

OUT = Path("reports/game_draft_model")
MD = Path("data/processed/modeling")
FIG = Path("figures/game_draft_model")
GAME_MODELS = ["G0", "G1", "G2", "G3", "G4", "G*", "G5"]
SERIES_MODELS = ["S0", "S1", "S2", "S3", "S4", "S1F"]
DRAFT_MODELS = ["D0", "D0R", "D1", "D1R", "D2", "D3", "D4", "D5", "D6"]
SERIES_N_PARAMS = {"S0": "0 (frozen B5)", "S1": "game Elo only (1-2)", "S2": "game Elo + 7 (logit, intercept, 5 game-number)",
                   "S3": "game Elo + 4 (intercept, strength, score_diff, prev_winner)", "S4": "game Elo + 3 (intercept, 2 logits)",
                   "S1F": "game Elo + 4 (intercept, logit, BO7, BO7 x logit)"}


def _with_ci(m, boot, keys):
    return m.merge(boot, on=keys, how="left")


def main():
    bad = lock.check()
    if bad:
        raise SystemExit(f"HARD FAILURE: locked artifacts changed before run: {bad}")
    print("v0.6 lock verified before run")
    OUT.mkdir(parents=True, exist_ok=True); MD.mkdir(parents=True, exist_ok=True)
    canonical, games, _ = data.load()
    bench = pd.read_parquet(data.BENCH_PRED)
    identified = pd.read_parquet(GM.IDENTIFIED)
    tl = GM.build(canonical, games, bench)
    GM.eligibility(tl).to_csv(OUT / "game_eligibility_by_season.csv", index=False)
    runs = A.run_all(tl)
    gp, sp, sel, st = A.run_folds(tl, runs)
    fmt_map = {s["series_id"]: s["format"] for s in tl}

    # sensitivity: WZRY winner fills missing kplow winners (training-dominant); evaluated on primary rows
    tlw = GM.build(canonical, games, bench, identified, fill_wzry=True)
    gpw, spw, selw, _ = A.run_folds(tlw, A.run_all(tlw))
    gpw = gpw[gpw.game_key.isin(set(gp.game_key))]

    gp.to_parquet(MD / "game_strength_predictions.parquet", index=False)
    sp.to_parquet(MD / "series_strength_predictions_v06.parquet", index=False)
    sel.drop(columns="pkey").to_csv(OUT / "fold_selections_game.csv", index=False)

    gm = A.metrics(gp, ["model_id", "mode"])
    gboot = []
    for mode in ("PRE_SERIES", "LIVE_SERIES"):
        d = gp[gp["mode"] == mode]
        gboot.append(A.cluster_bootstrap(d, "G1", GAME_MODELS, "game_key").assign(mode=mode))
    live_vs_pre = []
    for mdl in GAME_MODELS:
        d = gp[gp.model_id == mdl].assign(model_id=lambda x: x["mode"])
        live_vs_pre.append(A.cluster_bootstrap(d, "PRE_SERIES", ["LIVE_SERIES"], "game_key").assign(model_id=mdl, mode="LIVE_vs_PRE"))
    gboot = pd.concat(gboot + live_vs_pre, ignore_index=True)
    gb = gboot[gboot["mode"] != "LIVE_vs_PRE"].rename(columns=lambda c: c if c in ("model_id", "mode") else f"vs_G1_{c}")
    gm = gm.merge(gb[["model_id", "mode", "vs_G1_mean_delta_log_loss", "vs_G1_delta_log_loss_ci_low",
                      "vs_G1_delta_log_loss_ci_high", "vs_G1_mean_delta_brier", "vs_G1_delta_brier_ci_low",
                      "vs_G1_delta_brier_ci_high"]], on=["model_id", "mode"], how="left")
    gm["mechanism"] = gm.model_id.map({**A.MECH, "G*": "per-fold best of G1-G4 by training PRE-SERIES log loss"})
    gm["n_fitted_parameters"] = gm.model_id.map({**A.N_PARAMS, "G*": "1-2"})
    gm["train_rows_first_to_last_fold"] = gm.model_id.map(lambda m: f"{gp.train_rows.min()}-{gp.train_rows.max()}")
    sens = A.metrics(gpw, ["model_id", "mode"]).assign(mechanism="SENSITIVITY_WZRY_FILL: WZRY winner fills missing kplow "
                                                                   "winners (143 identified games, mostly 2022S2)")
    pd.concat([gm, sens], ignore_index=True).to_csv(OUT / "game_model_metrics.csv", index=False)
    gboot.to_csv(OUT / "game_bootstrap_deltas.csv", index=False)
    A.metrics(gp, ["model_id", "mode", "season"]).to_csv(OUT / "game_model_by_season.csv", index=False)

    sm = A.metrics(sp, ["model_id"])
    sboot = A.cluster_bootstrap(sp, "S0", SERIES_MODELS, "series_id", cluster="series_id")
    sm = sm.merge(sboot.rename(columns=lambda c: c if c == "model_id" else f"vs_B5_{c}"), on="model_id", how="left")
    sm["n_fitted_parameters"] = sm.model_id.map(SERIES_N_PARAMS)
    sm["train_series_first_to_last_fold"] = f"{sp.train_series.min()}-{sp.train_series.max()}"
    sm.to_csv(OUT / "series_probability_metrics.csv", index=False)
    A.metrics(sp, ["model_id", "season"]).to_csv(OUT / "series_probability_by_season.csv", index=False)
    pre = gp[(gp.model_id == "G*") & (gp["mode"] == "PRE_SERIES")]
    ftab = A.format_table(sp, pre)
    ftab.to_csv(OUT / "series_probability_by_format.csv", index=False)
    A.format_interaction(sp).to_csv(OUT / "series_format_interaction.csv", index=False)

    rows_games = pd.concat([runs[(r.selected, r.pkey)][0] for r in sel[sel.model == "G*"].itertuples()]).drop_duplicates("game_key")
    assoc = A.state_association(pre, rows_games, fmt_map)
    long = pd.concat([st.drop_duplicates("game_key").assign(model_id="BASE", p=lambda d: d.p_base)[["game_key", "series_id", "season", "model_id", "p", "y"]],
                      st[["game_key", "series_id", "season", "variable_set", "p", "y"]].rename(columns={"variable_set": "model_id"})])
    oot = A.cluster_bootstrap(long, "BASE", list(A.STATE_SETS), "game_key")
    oot["analysis"] = "out-of-time: delta game log loss vs strength-only logistic (negative = variable helps)"
    oot["decision"] = ["KEEP_CANDIDATE" if h < 0 else "DISCARD" for h in oot.delta_log_loss_ci_high]
    pd.concat([assoc, oot.rename(columns={"model_id": "variable_set"})], ignore_index=True).to_csv(
        OUT / "series_state_analysis.csv", index=False)

    # ---- Experiment B
    hf, sf, cf, ev = D.load()
    gt = D.game_table(identified, tl)
    dp, seq, dsel, cx, feats = B.run(gt, hf, sf, cf, ev, runs, sel)
    feats.reset_index(drop=True).to_parquet(MD / "draft_model_features.parquet", index=False)
    dp.to_parquet(MD / "draft_predictions.parquet", index=False)
    seq.to_parquet(MD / "sequential_draft_predictions.parquet", index=False)
    dsel.to_csv(OUT / "fold_selections_draft.csv", index=False)
    cx.to_csv(OUT / "draft_model_complexity.csv", index=False)
    dm = A.metrics(dp, ["model_id"])
    dboot = pd.concat([A.cluster_bootstrap(dp, "D0", DRAFT_MODELS, "game_key"),
                       A.cluster_bootstrap(dp, "D0R", DRAFT_MODELS, "game_key")], ignore_index=True)
    dboot.to_csv(OUT / "draft_bootstrap_deltas.csv", index=False)
    b0 = dboot[dboot.reference == "D0"].rename(columns=lambda c: c if c == "model_id" else f"vs_D0_{c}")
    dm = dm.merge(b0, on="model_id", how="left")
    cxa = cx.groupby("model_id").agg(n_features=("n_features", "max"), n_fitted_parameters_max=("n_fitted_parameters", "max"),
                                     train_rows_per_fold=("train_rows", lambda x: "|".join(map(str, x))),
                                     validation_rows=("validation_rows", "sum")).reset_index()
    dm.merge(cxa, on="model_id").to_csv(OUT / "draft_model_metrics.csv", index=False)
    dbs = A.metrics(dp, ["model_id", "season"]).merge(cx[["validation_season", "model_id", "train_rows", "hyperparameters"]]
                                                      .rename(columns={"validation_season": "season"}), on=["model_id", "season"])
    dbs.to_csv(OUT / "draft_model_by_season.csv", index=False)
    m = dm.set_index("model_id")
    steps = [("D0R", "D0", "recalibration only"), ("D1", "D0R", "+ hero individual strength"),
             ("D2", "D1", "+ team x hero familiarity"), ("D3", "D2", "+ synergy"), ("D4", "D3", "+ counter"),
             ("D5", "D4", "+ ban strength, C tuned"), ("D6", "D5", "gradient boosting, same features"),
             ("D1R", "D1", "hero strength with recency weighting (patch proxy)")]
    pd.DataFrame([{"model_id": a, "compared_to": b, "added": lab, "log_loss": m.loc[a, "log_loss"],
                   "delta_log_loss_vs_previous": m.loc[a, "log_loss"] - m.loc[b, "log_loss"],
                   "delta_brier_vs_previous": m.loc[a, "brier"] - m.loc[b, "brier"],
                   "delta_log_loss_vs_D0": m.loc[a, "log_loss"] - m.loc["D0", "log_loss"]} for a, b, lab in steps]).to_csv(
        OUT / "draft_feature_ablation.csv", index=False)
    w, dig, by_team = B.information_gain(dp, gt, ev, post="D5")
    dig.to_csv(OUT / "draft_information_gain.csv", index=False)
    by_team.to_csv(OUT / "draft_information_by_team.csv", index=False)
    seq_m = A.metrics(seq.assign(model_id=seq.step), ["model_id"]).rename(columns={"model_id": "step"})
    seq_m["checkpoint"] = seq_m.step.map(D.CHECKPOINTS).fillna("")
    sl = seq.assign(model_id=seq.step.map(lambda j: f"step_{j:02d}"))
    sboot2 = A.cluster_bootstrap(sl, "step_00", [f"step_{j:02d}" for j in range(1, 19)], "game_key")
    seq_m = seq_m.merge(sboot2.assign(step=sboot2.model_id.str[5:].astype(int)).drop(columns="model_id"), on="step", how="left")
    seq_m.to_csv(OUT / "sequential_draft_metrics.csv", index=False)
    figs = figures.make(FIG, gboot[gboot["mode"] != "LIVE_vs_PRE"], sboot, ftab, sp, dboot, dp, dig, seq_m)
    bad = lock.check()
    if bad:
        raise SystemExit(f"HARD FAILURE: locked artifacts changed during run: {bad}")
    summary = {"eval_games": int(len(pre)), "eval_series": int(sp[sp.model_id == "S0"].shape[0]),
               "draft_eval_games": int(dp[dp.model_id == "D0"].shape[0]), "figures": figs, "lock_after_run": "verified"}
    (OUT / "run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
