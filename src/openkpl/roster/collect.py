"""Polite, provenance-tracked collection from the kplow endpoint family.

Only payload shapes that the official site (kpl.qq.com) itself sends are used;
parameter values come from the validated temporal dataset (series IDs) or
from other responses of the same source (season IDs, hero combos).
"""
import json
from concurrent.futures import ThreadPoolExecutor

from openkpl.refresh.snapshot import API_BASE

SITE = "kpl.qq.com static bundle index-DLQZLYyn.js (endpoint constants) + route chunk"
SEASON_ENDPOINTS = {
    "getTeamsList": "HomeView-Ddqq4bvT.js",
    "getTeamsIntro": "Teams-79aFtuw5.js",
    "getSeasonPlayerPerf": "HomeView-Ddqq4bvT.js",
    "getPlayerRank": "HomeView-Ddqq4bvT.js",
    "getHeroRankList": "HomeView-Ddqq4bvT.js",
    "getSeasonHeroCombo": "HomeView-Ddqq4bvT.js",
}


def _run(store, jobs, workers):
    def one(job):
        name, endpoint, payload, disc, ids = job
        if (store.root / f"{name}.json").exists():
            return name, "SKIPPED_EXISTS"
        _, e = store.fetch(name, "POST", f"{API_BASE}/{endpoint}", payload, discovery=disc, source_ids=ids)
        return name, e["http_status"]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, jobs))


def schedule_detail_jobs(series):
    """series: iterable of (season, scheduleid)."""
    return [(f"scheduledetail_{sid}", "getScheduleDetail", {"seasonid": season, "scheduleid": sid},
             f"{SITE} Schedule-Cp-VSdyW.js: getScheduleDetail {{seasonid, scheduleid}}; scheduleid from validated temporal dataset",
             {"seasonid": season, "scheduleid": sid}) for season, sid in series]


def season_jobs(seasons, endpoints=SEASON_ENDPOINTS):
    return [(f"{ep}_{s}", ep, {"seasonid": s}, f"{SITE} {chunk}: {ep} {{seasonid}}", {"seasonid": s})
            for s in seasons for ep, chunk in endpoints.items()]


def combo_jobs(season, combo_body):
    j = json.loads(combo_body)
    data = j.get("data") or {}
    heros = sorted({c["heros"] for key in ("high_appearance_list", "high_win_rate_list") for c in data.get(key) or []})
    return [(f"getSeasonHeroComboMatches_{season}_{h.replace(',', '-')}", "getSeasonHeroComboMatches",
             {"seasonid": season, "heros": h},
             f"{SITE} HomeView-Ddqq4bvT.js PlayerData2Detail: {{seasonid, heros}}; heros listed by getSeasonHeroCombo_{season}",
             {"seasonid": season, "heros": h}) for h in heros]


def collect(store, jobs, workers=3):
    return _run(store, jobs, workers)
