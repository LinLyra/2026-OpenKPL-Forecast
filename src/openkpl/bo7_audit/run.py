"""Run the v0.6.1 BO7 calibration audit: `python -m openkpl.bo7_audit.run`."""
import datetime as dt
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl-openkpl")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from openkpl.bo7_audit import audit as AU  # noqa: E402
from openkpl.bo7_audit import lock  # noqa: E402
from openkpl.evaluation.calibration import reliability_bins  # noqa: E402
from openkpl.roster import baseline  # noqa: E402

OUT = Path("reports/bo7_audit")
FIG = Path("figures/bo7_audit")
PRIMARY = ["C0", "C1", "C2", "C3", "C4", "CSEL"]
SECONDARY = ["C1_A", "C2_A", "C3_A", "C4_A", "CSEL_A"]


def guard(root="."):
    root = Path(root)
    if not (root / lock.RULE_PATH).exists() or not (root / lock.LOCK_PATH).exists():
        raise RuntimeError("PROMOTION_RULE.md and the v0.6.1 lock must exist before any model is fitted")
    bad = lock.check(root)
    if bad:
        raise RuntimeError(f"lock verification failed: {bad}")
    return baseline.sha256_file(root / lock.RULE_PATH)


def analyse(series, fmt):
    preds, stab = AU.run_format(series, fmt)
    boot = AU.bootstrap(preds, PRIMARY + SECONDARY)
    boot_sec = AU.bootstrap(preds, ["CSEL_A"], ref="CSEL")
    df = series[series.format == fmt]
    loso = AU.leave_one_season_out(df)
    drop = AU.drop_one_season(preds)
    crit, decision = AU.promotion(preds, boot, stab, loso, drop)
    crit_a, dec_a = AU.promotion(preds, boot, stab, loso, AU.drop_one_season(preds, "CSEL_A"),
                                 model="CSEL_A", family="SECONDARY_intercept")
    sec_beats_primary = bool(boot_sec.frac_beats_ref_log_loss.iloc[0] >= 0.95)
    return dict(preds=preds, stab=stab, boot=boot, boot_sec=boot_sec, loso=loso, drop=drop, crit=crit,
                decision=decision, crit_a=crit_a, dec_a=dec_a, sec_beats_primary=sec_beats_primary,
                bins=AU.favorite_bins(df), metrics=AU.metrics(preds), season=AU.by_season(preds))


def figures(r7, r5):
    FIG.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))
    for m, c in (("B5", "k"), ("C1", "tab:red"), ("CSEL", "tab:blue")):
        g = r7["preds"][r7["preds"].model_id == m]
        rb = reliability_bins(g.y.to_numpy(), g.p.to_numpy(), n_bins=5)
        rb = rb[rb.n > 0]
        ax.plot(rb.mean_predicted_p, rb.observed_win_rate, "o-", color=c, label=f"{m} (n={len(g)})")
    ax.plot([0, 1], [0, 1], ":", color="grey")
    ax.set(xlabel="predicted P(team_a wins series)", ylabel="observed", title="BO7 OOT calibration (5 bins)")
    ax.legend()
    fig.tight_layout(); fig.savefig(FIG / "bo7_calibration.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for r, fmt, st in ((r7, "BO7", "-"), (r5, "BO5 (control)", "--")):
        s = r["stab"][r["stab"].model_family == "PRIMARY_zero_intercept"]
        ax.plot(s.training_end, s.beta_raw, "o" + st, label=f"{fmt} beta_raw (C1)")
        ax.plot(s.training_end, s.beta_shrunk, "s" + st, alpha=.6, label=f"{fmt} beta_shrunk (CSEL)")
    ax.axhline(1, color="grey", lw=1)
    ax.set(xlabel="training cutoff (last training season)", ylabel="beta", title="Pooled beta by training cutoff")
    ax.tick_params(axis="x", rotation=45); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "bo7_beta_stability.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 5))
    for r, fmt, c in ((r7, "BO7", "tab:red"), (r5, "BO5", "tab:blue")):
        b = r["bins"]
        ax.plot(b.mean_predicted_favorite_p, b.observed_favorite_win_rate, "o-", color=c, label=fmt)
        for x in b.itertuples():
            ax.annotate(f"n={x.n}", (x.mean_predicted_favorite_p, x.observed_favorite_win_rate), fontsize=7)
    ax.plot([.5, 1], [.5, 1], ":", color="grey")
    ax.set(xlabel="mean B5 favorite probability", ylabel="observed favorite win rate",
           title="Favorite-strength bins (descriptive, all B5 seasons)")
    ax.legend()
    fig.tight_layout(); fig.savefig(FIG / "bo7_predicted_vs_observed.png", dpi=130); plt.close(fig)


def main():
    started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rule_sha = guard()
    series = AU.load_series(".")
    r7, r5 = analyse(series, "BO7"), analyse(series, "BO5")

    def tag(d, **kw):
        return d.assign(**kw)

    fam = lambda m: "SECONDARY_intercept" if m.endswith("_A") else ("REFERENCE" if m == "B5" else "PRIMARY")  # noqa: E731
    mm = r7["metrics"].merge(r7["boot"].add_prefix("vs_B5_").rename(columns={"vs_B5_model_id": "model_id"}),
                             on="model_id", how="left")
    mm.insert(1, "family", mm.model_id.map(fam))
    mm["lambda"] = mm.model_id.str.replace("_A", "").map({"C0": np.inf, **AU.LAMBDAS})
    mm.to_csv(OUT / "bo7_calibration_models.csv", index=False)
    tag(r7["season"], family=r7["season"].model_id.map(fam)).to_csv(OUT / "bo7_temporal_results.csv", index=False)
    pd.concat([r7["boot"].assign(family=r7["boot"].model_id.map(fam)),
               r7["boot_sec"].assign(family="SECONDARY_vs_PRIMARY")]).to_csv(OUT / "bo7_bootstrap.csv", index=False)
    r7["stab"].to_csv(OUT / "bo7_beta_stability.csv", index=False)
    r7["loso"].to_csv(OUT / "bo7_leave_one_season_out.csv", index=False)
    b = pd.concat([r7["bins"].assign(format="BO7"), r5["bins"].assign(format="BO5 (control, descriptive)")])
    b.to_csv(OUT / "bo7_favorite_bins.csv", index=False)
    ctrl = r5["metrics"].merge(r5["boot"].add_prefix("vs_B5_").rename(columns={"vs_B5_model_id": "model_id"}),
                               on="model_id", how="left").assign(section="metrics")
    stab5 = r5["stab"].assign(section="beta_stability")
    loso5 = r5["loso"].assign(section="leave_one_season_out")
    pd.concat([ctrl, stab5, loso5], ignore_index=True).assign(format="BO5", role="NEGATIVE_CONTROL (not used for BO7)") \
        .to_csv(OUT / "bo5_negative_control.csv", index=False)
    r7["drop"].to_csv(OUT / "bo7_drop_one_validation_season.csv", index=False)
    pd.concat([r7["preds"].assign(format="BO7"), r5["preds"].assign(format="BO5")]) \
        .to_parquet("data/processed/modeling/bo7_audit_predictions.parquet", index=False)
    figures(r7, r5)

    after = lock.check()
    summary = {"started_at": started, "promotion_rule_sha256": rule_sha, "lock_created_at":
               json.loads(Path(lock.LOCK_PATH).read_text())["created_at"],
               "bo7_series_all_b5_seasons": int((series.format == "BO7").sum()),
               "bo7_validation_series": int(r7["preds"].query("model_id=='B5'").shape[0]),
               "bo5_validation_series": int(r5["preds"].query("model_id=='B5'").shape[0]),
               "criteria_primary": r7["crit"], "decision": r7["decision"],
               "criteria_secondary": r7["crit_a"], "secondary_passes_all": r7["dec_a"] == "PROMOTE_BO7_CORRECTION",
               "secondary_beats_primary_95": r7["sec_beats_primary"],
               "bo5_control_criteria": r5["crit"], "bo5_control_would_pass_rule": r5["decision"] == "PROMOTE_BO7_CORRECTION",
               "lock_after_run": "verified" if not after else after}
    (OUT / "run_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    if after:
        raise RuntimeError(f"HARD FAILURE: locked artifacts changed: {after}")
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
