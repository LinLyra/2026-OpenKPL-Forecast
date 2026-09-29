"""Global deterministic linkage of WZRY.csv rows to kplow games (WZRY.csv is read, never written).

Matching keys use only team identity (exact registry names) and heroes. The winner and the
WZRY row order are never used for matching; the winner is compared only after linkage.
Uniqueness is evaluated against the entire candidate universe in one index (no season filter,
because WZRY carries no date).
"""
import hashlib
from collections import Counter, defaultdict

import pandas as pd

from openkpl.roster.wzry_link import wzry_games

LEVELS = ["F1", "F2", "F3"]
LEVEL_DESC = {
    "F1": "canonical team pair",
    "F2": "canonical team pair + the two unordered five-hero sets (not attributed to teams)",
    "F3": "canonical team pair + team-specific five-hero sets",
    "F4": "team pair + hero-role assignments (NOT APPLICABLE: kplow roles are unlabeled before 2025S3 and WZRY rows end by 2024S1)",
}


def row_hash(row):
    s = "\x1f".join(str(row[c]) for c in ["team1", "team1_win", "team2", "team2_win", "battle_process", "BP_process"])
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def fp(team1, team2, h1, h2, level):
    if not (team1 and team2):
        return None
    pair = frozenset([team1, team2])
    if level == "F1":
        return pair
    if len(h1) != 5 or len(h2) != 5:
        return None
    if level == "F2":
        return (pair, frozenset([h1, h2]))
    if level == "F3":
        return frozenset([(team1, h1), (team2, h2)])
    raise ValueError(level)


def kplow_candidates(apps, games):
    """One record per game with exactly two mapped teams of five players each."""
    a = apps[apps.canonical_team_id.notna()]
    heroes = a.groupby(["game_key", "canonical_team_id"]).hero_name.apply(frozenset)
    g = games.set_index("game_key")
    out = []
    for key, grp in heroes.groupby(level=0):
        teams = sorted(grp.index.get_level_values(1))
        if len(teams) != 2:
            continue
        out.append({"game_key": key, "team1": teams[0], "team2": teams[1],
                    "heroes1": grp[(key, teams[0])], "heroes2": grp[(key, teams[1])],
                    "winner": g.loc[key, "winner_team_id"]})
    return pd.DataFrame(out)


def link(wzry_df, cand, canon_names, games):
    """Return per-row linkage (one row per WZRY row)."""
    idx = {lvl: defaultdict(list) for lvl in LEVELS}
    for r in cand.itertuples(index=False):
        for lvl in LEVELS:
            k = fp(r.team1, r.team2, r.heroes1, r.heroes2, lvl)
            if k is not None:
                idx[lvl][k].append(r.game_key)
    w = wzry_games(wzry_df)
    g = games.set_index("game_key")
    cw = cand.set_index("game_key")
    rows = []
    for (i, raw), rec in zip(wzry_df.iterrows(), w.itertuples(index=False)):
        t1, t2 = canon_names.get(rec.team1), canon_names.get(rec.team2)
        flags = []
        if len(rec.heroes1) != 5 or len(rec.heroes2) != 5:
            flags.append("WZRY_TEAM_HERO_COUNT_NOT_5")
        if str(raw.team1_win) == str(raw.team2_win):
            flags.append("WZRY_WIN_FLAGS_NOT_COMPLEMENTARY")
        counts, cands = {}, {}
        for lvl in LEVELS:
            k = fp(t1, t2, rec.heroes1, rec.heroes2, lvl)
            hits = idx[lvl].get(k, []) if k is not None else []
            counts[lvl], cands[lvl] = (len(hits) if k is not None else None), hits
        winner_w = canon_names.get(rec.winner) if rec.winner else None
        if not (t1 and t2):
            status, level, hits = "UNRESOLVED_TEAM_IDENTITY", None, []
        elif counts["F3"] == 1:
            status, hits = "UNIQUE_EXACT_MATCH", cands["F3"]
            level = next(l for l in LEVELS if counts[l] == 1)
        elif counts["F3"] and counts["F3"] > 1:
            status, level, hits = "MULTIPLE_EXACT_MATCHES", "F3", cands["F3"]
        else:
            status, level, hits = "NO_MATCH", None, []
        key = hits[0] if len(hits) == 1 else None
        winner_k = g.loc[key, "winner_team_id"] if key else None
        winner_k = None if winner_k is None or pd.isna(winner_k) else winner_k
        rows.append({
            "wzry_row_id": int(i), "wzry_row_hash": row_hash(raw), "linkage_status": status,
            "series_id": g.loc[key, "series_id"] if key else None, "game_key": key,
            "game_number": int(g.loc[key, "game_number"]) if key else None,
            "season": g.loc[key, "season_id"] if key else None,
            "date": g.loc[key, "series_start_time"].date().isoformat() if key else None,
            "team1_raw": rec.team1, "team2_raw": rec.team2,
            "team1_canonical_id": t1, "team2_canonical_id": t2,
            "fingerprint_level": level, "candidate_count": counts["F3"],
            "candidate_count_F1": counts["F1"], "candidate_count_F2": counts["F2"],
            "candidates": "|".join(hits[:20]),
            "winner_wzry": winner_w, "winner_kplow": winner_k,
            "winner_agreement": winner_class(winner_w, winner_k) if key else None,
            "quality_flags": "|".join(flags),
        })
    out = pd.DataFrame(rows)
    dup = out[out.game_key.notna()].game_key.value_counts()
    many = set(dup[dup > 1].index)
    for mask, flag in [(out.game_key.isin(many), "GAME_CLAIMED_BY_MULTIPLE_WZRY_ROWS"),
                       (out.winner_agreement == "CONTRADICTION", "WINNER_CONTRADICTION")]:
        out.loc[mask, "quality_flags"] = out.loc[mask, "quality_flags"].map(lambda s: f"{s}|{flag}" if s else flag)
        out.loc[mask, "linkage_status"] = "SOURCE_CONFLICT"
    return out


def winner_class(w, k):
    w = None if w is None or pd.isna(w) else w
    k = None if k is None or pd.isna(k) else k
    if w is None and k is None:
        return "BOTH_MISSING"
    if k is None:
        return "KPL_WINNER_MISSING"
    if w is None:
        return "WZRY_WINNER_MISSING"
    return "AGREE" if w == k else "CONTRADICTION"


def summaries(link_df):
    total = len(link_df)
    st = link_df.linkage_status.value_counts()
    summary = pd.DataFrame([{"metric": m, "value": int(st.get(k, 0)) if k else total} for m, k in [
        ("total_wzry_rows", None), ("unique_exact_matches", "UNIQUE_EXACT_MATCH"),
        ("multiple_exact_matches", "MULTIPLE_EXACT_MATCHES"), ("no_matches", "NO_MATCH"),
        ("unresolved_team_identity", "UNRESOLVED_TEAM_IDENTITY"), ("source_conflicts", "SOURCE_CONFLICT")]])
    lv = link_df[link_df.linkage_status == "UNIQUE_EXACT_MATCH"].fingerprint_level.value_counts()
    summary = pd.concat([summary, pd.DataFrame([{"metric": f"unique_first_achieved_at_{l}", "value": int(lv.get(l, 0))} for l in LEVELS])])
    for lvl in LEVELS:
        col = f"candidate_count_{lvl}" if lvl != "F3" else "candidate_count"
        v = link_df[col].dropna()
        summary = pd.concat([summary, pd.DataFrame([
            {"metric": f"{lvl}_rows_testable", "value": int(len(v))},
            {"metric": f"{lvl}_exactly_one_candidate", "value": int((v == 1).sum())},
            {"metric": f"{lvl}_multiple_candidates", "value": int((v > 1).sum())},
            {"metric": f"{lvl}_zero_candidates", "value": int((v == 0).sum())}])])
    by_season = link_df[link_df.season.notna()].groupby(["season", "linkage_status"]).size().unstack(fill_value=0).reset_index()
    teams = pd.concat([link_df[["team1_raw", "team1_canonical_id", "linkage_status"]].set_axis(["team_raw", "canonical_team_id", "linkage_status"], axis=1),
                       link_df[["team2_raw", "team2_canonical_id", "linkage_status"]].set_axis(["team_raw", "canonical_team_id", "linkage_status"], axis=1)])
    by_team = teams.fillna({"canonical_team_id": "UNRESOLVED"}).groupby(["team_raw", "canonical_team_id", "linkage_status"]).size().unstack(fill_value=0).reset_index()
    amb = link_df[link_df.linkage_status.isin(["MULTIPLE_EXACT_MATCHES", "SOURCE_CONFLICT"])][
        ["wzry_row_id", "wzry_row_hash", "linkage_status", "team1_canonical_id", "team2_canonical_id",
         "candidate_count", "candidates", "winner_wzry", "winner_kplow", "quality_flags"]]
    return summary, by_season, by_team, amb


def level_counts(link_df):
    return Counter(link_df.fingerprint_level.dropna())
