"""Descriptive 2026 rotation readiness (2026S1 + 2026S2 regular data only; no Annual Finals)."""
import numpy as np
import pandas as pd

from openkpl.history.players import continuity_score
from openkpl.player_model.ratings import PlayerElo

SEASONS_2026 = ("KPL2026S1", "KPL2026S2")


def final_ratings(timeline, cfg):
    elo = PlayerElo(*cfg)
    trace = []
    for s in timeline:
        elo.update_series(s)
        for team in (s["a"], s["b"]):
            for p in s["played"][team]:
                trace.append({"t": s["t"], "season": s["season"], "player_id": p, "team": team, "rating": elo.eff(p)})
    return elo, pd.DataFrame(trace)


def readiness(timeline, hist, elo, method="DECAY"):
    rows = []
    teams = sorted({s[x] for s in timeline if s["season"] in SEASONS_2026 for x in ("a", "b")})
    for team in teams:
        recs = []
        for s in timeline:
            if s["season"] not in SEASONS_2026 or team not in (s["a"], s["b"]) or not s["played"][team]:
                continue
            lineups = [g["lineup"][team] for g in s["games"] if team in g["lineup"]]
            won = s["y"] if team == s["a"] else 1 - s["y"]
            recs.append({"players": len(s["played"][team]), "won": won,
                         "changes": sum(1 for x, y in zip(lineups, lineups[1:]) if x != y),
                         "continuity": continuity_score(lineups), "ids": set(s["played"][team])})
        if not recs:
            continue
        r = pd.DataFrame(recs)
        rot = r[r.players > 5]
        rank = hist.ranking(team, method)
        e = [elo.eff(p) for p in rank]
        core = float(np.mean(e[:5])) if e else np.nan
        bench = float(np.mean(e[5:])) if len(e) > 5 else np.nan
        rows.append({"team_id": team, "series_2026": len(r), "distinct_players_used_2026": len(set().union(*r.ids)),
                     "mean_players_per_series": r.players.mean(), "freq_series_more_than_5_players": (r.players > 5).mean(),
                     "series_with_rotation": len(rot),
                     "win_rate_series_with_rotation": rot.won.mean() if len(rot) else np.nan,
                     "win_rate_series_without_rotation": r[r.players <= 5].won.mean() if (r.players <= 5).any() else np.nan,
                     "mean_lineup_changes_per_series": r.changes.mean(), "mean_roster_continuity": r.continuity.mean(),
                     "core5_mean_rating": core, "player6_rating": e[5] if len(e) > 5 else np.nan,
                     "player7_rating": e[6] if len(e) > 6 else np.nan, "bench_mean_rating": bench,
                     "core_to_bench_gap": core - bench if len(e) > 5 else np.nan,
                     "core_players": "|".join(rank[:5]), "bench_players": "|".join(rank[5:]),
                     "rating_state_as_of": max(s["t"] for s in timeline).strftime("%Y-%m-%d %H:%M"),
                     "note": "descriptive; win rates are in-sample 2026 outcomes; not a prediction of the Annual "
                             "Finals rotation rule (rule not verified)"})
    return pd.DataFrame(rows)
