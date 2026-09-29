"""Draft ladder D0-D6 (+ D0R control, D1R recency variant) and the sequential-draft experiment."""
import math

import numpy as np
import pandas as pd

from openkpl.game_draft_model import draft as D
from openkpl.game_draft_model.series_math import game_prob_from_series
from openkpl.player_model import models as M

CANDIDATES = ["B5_game", "Gstar_pre", "Gstar_live"]


def candidates(gt, runs, star, pkey):
    g = runs[(star, pkey)][0].set_index("game_key")
    out = pd.DataFrame(index=gt.index)
    out["Gstar_pre"] = g.p_pre.reindex(gt.index)
    out["Gstar_live"] = g.p_live.reindex(gt.index)
    out["B5_game"] = np.nan
    for fmt in ("BO5", "BO7", "BO3"):
        m = (gt.format == fmt) & gt.p_b5.notna()
        if m.any():
            out.loc[m, "B5_game"] = game_prob_from_series(gt.loc[m, "p_b5"].astype(float), fmt)
    return out


def _inner(tr):
    ss = tr.groupby("season").date.min().sort_values().index.tolist()
    return None if len(ss) < 2 else (tr[tr.season != ss[-1]], tr[tr.season == ss[-1]])


def _select(tr, cands, score):
    sp = _inner(tr)
    if sp is None:
        return cands[0], math.nan, "no inner season (single training season): a-priori default"
    scores = [(round(score(sp[0], sp[1], c), 10), i) for i, c in enumerate(cands)]
    s, i = min(scores)
    return cands[i], s, f"inner: fit {sp[0].season.nunique()} season(s), validate {sp[1].season.iloc[0]}"


def _n_params(model):
    last = model.steps[-1][1]
    if hasattr(last, "coef_"):
        return int(last.coef_.size + 1)
    return int(sum(p.get_n_leaf_nodes() for it in last._predictors for p in it))


def run(gt, hf, sf, cf, events, runs, a_sel, eval_seasons=("KPL2023S1", "KPL2023S2", "KPL2024S1")):
    prim = gt[gt.kplow_winner_known].copy()
    prim["y"] = prim.y.astype(int)
    static_cache = {}

    def static(k, mn):
        if (k, mn) not in static_cache:
            static_cache[(k, mn)] = D.static_features(gt, hf, sf, cf, k, mn)
        return static_cache[(k, mn)]

    ev = {g: sorted(x.to_dict("records"), key=lambda e: e["sequence"]) for g, x in events.groupby("game_key")}
    standard = {g for g, x in events.groupby("game_key") if len(x) == 18 and x.phase_if_derivable.notna().all()}
    preds, seq, sel, cx, feats = [], [], [], [], []
    seasons = prim.groupby("season").date.min().sort_values().index.tolist()
    for v in eval_seasons:
        star = a_sel[(a_sel.validation_season == v) & (a_sel.model == "G*")].iloc[0]
        cand = candidates(gt, runs, star.selected, star.pkey)
        tr_ids = prim.index[prim.season.isin(seasons[:seasons.index(v)])]
        va_ids = prim.index[prim.season == v]
        base = prim.join(cand)
        tr_ll = {c: M.log_loss(base.loc[tr_ids, "y"], base.loc[tr_ids, c]) for c in CANDIDATES
                 if base.loc[tr_ids, c].notna().all()}
        d0 = min(tr_ll, key=tr_ll.get)
        sel.append({"validation_season": v, "stage": "D0 baseline", "selected": d0,
                    "detail": "; ".join(f"{c} train_ll={x:.5f}" for c, x in tr_ll.items()),
                    "train_rows": len(tr_ids), "validation_rows": len(va_ids)})
        base["p_d0"] = base[d0]
        base["logit_d0"] = M.logit(base.p_d0)

        def frame(k, mn):
            return base.join(static(k, mn))

        grid = [D.DEFAULT_SHRINK] + [(k, mn) for k in D.K_GRID for mn in D.MIN_N_GRID if (k, mn) != D.DEFAULT_SHRINK]
        c4 = D.cols(D.LADDER["D4"])
        (k, mn), s_ll, note = _select(base.loc[tr_ids], grid, lambda a, b, c: M.log_loss(
            b.y, M.fit_predict(lambda: M.logistic(M.RUNG_C), frame(*c).loc[a.index], frame(*c).loc[b.index], c4)[1]))
        sel.append({"validation_season": v, "stage": "shrinkage (K, min_n)", "selected": f"K={k:g}, min_n={mn}",
                    "detail": f"{note}; inner_ll={s_ll}", "train_rows": len(tr_ids), "validation_rows": len(va_ids)})
        F = frame(k, mn)
        rec = {h: D.recency_hero_strength(gt, hf, k, mn, h) for h in D.RECENCY_GRID}
        c1r = [c if c != "hero_strength_diff" else "hero_strength_rec_diff" for c in D.cols(D.LADDER["D1"])]
        h, h_ll, hnote = _select(base.loc[tr_ids], D.RECENCY_GRID, lambda a, b, hh: M.log_loss(
            b.y, M.fit_predict(lambda: M.logistic(M.RUNG_C), F.assign(hero_strength_rec_diff=rec[hh]).loc[a.index],
                               F.assign(hero_strength_rec_diff=rec[hh]).loc[b.index], c1r)[1]))
        sel.append({"validation_season": v, "stage": "D1R recency half-life (days)", "selected": str(h),
                    "detail": f"{hnote}; inner_ll={h_ll}", "train_rows": len(tr_ids), "validation_rows": len(va_ids)})
        F = F.assign(hero_strength_rec_diff=rec[h])
        tr, va = F.loc[tr_ids], F.loc[va_ids]
        feats.append(va.assign(fold=v, d0_source=d0, shrink_K=k, shrink_min_n=mn, recency_half_life=h))
        if v == eval_seasons[0]:
            feats.append(tr.assign(fold=f"training rows of {v}", d0_source=d0, shrink_K=k, shrink_min_n=mn,
                                   recency_half_life=h))

        def emit(mid, p, model=None, ncols=0, hp=""):
            preds.append(pd.DataFrame({"game_key": va.game_key.values, "series_id": va.series_id.values, "season": v,
                                       "game_number": va.game_number.values, "format": va.format.values,
                                       "team_a": va.team_a.values, "team_b": va.team_b.values, "model_id": mid,
                                       "p": np.asarray(p, float), "y": va.y.values}))
            cx.append({"validation_season": v, "model_id": mid, "n_features": ncols,
                       "n_fitted_parameters": _n_params(model) if model is not None else 0,
                       "train_rows": len(tr), "validation_rows": len(va), "hyperparameters": hp})

        emit("D0", va.p_d0, hp=f"raw {d0} probability (no fitting)")
        m, p = M.fit_predict(lambda: M.logistic(M.RUNG_C), tr, va, ["logit_d0"])
        emit("D0R", p, m, 1, "control: logistic recalibration of D0")
        for mid, groups in D.LADDER.items():
            c = D.cols(groups)
            m, p = M.fit_predict(lambda: M.logistic(M.RUNG_C), tr, va, c)
            emit(mid, p, m, len(c), f"C={M.RUNG_C}; K={k:g}, min_n={mn}")
        m, p = M.fit_predict(lambda: M.logistic(M.RUNG_C), tr, va, c1r)
        emit("D1R", p, m, len(c1r), f"C={M.RUNG_C}; recency half-life={h}")
        call = D.cols(D.ALL_STATIC)
        cc, c_ll, cnote = _select(tr, [1.0] + [x for x in D.D5_C_GRID if x != 1.0], lambda a, b, C: M.log_loss(
            b.y, M.fit_predict(lambda: M.logistic(C), a, b, call)[1]))
        m, p = M.fit_predict(lambda: M.logistic(cc), tr, va, call)
        emit("D5", p, m, len(call), f"C={cc} ({cnote})")
        g0 = {"max_iter": 100, "max_depth": 3}
        gp, g_ll, gnote = _select(tr, [g0] + [x for x in D.D6_GRID if x != g0], lambda a, b, G: M.log_loss(
            b.y, M.fit_predict(lambda: M.hgb(G), a, b, call)[1]))
        m, p = M.fit_predict(lambda: M.hgb(gp), tr, va, call)
        emit("D6", p, m, len(call), f"{gp} ({gnote})")

        lk = D.StepLookup(hf, sf, cf, k, mn)
        std_tr = [g for g in tr.index if g in standard]
        std_va = [g for g in va.index if g in standard]
        rows = {}
        for g in std_tr + std_va:
            r = F.loc[g]
            rows[g] = [D.step_features(g, ev[g], j, r.team_a, r.team_b, lk) for j in range(19)]
        sc = ["logit_d0"] + [f"{n}_diff" for n in D.STEP_FEATS]
        for j in range(19):
            def mk(ids):
                x = pd.DataFrame([rows[g][j] for g in ids], index=ids)
                return x.assign(logit_d0=F.loc[ids, "logit_d0"].values, y=F.loc[ids, "y"].values)
            xtr, xva = mk(std_tr), mk(std_va)
            _, p = M.fit_predict(lambda: M.logistic(M.RUNG_C), xtr, xva, sc)
            seq.append(pd.DataFrame({"game_key": std_va, "series_id": F.loc[std_va, "series_id"].values, "season": v,
                                     "step": j, "checkpoint": D.CHECKPOINTS.get(j, ""), "p": p,
                                     "y": xva.y.values, "p_d0": F.loc[std_va, "p_d0"].values,
                                     "train_rows": len(xtr)}))
        sel.append({"validation_season": v, "stage": "sequential universe", "selected": "standard 18-event drafts",
                    "detail": f"excluded non-standard: train {len(tr) - len(std_tr)}, validation {len(va) - len(std_va)}",
                    "train_rows": len(std_tr), "validation_rows": len(std_va)})
    return (pd.concat(preds, ignore_index=True), pd.concat(seq, ignore_index=True), pd.DataFrame(sel),
            pd.DataFrame(cx), pd.concat(feats))


def information_gain(preds, gt, events, post="D5"):
    w = preds.pivot_table(index=["game_key", "series_id", "season", "game_number", "format", "team_a", "team_b", "y"],
                          columns="model_id", values="p").reset_index()
    fp = {g: D.first_pick_team(sorted(x.to_dict("records"), key=lambda e: e["sequence"])) for g, x in events.groupby("game_key")}
    lossf = lambda p, y: -(y * np.log(np.clip(p, 1e-6, 1 - 1e-6)) + (1 - y) * np.log(np.clip(1 - p, 1e-6, 1 - 1e-6)))  # noqa: E731
    for ref in ("D0", "D0R"):
        w[f"DIG_vs_{ref}"] = lossf(w[ref], w.y) - lossf(w[post], w.y)
        w[f"delta_brier_vs_{ref}"] = (w[post] - w.y) ** 2 - (w[ref] - w.y) ** 2
    w["first_pick_side"] = [("team_a" if fp.get(g) == a else "team_b" if fp.get(g) == b else "unknown")
                            for g, a, b in zip(w.game_key, w.team_a, w.team_b)]
    rows = []
    for by in ("season", "first_pick_side", "game_number", "format"):
        for k, g in w.groupby(by):
            rows.append({"group_by": by, "group": str(k), "n_games": len(g), "mean_DIG_vs_D0": g.DIG_vs_D0.mean(),
                         "mean_DIG_vs_D0R": g.DIG_vs_D0R.mean(), "mean_delta_brier_vs_D0": g.delta_brier_vs_D0.mean(),
                         "mean_delta_brier_vs_D0R": g.delta_brier_vs_D0R.mean(), "post_draft_model": post})
    rows.append({"group_by": "ALL", "group": "ALL", "n_games": len(w), "mean_DIG_vs_D0": w.DIG_vs_D0.mean(),
                 "mean_DIG_vs_D0R": w.DIG_vs_D0R.mean(), "mean_delta_brier_vs_D0": w.delta_brier_vs_D0.mean(),
                 "mean_delta_brier_vs_D0R": w.delta_brier_vs_D0R.mean(), "post_draft_model": post})
    team = []
    for side, opp in (("team_a", "team_b"), ("team_b", "team_a")):
        s = 1 if side == "team_a" else -1
        yt = w.y if side == "team_a" else 1 - w.y
        pd0 = w.D0 if side == "team_a" else 1 - w.D0
        ppost = w[post] if side == "team_a" else 1 - w[post]
        team.append(pd.DataFrame({"team_id": w[side], "game_key": w.game_key, "season": w.season, "y_team": yt,
                                  "p_pre_draft": pd0, "p_post_draft": ppost, "DIG": w.DIG_vs_D0}))
    t = pd.concat(team)
    by_team = t.groupby("team_id").agg(n_games=("game_key", "size"), mean_DIG=("DIG", "mean"),
                                       result_minus_pre_draft=("y_team", "mean"), mean_pre=("p_pre_draft", "mean"),
                                       mean_post=("p_post_draft", "mean")).reset_index()
    by_team["result_minus_pre_draft"] = by_team.result_minus_pre_draft - by_team.mean_pre
    by_team["draft_implied_shift"] = by_team.mean_post - by_team.mean_pre
    by_team["label"] = "EXPLORATORY team-level draft residual; NOT coach quality / coach draft value"
    return w, pd.DataFrame(rows), by_team
