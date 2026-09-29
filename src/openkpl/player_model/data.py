"""Series timeline with per-game lineups, restricted to the validated v0.3.1 development universe."""
from collections import Counter

import pandas as pd

from openkpl.evaluation.benchmark import PROSPECTIVE_HOLDOUT_START

CANONICAL = "data/processed/temporal/v2026_09_28/canonical_series.parquet"
GAMES = "data/processed/games/kpl_games.parquet"
APPS = "data/processed/games/player_game_appearances.parquet"
BENCH_PRED = "reports/benchmark/v2026_09_28/temporal_predictions.parquet"
ANNUAL_FINALS_2026 = "KPL2026S3"


def dev_universe(canonical):
    c = canonical[canonical.is_label_eligible.astype(bool)].copy()
    c["start_time"] = pd.to_datetime(c.start_time)
    c = c[(c.start_time < PROSPECTIVE_HOLDOUT_START) & (c.season != ANNUAL_FINALS_2026)]
    return c.sort_values(["start_time", "chronological_order", "series_id"], kind="stable").reset_index(drop=True)


def build_timeline(canonical, games, apps):
    """One dict per development series, chronological, with lineups from actual appearances only."""
    c = dev_universe(canonical)
    a = apps[apps.player_id.notna() & (apps.player_id != "") & apps.canonical_team_id.notna()]
    by_game = {k: g for k, g in a.groupby("game_key")}
    winners = dict(zip(games.game_key, games.winner_team_id))
    gnums = games.groupby("series_id").apply(lambda g: sorted(zip(g.game_number, g.game_key)), include_groups=False)
    out = []
    for r in c.itertuples(index=False):
        gl = []
        for n, key in gnums.get(r.series_id, []):
            g = by_game.get(key)
            lineup = {} if g is None else {t: frozenset(x.player_id) for t, x in g.groupby("canonical_team_id")}
            heroes = [] if g is None else [(p, t, None if pd.isna(h) else int(h), None if w is None or pd.isna(w) else bool(w))
                                           for p, t, h, w in zip(g.player_id, g.canonical_team_id, g.hero_id, g.won)]
            w = winners.get(key)
            gl.append({"game_number": int(n), "winner": None if w is None or pd.isna(w) else w,
                       "lineup": lineup, "heroes": heroes})
        played = {t: Counter() for t in (r.canonical_team_a_id, r.canonical_team_b_id)}
        for g in gl:
            for t, ps in g["lineup"].items():
                if t in played:
                    played[t].update(ps)
        out.append({"series_id": r.series_id, "t": r.start_time, "season": r.season, "stage": r.stage,
                    "a": r.canonical_team_a_id, "b": r.canonical_team_b_id, "y": int(r.label_team_a_win),
                    "games": gl, "played": played,
                    "has_lineup": all(len(played[t]) > 0 for t in played)})
    return out


def batches(timeline):
    """Groups of series sharing a start_time; features for a batch see only earlier batches."""
    cur, t = [], None
    for s in timeline:
        if s["t"] != t and cur:
            yield cur
            cur = []
        t = s["t"]
        cur.append(s)
    if cur:
        yield cur


def load(root="."):
    from pathlib import Path
    root = Path(root)
    canonical = pd.read_parquet(root / CANONICAL)
    games = pd.read_parquet(root / GAMES)
    apps = pd.read_parquet(root / APPS)
    return canonical, games, apps
