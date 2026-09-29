"""Online temporal rating models and the leakage-safe runner.

Protocol for every model, per timestamp batch (all rows sharing start_time):
1. `start_batch(t, season)`: time/season effects known before play;
2. `predict(a, b, t)` for every row of the batch from the pre-batch state;
3. `update_batch(records)` once, after all predictions of the batch.
No row at timestamp t can therefore learn from another row at timestamp t,
and the current result can never affect its own prediction.
"""
import numpy as np
import pandas as pd

R0 = 1500.0
_DAY_NS = 86_400 * 10**9


class TemporalModel:
    model_id = "BASE"

    def __init__(self, **params):
        self.params = dict(params)
        self.reset()

    def reset(self):
        pass

    def start_batch(self, t, season):
        pass

    def predict(self, a, b, t):
        """Return (p_team_a, pre_rating_a, pre_rating_b)."""
        raise NotImplementedError

    def update_batch(self, records):
        """records: list of (a, b, y_team_a, p_team_a, t, pre_rating_a, pre_rating_b)."""
        raise NotImplementedError


def to_days(ts):
    ts = pd.to_datetime(pd.Series(ts))
    return ts.astype("datetime64[ns]").astype("int64").to_numpy() / _DAY_NS


def prepare_batches(df):
    """Labeled rows -> ordered batches. df needs start_time, season, canonical_team_{a,b}_id, label_team_a_win.

    Returns (ordered frame, batches) where batches = [(t_days, season, [(row_pos, a, b, y), ...]), ...].
    """
    d = df.sort_values(["start_time", "series_id"], kind="stable").reset_index(drop=True)
    days = to_days(d.start_time)
    a = d.canonical_team_a_id.to_numpy(); b = d.canonical_team_b_id.to_numpy()
    y = d.label_team_a_win.astype(float).to_numpy(); season = d.season.to_numpy()
    batches, i, n = [], 0, len(d)
    while i < n:
        j = i
        while j < n and days[j] == days[i]:
            j += 1
        seasons = set(season[i:j])
        if len(seasons) != 1:
            raise ValueError(f"timestamp batch spans several seasons: {sorted(seasons)}")
        batches.append((days[i], season[i], [(k, a[k], b[k], y[k]) for k in range(i, j)]))
        i = j
    return d, batches


def run_online(batches, n_rows, model):
    """Run `model` over prepared batches. Returns arrays aligned with the ordered frame:
    p_team_a, pre_rating_a, pre_rating_b, data_through_days (NaN when no prior data)."""
    model.reset()
    p = np.full(n_rows, np.nan); ra = np.full(n_rows, np.nan); rb = np.full(n_rows, np.nan)
    through = np.full(n_rows, np.nan)
    last = np.nan
    for t, season, rows in batches:
        model.start_batch(t, season)
        recs = []
        for k, a, b, y in rows:
            pk, rak, rbk = model.predict(a, b, t)
            p[k], ra[k], rb[k], through[k] = pk, rak, rbk, last
            recs.append((a, b, y, pk, t, rak, rbk))
        model.update_batch(recs)
        last = t
    return p, ra, rb, through
