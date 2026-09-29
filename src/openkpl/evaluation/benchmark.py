"""Canonical temporal benchmark (v0.3 Phase B): model ladder B0-B5 plus the optional E_SLOT experiment.

Universe: label-eligible canonical series (status 4, decisive score, resolved
identities) with start_time < PROSPECTIVE_HOLDOUT_START. Rows at or after that
boundary are prospective holdout and are never passed to any model, tuner or
metric here. Scheduled/unfinished series are never labels.
"""
import functools
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.evaluation.calibration import EPS, METRIC_KEYS, evaluate, reliability_bins
from openkpl.evaluation.temporal_cv import build_folds, select_hyperparameters
from openkpl.modeling.temporal import (CoinFlip, DecayElo, Elo, SeasonResetElo, SlotInheritanceElo,
                                       SmoothedWinRate, prepare_batches, run_online)
from openkpl.modeling.temporal.base import _DAY_NS, to_days

BENCHMARK_VERSION = "0.3.0-phaseB"
MODEL_FREEZE_DATE = "2026-09-28"
PROSPECTIVE_HOLDOUT_START = pd.Timestamp(MODEL_FREEZE_DATE)
K_GRID = [8.0, 12.0, 16.0, 20.0, 24.0, 32.0, 40.0, 48.0, 64.0, 80.0]
DEFAULTS = {"k": 24.0, "scale": 400.0, "rho": 1.0, "half_life_days": math.inf, "lambda_slot": 0.0}
SLOT_LAMBDAS = [0.0, 0.25, 0.5, 0.75, 1.0]
MIN_SLOT_EXAMPLES = 5
SELECTION = {"metric": "log_loss (mean, probabilities clipped to [1e-6, 1-1e-6])",
             "tie_break": "log loss rounded to 1e-10, then Brier rounded to 1e-10, then closeness to the untuned "
                          "default (K=24, scale=400, rho=1, half_life=inf); remaining exact ties by sorted parameter tuple",
             "inner_objective": "online one-step-ahead predictions over all development rows before the outer "
                                "validation start"}

MODEL_SPECS = [
    {"model_id": "B0", "factory": CoinFlip, "fixed": {}, "grid": None,
     "mechanism": "Constant P(team_a)=0.5"},
    {"model_id": "B1", "factory": SmoothedWinRate, "fixed": {"alpha": 5.0, "beta": 5.0}, "grid": None,
     "mechanism": "Team history: expanding Beta(5,5)-smoothed win rate, combined by log5"},
    {"model_id": "B2", "factory": Elo, "fixed": {"k": 24.0, "scale": 400.0}, "grid": None,
     "mechanism": "Sequential Elo dynamics on canonical IDs (K=24, scale=400, untuned)"},
    {"model_id": "B3", "factory": Elo, "fixed": {},
     "grid": {"k": K_GRID, "scale": [200.0, 300.0, 400.0, 600.0]},
     "mechanism": "Nested temporal tuning of K and scale"},
    {"model_id": "B4", "factory": functools.partial(DecayElo, scale=400.0), "fixed": {"scale": 400.0},
     "grid": {"k": K_GRID, "half_life_days": [14.0, 30.0, 60.0, 90.0, 180.0, 365.0, 730.0, math.inf]},
     "mechanism": "Inactivity regression to 1500 with tuned half-life (K tuned jointly, scale 400)"},
    {"model_id": "B5", "factory": functools.partial(SeasonResetElo, scale=400.0), "fixed": {"scale": 400.0},
     "grid": {"k": K_GRID, "rho": [0.0, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0]},
     "mechanism": "Season-start regression to 1500 with tuned rho (K tuned jointly, scale 400; no decay)"},
]
MODEL_IDS = [m["model_id"] for m in MODEL_SPECS]


def _jsonable(v):
    if isinstance(v, float) and math.isinf(v):
        return "inf"
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return _jsonable(float(v))
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v


def _params_str(params):
    return json.dumps({k: _jsonable(v) for k, v in sorted(params.items())}, sort_keys=True)


def split_universe(canonical, holdout_start=PROSPECTIVE_HOLDOUT_START):
    lab = canonical[canonical.is_label_eligible.astype(bool)].copy()
    lab["start_time"] = pd.to_datetime(lab.start_time)
    hold = lab.start_time >= holdout_start
    return lab[~hold].copy(), lab[hold].copy()


def _slot_affected(d, predecessors):
    """Mask of series involving a slot successor during the season it first appears."""
    mask = np.zeros(len(d), bool)
    for team in predecessors:
        rows = (d.canonical_team_a_id == team) | (d.canonical_team_b_id == team)
        if rows.any():
            first = d.loc[rows, "season"].iloc[0]
            mask |= (rows & (d.season == first)).to_numpy()
    return mask


def compute_benchmark(canonical, membership=None, holdout_start=PROSPECTIVE_HOLDOUT_START):
    dev, holdout = split_universe(canonical, holdout_start)
    folds = build_folds(dev, canonical)
    if folds.empty:
        raise ValueError("no temporal folds: the development universe needs at least two seasons before the "
                         "prospective holdout start")
    d, batches = prepare_batches(dev)
    n = len(d)
    day_to_ts = dict(zip(to_days(d.start_time), d.start_time))
    y = d.label_team_a_win.astype(int).to_numpy()
    cache = {}

    def full_run(key, factory, params):
        k = (key, _params_str(params))
        if k not in cache:
            cache[k] = run_online(batches, n, factory(**params))
        return cache[k]

    def frame(mid, mask, run, fold_id, params):
        p, ra, rb, th = run
        sub = d[mask]
        return pd.DataFrame({
            "series_id": sub.series_id.values, "start_time_raw": sub.start_time_raw.values,
            "start_time": sub.start_time.values, "season": sub.season.values, "stage": sub.stage.values,
            "canonical_team_a_id": sub.canonical_team_a_id.values, "canonical_team_b_id": sub.canonical_team_b_id.values,
            "model_id": mid, "pre_match_rating_a": ra[mask], "pre_match_rating_b": rb[mask],
            "predicted_p_team_a": p[mask], "actual_team_a_win": y[mask], "fold_id": fold_id,
            "is_development": True, "is_prospective_holdout": False,
            "hyperparameter_version": f"{mid}|{fold_id}|{_params_str(params)}",
            "prediction_generated_from_data_through": [day_to_ts.get(t, pd.NaT) if not np.isnan(t) else pd.NaT
                                                       for t in th[mask]],
        })

    preds, selections, slot_rows = [], {m["model_id"]: [] for m in MODEL_SPECS if m["grid"]}, []
    predecessors = {}
    if membership is not None:
        from openkpl.identity.membership import slot_predecessors
        predecessors = slot_predecessors(membership)
    for f in folds.itertuples(index=False):
        mask = (d.season == f.validation_season).to_numpy()
        for spec in MODEL_SPECS:
            mid = spec["model_id"]
            if spec["grid"]:
                params, table = select_hyperparameters(dev, f.validation_start, spec["factory"], spec["grid"], DEFAULTS)
                best = table.iloc[0]
                selections[mid].append({"fold_id": f.fold_id, "validation_season": f.validation_season,
                                        "selected": {k: _jsonable(v) for k, v in params.items()},
                                        "inner_n": int(best.n_inner), "inner_log_loss": float(best.inner_log_loss),
                                        "inner_brier": float(best.inner_brier),
                                        "n_configs_tied_at_best": int(table.tied_at_best.sum()),
                                        "inner_data_through": _jsonable(pd.Timestamp(best.inner_data_through)),
                                        "inner_cutoff_exclusive": _jsonable(pd.Timestamp(f.validation_start))})
            else:
                params = dict(spec["fixed"])
            preds.append(frame(mid, mask, full_run(mid, spec["factory"], params), f.fold_id, params))
        b3 = selections["B3"][-1]["selected"]
        for lam in SLOT_LAMBDAS:
            params = {"k": float(b3["k"]), "scale": float(b3["scale"]), "lambda_slot": lam}
            factory = functools.partial(SlotInheritanceElo, predecessors=predecessors)
            p, *_ = full_run("E_SLOT", factory, params)
            slot_rows.append(pd.DataFrame({"series_id": d.series_id[mask].values, "fold_id": f.fold_id,
                                           "lambda_slot": lam, "p": p[mask], "y": y[mask]}))
    predictions = pd.concat(preds, ignore_index=True).sort_values(
        ["start_time", "series_id", "model_id"], kind="stable").reset_index(drop=True)

    final = {}
    for spec in MODEL_SPECS:
        if spec["grid"]:
            params, table = select_hyperparameters(dev, holdout_start, spec["factory"], spec["grid"], DEFAULTS)
            best = table.iloc[0]
            final[spec["model_id"]] = {"selected": {k: _jsonable(v) for k, v in params.items()},
                                       "inner_n": int(best.n_inner), "inner_log_loss": float(best.inner_log_loss),
                                       "inner_brier": float(best.inner_brier),
                                       "n_configs_tied_at_best": int(table.tied_at_best.sum())}
        else:
            final[spec["model_id"]] = {"selected": {k: _jsonable(v) for k, v in spec["fixed"].items()},
                                       "note": "fixed a priori; not tuned"}

    metrics = pd.DataFrame([{"model_id": m, **evaluate(g.actual_team_a_win, g.predicted_p_team_a)}
                            for m, g in predictions.groupby("model_id", sort=False)])
    metrics = metrics.set_index("model_id").loc[MODEL_IDS].reset_index()
    season_order = folds.validation_season.tolist()
    season = pd.DataFrame([{"model_id": m, "season": s, **evaluate(g.actual_team_a_win, g.predicted_p_team_a)}
                           for (m, s), g in predictions.groupby(["model_id", "season"])])
    season["_o"] = season.season.map({s: i for i, s in enumerate(season_order)})
    season["_m"] = season.model_id.map({m: i for i, m in enumerate(MODEL_IDS)})
    season = season.sort_values(["_m", "_o"]).drop(columns=["_o", "_m"]).reset_index(drop=True)
    calib = pd.concat([reliability_bins(g.actual_team_a_win, g.predicted_p_team_a).assign(model_id=m)
                       for m, g in predictions.groupby("model_id", sort=False)], ignore_index=True)
    calib = calib[["model_id"] + [c for c in calib.columns if c != "model_id"]]
    ablation = build_ablation(metrics)
    slot = build_slot_table(pd.concat(slot_rows, ignore_index=True), d, predecessors)
    return {"dev": dev, "holdout": holdout, "folds": folds, "predictions": predictions, "metrics": metrics,
            "season_metrics": season, "calibration": calib, "ablation": ablation, "selections": selections,
            "final": final, "slot": slot, "predecessors": predecessors, "ordered_dev": d}


def build_ablation(metrics):
    mech = {m["model_id"]: m["mechanism"] for m in MODEL_SPECS}
    m = metrics.set_index("model_id")
    rows, prev = [], None
    for mid in MODEL_IDS:
        ll, br = m.loc[mid, "log_loss"], m.loc[mid, "brier"]
        dll = ll - m.loc[prev, "log_loss"] if prev else math.nan
        dbr = br - m.loc[prev, "brier"] if prev else math.nan
        note = "reference rung" if prev is None else (
            f"vs {prev}: log loss {'improved' if dll < 0 else 'worsened' if dll > 0 else 'unchanged'}, "
            f"Brier {'improved' if dbr < 0 else 'worsened' if dbr > 0 else 'unchanged'}")
        if mid in ("B4", "B5"):
            note += (f"; vs B3 (its actual base): d_log_loss={ll - m.loc['B3', 'log_loss']:+.5f}, "
                     f"d_brier={br - m.loc['B3', 'brier']:+.5f}")
        rows.append({"model": mid, "features_or_mechanism_added": mech[mid], "log_loss": ll,
                     "delta_log_loss_vs_previous": dll, "brier": br, "delta_brier_vs_previous": dbr, "notes": note})
        prev = mid
    return pd.DataFrame(rows)


def build_slot_table(slot_preds, d, predecessors):
    """A slot example is usable when the predecessor played before the successor's first series and that
    first series lies in an out-of-sample validation season."""
    affected_ids = set(d.series_id[_slot_affected(d, predecessors)])
    oos_ids = set(slot_preds.series_id)
    plays = lambda team: (d.canonical_team_a_id == team) | (d.canonical_team_b_id == team)  # noqa: E731
    usable = []
    for team, pred in predecessors.items():
        rows = d[plays(team)]
        if len(rows) and rows.series_id.iloc[0] in oos_ids and (plays(pred) & (d.start_time < rows.start_time.iloc[0])).any():
            usable.append(team)
    status = "INSUFFICIENT EVIDENCE" if len(usable) < MIN_SLOT_EXAMPLES else "ESTIMABLE"
    rows = []
    for lam, g in slot_preds.groupby("lambda_slot"):
        a = g[g.series_id.isin(affected_ids)]
        mo, ma = evaluate(g.y, g.p), evaluate(a.y, a.p)
        rows.append({"lambda_slot": lam, "n_slot_examples": len(usable), "slot_examples": "|".join(
            f"{predecessors[t]}->{t}" for t in sorted(usable)), "n_oos": mo["n"], "oos_log_loss": mo["log_loss"],
            "oos_brier": mo["brier"], "n_affected": ma["n"], "affected_log_loss": ma["log_loss"],
            "affected_brier": ma["brier"], "status": status,
            "note": f"K/scale from the B3 fold selection; minimum {MIN_SLOT_EXAMPLES} slot examples required to "
                    "estimate lambda_slot"})
    t = pd.DataFrame(rows)
    if len(t):
        base = t.loc[t.lambda_slot == 0.0].iloc[0]
        t["delta_affected_log_loss_vs_lambda0"] = t.affected_log_loss - base.affected_log_loss
        t["delta_oos_log_loss_vs_lambda0"] = t.oos_log_loss - base.oos_log_loss
    return t


# ---- artifacts ---------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit(root):
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def known_source_gaps(canonical):
    c = canonical.copy()
    c["start_time"] = pd.to_datetime(c.start_time)
    gaps = [f"No series before {c.start_time.min():%Y-%m-%d} in source: 2020-2021 seasons are not covered."]
    seasons = set(c.season)
    years = sorted({s[3:7] for s in seasons if s.startswith("KPL")})
    for yr in years:
        have = {s for s in seasons if s.startswith(f"KPL{yr}")}
        if f"KPL{yr}S2" in have and f"KPL{yr}S3" not in have:
            gaps.append(f"KPL{yr}S3 (annual finals) is not in the source.")
    gaps.append(f"No series after {c.start_time.max():%Y-%m-%d} in source; any later competition is not covered "
                "(its existence is not asserted here).")
    for s, g in c.groupby("season"):
        unl = g[~g.is_label_eligible.astype(bool)]
        if len(unl):
            gaps.append(f"{s}: {len(g) - len(unl)} of {len(g)} scheduled series have labels; "
                        f"{len(unl)} unplayed/unfinished at crawl time are not labels "
                        f"(flags: {', '.join(sorted(set(unl.data_quality_flag)))}).")
    return gaps


TIMEZONE_STATUS = ("UNVERIFIED. start_time is naive, converted by the crawler with datetime.fromtimestamp in an "
                   "unrecorded local time zone. Ordering is valid if the offset is constant (DST in the crawler zone "
                   "could shift some times by 1h). INFERENCE only: series start at 14:00-20:00 and the one in-progress "
                   "series (14:00 start, 2-0) was crawled at update_time 07:40, consistent with start_time in China "
                   "Standard Time and update_time in UTC.")


def build_manifest(res, canonical, paths, root):
    dev = res["dev"]
    seasons_all = canonical.groupby("season").start_time.min().sort_values().index.tolist()
    included = res["folds"].validation_season.tolist()
    burn_in = [s for s in seasons_all if s in set(dev.season) and s not in included]
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_dataset": "PythonMajor-assignment/data/kpl_data.db",
        "source_dataset_hash": sha256_file(paths["source_db"]),
        "canonical_series_hash": sha256_file(paths["canonical"]),
        "identity_registry_hash": sha256_file(paths["registry"]),
        "membership_table_hash": sha256_file(paths["membership"]),
        "model_freeze_date": MODEL_FREEZE_DATE,
        "development_start": _jsonable(dev.start_time.min()),
        "development_end": _jsonable(dev.start_time.max()),
        "development_rule": "is_label_eligible AND start_time < prospective_holdout_start",
        "prospective_holdout_start": _jsonable(PROSPECTIVE_HOLDOUT_START),
        "prospective_holdout_rule": "every series with start_time >= prospective_holdout_start (includes the 2026 "
                                    "KPL Annual Finals); never used for fitting, tuning, selection or metrics",
        "prospective_holdout_labeled_rows_present": int(len(res["holdout"])),
        "included_seasons": included,
        "training_only_seasons": burn_in,
        "excluded_seasons": [s for s in seasons_all if s not in set(dev.season)],
        "known_source_gaps": known_source_gaps(canonical),
        "timezone_status": TIMEZONE_STATUS,
        "git_commit_if_available": git_commit(root),
        "n_development_series": int(len(dev)),
        "n_oos_predictions_per_model": int(res["folds"].n_validation.sum()),
        "log_loss_epsilon": EPS,
    }


def hyperparameter_record(res):
    return {
        "selection": SELECTION,
        "development_cutoff_exclusive": _jsonable(PROSPECTIVE_HOLDOUT_START),
        "defaults_for_tie_break": {k: _jsonable(v) for k, v in DEFAULTS.items()},
        "fixed_models": {m["model_id"]: {k: _jsonable(v) for k, v in m["fixed"].items()}
                         for m in MODEL_SPECS if not m["grid"]},
        "search_grids": {m["model_id"]: {k: [_jsonable(x) for x in v] for k, v in m["grid"].items()}
                         for m in MODEL_SPECS if m["grid"]},
        "fixed_within_tuned_models": {m["model_id"]: {k: _jsonable(v) for k, v in m["fixed"].items()}
                                      for m in MODEL_SPECS if m["grid"]},
        "fold_level_selections": res["selections"],
        "final_development_selected": res["final"],
        "e_slot": {"lambda_grid": SLOT_LAMBDAS, "k_scale_source": "B3 fold-level selection",
                   "min_slot_examples": MIN_SLOT_EXAMPLES,
                   "predecessors": res["predecessors"]},
        "identifiability_notes": [
            "Elo probabilities depend on K and scale only through K/scale; equivalent pairs tie exactly and are "
            "resolved by closeness to scale=400.",
            "Fold F01 inner window is a single season: rho (B5) is not identifiable there and falls back to the "
            "tie-break (rho=1).",
        ],
    }


def write_benchmark(res, canonical, paths, out_dir, root):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    fmt = "%Y-%m-%d %H:%M:%S"
    folds = res["folds"].copy()
    for c in ["train_start", "train_end", "validation_start", "validation_end"]:
        folds[c] = pd.to_datetime(folds[c]).dt.strftime(fmt)
    folds.to_csv(out / "temporal_folds.csv", index=False, encoding="utf-8-sig")
    res["predictions"].to_parquet(out / "temporal_predictions.parquet", index=False)
    cols = ["model_id", "n", "log_loss", "brier", "accuracy", "roc_auc", "ece", "calibration_intercept",
            "calibration_slope", "mean_predicted_p", "observed_win_rate", "notes"]
    res["metrics"][cols].to_csv(out / "temporal_metrics.csv", index=False, encoding="utf-8-sig")
    res["season_metrics"][["model_id", "season"] + cols[1:]].to_csv(out / "season_metrics.csv", index=False,
                                                                    encoding="utf-8-sig")
    res["calibration"].to_csv(out / "calibration.csv", index=False, encoding="utf-8-sig")
    res["ablation"].to_csv(out / "model_ablation.csv", index=False, encoding="utf-8-sig")
    res["slot"].to_csv(out / "slot_experiment.csv", index=False, encoding="utf-8-sig")
    hp = hyperparameter_record(res)
    (out / "hyperparameters.json").write_text(json.dumps(hp, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = build_manifest(res, canonical, paths, root)
    (out / "benchmark_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest, hp


def run_temporal_benchmark(paths, out_dir, fig_dir, root):
    from openkpl.evaluation.benchmark_report import render_report
    from openkpl.evaluation.figures import make_figures
    from openkpl.identity.membership import read_membership
    canonical = pd.read_parquet(paths["canonical"])
    membership = read_membership(paths["membership"])
    res = compute_benchmark(canonical, membership)
    manifest, hp = write_benchmark(res, canonical, paths, out_dir, root)
    figs = make_figures(out_dir, fig_dir)
    (Path(out_dir) / "temporal_benchmark.md").write_text(render_report(res, manifest, hp, figs), encoding="utf-8")
    return res, manifest
