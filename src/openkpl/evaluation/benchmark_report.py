"""Markdown report for the temporal benchmark, rendered from computed benchmark results."""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.evaluation.benchmark import MODEL_IDS, MODEL_SPECS, MIN_SLOT_EXAMPLES, SLOT_LAMBDAS
from openkpl.evaluation.calibration import EPS

PAIRS = [("B1", "B0"), ("B2", "B1"), ("B3", "B2"), ("B4", "B3"), ("B5", "B3"), ("B5", "B4")]


def _f(v, nd=4):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "NA"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        return f"{v:.{nd}f}"
    return str(v)


def table(df, cols=None, nd=4):
    cols = cols or list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in df[cols].itertuples(index=False):
        lines.append("| " + " | ".join(_f(v, nd) for v in r) + " |")
    return "\n".join(lines)


def _row_logloss(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired_differences(pred):
    w = pred.pivot(index="series_id", columns="model_id", values="predicted_p_team_a")
    y = pred.drop_duplicates("series_id").set_index("series_id").actual_team_a_win.reindex(w.index).astype(float)
    rows = []
    for a, b in PAIRS:
        dl = _row_logloss(w[a], y) - _row_logloss(w[b], y)
        db = (w[a] - y) ** 2 - (w[b] - y) ** 2
        n = len(dl)
        rows.append({"comparison": f"{a} - {b}", "n": n, "mean_d_log_loss": dl.mean(),
                     "se_d_log_loss": dl.std(ddof=1) / math.sqrt(n), "mean_d_brier": db.mean(),
                     "se_d_brier": db.std(ddof=1) / math.sqrt(n)})
    t = pd.DataFrame(rows)
    t["log_loss_diff_over_2se"] = (t.mean_d_log_loss.abs() > 2 * t.se_d_log_loss)
    return t


def spread(pred):
    rows = []
    for m, g in pred.groupby("model_id", sort=False):
        p = g.predicted_p_team_a
        rows.append({"model_id": m, "sd_p": p.std(ddof=0), "min_p": p.min(), "max_p": p.max(),
                     "share_p_in_0.4_0.6": ((p >= 0.4) & (p <= 0.6)).mean()})
    return pd.DataFrame(rows)


def calibration_reading(slope, intercept):
    out = []
    if isinstance(slope, float) and math.isnan(slope):
        out.append("slope undefined (constant predictions)")
    elif slope < 0.8:
        out.append("over-confident (slope < 0.8: predictions too extreme)")
    elif slope > 1.2:
        out.append("under-confident / compressed (slope > 1.2)")
    else:
        out.append("slope within [0.8, 1.2]")
    if not math.isnan(intercept) and abs(intercept) > 0.1:
        out.append(f"calibration-in-the-large offset {intercept:+.3f} (positive = team_a wins more often than predicted)")
    return "; ".join(out)


def render_report(res, manifest, hp, figs):
    m, s, folds, pred = res["metrics"], res["season_metrics"], res["folds"], res["predictions"]
    abl, slot = res["ablation"], res["slot"]
    pairs = paired_differences(pred)
    spr = spread(pred)
    by_ll = m.sort_values("log_loss").model_id.tolist()
    by_br = m.sort_values("brier").model_id.tolist()
    b0 = m.set_index("model_id").loc["B0"]
    mi = m.set_index("model_id")
    fig_rel = {k: "../../figures/benchmark/" + Path(v).name for k, v in figs.items()}
    L = []
    add = L.append

    add("# OpenKPL Temporal Benchmark (v0.3 Phase B)\n")
    add(f"Generated {manifest['generated_at']} | benchmark {manifest['benchmark_version']} | "
        f"git commit: {manifest['git_commit_if_available'] or 'not available (not a git repository)'}\n")
    add("No final model is selected in this report. Model freeze is a separate, explicit step (`openkpl freeze`).\n")

    add("## 1. Executive summary\n")
    add(f"- Out-of-sample (OOS) predictions: {int(m.n.iloc[0])} completed series per model across {len(folds)} "
        f"season-level expanding-window folds ({folds.validation_season.iloc[0]} to {folds.validation_season.iloc[-1]}).")
    add(f"- Lowest OOS log loss: {by_ll[0]} ({mi.loc[by_ll[0], 'log_loss']:.4f}); lowest OOS Brier: {by_br[0]} "
        f"({mi.loc[by_br[0], 'brier']:.4f}). B0 coin flip: log loss {b0.log_loss:.4f}, Brier {b0.brier:.4f}.")
    add(f"- Log loss ranking: {' < '.join(by_ll)}. Brier ranking: {' < '.join(by_br)}.")
    sig = pairs[pairs.log_loss_diff_over_2se]
    add("- Paired per-series log-loss differences exceeding 2 naive standard errors: "
        + (", ".join(f"{r.comparison} ({r.mean_d_log_loss:+.4f})" for r in sig.itertuples()) or "none") + ".")
    add(f"- The first-listed team (team_a) won {b0.observed_win_rate:.1%} of OOS series. No model here uses side/"
        "order information, so all models are symmetric in team_a/team_b.")
    add(f"- Prospective holdout (start_time >= {manifest['prospective_holdout_start']}): "
        f"{manifest['prospective_holdout_labeled_rows_present']} labeled rows present; none were used.\n")

    add("## 2. Data universe\n")
    add(f"- Source: `{manifest['source_dataset']}` (sha256 `{manifest['source_dataset_hash'][:16]}...`), via "
        "`data/processed/temporal/canonical_series.parquet`. The WZRY draft corpus is not used and not joined.")
    add(f"- Development rule: `{manifest['development_rule']}`; {manifest['n_development_series']} series from "
        f"{manifest['development_start']} to {manifest['development_end']}.")
    add(f"- Validation (OOS) seasons: {', '.join(manifest['included_seasons'])}. Training-only seasons: "
        f"{', '.join(manifest['training_only_seasons']) or 'none'}. Excluded seasons: "
        f"{', '.join(manifest['excluded_seasons']) or 'none'}.")
    add("- Labels: status == 4 with a decisive series score and both teams resolved. Scheduled or unfinished series "
        "are never labels.\n")

    add("## 3. Identity resolution\n")
    add("- Observed names are mapped to canonical team IDs using VERIFIED rows of "
        "`data/dimensions/team_identity_registry.csv`; raw names are kept as `raw_team_a` / `raw_team_b`.")
    add("- Multi-name canonical teams: TEAM_HERO, TEAM_DRG, TEAM_LGD_NBW, TEAM_MTG, TEAM_QINGJIU, TEAM_TCG, TEAM_KSG "
        "(KSG is a SOURCE_ALIAS, not a verified rebrand). All other names are one-to-one.")
    add("- League-slot continuity (厦门VG -> 北京JDG) is stored separately in `team_season_membership.csv` and does not "
        "affect B0-B5. See `canonicalization_audit.csv` for resolution counts and checks.\n")

    add("## 4. Known coverage gaps\n")
    for g in manifest["known_source_gaps"]:
        add(f"- {g}")
    add(f"- Timezone: {manifest['timezone_status']}")
    add("- Missing seasons are not imputed. Ratings carry across gaps as if no matches occurred.\n")

    add("## 5. Temporal validation design\n")
    add("- Season-level expanding window: fold f trains on every development series before the start of validation "
        "season v_f and validates on v_f. Within a fold, models still predict online (each series from data strictly "
        "before its timestamp), so validation-season results also update ratings for later validation series. "
        "This is standard for sequential rating systems; no validation label is used before its own prediction.")
    add("- Same-timestamp series are predicted as a batch from the pre-timestamp state, then updated together. "
        "(The current source has no shared timestamps among completed series; the logic is tested on synthetic data.)")
    add("- Nested tuning: for fold f, each configuration is run online over training rows only (start_time < "
        "validation start) and scored on those one-step-ahead predictions; the best configuration is then applied to "
        "the validation season.\n")
    ft = folds.copy()
    for c in ["train_start", "train_end", "validation_start", "validation_end"]:
        ft[c] = pd.to_datetime(ft[c]).dt.strftime("%Y-%m-%d")
    add(table(ft, ["fold_id", "train_seasons", "validation_season", "n_train", "n_validation", "coverage_warning"]))
    add("")

    add("## 6. Model definitions\n")
    add("| model | mechanism |\n|---|---|")
    for spec in MODEL_SPECS:
        add(f"| {spec['model_id']} | {spec['mechanism']} |")
    add("\nFormulas: Elo P(A) = 1 / (1 + 10^((R_B - R_A)/scale)), R <- R + K(y - P), new teams at 1500. "
        "B4: R_pre(t) = 1500 + (R - 1500) * 2^(-(t - t_last)/h). B5: at each new season label, "
        "R <- 1500 + rho (R - 1500). B1: s = (w + 5)/(n + 10), combined by log5.\n")

    add("## 7. Hyperparameter selection\n")
    add(f"- Objective: {hp['selection']['metric']}. Tie-break: {hp['selection']['tie_break']}.")
    for note in hp["identifiability_notes"]:
        add(f"- {note}")
    rows = []
    for mid, sel in res["selections"].items():
        for r in sel:
            rows.append({"model": mid, "fold": r["fold_id"], "validation": r["validation_season"],
                         "selected": ", ".join(f"{k}={v}" for k, v in r["selected"].items()),
                         "inner_n": r["inner_n"], "inner_log_loss": r["inner_log_loss"],
                         "tied": r["n_configs_tied_at_best"]})
    add("\nFold-level selections (inner data strictly before validation start):\n")
    add(table(pd.DataFrame(rows)))
    add("\nFinal development-selected values (all development data; candidates for freeze only):\n")
    for mid, f in res["final"].items():
        add(f"- {mid}: {', '.join(f'{k}={v}' for k, v in f['selected'].items()) or '(no parameters)'}")
    add("")

    add("## 8. Overall OOS results\n")
    add(table(m, ["model_id", "n", "log_loss", "brier", "accuracy", "roc_auc", "ece", "calibration_intercept",
                  "calibration_slope", "mean_predicted_p", "observed_win_rate"]))
    add(f"\n![model comparison]({fig_rel['model_comparison']})\n")
    add("Paired per-series differences (negative = first model better). SE assumes independent series and is "
        "therefore optimistic:\n")
    add(table(pairs, nd=5))
    add("")

    add("## 9. Season-by-season results\n")
    wide_ll = s.pivot(index="season", columns="model_id", values="log_loss").reindex(folds.validation_season)[MODEL_IDS]
    wide_br = s.pivot(index="season", columns="model_id", values="brier").reindex(folds.validation_season)[MODEL_IDS]
    add("Log loss:\n"); add(table(wide_ll.reset_index()))
    add("\nBrier:\n"); add(table(wide_br.reset_index()))
    worse = [x for x in wide_ll.index if (wide_ll.loc[x, ["B2", "B3", "B4", "B5"]] > wide_ll.loc[x, "B0"]).all()]
    add(f"\nSeasons where every Elo variant (B2-B5) has higher log loss than B0: {', '.join(worse) or 'none'}.")
    add(f"\n![log loss by season]({fig_rel['logloss_by_season']})\n![brier by season]({fig_rel['brier_by_season']})\n")

    add("## 10. Calibration analysis\n")
    cal = m[["model_id", "ece", "calibration_intercept", "calibration_slope"]].merge(spr, on="model_id")
    cal["reading"] = [calibration_reading(r.calibration_slope, r.calibration_intercept) for r in cal.itertuples()]
    add(table(cal))
    unstable = s[(s.model_id.isin(["B2", "B3", "B4", "B5"])) &
                 ((s.calibration_slope < 0.5) | (s.calibration_slope > 1.5) | (s.ece > 0.1))]
    add("\nSeason-level instability (B2-B5 rows with slope outside [0.5, 1.5] or ECE > 0.10):\n")
    add(table(unstable[["model_id", "season", "n", "ece", "calibration_intercept", "calibration_slope"]])
        if len(unstable) else "none")
    add(f"\n![calibration]({fig_rel['calibration_curve']})\n")
    add("Raw-model diagnostics only; no post-hoc recalibration is applied.\n")

    add("## 11. Ablation findings\n")
    add(table(abl, nd=5))
    add("")

    add("## 12. Slot-continuity experiment (E_SLOT, not part of B0-B5)\n")
    if len(slot):
        add(f"Status: **{slot.status.iloc[0]}** ({int(slot.n_slot_examples.iloc[0])} usable slot example(s): "
            f"{slot.slot_examples.iloc[0] or 'none'}; minimum {MIN_SLOT_EXAMPLES}). Lambda grid {SLOT_LAMBDAS}.\n")
        add(table(slot[["lambda_slot", "n_oos", "oos_log_loss", "oos_brier", "n_affected", "affected_log_loss",
                        "affected_brier", "delta_affected_log_loss_vs_lambda0"]], nd=5))
        add("\nNo best lambda is claimed. The affected rows are the successor team's series in its first season.\n")

    add("## 13. Failure cases\n")
    ref = by_ll[0] if by_ll[0] != "B0" else by_ll[1]
    g = pred[pred.model_id == ref].copy()
    g["row_log_loss"] = _row_logloss(g.predicted_p_team_a, g.actual_team_a_win.astype(float))
    top = g.sort_values(["row_log_loss", "series_id"], ascending=[False, True]).head(10)
    add(f"Ten highest-loss OOS predictions for {ref} (lowest overall log loss excluding B0):\n")
    add(table(top[["series_id", "season", "stage", "canonical_team_a_id", "canonical_team_b_id",
                   "predicted_p_team_a", "actual_team_a_win"]]))
    stages = g.groupby("stage").agg(n=("row_log_loss", "size"), log_loss=("row_log_loss", "mean")).reset_index()
    add(f"\n{ref} OOS log loss by stage:\n"); add(table(stages.sort_values("log_loss", ascending=False)))
    add("")

    add("## 14. Limitations\n")
    for x in [
        "Series-level outcomes only: no game scores, margins, rosters, patches, or draft information are used.",
        "Coverage gaps (section 4) mean ratings bridge missing seasons without data.",
        "Timestamps are in an unverified time zone; only relative order is used.",
        "Standard errors in section 8 ignore serial dependence and multiple comparisons.",
        "Annual-finals seasons are short, knockout-heavy and include only top teams; their metrics are noisy.",
        "KPL2026S1 is partial (crawl on 2026-02-04).",
        "Team_a wins more often than 50%; symmetric models cannot use this, and B0 is not the best constant.",
        "One-to-one canonical identities were created on reviewer instruction without per-name external URLs.",
    ]:
        add(f"- {x}")
    add("")

    add("## 15. Prospective freeze protocol\n")
    add(f"- MODEL_FREEZE_DATE = {manifest['model_freeze_date']}; prospective holdout = every series with start_time "
        f">= {manifest['prospective_holdout_start']} (includes the 2026 KPL Annual Finals).")
    add("- Holdout rows are removed before any fitting, tuning, selection, calibration or metric in this benchmark.")
    add("- After review, run `openkpl freeze --model <ID>` once. It records hashes, the chosen model, its "
        "development-selected hyperparameters and development metrics in `reports/freeze/`, and refuses to "
        "overwrite an existing freeze without `--force`.")
    add("- Only after freeze may holdout results be collected and scored, with no further changes.\n")

    add("## 16. Reproduction commands\n")
    add("```bash\npython -m pip install -e .\npython -m unittest discover -s tests -v\n"
        "python -m openkpl.cli build-temporal\npython -m openkpl.cli canonicalize\n"
        "python -m openkpl.cli temporal-benchmark\n# later, after review only:\n"
        "# python -m openkpl.cli freeze --model <ID>\n```\n")
    add(f"![elo history]({fig_rel['elo_history']})\n")
    return "\n".join(L)
