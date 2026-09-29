"""v0.6.1 pre-registered BO7 calibration audit (see reports/bo7_audit/PROMOTION_RULE.md).

Primary:   p' = sigmoid(beta * logit(p_B5)), penalty (lam/2)(beta-1)^2, fitted on one format only.
Secondary: p' = sigmoid(alpha + beta * logit(p_B5)), penalty (lam/2)(alpha^2 + (beta-1)^2).
"""
import numpy as np
import pandas as pd

from openkpl.evaluation.calibration import evaluate
from openkpl.game_draft_model import experiment_a as A
from openkpl.game_draft_model import games as GM
from openkpl.player_model import data

EPS = 1e-6
LAMBDAS = {"C1": 0.0, "C2": 2.0, "C3": 10.0, "C4": 50.0}
CANDIDATES = ["C0", "C1", "C2", "C3", "C4"]
STRENGTH_ORDER = ["C0", "C4", "C3", "C2", "C1"]
FIRST_FOLD_DEFAULT = "C4"
BETA_BOUND = 20.0
HIGH_INSTABILITY_DELTA = 0.30
BINS = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.0 + 1e-9)]


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, float)))


def load_series(root="."):
    canonical, games, _ = data.load(root)
    tl = GM.build(canonical, games, pd.read_parquet(f"{root}/{data.BENCH_PRED}"))
    d = pd.DataFrame([{k: s[k] for k in ("series_id", "t", "season", "stage", "format", "format_source", "y", "p_b5")}
                      for s in tl])
    d = d[d.p_b5.notna()].rename(columns={"p_b5": "p"}).sort_values(["t", "series_id"]).reset_index(drop=True)
    d["z"] = logit(d.p)
    return d


def season_order(df):
    return df.groupby("season").t.min().sort_values().index.tolist()


def fit(z, y, lam, intercept=False, iters=100):
    """Penalized Newton-Raphson centred at (alpha, beta) = (0, 1). Returns (alpha, beta)."""
    z, y = np.asarray(z, float), np.asarray(y, float)
    X = np.column_stack([np.ones_like(z), z]) if intercept else z[:, None]
    center = np.array([0.0, 1.0]) if intercept else np.array([1.0])
    th = center.copy()
    for _ in range(iters):
        p = sigmoid(X @ th)
        g = X.T @ (p - y) + lam * (th - center)
        H = X.T @ (X * (p * (1 - p))[:, None]) + lam * np.eye(len(th)) + 1e-9 * np.eye(len(th))
        step = np.linalg.solve(H, g)
        th = np.clip(th - step, -BETA_BOUND, BETA_BOUND)
        if np.max(np.abs(step)) < 1e-10:
            break
    return (float(th[0]), float(th[1])) if intercept else (0.0, float(th[0]))


def apply(z, ab):
    return sigmoid(ab[0] + ab[1] * np.asarray(z, float))


def temporal(df, intercept=False):
    """Expanding-window OOT predictions on the given (single-format) frame.
    Fold v is fitted only on seasons strictly before v; CSEL picks lambda from earlier folds' OOT losses only."""
    order = season_order(df)
    tag = "_A" if intercept else ""
    preds, stab, oot_loss = [], [], {c: [] for c in CANDIDATES}
    for i, v in enumerate(order[1:], start=1):
        train = df[df.season.isin(order[:i])]
        val = df[df.season == v]
        fits = {"C0": (0.0, 1.0)}
        for c, lam in LAMBDAS.items():
            fits[c] = fit(train.z, train.y, lam, intercept)
        prior = {c: sum(oot_loss[c]) for c in CANDIDATES}
        if not oot_loss["C0"]:
            sel = FIRST_FOLD_DEFAULT
        else:
            best = min(prior.values())
            sel = next(c for c in STRENGTH_ORDER if prior[c] <= best + 1e-12)
        fits["CSEL"] = fits[sel]
        for c, ab in fits.items():
            p = apply(val.z, ab)
            preds.append(pd.DataFrame({"series_id": val.series_id.values, "season": v, "model_id": c + tag,
                                       "p": p, "y": val.y.values, "p_b5": val.p.values}))
            if c in oot_loss:
                oot_loss[c].append(A.ll(val.y.values, p) * len(val))
        pv = apply(val.z, fits["CSEL"])
        stab.append({"validation_season": v, "training_end": order[i - 1], "n_train": len(train), "n_validation": len(val),
                     "alpha_raw": fits["C1"][0], "beta_raw": fits["C1"][1],
                     **{f"beta_{c}": fits[c][1] for c in ("C2", "C3", "C4")},
                     **({f"alpha_{c}": fits[c][0] for c in ("C2", "C3", "C4")} if intercept else {}),
                     "selected": sel, "beta_shrunk": fits[sel][1], "alpha_shrunk": fits[sel][0],
                     "validation_logloss": A.ll(val.y.values, pv),
                     "validation_logloss_b5": A.ll(val.y.values, val.p.values),
                     "delta_vs_b5": A.ll(val.y.values, pv) - A.ll(val.y.values, val.p.values),
                     "model_family": "SECONDARY_intercept" if intercept else "PRIMARY_zero_intercept"})
    return pd.concat(preds, ignore_index=True), pd.DataFrame(stab)


def run_format(series, fmt):
    """The only entry point for fitting: rows of other formats never reach the fit."""
    df = series[series.format == fmt].reset_index(drop=True)
    p0, s0 = temporal(df, intercept=False)
    p1, s1 = temporal(df, intercept=True)
    b5 = p0[p0.model_id == "C0"].assign(model_id="B5", p=lambda x: x.p_b5)
    return pd.concat([b5, p0, p1[~p1.model_id.isin(["C0_A"])]], ignore_index=True), pd.concat([s0, s1], ignore_index=True)


def assert_identical_series(preds, ref="B5"):
    base = set(preds[preds.model_id == ref].series_id)
    for m, g in preds.groupby("model_id"):
        if set(g.series_id) != base or g.series_id.duplicated().any():
            raise ValueError(f"{m} is not evaluated on the identical series set as {ref}")


def bootstrap(preds, models, ref="B5", b=2000):
    assert_identical_series(preds, ref)
    return A.cluster_bootstrap(preds, ref, models, "series_id", cluster="series_id", strata="season", b=b)


def metrics(preds):
    rows = []
    for m, g in preds.groupby("model_id", sort=False):
        rows.append({"model_id": m, **evaluate(g.y, g.p)})
    return pd.DataFrame(rows)


def by_season(preds):
    return A.metrics(preds, ["model_id", "season"])


def drop_one_season(preds, model="CSEL", ref="B5"):
    w = preds.pivot_table(index=["series_id", "season"], columns="model_id", values="p").reset_index()
    y = preds.drop_duplicates("series_id").set_index("series_id").y
    w["y"] = w.series_id.map(y)
    lm = lambda p: -(w.y * np.log(np.clip(p, EPS, 1 - EPS)) + (1 - w.y) * np.log(np.clip(1 - p, EPS, 1)))  # noqa: E731
    w["d"] = lm(w[model]) - lm(w[ref])
    return pd.DataFrame([{"dropped_validation_season": s, "n_remaining": int((w.season != s).sum()),
                          "delta_log_loss": float(w.loc[w.season != s, "d"].mean())} for s in sorted(w.season.unique())])


def leave_one_season_out(df):
    rows = []
    full = {c: fit(df.z, df.y, lam)[1] for c, lam in LAMBDAS.items()}
    for s in [None] + season_order(df):
        d = df if s is None else df[df.season != s]
        b = {c: fit(d.z, d.y, lam)[1] for c, lam in LAMBDAS.items()}
        rows.append({"removed_season": s or "NONE (all seasons)", "n_series": len(d),
                     **{f"beta_{c}": b[c] for c in LAMBDAS},
                     "change_vs_all_C1": b["C1"] - full["C1"],
                     "HIGH_INSTABILITY": bool(s is not None and (abs(b["C1"] - full["C1"]) > HIGH_INSTABILITY_DELTA
                                                                or np.sign(b["C1"] - 1) != np.sign(full["C1"] - 1)))})
    return pd.DataFrame(rows)


def favorite_bins(df):
    fav = np.maximum(df.p, 1 - df.p)
    won = np.where(df.p >= 0.5, df.y, 1 - df.y)
    rows = []
    for lo, hi in BINS:
        m = (fav >= lo) & (fav < hi)
        rows.append({"bin": f"{lo:.2f}-{min(hi, 1):.2f}" if hi < 1 else f"{lo:.2f}+", "n": int(m.sum()),
                     "mean_predicted_favorite_p": float(fav[m].mean()) if m.any() else np.nan,
                     "observed_favorite_win_rate": float(won[m].mean()) if m.any() else np.nan})
    return pd.DataFrame(rows)


def promotion(preds, boot, stab, loso, drop, ref="B5", model="CSEL", family="PRIMARY_zero_intercept"):
    m = metrics(preds).set_index("model_id")
    bt = boot.set_index("model_id").loc[model]
    s = stab[stab.model_family == family]
    signs = np.sign(s.beta_raw - 1)
    c = {
        "1_oot_logloss_improves": bool(bt.mean_delta_log_loss < 0),
        "2_brier_not_materially_worse": bool(bt.mean_delta_brier <= 0.0010),
        "3_ci_predominantly_below_zero": bool(bt.frac_beats_ref_log_loss >= 0.95),
        "4_beta_direction_stable": bool(signs.nunique() == 1 and signs.iloc[0] != 0),
        "5a_not_single_season_driven": bool((drop.delta_log_loss < 0).all()),
        "5b_no_high_instability": bool(not loso.HIGH_INSTABILITY.any()),
        "6_calibration_not_worse": bool(m.loc[model, "ece"] <= m.loc[ref, "ece"] + 0.02 and
                                        abs(m.loc[model, "calibration_slope"] - 1)
                                        <= abs(m.loc[ref, "calibration_slope"] - 1) + 0.10),
    }
    return c, ("PROMOTE_BO7_CORRECTION" if all(c.values()) else "REJECT_BO7_CORRECTION")
