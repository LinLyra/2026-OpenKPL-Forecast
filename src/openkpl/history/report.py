"""Completeness / quality tables for v0.4 Phase B (diagnostics only; nothing repaired)."""
import ast
import json
from pathlib import Path

import pandas as pd

P = Path("data/processed")
RC, RW = Path("reports/roster_collection"), Path("reports/wzry_linkage")


def load():
    return {n: pd.read_parquet(P / f) for n, f in {
        "games": "games/kpl_games.parquet", "apps": "games/player_game_appearances.parquet",
        "usage": "rosters/series_player_usage.parquet", "rot": "rosters/series_rotation_summary.parquet",
        "pht": "features/player_hero_temporal.parquet", "link": "drafts/wzry_game_linkage.parquet",
        "idg": "drafts/identified_draft_games.parquet", "ev": "drafts/draft_events_identified.parquet",
        "hf": "features/hero_temporal_features.parquet", "sf": "features/hero_synergy_temporal.parquet",
        "cf": "features/hero_counter_temporal.parquet", "shu": "features/series_hero_usage.parquet"}.items()}


def has(flags, f):
    return flags.fillna("").str.split("|").map(lambda x: f in x)


def season_coverage(canonical, man, T):
    g, a = T["games"], T["apps"]
    rows = []
    for s, c in canonical.groupby("season"):
        m = man[man.season_id == s]
        gs = g[g.season_id == s]
        ap = a[a.season_id == s]
        full = gs[gs.quality_flags.fillna("").eq("") | ~gs.quality_flags.str.contains("NO_LINEUP|NOT_5V5|PLAYER_COUNT")]
        rows.append({
            "season_id": s, "validated_series": len(c), "series_fetched": int((m.request_status == "FETCHED").sum()),
            "series_failed": int((m.request_status == "FAILED").sum()),
            "series_not_attempted": int((m.request_status == "NOT_ATTEMPTED").sum()),
            "series_game_count_matches": int(m.game_count_matches.sum()),
            "expected_games": int((c.score_a + c.score_b).sum()), "games_recovered": len(gs),
            "games_complete_5v5": len(full), "games_with_winner": int(gs.winner_team_id.notna().sum()),
            "games_with_roles_1_5": int(gs.game_key.isin(_role_complete(ap)).sum()),
            "player_appearances": len(ap), "distinct_players": int(ap.player_id.nunique()),
        })
    return pd.DataFrame(rows)


def _role_complete(ap):
    ok = ap.groupby(["game_key", "canonical_team_id"]).position_raw.apply(lambda s: sorted(s.tolist()) == [1, 2, 3, 4, 5])
    per = ok.groupby(level=0).agg(lambda s: len(s) == 2 and s.all())
    return set(per[per].index)


def bp_battle_consistency(idg, ev):
    """WZRY-internal: per team, BP_process picks == battle_process heroes."""
    bad = []
    for r in idg.itertuples(index=False):
        battle = {}
        for e in ast.literal_eval(r.battle_process):
            battle.setdefault(e["team"], set()).add(e["hero"])
        picks = {}
        for e in ast.literal_eval(r.BP_process):
            if e.get("ban_or_pick") == "pick":
                picks.setdefault(e["team"], set()).add(e["hero"])
        if picks != battle:
            bad.append(r.game_key)
    return bad


def quality(canonical, man, T, reg, cand_pairs):
    g, a, link, idg, ev = T["games"], T["apps"], T["link"], T["idg"], T["ev"]
    rows = []

    def add(area, metric, value, denom=None, note=""):
        rows.append({"area": area, "metric": metric, "value": value, "denominator": denom,
                     "pct": round(100 * value / denom, 2) if denom else None, "action": "NOT_REPAIRED" if "anomal" in note else "", "notes": note})

    add("collection", "validated_temporal_series_total", len(canonical))
    add("collection", "series_successfully_fetched", int((man.request_status == "FETCHED").sum()), len(canonical))
    add("collection", "series_unsupported", int(((man.request_status == "FETCHED") & (man.lineup_availability == "NONE")).sum()), len(canonical),
        "endpoint answers but returns no lineups (2022S1 schema); counted as fetched, lineup-unsupported")
    add("collection", "series_failed", int((man.request_status == "FAILED").sum()), len(canonical))
    add("collection", "series_not_attempted", int((man.request_status == "NOT_ATTEMPTED").sum()), len(canonical))
    add("collection", "series_with_retries", int((man.retry_count > 0).sum()), len(canonical))
    add("collection", "series_game_count_matches_score", int(man.game_count_matches.sum()), int((man.request_status == "FETCHED").sum()))
    fl = g.quality_flags.fillna("")
    add("games", "games_recovered", len(g), int((canonical.score_a + canonical.score_b).sum()))
    add("games", "games_with_complete_5v5_lineups", int((~fl.str.contains("NO_LINEUP|NOT_5V5|PLAYER_COUNT")).sum()), len(g))
    add("games", "games_missing_players", int(fl.str.contains("NO_LINEUP|NOT_5V5|PLAYER_COUNT|PLAYER_ID_MISSING").sum()), len(g), "anomaly; includes NO_LINEUP 2022S1")
    add("games", "games_no_lineup", int(has(g.quality_flags, "NO_LINEUP").sum()), len(g), "anomaly")
    add("games", "games_missing_winner", int(g.winner_team_id.isna().sum()), len(g), "anomaly")
    add("games", "games_missing_winner_with_lineup", int((g.winner_team_id.isna() & ~has(g.quality_flags, "NO_LINEUP")).sum()), len(g), "anomaly")
    rep = has(g.quality_flags, "DUPLICATE_HERO_IN_GAME")
    add("games", "games_with_repeated_heroes", int(rep.sum()), len(g),
        "anomaly; game numbers: " + json.dumps(g[rep].game_number.value_counts().to_dict()))
    add("games", "games_with_missing_heroes", int(has(g.quality_flags, "HERO_MISSING").sum()), len(g),
        "anomaly; empty hero_name / hero_id 0 in source; excluded from hero-keyed statistics")
    add("games", "games_with_unknown_role", int(has(g.quality_flags, "POSITION_UNLABELED").sum()), len(g), "positions all 0")
    add("games", "games_with_roles_not_1_to_5", int(has(g.quality_flags, "POSITION_NOT_1_TO_5").sum()), len(g), "anomaly")
    add("games", "games_with_source_battle_id", int(g.source_battle_id_if_available.notna().sum()), len(g))
    add("games", "games_with_video_id", int(g.source_video_id_if_available.notna().sum()), len(g))
    add("games", "duplicate_game_keys", int(g.game_key.duplicated().sum()), len(g), "anomaly")
    add("players", "appearance_rows", len(a))
    add("players", "appearances_missing_player_id", int(a.player_id.isna().sum()), len(a), "anomaly")
    add("players", "appearances_team_unmapped", int(a.canonical_team_id.isna().sum()), len(a), "anomaly")
    add("players", "player_ids", int(a.player_id.nunique()))
    add("players", "unique_derived_handles", int(a.player_handle_derived.nunique()))
    add("players", "players_with_transfers", int((reg.transfer_count > 0).sum()), len(reg))
    add("players", "identity_review_pairs", len(cand_pairs), None, "same derived handle, different player_id; not merged")
    add("players", "identity_conflicts_same_game", int((cand_pairs.same_game_count > 0).sum()) if len(cand_pairs) else 0, len(cand_pairs) or None)
    add("players", "handles_with_unstripped_team_prefix", int(reg.quality_flags.str.contains("HANDLE_PREFIX_NOT_STRIPPED").sum()), len(reg), "anomaly; display prefix != source team name")
    st = link.linkage_status.value_counts()
    for k in ["UNIQUE_EXACT_MATCH", "MULTIPLE_EXACT_MATCHES", "NO_MATCH", "UNRESOLVED_TEAM_IDENTITY", "SOURCE_CONFLICT"]:
        add("wzry", k.lower(), int(st.get(k, 0)), len(link))
    add("wzry", "winner_contradictions", int((link.winner_agreement == "CONTRADICTION").sum()), int(link.game_key.notna().sum()))
    bad = bp_battle_consistency(idg, ev)
    add("drafts", "identified_games", len(idg))
    add("drafts", "wzry_bp_picks_differ_from_battle_heroes", len(bad), len(idg), "anomaly (WZRY-internal): " + "; ".join(bad[:5]))
    add("drafts", "draft_events", len(ev))
    add("drafts", "events_nonstandard_bp_shape", int(has(ev.quality_flags, "NONSTANDARD_BP_SHAPE").sum()), len(ev), "anomaly")
    add("drafts", "events_hero_id_unmapped", int(has(ev.quality_flags, "HERO_ID_UNMAPPED").sum()), len(ev), "anomaly")
    add("drafts", "events_team_unmapped", int(has(ev.quality_flags, "TEAM_UNMAPPED").sum()), len(ev), "anomaly")
    return pd.DataFrame(rows)


def global_bp_table(shu):
    s = shu[shu.game_number > 1]
    t = s.groupby("season_id").agg(
        team_games_after_g1=("series_id", "size"),
        team_games_repeating_own_hero=("repeats_own_previous", lambda x: int((x > 0).sum())),
        team_games_repeating_any_series_hero=("repeats_any_previous", lambda x: int((x > 0).sum())),
    )
    t["own_repeat_rate"] = (t.team_games_repeating_own_hero / t.team_games_after_g1).round(4)
    t["any_repeat_rate"] = (t.team_games_repeating_any_series_hero / t.team_games_after_g1).round(4)
    by_game = s.groupby(["season_id", "game_number"]).repeats_own_previous.apply(lambda x: int((x > 0).sum())).unstack(fill_value=0)
    return t.reset_index(), by_game.reset_index()
