"""OpenKPL command-line interface.

v0.1 commands: audit, ingest
v0.2 commands: build-draft, build-temporal, quality, hero-features, baseline
v0.3 commands: identity-audit, canonicalize, temporal-benchmark, freeze

The WZRY draft corpus and the kpl_data.db series backbone are never joined.
"""
from pathlib import Path
import argparse
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "data/raw/external"
AUD = ROOT / "reports/audit"
PROC = ROOT / "data/processed"
DRAFT = PROC / "draft"
TEMP = PROC / "temporal"
DIMS = ROOT / "data/dimensions"
HERO = ROOT / "features/hero"
REPORT = ROOT / "reports/data_quality"
EVAL = ROOT / "evaluation"
IDENTITY = ROOT / "reports/identity"
IDENTITY_REGISTRY = DIMS / "team_identity_registry.csv"
MEMBERSHIP = DIMS / "team_season_membership.csv"
CANONICAL = TEMP / "canonical_series.parquet"
BENCH = ROOT / "reports/benchmark"
BENCH_FIGS = ROOT / "figures/benchmark"
FREEZE_DIR = ROOT / "reports/freeze"
CANON_AUDIT = BENCH / "canonicalization_audit.csv"
SNAPSHOTS = ROOT / "data/raw/snapshots"
STAGING = ROOT / "data/staging"
REFRESH = ROOT / "reports/data_refresh"
WZRY = EXT / "HoK-BP-LLM" / "王者荣耀KPL历年比赛数据" / "WZRY.csv"
DB = EXT / "PythonMajor-assignment" / "data" / "kpl_data.db"


def need(p, hint=None):
    if not p.exists():
        raise SystemExit(f"Missing: {p}" + (f"\n{hint}" if hint else ""))


# ---- v0.1 -----------------------------------------------------------------

def audit():
    from openkpl.audit.files import inventory, profile_tabular, profile_sqlite, field_evidence
    AUD.mkdir(parents=True, exist_ok=True)
    inv = inventory(EXT); tab = profile_tabular(EXT); sql = profile_sqlite(EXT)
    ev = field_evidence(tab, sql)
    inv.to_csv(AUD / "file_inventory.csv", index=False)
    tab.to_csv(AUD / "tabular_profile.csv", index=False)
    sql.to_csv(AUD / "sqlite_tables.csv", index=False)
    ev.to_csv(AUD / "field_evidence.csv", index=False)
    print(ev.to_string(index=False))
    print(f"\nAudit written to {AUD}")


def ingest():
    """v0.1 heuristic CSV normalizer. Output is exploratory, not a temporal table."""
    from openkpl.ingestion.normalize import normalize_match_frame
    candidates = []
    for p in EXT.rglob("*.csv"):
        try:
            df = pd.read_csv(p, encoding="utf-8-sig")
        except Exception:
            try:
                df = pd.read_csv(p, encoding="gb18030")
            except Exception:
                continue
        try:
            n = normalize_match_frame(df)
            n["source_file"] = str(p.relative_to(EXT))
            candidates.append(n)
        except Exception:
            pass
    if not candidates:
        print("No automatically recognizable match CSV found. Run audit and map source fields explicitly.")
        return
    out = pd.concat(candidates, ignore_index=True).drop_duplicates()
    PROC.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PROC / "matches_seed.parquet", index=False)
    print(f"Wrote {len(out)} rows to data/processed/matches_seed.parquet")
    if "start_time" not in out or out["start_time"].isna().all():
        print("WARNING: no start_time in these rows. They are NOT chronological; "
              "do not use them for Elo. Use build-temporal + baseline instead.")


# ---- v0.2 -----------------------------------------------------------------

def build_draft():
    from openkpl.transform.draft import build_draft_tables
    need(WZRY)
    DRAFT.mkdir(parents=True, exist_ok=True); DIMS.mkdir(parents=True, exist_ok=True)
    g, e, l, o, t, h = build_draft_tables(WZRY)
    for df, name in [(g, "draft_games"), (e, "draft_events"), (l, "game_lineups"), (o, "hero_loadouts")]:
        df.to_parquet(DRAFT / f"{name}.parquet", index=False)
    t.to_parquet(DIMS / "draft_teams.parquet", index=False)
    h.to_parquet(DIMS / "heroes.parquet", index=False)
    print(f"{len(g):,} games | {len(e):,} BP events | {len(l):,} lineup slots | {len(o):,} item rows"
          f" | {len(t)} teams | {len(h)} heroes")
    print("draft_game_id values are synthetic row IDs (wzry_NNNNNN), not official KPL game IDs.")


def build_temporal():
    from openkpl.transform.temporal import build_series_table
    need(DB)
    TEMP.mkdir(parents=True, exist_ok=True)
    s = build_series_table(DB)
    s.to_parquet(TEMP / "series.parquet", index=False)
    flags = s.label_flag.value_counts().to_dict()
    print(f"{len(s):,} series rows | {int(s.is_completed_labeled.sum()):,} labeled | label_flag={flags}")


def quality():
    from openkpl.audit.quality import run
    for p in [DRAFT / "draft_games.parquet", TEMP / "series.parquet"]:
        need(p, "Run build-draft and build-temporal first.")
    g = pd.read_parquet(DRAFT / "draft_games.parquet")
    e = pd.read_parquet(DRAFT / "draft_events.parquet")
    l = pd.read_parquet(DRAFT / "game_lineups.parquet")
    s = pd.read_parquet(TEMP / "series.parquet")
    res = run(g, e, l, s, REPORT)
    print(json.dumps({"draft": res["draft"], "temporal": res["temporal"]}, ensure_ascii=False, indent=2, default=str))
    bad = [r for r in res["reconciliation"] if not r["match"]]
    print(f"\nForensic reconciliation: {len(res['reconciliation']) - len(bad)}/{len(res['reconciliation'])} metrics match")
    for r in bad:
        print(f"  MISMATCH {r['metric']}: forensic={r['forensic_audit']} etl={r['etl']}")
    print(f"Reports written to {REPORT}")


def hero_features():
    from openkpl.features.hero import role_features, synergy, counter
    need(DRAFT / "game_lineups.parquet", "Run build-draft first.")
    g = pd.read_parquet(DRAFT / "draft_games.parquet")
    l = pd.read_parquet(DRAFT / "game_lineups.parquet")
    HERO.mkdir(parents=True, exist_ok=True)
    r, h = role_features(l); sy = synergy(g, l); co = counter(g, l)
    r.to_parquet(HERO / "hero_role_profile.parquet", index=False)
    h.to_parquet(HERO / "hero_flexibility.parquet", index=False)
    sy.to_parquet(HERO / "hero_pair_synergy.parquet", index=False)
    co.to_parquet(HERO / "hero_counter_association.parquet", index=False)
    print(f"{len(h)} heroes with HFI | {len(sy)} synergy pairs | {len(co)} directed counter pairs")
    print("Descriptive, non-temporal associations from WZRY; not causal and not patch-specific.")


def identity_audit():
    from openkpl.identity.audit import run_identity_audit
    need(TEMP / "series.parquet", "Run build-temporal first.")
    s = pd.read_parquet(TEMP / "series.parquet")
    res = run_identity_audit(s, IDENTITY, IDENTITY_REGISTRY)
    sm = res["summary"]
    print("Team identity audit (evidence only; no names are merged)")
    for k in ["unique_observed_team_names", "single_season_names", "multi_season_names", "transition_candidates",
              "strong_name_candidates", "identity_conflicts", "candidate_pairs_that_played_each_other",
              "mid_season_candidate_changes", "candidate_chains", "unreviewed_registry_rows",
              "registry_rows_with_canonical_id"]:
        print(f"  {k}: {sm[k]}")
    print(f"  short_lifetime_names (<20 series): {sm['short_lifetime_names']}")
    print("  candidate chains:")
    for c in res["chains"]:
        print("    " + " -> ".join(c))
    ov = res["overlap"]
    sim = ov[ov.identity_conflict_flag].merge(res["candidates"], on=["old_name", "new_name"])
    sim = sim[sim.strong_name_evidence | sim.similar_string_flag]
    print("  simultaneous similar names (conflict):")
    for r in sim.itertuples(index=False):
        print(f"    {r.old_name} / {r.new_name}: {r.conflict_reasons}")
    mid = ov[ov.mid_season_change]
    print(f"  suspicious mid-season changes: {list(zip(mid.old_name, mid.new_name)) or 'none'}")
    print(f"  non-contiguous names (missing a full season mid-run): {sm['noncontiguous_names'] or 'none'}")
    print(f"  full-season boundaries with unequal left/arrived counts: {sm['unbalanced_boundaries']}")
    reg = "created" if sm["registry_created"] else f"kept existing, added {len(sm['registry_rows_added'])} rows"
    print(f"  registry: {reg}; problems: {sm['registry_problems'] or 'none'}")
    print(f"Reports written to {IDENTITY}")


def _bench_paths():
    return {"source_db": DB, "canonical": CANONICAL, "registry": IDENTITY_REGISTRY, "membership": MEMBERSHIP}


def canonicalize(args=None):
    from openkpl.identity.membership import validate_membership, write_membership_if_absent
    from openkpl.identity.registry import read_registry, validate_registry
    from openkpl.transform.canonical import build_canonical_series
    need(TEMP / "series.parquet", "Run build-temporal first.")
    need(IDENTITY_REGISTRY, "Run identity-audit and review the registry first.")
    reg = read_registry(IDENTITY_REGISTRY)
    problems = validate_registry(reg)
    if problems:
        raise SystemExit(f"Registry invalid: {problems}")
    s = pd.read_parquet(TEMP / "series.parquet")
    canon, audit, checks = build_canonical_series(s, reg)
    canon.to_parquet(CANONICAL, index=False)
    mem, created = write_membership_if_absent(MEMBERSHIP, canon, reg)
    mproblems = validate_membership(mem)
    clean = audit["unresolved_series"] == 0 and audit["conflicted_series"] == 0 and all(checks.values()) and not mproblems
    BENCH.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{**audit, **checks, "membership_problems": "; ".join(mproblems), "clean": clean}]).to_csv(
        CANON_AUDIT, index=False, encoding="utf-8-sig")
    bad = canon[canon.identity_resolution_status != "RESOLVED"]
    if len(bad):
        bad.to_csv(BENCH / "canonicalization_unresolved_rows.csv", index=False, encoding="utf-8-sig")
    print(json.dumps({**audit, **checks}, ensure_ascii=False, indent=2))
    print(f"membership table: {'created' if created else 'kept existing'} ({len(mem)} rows); "
          f"problems: {mproblems or 'none'}")
    print("CANONICALIZATION CLEAN" if clean else
          "CANONICALIZATION NOT CLEAN: STOP and review canonicalization_audit.csv before benchmarking.")


def temporal_benchmark(args=None):
    from openkpl.evaluation.benchmark import run_temporal_benchmark
    version = getattr(args, "data_version", None)
    if version:
        vdir = TEMP / version
        need(vdir / "MERGE_RECORD.json", "Run refresh-merge first; only merged, audited versions can be benchmarked.")
        paths = {**_bench_paths(), "canonical": vdir / "canonical_series.parquet",
                 "membership": vdir / "team_season_membership.csv"}
        out, figs = BENCH / version, BENCH_FIGS / version
    else:
        need(CANONICAL, "Run canonicalize first.")
        need(CANON_AUDIT, "Run canonicalize first.")
        need(MEMBERSHIP, "Run canonicalize first.")
        audit = pd.read_csv(CANON_AUDIT, encoding="utf-8-sig").iloc[0]
        if not bool(audit["clean"]):
            raise SystemExit("Canonicalization is not clean; refusing to benchmark. See canonicalization_audit.csv.")
        paths, out, figs = _bench_paths(), BENCH, BENCH_FIGS
    res, manifest = run_temporal_benchmark(paths, out, figs, ROOT)
    if version:
        from openkpl.refresh.merge import benchmark_before_after
        cmp = benchmark_before_after(pd.read_csv(BENCH / "temporal_metrics.csv", encoding="utf-8-sig"), res["metrics"])
        REFRESH.mkdir(parents=True, exist_ok=True)
        cmp.to_csv(REFRESH / "benchmark_before_after.csv", index=False, encoding="utf-8-sig")
    cols = ["model_id", "n", "log_loss", "brier", "accuracy", "ece", "calibration_intercept", "calibration_slope"]
    print(res["metrics"][cols].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(f"\nfolds: {len(res['folds'])} | prospective holdout labeled rows (unused): "
          f"{manifest['prospective_holdout_labeled_rows_present']}")
    print(f"Artifacts: {out} | figures: {figs}. No model has been frozen.")


def _snapshot_date(args):
    from datetime import datetime
    return getattr(args, "snapshot_date", None) or datetime.now().strftime("%Y-%m-%d")


def refresh_snapshot(args):
    from openkpl.evaluation.benchmark import git_commit
    from openkpl.refresh.snapshot import SnapshotExistsError, take_snapshot
    try:
        m = take_snapshot(SNAPSHOTS, _snapshot_date(args), git_commit=git_commit(ROOT))
    except SnapshotExistsError as e:
        raise SystemExit(str(e))
    bad = [r for r in m["requests"] if r["http_status"] != 200]
    print(f"snapshot {m['snapshot_date']}: {len(m['requests'])} requests, {len(bad)} non-200; "
          f"discovered seasons: {m['discovered_seasons']}")


def refresh_audit(args):
    from openkpl.evaluation.benchmark import PROSPECTIVE_HOLDOUT_START
    from openkpl.refresh.run import run_refresh_audit
    snap = SNAPSHOTS / _snapshot_date(args)
    need(snap / "SNAPSHOT_MANIFEST.json", "Run refresh-snapshot first.")
    res = run_refresh_audit(snap, TEMP / "series.parquet", CANONICAL, IDENTITY_REGISTRY, REFRESH, STAGING,
                            PROSPECTIVE_HOLDOUT_START)
    g = res["gate"]
    print(res["inventory"][["source_competition_id", "source_competition_name", "total_series", "completed_series",
                            "earliest_series_date", "latest_series_date", "unique_teams"]].to_string(index=False))
    print(f"\ndiff: {g['diff_counts']}")
    print(res["coverage"][["season", "stage_id", "expected_or_discovered_series", "retrieved_series",
                           "completed_series", "coverage_status"]].to_string(index=False))
    print(f"\nstaging canonicalization: {res['canon_audit']}")
    print(f"checks: {res['checks']}")
    print(f"\nDECISION: {g['decision']} | merge allowed: {g['merge_allowed']} | blockers: {g['merge_blockers'] or 'none'}")


def refresh_merge(args):
    from openkpl.evaluation.benchmark import PROSPECTIVE_HOLDOUT_START
    from openkpl.identity.registry import read_registry
    from openkpl.refresh.merge import MergeRefusedError, merge_refresh
    need(REFRESH / "refresh_audit_summary.json", "Run refresh-audit first.")
    gate = json.loads((REFRESH / "refresh_audit_summary.json").read_text(encoding="utf-8"))
    version = getattr(args, "data_version", None) or f"v{_snapshot_date(args).replace('-', '_')}"
    try:
        rec = merge_refresh(pd.read_parquet(TEMP / "series.parquet"), pd.read_parquet(STAGING / "2026_temporal_refresh.parquet"),
                            read_registry(IDENTITY_REGISTRY), pd.read_csv(REFRESH / "refresh_diff.csv", encoding="utf-8-sig"),
                            gate, TEMP / version, CANONICAL, PROSPECTIVE_HOLDOUT_START)
    except MergeRefusedError as e:
        raise SystemExit(f"MERGE REFUSED: {e}")
    print(json.dumps(rec, ensure_ascii=False, indent=2, default=str))


def refresh_analysis(args):
    from openkpl.refresh import analysis as A
    version = getattr(args, "data_version", None)
    if not version:
        raise SystemExit("refresh-analysis requires --data-version <version>.")
    vbench = BENCH / version
    need(vbench / "temporal_predictions.parquet", f"Run temporal-benchmark --data-version {version} first.")
    old_pred = pd.read_parquet(BENCH / "temporal_predictions.parquet")
    new_pred = pd.read_parquet(vbench / "temporal_predictions.parquet")
    old_hp = json.loads((BENCH / "hyperparameters.json").read_text(encoding="utf-8"))
    new_hp = json.loads((vbench / "hyperparameters.json").read_text(encoding="utf-8"))
    canon = pd.read_parquet(TEMP / version / "canonical_series.parquet")
    staging = pd.read_parquet(STAGING / "2026_temporal_refresh.parquet")
    out = {
        "metrics_2026.csv": A.season_metrics(new_pred, ["KPL2026S1", "KPL2026S2"]),
        "benchmark_common_rows.csv": A.common_row_comparison(old_pred, new_pred),
        "hyperparameters_before_after.csv": A.hyperparameter_comparison(old_hp, new_hp),
        "syg_wst_diagnostic.csv": A.team_diagnostic(new_pred, ["TEAM_SYG", "TEAM_WST"]),
        "paired_model_differences.csv": A.paired_differences({"phase_b": old_pred, version: new_pred}),
    }
    team_a, unmatched = A.team_a_diagnostic(staging, canon)
    out["team_a_diagnostic_2026.csv"] = team_a
    for name, df in out.items():
        df.to_csv(REFRESH / name, index=False, encoding="utf-8-sig")
    print(f"wrote {sorted(out)} to {REFRESH}; team_a rows without source stage/venue: {unmatched}")


def freeze_model(args):
    from openkpl.evaluation.freeze import FreezeExistsError, freeze
    if not args.model:
        raise SystemExit("freeze requires --model <B0..B5>; the model must be chosen explicitly after review.")
    need(BENCH / "benchmark_manifest.json", "Run temporal-benchmark first.")
    try:
        m = freeze(args.model, BENCH, FREEZE_DIR, _bench_paths(), ROOT, force=args.force)
    except FreezeExistsError as e:
        raise SystemExit(str(e))
    print(json.dumps(m, ensure_ascii=False, indent=2, default=str))


def baseline():
    from openkpl.modeling.elo import build_series_elo
    from openkpl.evaluation.metrics import binary_metrics
    need(TEMP / "series.parquet", "Run build-temporal first.")
    need(REPORT / "temporal_quality_summary.json", "Run quality and review the temporal report before the baseline.")
    s = pd.read_parquet(TEMP / "series.parquet")
    p = build_series_elo(s)
    if p.empty:
        raise SystemExit("No completed labeled series.")
    m = binary_metrics(p.y_team_a, p.p_team_a)
    EVAL.mkdir(parents=True, exist_ok=True)
    p.to_parquet(EVAL / "elo_series_predictions.parquet", index=False)
    (EVAL / "elo_metrics.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(json.dumps(m, indent=2))


COMMANDS = {
    "audit": audit,
    "ingest": ingest,
    "build-draft": build_draft,
    "build-temporal": build_temporal,
    "quality": quality,
    "hero-features": hero_features,
    "identity-audit": identity_audit,
    "baseline": baseline,
    "canonicalize": canonicalize,
    "temporal-benchmark": temporal_benchmark,
    "freeze": freeze_model,
    "refresh-snapshot": refresh_snapshot,
    "refresh-audit": refresh_audit,
    "refresh-merge": refresh_merge,
    "refresh-analysis": refresh_analysis,
}
TAKES_ARGS = {"canonicalize", "temporal-benchmark", "freeze", "refresh-snapshot", "refresh-audit", "refresh-merge",
              "refresh-analysis"}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="openkpl", description="OpenKPL Analytics pipeline")
    ap.add_argument("command", choices=list(COMMANDS))
    ap.add_argument("--model", help="freeze only: model ID to freeze (B0-B5)")
    ap.add_argument("--force", action="store_true", help="freeze only: overwrite an existing freeze manifest")
    ap.add_argument("--snapshot-date", help="refresh-*: snapshot directory name (default: today, YYYY-MM-DD)")
    ap.add_argument("--data-version", help="refresh-merge / temporal-benchmark: versioned dataset name, e.g. v2026_09_28")
    a = ap.parse_args(argv)
    if a.command in TAKES_ARGS:
        COMMANDS[a.command](a)
    else:
        COMMANDS[a.command]()


if __name__ == "__main__":
    main()
