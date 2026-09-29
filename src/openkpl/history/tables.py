"""Canonical game and player-appearance tables from write-once getScheduleDetail responses."""
import json
from pathlib import Path

import pandas as pd

from openkpl.history.collect_full import PHASE_A_STORE, PHASE_B_STORE
from openkpl.roster import parse
from openkpl.roster.audit import display_handle
from openkpl.roster.load import latest_ok
from openkpl.roster.raw_store import RawStore

SNAPSHOT = "data/raw/snapshots/2026-09-28/original_api"
# Source-provided mapping (getTeamsIntro player_msg position -> position_cn), consistent on every labeled row.
POSITION_NAMES = {1: "对抗路", 2: "中路", 3: "发育路", 4: "打野", 5: "游走"}
DATA_SOURCE = "kplow getScheduleDetail"


def game_key(series_id, game_number):
    return f"{series_id}#G{int(game_number)}"


def snapshot_schedules(root="."):
    rows, seasons = [], {}
    for f in sorted((Path(root) / SNAPSHOT).glob("*_schedule_*.json")):
        d = json.loads(f.read_bytes()).get("data") or {}
        rows += d.get("list") or []
    sl = json.loads((Path(root) / SNAPSHOT / "000_season_list.json").read_bytes())["data"]["seasons"]
    seasons = {s["seasonid"]: s["season_name"] for s in sl}
    sched = pd.DataFrame(rows).drop_duplicates("scheduleid").set_index("scheduleid")
    return sched, seasons


def detail_responses(roots=(PHASE_A_STORE, PHASE_B_STORE)):
    """{scheduleid: (body, entry, root)} latest successful detail response per series across stores."""
    out = {}
    for root in roots:
        if not (Path(root) / "MANIFEST.jsonl").exists():
            continue
        for (ep, ids), (body, e) in latest_ok(RawStore(root, transport=None, pause=0)).items():
            ids = dict(ids)
            if ep != "getScheduleDetail":
                continue
            sid = ids["scheduleid"]
            if sid not in out or e["retrieved_at"] > out[sid][1]["retrieved_at"]:
                out[sid] = (body, e, root)
    return out


def combo_battles(root=PHASE_A_STORE):
    rows = []
    for (ep, ids), (body, e) in latest_ok(RawStore(root, transport=None, pause=0)).items():
        if ep == "getSeasonHeroComboMatches":
            ids = dict(ids)
            rows += parse.parse_combo_matches(ids["seasonid"], ids["heros"], body)
    b = pd.DataFrame(rows)
    if b.empty:
        return {}
    b = b.drop_duplicates("battle_id")
    return {game_key(s, n): bid for s, n, bid in zip(b.scheduleid, b.match_num, b.battle_id)}


def build(canonical, responses, sched, season_names, battles):
    c = canonical.set_index("series_id")
    games, apps = [], []
    for sid, (body, e, root) in sorted(responses.items()):
        if sid not in c.index:
            continue
        s = c.loc[sid]
        sr = sched.loc[sid] if sid in sched.index else None
        slot_map, slot_name = {}, {}
        if sr is not None:
            slot_map = {sr.team_a_id: s.canonical_team_a_id, sr.team_b_id: s.canonical_team_b_id}
            slot_name = {sr.team_a_id: sr.team_a_name, sr.team_b_id: sr.team_b_name}
        sp, gs, gp = parse.parse_schedule_detail(sid, body)
        raw_players = {p["playerid"]: p for p in sp}
        snap = f"{root}/{e['file']}"
        by_round = {}
        for i, p in enumerate(gp):
            by_round.setdefault(p["round"], []).append((i, p))
        for g in gs:
            n = int(g["round"])
            key = game_key(sid, n)
            rp = [p for _, p in by_round.get(g["round"], [])]
            flags = parse.validate_lineup(rp)
            win_slot = g["win_team_slot"]
            winner = slot_map.get(win_slot) if win_slot else None
            if not win_slot:
                flags.append("WINNER_MISSING")
            elif winner is None:
                flags.append("WINNER_SLOT_UNMAPPED")
            if any(p["playerid"] == "" for p in rp):
                flags.append("PLAYER_ID_MISSING")
            if any(_hero_missing(p["hero_id"], p["hero_name"]) for p in rp):
                flags.append("HERO_MISSING")
                flags = [f for f in flags if f != "DUPLICATE_HERO_IN_GAME"]
            bid = battles.get(key)
            games.append({
                "game_key": key, "series_id": sid, "season_id": s.season, "season": season_names.get(s.season, ""),
                "stage": s.stage, "game_number": n, "series_start_time": s.start_time,
                "chronological_order": int(s.chronological_order),
                "winner_team_id": winner, "winner_team_name": g["win_team_name"] or None,
                "winner_source_team_id": win_slot or None, "game_start_time_if_available": pd.NaT,
                "source_battle_id_if_available": bid,
                "battle_id_epoch_utc_inferred": pd.to_datetime(int(bid.split("_")[0]), unit="s", utc=True) if bid else pd.NaT,
                "source_video_id_if_available": g.get("has_game_vid") and _vid(body, n) or None,
                "n_players": g["n_players"], "data_source": DATA_SOURCE, "source_snapshot": snap,
                "source_sha256": e["sha256"], "quality_flags": "|".join(sorted(set(flags))),
            })
            for order, (_, p) in enumerate(by_round.get(g["round"], []), start=1):
                slot = p["team_slot"]
                canon = slot_map.get(slot)
                pf = []
                if p["playerid"] == "":
                    pf.append("PLAYER_ID_MISSING")
                if canon is None:
                    pf.append("TEAM_UNMAPPED")
                pos = p["position"]
                if pos in (0, None):
                    pf.append("POSITION_UNLABELED")
                hero_missing = _hero_missing(p["hero_id"], p["hero_name"])
                if hero_missing:
                    pf.append("HERO_MISSING")
                raw = raw_players.get(p["playerid"], {})
                team_raw = slot_name.get(slot)
                apps.append({
                    "game_key": key, "series_id": sid, "game_number": n, "season_id": s.season,
                    "canonical_team_id": canon, "source_team_id": slot if slot != parse.UNKNOWN else None,
                    "team_name_raw": team_raw, "player_id": p["playerid"] or None,
                    "player_name_raw": raw.get("player_name") or None,
                    "player_handle_raw": raw.get("player_name_short") or None,
                    "player_handle_derived": (raw.get("player_name_short") or
                                              display_handle(raw.get("player_name") or "", {team_raw} - {None})) or None,
                    "hero_id": None if hero_missing else p["hero_id"], "hero_name": None if hero_missing else p["hero_name"],
                    "hero_id_raw": p["hero_id"], "hero_name_raw": p["hero_name"], "position_raw": pos,
                    "position_normalized": POSITION_NAMES.get(pos),
                    "appearance_order_if_meaningful": None, "source_list_order": order, "won": (None if not winner or canon is None else canon == winner),
                    "source_snapshot": snap, "quality_flags": "|".join(pf),
                })
    return pd.DataFrame(games), pd.DataFrame(apps)


def _hero_missing(hero_id, hero_name):
    return not hero_name or not hero_id or int(hero_id) <= 0


def _vid(body, n):
    d = json.loads(body).get("data") or {}
    for r in d.get("round_details") or []:
        if int(r.get("round") or 0) == n:
            return r.get("vid") or None
    return None
