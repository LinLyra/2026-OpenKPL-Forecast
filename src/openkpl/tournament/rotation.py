"""DESCRIPTIVE — NOT USED IN PRIMARY FORECAST: historical (pre-cutoff) rotation profile of the six Master teams."""
from pathlib import Path

import pandas as pd

from openkpl.evaluation.benchmark import PROSPECTIVE_HOLDOUT_START

ROTATION_2026 = "reports/player_model/rotation_readiness_2026.csv"
SERIES_ROTATION = "data/processed/rosters/series_rotation_summary.parquet"
CANONICAL = "data/processed/temporal/v2026_09_28/canonical_series.parquet"
LABEL = "DESCRIPTIVE — NOT USED IN PRIMARY FORECAST"


def master_rotation(teams, root="."):
    root = Path(root)
    canon = pd.read_parquet(root / CANONICAL)[["series_id", "season", "start_time"]]
    canon["start_time"] = pd.to_datetime(canon.start_time)
    sr = pd.read_parquet(root / SERIES_ROTATION).merge(canon, on="series_id", how="inner")
    sr = sr[sr.start_time < PROSPECTIVE_HOLDOUT_START]
    r26 = pd.read_csv(root / ROTATION_2026).set_index("team_id")
    rows = []
    for t in teams[teams.group == "MASTER"].itertuples(index=False):
        for window, mask in (("2026 (S1+S2)", sr.season.str.startswith("KPL2026")), ("all history 2022S2-2026S2", sr.season.notna())):
            x = sr[(sr.team_id == t.canonical_team_id) & mask]
            row = {"team": t.official_name, "canonical_team_id": t.canonical_team_id, "window": window,
                   "series_observed": len(x),
                   "mean_players_used_per_series": x.unique_players_used.mean(),
                   "freq_series_more_than_5_players": (x.unique_players_used > 5).mean(),
                   "freq_series_at_least_6_players": (x.unique_players_used >= 6).mean(),
                   "freq_series_at_least_7_players": (x.unique_players_used >= 7).mean(),
                   "max_players_used_in_a_series": x.unique_players_used.max(),
                   "lineup_change_frequency": (x.lineup_changes > 0).mean(),
                   "mean_lineup_changes_per_series": x.lineup_changes.mean()}
            if window.startswith("2026") and t.canonical_team_id in r26.index:
                q = r26.loc[t.canonical_team_id]
                row.update({"core5_mean_player_rating": q.core5_mean_rating, "player6_rating": q.player6_rating,
                            "player7_rating": q.player7_rating, "core_to_bench_gap": q.core_to_bench_gap,
                            "player_rating_state_as_of": q.rating_state_as_of})
            row["label"] = LABEL
            row["note"] = ("Historical registered-roster usage only; the Annual Finals 7-player lists (with loans) are "
                           "not used and players 6/7 in the Finals list may differ from the historical players 6/7. "
                           "Player ratings are v0.5 PlayerElo P1 states (v0.5 rejected them as predictors).")
            rows.append(row)
    return pd.DataFrame(rows)
