"""Expanding-window evaluation of the v0.5 player/roster ladder (deployable) and oracle ablations (not)."""
import itertools

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from openkpl.evaluation.calibration import EPS, evaluate
from openkpl.player_model import features as F
from openkpl.player_model import models as M
from openkpl.player_model.ratings import PlayerElo

RATING_GRID = [("P2", "game", 16.0, 10.0)] + [c for c in itertools.product(("P1", "P2"), ("game", "series"),
                                                                         (8.0, 16.0, 32.0, 64.0), (0.0, 10.0))
                                               if c != ("P2", "game", 16.0, 10.0)]
METHODS = ["DECAY"] + [m for m in F.CORE_METHODS if m != "DECAY"]
DEPLOYABLE = ["B5", "B5R", "B6", "B7", "B8", "B9", "B10", "B11", "B12"]
EXPLORATORY = ["X1", "X2", "X3"]
ORACLES = ["O1", "O2", "O3"]
ISOTONIC_MIN_N = 500
BOOTSTRAP_B = 2000
SEED = 20260929
PERM_REPEATS = 20
ALL_NAMES = (F.RATING_FEATURES + F.BENCH_RATING_FEATURES + F.ROSTER_FEATURES + F.BENCH_HIST_FEATURES
             + F.HERO_FEATURES)


def cfg_id(cfg, method):
    v, mode, k, m = cfg
    return f"{v}|{mode}|k={k:g}|m={m:g}|core={method}"


def base_frame(timeline, bench_pred):
    b5 = bench_pred[bench_pred.model_id == "B5"].set_index("series_id")
    rows = []
    for s in timeline:
        if s["series_id"] in b5.index:
            r = b5.loc[s["series_id"]]
            if int(r.actual_team_a_win) != s["y"]:
                raise AssertionError(f"label mismatch for {s['series_id']}")
            rows.append({"series_id": s["series_id"], "season": s["season"], "stage": s["stage"], "t": s["t"],
                         "team_a": s["a"], "team_b": s["b"], "y": s["y"], "has_lineup": s["has_lineup"],
                         "p_b5": float(r.predicted_p_team_a), "b5_fold": r.fold_id})
    df = pd.DataFrame(rows)
    df["logit_b5"] = M.logit(df.p_b5)
    return df.set_index("series_id", drop=False)


def build_frames(timeline, base):
    rankings, static, hist = F.history_pass(timeline)
    frames, oracles = {}, {}
    for cfg in RATING_GRID:
        out, orc = F.rating_pass(timeline, rankings, PlayerElo(*cfg), METHODS)
        o = pd.DataFrame.from_dict(orc, orient="index")
        o = M.add_diffs(o, F.ORACLE_RATING + F.ORACLE_ROTATION)
        oracles[cfg] = o
        for m in METHODS:
            r = pd.DataFrame.from_dict(out[m], orient="index")
            st = pd.DataFrame.from_dict({k[0]: v for k, v in static.items() if k[1] == m}, orient="index")
            f = M.add_diffs(r.join(st), ALL_NAMES)
            frames[(cfg, m)] = base.join(f, how="left")
    return frames, oracles, rankings, hist


def _score_b7(tr, va, frame):
    cols = M.columns(["PLAYER"])
    _, p = M.fit_predict(lambda: M.logistic(M.RUNG_C), frame.loc[tr.index], frame.loc[va.index], cols)
    return M.log_loss(va.y, p)


def run_folds(base, frames, oracles):
    seasons = base.groupby("season").t.min().sort_values().index.tolist()
    preds, oracle_preds, selections, fitted = [], [], [], {}
    loo = []
    for i, v in enumerate(seasons[1:], start=1):
        train_ids = base.index[base.season.isin(seasons[:i])]
        test_ids = base.index[base.season == v]
        tr0 = base.loc[train_ids]
        cands = [((c, m), frames[(c, m)]) for c in RATING_GRID for m in METHODS]
        key, frame, tab = M.select(tr0, cands, _score_b7)
        cid = cfg_id(*key)
        selections.append({"validation_season": v, "stage": "rating_config_and_core_method", "selected": cid,
                           "n_candidates": len(cands), "inner_log_loss": tab.inner_log_loss.min(),
                           "note": tab.note.iloc[0] if "note" in tab else ""})
        tr, te = frame.loc[train_ids], frame.loc[test_ids]

        def emit(mid, p, extra=None):
            preds.append(pd.DataFrame({"series_id": te.series_id.values, "season": v, "model_id": mid,
                                       "p": np.asarray(p, float), "y": te.y.values, "feature_config": cid,
                                       **(extra or {})}))

        emit("B5", te.p_b5.values, {"hyperparameter": "frozen v0.3.1 B5 prediction"})
        for mid, groups in M.LADDER.items():
            _, p = M.fit_predict(lambda: M.logistic(M.RUNG_C), tr, te, M.columns(groups))
            emit(mid, p, {"hyperparameter": f"C={M.RUNG_C}"})
        _, p1 = M.fit_predict(lambda: M.logistic(M.RUNG_C), tr, te, M.EXPLORATORY_X1)
        emit("X1", p1, {"hyperparameter": "post-hoc exploratory; player Elo only"})
        _, p = M.fit_predict(lambda: M.logistic(M.RUNG_C), tr, te, M.EXPLORATORY_X2)
        emit("X2", p, {"hyperparameter": "post-hoc exploratory; B5 + core strength"})
        emit("X3", 1 / (1 + np.exp(-(0.5 * te.logit_b5.values + 0.5 * M.logit(p1)))),
             {"hyperparameter": "post-hoc exploratory; fixed 50/50 logit average of B5 and X1"})
        cols = M.columns(M.ALL_SAFE)
        c_key, _, ctab = M.select(tr, [(c, c) for c in [M.B11_DEFAULT_C] + [x for x in M.B11_C_GRID
                                                                          if x != M.B11_DEFAULT_C]],
                                  lambda a, b, c: M.log_loss(b.y, M.fit_predict(lambda: M.logistic(c), a, b, cols)[1]))
        m11, p = M.fit_predict(lambda: M.logistic(c_key), tr, te, cols)
        emit("B11", p, {"hyperparameter": f"C={c_key}"})
        selections.append({"validation_season": v, "stage": "B11_C", "selected": str(c_key),
                           "n_candidates": len(M.B11_C_GRID), "inner_log_loss": ctab.inner_log_loss.min(), "note": ""})
        grid = [M.B12_DEFAULT] + [g for g in M.B12_GRID if g != M.B12_DEFAULT]
        g_key, g_obj, gtab = M.select(tr, [(str(g), g) for g in grid],
                                      lambda a, b, g: M.log_loss(b.y, M.fit_predict(lambda: M.hgb(g), a, b, cols)[1]))
        m12, p = M.fit_predict(lambda: M.hgb(g_obj), tr, te, cols)
        emit("B12", p, {"hyperparameter": g_key})
        selections.append({"validation_season": v, "stage": "B12_params", "selected": g_key,
                           "n_candidates": len(grid), "inner_log_loss": gtab.inner_log_loss.min(), "note": ""})
        fitted[v] = {"B11": (m11, te, cols), "B12": (m12, te, cols)}
        for g in M.ALL_SAFE:
            keep = [x for x in M.ALL_SAFE if x != g]
            _, p = M.fit_predict(lambda: M.logistic(c_key), tr, te, M.columns(keep))
            loo.append(pd.DataFrame({"series_id": te.series_id.values, "season": v, "variant": f"B11 minus {g}",
                                     "p": p, "y": te.y.values}))
        o = oracles[key[0]]
        otr, ote = tr.join(o, how="left"), te.join(o, how="left")
        for oid in ORACLES:
            oracle_preds.append(pd.DataFrame({"series_id": te.series_id.values, "season": v, "model_id": oid,
                                              "p": M.fit_oracle(oid, otr, ote), "y": te.y.values,
                                              "feature_config": cid, "label": "ORACLE / NON-PROSPECTIVE"}))
    return (pd.concat(preds, ignore_index=True), pd.concat(oracle_preds, ignore_index=True),
            pd.DataFrame(selections), fitted, pd.concat(loo, ignore_index=True))


# ---- calibration ---------------------------------------------------------------

def calibrate(preds, seasons):
    """Per model and season, calibrators are fit only on that model's predictions for earlier
    validation seasons (each produced out-of-fold by an earlier fold)."""
    out = []
    for mid, g in preds.groupby("model_id", sort=False):
        g = g.copy()
        g["p_raw"] = g.p
        g["p_platt"], g["p_isotonic"], g["p_selected"], g["selected_method"] = np.nan, np.nan, np.nan, "raw"
        for v in seasons:
            cur = g.season == v
            prior = g[g.season.isin(seasons[:seasons.index(v)])]
            if len(prior) and prior.y.nunique() == 2:
                lr = LogisticRegression(C=1e6, max_iter=1000).fit(M.logit(prior.p_raw)[:, None], prior.y)
                g.loc[cur, "p_platt"] = lr.predict_proba(M.logit(g.loc[cur, "p_raw"])[:, None])[:, 1]
            if len(prior) >= ISOTONIC_MIN_N:
                iso = IsotonicRegression(y_min=EPS, y_max=1 - EPS, out_of_bounds="clip").fit(prior.p_raw, prior.y)
                g.loc[cur, "p_isotonic"] = iso.predict(g.loc[cur, "p_raw"])
            done = g[g.season.isin(seasons[:seasons.index(v)])]
            scores = {"raw": 0.0}
            for meth in ("platt", "isotonic"):
                d = done[done[f"p_{meth}"].notna()]
                if len(d):
                    scores[meth] = M.log_loss(d.y, d[f"p_{meth}"]) - M.log_loss(d.y, d.p_raw)
            method = min(scores, key=lambda k: (round(scores[k], 10), ["raw", "platt", "isotonic"].index(k)))
            vals = g.loc[cur, f"p_{method}"]
            if vals.isna().any():
                method, vals = "raw", g.loc[cur, "p_raw"]
            g.loc[cur, "p_selected"], g.loc[cur, "selected_method"] = vals.values, method
        out.append(g)
    return pd.concat(out, ignore_index=True)


def calibration_metrics(cal):
    rows = []
    for mid, g in cal.groupby("model_id", sort=False):
        for meth in ("raw", "platt", "isotonic", "selected"):
            d = g[g[f"p_{meth}"].notna()]
            if not len(d):
                continue
            e = evaluate(d.y, d[f"p_{meth}"])
            rows.append({"model_id": mid, "calibration": meth, "n": e["n"], "log_loss": e["log_loss"],
                         "brier": e["brier"], "ece": e["ece"], "calibration_intercept": e["calibration_intercept"],
                         "calibration_slope": e["calibration_slope"],
                         "seasons": "|".join(sorted(d.season.unique())),
                         "note": "raw rows for the same seasons: " + (
                             f"log_loss={M.log_loss(d.y, d.p_raw):.5f}" if meth in ("platt", "isotonic") else "")})
    return pd.DataFrame(rows)


# ---- metrics, deltas, bootstrap --------------------------------------------------

def metric_table(preds, col="p", by=None):
    keys = ["model_id"] + ([by] if by else [])
    rows = []
    for k, g in preds.groupby(keys, sort=False):
        k = k if isinstance(k, tuple) else (k,)
        rows.append({**dict(zip(keys, k)), **evaluate(g.y, g[col])})
    return pd.DataFrame(rows)


def deltas(preds, ref="B5", by=None):
    wide = preds.pivot_table(index=["series_id", "season"], columns="model_id", values="p").reset_index()
    y = preds.drop_duplicates("series_id").set_index("series_id").y
    wide["y"] = wide.series_id.map(y)
    rows = []
    groups = [("ALL", wide)] if by is None else list(wide.groupby("season"))
    for name, w in groups:
        for mid in [c for c in preds.model_id.unique() if c != ref]:
            ll = M.log_loss(w.y, w[mid]) - M.log_loss(w.y, w[ref])
            br = float(np.mean((w[mid] - w.y) ** 2) - np.mean((w[ref] - w.y) ** 2))
            rows.append({"season": name, "model_id": mid, "reference": ref, "n": len(w),
                         "delta_log_loss": ll, "delta_brier": br})
    return pd.DataFrame(rows)


def paired_bootstrap(preds, ref="B5", b=BOOTSTRAP_B, seed=SEED):
    """Series-level paired bootstrap, resampling series within each validation season."""
    wide = preds.pivot_table(index=["series_id", "season"], columns="model_id", values="p").reset_index()
    y = preds.drop_duplicates("series_id").set_index("series_id").y
    wide["y"] = wide.series_id.map(y)
    rng = np.random.default_rng(seed)
    strata = [np.flatnonzero(wide.season.to_numpy() == s) for s in wide.season.unique()]
    idx = np.stack([np.concatenate([rng.choice(ix, len(ix), replace=True) for ix in strata]) for _ in range(b)])
    yv = wide.y.to_numpy(float)

    def ll_vec(p):
        p = np.clip(p, EPS, 1 - EPS)
        return -(yv * np.log(p) + (1 - yv) * np.log(1 - p))

    ref_ll, ref_br = ll_vec(wide[ref].to_numpy()), (wide[ref].to_numpy() - yv) ** 2
    rows = []
    for mid in [c for c in preds.model_id.unique() if c != ref]:
        dl = ll_vec(wide[mid].to_numpy()) - ref_ll
        db = (wide[mid].to_numpy() - yv) ** 2 - ref_br
        bl, bb = dl[idx].mean(axis=1), db[idx].mean(axis=1)
        rows.append({"model_id": mid, "reference": ref, "n_series": len(wide), "bootstrap_samples": b,
                     "mean_delta_log_loss": float(dl.mean()),
                     "delta_log_loss_ci_low": float(np.quantile(bl, 0.025)),
                     "delta_log_loss_ci_high": float(np.quantile(bl, 0.975)),
                     "frac_samples_beats_ref_log_loss": float((bl < 0).mean()),
                     "mean_delta_brier": float(db.mean()),
                     "delta_brier_ci_low": float(np.quantile(bb, 0.025)),
                     "delta_brier_ci_high": float(np.quantile(bb, 0.975)),
                     "frac_samples_beats_ref_brier": float((bb < 0).mean()),
                     "method": "paired, series-level, stratified by validation season"})
    return pd.DataFrame(rows)


def permutation_importance(fitted, repeats=PERM_REPEATS, seed=SEED):
    groups = {"TEAM": M.TEAM, **{g: M.SAFE_DIFF[g] for g in M.ALL_SAFE}}
    rng = np.random.default_rng(seed)
    rows = []
    for v, models in fitted.items():
        for mid, (model, te, cols) in models.items():
            x = te[cols].to_numpy(float)
            base = M.log_loss(te.y, model.predict_proba(x)[:, 1])
            for g, gcols in groups.items():
                ix = [cols.index(c) for c in gcols]
                inc = []
                for _ in range(repeats):
                    xp = x.copy()
                    perm = rng.permutation(len(xp))
                    xp[:, ix] = x[perm][:, ix]
                    inc.append(M.log_loss(te.y, model.predict_proba(xp)[:, 1]) - base)
                rows.append({"model_id": mid, "season": v, "group": g, "n": len(te),
                             "mean_log_loss_increase": float(np.mean(inc)), "sd": float(np.std(inc))})
    per = pd.DataFrame(rows)
    agg = per.groupby(["model_id", "group"]).apply(
        lambda d: pd.Series({"n": d.n.sum(), "mean_log_loss_increase": np.average(d.mean_log_loss_increase, weights=d.n),
                             "seasons_positive": int((d.mean_log_loss_increase > 0).sum()),
                             "seasons": len(d)}), include_groups=False).reset_index()
    agg["season"] = "ALL"
    agg["method"] = f"grouped permutation within each validation season, {repeats} repeats; not causal"
    return pd.concat([agg, per.assign(method="per season")], ignore_index=True)
