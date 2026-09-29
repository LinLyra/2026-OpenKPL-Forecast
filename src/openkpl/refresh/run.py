"""Orchestrates the v0.3.1 refresh audit from an immutable snapshot. Writes staging + reports only."""
import json
from pathlib import Path

import pandas as pd

from openkpl.identity.registry import read_registry
from openkpl.refresh import audit as A
from openkpl.refresh.normalize import duplicate_source_ids, normalize_schedules
from openkpl.refresh.snapshot import load_snapshot

STAGING_MIN_SEASON = "KPL2022"


def run_refresh_audit(snapshot_dir, existing_series_path, existing_canonical_path, registry_path,
                      report_dir, staging_dir, holdout_start):
    report_dir, staging_dir = Path(report_dir), Path(staging_dir)
    report_dir.mkdir(parents=True, exist_ok=True); staging_dir.mkdir(parents=True, exist_ok=True)
    manifest, bodies = load_snapshot(snapshot_dir)
    all_rows, summary = normalize_schedules(bodies)
    dups = duplicate_source_ids(all_rows)
    if dups:
        raise ValueError(f"duplicate source series IDs in snapshot: {dups[:10]}")
    staging = all_rows[all_rows.season >= STAGING_MIN_SEASON].reset_index(drop=True)
    staging.to_parquet(staging_dir / "2026_temporal_refresh.parquet", index=False)

    existing = pd.read_parquet(existing_series_path)
    existing_canon = pd.read_parquet(existing_canonical_path)
    inventory = A.build_inventory(bodies, all_rows, summary)
    diff = A.build_diff(staging, existing)
    coverage = A.build_coverage(staging, existing_canon, bodies)
    reg = read_registry(registry_path)
    canon, canon_audit, canon_checks = A.canonicalize_staging(staging, reg, manifest["completed_at"], holdout_start)
    canon.to_parquet(staging_dir / "2026_temporal_refresh_canonical.parquet", index=False)
    missing = A.build_missing_manifest(coverage, inventory, canon, bodies)
    bias, venue, _ = A.team_a_tables(staging)
    seeds = A.playoff_seed_table(staging, bodies)
    gate = A.decide(inventory, coverage, diff, staging, canon_audit, canon_checks)

    w = lambda df, name: df.to_csv(report_dir / name, index=False, encoding="utf-8-sig")  # noqa: E731
    w(inventory, "source_competition_inventory.csv")
    w(diff, "refresh_diff.csv")
    w(diff.groupby(["season", "diff_class"]).size().rename("n").reset_index(), "refresh_diff_summary.csv")
    w(coverage, "coverage_2026.csv")
    w(missing, "missing_series_manifest.csv")
    w(bias, "team_a_bias.csv")
    w(venue, "team_a_venue_crosstab.csv")
    w(seeds, "team_a_playoff_standings_crosstab.csv")
    summary_out = {"snapshot": str(snapshot_dir), "snapshot_retrieved_at": manifest["retrieved_at"],
                   "staging_rows": int(len(staging)), "staging_seasons": sorted(staging.season.unique()),
                   "canonicalization_audit": canon_audit, "checks": canon_checks, **gate}
    (report_dir / "refresh_audit_summary.json").write_text(json.dumps(summary_out, ensure_ascii=False, indent=2,
                                                                      default=str), encoding="utf-8")
    (report_dir / "team_a_semantics.md").write_text(render_team_a(bias, venue, seeds, staging), encoding="utf-8")
    return {"staging": staging, "inventory": inventory, "diff": diff, "coverage": coverage, "missing": missing,
            "canon": canon, "canon_audit": canon_audit, "checks": canon_checks, "gate": gate, "bias": bias,
            "venue": venue, "seeds": seeds, "manifest": manifest}


def render_team_a(bias, venue, seeds, staging):
    tot = bias[["n", "team_a_wins"]].sum()
    v = venue.groupby("venue_relation")[["n", "team_a_wins"]].sum()
    v["rate"] = v.team_a_wins / v.n
    host_share = (v.loc["TEAM_A_CITY_HOSTS", "n"] / (v.loc["TEAM_A_CITY_HOSTS", "n"] + v.loc["TEAM_B_CITY_HOSTS", "n"])
                  if {"TEAM_A_CITY_HOSTS", "TEAM_B_CITY_HOSTS"} <= set(v.index) else float("nan"))
    L = ["# team_a semantics (v0.3.1 forensic audit)\n",
         "## VERIFIED SOURCE SEMANTICS\n",
         "- The source record has `team_a_*` / `team_b_*` fields (id, name, group, score, logo) and match-level "
         "`location_name`, `arenas`, `bo_total`, `competition_format`. No field declares home/away, side "
         "(blue/red), seed, or bracket slot. No public documentation of the ordering was found in the source or "
         "the site bundle.",
         "- Side (blue/red) is decided per game inside a BO5/BO7 series, so it cannot be a series-level property.",
         "- **Verified meaning of team_a: UNKNOWN.**\n",
         "## EMPIRICAL PATTERN\n",
         f"- Completed series in staging (2022S1-2026S2): n={int(tot.n)}, team_a wins {int(tot.team_a_wins)} "
         f"({tot.team_a_wins / tot.n:.1%}). Per season x stage: `team_a_bias.csv`.",
         "- Venue cross-tab (`team_a_venue_crosstab.csv`): team city = the `location_name` value that prefixes the "
         "team name (e.g. 北京WB -> 北京). `location_name` is '0' (not recorded) for every 2022-2025 series, "
         "so venue analysis covers 2026 only (home-city venues appear from KPL2026S1).",
         ]
    for rel, r in v.iterrows():
        L.append(f"  - {rel}: n={int(r.n)}, team_a win rate {r.rate:.1%}")
    L.append(f"- When exactly one team's city hosts, that team is team_a in {host_share:.1%} of series.")
    if len(seeds):
        s = seeds[seeds.relation != "UNRANKED"]
        L.append(f"- 2026 playoffs/finals vs the last group-stage standings (`team_a_playoff_standings_crosstab.csv`): "
                 f"team_a had the better standing in {(s.relation == 'TEAM_A_BETTER_STANDING').mean():.1%} of "
                 f"{len(s)} ranked series (ranks compared within the source's group order).")
    L += ["\n## UNKNOWN / INFERENCE\n",
          "- Any reading of team_a as 'home', 'host' or 'higher seed' is INFERENCE from the patterns above, not source "
          "semantics. For 2022-2025 there is no venue field at all, and in 2026 many series are at venues neither "
          "team is named after (NEITHER_CITY_HOSTS); there the order is unexplained.",
          "- The 2026 host pattern and the playoff-standing pattern rest on small samples (host n="
          f"{int(v.loc[['TEAM_A_CITY_HOSTS', 'TEAM_B_CITY_HOSTS'], 'n'].sum()) if host_share == host_share else 0}, "
          f"ranked playoff n={len(seeds[seeds.relation != 'UNRANKED']) if len(seeds) else 0}).",
          "- The win-rate gap alone is not used as evidence of meaning.",
          "- Models must stay symmetric in team_a/team_b unless a side/seed feature is added as a separate, "
          "leakage-safe experiment."]
    return "\n".join(L) + "\n"
