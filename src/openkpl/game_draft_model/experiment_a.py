"""Experiment A: game-level team strength (G0-G5, PRE-SERIES vs LIVE-SERIES) and series probability (S0-S4).

Folds: validation season v in 2023S1..2026S2; training = every earlier season (games with a
known kplow winner exist from 2022S2). Hyperparameters are selected by online PRE-SERIES game
log loss over training games only (v0.3 convention: candidate runs the full timeline online,
selection scores only rows before the validation start). Stacked models (G5, S2-S4, S1F) are fit
on training rows only.
"""
import itertools
import math

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from openkpl.evaluation.calibration import EPS, evaluate
from openkpl.game_draft_model import elo as E
from openkpl.game_draft_model.series_math import WINS_NEEDED, game_prob_from_series, series_prob, series_prob_state

K_GRID = [8.0, 12.0, 16.0, 24.0, 32.0, 48.0]
H_GRID = [30.0, 60.0, 120.0, 240.0, 480.0]
RHO_GRID = [0.0, 0.25, 0.5, 0.75, 1.0]
DEFAULT = {"k": 24.0, "half_life_days": math.inf, "rho": 1.0}
FAMILIES = {
    "G1": [{"k": k} for k in K_GRID],
    "G2": [{"k": k, "half_life_days": h} for k, h in itertools.product(K_GRID, H_GRID)],
    "G3": [{"k": k, "rho": r} for k, r in itertools.product(K_GRID, RHO_GRID)],
    "G4": [{"k": k, "rho": r, "series_aware": True} for k, r in itertools.product(K_GRID, RHO_GRID)],
}
MECH = {"G0": "constant 0.5", "G1": "vanilla game Elo (K tuned)", "G2": "game Elo + inactivity decay (K, half-life tuned)",
        "G3": "game Elo + season-start mean reversion (K, rho tuned)",
        "G4": "series-aware game Elo: games scored vs frozen pre-series ratings, applied at series end (K, rho tuned)",
        "G5": "logistic stack of best-of-G1..G4 (by training log loss) + frozen B5 converted to game probability"}
N_PARAMS = {"G0": 0, "G1": 1, "G2": 2, "G3": 2, "G4": 2, "G5": 3}
STATE_SETS = {
    "game_number": ["gn_c", "gn_x_logit"],
    "score_diff": ["score_diff"],
    "match_point_diff (= -elimination_diff)": ["match_point_diff"],
    "decider_x_strength": ["decider_x_logit"],
    "previous_game_winner": ["prev_winner"],
    "ALL": ["gn_c", "gn_x_logit", "score_diff", "match_point_diff", "decider_x_logit", "prev_winner"],
}


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def ll(y, p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _closeness(params):
    c = abs(math.log(params.get("k", 24.0) / 24.0))
    h = params.get("half_life_days", math.inf)
    c += 0 if math.isinf(h) else 1 / h
    return c + abs(params.get("rho", 1.0) - 1.0)


def _pkey(params):
    return tuple(sorted((k, float(v)) for k, v in params.items()))


def run_all(timeline):
    return {(fam, _pkey(p)): E.run(timeline, p) for fam, grid in FAMILIES.items() for p in grid}


def series_frame(timeline):
    return pd.DataFrame([{"series_id": s["series_id"], "season": s["season"], "t": s["t"], "stage": s["stage"],
                          "format": s["format"], "format_source": s["format_source"], "team_a": s["a"],
                          "team_b": s["b"], "y": s["y"], "p_b5": s["p_b5"]} for s in timeline]).set_index("series_id", drop=False)


def fit_lr(x, y, c=1e4):
    return LogisticRegression(C=c, max_iter=5000).fit(np.asarray(x, float), np.asarray(y, int))


def state_covariates(g, fmt_map):
    n = g.series_id.map(fmt_map).map(WINS_NEEDED)
    lp = logit(g.p_pre)
    mpa, mpb = (g.wins_a_before == n - 1).astype(int), (g.wins_b_before == n - 1).astype(int)
    return pd.DataFrame({"logit_pre": lp, "gn_c": g.game_number - 3, "gn_x_logit": (g.game_number - 3) * lp,
                         "score_diff": g.wins_a_before - g.wins_b_before, "match_point_diff": mpa - mpb,
                         "decider_x_logit": (mpa & mpb) * lp, "prev_winner": g.prev_winner}, index=g.index)


def run_folds(timeline, runs):
    sf = series_frame(timeline)
    fmt_map = sf.format.to_dict()
    season_of = sf.season.to_dict()
    seasons = sf[sf.p_b5.notna()].groupby("season").t.min().sort_values().index.tolist()
    eval_seasons = seasons[1:]
    gpreds, spreds, sel, state_oot = [], [], [], []
    for v in eval_seasons:
        tr_seasons = [s for s in sf.groupby("season").t.min().sort_values().index if sf[sf.season == s].t.min() < sf[sf.season == v].t.min()]
        best = {}
        for fam, grid in FAMILIES.items():
            scored = []
            for p in grid:
                g = runs[(fam, _pkey(p))][0]
                tr = g[g.series_id.map(season_of).isin(tr_seasons)]
                scored.append((round(ll(tr.y, tr.p_pre), 10), round(_closeness(p), 10), _pkey(p), p, len(tr)))
            scored.sort(key=lambda x: x[:3])
            best[fam] = scored[0]
            sel.append({"validation_season": v, "model": fam, "selected": str(scored[0][3]),
                        "train_log_loss_pre": scored[0][0], "train_games": scored[0][4], "pkey": scored[0][2]})
        star = min(best, key=lambda f: best[f][0])
        sel.append({"validation_season": v, "model": "G*", "selected": star, "train_log_loss_pre": best[star][0],
                    "train_games": best[star][4], "pkey": best[star][2]})
        gs, ss = runs[(star, best[star][2])]
        gs = gs.assign(season=gs.series_id.map(season_of), format=gs.series_id.map(fmt_map))
        gs["p_b5"] = gs.series_id.map(sf.p_b5)
        gs["p_b5_game"] = np.nan
        for fmt in ("BO5", "BO7", "BO3"):
            m = (gs.format == fmt) & gs.p_b5.notna()
            if m.any():
                gs.loc[m, "p_b5_game"] = game_prob_from_series(gs.loc[m, "p_b5"], fmt)
        gtr, gva = gs[gs.season.isin(tr_seasons)], gs[gs.season == v]

        def emit(model, mode, p, cfg):
            gpreds.append(pd.DataFrame({"game_key": gva.game_key.values, "series_id": gva.series_id.values,
                                        "season": v, "game_number": gva.game_number.values, "format": gva.format.values,
                                        "model_id": model, "mode": mode, "p": np.asarray(p, float), "y": gva.y.values,
                                        "config": cfg, "train_rows": len(gtr)}))

        emit("G0", "PRE_SERIES", np.full(len(gva), 0.5), "fixed")
        emit("G0", "LIVE_SERIES", np.full(len(gva), 0.5), "fixed")
        for fam in FAMILIES:
            g = runs[(fam, best[fam][2])][0]
            g = g[g.series_id.map(season_of) == v].set_index("game_key").loc[gva.game_key]
            emit(fam, "PRE_SERIES", g.p_pre.values, str(best[fam][3]))
            emit(fam, "LIVE_SERIES", g.p_live.values, str(best[fam][3]))
        emit("G*", "PRE_SERIES", gva.p_pre.values, f"{star} {best[star][3]}")
        emit("G*", "LIVE_SERIES", gva.p_live.values, f"{star} {best[star][3]}")
        t5 = gtr[gtr.p_b5_game.notna()]
        for mode, col in (("PRE_SERIES", "p_pre"), ("LIVE_SERIES", "p_live")):
            m = fit_lr(np.column_stack([logit(t5[col]), logit(t5.p_b5_game)]), t5.y)
            p = m.predict_proba(np.column_stack([logit(gva[col]), logit(gva.p_b5_game)]))[:, 1]
            emit("G5", mode, p, f"{star}+B5game; coef={np.round(m.coef_[0], 3).tolist()}")

        # series models
        ss = ss.set_index("series_id").join(sf[["season", "format", "y", "p_b5"]])
        ss = ss[ss.p_b5.notna()]
        ss["S1"] = [float(series_prob(p, f)) for p, f in zip(ss.p_game_pre, ss.format)]
        str_, sva = ss[ss.season.isin(tr_seasons)], ss[ss.season == v]
        gn_d = lambda d: np.column_stack([logit(d.p_pre)] + [(np.minimum(d.game_number, 6) == k).astype(float) for k in range(2, 7)])  # noqa: E731
        m2 = fit_lr(gn_d(gtr), gtr.y)
        cov_tr = state_covariates(gtr, fmt_map)
        m3 = fit_lr(cov_tr[["logit_pre", "score_diff", "prev_winner"]], gtr.y)

        def s2(p0, fmt):
            b0, co = m2.intercept_[0], m2.coef_[0]
            f = lambda k, wa, wb, prev: 1 / (1 + math.exp(-(b0 + co[0] * logit(p0) + (co[min(k, 6) - 1] if k >= 2 else 0))))  # noqa: E731
            return series_prob_state(f, fmt)

        def s3(p0, fmt):
            b0, co = m3.intercept_[0], m3.coef_[0]
            f = lambda k, wa, wb, prev: 1 / (1 + math.exp(-(b0 + co[0] * logit(p0) + co[1] * (wa - wb) + co[2] * prev)))  # noqa: E731
            return series_prob_state(f, fmt)

        m4 = fit_lr(np.column_stack([logit(str_.p_b5), logit(str_.S1)]), str_.y)
        bo7 = lambda d: (d.format == "BO7").astype(float).to_numpy()  # noqa: E731
        xf = lambda d: np.column_stack([logit(d.S1), bo7(d), bo7(d) * logit(d.S1)])  # noqa: E731
        mf = fit_lr(xf(str_), str_.y)
        out = {"S0": sva.p_b5.values, "S1": sva.S1.values,
               "S2": [s2(p, f) for p, f in zip(sva.p_game_pre, sva.format)],
               "S3": [s3(p, f) for p, f in zip(sva.p_game_pre, sva.format)],
               "S4": m4.predict_proba(np.column_stack([logit(sva.p_b5), logit(sva.S1)]))[:, 1],
               "S1F": mf.predict_proba(xf(sva))[:, 1]}
        for mid, p in out.items():
            spreds.append(pd.DataFrame({"series_id": sva.index, "season": v, "format": sva.format.values,
                                        "model_id": mid, "p": np.asarray(p, float), "y": sva.y.values,
                                        "p_game_pre": sva.p_game_pre.values, "game_model": star,
                                        "train_series": len(str_), "train_games": len(gtr)}))
        # out-of-time series-state tests (PRE-SERIES strength as control)
        cov_va = state_covariates(gva, fmt_map)
        base = fit_lr(cov_tr[["logit_pre"]], gtr.y).predict_proba(cov_va[["logit_pre"]])[:, 1]
        for name, cols in STATE_SETS.items():
            p = fit_lr(cov_tr[["logit_pre"] + cols], gtr.y).predict_proba(cov_va[["logit_pre"] + cols])[:, 1]
            state_oot.append(pd.DataFrame({"game_key": gva.game_key.values, "series_id": gva.series_id.values,
                                           "season": v, "variable_set": name, "p": p, "p_base": base, "y": gva.y.values}))
    return (pd.concat(gpreds, ignore_index=True), pd.concat(spreds, ignore_index=True), pd.DataFrame(sel),
            pd.concat(state_oot, ignore_index=True))


def cluster_logit(x, y, cluster):
    """Logistic MLE with series-clustered sandwich standard errors."""
    x = np.column_stack([np.ones(len(y)), np.asarray(x, float)])
    y = np.asarray(y, float)
    beta = np.zeros(x.shape[1])
    for _ in range(100):
        mu = 1 / (1 + np.exp(-x @ beta))
        h = x.T @ (x * (mu * (1 - mu))[:, None])
        step = np.linalg.solve(h, x.T @ (y - mu))
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    mu = 1 / (1 + np.exp(-x @ beta))
    score = x * (y - mu)[:, None]
    meat = sum(np.outer(s, s) for s in pd.DataFrame(score).groupby(np.asarray(cluster)).sum().to_numpy())
    hinv = np.linalg.inv(h)
    se = np.sqrt(np.diag(hinv @ meat @ hinv))
    return beta, se


def state_association(gpreds_pre, games_rows, fmt_map):
    """In-sample association on out-of-time PRE-SERIES predictions of the evaluation games."""
    g = games_rows.set_index("game_key").loc[gpreds_pre.game_key].reset_index()
    g["p_pre"] = gpreds_pre.p.values
    cov = state_covariates(g, fmt_map)
    rows = []
    for name, cols in STATE_SETS.items():
        b, se = cluster_logit(cov[["logit_pre"] + cols], g.y, g.series_id)
        for i, c in enumerate(["intercept", "logit_pre"] + cols):
            z = b[i] / se[i]
            rows.append({"variable_set": name, "term": c, "coef": b[i], "cluster_se": se[i], "z": z,
                         "p_value_normal": float(math.erfc(abs(z) / math.sqrt(2))), "n_games": len(g),
                         "n_series_clusters": g.series_id.nunique(), "analysis": "in-sample association (descriptive)"})
    return pd.DataFrame(rows)


def cluster_bootstrap(df, ref, models, key, cluster="series_id", strata="season", b=2000, seed=20260929):
    """Paired bootstrap resampling whole clusters within strata. df is long: key, cluster, strata, model_id, p, y."""
    wide = df.pivot_table(index=list(dict.fromkeys([key, cluster, strata])), columns="model_id", values="p").reset_index()
    y = df.drop_duplicates(key).set_index(key).y
    wide["y"] = wide[key].map(y).astype(float)
    cl = wide.groupby(cluster)
    cl_ids = list(cl.groups)
    cl_strata = cl[strata].first().loc[cl_ids].to_numpy()
    yv = wide.y.to_numpy()

    def loss(p):
        p = np.clip(p, EPS, 1 - EPS)
        return -(yv * np.log(p) + (1 - yv) * np.log(1 - p)), (p - yv) ** 2

    ref_ll, ref_br = loss(wide[ref].to_numpy())
    code = pd.Series(range(len(cl_ids)), index=cl_ids)
    wc = code.loc[wide[cluster]].to_numpy()
    rng = np.random.default_rng(seed)
    per_stratum = [np.flatnonzero(cl_strata == s) for s in np.unique(cl_strata)]
    draws = [np.concatenate([rng.choice(ix, len(ix), replace=True) for ix in per_stratum]) for _ in range(b)]
    rows = []
    for m in models:
        if m == ref:
            continue
        mll, mbr = loss(wide[m].to_numpy())
        dll = np.bincount(wc, weights=mll - ref_ll, minlength=len(cl_ids))
        dbr = np.bincount(wc, weights=mbr - ref_br, minlength=len(cl_ids))
        cnt = np.bincount(wc, minlength=len(cl_ids)).astype(float)
        bl = np.array([dll[d].sum() / cnt[d].sum() for d in draws])
        bb = np.array([dbr[d].sum() / cnt[d].sum() for d in draws])
        rows.append({"model_id": m, "reference": ref, "n_rows": len(wide), "n_clusters": len(cl_ids),
                     "bootstrap_samples": b, "mean_delta_log_loss": float((mll - ref_ll).mean()),
                     "delta_log_loss_ci_low": float(np.quantile(bl, 0.025)),
                     "delta_log_loss_ci_high": float(np.quantile(bl, 0.975)),
                     "frac_beats_ref_log_loss": float((bl < 0).mean()),
                     "mean_delta_brier": float((mbr - ref_br).mean()),
                     "delta_brier_ci_low": float(np.quantile(bb, 0.025)),
                     "delta_brier_ci_high": float(np.quantile(bb, 0.975)),
                     "cluster": cluster, "strata": strata})
    return pd.DataFrame(rows)


def metrics(df, keys):
    rows = []
    for k, g in df.groupby(keys, sort=False):
        k = k if isinstance(k, tuple) else (k,)
        rows.append({**dict(zip(keys, k)), **evaluate(g.y, g.p)})
    return pd.DataFrame(rows)


def format_table(spreds, gpreds_pre):
    rows = []
    for fmt, g in spreds.groupby("format"):
        s0 = g[g.model_id == "S0"]
        gg = gpreds_pre[gpreds_pre.format == fmt]
        fav_g = np.where(gg.p >= 0.5, gg.p, 1 - gg.p)
        won_g = np.where(gg.p >= 0.5, gg.y, 1 - gg.y)
        row = {"format": fmt, "n_series": len(s0), "n_games": len(gg),
               "game_favorite_mean_predicted": fav_g.mean(), "game_favorite_observed_win_rate": won_g.mean()}
        for mid in ("S0", "S1", "S4", "S1F"):
            d = g[g.model_id == mid]
            fav = np.where(d.p >= 0.5, d.p, 1 - d.p)
            won = np.where(d.p >= 0.5, d.y, 1 - d.y)
            e = evaluate(d.y, d.p)
            row.update({f"{mid}_series_favorite_mean_predicted": fav.mean(),
                        f"{mid}_series_favorite_observed_win_rate": won.mean(),
                        f"{mid}_log_loss": e["log_loss"], f"{mid}_brier": e["brier"], f"{mid}_ece": e["ece"],
                        f"{mid}_calibration_slope": e["calibration_slope"],
                        f"{mid}_calibration_intercept": e["calibration_intercept"]})
        rows.append(row)
    return pd.DataFrame(rows)


def format_interaction(spreds):
    d = spreds[spreds.model_id == "S1"]
    bo7 = (d.format == "BO7").astype(float)
    b, se = cluster_logit(np.column_stack([logit(d.p), bo7, bo7 * logit(d.p)]), d.y, d.series_id)
    terms = ["intercept", "logit_S1", "BO7", "BO7_x_logit_S1"]
    return pd.DataFrame({"term": terms, "coef": b, "se": se, "z": b / se,
                         "p_value_normal": [float(math.erfc(abs(x) / math.sqrt(2))) for x in b / se],
                         "note": "in-sample on out-of-time S1 predictions; slope 1 / intercept 0 = S1 correct"})
