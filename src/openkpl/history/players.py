"""Player identity registry, series usage/rotation, and strictly temporal player-hero history."""
from collections import defaultdict

import pandas as pd


def ordered(games):
    """Deterministic temporal order: series start time, validated chronological order, game number."""
    return games.sort_values(["series_start_time", "chronological_order", "game_number"]).reset_index(drop=True)


def _team_sequence(df):
    seq = []
    for t in df.canonical_team_id:
        if t and (not seq or seq[-1] != t):
            seq.append(t)
    return seq


def player_registry(apps, games):
    g = games.set_index("game_key")[["series_start_time", "chronological_order", "game_number", "season_id"]]
    a = apps[apps.player_id.notna()].join(g[["series_start_time", "chronological_order"]], on="game_key")
    a = a.sort_values(["series_start_time", "chronological_order", "game_number"])
    handles = a.groupby("player_id").player_handle_derived.apply(lambda s: set(s.dropna()))
    owners = defaultdict(set)
    for pid, hs in handles.items():
        for h in hs:
            owners[h].add(pid)
    rows = []
    for pid, grp in a.groupby("player_id", sort=True):
        seq = _team_sequence(grp)
        hs = sorted(handles[pid])
        related = sorted(set().union(*(owners[h] for h in hs)) - {pid}) if hs else []
        flags = []
        if related:
            flags.append("SAME_HANDLE_DIFFERENT_ID")
        if len(hs) > 1:
            flags.append("MULTIPLE_HANDLES")
        if grp.canonical_team_id.isna().any():
            flags.append("TEAM_UNMAPPED_APPEARANCE")
        if any("." in h for h in hs):
            flags.append("HANDLE_PREFIX_NOT_STRIPPED")
        roles = sorted(set(grp.position_raw.dropna().astype(int)) - {0})
        rows.append({
            "player_id": pid,
            "first_seen": grp.series_start_time.min(), "last_seen": grp.series_start_time.max(),
            "first_season": grp.season_id.iloc[0], "last_season": grp.season_id.iloc[-1],
            "games_observed": int(grp.game_key.nunique()), "series_observed": int(grp.series_id.nunique()),
            "teams_observed": "|".join(sorted(set(grp.canonical_team_id.dropna()))),
            "team_sequence": ">".join(seq), "transfer_count": max(len(seq) - 1, 0),
            "seasons_observed": "|".join(sorted(set(grp.season_id))),
            "name_variants": "|".join(sorted(set(grp.player_name_raw.dropna()))),
            "handle_variants": "|".join(hs), "roles_observed": "|".join(map(str, roles)),
            "related_player_ids": "|".join(related),
            "identity_status": "REVIEW_REQUIRED" if related else "SOURCE_ID_STABLE",
            "quality_flags": "|".join(flags),
        })
    return pd.DataFrame(rows)


def identity_candidates(apps, games, registry):
    """Pairwise evidence for players sharing a derived handle (never merged)."""
    g = games.set_index("game_key")
    a = apps[apps.player_id.notna()].join(g[["series_start_time"]], on="game_key")
    rows = []
    for _, r in registry[registry.related_player_ids != ""].iterrows():
        for other in r.related_player_ids.split("|"):
            if other < r.player_id:
                continue
            x, y = a[a.player_id == r.player_id], a[a.player_id == other]
            shared_handles = sorted(set(x.player_handle_derived.dropna()) & set(y.player_handle_derived.dropna()))
            same_game = sorted(set(x.game_key) & set(y.game_key))
            same_series = sorted(set(x.series_id) & set(y.series_id))
            same_day = sorted(set(x.series_start_time.dt.date) & set(y.series_start_time.dt.date))
            overlap = not (x.series_start_time.max() < y.series_start_time.min() or y.series_start_time.max() < x.series_start_time.min())
            if same_game:
                verdict = "DIFFERENT_PEOPLE (appear in the same game)"
            elif same_series:
                verdict = "LIKELY_DIFFERENT_PEOPLE (appear in the same series)"
            elif overlap:
                verdict = "UNRESOLVED (active periods overlap; never in the same series)"
            else:
                verdict = "SOURCE_ID_MIGRATION_PLAUSIBLE (disjoint active periods); not merged"
            rows.append({
                "player_id_a": r.player_id, "player_id_b": other, "shared_handles": "|".join(shared_handles),
                "a_first_seen": x.series_start_time.min(), "a_last_seen": x.series_start_time.max(),
                "b_first_seen": y.series_start_time.min(), "b_last_seen": y.series_start_time.max(),
                "a_seasons": "|".join(sorted(set(x.season_id))), "b_seasons": "|".join(sorted(set(y.season_id))),
                "a_teams": "|".join(sorted(set(x.canonical_team_id.dropna()))),
                "b_teams": "|".join(sorted(set(y.canonical_team_id.dropna()))),
                "a_games": int(x.game_key.nunique()), "b_games": int(y.game_key.nunique()),
                "active_periods_overlap": overlap, "same_day_series": len(same_day),
                "same_series_count": len(same_series), "same_game_count": len(same_game),
                "a_names": "|".join(sorted(set(x.player_name_raw.dropna()))),
                "b_names": "|".join(sorted(set(y.player_name_raw.dropna()))),
                "assessment": verdict, "merged": False,
            })
    return pd.DataFrame(rows)


def series_usage(apps):
    a = apps[apps.player_id.notna() & apps.canonical_team_id.notna()]
    rows = []
    for (sid, team, pid), grp in a.groupby(["series_id", "canonical_team_id", "player_id"]):
        nums = sorted(grp.game_number)
        rows.append({
            "series_id": sid, "canonical_team_id": team, "player_id": pid, "games_played": len(nums),
            "first_game_played": nums[0], "last_game_played": nums[-1],
            "roles_observed": "|".join(map(str, sorted(set(grp.position_raw.dropna().astype(int)) - {0}))),
            "heroes_used": "|".join(map(str, sorted(set(grp.hero_id.dropna().astype(int))))),
            "started_game1": nums[0] == 1, "entered_after_game1": nums[0] > 1,
        })
    return pd.DataFrame(rows)


def continuity_score(lineups):
    """lineups: list of frozensets ordered by game number.
    score = mean over games g=2..N of |L_g ∩ L_1| / |L_1|; 1.0 when only one game."""
    if len(lineups) < 2 or not lineups[0]:
        return 1.0 if lineups else None
    base = lineups[0]
    return sum(len(l & base) / len(base) for l in lineups[1:]) / (len(lineups) - 1)


def rotation_summary(apps):
    a = apps[apps.player_id.notna() & apps.canonical_team_id.notna()]
    rows = []
    for (sid, team), grp in a.groupby(["series_id", "canonical_team_id"]):
        lu = grp.groupby("game_number").player_id.apply(frozenset).sort_index()
        ls = list(lu)
        base = ls[0]
        later = set().union(*ls[1:]) if len(ls) > 1 else set()
        rows.append({
            "series_id": sid, "team_id": team, "games": len(ls),
            "unique_players_used": len(set().union(*ls)),
            "lineup_changes": sum(1 for x, y in zip(ls, ls[1:]) if x != y),
            "players_added_after_game1": len(later - base),
            "players_removed_after_game1": len(base - set().union(*ls[1:])) if len(ls) > 1 else 0,
            "distinct_lineups": len(set(ls)), "roster_continuity_score": continuity_score(ls),
            "complete_5_player_lineups": all(len(x) == 5 for x in ls),
        })
    return pd.DataFrame(rows)


class _Counter:
    def __init__(self):
        self.n, self.w, self.d = defaultdict(int), defaultdict(int), defaultdict(int)

    def get(self, k):
        if k is None:
            return None, None, None
        n, w, d = self.n[k], self.w[k], self.d[k]
        return n, w, (w / d if d else None)

    def add(self, k, won):
        if k is None:
            return
        self.n[k] += 1
        if won is not None:
            self.d[k] += 1
            self.w[k] += int(bool(won))


def _hero(r):
    return None if r.hero_id is None or pd.isna(r.hero_id) else int(r.hero_id)


KEYS = {
    "player_hero": lambda r: (r.player_id, _hero(r)) if _hero(r) is not None else None,
    "player": lambda r: r.player_id,
    "hero": _hero,
    "team_hero": lambda r: (r.canonical_team_id, _hero(r)) if _hero(r) is not None else None,
}


def player_hero_temporal(apps, games):
    """Per appearance, stats from strictly earlier games (`*_prior_*`) and from earlier series only (`*_preseries_*`).

    Ordering: series_start_time, chronological_order, game_number. Games with unknown winner count toward
    `*_games` but not toward wins/decided; winrate = wins / decided games.
    """
    og = ordered(games)
    rank = {k: i for i, k in enumerate(og.game_key)}
    a = apps[apps.player_id.notna() & apps.canonical_team_id.notna()].copy()
    a["temporal_rank"] = a.game_key.map(rank)
    a = a.sort_values(["temporal_rank", "canonical_team_id", "player_id"]).reset_index(drop=True)
    game_state = {k: _Counter() for k in KEYS}
    series_state = {k: _Counter() for k in KEYS}
    pending, current_series = [], None
    out = []
    for _, grp in a.groupby("temporal_rank", sort=True):
        sid = grp.series_id.iloc[0]
        if sid != current_series:
            for name, key, won in pending:
                series_state[name].add(key, won)
            pending, current_series = [], sid
        rows = list(grp.itertuples(index=False))
        for r in rows:
            rec = {"game_key": r.game_key, "series_id": r.series_id, "game_number": r.game_number,
                   "canonical_team_id": r.canonical_team_id, "player_id": r.player_id, "hero_id": r.hero_id,
                   "won": r.won, "temporal_rank": r.temporal_rank}
            for name, fn in KEYS.items():
                k = fn(r)
                n, w, wr = game_state[name].get(k)
                rec.update({f"{name}_prior_games": n, f"{name}_prior_wins": w, f"{name}_prior_winrate": wr})
                n, w, wr = series_state[name].get(k)
                rec.update({f"{name}_preseries_games": n, f"{name}_preseries_wins": w, f"{name}_preseries_winrate": wr})
            out.append(rec)
        for r in rows:
            for name, fn in KEYS.items():
                k = fn(r)
                game_state[name].add(k, r.won)
                pending.append((name, k, r.won))
    return pd.DataFrame(out)
