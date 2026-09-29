import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl-openkpl")
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from openkpl.evaluation.calibration import reliability_bins  # noqa: E402


def make(out, boot, season, preds, trace, rot, order):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    b = boot[boot.reference == "B5"].set_index("model_id").reindex([m for m in order if m != "B5"]).dropna(how="all")
    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(b))
    ax.errorbar(b.mean_delta_log_loss, y, xerr=[b.mean_delta_log_loss - b.delta_log_loss_ci_low,
                                              b.delta_log_loss_ci_high - b.mean_delta_log_loss], fmt="o", capsize=3)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(y, b.index)
    ax.set_xlabel("delta log loss vs frozen B5 (negative = better), 95% paired bootstrap")
    ax.set_title("v0.5 deployable + exploratory models vs B5 (1,194 series, 2023S1-2026S2)")
    fig.tight_layout(); fig.savefig(out / "model_comparison.png", dpi=130); plt.close(fig)
    for metric, name in (("log_loss", "logloss_by_season.png"), ("brier", "brier_by_season.png")):
        fig, ax = plt.subplots(figsize=(10, 5))
        for m in order:
            d = season[season.model_id == m]
            ax.plot(d.season.str[3:], d[metric], marker="o", lw=2.5 if m == "B5" else 1, label=m)
        ax.set_ylabel(metric); ax.legend(ncol=4, fontsize=8); ax.set_title(f"{metric} by validation season")
        fig.tight_layout(); fig.savefig(out / name, dpi=130); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 6))
    for m in ("B5", "B11", "B12", "X3"):
        d = preds[preds.model_id == m]
        rb = reliability_bins(d.y, d.p)
        rb = rb[rb.n > 0]
        ax.plot(rb.mean_predicted_p, rb.observed_win_rate, marker="o", label=m)
    ax.plot([0, 1], [0, 1], "k--", lw=0.8)
    ax.set_xlabel("mean predicted P(team_a wins)"); ax.set_ylabel("observed team_a win rate")
    ax.legend(); ax.set_title("Reliability (raw, out-of-time)")
    fig.tight_layout(); fig.savefig(out / "calibration_comparison.png", dpi=130); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 5))
    top = trace.groupby("player_id").size().sort_values(ascending=False).index[:8]
    for p in top:
        d = trace[trace.player_id == p]
        ax.plot(d.t, d.rating, lw=1, label=f"{p} ({d.team.iloc[-1]})")
    ax.axhline(1500, color="k", lw=0.6)
    ax.set_ylabel("effective player rating"); ax.legend(fontsize=7, ncol=2)
    ax.set_title("Player rating history (8 most-active players; latest fold-selected config)")
    fig.tight_layout(); fig.savefig(out / "player_rating_history.png", dpi=130); plt.close(fig)
    r = rot.sort_values("core5_mean_rating", ascending=False)
    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(r))
    ax.bar(x - 0.27, r.core5_mean_rating, 0.27, label="core5 mean")
    ax.bar(x, r.player6_rating, 0.27, label="player6")
    ax.bar(x + 0.27, r.player7_rating, 0.27, label="player7")
    ax.set_xticks(x, r.team_id.str.replace("TEAM_", ""), rotation=60, fontsize=8)
    ax.set_ylim(1300, max(1800, np.nanmax(r[["core5_mean_rating", "player6_rating", "player7_rating"]].to_numpy()) + 20))
    ax.legend(); ax.set_title("2026 core vs bench player ratings (state after 2026S2; descriptive)")
    fig.tight_layout(); fig.savefig(out / "rotation_strength_2026.png", dpi=130); plt.close(fig)
    return sorted(p.name for p in out.glob("*.png"))
