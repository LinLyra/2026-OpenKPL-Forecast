"""v0.3.1 refresh audit: inventory, diff, 2026 coverage, missing manifest, team_a forensics, decision gate."""
import json
from math import comb

import numpy as np
import pandas as pd

from openkpl.refresh.normalize import utc8_string
from openkpl.transform.canonical import build_canonical_series

DIFF_CLASSES = ["EXACT_EXISTING", "NEW_SERIES", "RESULT_UPDATED", "STATUS_UPDATED", "SCORE_CONFLICT",
                "TEAM_NAME_CONFLICT", "DATE_CONFLICT", "UNMATCHED"]
BLOCKING_DIFF = {"SCORE_CONFLICT", "TEAM_NAME_CONFLICT", "DATE_CONFLICT", "UNMATCHED"}
REFRESH_SEASONS_PREFIX = "KPL2026"
ANNUAL_FINALS_LABEL = "2026_ANNUAL_FINALS"
DECISIONS = ["READY_TO_MERGE", "NEEDS_REPLACEMENT_SOURCE", "PARTIAL_SOURCE_NEEDS_SUPPLEMENT"]


def _body_json(bodies, name):
    if name not in bodies:
        return None
    try:
        return json.loads(bodies[name][0].decode("utf-8"))
    except Exception:
        return None


def kv_config(bodies):
    j = _body_json(bodies, "kv_config") or {}
    cfg = (j.get("data") or {}).get("config") or {}
    out = {}
    for k, v in cfg.items():
        try:
            out[k] = json.loads(v) if isinstance(v, str) else v
        except Exception:
            out[k] = v
    return out


def season_list(bodies):
    j = _body_json(bodies, "season_list") or {}
    return ((j.get("data") or {}).get("seasons")) or []


# ---- inventory ----------------------------------------------------------------

def build_inventory(bodies, all_rows, summary):
    meta = {s["seasonid"]: s for s in season_list(bodies)}
    kv = kv_config(bodies)
    kv_names = {}
    for block in (kv.get("kpl_season_select_list") or {}).values():
        for s in block.get("seasons", []):
            kv_names.setdefault(s["seasonid"], s["season_name"])
    rows = []
    for r in summary.itertuples(index=False):
        sid = r.source_competition_id
        g = all_rows[all_rows.source_competition_id == sid]
        m = meta.get(sid, {})
        stages_in_schedule = set(g.stage_id)
        regular = bool(stages_in_schedule & {"cgs1", "cgs2", "cgs3"})
        name = m.get("season_name", "")
        conflict = []
        if "总决赛" in name and regular:
            conflict.append("season_list name says annual finals but schedule contains regular-season rounds")
        if sid in kv_names and name and kv_names[sid] not in name and name not in kv_names[sid]:
            conflict.append(f"kv season_select_list names it '{kv_names[sid]}'")
        rows.append({
            "source_competition_id": sid, "source_competition_name": name or "(not in season list)",
            "kv_select_list_name": kv_names.get(sid, ""), "season_time_desc": m.get("season_time_desc", ""),
            "declared_start": utc8_string(m["start_time"]) if m.get("start_time") else "",
            "declared_end": utc8_string(m["end_time"]) if m.get("end_time") else "",
            "is_cur_season": m.get("is_cur_season", ""), "api_result": r.api_result, "api_msg": r.api_msg,
            "earliest_series_date": g.start_time_raw.min() if len(g) else "",
            "latest_series_date": g.start_time_raw.max() if len(g) else "",
            "total_series": int(len(g)), "completed_series": int((g.status == 4).sum()),
            "scheduled_unplayed_series": int((g.status != 4).sum()),
            "stages_present": "|".join(f"{sid_}:{nm or '(empty)'}" for sid_, nm in
                                       g[["stage_id", "stage"]].drop_duplicates().itertuples(index=False)),
            "unique_teams": int(len(set(g.raw_team_a) | set(g.raw_team_b))),
            "teams": "|".join(sorted(set(g.raw_team_a) | set(g.raw_team_b))),
            "retrieved_at": r.retrieved_at, "raw_source_file": r.raw_source_file,
            "metadata_conflict": "; ".join(conflict),
        })
    return pd.DataFrame(rows)


# ---- diff ---------------------------------------------------------------------

def _pair(a, b):
    return tuple(sorted([str(a), str(b)]))


def build_diff(staging, existing):
    ex = existing.copy()
    ex["match_date"] = ex.start_time_raw.str[:10]
    ex_by_id = ex.set_index("series_id")
    fallback = {}
    for r in ex.itertuples(index=False):
        fallback.setdefault((r.season, r.match_date, _pair(r.team_a, r.team_b)), []).append(r.series_id)
    matched, rows = set(), []
    for r in staging.itertuples(index=False):
        old, method = None, ""
        if r.source_series_id in ex_by_id.index:
            old, method = ex_by_id.loc[r.source_series_id], "SOURCE_SERIES_ID"
        else:
            cands = [c for c in fallback.get((r.season, str(r.start_time_raw)[:10], _pair(r.raw_team_a, r.raw_team_b)), [])
                     if c not in matched]
            if len(cands) == 1:
                old, method = ex_by_id.loc[cands[0]], "FALLBACK_COMPETITION_DATE_TEAMPAIR"
        row = {"source_series_id": r.source_series_id, "season": r.season, "stage": r.stage,
               "new_start_time_raw": r.start_time_raw, "new_team_a": r.raw_team_a, "new_team_b": r.raw_team_b,
               "new_status": r.status, "new_score_a": r.score_a, "new_score_b": r.score_b, "match_method": method}
        if old is None:
            rows.append({**row, "diff_class": "NEW_SERIES", "existing_series_id": "", "detail": ""})
            continue
        matched.add(old.name)
        details, cls = [], "EXACT_EXISTING"
        old_done, new_done = int(old.status) == 4, r.status == 4
        if (old.team_a, old.team_b) != (r.raw_team_a, r.raw_team_b):
            cls = "TEAM_NAME_CONFLICT"; details.append(f"teams {old.team_a} vs {old.team_b} -> {r.raw_team_a} vs {r.raw_team_b}")
        elif old.start_time_raw != r.start_time_raw:
            cls = "DATE_CONFLICT"; details.append(f"start {old.start_time_raw} -> {r.start_time_raw}")
        elif old_done and new_done and (int(old.score_a), int(old.score_b)) != (int(r.score_a), int(r.score_b)):
            cls = "SCORE_CONFLICT"; details.append(f"score {old.score_a}-{old.score_b} -> {r.score_a}-{r.score_b}")
        elif old_done and not new_done:
            cls = "SCORE_CONFLICT"; details.append(f"completed result retracted: status {old.status} -> {r.status}")
        elif not old_done and new_done:
            cls = "RESULT_UPDATED"; details.append(f"status {old.status} -> 4, score {r.score_a}-{r.score_b}")
        elif int(old.status) != r.status:
            cls = "STATUS_UPDATED"; details.append(f"status {old.status} -> {r.status}")
        if str(old.stage) != str(r.stage):
            details.append(f"stage '{old.stage}' -> '{r.stage}'")
        rows.append({**row, "diff_class": cls, "existing_series_id": old.name, "detail": "; ".join(details),
                     "old_start_time_raw": old.start_time_raw, "old_team_a": old.team_a, "old_team_b": old.team_b,
                     "old_status": int(old.status), "old_score_a": int(old.score_a), "old_score_b": int(old.score_b)})
    for sid, r in ex_by_id.iterrows():
        if sid not in matched:
            rows.append({"source_series_id": "", "existing_series_id": sid, "season": r.season, "stage": r.stage,
                         "old_start_time_raw": r.start_time_raw, "old_team_a": r.team_a, "old_team_b": r.team_b,
                         "old_status": int(r.status), "diff_class": "UNMATCHED", "match_method": "",
                         "detail": "existing row not returned by the refreshed source"})
    cols = ["diff_class", "match_method", "source_series_id", "existing_series_id", "season", "stage",
            "old_start_time_raw", "new_start_time_raw", "old_team_a", "old_team_b", "new_team_a", "new_team_b",
            "old_status", "new_status", "old_score_a", "old_score_b", "new_score_a", "new_score_b", "detail"]
    d = pd.DataFrame(rows).reindex(columns=cols)
    return d.sort_values(["season", "diff_class", "source_series_id", "existing_series_id"], kind="stable").reset_index(drop=True)


# ---- coverage -----------------------------------------------------------------

def _progress(bodies, sid):
    j = _body_json(bodies, f"progress_{sid}") or {}
    return {s["stage_id"]: s for s in ((j.get("data") or {}).get("stage_list") or [])}


def build_coverage(staging, existing_canonical, bodies):
    kv = kv_config(bodies)
    bracket = {b["seasonid"]: {x["scheduleid"] for x in b["schedule_list"]} for b in kv.get("kpl_jhs_match") or []}
    finals = {}
    for b in kv.get("kpl_js_match") or []:
        finals.setdefault(b["seasonid"], set()).add(b["scheduleid"])
    rows = []
    s26 = staging[staging.season.str.startswith(REFRESH_SEASONS_PREFIX)]
    for (sid, stage_id), g in s26.groupby(["season", "stage_id"], sort=True):
        prog = _progress(bodies, sid).get(stage_id)
        expected, evidence = None, []
        if prog and prog.get("groups"):
            expected = sum(comb(len(gr["teams"]), 2) for gr in prog["groups"])
            wins = sum(t["wins"] for gr in prog["groups"] for t in gr["teams"])
            evidence.append(f"source standings: {len(prog['groups'])} groups of "
                            f"{'/'.join(str(len(gr['teams'])) for gr in prog['groups'])} teams -> {expected} "
                            f"round-robin series; standings wins total {wins}")
            if wins != int((g.status == 4).sum()):
                evidence.append("STANDINGS_WINS_MISMATCH")
        elif stage_id == "jhs" and sid in bracket:
            ids = bracket[sid] - finals.get(sid, set())
            expected = len(ids)
            same = ids == set(g.source_series_id)
            evidence.append(f"source bracket config kpl_jhs_match declares {expected} playoff schedule IDs; "
                            f"retrieved IDs {'match exactly' if same else 'DO NOT match'}")
            if not same:
                expected = None
        elif stage_id == "js" and sid in finals:
            expected = len(finals[sid])
            same = finals[sid] == set(g.source_series_id)
            evidence.append(f"source kpl_js_match declares {expected} final schedule ID(s); "
                            f"retrieved {'match' if same else 'DO NOT match'}")
            if not same:
                expected = None
        else:
            evidence.append("no structural expected count in source (stage not in standings or bracket config)")
        completed = int((g.status == 4).sum())
        if expected is None:
            status = "UNKNOWN"
        elif completed == expected == len(g) and "STANDINGS_WINS_MISMATCH" not in evidence:
            status = "COMPLETE"
        else:
            status = "PARTIAL"
        cur = existing_canonical[(existing_canonical.season == sid) & existing_canonical.series_id.isin(g.source_series_id)]
        rows.append({"season": sid, "stage_id": stage_id, "stage": g.stage.iloc[0] or "(empty in source)",
                     "expected_or_discovered_series": expected if expected is not None else pd.NA,
                     "retrieved_series": len(g), "completed_series": completed,
                     "scheduled_series": int((g.status != 4).sum()),
                     "missing_series": (expected - completed) if expected is not None else pd.NA,
                     "earliest_date": g.start_time_raw.min(), "latest_date": g.start_time_raw.max(),
                     "unique_teams": len(set(g.raw_team_a) | set(g.raw_team_b)),
                     "coverage_status": status, "evidence": "; ".join(evidence),
                     "current_series": len(cur), "current_completed_series": int(cur.is_label_eligible.sum())})
    meta = {s["seasonid"]: s for s in season_list(bodies)}
    window = "; ".join(f"{k}: '{v['season_name']}' {v.get('season_time_desc', '')}" for k, v in meta.items()
                       if k.startswith(REFRESH_SEASONS_PREFIX) and "总决赛" in v.get("season_name", ""))
    rows.append({"season": ANNUAL_FINALS_LABEL, "stage_id": "ALL", "stage": "ALL",
                 "expected_or_discovered_series": pd.NA, "retrieved_series": 0, "completed_series": 0,
                 "scheduled_series": 0, "missing_series": pd.NA, "earliest_date": "", "latest_date": "",
                 "unique_teams": 0, "coverage_status": "UNKNOWN",
                 "evidence": "no schedule published in source (KPL2026S3: 'season not found'); season-list metadata "
                             f"only: {window or 'none'}", "current_series": 0, "current_completed_series": 0})
    return pd.DataFrame(rows)


# ---- missing manifest ----------------------------------------------------------

def build_missing_manifest(coverage, inventory, staging_canonical, bodies):
    checked = "kplow getScheduleList / getSeasonAndStageAndTeamList / getScheduleProgress / getKVConfig"
    rows = []
    af = coverage[coverage.season == ANNUAL_FINALS_LABEL].iloc[0]
    rows.append({"season": ANNUAL_FINALS_LABEL, "stage": "ALL", "date_if_known": "10月2日至11月14日 per season-list text (unverified)",
                 "team_a_if_known": "", "team_b_if_known": "",
                 "missing_field": "entire schedule: series, dates, participants, groups, seeds",
                 "reason": "not yet published by the source at retrieval time; prospective holdout, never a development label",
                 "source_checked": checked})
    for r in coverage[(coverage.season != ANNUAL_FINALS_LABEL) & (coverage.coverage_status != "COMPLETE")].itertuples():
        rows.append({"season": r.season, "stage": f"{r.stage_id}:{r.stage}", "date_if_known": f"{r.earliest_date}..{r.latest_date}",
                     "team_a_if_known": "", "team_b_if_known": "",
                     "missing_field": "structural expected series count" if r.coverage_status == "UNKNOWN" else "series",
                     "reason": ("retrieved series are all completed, but the source declares no expected count for this "
                                "stage, so completeness cannot be proven" if r.coverage_status == "UNKNOWN"
                                else f"{r.missing_series} expected series missing"), "source_checked": checked})
    empty = staging_canonical[staging_canonical.stage == ""]
    for season, g in empty.groupby("season"):
        rows.append({"season": season, "stage": "|".join(sorted(set(g.stage_id_src))), "date_if_known": "",
                     "team_a_if_known": "", "team_b_if_known": "", "missing_field": "stage_name",
                     "reason": f"{len(g)} rows have an empty stage_name in the source (stage_id present); not filled",
                     "source_checked": checked})
    unres = staging_canonical[staging_canonical.identity_resolution_status != "RESOLVED"]
    for name in sorted({n for r in unres.itertuples() for n, c in [(r.raw_team_a, r.canonical_team_a_id), (r.raw_team_b, r.canonical_team_b_id)] if pd.isna(c)}):
        g = unres[(unres.raw_team_a == name) | (unres.raw_team_b == name)]
        rows.append({"season": "|".join(sorted(set(g.season))), "stage": "ALL",
                     "date_if_known": f"{g.start_time_raw.min()}..{g.start_time_raw.max()}", "team_a_if_known": name,
                     "team_b_if_known": "", "missing_field": "canonical team identity",
                     "reason": f"new observed name, not in the reviewed registry; {len(g)} series UNRESOLVED",
                     "source_checked": "data/dimensions/team_identity_registry.csv"})
    for r in inventory[inventory.api_result != 0].itertuples():
        rows.append({"season": r.source_competition_id, "stage": "ALL", "date_if_known": "", "team_a_if_known": "",
                     "team_b_if_known": "", "missing_field": "entire season",
                     "reason": f"source returned result={r.api_result} '{r.api_msg}' and the season is not in the season list",
                     "source_checked": checked})
    older = inventory[(inventory.api_result == 0) & (inventory.source_competition_id < "KPL2022")]
    if len(older):
        rows.append({"season": "|".join(older.source_competition_id), "stage": "ALL",
                     "date_if_known": f"{older.earliest_series_date.min()}..{older.latest_series_date.max()}",
                     "team_a_if_known": "", "team_b_if_known": "", "missing_field": "not ingested",
                     "reason": f"AVAILABLE in the original source ({int(older.total_series.sum())} series) but outside "
                               "the benchmark universe; the original crawler hard-coded END_YEAR=2022. Not merged.",
                     "source_checked": checked})
    return pd.DataFrame(rows)


# ---- staging canonicalization ---------------------------------------------------

def staging_as_series(staging):
    s = pd.DataFrame({
        "series_id": staging.source_series_id, "season": staging.season, "stage": staging.stage,
        "stage_id_src": staging.stage_id, "start_time_raw": staging.start_time_raw,
        "start_time": pd.to_datetime(staging.start_time_raw), "team_a": staging.raw_team_a,
        "team_b": staging.raw_team_b, "score_a": staging.score_a.astype("float"),
        "score_b": staging.score_b.astype("float"), "status": staging.status.astype("float"),
    })
    decisive = s.score_a.notna() & s.score_b.notna() & (s.score_a != s.score_b)
    s["label_flag"] = np.where((s.status == 4) & decisive, "COMPLETED",
                               np.where(s.status == 4, "FINISHED_NO_DECISIVE_SCORE", "NOT_FINISHED"))
    s["start_time_is_epoch_fallback"] = False
    return s


def canonicalize_staging(staging, registry, retrieved_at, holdout_start):
    s = staging_as_series(staging)
    canon, audit, checks = build_canonical_series(s.drop(columns=["stage_id_src"]), registry)
    canon = canon.merge(s[["series_id", "stage_id_src"]], on="series_id", how="left")
    canon = canon.merge(staging[["source_series_id", "raw_record_hash", "raw_source_file"]]
                        .rename(columns={"source_series_id": "series_id"}), on="series_id", how="left")
    ret = pd.Timestamp(retrieved_at).tz_convert("Asia/Shanghai").tz_localize(None) if pd.Timestamp(retrieved_at).tzinfo else pd.Timestamp(retrieved_at)
    lab = canon[canon.is_label_eligible]
    checks = {**checks,
              "no_duplicate_source_series_id": bool(not staging.source_series_id.duplicated().any()),
              "no_completed_result_after_retrieval_time": bool((lab.start_time <= ret).all()),
              "no_label_at_or_after_prospective_holdout_start": bool((lab.start_time < holdout_start).all())}
    return canon, audit, checks


# ---- team_a forensics ----------------------------------------------------------

def team_city(name, cities):
    for c in sorted(cities, key=len, reverse=True):
        if c and str(name).startswith(c):
            return c
    return ""


def team_a_tables(staging):
    done = staging[staging.status == 4].copy()
    done["team_a_win"] = (done.score_a > done.score_b).astype(int)
    bias = done.groupby(["season", "stage_id", "stage"], sort=True).agg(
        n=("team_a_win", "size"), team_a_wins=("team_a_win", "sum")).reset_index()
    bias["team_a_win_rate"] = bias.team_a_wins / bias.n
    missing_loc = {"", "0", "None"}
    cities = set(staging.location_name.dropna().astype(str)) - missing_loc
    done["city_a"] = [team_city(n, cities) for n in done.raw_team_a]
    done["city_b"] = [team_city(n, cities) for n in done.raw_team_b]
    no_venue = done.location_name.isna() | done.location_name.astype(str).isin(missing_loc)
    host = np.select([no_venue,
                      (done.city_a == done.location_name) & (done.city_b != done.location_name),
                      (done.city_b == done.location_name) & (done.city_a != done.location_name),
                      (done.city_a == done.location_name) & (done.city_b == done.location_name)],
                     ["VENUE_NOT_RECORDED", "TEAM_A_CITY_HOSTS", "TEAM_B_CITY_HOSTS", "BOTH_SAME_CITY"],
                     "NEITHER_CITY_HOSTS")
    done["venue_relation"] = host
    venue = done.groupby(["season", "venue_relation"]).agg(n=("team_a_win", "size"),
                                                           team_a_wins=("team_a_win", "sum")).reset_index()
    venue["team_a_win_rate"] = venue.team_a_wins / venue.n
    return bias, venue, done


def playoff_seed_table(staging, bodies):
    """For 2026 playoff/final series, compare team_a vs team_b rank in the last group stage's source standings."""
    rows = []
    for sid in sorted(staging.season[staging.season.str.startswith(REFRESH_SEASONS_PREFIX)].unique()):
        prog = _progress(bodies, sid)
        group_stages = [k for k, v in prog.items() if v.get("groups")]
        if not group_stages:
            continue
        last = sorted(group_stages)[-1]
        rank = {}
        for gi, gr in enumerate(prog[last]["groups"]):
            for ti, t in enumerate(gr["teams"]):
                rank[t["team_name"]] = (gi, ti)
        g = staging[(staging.season == sid) & staging.stage_id.isin(["jhs", "js"])]
        for r in g.itertuples():
            ra, rb = rank.get(r.raw_team_a), rank.get(r.raw_team_b)
            rel = ("UNRANKED" if ra is None or rb is None else
                   "TEAM_A_BETTER_STANDING" if ra < rb else "TEAM_B_BETTER_STANDING")
            rows.append({"season": sid, "source_series_id": r.source_series_id, "stage_id": r.stage_id,
                         "raw_team_a": r.raw_team_a, "raw_team_b": r.raw_team_b, "standings_stage": last,
                         "team_a_group_rank": None if ra is None else f"{ra[0]}:{ra[1] + 1}",
                         "team_b_group_rank": None if rb is None else f"{rb[0]}:{rb[1] + 1}", "relation": rel,
                         "team_a_win": int(r.score_a > r.score_b) if r.status == 4 else None})
    return pd.DataFrame(rows)


# ---- decision gate ------------------------------------------------------------

def decide(inventory, coverage, diff, staging, canon_audit, canon_checks):
    endpoint_ok = bool((inventory.api_result == 0).any())
    s26 = coverage[coverage.season.isin(["KPL2026S1", "KPL2026S2"])]
    seasons_found = set(s26.season)
    partial = bool((s26.coverage_status == "PARTIAL").any()) or seasons_found != {"KPL2026S1", "KPL2026S2"}
    if not endpoint_ok:
        decision = "NEEDS_REPLACEMENT_SOURCE"
    elif partial:
        decision = "PARTIAL_SOURCE_NEEDS_SUPPLEMENT"
    else:
        decision = "READY_TO_MERGE"
    blocking_diff = diff[diff.diff_class.isin(BLOCKING_DIFF)]
    blockers = []
    if len(blocking_diff):
        blockers.append(f"{len(blocking_diff)} blocking diff rows: {blocking_diff.diff_class.value_counts().to_dict()}")
    if canon_audit["unresolved_series"] or canon_audit["conflicted_series"]:
        blockers.append(f"identity: {canon_audit['unresolved_series']} unresolved, "
                        f"{canon_audit['conflicted_series']} conflicted staging series")
    failed = [k for k, v in canon_checks.items() if not v]
    if failed:
        blockers.append(f"failed checks: {failed}")
    return {"decision": decision, "endpoint_works": endpoint_ok, "merge_allowed": decision == "READY_TO_MERGE" and not blockers,
            "merge_blockers": blockers, "coverage_status_2026": s26[["season", "stage_id", "coverage_status"]]
            .to_dict("records"), "diff_counts": diff.diff_class.value_counts().to_dict()}
