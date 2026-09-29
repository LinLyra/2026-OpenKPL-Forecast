"""Sequential game-level team Elo (G1-G4) with separate PRE-SERIES and LIVE-SERIES predictions.

Before each series (at its start_time):
  decay (G2):           R <- 1500 + (R - 1500) * 0.5 ** (days_since_team_last_series / half_life)
  season reversion (G3, G4): on a team's first series of a new season, R <- 1500 + rho (R - 1500)
Pre-series ratings ra0, rb0 are frozen at this point.

For game k of the series (games with a known winner only):
  PRE-SERIES  p_pre  = 1 / (1 + 10 ** ((rb0 - ra0) / 400))   -- uses no game of the current series
  LIVE-SERIES p_live = 1 / (1 + 10 ** ((rb - ra) / 400))     -- ratings after games 1..k-1 of this series
Updates:
  G1-G3 (per game):   R_a += K (y_k - p_live), R_b -= same, immediately after game k
  G4 (series-aware):  all games are scored against the frozen pre-series ratings and applied once
                      at series end: R_a += K * sum_k (y_k - p_pre); so p_live == p_pre for G4.
Games with an unknown winner produce no prediction row and no update.
"""
import math

import pandas as pd

BASE, SCALE = 1500.0, 400.0


def expect(ra, rb):
    return 1.0 / (1.0 + 10 ** ((rb - ra) / SCALE))


class GameElo:
    def __init__(self, k=24.0, half_life_days=math.inf, rho=1.0, series_aware=False):
        self.k, self.h, self.rho, self.series_aware = float(k), float(half_life_days), float(rho), bool(series_aware)
        self.R, self.last_t, self.season = {}, {}, {}

    def _prepare(self, team, t, season):
        r = self.R.get(team, BASE)
        if team in self.last_t and not math.isinf(self.h):
            days = (t - self.last_t[team]).total_seconds() / 86400
            r = BASE + (r - BASE) * 0.5 ** (days / self.h)
        if team in self.season and self.season[team] != season:
            r = BASE + self.rho * (r - BASE)
        self.R[team], self.last_t[team], self.season[team] = r, t, season

    def play_series(self, s):
        """Returns per-game rows; mutates state only after each game's prediction is recorded."""
        a, b = s["a"], s["b"]
        self._prepare(a, s["t"], s["season"])
        self._prepare(b, s["t"], s["season"])
        ra0, rb0 = self.R[a], self.R[b]
        rows, acc, wa, wb, prev = [], 0.0, 0, 0, 0
        for g in s["games"]:
            if g["winner_side"] is None:
                continue
            p_pre = expect(ra0, rb0)
            p_live = p_pre if self.series_aware else expect(self.R[a], self.R[b])
            y = 1 if g["winner_side"] == "a" else 0
            rows.append({"game_key": g["game_key"], "series_id": s["series_id"], "game_number": g["game_number"],
                         "p_pre": p_pre, "p_live": p_live, "y": y, "wins_a_before": wa, "wins_b_before": wb,
                         "prev_winner": prev, "rating_a_pre": ra0, "rating_b_pre": rb0})
            if self.series_aware:
                acc += y - p_pre
            else:
                d = self.k * (y - p_live)
                self.R[a] += d
                self.R[b] -= d
            wa, wb, prev = wa + y, wb + (1 - y), (1 if y else -1)
        if self.series_aware:
            self.R[a] += self.k * acc
            self.R[b] -= self.k * acc
        return rows, expect(ra0, rb0)


def run(timeline, params):
    elo = GameElo(**params)
    games, series = [], []
    for s in timeline:
        rows, p0 = elo.play_series(s)
        games += rows
        series.append({"series_id": s["series_id"], "p_game_pre": p0})
    return pd.DataFrame(games), pd.DataFrame(series)
