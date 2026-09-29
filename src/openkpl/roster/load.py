"""Load parsed tables from a RawStore (latest successful response per request)."""
import json

import pandas as pd

from openkpl.roster import parse
from openkpl.roster.raw_store import RawStore


def latest_ok(store):
    """{(endpoint, frozen source_ids): (body, entry)} keeping the last HTTP-200 / result-0 response."""
    out = {}
    for name, (body, e) in store.load(verify=True).items():
        if e["http_status"] != 200:
            continue
        try:
            j = json.loads(body)
        except ValueError:
            continue
        ep = e["url"].rsplit("/", 1)[-1]
        key = (ep, tuple(sorted((e.get("source_ids") or {}).items())))
        if j.get("result") == 0 and (key not in out or e["retrieved_at"] > out[key][1]["retrieved_at"]):
            out[key] = (body, e)
    return out


def tables(root):
    store = RawStore(root, transport=None, pause=0)
    ok = latest_ok(store)
    sp, games, gp, reg, perf, combo, slot_names = [], [], [], [], [], [], {}
    for (ep, ids), (body, e) in ok.items():
        ids = dict(ids)
        if ep == "getScheduleDetail":
            a, b, c = parse.parse_schedule_detail(ids["scheduleid"], body)
            for rows in (a, b, c):
                for r in rows:
                    r["season"] = ids["seasonid"]
            sp += a; games += b; gp += c
        elif ep == "getTeamsList":
            reg += parse.parse_teams_list(ids["seasonid"], body)
        elif ep == "getSeasonPlayerPerf":
            perf += parse.parse_player_perf(ids["seasonid"], body)
        elif ep == "getSeasonHeroComboMatches":
            combo += parse.parse_combo_matches(ids["seasonid"], ids["heros"], body)
        elif ep == "getTeamsIntro":
            for t in (json.loads(body)["data"] or {}).get("team_list") or []:
                slot_names[t["teamid"]] = t["team_name"]
    return {k: pd.DataFrame(v) for k, v in dict(series_players=sp, games=games, game_players=gp,
                                                   registered=reg, perf=perf, combo=combo).items()}, slot_names
