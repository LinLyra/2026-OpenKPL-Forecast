"""v0.4 Phase B build: games, appearances, players, rosters, player-hero history, WZRY linkage, drafts, features."""
import json
from pathlib import Path

import pandas as pd

from openkpl.history import drafts, players, report, tables, wzry_full
from openkpl.history.collect_full import PHASE_A_STORE, PHASE_B_STORE
from openkpl.roster import baseline
from openkpl.roster.raw_store import RawStore

WZRY = "data/raw/external/HoK-BP-LLM/王者荣耀KPL历年比赛数据/WZRY.csv"
P = Path("data/processed")
RC, RW = Path("reports/roster_collection"), Path("reports/wzry_linkage")


def check_locks():
    a = baseline.check_lock(json.loads(Path("reports/roster_audit/baseline_lock.json").read_text()))
    b = baseline.check_lock(json.loads((RC / "phase_b_lock.json").read_text()))
    if a or b:
        raise SystemExit(f"HARD FAILURE: locked artifacts mutated: {a + b}")
    return len(json.loads((RC / "phase_b_lock.json").read_text())["artifacts"])


def manifest_entries():
    out = []
    for root in (PHASE_A_STORE, PHASE_B_STORE):
        for e in RawStore(root, transport=None, pause=0).entries():
            out.append(dict(e, store=root))
    return out


def collection_manifest(canonical, entries, games, season_names):
    det = [e for e in entries if "getScheduleDetail" in e["url"]]
    by_sid = {}
    for e in det:
        by_sid.setdefault(e["source_ids"].get("scheduleid"), []).append(e)
    gc = games.groupby("series_id")
    rows = []
    for s in canonical.itertuples(index=False):
        es = sorted(by_sid.get(s.series_id, []), key=lambda e: e["retrieved_at"])
        last = es[-1] if es else None
        result = None
        if last and last["http_status"] == 200:
            try:
                result = json.loads((Path(last["store"]) / last["file"]).read_bytes()).get("result")
            except ValueError:
                result = "NOT_JSON"
        g = gc.get_group(s.series_id) if s.series_id in gc.groups else None
        n = 0 if g is None else len(g)
        lineup_ok = 0 if g is None else int((g.n_players == 10).sum())
        winners = 0 if g is None else int(g.winner_team_id.notna().sum())
        status = ("FETCHED" if result == 0 else "FAILED") if es else "NOT_ATTEMPTED"
        rows.append({
            "series_id": s.series_id, "season_id": s.season, "season": season_names.get(s.season, ""), "stage": s.stage,
            "request_status": status, "http_status": last["http_status"] if last else None, "source_result": result,
            "games_returned": n, "expected_games": int(s.score_a + s.score_b),
            "game_count_matches": n == int(s.score_a + s.score_b),
            "lineup_availability": "NONE" if lineup_ok == 0 else ("FULL" if lineup_ok == n else "PARTIAL"),
            "games_with_10_players": lineup_ok,
            "winner_availability": "NONE" if winners == 0 else ("FULL" if winners == n else "PARTIAL"),
            "games_with_winner": winners, "error": "; ".join(e["error"] for e in es if e["error"]) or None,
            "retry_count": max(len(es) - 1, 0), "store": last["store"] if last else None,
            "raw_file": last["file"] if last else None,
        })
    return pd.DataFrame(rows)


def raw_provenance(entries):
    return pd.DataFrame([{
        "store": e["store"], "file": e["file"], "request": f"{e['method']} {e['url']}",
        "payload": json.dumps(e["payload"], ensure_ascii=False) if e["payload"] else "",
        "retrieval_timestamp": e["retrieved_at"], "sha256": e["sha256"], "bytes": e["bytes"],
        "source_identifiers": json.dumps(e.get("source_ids") or {}, ensure_ascii=False),
        "http_status": e["http_status"], "error": e["error"] or "", "discovery": e["discovery"]} for e in entries])


def hero_rank_pairs():
    pairs = []
    for f in Path(PHASE_A_STORE).glob("getHeroRankList_*.json"):
        d = json.loads(f.read_bytes()).get("data") or {}
        for rows in d.values():
            pairs += [(r["hero_name"], r["hero_id"]) for r in rows or [] if r.get("hero_id")]
    return pairs


def main():
    n_locked = check_locks()
    for d in [P / "games", P / "rosters", P / "features", P / "drafts", RC, RW, Path("data/dimensions")]:
        d.mkdir(parents=True, exist_ok=True)
    canonical = pd.read_parquet(f"{baseline.TEMPORAL}/canonical_series.parquet")
    registry = pd.read_csv("data/dimensions/team_identity_registry.csv")
    canon_names = dict(zip(registry.observed_name, registry.canonical_team_id))
    sched, season_names = tables.snapshot_schedules()
    games, apps = tables.build(canonical, tables.detail_responses(), sched, season_names, tables.combo_battles())
    games.to_parquet(P / "games/kpl_games.parquet", index=False)
    apps.to_parquet(P / "games/player_game_appearances.parquet", index=False)

    entries = manifest_entries()
    collection_manifest(canonical, entries, games, season_names).to_csv(RC / "collection_manifest.csv", index=False)
    raw_provenance(entries).to_csv(RC / "raw_provenance.csv", index=False)

    reg = players.player_registry(apps, games)
    reg.to_csv("data/dimensions/player_identity_registry.csv", index=False)
    players.identity_candidates(apps, games, reg).to_csv(RC / "player_identity_candidates.csv", index=False)
    players.series_usage(apps).to_parquet(P / "rosters/series_player_usage.parquet", index=False)
    players.rotation_summary(apps).to_parquet(P / "rosters/series_rotation_summary.parquet", index=False)
    players.player_hero_temporal(apps, games).to_parquet(P / "features/player_hero_temporal.parquet", index=False)

    wz = pd.read_csv(WZRY, encoding="gb18030")
    cand = wzry_full.kplow_candidates(apps, games)
    link = wzry_full.link(wz, cand, canon_names, games)
    link.to_parquet(P / "drafts/wzry_game_linkage.parquet", index=False)
    summary, by_season, by_team, amb = wzry_full.summaries(link)
    summary = pd.concat([summary, pd.DataFrame([{"metric": "candidate_universe_games", "value": len(cand)}])])
    summary.to_csv(RW / "full_linkage_summary.csv", index=False)
    by_season.to_csv(RW / "linkage_by_season.csv", index=False)
    by_team.to_csv(RW / "linkage_by_team.csv", index=False)
    amb.to_csv(RW / "linkage_ambiguities.csv", index=False)
    u = link[link.linkage_status.isin(["UNIQUE_EXACT_MATCH", "SOURCE_CONFLICT"]) & link.game_key.notna()]
    u[["wzry_row_id", "game_key", "linkage_status", "winner_wzry", "winner_kplow", "winner_agreement", "quality_flags"]] \
        .to_csv(RW / "winner_validation.csv", index=False)

    idg = drafts.identified_games(link, wz, games)
    idg.to_parquet(P / "drafts/identified_draft_games.parquet", index=False)
    name_to_id = drafts.hero_id_map(apps, hero_rank_pairs())
    ev = drafts.draft_events(idg, canon_names, name_to_id)
    ev.to_parquet(P / "drafts/draft_events_identified.parquet", index=False)
    hf, sf, cf = drafts.temporal_features(idg, ev, apps)
    hf.to_parquet(P / "features/hero_temporal_features.parquet", index=False)
    sf.to_parquet(P / "features/hero_synergy_temporal.parquet", index=False)
    cf.to_parquet(P / "features/hero_counter_temporal.parquet", index=False)
    drafts.series_hero_usage(apps, games).to_parquet(P / "features/series_hero_usage.parquet", index=False)

    T = report.load()
    man = pd.read_csv(RC / "collection_manifest.csv")
    cand_pairs = pd.read_csv(RC / "player_identity_candidates.csv") if (RC / "player_identity_candidates.csv").stat().st_size > 1 else pd.DataFrame()
    report.season_coverage(canonical, man, T).to_csv(RC / "season_coverage.csv", index=False)
    report.quality(canonical, man, T, reg, cand_pairs).to_csv(RC / "full_collection_quality.csv", index=False)
    by_season, by_game = report.global_bp_table(T["shu"])
    by_season.to_csv(RC / "global_bp_repeat_by_season.csv", index=False)
    by_game.to_csv(RC / "global_bp_own_repeat_by_game_number.csv", index=False)

    print("locked artifacts verified before build:", n_locked)
    print("after build lock check:", check_locks())


if __name__ == "__main__":
    main()
