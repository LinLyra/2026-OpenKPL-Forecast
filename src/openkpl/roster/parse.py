"""Pure parsers for kplow roster / game-level responses (no network, no repair).

Every output row keeps the source identifiers verbatim.  Nothing is imputed:
missing winners stay empty, unknown team membership stays UNKNOWN.
"""
import json

import pandas as pd

UNKNOWN = "UNKNOWN"


def _data(body):
    j = json.loads(body) if isinstance(body, (bytes, str)) else body
    return j.get("result"), j.get("data")


def parse_schedule_detail(scheduleid, body):
    """Return (series_players, games, game_players) lists of dicts."""
    _, d = _data(body)
    d = d or {}
    sp = []
    for p in d.get("players") or []:
        sp.append({
            "scheduleid": scheduleid, "playerid": str(p.get("playerid") or ""), "team_slot": p.get("team_id") or "",
            "player_name": p.get("player_name") or "", "player_name_short": p.get("player_name_short") or "",
            "player_name_real": p.get("player_name_real") or "", "position": p.get("position"),
        })
    slot_of = {}
    for r in sp:
        slot_of.setdefault(r["playerid"], set()).add(r["team_slot"])
    games, gp = [], []
    for r in d.get("round_details") or []:
        players = r.get("players") or []
        games.append({
            "scheduleid": scheduleid, "round": r.get("round"), "win_team_slot": r.get("win_team") or "",
            "win_team_name": r.get("win_team_name") or "", "has_game_vid": bool(r.get("vid")),
            "n_players": len(players),
        })
        for p in players:
            pid = str(p.get("playerid") or "")
            slots = slot_of.get(pid, set())
            gp.append({
                "scheduleid": scheduleid, "round": r.get("round"), "playerid": pid,
                "team_slot": next(iter(slots)) if len(slots) == 1 else UNKNOWN,
                "position": p.get("position"), "hero_id": p.get("hero_id"), "hero_name": p.get("hero_name") or "",
                "has_player_vid": bool(p.get("vid")),
            })
    return sp, games, gp


def parse_teams_list(season, body):
    res, d = _data(body)
    rows = []
    for t in d or []:
        for p in t.get("player_list") or []:
            rows.append({
                "season": season, "team_slot": t.get("teamid"), "team_name": t.get("team_name"),
                "playerid": str(p.get("playerid") or ""), "player_name": p.get("player_name") or "",
                "short_name": p.get("short_name") or "", "real_name": p.get("real_name") or "",
                "openid": p.get("openid") or "", "position": p.get("position"),
            })
    return rows


def parse_player_perf(season, body):
    _, d = _data(body)
    return [{
        "season": season, "playerid": str(p.get("player_id") or ""), "team_slot": p.get("team_id"),
        "team_name": p.get("team_name"), "short_name": p.get("player_short_name") or "",
        "real_name": p.get("player_real_name") or "", "position": p.get("position"), "matchcount": p.get("Matchcount"),
    } for p in d or []]


def parse_combo_matches(season, heros, body):
    _, d = _data(body)
    rows = []
    for t in d or []:
        for m in t.get("matches") or []:
            rows.append({
                "season": season, "combo": heros, "team_slot": t.get("team_id"), "battle_id": m.get("battle_id"),
                "scheduleid": m.get("schedule_id"), "schedule_date": m.get("schedule_date"),
                "match_num": m.get("match_num"), "rival_team_slot": m.get("rival_team_id"),
                "schedule_result": m.get("schedule_result"),
                "picks_left": tuple((x["hero_id"], x["order"]) for x in m.get("bp_picks_left") or []),
                "picks_right": tuple((x["hero_id"], x["order"]) for x in m.get("bp_picks_right") or []),
                "kill_left": m.get("kill_left"), "kill_right": m.get("kill_right"), "duration": m.get("duration"),
            })
    return rows


def validate_lineup(game_players):
    """Flags for one game's player rows (list of dicts). Returns list of flag strings."""
    flags = []
    n = len(game_players)
    if n == 0:
        return ["NO_LINEUP"]
    if n != 10:
        flags.append(f"PLAYER_COUNT_{n}")
    pids = [p["playerid"] for p in game_players]
    if len(set(pids)) != len(pids):
        flags.append("DUPLICATE_PLAYER_IN_GAME")
    heroes = [p["hero_id"] for p in game_players]
    if len(set(heroes)) != len(heroes):
        flags.append("DUPLICATE_HERO_IN_GAME")
    if any(p["team_slot"] == UNKNOWN for p in game_players):
        flags.append("PLAYER_TEAM_UNKNOWN")
    by_team = {}
    for p in game_players:
        by_team.setdefault(p["team_slot"], []).append(p)
    known = {k: v for k, v in by_team.items() if k != UNKNOWN}
    if len(known) != 2 or any(len(v) != 5 for v in known.values()):
        flags.append("NOT_5V5")
    for v in known.values():
        pos = [p["position"] for p in v]
        if all(x in (0, None) for x in pos):
            flags.append("POSITION_UNLABELED")
        elif sorted(pos) != [1, 2, 3, 4, 5]:
            flags.append("POSITION_NOT_1_TO_5")
    return sorted(set(flags))


def duplicate_ids(df, key, attrs):
    """Rows of `key` values that map to more than one distinct combination of `attrs`."""
    g = df.groupby(key)[attrs].nunique()
    return g[(g > 1).any(axis=1)]


def link_games(games, series_ids):
    """Game→series linkage: every game must carry a scheduleid present in the temporal dataset."""
    g = pd.DataFrame(games)
    if g.empty:
        return {"games_total": 0, "games_with_parent_series": 0, "orphan_games": 0}
    ok = g.scheduleid.isin(set(series_ids))
    return {"games_total": int(len(g)), "games_with_parent_series": int(ok.sum()), "orphan_games": int((~ok).sum())}
