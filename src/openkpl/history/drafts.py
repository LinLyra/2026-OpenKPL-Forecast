"""Identified (dated) WZRY drafts, draft events, and out-of-time hero / synergy / counter primitives.

Out-of-time rule: every feature row for game G is computed from state that only contains games
strictly earlier than G in the order (series_start_time, chronological_order, game_number).
State is updated after all rows for G are emitted.

Outcome label for a game = kplow winner_team_id. If the kplow winner is missing, the game counts
toward appearance counts but not toward wins/decided (WZRY winner is not substituted).

Shrinkage metadata (fixed a priori, not tuned): winrate_shrunk = (wins + K * 0.5) / (decided + K), K = 10.
MIN_SAMPLE = 5 decided games for `meets_min_sample`.
"""
import ast
from collections import defaultdict
from itertools import combinations

import pandas as pd

K_SHRINK = 10
PRIOR_MEAN = 0.5
MIN_SAMPLE = 5
PHASES_18 = ["BAN_PHASE_1"] * 4 + ["PICK_PHASE_1"] * 6 + ["BAN_PHASE_2"] * 4 + ["PICK_PHASE_2"] * 4
SHAPE_18 = ["ban"] * 4 + ["pick"] * 6 + ["ban"] * 4 + ["pick"] * 4


def hero_id_map(apps, hero_rank_rows=()):
    """Exact name->id mapping only where every observed (name, id) evidence is one-to-one."""
    a = apps[apps.hero_id.notna() & apps.hero_name.notna()]
    pairs = set(zip(a.hero_name, a.hero_id)) | {(n, int(i)) for n, i in hero_rank_rows}
    by_name, by_id = defaultdict(set), defaultdict(set)
    for n, i in pairs:
        if n and i:
            by_name[n].add(int(i))
            by_id[int(i)].add(n)
    return {n: next(iter(ids)) for n, ids in by_name.items() if len(ids) == 1 and len(by_id[next(iter(ids))]) == 1}


def identified_games(link_df, wzry_df, games):
    u = link_df[link_df.linkage_status == "UNIQUE_EXACT_MATCH"]
    g = games.set_index("game_key")
    rows = []
    for r in u.itertuples(index=False):
        raw = wzry_df.loc[r.wzry_row_id]
        gm = g.loc[r.game_key]
        conf = {"AGREE": "HIGH_F3_GLOBAL_UNIQUE_WINNER_AGREES",
                "KPL_WINNER_MISSING": "MEDIUM_F3_GLOBAL_UNIQUE_KPL_WINNER_MISSING"}.get(r.winner_agreement, "LOW_" + str(r.winner_agreement))
        rows.append({
            "game_key": r.game_key, "series_id": r.series_id, "season": r.season, "date": r.date,
            "stage": gm.stage, "game_number": r.game_number, "series_start_time": gm.series_start_time,
            "chronological_order": int(gm.chronological_order),
            "team1": r.team1_canonical_id, "team2": r.team2_canonical_id,
            "team1_raw": r.team1_raw, "team2_raw": r.team2_raw,
            "winner": r.winner_kplow, "winner_wzry": r.winner_wzry, "winner_agreement": r.winner_agreement,
            "battle_process": raw.battle_process, "BP_process": raw.BP_process,
            "wzry_row_id": r.wzry_row_id, "source_row_hash": r.wzry_row_hash,
            "linkage_method": f"{r.fingerprint_level} exact fingerprint; unique across full candidate universe (F3 count = 1)",
            "linkage_confidence_category": conf,
        })
    return pd.DataFrame(rows)


def draft_events(idg, canon_names, name_to_id):
    rows = []
    for r in idg.itertuples(index=False):
        ev = ast.literal_eval(r.BP_process)
        shape = [e.get("ban_or_pick") for e in ev]
        phases = PHASES_18 if shape == SHAPE_18 else [None] * len(ev)
        for seq, (e, ph) in enumerate(zip(ev, phases), start=1):
            flags = []
            if ph is None:
                flags.append("NONSTANDARD_BP_SHAPE")
            hid = name_to_id.get(e.get("hero"))
            if hid is None:
                flags.append("HERO_ID_UNMAPPED")
            team = canon_names.get(e.get("team"))
            if team is None:
                flags.append("TEAM_UNMAPPED")
            rows.append({"game_key": r.game_key, "sequence": seq, "phase_if_derivable": ph, "team_id": team,
                         "team_raw": e.get("team"), "ban_or_pick": e.get("ban_or_pick"), "hero_id": hid,
                         "hero_name": e.get("hero"), "source": "WZRY.csv BP_process", "quality_flags": "|".join(flags)})
    return pd.DataFrame(rows)


class Stat:
    def __init__(self):
        self.n, self.w, self.d = defaultdict(int), defaultdict(int), defaultdict(int)

    def row(self, k, prefix):
        n, w, d = self.n[k], self.w[k], self.d[k]
        return {f"{prefix}_games": n, f"{prefix}_wins": w, f"{prefix}_decided": d,
                f"{prefix}_winrate": w / d if d else None,
                f"{prefix}_winrate_shrunk": (w + K_SHRINK * PRIOR_MEAN) / (d + K_SHRINK),
                f"{prefix}_meets_min_sample": d >= MIN_SAMPLE}

    def add(self, k, won):
        self.n[k] += 1
        if won is not None:
            self.d[k] += 1
            self.w[k] += int(won)


def _order(idg):
    return idg.sort_values(["series_start_time", "chronological_order", "game_number"]).reset_index(drop=True)


def temporal_features(idg, events, apps):
    """Returns (hero_features, synergy, counter) with strictly prior state."""
    ev = events.groupby("game_key")
    app = apps.set_index(["game_key", "canonical_team_id", "hero_name"]).player_id
    app = app[~app.index.duplicated(keep=False)]
    pick_cnt, ban_cnt = defaultdict(int), defaultdict(int)
    hero, team_hero, player_hero, syn, cnt = Stat(), Stat(), Stat(), Stat(), Stat()
    hf, sf, cf = [], [], []
    for rank, g in enumerate(_order(idg).itertuples(index=False)):
        e = ev.get_group(g.game_key)
        picks = {t: sorted(e[(e.team_id == t) & (e.ban_or_pick == "pick")].hero_name) for t in (g.team1, g.team2)}
        won = {t: (None if g.winner is None or pd.isna(g.winner) else g.winner == t) for t in (g.team1, g.team2)}
        opp = {g.team1: g.team2, g.team2: g.team1}
        for x in e.itertuples(index=False):
            rec = {"game_key": g.game_key, "temporal_rank": rank, "sequence": x.sequence, "team_id": x.team_id,
                   "ban_or_pick": x.ban_or_pick, "hero_name": x.hero_name, "hero_id": x.hero_id,
                   "hero_prior_pick_count": pick_cnt[x.hero_name], "hero_prior_ban_count": ban_cnt[x.hero_name]}
            rec.update(hero.row(x.hero_name, "hero_prior"))
            rec.update(team_hero.row((x.team_id, x.hero_name), "team_hero_prior"))
            pid = app.get((g.game_key, x.team_id, x.hero_name)) if x.ban_or_pick == "pick" else None
            rec["player_id"] = pid
            rec.update(player_hero.row((pid, x.hero_name), "player_hero_prior") if pid else {})
            rec["won_current_game_label"] = won.get(x.team_id) if x.ban_or_pick == "pick" else None
            hf.append(rec)
        for t in (g.team1, g.team2):
            for a, b in combinations(picks[t], 2):
                r = {"game_key": g.game_key, "temporal_rank": rank, "team_id": t, "hero_a": a, "hero_b": b}
                r.update(syn.row((a, b), "pair_prior"))
                r["won_current_game_label"] = won[t]
                sf.append(r)
            for a in picks[t]:
                for b in picks[opp[t]]:
                    r = {"game_key": g.game_key, "temporal_rank": rank, "team_id": t, "hero": a, "opponent_hero": b}
                    r.update(cnt.row((a, b), "vs_prior"))
                    r["won_current_game_label"] = won[t]
                    cf.append(r)
        for x in e.itertuples(index=False):
            if x.ban_or_pick == "ban":
                ban_cnt[x.hero_name] += 1
            elif x.ban_or_pick == "pick":
                pick_cnt[x.hero_name] += 1
        for t in (g.team1, g.team2):
            for h in picks[t]:
                hero.add(h, won[t])
                team_hero.add((t, h), won[t])
                pid = app.get((g.game_key, t, h))
                if pid:
                    player_hero.add((pid, h), won[t])
            for a, b in combinations(picks[t], 2):
                syn.add((a, b), won[t])
            for a in picks[t]:
                for b in picks[opp[t]]:
                    cnt.add((a, b), won[t])
    return pd.DataFrame(hf), pd.DataFrame(sf), pd.DataFrame(cf)


def series_hero_usage(apps, games):
    g = games.set_index("game_key")
    a = apps[apps.canonical_team_id.notna() & apps.hero_id.notna()]
    rows = []
    for sid, sg in a.groupby("series_id"):
        per = sg.groupby(["game_number", "canonical_team_id"]).hero_id.apply(lambda s: frozenset(int(x) for x in s))
        teams = sorted(sg.canonical_team_id.unique())
        prev = {t: set() for t in teams}
        prev_all = set()
        for n in sorted(sg.game_number.unique()):
            cur = {t: per.get((n, t), frozenset()) for t in teams}
            for t in teams:
                rows.append({
                    "series_id": sid, "season_id": g.loc[f"{sid}#G{n}", "season_id"], "game_number": int(n), "team_id": t,
                    "heroes_used_current_game": "|".join(map(str, sorted(cur[t]))),
                    "heroes_used_previous_games": "|".join(map(str, sorted(prev[t]))),
                    "distinct_heroes_used_before_game": len(prev[t]),
                    "heroes_used_previous_games_both_teams": "|".join(map(str, sorted(prev_all))),
                    "distinct_heroes_used_before_game_both_teams": len(prev_all),
                    "repeats_own_previous": len(cur[t] & prev[t]),
                    "repeats_any_previous": len(cur[t] & prev_all),
                    "lineup_complete": len(cur[t]) == 5,
                })
            for t in teams:
                prev[t] |= cur[t]
                prev_all |= cur[t]
    return pd.DataFrame(rows)
