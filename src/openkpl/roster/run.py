"""Build v0.4 Phase A roster-audit tables from saved raw responses (no network)."""
import json
from pathlib import Path

import pandas as pd

from openkpl.roster import audit, baseline, wzry_link
from openkpl.roster.load import tables

RAW = "data/raw/roster_discovery/2026-09-29/api_sample"
OUT = Path("reports/roster_audit")
WZRY = "data/raw/external/HoK-BP-LLM/王者荣耀KPL历年比赛数据/WZRY.csv"


SAMPLE_SERIES = ["KPL2026S1M1W2D1", "KPL2026S1M1W1D1", "KPL2026S1M10W1D1", "KPL2026S1M10W1D12",
                 "KPL2026S2M1W1D1", "KPL2026S2M1W2D1", "KPL2026S2M7W1D2", "KPL2026S2M18W1D1",
                 "KPL2025S2M1W1D1", "KPL2024S1M1W1D1", "KPL2023S1M1W1D3", "KPL2022S1M1W1D1"]


def provenance(root_dirs):
    rows = []
    for d in root_dirs:
        for line in (Path(d) / "MANIFEST.jsonl").read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            schema = ""
            if e["http_status"] == 200 and e["file"].endswith(".json"):
                try:
                    j = json.loads((Path(d) / e["file"]).read_bytes())
                    data = j.get("data")
                    schema = f"result={j.get('result')}; data={type(data).__name__}"
                    if isinstance(data, dict):
                        schema += "; keys=" + ",".join(sorted(data)[:12])
                    elif isinstance(data, list):
                        schema += f"; len={len(data)}"
                except ValueError:
                    schema = "not JSON"
            rows.append({"directory": d, "file": e["file"], "request": f"{e['method']} {e['url']}",
                         "payload": json.dumps(e["payload"], ensure_ascii=False) if e["payload"] else "",
                         "retrieval_timestamp": e["retrieved_at"], "sha256": e["sha256"], "bytes": e["bytes"],
                         "source_identifiers": json.dumps(e.get("source_ids") or {}, ensure_ascii=False),
                         "http_status": e["http_status"], "error": e["error"] or "", "schema_notes": schema,
                         "discovery": e["discovery"]})
    return pd.DataFrame(rows)


def sample_verification(canonical, T):
    c = canonical.set_index("series_id")
    g, gp, cb = T["games"], T["game_players"], T["combo"]
    rows = []
    for sid in SAMPLE_SERIES:
        r = c.loc[sid]
        gs, gps = g[g.scheduleid == sid], gp[gp.scheduleid == sid]
        b = cb[cb.scheduleid == sid].drop_duplicates("battle_id")
        rows.append({
            "series_id": sid, "competition_id": r.season, "season": r.season, "stage": r.stage,
            "start_time": r.start_time, "team_a": r.canonical_team_a_id, "team_b": r.canonical_team_b_id,
            "series_score": f"{int(r.score_a)}-{int(r.score_b)}", "games_in_source": len(gs),
            "game_id": f"battle_id for {len(b)}/{len(gs)} games" if len(gs) else "", "game_number": "round (1..N)",
            "game_start_time": "ABSENT (battle_id epoch prefix for combo games)" if len(b) else "ABSENT",
            "duration": f"{len(b)}/{len(gs)} via combo endpoint", "blue_team": "ABSENT", "red_team": "ABSENT",
            "winner": f"{int((gs.win_team_slot != '').sum())}/{len(gs)}",
            "player_id": f"{int((gps.playerid != '').sum())}/{len(gps)} rows",
            "role": f"{int(gps.position.between(1, 5).sum())}/{len(gps)} rows labeled 1-5",
            "hero_id": f"{int((gps.hero_id > 0).sum())}/{len(gps)} rows",
            "kda_gold_damage": "ABSENT", "bp": f"picks+order for {len(b)}/{len(gs)} games; bans ABSENT",
        })
    return pd.DataFrame(rows)


def main():
    canonical = pd.read_parquet(f"{baseline.TEMPORAL}/canonical_series.parquet")
    registry = pd.read_csv("data/dimensions/team_identity_registry.csv")
    lock = json.loads((OUT / "baseline_lock.json").read_text())
    lock_problems = baseline.check_lock(lock)
    T, slot_names = tables(RAW)
    s2c = audit.slot_canon(slot_names, registry)
    T["game_players"] = T["game_players"].copy()
    flags = audit.game_flags(T["game_players"])

    combo_lists, perf_counts = {}, T["perf"].groupby("season").size().to_dict()
    for f in Path(RAW).glob("getSeasonHeroCombo_*.json"):
        d = json.loads(f.read_bytes())["data"] or {}
        combo_lists[f.stem.split("_")[-1]] = len({c["heros"] for k in ("high_appearance_list", "high_win_rate_list") for c in d.get(k) or []})

    provenance([RAW, str(Path(RAW).parent / "site")]).to_csv(OUT / "provenance_manifest.csv", index=False)
    sample_verification(canonical, T).to_csv(OUT / "sample_verification.csv", index=False)
    audit.coverage_2026(canonical, T, flags).to_csv(OUT / "coverage_2026.csv", index=False)
    audit.historical_coverage(canonical, T, flags, combo_lists, perf_counts).to_csv(OUT / "historical_coverage.csv", index=False)
    audit.temporal_linkage(canonical, T).to_csv(OUT / "temporal_linkage.csv", index=False)
    audit.player_identity(T, s2c, canonical, slot_names).to_csv(OUT / "player_identity_inventory.csv", index=False)
    audit.data_quality(canonical, T, flags, lock_problems).to_csv(OUT / "data_quality.csv", index=False)

    canon_names = dict(zip(registry.observed_name, registry.canonical_team_id))
    w = wzry_link.wzry_games(pd.read_csv(WZRY, encoding="gb18030"))
    k = wzry_link.kplow_games(T["game_players"], T["games"], slot_names)
    universe = sorted(k.scheduleid.str[:9].unique())
    res = [dict(direction="WZRY->kplow", **wzry_link.match_counts(w, k, lvl, canon_names)) for lvl in wzry_link.LEVELS]
    k2 = k[k.scheduleid.str[:9].isin(["KPL2023S1", "KPL2023S2"])]
    res += [dict(direction="kplow(2023 full)->WZRY", **wzry_link.match_counts(k2, w, lvl, canon_names)) for lvl in wzry_link.LEVELS]
    pd.DataFrame(res).to_csv(OUT / "wzry_linkage_counts.csv", index=False)
    pairs = wzry_link.matched_pairs(w, k, "F3W_pair_team_heroes_winner", canon_names)
    p3 = wzry_link.matched_pairs(w, k, "F3_pair_team_heroes", canon_names)
    pairs = pairs.merge(p3[["wzry_row", "n_candidates", "candidate"]].rename(
        columns={"n_candidates": "n_candidates_F3", "candidate": "candidate_F3"}), on="wzry_row")
    kk = k.assign(key=k.scheduleid + "#" + k["round"].astype(str)).set_index("key")
    wz = w.set_index("wzry_row")
    one = pairs[pairs.n_candidates_F3 == 1].copy()
    one["winner_status"] = [
        "KPLOW_WINNER_BLANK" if not kk.loc[c, "winner"] else
        ("AGREE" if canon_names.get(wz.loc[r, "winner"]) == canon_names.get(kk.loc[c, "winner"]) else "DISAGREE")
        for r, c in zip(one.wzry_row, one.candidate_F3)]
    chron = canonical.set_index("series_id").chronological_order
    one["chronological_order"] = one.candidate_F3.str.split("#").str[0].map(chron)
    one["round"] = one.candidate_F3.str.split("#").str[1].astype(int)
    pairs = pairs.merge(one[["wzry_row", "winner_status", "chronological_order", "round"]], on="wzry_row", how="left")
    pairs.to_csv(OUT / "wzry_linkage_sample.csv", index=False)
    srt = one.sort_values("wzry_row")
    order_key = srt.chronological_order * 10 + srt["round"]
    summary = {
        "lock_problems": lock_problems, "kplow_universe_seasons": universe, "kplow_games_in_universe": len(k),
        "wzry_rows": len(w), "wzry_team_names_mapped": int(w.team1.isin(canon_names).sum() + w.team2.isin(canon_names).sum()),
        "wzry_team_name_slots": 2 * len(w),
        "wzry_unmapped_team_names": sorted((set(w.team1) | set(w.team2)) - set(canon_names)),
        "wzry_rows_with_unmapped_team": int((~w.team1.isin(canon_names) | ~w.team2.isin(canon_names)).sum()),
        "kplow_unmapped_team_names": sorted((set(k.team1) | set(k.team2)) - set(canon_names)),
        "hero_names_wzry_not_in_kplow": sorted(set().union(*w.heroes1, *w.heroes2) - set(T["game_players"].hero_name)),
        "matched_by_season_F3W": pairs[pairs.n_candidates == 1].candidate.str[:9].value_counts().to_dict(),
        "F3_unique_matches": len(one), "F3_winner_status": one.winner_status.value_counts().to_dict(),
        "F3_unique_matches_by_season": one.candidate_F3.str[:9].value_counts().to_dict(),
        "wzry_row_vs_chronology_spearman": round(float(srt.wzry_row.corr(order_key, method="spearman")), 4) if len(srt) > 2 else None,
        "wzry_row_order_monotonic_share": round(float((order_key.diff().dropna() > 0).mean()), 4) if len(srt) > 2 else None,
        "untestable_fingerprints": wzry_link.UNTESTABLE,
    }
    (OUT / "wzry_linkage_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "hero_names_wzry_not_in_kplow"}, ensure_ascii=False, indent=1))
    print(pd.DataFrame(res).to_string())


if __name__ == "__main__":
    main()
