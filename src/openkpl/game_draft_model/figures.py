import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl-openkpl")
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from openkpl.evaluation.calibration import reliability_bins  # noqa: E402


def _ci(ax, b, title, xlabel):
    y = np.arange(len(b))
    ax.errorbar(b.mean_delta_log_loss, y, xerr=[b.mean_delta_log_loss - b.delta_log_loss_ci_low,
                                              b.delta_log_loss_ci_high - b.mean_delta_log_loss], fmt="o", capsize=3)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(y, b.model_id)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel(xlabel, fontsize=9)


def _rel(ax, df, models, title):
    for m in models:
        d = df[df.model_id == m]
        rb = reliability_bins(d.y, d.p)
        rb = rb[rb.n > 0]
        ax.plot(rb.mean_predicted_p, rb.observed_win_rate, marker="o", label=m)
    ax.plot([0, 1], [0, 1], "k--", lw=0.8)
    ax.set_xlabel("mean predicted P(team_a)"); ax.set_ylabel("observed")
    ax.legend(fontsize=8); ax.set_title(title, fontsize=10)


def make(out, game_boot, series_boot, fmt, spreds, draft_boot, dpreds, dig, seq_m):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.5))
    for ax, mode in zip(axs, ("PRE_SERIES", "LIVE_SERIES")):
        _ci(ax, game_boot[game_boot["mode"] == mode], f"Game models vs G1 ({mode}); series-clustered bootstrap",
            "delta game log loss vs G1 (negative = better)")
    fig.tight_layout(); fig.savefig(out / "game_model_comparison.png", dpi=130); plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(13, 5))
    _rel(axs[0], spreds, ["S0", "S1", "S4"], "Series reliability (out-of-time)")
    _ci(axs[1], series_boot, "Series models vs B5 (series bootstrap)", "delta series log loss vs B5")
    fig.tight_layout(); fig.savefig(out / "series_probability_calibration.png", dpi=130); plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.5))
    x = np.arange(len(fmt))
    axs[0].bar(x - 0.2, fmt.game_favorite_mean_predicted, 0.4, label="predicted")
    axs[0].bar(x + 0.2, fmt.game_favorite_observed_win_rate, 0.4, label="observed")
    axs[0].set_xticks(x, fmt.format); axs[0].set_ylim(0.5, 0.8); axs[0].set_title("Game favorite (G*, PRE-SERIES)")
    axs[0].legend()
    w = 0.2
    for i, (m, lab) in enumerate((("S0", "B5 predicted"), ("S1", "S1 predicted"))):
        axs[1].bar(x + (i - 1) * w, fmt[f"{m}_series_favorite_mean_predicted"], w, label=lab)
    axs[1].bar(x + w, fmt.S1_series_favorite_observed_win_rate, w, label="observed (S1 favorite)")
    axs[1].set_xticks(x, [f"{f} (n={n})" for f, n in zip(fmt.format, fmt.n_series)]); axs[1].set_ylim(0.5, 0.9)
    axs[1].set_title("Series favorite by format"); axs[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / "bo5_vs_bo7.png", dpi=130); plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 5))
    _ci(ax, draft_boot[draft_boot.reference == "D0"], "Draft models vs D0 (series-clustered bootstrap, 1,426 games)",
        "delta game log loss vs D0 (negative = better)")
    fig.tight_layout(); fig.savefig(out / "draft_model_comparison.png", dpi=130); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 6))
    _rel(ax, dpreds, ["D0", "D1", "D4", "D5", "D6"], "Draft models reliability (out-of-time)")
    fig.tight_layout(); fig.savefig(out / "draft_calibration.png", dpi=130); plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, by in zip(axs, ("season", "game_number")):
        d = dig[dig.group_by == by]
        ax.bar(d.group, d.mean_DIG_vs_D0, label="vs D0")
        ax.bar(d.group, d.mean_DIG_vs_D0R, alpha=0.5, label="vs D0R")
        ax.axhline(0, color="k", lw=0.8); ax.set_title(f"Mean DIG (D5) by {by}"); ax.legend(fontsize=8)
        ax.tick_params(axis="x", rotation=30)
    fig.tight_layout(); fig.savefig(out / "draft_information_gain.png", dpi=130); plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(seq_m.step, seq_m.log_loss, marker="o")
    for s, lab in zip(seq_m.step, seq_m.checkpoint):
        if isinstance(lab, str) and lab:
            ax.axvline(s, color="grey", lw=0.5)
            ax.text(s, seq_m.log_loss.max(), lab.split(" ")[0], rotation=90, fontsize=6, va="top")
    ax.set_xlabel("draft events observed"); ax.set_ylabel("log loss (validation games)")
    ax.set_title("Sequential draft: out-of-time log loss by draft step")
    fig.tight_layout(); fig.savefig(out / "win_probability_by_draft_step.png", dpi=130); plt.close(fig)
    return sorted(p.name for p in out.glob("*.png"))
