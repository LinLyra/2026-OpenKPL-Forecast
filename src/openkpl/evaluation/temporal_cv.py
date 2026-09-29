"""Season-level expanding-window folds and nested temporal hyperparameter selection.

Outer fold f validates season v_f; its training data is every development row
with start_time < start(v_f). Inner selection for fold f runs each candidate
configuration online over that training data only and scores its one-step-ahead
predictions there. The tuner truncates at the cutoff itself, so it cannot see
rows at or after the validation start.

Selection: minimum log loss; ties (rounded to 1e-10) broken by Brier, then by
closeness to the untuned default configuration (K = 24, scale = 400, rho = 1,
no decay), which also resolves exactly equivalent K / scale ratios.
"""
import itertools
import math
import re

import numpy as np
import pandas as pd

from openkpl.evaluation.calibration import EPS
from openkpl.modeling.temporal.base import prepare_batches, run_online

FOLD_COLUMNS = ["fold_id", "train_start", "train_end", "validation_start", "validation_end", "train_seasons",
                "validation_season", "n_train", "n_validation", "coverage_warning"]
_SEASON = re.compile(r"^KPL(\d{4})S(\d)$")


def season_sequence(df):
    return df.groupby("season").start_time.min().sort_values(kind="stable").index.tolist()


def _season_warnings(season, prev_season, canonical):
    w = []
    sched = canonical[canonical.season == season]
    lab = int(sched.is_label_eligible.sum())
    if lab < len(sched):
        w.append(f"PARTIAL_SEASON: {lab} of {len(sched)} scheduled series labeled")
    teams = pd.concat([canonical.canonical_team_a_id, canonical.canonical_team_b_id]).groupby(
        pd.concat([canonical.season, canonical.season])).nunique()
    if teams.get(season, 0) < teams.max():
        w.append(f"ANNUAL_FINALS_SUBSET: {teams.get(season, 0)} of {teams.max()} teams, different format")
    m, p = _SEASON.match(season or ""), _SEASON.match(prev_season or "")
    if m and p and int(m.group(1)) == int(p.group(1)) + 1 and p.group(2) == "2":
        w.append(f"PRECEDING_ANNUAL_FINALS_NOT_IN_SOURCE: KPL{p.group(1)}S3 missing")
    return w


def build_folds(dev, canonical):
    seasons = season_sequence(dev)
    rows = []
    for i, v in enumerate(seasons[1:], start=1):
        vs = dev[dev.season == v]
        start = vs.start_time.min()
        train = dev[dev.start_time < start]
        warn = _season_warnings(v, seasons[i - 1], canonical)
        if i == 1:
            warn.insert(0, "SINGLE_SEASON_TRAINING: inner tuning window has no season transition")
        rows.append({"fold_id": f"F{i:02d}", "train_start": train.start_time.min(), "train_end": train.start_time.max(),
                     "validation_start": start, "validation_end": vs.start_time.max(),
                     "train_seasons": "|".join(season_sequence(train)), "validation_season": v,
                     "n_train": int(len(train)), "n_validation": int(len(vs)),
                     "coverage_warning": "; ".join(warn)})
    folds = pd.DataFrame(rows, columns=FOLD_COLUMNS)
    if (folds.train_end >= folds.validation_start).any():
        raise AssertionError("a fold trains on data at or after its validation start")
    return folds


def grid_configs(grid):
    keys = list(grid)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(grid[k] for k in keys))]


def _closeness(value, default):
    if default is None:
        return 0.0
    if math.isinf(default):
        return 0.0 if math.isinf(value) else 1.0 / value
    if math.isinf(value):
        return math.inf
    if default > 0 and value > 0:
        return abs(math.log(value / default))
    return abs(value - default)


def tie_break_key(params, log_loss, brier, defaults):
    return (round(log_loss, 10), round(brier, 10),
            round(sum(_closeness(v, defaults.get(k)) for k, v in params.items()), 10),
            tuple(sorted((k, v) for k, v in params.items())))


def score_config(batches, n, factory, params):
    p, *_ = run_online(batches, n, factory(**params))
    y = np.array([r[3] for _, _, rows in batches for r in rows])
    order = np.array([r[0] for _, _, rows in batches for r in rows])
    p = p[order]
    pc = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc))), float(np.mean((p - y) ** 2))


def select_hyperparameters(dev, cutoff, factory, grid, defaults):
    """Pick the best configuration using only rows with start_time < cutoff. Returns (params, table)."""
    train = dev[dev.start_time < cutoff]
    if train.empty:
        raise ValueError("no training rows before cutoff")
    d, batches = prepare_batches(train)
    rows = []
    for params in grid_configs(grid):
        ll, br = score_config(batches, len(d), factory, params)
        rows.append({**params, "inner_log_loss": ll, "inner_brier": br,
                     "_key": tie_break_key(params, ll, br, defaults)})
    table = pd.DataFrame(rows).sort_values("_key", kind="stable").reset_index(drop=True)
    best_key = table._key.iloc[0]
    table["tied_at_best"] = [k[:2] == best_key[:2] for k in table._key]
    best = {k: float(table.loc[0, k]) for k in grid}
    return best, table.drop(columns="_key").assign(n_inner=len(d), inner_cutoff=cutoff,
                                                    inner_data_through=d.start_time.max())
