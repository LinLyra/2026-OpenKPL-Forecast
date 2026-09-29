import pandas as pd


def expected(ra, rb):
    return 1 / (1 + 10 ** ((rb - ra) / 400))


def build_elo(matches: pd.DataFrame, k=24, initial=1500):
    """v0.1 generic Elo over a match frame (team_a, team_b, winner_team).

    Kept for backward compatibility. Rows are ordered by start_time/source_row
    when available; without start_time the order is file order and is NOT
    chronological. Use `build_series_elo` for the temporal baseline.
    """
    ratings = {}
    rows = []
    sort_cols = [c for c in ["start_time", "source_row"] if c in matches.columns]
    data = matches.sort_values(sort_cols) if sort_cols else matches.copy()
    for idx, r in data.iterrows():
        a, b = str(r.team_a), str(r.team_b)
        ra, rb = ratings.get(a, initial), ratings.get(b, initial)
        p = expected(ra, rb)
        winner = str(r.get("winner_team", ""))
        if winner not in (a, b):
            continue
        y = 1.0 if winner == a else 0.0
        rows.append({"row_id": idx, "team_a": a, "team_b": b,
                     "elo_a_pre": ra, "elo_b_pre": rb, "elo_delta_pre": ra - rb,
                     "p_a_elo": p, "y_a": y})
        ratings[a] = ra + k * (y - p)
        ratings[b] = rb + k * ((1 - y) - (1 - p))
    return pd.DataFrame(rows)


def build_series_elo(series: pd.DataFrame, initial=1500.0, k=24.0):
    """Leakage-safe chronological Elo over dated, completed series (v0.2).

    Only `is_completed_labeled` rows are used. Rows are processed in
    (start_time, series_id) order. All series sharing one start_time are
    predicted from the ratings that existed before that timestamp; ratings
    are updated only after the whole timestamp group is predicted.
    """
    d = series[series.is_completed_labeled & series.start_time.notna()]
    d = d.sort_values(["start_time", "series_id"], kind="stable")
    rating = {}
    rows = []
    for ts, grp in d.groupby("start_time", sort=True):
        updates = []
        for _, r in grp.iterrows():
            a, b = str(r.team_a), str(r.team_b)
            ra, rb = rating.get(a, initial), rating.get(b, initial)
            p = expected(ra, rb)
            y = 1.0 if r.winner_team == a else 0.0
            rows.append({"series_id": r.series_id, "start_time": r.start_time, "season": r.get("season"),
                         "team_a": a, "team_b": b, "winner_team": r.winner_team,
                         "elo_a_pre": ra, "elo_b_pre": rb, "elo_delta_pre": ra - rb,
                         "p_team_a": p, "y_team_a": y})
            updates.append((a, b, ra, rb, p, y))
        for a, b, ra, rb, p, y in updates:
            rating[a] = rating.get(a, initial) + k * (y - p)
            rating[b] = rating.get(b, initial) + k * ((1 - y) - (1 - p))
    return pd.DataFrame(rows)
