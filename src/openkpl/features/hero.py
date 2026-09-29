"""Descriptive hero features from the non-temporal WZRY draft corpus.

These are retrospective associations pooled over an undated corpus. They are
not causal effects and are not current-meta or patch-specific estimates.
"""
import math
from collections import defaultdict

import numpy as np
import pandas as pd

ROLES = ["对抗路", "打野", "中路", "发育路", "游走"]
DEFAULT_PRIOR = 20.0


def role_features(lineups):
    """Hero role profile and Hero Flexibility Index (HFI).

    HFI = Shannon entropy of the hero's role shares over the five known roles,
    divided by log(5). Unknown/blank positions are excluded from the shares.
    """
    k = lineups[lineups.position_normalized.isin(ROLES) & lineups.hero.notna()]
    p = k.groupby(["hero", "position_normalized"]).size().rename("n").reset_index()
    p["share"] = p.n / p.groupby("hero").n.transform("sum")
    unknown = (lineups[~lineups.position_normalized.isin(ROLES) & lineups.hero.notna()]
               .groupby("hero").size())
    rows = []
    for h, g in p.groupby("hero"):
        q = g.share.to_numpy(float)
        ent = max(0.0, float(-(q * np.log(q)).sum()))
        rows.append({"hero": h, "known_role_slots": int(g.n.sum()),
                     "unknown_role_slots": int(unknown.get(h, 0)),
                     "roles_observed": len(g),
                     "primary_role": g.sort_values(["n", "position_normalized"], ascending=[False, True]).iloc[0].position_normalized,
                     "primary_role_share": float(g.share.max()),
                     "role_entropy": ent,
                     "hero_flexibility_index": ent / math.log(len(ROLES))})
    return p, pd.DataFrame(rows).sort_values("hero").reset_index(drop=True)


def _shrink(wins, n, prior):
    return (wins + prior * 0.5) / (n + prior)


def synergy(games, lineups, prior=DEFAULT_PRIOR):
    """Same-team hero pair win association, shrunk toward 0.5."""
    winners = games.set_index("draft_game_id").winner_team.to_dict()
    acc = defaultdict(lambda: [0, 0])
    for (gid, team), g in lineups.groupby(["draft_game_id", "team"]):
        hs = sorted(set(g.hero.dropna()))
        won = winners.get(gid) == team
        for i in range(len(hs)):
            for j in range(i + 1, len(hs)):
                acc[(hs[i], hs[j])][0] += 1
                acc[(hs[i], hs[j])][1] += int(won)
    rows = []
    for (a, b), (n, w) in acc.items():
        s = _shrink(w, n, prior)
        rows.append({"hero_a": a, "hero_b": b, "games": n, "wins": w, "raw_win_rate": w / n,
                     "shrunk_win_rate": s, "association_vs_0_5": s - 0.5, "prior_strength": prior})
    return pd.DataFrame(rows).sort_values(["games", "hero_a", "hero_b"], ascending=[False, True, True]).reset_index(drop=True)


def counter(games, lineups, prior=DEFAULT_PRIOR):
    """Directed cross-team hero association: win rate of `hero` when facing `opponent_hero`."""
    winners = games.set_index("draft_game_id").winner_team.to_dict()
    acc = defaultdict(lambda: [0, 0])
    for gid, g in lineups.groupby("draft_game_id"):
        ts = list(g.team.dropna().unique())
        if len(ts) != 2:
            continue
        a, b = ts
        ha = set(g.loc[g.team == a, "hero"].dropna())
        hb = set(g.loc[g.team == b, "hero"].dropna())
        w = winners.get(gid)
        for x in ha:
            for y in hb:
                acc[(x, y)][0] += 1
                acc[(x, y)][1] += int(w == a)
                acc[(y, x)][0] += 1
                acc[(y, x)][1] += int(w == b)
    rows = []
    for (h, o), (n, w) in acc.items():
        s = _shrink(w, n, prior)
        rows.append({"hero": h, "opponent_hero": o, "games": n, "wins": w, "raw_win_rate": w / n,
                     "shrunk_win_rate": s, "association_vs_0_5": s - 0.5, "prior_strength": prior})
    return pd.DataFrame(rows).sort_values(["games", "hero", "opponent_hero"], ascending=[False, True, True]).reset_index(drop=True)
