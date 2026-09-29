"""Figures for the v1.0 tournament forecast (team labels = canonical ids, avoiding CJK font dependence)."""
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl-openkpl")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from openkpl.tournament import engine as E

FIG = "figures/tournament"


def _save(fig, root, name):
    fig.tight_layout()
    fig.savefig(root / FIG / name, dpi=150)
    plt.close(fig)


def make_all(root, ctx, runs, fc, conv, step, pa):
    short = dict(zip(ctx.names, ctx.short))
    P0 = runs["PRIMARY"]
    n = P0["n"]
    order = np.argsort(-P0["p"]["champion"])
    lab = [ctx.short[i] for i in order]

    for key, fname, title in (("champion", "championship_probabilities.png", "P(champion) — PRIMARY frozen raw B5"),
                              ("final", "final_probabilities.png", "P(reach final) — PRIMARY frozen raw B5")):
        p = P0["p"][key][order]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(lab, p, yerr=1.96 * np.sqrt(p * (1 - p) / n), color="#3b6ea5", label="PRIMARY (±1.96 MC SE)")
        if key == "champion":
            ax.scatter(lab, runs["CONSERVATIVE"]["p"][key][order], marker="v", color="grey", zorder=3, label="CONSERVATIVE λ=0.85")
            ax.scatter(lab, runs["AGGRESSIVE"]["p"][key][order], marker="^", color="black", zorder=3, label="AGGRESSIVE λ=1.15")
        ax.set_ylabel("probability")
        ax.set_title(title)
        ax.legend()
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        _save(fig, root, fname)

    o2 = np.argsort(-(P0["p"]["knockout"]))
    fig, ax = plt.subplots(figsize=(10, 5))
    parts = [("direct_knockout", "direct knockout", "#2a9d8f"), ("breakthrough_win", "via breakthrough", "#e9c46a"),
             ("breakthrough_elimination", "eliminated in breakthrough", "#f4a261"),
             ("stage1_elimination", "eliminated in stage 1", "#e76f51")]
    bottom = np.zeros(12)
    for k, l, c in parts:
        ax.bar([ctx.short[i] for i in o2], P0["p"][k][o2], bottom=bottom, label=l, color=c)
        bottom += P0["p"][k][o2]
    ax.set_title("Stage 1 / breakthrough outcome distribution (PRIMARY)")
    ax.legend(fontsize=8)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    _save(fig, root, "stage1_advancement.png")

    fig, ax = plt.subplots(figsize=(11, 5.5))
    bottom = np.zeros(12)
    cmap = plt.get_cmap("viridis", len(E.ELIM_CODES))
    for j, k in enumerate(E.ELIM_CODES):
        v = P0["elim"][k][order]
        ax.bar(lab, v, bottom=bottom, label=k, color=cmap(j))
        bottom += v
    ax.set_title("Path flow: terminal stage distribution (PRIMARY)")
    ax.legend(fontsize=7, ncol=4, loc="upper right")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    _save(fig, root, "path_flow.png")

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(pa.expected_opp_rating, pa.expected_difficulty_per_series, s=3000 * P0["p"]["champion"] + 20, alpha=0.6)
    for i in range(12):
        ax.annotate(ctx.short[i], (pa.expected_opp_rating[i], pa.expected_difficulty_per_series[i]), fontsize=8)
    ax.set_xlabel("expected opponent frozen rating per series played")
    ax.set_ylabel("probability-weighted difficulty (mean 1 - p_win per series)")
    ax.set_title("Path difficulty (bubble area ∝ P(champion)); descriptive")
    _save(fig, root, "path_difficulty.png")

    fig, ax = plt.subplots(figsize=(10, 5.5))
    names = [k for k in runs if k not in ("NEUTRAL_FORMAT", "PRIMARY_INDEPENDENT_SEED")]
    M = np.stack([runs[k]["p"]["champion"][order] for k in names])
    x = np.arange(12)
    ax.vlines(x, M.min(0), M.max(0), color="grey", lw=6, alpha=0.5, label="range over all rule/selection/transform scenarios")
    for k, mk in (("CONSERVATIVE", "v"), ("AGGRESSIVE", "^"), ("BO7_SENSITIVITY", "s")):
        ax.scatter(x, runs[k]["p"]["champion"][order], marker=mk, s=25, label=k)
    ax.scatter(x, P0["p"]["champion"][order], color="red", zorder=3, label="PRIMARY")
    ax.set_xticks(x, lab, rotation=45, ha="right")
    ax.set_ylabel("P(champion)")
    ax.set_title("Championship probability uncertainty ranges")
    ax.legend(fontsize=7)
    _save(fig, root, "uncertainty_ranges.png")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for q, g in conv.groupby("quantity"):
        ax.plot(g.n_sims, g.max_abs_diff_vs_full_1M.clip(lower=1e-6), marker="o", label=f"{q}: max |p(n) - p(1M)|")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("simulations")
    ax.set_ylabel("max absolute difference")
    ax.set_title("Monte Carlo convergence (PRIMARY)")
    ax.legend(fontsize=8)
    _save(fig, root, "monte_carlo_convergence.png")

    for fmt in ("bo5", "bo7"):
        fig, ax = plt.subplots(figsize=(8, 7))
        P = ctx.P.copy()
        np.fill_diagonal(P, np.nan)
        im = ax.imshow(P, cmap="RdBu_r", vmin=0, vmax=1)
        ax.set_xticks(range(12), ctx.short, rotation=60, ha="right", fontsize=8)
        ax.set_yticks(range(12), ctx.short, fontsize=8)
        for i in range(12):
            for j in range(12):
                if i != j:
                    ax.text(j, i, f"{P[i, j]:.2f}", ha="center", va="center", fontsize=6)
        ax.axhline(5.5, color="k", lw=1)
        ax.axvline(5.5, color="k", lw=1)
        fig.colorbar(im, ax=ax, label=f"P(row beats column), {fmt.upper()} (raw B5)")
        ax.set_title(f"{fmt.upper()} matchup matrix — frozen raw B5 (identical for BO5/BO7)")
        _save(fig, root, f"{fmt}_matchup_heatmap.png")
