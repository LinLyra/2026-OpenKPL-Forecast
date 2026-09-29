"""Model ladder B5-B12 and oracle ablations O1-O3 on top of the frozen v0.3.1 B5 predictions.

Every candidate is fit per outer fold on development seasons strictly before the
validation season. Inner selections use the last training season as the inner
validation set (model fit on the earlier training seasons only). Imputation and
scaling are part of the fitted pipeline, so their statistics come from training rows.
"""
import math

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from openkpl.evaluation.calibration import EPS
from openkpl.player_model import features as F

TEAM = ["logit_b5"]
GROUPS = {
    "PLAYER": F.RATING_FEATURES,
    "ROSTER": F.ROSTER_FEATURES,
    "BENCH": F.BENCH_RATING_FEATURES + F.BENCH_HIST_FEATURES,
    "HERO": F.HERO_FEATURES,
}
SAFE_DIFF = {g: [f"{c}_diff" for c in cols if c != "top5_player_rating_sum"] for g, cols in GROUPS.items()}
LADDER = {
    "B5R": [],
    "B6": ["ROSTER"],
    "B7": ["PLAYER"],
    "B8": ["PLAYER", "ROSTER"],
    "B9": ["PLAYER", "ROSTER", "BENCH"],
    "B10": ["PLAYER", "ROSTER", "BENCH", "HERO"],
}
ALL_SAFE = ["PLAYER", "ROSTER", "BENCH", "HERO"]
EXPLORATORY_X1 = ["expected_core_strength_diff"]
EXPLORATORY_X2 = ["logit_b5", "expected_core_strength_diff"]
RUNG_C = 1.0
B11_C_GRID = [0.01, 0.03, 0.1, 0.3, 1.0, 3.0]
B11_DEFAULT_C = 1.0
B12_GRID = [{"max_iter": it, "max_depth": d} for it in (50, 100, 200) for d in (2, 3)]
B12_DEFAULT = {"max_iter": 100, "max_depth": 3}
B12_FIXED = {"learning_rate": 0.05, "min_samples_leaf": 20, "l2_regularization": 1.0, "random_state": 0}
ORACLE_C = 0.3
CLIP_Q = 0.005
ORACLE = {"O1": "identities", "O2": F.ORACLE_RATING, "O3": F.ORACLE_ROTATION}


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def log_loss(y, p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def columns(groups):
    cols = TEAM + [c for g in groups for c in SAFE_DIFF[g]]
    assert_deployable(cols)
    return cols


def assert_deployable(cols):
    bad = [c for c in cols if c.startswith("oracle_")]
    if bad:
        raise ValueError(f"oracle features in a deployable model: {bad}")


def add_diffs(df, names):
    """Team-a minus team-b differences; heavy-tailed day counts are differenced on log1p(days)."""
    for n in names:
        a, b = df[f"{n}_a"], df[f"{n}_b"]
        if n.startswith("days_since"):
            a, b = np.log1p(a), np.log1p(b)
        df[f"{n}_diff"] = a - b
    return df


class QuantileClipper(BaseEstimator, TransformerMixin):
    """Clips each column to training-fold quantiles so unseen extremes cannot extrapolate linearly."""

    def __init__(self, q=CLIP_Q):
        self.q = q

    def fit(self, x, y=None):
        x = np.asarray(x, float)
        self.lo_, self.hi_ = np.quantile(x, self.q, axis=0), np.quantile(x, 1 - self.q, axis=0)
        return self

    def transform(self, x):
        return np.clip(np.asarray(x, float), self.lo_, self.hi_)


def _prep():
    return [SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), QuantileClipper()]


def logistic(C):
    return make_pipeline(*_prep(), StandardScaler(), LogisticRegression(C=C, max_iter=2000))


def hgb(params):
    return make_pipeline(*_prep(), HistGradientBoostingClassifier(**params, **B12_FIXED))


def fit_predict(make, train, test, cols):
    m = make().fit(train[cols].to_numpy(float), train.y.to_numpy())
    return m, m.predict_proba(test[cols].to_numpy(float))[:, 1]


def inner_split(train):
    seasons = sorted(train.season.unique(), key=lambda s: train.loc[train.season == s, "t"].min())
    if len(seasons) < 2:
        return None
    return train[train.season != seasons[-1]], train[train.season == seasons[-1]]


def select(train, candidates, score):
    """candidates: list of (key, obj), default first. Returns (key, obj, table)."""
    sp = inner_split(train)
    if sp is None:
        return candidates[0][0], candidates[0][1], pd.DataFrame([{"candidate": str(candidates[0][0]),
                                                                    "inner_log_loss": math.nan,
                                                                    "note": "no inner season; a-priori default"}])
    rows = [{"candidate": str(k), "inner_log_loss": score(sp[0], sp[1], obj)} for k, obj in candidates]
    t = pd.DataFrame(rows)
    best = int(np.argmin(np.round(t.inner_log_loss.to_numpy(), 10)))
    return candidates[best][0], candidates[best][1], t


def oracle_identity_design(train, test):
    players = sorted({p for r in train.itertuples() for p in list(r.oracle_players_a) + list(r.oracle_players_b)})
    idx = {p: i for i, p in enumerate(players)}

    def mat(df):
        rows, cols, vals = [], [], []
        for i, r in enumerate(df.itertuples()):
            for p in r.oracle_players_a:
                if p in idx:
                    rows.append(i); cols.append(idx[p]); vals.append(1.0)
            for p in r.oracle_players_b:
                if p in idx:
                    rows.append(i); cols.append(idx[p]); vals.append(-1.0)
        return sparse.csr_matrix((vals, (rows, cols)), shape=(len(df), len(players)))

    mu, sd = train.logit_b5.mean(), train.logit_b5.std() or 1.0
    z = lambda df: sparse.csr_matrix(((df.logit_b5 - mu) / sd).to_numpy()[:, None])  # noqa: E731
    return sparse.hstack([z(train), mat(train)]).tocsr(), sparse.hstack([z(test), mat(test)]).tocsr()


def fit_oracle(oid, train, test):
    if oid == "O1":
        xtr, xte = oracle_identity_design(train, test)
        m = LogisticRegression(C=ORACLE_C, max_iter=2000).fit(xtr, train.y.to_numpy())
        return m.predict_proba(xte)[:, 1]
    cols = TEAM + [f"{c}_diff" for c in ORACLE[oid]]
    return fit_predict(lambda: logistic(RUNG_C), train, test, cols)[1]
