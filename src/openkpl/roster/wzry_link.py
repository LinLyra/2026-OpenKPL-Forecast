"""Exact-fingerprint linkage feasibility between WZRY.csv game rows and kplow games.

No fuzzy matching: hero and team strings must be byte-identical (team names are
only mapped to canonical IDs through exact `observed_name` rows of the verified
registry).  Results are diagnostics, never a join written back to either source.
"""
import ast
from collections import Counter

import pandas as pd

LEVELS = ["F1_team_pair", "F2_pair_hero10", "F3_pair_team_heroes", "F3W_pair_team_heroes_winner",
          "D1_hero10", "D2_hero_sides"]
UNTESTABLE = {
    "F4_pair_ordered_bp": "kplow has no ban records and pick order only via getSeasonHeroComboMatches (2026 seasons only)",
    "F5_pair_ordered_bp_final_heroes": "requires F4",
    "equipment": "kplow getScheduleDetail has no equipment field",
}


def wzry_games(df):
    """One record per WZRY row: team names, winner name, per-team hero sets (from battle_process)."""
    out = []
    for i, r in df.iterrows():
        rec = {"wzry_row": int(i), "team1": r.team1, "team2": r.team2,
               "winner": r.team1 if str(r.team1_win) == "True" else (r.team2 if str(r.team2_win) == "True" else "")}
        heroes = {r.team1: set(), r.team2: set()}
        try:
            for e in ast.literal_eval(r.battle_process):
                heroes.setdefault(e["team"], set()).add(e["hero"])
        except (ValueError, SyntaxError):
            rec["parse_error"] = True
        rec["heroes1"], rec["heroes2"] = frozenset(heroes.get(r.team1, ())), frozenset(heroes.get(r.team2, ()))
        out.append(rec)
    return pd.DataFrame(out)


def kplow_games(game_players, games, slot_names):
    """One record per (scheduleid, round) with team names, winner name, per-team hero sets."""
    gp = pd.DataFrame(game_players)
    g = pd.DataFrame(games).set_index(["scheduleid", "round"])
    out = []
    for (sid, rnd), grp in gp.groupby(["scheduleid", "round"]):
        teams = sorted(t for t in grp.team_slot.unique())
        if len(teams) != 2:
            continue
        hs = [frozenset(grp[grp.team_slot == t].hero_name) for t in teams]
        win_slot = g.loc[(sid, rnd), "win_team_slot"] if (sid, rnd) in g.index else ""
        out.append({"scheduleid": sid, "round": int(rnd), "team1": slot_names.get(teams[0], teams[0]),
                    "team2": slot_names.get(teams[1], teams[1]), "winner": slot_names.get(win_slot, win_slot),
                    "heroes1": hs[0], "heroes2": hs[1]})
    return pd.DataFrame(out)


def fingerprint(rec, level, canon):
    """Exact fingerprint or None when the record lacks the required fields."""
    h1, h2 = rec["heroes1"], rec["heroes2"]
    sides_ok = len(h1) == 5 and len(h2) == 5
    if level == "D1_hero10":
        return frozenset(h1 | h2) if len(h1 | h2) == 10 else None
    if level == "D2_hero_sides":
        return frozenset([h1, h2]) if sides_ok else None
    t1, t2 = canon.get(rec["team1"]), canon.get(rec["team2"])
    if not (t1 and t2):
        return None
    pair = frozenset([t1, t2])
    if level == "F1_team_pair":
        return pair
    if level == "F2_pair_hero10":
        return (pair, frozenset(h1 | h2)) if len(h1 | h2) == 10 else None
    if not sides_ok:
        return None
    key = frozenset([(t1, h1), (t2, h2)])
    if level == "F3_pair_team_heroes":
        return key
    if level == "F3W_pair_team_heroes_winner":
        w = canon.get(rec["winner"]) if rec["winner"] else None
        return (key, w) if w else None
    raise ValueError(level)


def match_counts(left, right, level, canon):
    """For each left record, count right records with an identical fingerprint."""
    rk = Counter(k for k in (fingerprint(r, level, canon) for _, r in right.iterrows()) if k is not None)
    lk = [fingerprint(r, level, canon) for _, r in left.iterrows()]
    tested = [k for k in lk if k is not None]
    within = Counter(tested)
    return {
        "level": level, "rows_total": len(lk), "sample_rows_tested": len(tested),
        "unique_exact_match": sum(1 for k in tested if rk.get(k, 0) == 1),
        "multiple_matches": sum(1 for k in tested if rk.get(k, 0) > 1),
        "no_match": sum(1 for k in tested if rk.get(k, 0) == 0),
        "fingerprint_not_unique_within_source": sum(1 for k in tested if within[k] > 1),
    }


def matched_pairs(left, right, level, canon):
    idx = {}
    for _, r in right.iterrows():
        k = fingerprint(r, level, canon)
        if k is not None:
            idx.setdefault(k, []).append((r["scheduleid"], r["round"]))
    rows = []
    for _, r in left.iterrows():
        k = fingerprint(r, level, canon)
        hits = idx.get(k, []) if k is not None else []
        rows.append({"wzry_row": r["wzry_row"], "level": level, "n_candidates": len(hits),
                     "candidate": f"{hits[0][0]}#{hits[0][1]}" if len(hits) == 1 else ""})
    return pd.DataFrame(rows)
