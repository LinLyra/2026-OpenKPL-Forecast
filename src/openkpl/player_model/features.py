"""Pre-series team features from strictly earlier series, plus separately labeled oracle features.

A series at start_time t sees only series with start_time < t (batch = identical
start_time). Nothing from the target series enters a PRE_SERIES_SAFE feature.

Expected-core methods (rank the team's candidate pool; core = top 5, bench = rank 6+):
  FREQ5  games played for the team over its last 5 series
  DECAY  sum_j games_j * 0.5 ** (j / 3) over the last 20 series (j = 0 is the most recent)
  LAST   games in the team's last series
  HIST   games over all earlier series of the team
Ties: DECAY score, then player_id. The pool is every player who appeared for the team
in its last 10 series (all series for HIST) and whose most recent appearance anywhere
before t was for this team.
"""
import math
from collections import Counter, defaultdict

import numpy as np

from openkpl.player_model.data import batches

CORE_METHODS = ["FREQ5", "DECAY", "LAST", "HIST"]
POOL_SERIES = 10
DECAY_HALF_LIFE = 3.0
MIN_HERO_GAMES = 3
WR_SHRINK = 5.0

RATING_FEATURES = ["expected_core_strength", "top5_player_rating_mean", "top5_player_rating_sum",
                   "recent_player_rating_mean", "player_rating_max", "player_rating_min", "player_rating_std"]
BENCH_RATING_FEATURES = ["player6_rating", "player7_rating", "bench_mean_rating", "bench_gap_to_core"]
ROSTER_FEATURES = ["returning_players_from_previous_series", "core5_overlap_previous_series",
                   "rolling_unique_players_used", "rolling_lineup_changes", "rolling_rotation_rate",
                   "roster_stability_3_series", "roster_stability_5_series", "roster_stability_10_series",
                   "days_since_player_last_appearance", "days_since_team_last_series", "new_player_count",
                   "recently_returned_player_count", "is_first_series_of_season"]
BENCH_HIST_FEATURES = ["historical_substitution_frequency", "historical_performance_when_rotating",
                       "historical_number_of_players_used"]
HERO_FEATURES = ["player_hero_experience_depth", "player_hero_diversity", "weighted_player_hero_winrate",
                 "weighted_player_hero_games", "team_hero_depth", "hero_pool_concentration"]
ORACLE_RATING = ["oracle_actual_lineup_rating_mean", "oracle_actual_lineup_rating_min",
                 "oracle_actual_lineup_rating_max"]
ORACLE_ROTATION = ["oracle_unique_players_used", "oracle_lineup_changes", "oracle_players_entered_after_game1"]


def _mean(x):
    return float(np.mean(x)) if len(x) else math.nan


def _lineup_changes(lineups):
    return sum(1 for x, y in zip(lineups, lineups[1:]) if x != y)


class History:
    """Mutable pre-series state, updated only after a whole batch has been featurized."""

    def __init__(self):
        self.team = defaultdict(list)
        self.player_last = {}
        self.ph = defaultdict(Counter)
        self.ph_w = defaultdict(Counter)
        self.ph_d = defaultdict(Counter)

    def add(self, s):
        for side, team in (("a", s["a"]), ("b", s["b"])):
            played = s["played"][team]
            if not played:
                continue
            lineups = [g["lineup"][team] for g in s["games"] if team in g["lineup"]]
            won = s["y"] if side == "a" else 1 - s["y"]
            self.team[team].append({"t": s["t"], "season": s["season"], "series_id": s["series_id"],
                                    "played": Counter(played), "unique": len(played),
                                    "changes": _lineup_changes(lineups), "won": won,
                                    "heroes": Counter()})
            for p in played:
                self.player_last[p] = (s["t"], team)
        for g in s["games"]:
            for p, team, h, w in g["heroes"]:
                if h is None:
                    continue
                self.ph[p][h] += 1
                if w is not None:
                    self.ph_d[p][h] += 1
                    self.ph_w[p][h] += int(w)
                rec = self.team.get(team)
                if rec and rec[-1]["series_id"] == s["series_id"]:
                    rec[-1]["heroes"][h] += 1

    def ranking(self, team, method):
        hist = self.team.get(team, [])
        if not hist:
            return []
        window = hist if method == "HIST" else hist[-POOL_SERIES:]
        pool = {p for r in window for p in r["played"] if self.player_last.get(p, (None, None))[1] == team}
        recent = hist[-20:][::-1]
        decay = Counter()
        for j, r in enumerate(recent):
            for p, n in r["played"].items():
                decay[p] += n * 0.5 ** (j / DECAY_HALF_LIFE)
        if method == "DECAY":
            score = decay
        elif method == "FREQ5":
            score = sum((r["played"] for r in hist[-5:]), Counter())
        elif method == "LAST":
            score = hist[-1]["played"]
        else:
            score = sum((r["played"] for r in hist), Counter())
        return sorted(pool, key=lambda p: (-score.get(p, 0), -decay.get(p, 0.0), p))

    def roster_features(self, team, t, season, core):
        hist = self.team.get(team, [])
        f = dict.fromkeys(ROSTER_FEATURES + BENCH_HIST_FEATURES, math.nan)
        f["is_first_series_of_season"] = float(not hist or hist[-1]["season"] != season)
        if not hist:
            return f
        last = hist[-1]
        lp = set(last["played"])
        if len(hist) >= 2:
            f["returning_players_from_previous_series"] = len(lp & set(hist[-2]["played"]))
        f["core5_overlap_previous_series"] = len(set(core) & lp)
        w5, w10 = hist[-5:], hist[-10:]
        f["rolling_unique_players_used"] = _mean([r["unique"] for r in w5])
        f["rolling_lineup_changes"] = _mean([r["changes"] for r in w5])
        f["rolling_rotation_rate"] = _mean([r["unique"] > 5 for r in w5])
        for k in (3, 5, 10):
            c = sum((r["played"] for r in hist[-k:]), Counter())
            tot = sum(c.values())
            f[f"roster_stability_{k}_series"] = sum(n for _, n in c.most_common(5)) / tot if tot else math.nan
        days = [(t - self.player_last[p][0]).total_seconds() / 86400 for p in core if p in self.player_last]
        f["days_since_player_last_appearance"] = _mean(days)
        f["days_since_team_last_series"] = (t - last["t"]).total_seconds() / 86400
        before = set().union(*[set(r["played"]) for r in hist[:-1]]) if len(hist) > 1 else set()
        f["new_player_count"] = len(lp - before)
        gap = set().union(*[set(r["played"]) for r in hist[-4:-1]]) if len(hist) > 1 else set()
        f["recently_returned_player_count"] = len((lp & before) - gap)
        f["historical_substitution_frequency"] = _mean([r["changes"] > 0 for r in w10])
        rot = [r["won"] for r in hist[-20:] if r["unique"] > 5]
        f["historical_performance_when_rotating"] = (sum(rot) + 0.5 * WR_SHRINK) / (len(rot) + WR_SHRINK)
        f["historical_number_of_players_used"] = _mean([r["unique"] for r in w10])
        return f

    def hero_features(self, team, core):
        f = dict.fromkeys(HERO_FEATURES, math.nan)
        hist = self.team.get(team, [])
        if not core:
            return f
        depth, div, wr, games, hhi = [], [], [], [], []
        for p in core:
            c = self.ph.get(p, Counter())
            tot = sum(c.values())
            depth.append(sum(1 for n in c.values() if n >= MIN_HERO_GAMES))
            games.append(tot)
            if tot:
                q = np.array(list(c.values()), float) / tot
                div.append(float(-(q * np.log(q)).sum()))
                hhi.append(float((q ** 2).sum()))
                d, w = self.ph_d[p], self.ph_w[p]
                wr.append(sum(n * (w[h] + 0.5 * WR_SHRINK) / (d[h] + WR_SHRINK) for h, n in c.items()) / tot)
        f["player_hero_experience_depth"] = _mean(depth)
        f["player_hero_diversity"] = _mean(div)
        f["weighted_player_hero_winrate"] = _mean(wr)
        f["weighted_player_hero_games"] = _mean(games)
        f["hero_pool_concentration"] = _mean(hhi)
        if hist:
            th = sum((r["heroes"] for r in hist[-POOL_SERIES:]), Counter())
            f["team_hero_depth"] = sum(1 for n in th.values() if n >= MIN_HERO_GAMES)
        return f


def history_pass(timeline):
    """Config-independent pass. Returns (rankings, static):
    rankings[(series_id, team)][method] -> ordered pool; static[(series_id, method)] -> feature dict."""
    h = History()
    rankings, static = {}, {}
    for batch in batches(timeline):
        for s in batch:
            for side in ("a", "b"):
                team = s[side]
                ranks = {m: h.ranking(team, m) for m in CORE_METHODS}
                rankings[(s["series_id"], team)] = ranks
                for m in CORE_METHODS:
                    core = ranks[m][:5]
                    f = h.roster_features(team, s["t"], s["season"], core)
                    f.update(h.hero_features(team, core))
                    static.setdefault((s["series_id"], m), {}).update({f"{k}_{side}": v for k, v in f.items()})
        for s in batch:
            h.add(s)
    return rankings, static, h


def rating_features(rank, elo, last_played):
    f = dict.fromkeys(RATING_FEATURES + BENCH_RATING_FEATURES, math.nan)
    if not rank:
        return f
    e = [elo.eff(p) for p in rank]
    core = e[:5]
    f["expected_core_strength"] = _mean(core)
    top = sorted(e, reverse=True)[:5]
    f["top5_player_rating_mean"] = _mean(top)
    f["top5_player_rating_sum"] = float(sum(top))
    f["recent_player_rating_mean"] = _mean([elo.eff(p) for p in last_played]) if last_played else math.nan
    f["player_rating_max"], f["player_rating_min"] = max(core), min(core)
    f["player_rating_std"] = float(np.std(core))
    if len(e) > 5:
        f["player6_rating"] = e[5]
        f["bench_mean_rating"] = _mean(e[5:])
        f["bench_gap_to_core"] = f["expected_core_strength"] - f["bench_mean_rating"]
    if len(e) > 6:
        f["player7_rating"] = e[6]
    return f


def oracle_features(s, team, elo):
    played = s["played"][team]
    f = dict.fromkeys(ORACLE_RATING + ORACLE_ROTATION, math.nan)
    if not played:
        return f
    w = np.array(list(played.values()), float)
    e = np.array([elo.eff(p) for p in played])
    f["oracle_actual_lineup_rating_mean"] = float((w * e).sum() / w.sum())
    f["oracle_actual_lineup_rating_min"], f["oracle_actual_lineup_rating_max"] = float(e.min()), float(e.max())
    lineups = [g["lineup"][team] for g in s["games"] if team in g["lineup"]]
    f["oracle_unique_players_used"] = len(played)
    f["oracle_lineup_changes"] = _lineup_changes(lineups)
    f["oracle_players_entered_after_game1"] = len(set(played) - set(lineups[0])) if lineups else math.nan
    return f


def rating_pass(timeline, rankings, elo, methods=CORE_METHODS):
    """Runs one rating configuration; returns {method: {series_id: features}} and {series_id: oracle}."""
    out = {m: {} for m in methods}
    oracle = {}
    last = {}
    for batch in batches(timeline):
        for s in batch:
            sid = s["series_id"]
            for m in methods:
                row = {}
                for side in ("a", "b"):
                    team = s[side]
                    row.update({f"{k}_{side}": v for k, v in
                                rating_features(rankings[(sid, team)][m], elo, last.get(team, ())).items()})
                out[m][sid] = row
            oracle[sid] = {f"{k}_{side}": v for side in ("a", "b")
                           for k, v in oracle_features(s, s[side], elo).items()}
            oracle[sid]["oracle_players_a"] = sorted(s["played"][s["a"]])
            oracle[sid]["oracle_players_b"] = sorted(s["played"][s["b"]])
        for s in batch:
            elo.update_series(s)
            for side in ("a", "b"):
                if s["played"][s[side]]:
                    last[s[side]] = tuple(s["played"][s[side]])
    return out, oracle
