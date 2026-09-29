"""Probability metrics and raw-model calibration diagnostics (no post-hoc recalibration).

- Log loss clips probabilities to [EPS, 1 - EPS], EPS = 1e-6, for numerical
  stability only.
- Accuracy counts p >= 0.5 as a team_a prediction (so B0 accuracy equals the
  observed team_a win rate). It is a secondary metric.
- ECE: 10 equal-width bins on [0, 1], weighted mean |mean(p) - mean(y)|.
- Calibration slope b: logistic regression y ~ a + b * logit(p).
  Calibration intercept a: y ~ a + offset(logit(p)) (calibration-in-the-large).
  Perfect calibration: slope 1, intercept 0. Slope < 1 means over-confident
  (too extreme); slope > 1 means under-confident (too compressed).
Undefined values are returned as NaN with a reason in `notes`.
"""
import math

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

EPS = 1e-6
N_BINS = 10
METRIC_KEYS = ["n", "log_loss", "brier", "accuracy", "roc_auc", "ece", "calibration_intercept",
               "calibration_slope", "mean_predicted_p", "observed_win_rate", "notes"]


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def _logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _newton_logistic(X, y, offset, iters=100, tol=1e-10):
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        mu = _sigmoid(X @ beta + offset)
        w = mu * (1 - mu)
        h = X.T @ (X * w[:, None])
        try:
            step = np.linalg.solve(h, X.T @ (y - mu))
        except np.linalg.LinAlgError:
            return None
        beta = beta + step
        if not np.all(np.isfinite(beta)):
            return None
        if np.max(np.abs(step)) < tol:
            return beta
    return None


def calibration_intercept_slope(y, p):
    """Returns (intercept, slope, notes)."""
    y = np.asarray(y, float); x = _logit(np.asarray(p, float)); notes = []
    if len(y) == 0:
        return math.nan, math.nan, ["no predictions"]
    if y.min() == y.max():
        return math.nan, math.nan, ["only one outcome class; calibration regression undefined"]
    a = _newton_logistic(np.ones((len(y), 1)), y, x)
    intercept = float(a[0]) if a is not None else math.nan
    if a is None:
        notes.append("calibration intercept did not converge")
    if np.var(x) < 1e-12:
        slope = math.nan
        notes.append("calibration slope undefined: predicted probabilities are constant")
    else:
        b = _newton_logistic(np.column_stack([np.ones(len(y)), x]), y, np.zeros(len(y)))
        slope = float(b[1]) if b is not None else math.nan
        if b is None:
            notes.append("calibration slope did not converge (possible separation)")
    return intercept, slope, notes


def reliability_bins(y, p, n_bins=N_BINS):
    y = np.asarray(y, float); p = np.asarray(p, float)
    idx = np.minimum((p * n_bins).astype(int), n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = idx == b
        rows.append({"bin": b, "bin_lower": b / n_bins, "bin_upper": (b + 1) / n_bins, "n": int(m.sum()),
                     "mean_predicted_p": float(p[m].mean()) if m.any() else math.nan,
                     "observed_win_rate": float(y[m].mean()) if m.any() else math.nan})
    return pd.DataFrame(rows)


def ece(y, p, n_bins=N_BINS):
    b = reliability_bins(y, p, n_bins)
    b = b[b.n > 0]
    if b.empty:
        return math.nan
    return float((b.n * (b.mean_predicted_p - b.observed_win_rate).abs()).sum() / b.n.sum())


def evaluate(y, p):
    y = np.asarray(y, float); p = np.asarray(p, float)
    n = len(y)
    if n == 0:
        return {**{k: math.nan for k in METRIC_KEYS}, "n": 0, "notes": "no predictions"}
    notes = []
    pc = np.clip(p, EPS, 1 - EPS)
    ll = float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))
    if y.min() == y.max():
        auc = math.nan
        notes.append("ROC AUC undefined: one outcome class")
    else:
        auc = float(roc_auc_score(y, p))
        if np.ptp(p) == 0:
            notes.append("ROC AUC = 0.5 by construction: constant predictions")
    ci, cs, cn = calibration_intercept_slope(y, p)
    notes += cn
    return {"n": n, "log_loss": ll, "brier": float(np.mean((p - y) ** 2)),
            "accuracy": float(np.mean((p >= 0.5) == (y == 1))), "roc_auc": auc, "ece": ece(y, p),
            "calibration_intercept": ci, "calibration_slope": cs, "mean_predicted_p": float(p.mean()),
            "observed_win_rate": float(y.mean()), "notes": "; ".join(notes)}
