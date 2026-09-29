"""v0.4 Phase A report builders (diagnostics only; nothing is written back to sources)."""
import re
from collections import Counter

import pandas as pd

from openkpl.roster.parse import UNKNOWN, validate_lineup

SPRING, SUMMER = "KPL2026S1", "KPL2026S2"


def slot_canon(slot_names, registry):
    exact = dict(zip(registry.observed_name, registry.canonical_team_id))
    return {s: exact.get(n) for s, n in slot_names.items()}


def game_flags(gp):
    return {k: validate_lineup(g.to_dict("records")) for k, g in gp.groupby(["scheduleid", "round"])}


def _pct(n, d):
    return round(100.0 * n / d, 2) if d else None


def coverage_2026(canonical, T, flags):
    g, gp, sp, cb = T["games"], T["game_players"], T["series_players"], T["combo"]
    rows = []
    for season, label in [(SPRING, "2026 Spring"), (SUMMER, "2026 Summer")]:
        c = canonical[canonical.season == season]
        sids = set(c.series_id)
        gs = g[g.season == season]
        gps = gp[gp.season == season]
        games_total = int((c.score_a + c.score_b).sum())
        rc = gs.groupby("scheduleid").size()
        exp = (c.set_index("series_id").score_a + c.set_index("series_id").score_b)
        rec_ok = [s for s in sids if s in rc.index and rc[s] == exp[s]]
        f = {k: v for k, v in flags.items() if k[0] in sids}
        pid_ok = gps.groupby(["scheduleid", "round"]).playerid.apply(lambda s: (s != "").all() and len(s) == 10)
        hero_ok = gps.groupby(["scheduleid", "round"]).hero_id.apply(lambda s: s.notna().all() and (s > 0).all() and len(s) == 10)
        battles = cb[cb.scheduleid.isin(sids)].drop_duplicates("battle_id")
        lineup_all = gps.groupby("scheduleid")["round"].nunique()
        sub_obs = 0
        for sid, grp in gps.groupby("scheduleid"):
            sets = grp.groupby(["round", "team_slot"]).playerid.apply(frozenset).unstack()
            if any(sets[col].nunique() > 1 for col in sets.columns):
                sub_obs += 1
        m = [
            ("series_total", len(sids), len(sids), "validated canonical temporal dataset (completed)"),
            ("series_with_stable_ids", len(sids & set(sp[sp.season == season].scheduleid) | sids & set(gs.scheduleid)), len(sids),
             "scheduleid is the source series ID (getScheduleList); getScheduleDetail accepted it for every counted series"),
            ("series_with_game_records", len(rec_ok), len(sids), "round_details count equals validated score_a+score_b"),
            ("games_total", games_total, games_total, "sum of validated series scores"),
            ("games_with_game_ids", len(battles), games_total,
             "source battle_id only via getSeasonHeroComboMatches for site-listed hero combos; (scheduleid, round) composite key covers every game with records"),
            ("games_with_composite_key_scheduleid_round", len(gs), games_total, "not a source game ID; source positional key"),
            ("games_with_winner", int((gs.win_team_slot != "").sum()), games_total, "round_details.win_team"),
            ("games_with_blue_red_side", 0, games_total, "no per-game side field in any tested endpoint; side exists only as team-season aggregates (getTeamsIntro)"),
            ("games_with_complete_10_player_lineup", sum(1 for v in f.values() if not {"NO_LINEUP", "NOT_5V5", "PLAYER_TEAM_UNKNOWN"} & set(v) and not any(x.startswith("PLAYER_COUNT") for x in v)), games_total, "10 players, 5 per team, team from series roster"),
            ("games_with_player_ids", int(pid_ok.sum()), games_total, "all 10 playerid non-empty"),
            ("games_with_roles", sum(1 for v in f.values() if not {"POSITION_UNLABELED", "POSITION_NOT_1_TO_5", "NOT_5V5"} & set(v)), games_total, "each team positions exactly {1..5}"),
            ("games_with_hero_assignments", int(hero_ok.sum()), games_total, "10 hero_id > 0 mapped to playerid"),
            ("games_with_kda", 0, games_total, "no per-player per-game K/D/A in any tested endpoint (season aggregates only)"),
            ("games_with_team_kills", len(battles), games_total, "team kill totals only via getSeasonHeroComboMatches"),
            ("games_with_duration", len(battles), games_total, "via getSeasonHeroComboMatches"),
            ("games_with_gold", 0, games_total, "absent for completed games"),
            ("games_with_damage", 0, games_total, "absent for completed games"),
            ("games_with_complete_bp", 0, games_total, "bans absent in every tested endpoint"),
            ("games_with_ordered_bp", 0, games_total, "complete ordered BP absent"),
            ("games_with_ordered_picks_only", len(battles), games_total, "pick order index (bp_picks_*.order) via getSeasonHeroComboMatches; no bans"),
            ("games_with_game_vod", int(gs.has_game_vid.sum()), games_total, "round_details.vid"),
            ("series_with_substitution_information", int((lineup_all == lineup_all.index.map(exp)).sum()), len(sids),
             "per-game lineups for every game of the series (substitutions observable)"),
            ("series_with_substitution_observed", sub_obs, len(sids), "a team's 5-player set differs between games of the series"),
        ]
        rows += [{"season": label, "season_id": season, "metric": k, "numerator": int(n), "denominator": int(d),
                  "coverage_pct": _pct(n, d), "method": "FULL_COLLECTION", "notes": note} for k, n, d, note in m]
    return pd.DataFrame(rows)


def _classify(n_with, n_tested):
    if n_tested == 0:
        return "UNKNOWN"
    if n_with == 0:
        return "NONE"
    return "FULL" if n_with == n_tested else "PARTIAL"


def historical_coverage(canonical, T, flags, combo_lists, perf_counts):
    g, gp = T["games"], T["game_players"]
    rows = []
    for season in sorted(canonical.season.unique()):
        c = canonical[canonical.season == season]
        tested = sorted(set(c.series_id) & set(g.scheduleid))
        basis = "FULL_COLLECTION" if len(tested) == len(c) else f"SAMPLE_{len(tested)}_OF_{len(c)}"
        gs = g[g.scheduleid.isin(tested)]
        gps = gp[gp.scheduleid.isin(tested)]
        keys = list(zip(gs.scheduleid, gs["round"]))
        f = [flags.get(k, ["NO_LINEUP"]) for k in keys]
        exp = (c.set_index("series_id").score_a + c.set_index("series_id").score_b)
        rc = gs.groupby("scheduleid").size()
        n_rec = sum(1 for s in tested if rc.get(s, 0) == exp[s])
        n_win = int((gs.win_team_slot != "").sum())
        n_players = sum(1 for v in f if "NO_LINEUP" not in v)
        n_roles = sum(1 for v in f if not {"NO_LINEUP", "POSITION_UNLABELED", "POSITION_NOT_1_TO_5", "NOT_5V5"} & set(v))
        n_heroes = int(gps.groupby(["scheduleid", "round"]).hero_id.apply(lambda s: len(s) == 10 and (s > 0).all()).sum())
        layers = [
            ("series", n_rec, len(tested), "getScheduleDetail round count == validated score"),
            ("games", len(gs), int(exp[tested].sum()), "round_details rows"),
            ("game_winner", n_win, len(gs), "round_details.win_team"),
            ("players", n_players, len(gs), "round_details.players non-empty"),
            ("roles", n_roles, len(gs), "positions {1..5} per team; 0 means unlabeled"),
            ("heroes", n_heroes, len(gs), "10 hero_id per game"),
            ("BP", combo_lists.get(season, 0), None, "ordered picks only via hero-combo endpoint; value = number of site-listed combos"),
            ("boxscore", 0, len(gs), "no per-game boxscore; season aggregate rows in getSeasonPlayerPerf = %d" % perf_counts.get(season, 0)),
        ]
        for layer, n, d, note in layers:
            if layer == "BP":
                cls = "PARTIAL" if n else "NONE"
                d = n
            else:
                cls = _classify(n, d)
            rows.append({"season": season, "year": season[3:7], "layer": layer, "classification": cls,
                         "n_with_layer": n, "n_tested": d, "basis": basis, "notes": note})
    df = pd.DataFrame(rows)
    earliest = []
    for layer, grp in df.groupby("layer", sort=False):
        ok = grp[grp.classification.isin(["FULL", "PARTIAL"])]
        earliest.append({"season": "EARLIEST_AVAILABLE", "year": ok.year.min() if len(ok) else "", "layer": layer,
                         "classification": ok.season.min() if len(ok) else "NONE", "n_with_layer": None, "n_tested": None,
                         "basis": "derived from rows above", "notes": "earliest season with FULL or PARTIAL (within tested series)"})
    return pd.concat([df, pd.DataFrame(earliest)], ignore_index=True)


def temporal_linkage(canonical, T):
    g, cb = T["games"], T["combo"]
    rows = []
    for season in sorted(canonical.season.unique()) + ["ALL"]:
        c = canonical if season == "ALL" else canonical[canonical.season == season]
        sids = set(c.series_id)
        exp = c.set_index("series_id").score_a + c.set_index("series_id").score_b
        gs = g[g.season.isin(c.season.unique())]
        tested = sids & set(gs.scheduleid)
        rc = gs.groupby("scheduleid").size()
        linked = {s for s in tested if rc[s] == exp[s]}
        orphan = gs[~gs.scheduleid.isin(sids)]
        b = cb[cb.season.isin(c.season.unique())].drop_duplicates("battle_id")
        rows.append({
            "season": season, "temporal_series_total": len(sids), "series_tested": len(tested),
            "deterministically_linked_series": len(linked), "ambiguous_series": 0,
            "unlinked_series": len(tested - linked), "not_tested_series": len(sids - tested),
            "games_total": len(gs), "games_with_parent_series": int(gs.scheduleid.isin(sids).sum()),
            "orphan_games": len(orphan), "battle_ids_total": len(b),
            "battle_ids_with_parent_game": int(sum((s, n) in set(zip(gs.scheduleid, gs["round"])) for s, n in zip(b.scheduleid, b.match_num))),
            "link_method": "exact source scheduleid (series); (scheduleid, round) for games; battle_id -> (schedule_id, match_num)",
        })
    return pd.DataFrame(rows)


_PAREN_SUFFIX = re.compile(r"[（(][^（()）]*[)）]$")


def display_handle(player_name, team_names):
    """Strip the longest exact '<team_name>.' prefix and a trailing parenthetical; else return the raw name."""
    names = [team_names] if isinstance(team_names, str) else list(team_names or [])
    for t in sorted((t for t in names if t), key=len, reverse=True):
        if player_name.startswith(t + "."):
            return _PAREN_SUFFIX.sub("", player_name[len(t) + 1:])
    return player_name


def player_identity(T, slot_to_canon, canonical, slot_names=None):
    gp, sp, reg = T["game_players"], T["series_players"], T["registered"]
    slot_names = slot_names or {}
    order = {s: i for i, s in enumerate(sorted(canonical.season.unique()))}
    names = sp[sp.playerid != ""].copy()
    names["canon"] = names.team_slot.map(slot_to_canon)
    team_names = {}
    for slot, name in list(slot_names.items()) + list(zip(T["games"].win_team_slot, T["games"].win_team_name)):
        if slot and name:
            team_names.setdefault(slot, set()).add(name)
    handles = [_PAREN_SUFFIX.sub("", s) if s else display_handle(n, team_names.get(t))
               for s, n, t in zip(names.player_name_short, names.player_name, names.team_slot)]
    names["player_name_short"] = handles
    gpl = gp[gp.playerid != ""].copy()
    gpl["canon"] = gpl.team_slot.map(slot_to_canon)
    short_owners = names[names.player_name_short != ""].groupby("player_name_short").playerid.nunique()
    real_owners = names[names.player_name_real != ""].groupby("player_name_real").playerid.nunique()
    rows = []
    for pid, grp in names.groupby("playerid"):
        games = gpl[gpl.playerid == pid]
        seasons = sorted(grp.season.unique(), key=order.get)
        teams_seq = []
        for s in seasons:
            for t in sorted(grp[grp.season == s].canon.dropna().unique()):
                if not teams_seq or teams_seq[-1] != t:
                    teams_seq.append(t)
        shorts = sorted(set(grp.player_name_short) - {""})
        reals = sorted(set(grp.player_name_real) - {""})
        roles = sorted(set(games.position) - {0})
        flags = []
        if len(set(teams_seq)) > 1:
            flags.append("TRANSFER_OBSERVED")
        if len(shorts) > 1:
            flags.append("NAME_CHANGE_CANDIDATE")
        if any(short_owners.get(s, 0) > 1 for s in shorts):
            flags.append("DUPLICATE_DISPLAY_NAME")
        if any(real_owners.get(r, 0) > 1 for r in reals) or len(reals) > 1:
            flags.append("ID_INSTABILITY")
        if len(roles) > 1:
            flags.append("ROLE_CHANGE")
        if grp.canon.isna().any() or not shorts or any("." in s for s in shorts):
            flags.append("UNKNOWN_IDENTITY")
        rows.append({
            "playerid": pid, "display_handles": "|".join(shorts), "real_names": "|".join(reals),
            "raw_display_names": "|".join(sorted(set(grp.player_name))),
            "first_season": seasons[0], "last_season": seasons[-1], "seasons_observed": len(seasons),
            "canonical_team_sequence": ">".join(teams_seq), "roles_observed": "|".join(map(str, roles)),
            "games_observed": int(games[["scheduleid", "round"]].drop_duplicates().shape[0]),
            "in_registered_roster_2026": bool((reg.playerid == pid).any()), "flags": "|".join(flags),
        })
    return pd.DataFrame(rows).sort_values(["flags", "playerid"], ascending=[False, True])


def data_quality(canonical, T, flags, lock_problems):
    g, gp, sp, cb = T["games"], T["game_players"], T["series_players"], T["combo"]
    sids = set(canonical.series_id)
    rows = []

    def add(check, n_checked, bad, examples=None, note=""):
        if isinstance(bad, pd.DataFrame):
            bad = list(bad.itertuples(index=False, name=None))
        examples = bad if examples is None else examples
        rows.append({"check": check, "n_checked": int(n_checked), "n_flagged": int(len(bad) if hasattr(bad, "__len__") else bad),
                     "examples": "; ".join(map(str, list(examples)[:5])) if hasattr(examples, "__iter__") else "",
                     "action": "NOT_REPAIRED", "notes": note})

    add("duplicate series IDs (validated dataset)", len(canonical), canonical.series_id[canonical.series_id.duplicated()])
    dup_g = g[g.duplicated(["scheduleid", "round"], keep=False)]
    add("duplicate game IDs (scheduleid, round)", len(g), dup_g.drop_duplicates(["scheduleid", "round"])[["scheduleid", "round"]])
    bmap = cb.groupby("battle_id")[["scheduleid", "match_num"]].nunique()
    add("duplicate battle_id mapping to >1 game", cb.battle_id.nunique(), bmap[(bmap > 1).any(axis=1)].index)
    rmap = cb.groupby(["scheduleid", "match_num"]).battle_id.nunique()
    add("game mapped to >1 battle_id", len(rmap), rmap[rmap > 1].index)
    add("game without parent series", len(g), g[~g.scheduleid.isin(sids)].scheduleid)
    add("duplicate game_number inside series", len(g), dup_g.scheduleid.unique())
    rn = g.groupby("scheduleid")["round"].apply(lambda s: sorted(s) == list(range(1, len(s) + 1)))
    add("game numbers not contiguous 1..N", len(rn), rn[~rn].index)
    exp = canonical.set_index("series_id").score_a + canonical.set_index("series_id").score_b
    rc = g.groupby("scheduleid").size()
    add("game count != validated series score", len(rc), rc[rc != exp.reindex(rc.index)].index)
    win = g[g.win_team_slot != ""].groupby("scheduleid").win_team_slot.agg(lambda s: tuple(sorted(Counter(s).values(), reverse=True)))
    sc = canonical.set_index("series_id").apply(lambda r: tuple(sorted([int(r.score_a), int(r.score_b)], reverse=True)), axis=1)
    full = g.groupby("scheduleid").win_team_slot.apply(lambda s: (s != "").all())
    chk = [s for s in win.index if full[s]]
    bad = [s for s in chk if tuple(x for x in win[s]) != tuple(x for x in sc[s] if x)]
    add("per-game winners inconsistent with series score", len(chk), bad)
    add("games with blank winner", len(g), g[(g.win_team_slot == "") & (g.n_players > 0)].apply(lambda r: f"{r.scheduleid}#{r['round']}", axis=1),
        note="excludes games with no lineup (2022S1 schema)")
    add("games with no lineup", len(g), g[g.n_players == 0].scheduleid.unique(), note="rows present, players empty")
    fl = Counter(x for v in flags.values() for x in v)
    items = [("same player twice for same team/game", "DUPLICATE_PLAYER_IN_GAME"), ("team with !=5 players / not 5v5", "NOT_5V5"),
             ("duplicate hero in game", "DUPLICATE_HERO_IN_GAME"), ("player team unknown", "PLAYER_TEAM_UNKNOWN"),
             ("unknown roles (positions all 0)", "POSITION_UNLABELED"), ("roles not exactly 1..5", "POSITION_NOT_1_TO_5")]
    for name, key in items:
        ex = [f"{k[0]}#{k[1]}" for k, v in flags.items() if key in v]
        note = ""
        if key == "DUPLICATE_HERO_IN_GAME":
            rounds = Counter(k[1] for k, v in flags.items() if key in v)
            note = f"rounds of flagged games: {dict(rounds)}"
        add(name, len(flags), ex, ex, note)
    both = sp.groupby(["scheduleid", "playerid"]).team_slot.nunique()
    add("same player appearing for both teams (series roster)", len(both), both[both > 1].index)
    add("missing player IDs (game rows)", len(gp), gp[gp.playerid == ""].apply(lambda r: f"{r.scheduleid}#{r['round']}", axis=1))
    add("missing hero IDs (game rows)", len(gp), gp[gp.hero_id.isna() | (gp.hero_id <= 0)].apply(lambda r: f"{r.scheduleid}#{r['round']}", axis=1))
    lineup_not_in_series = gp[gp.team_slot == UNKNOWN]
    add("game player not in series roster", len(gp), lineup_not_in_series.apply(lambda r: f"{r.scheduleid}#{r['round']}:{r.playerid}", axis=1))
    neg = cb[(cb.kill_left < 0) | (cb.kill_right < 0)]
    add("impossible negative kills (team totals)", len(cb), neg.battle_id, note="per-player K/D/A not available")
    dur = cb.drop_duplicates("battle_id")
    add("impossible durations (<300s or >3600s)", len(dur), dur[(dur.duration < 300) | (dur.duration > 3600)].apply(lambda r: f"{r.battle_id}:{r.duration}", axis=1))
    heroes = gp.groupby(["scheduleid", "round", "team_slot"]).hero_id.apply(frozenset)
    u = cb.drop_duplicates(["battle_id", "team_slot"])
    mism = [r.battle_id for r in u.itertuples() if heroes.get((r.scheduleid, r.match_num, r.team_slot)) != frozenset(h for h, _ in r.picks_left)]
    add("BP picks inconsistent with final hero lineup", len(u), mism)
    w = g.set_index(["scheduleid", "round"]).win_team_slot
    res = [r.battle_id for r in u.itertuples() if (w.get((r.scheduleid, r.match_num)) == r.team_slot) != (r.schedule_result == 1)]
    add("battle result inconsistent with game winner", len(u), res)
    dates = pd.to_datetime(cb.battle_id.str.split("_").str[0].astype(int), unit="s", utc=True).dt.tz_convert("Asia/Shanghai").dt.strftime("%Y-%m-%d")
    add("battle_id epoch prefix date != schedule_date", len(cb), cb.battle_id[dates != cb.schedule_date],
        note="battle_id prefix interpreted as unix seconds (INFERENCE, consistent on all rows if 0)")
    gpn = gp[gp.playerid != ""].merge(sp[["scheduleid", "playerid", "player_name_short", "player_name_real"]], on=["scheduleid", "playerid"], how="left")
    ids = gpn.groupby("playerid").player_name_real.apply(lambda s: len(set(s.dropna()) - {""}))
    add("unstable source IDs (player id -> >1 real name)", len(ids), ids[ids > 1].index)
    rn2 = sp[sp.player_name_real != ""].groupby("player_name_real").playerid.nunique()
    add("real name mapped to >1 player id", len(rn2), rn2[rn2 > 1].index, note="could be namesakes; not merged")
    add("validated v0.3 artifacts changed since baseline lock", 0, lock_problems)
    return pd.DataFrame(rows)
