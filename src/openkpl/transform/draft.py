"""Historical draft ETL for HoK-BP-LLM WZRY.csv.

WZRY.csv has no verified date, season, series, game number, or official game ID.
`draft_game_id` values (`wzry_000000`, ...) are synthetic row identifiers only.
Nested cells are parsed with `ast.literal_eval`; `eval` is never used.
Anomalies are retained and flagged, never repaired.
"""
import ast
import hashlib
from collections import Counter

import pandas as pd

ROLES = ["对抗路", "打野", "中路", "发育路", "游走"]
UNKNOWN_ROLE = "未知"
SOURCE_COLUMNS = ["team1", "team1_win", "team2", "team2_win", "battle_process", "BP_process"]
SOURCE_DATASET = "HoK-BP-LLM/WZRY.csv"


def read_wzry(path):
    """Read WZRY.csv as raw text cells. The file is GB18030; UTF-8 fails."""
    last = None
    for enc in ("gb18030", "gbk", "utf-8-sig", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str, keep_default_na=False)
        except UnicodeDecodeError as e:
            last = e
    raise last


def literal(v, field, i):
    try:
        x = ast.literal_eval(str(v))
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"{field} row {i}: {e}") from e
    if not isinstance(x, list):
        raise TypeError(f"{field} row {i} is not a list")
    return x


def boolish(v):
    s = str(v).strip().lower()
    if s in {"true", "1"}:
        return True
    if s in {"false", "0"}:
        return False
    raise ValueError(f"Bad boolean {v!r}")


def phase(seq, n):
    if n != 18:
        return "NONSTANDARD"
    if seq <= 4:
        return "BAN_1"
    if seq <= 10:
        return "PICK_1"
    if seq <= 14:
        return "BAN_2"
    return "PICK_2"


def row_sha256(row):
    """SHA256 over the raw source cell text, joined by the unit separator."""
    payload = "\x1f".join(str(row[c]) for c in SOURCE_COLUMNS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def clean_five_role(battle, t1, t2):
    """True only if each team has each of the five roles exactly once."""
    by_team = {}
    for x in battle:
        by_team.setdefault(str(x.get("team", "")).strip(), []).append(str(x.get("position", "")).strip())
    if set(by_team) != {t1, t2}:
        return False
    return all(Counter(v) == Counter(ROLES) for v in by_team.values())


def build_draft_tables(path):
    df = read_wzry(path)
    missing = set(SOURCE_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    games, events, lineups, loadouts = [], [], [], []
    teams, heroes = set(), set()
    for i, r in df.reset_index(drop=True).iterrows():
        gid = f"wzry_{i:06d}"
        bp = literal(r.BP_process, "BP_process", i)
        battle = literal(r.battle_process, "battle_process", i)
        t1, t2 = str(r.team1).strip(), str(r.team2).strip()
        w1, w2 = boolish(r.team1_win), boolish(r.team2_win)
        winner = t1 if w1 and not w2 else t2 if w2 and not w1 else None
        teams |= {t1, t2}

        actions = [str(x.get("ban_or_pick", "")).strip().lower() for x in bp]
        bans, picks = actions.count("ban"), actions.count("pick")
        empty_bans = sum(a == "ban" and not str(x.get("hero", "")).strip() for a, x in zip(actions, bp))
        empty_picks = sum(a == "pick" and not str(x.get("hero", "")).strip() for a, x in zip(actions, bp))
        pick_heroes = [str(x.get("hero", "")).strip() for a, x in zip(actions, bp) if a == "pick"]
        lineup_heroes = [str(x.get("hero", "")).strip() for x in battle]
        raw_pos = [str(x.get("position", "")).strip() for x in battle]
        first_actor = str(bp[0].get("team", "")).strip() if bp else None
        standard = len(bp) == 18 and bans == 8 and picks == 10

        games.append(dict(
            draft_game_id=gid,
            draft_game_id_is_synthetic=True,
            source_row=i,
            source_row_sha256=row_sha256(r),
            team1=t1, team2=t2, team1_win=w1, team2_win=w2, winner_team=winner,
            first_actor=first_actor,
            first_actor_is_team1=first_actor == t1,
            bp_length=len(bp), ban_count=bans, pick_count=picks,
            empty_ban_count=empty_bans, empty_pick_count=empty_picks,
            lineup_slots=len(battle),
            unknown_position_slots=sum(p == UNKNOWN_ROLE for p in raw_pos),
            blank_position_slots=sum(p == "" for p in raw_pos),
            pick_set_matches_lineup=(sorted(pick_heroes) == sorted(lineup_heroes)),
            bp_quality_flag="STANDARD_18" if standard else "NONSTANDARD",
            lineup_quality_flag="CLEAN_FIVE_ROLE" if clean_five_role(battle, t1, t2) else "NONSTANDARD_ROLE_ASSIGNMENT",
            has_missing_hero=(empty_bans + empty_picks) > 0,
            temporal_identity_available=False,
            source_dataset=SOURCE_DATASET,
        ))

        for seq, (e, action) in enumerate(zip(bp, actions), 1):
            team = str(e.get("team", "")).strip()
            hero = str(e.get("hero", "")).strip()
            if team:
                teams.add(team)
            if hero:
                heroes.add(hero)
            events.append(dict(
                draft_event_id=f"{gid}_e{seq:02d}", draft_game_id=gid, sequence=seq,
                phase=phase(seq, len(bp)), acting_team=team,
                acting_team_is_team1=team == t1, action=action,
                hero=hero or None, hero_missing=not hero,
            ))

        for slot, (e, pos) in enumerate(zip(battle, raw_pos), 1):
            team = str(e.get("team", "")).strip()
            hero = str(e.get("hero", "")).strip()
            items = e.get("equiplist", []) or []
            if team:
                teams.add(team)
            if hero:
                heroes.add(hero)
            normalized = pos if pos in ROLES else UNKNOWN_ROLE
            lineups.append(dict(
                lineup_id=f"{gid}_l{slot:02d}", draft_game_id=gid, slot=slot, team=team,
                hero=hero or None, hero_missing=not hero,
                position_raw=pos, position_normalized=normalized,
                position_known=normalized != UNKNOWN_ROLE,
                equipment_count=len(items),
            ))
            for order, item in enumerate(items, 1):
                loadouts.append(dict(draft_game_id=gid, team=team, hero=hero or None,
                                     slot=slot, item_order=order, item=str(item).strip()))

    return tuple(map(pd.DataFrame, [
        games, events, lineups, loadouts,
        [{"team_name": x} for x in sorted(teams)],
        [{"hero_name": x} for x in sorted(heroes)],
    ]))
