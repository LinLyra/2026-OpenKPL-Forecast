"""Benchmark figures, generated only from saved artifacts in reports/benchmark/."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ELO_HISTORY_MODEL = "B2"
ELO_HISTORY_TOP_N = 8


def _read(out, name):
    return pd.read_csv(Path(out) / name, encoding="utf-8-sig")


def make_figures(out_dir, fig_dir):
    out, fig = Path(out_dir), Path(fig_dir)
    fig.mkdir(parents=True, exist_ok=True)
    m = _read(out, "temporal_metrics.csv")
    s = _read(out, "season_metrics.csv")
    c = _read(out, "calibration.csv")
    p = pd.read_parquet(out / "temporal_predictions.parquet")
    paths = {}

    f, ax = plt.subplots(1, 2, figsize=(10, 4))
    for a, col, title in [(ax[0], "log_loss", "Log loss (lower is better)"), (ax[1], "brier", "Brier (lower is better)")]:
        a.bar(m.model_id, m[col], color="#4c72b0")
        a.axhline(m.loc[m.model_id == "B0", col].iloc[0], color="grey", ls="--", lw=1, label="B0 coin flip")
        lo, hi = m[col].min(), m[col].max()
        a.set_ylim(lo - (hi - lo) * 0.6 - 1e-3, hi + (hi - lo) * 0.3 + 1e-3)
        for x, v in zip(m.model_id, m[col]):
            a.text(x, v, f"{v:.4f}", ha="center", va="bottom", fontsize=8)
        a.set_title(title); a.legend(fontsize=8)
    f.suptitle(f"Out-of-sample development results (n={int(m.n.iloc[0])} per model)")
    f.tight_layout(); paths["model_comparison"] = fig / "model_comparison.png"; f.savefig(paths["model_comparison"], dpi=130); plt.close(f)

    f, a = plt.subplots(figsize=(6, 6))
    a.plot([0, 1], [0, 1], color="grey", ls="--", lw=1)
    for mid, g in c[c.n > 0].groupby("model_id", sort=False):
        a.plot(g.mean_predicted_p, g.observed_win_rate, marker="o", ms=3, lw=1, label=mid)
    a.set_xlabel("mean predicted P(team_a wins)"); a.set_ylabel("observed team_a win rate")
    a.set_title("Reliability (10 equal-width bins, OOS)"); a.legend(fontsize=8)
    f.tight_layout(); paths["calibration_curve"] = fig / "calibration_curve.png"; f.savefig(paths["calibration_curve"], dpi=130); plt.close(f)

    seasons = list(dict.fromkeys(s.season))
    for col, name in [("brier", "brier_by_season"), ("log_loss", "logloss_by_season")]:
        f, a = plt.subplots(figsize=(10, 4))
        for mid, g in s.groupby("model_id", sort=False):
            g = g.set_index("season").reindex(seasons)
            a.plot(range(len(seasons)), g[col], marker="o", ms=3, lw=1, label=mid)
        a.set_xticks(range(len(seasons))); a.set_xticklabels([x.replace("KPL", "") for x in seasons], rotation=45)
        a.set_ylabel(col); a.set_title(f"{col} by validation season (OOS)"); a.legend(fontsize=8, ncol=6)
        f.tight_layout(); paths[name] = fig / f"{name}.png"; f.savefig(paths[name], dpi=130); plt.close(f)

    e = p[p.model_id == ELO_HISTORY_MODEL]
    long = pd.concat([e[["start_time", "canonical_team_a_id", "pre_match_rating_a"]].set_axis(["t", "team", "r"], axis=1),
                      e[["start_time", "canonical_team_b_id", "pre_match_rating_b"]].set_axis(["t", "team", "r"], axis=1)])
    top = long.team.value_counts().sort_index().sort_values(ascending=False, kind="stable").head(ELO_HISTORY_TOP_N).index
    f, a = plt.subplots(figsize=(11, 5))
    for team in top:
        g = long[long.team == team].sort_values("t")
        a.plot(pd.to_datetime(g.t), g.r, lw=1, label=team)
    a.axhline(1500, color="grey", ls="--", lw=0.8)
    a.set_ylabel("pre-match rating"); a.legend(fontsize=7, ncol=4)
    a.set_title(f"{ELO_HISTORY_MODEL} pre-match Elo, {ELO_HISTORY_TOP_N} teams with most OOS series")
    f.tight_layout(); paths["elo_history"] = fig / "elo_history.png"; f.savefig(paths["elo_history"], dpi=130); plt.close(f)
    return paths
