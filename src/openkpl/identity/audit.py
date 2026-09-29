"""Team identity audit over the temporal series backbone.

Observed team names are used exactly as they appear in series.parquet.
Nothing here canonicalizes, merges, or aliases teams.
"""
from pathlib import Path

import pandas as pd

from openkpl.identity.candidates import candidate_chains, generate_candidates, overlap_checks
from openkpl.identity.registry import validate_registry, write_or_update_registry

SHORT_LIFETIME_SERIES = 20
TS_FMT = "%Y-%m-%d %H:%M:%S"


def season_order(series):
    first = series.groupby("season").start_time.min().sort_values(kind="stable")
    return {s: i for i, s in enumerate(first.index)}


def team_appearances(series):
    """Long form: one row per (series, observed team)."""
    base = ["series_id", "season", "stage", "start_time", "is_completed_labeled", "winner_team"]
    a = series[base + ["team_a", "team_b"]].rename(columns={"team_a": "team", "team_b": "opponent"})
    b = series[base + ["team_b", "team_a"]].rename(columns={"team_b": "team", "team_a": "opponent"})
    ap = pd.concat([a, b], ignore_index=True)
    done = ap.is_completed_labeled.astype(bool)
    ap["win"] = done & (ap.winner_team == ap.team)
    ap["loss"] = done & (ap.winner_team == ap.opponent)
    return ap.sort_values(["start_time", "series_id", "team"], kind="stable").reset_index(drop=True)


def _ordered_unique(values):
    return list(dict.fromkeys(values))


def build_inventory(ap, order):
    rows = []
    for team, g in ap.groupby("team", sort=True):
        g = g.sort_values(["start_time", "series_id"], kind="stable")
        seasons = sorted(set(g.season), key=order.get)
        rows.append({
            "observed_team_name": team,
            "series_count": len(g),
            "completed_series_count": int(g.is_completed_labeled.sum()),
            "wins": int(g.win.sum()),
            "losses": int(g.loss.sum()),
            "first_seen": g.start_time.min(),
            "last_seen": g.start_time.max(),
            "first_season": seasons[0],
            "last_season": seasons[-1],
            "seasons_count": len(seasons),
            "seasons_list": "|".join(seasons),
            "stages_list": "|".join(_ordered_unique(g.stage)),
            "opponents_count": int(g.opponent.nunique()),
        })
    return pd.DataFrame(rows).sort_values(["first_seen", "observed_team_name"], kind="stable").reset_index(drop=True)


def build_presence(ap, order):
    rows = []
    for (team, season), g in ap.groupby(["team", "season"], sort=True):
        rows.append({
            "observed_team_name": team, "season": season, "series_count": len(g),
            "wins": int(g.win.sum()), "losses": int(g.loss.sum()),
            "first_seen_in_season": g.start_time.min(), "last_seen_in_season": g.start_time.max(),
        })
    p = pd.DataFrame(rows)
    p["_o"] = p.season.map(order)
    return p.sort_values(["observed_team_name", "_o"], kind="stable").drop(columns="_o").reset_index(drop=True)


def build_matrix(presence, inventory, order):
    m = presence.pivot(index="observed_team_name", columns="season", values="series_count").fillna(0).astype(int)
    m = m.reindex(columns=sorted(order, key=order.get), fill_value=0)
    m = m.reindex(inventory.observed_team_name)
    m.index.name = "observed_team_name"
    return m.reset_index()


def build_timeline(inventory):
    return inventory[["observed_team_name", "first_seen", "last_seen", "first_season", "last_season",
                      "series_count"]].copy()


def _fmt_times(df):
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime(TS_FMT)
    return out


def full_seasons(presence, order):
    """Seasons whose team count equals the maximum observed (data-driven; partial seasons excluded)."""
    n = presence.groupby("season").observed_team_name.nunique()
    return [s for s in sorted(order, key=order.get) if n.get(s, 0) == n.max()]


def boundary_ledger(presence, order):
    """Names leaving / arriving between consecutive full seasons."""
    fs = full_seasons(presence, order)
    teams = presence.groupby("season").observed_team_name.apply(set)
    rows = []
    for a, b in zip(fs, fs[1:]):
        left, arrived = sorted(teams[a] - teams[b]), sorted(teams[b] - teams[a])
        rows.append({"from_season": a, "to_season": b, "teams_from": len(teams[a]), "teams_to": len(teams[b]),
                     "left": "|".join(left), "arrived": "|".join(arrived),
                     "left_count": len(left), "arrived_count": len(arrived)})
    return pd.DataFrame(rows, columns=["from_season", "to_season", "teams_from", "teams_to", "left", "arrived",
                                       "left_count", "arrived_count"])


def noncontiguous_names(presence, order):
    """Names absent from a full season between their first and last full-season appearance."""
    fs = full_seasons(presence, order)
    idx = {s: i for i, s in enumerate(fs)}
    rows = []
    for team, g in presence[presence.season.isin(fs)].groupby("observed_team_name", sort=True):
        seen = sorted(idx[s] for s in g.season)
        missing = [fs[i] for i in range(seen[0], seen[-1] + 1) if i not in seen]
        if missing:
            rows.append({"observed_team_name": team, "missing_full_seasons": "|".join(missing)})
    return pd.DataFrame(rows, columns=["observed_team_name", "missing_full_seasons"])


def summarize(inventory, candidates, overlap, chains, registry, order):
    conflicts = overlap[overlap.identity_conflict_flag]
    last_season = max(order, key=order.get)
    return {
        "unique_observed_team_names": len(inventory),
        "single_season_names": int((inventory.seasons_count == 1).sum()),
        "multi_season_names": int((inventory.seasons_count > 1).sum()),
        "transition_candidates": len(candidates),
        "strong_name_candidates": int(candidates.strong_name_evidence.sum()),
        "identity_conflicts": len(conflicts),
        "candidate_pairs_that_played_each_other": int(overlap.played_each_other.sum()),
        "mid_season_candidate_changes": int(overlap.mid_season_change.sum()),
        "candidate_chains": len(chains),
        "unreviewed_registry_rows": int((registry.review_status == "UNREVIEWED").sum()),
        "registry_rows_with_canonical_id": int((registry.canonical_team_id != "").sum()),
        "short_lifetime_names": inventory.loc[inventory.series_count < SHORT_LIFETIME_SERIES, "observed_team_name"].tolist(),
        "names_active_in_latest_season": inventory.loc[inventory.last_season == last_season, "observed_team_name"].tolist(),
    }


def _md_table(df):
    df = _fmt_times(df).astype(str)
    head = "| " + " | ".join(df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    body = ["| " + " | ".join(v.replace("|", "\\|") for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep] + body)


def render_markdown(inventory, candidates, overlap, chains, summary, order, ledger, gaps):
    seasons = sorted(order, key=order.get)
    single = inventory[inventory.seasons_count == 1]
    multi = inventory[inventory.seasons_count > 1]
    cand = candidates.merge(overlap, on=["old_name", "new_name"])
    strong = cand[cand.strong_name_evidence]
    conflicts = cand[cand.identity_conflict_flag]
    boundary_only = cand[~cand.strong_name_evidence]
    mid = cand[cand.mid_season_change]
    short = inventory[inventory.series_count < SHORT_LIFETIME_SERIES]
    unresolved = sorted(set(strong[~strong.identity_conflict_flag].old_name) | set(strong[~strong.identity_conflict_flag].new_name))
    L = []
    L.append("# Team name timeline (v0.3 Phase A identity audit)\n")
    L.append("Source: `data/processed/temporal/series.parquet` (from `kpl_data.db`). Names are exact raw strings. "
             "This report is generated by `openkpl identity-audit`.\n")
    L.append("**Nothing in this report verifies that two names are the same organization.** "
             "Candidates, scores and chains are triage for external review. `transition_score` is a ranking aid only. "
             "The registry (`data/dimensions/team_identity_registry.csv`) is UNREVIEWED.\n")
    L.append("## Counts\n")
    for k in ["unique_observed_team_names", "single_season_names", "multi_season_names", "transition_candidates",
              "strong_name_candidates", "identity_conflicts", "candidate_pairs_that_played_each_other",
              "mid_season_candidate_changes", "candidate_chains", "unreviewed_registry_rows"]:
        L.append(f"- {k}: {summary[k]}")
    L.append(f"\nSeasons in chronological order: {', '.join(seasons)}.\n")
    L.append("`last_seen` includes scheduled series that had not been played at crawl time (status 1).\n")
    L.append("## Names active in only one season\n")
    L.append(_md_table(single[["observed_team_name", "first_season", "series_count", "completed_series_count", "first_seen", "last_seen"]]))
    L.append("\n## Names spanning multiple seasons\n")
    L.append(_md_table(multi[["observed_team_name", "first_season", "last_season", "seasons_count", "series_count"]]))
    L.append(f"\n## Short lifetimes (< {SHORT_LIFETIME_SERIES} series)\n")
    L.append(_md_table(short[["observed_team_name", "seasons_list", "series_count", "completed_series_count"]]))
    L.append("\n## Candidate rename families (strong name evidence, no coexistence)\n")
    L.append("Name evidence = a shared whole Latin token, or a shared CJK substring that is not just a common "
             "2-character city prefix. Raw string similarity is reported but is not name evidence. "
             "These are hypotheses only.\n")
    ok = strong[~strong.identity_conflict_flag]
    L.append(_md_table(ok[["old_name", "new_name", "old_last_season", "new_first_season", "days_between",
                           "shared_latin_tokens", "shared_cjk_substring", "string_similarity", "transition_score",
                           "mid_season_change"]]) if len(ok) else "None.")
    L.append("\n## Candidate chains (A -> B -> C)\n")
    L.append("\n".join(f"- {' -> '.join(c)}" for c in chains) if chains else "None.")
    L.append("\n## Full-season boundary ledger\n")
    L.append("Full seasons are those with the maximum team count; partial seasons (fewer teams, e.g. annual-finals "
             "formats) are excluded. Equal left/arrived counts are consistent with a fixed number of league slots; "
             "they do not say which name replaced which.\n")
    L.append(_md_table(ledger))
    L.append("\n## Non-contiguous presence\n")
    L.append("Names missing from a full season between their first and last full-season appearance.\n")
    L.append(_md_table(gaps) if len(gaps) else "None.")
    L.append("\n## Suspicious disappearance / appearance boundaries\n")
    L.append("Pairs where one name stops and another starts within 270 days with **no** name evidence. "
             "In a closed franchise league these may be slot transfers or sponsor renames, or unrelated teams. "
             "Most are expected to be unrelated.\n")
    L.append(_md_table(boundary_only[["old_name", "new_name", "old_last_season", "new_first_season", "days_between",
                                      "transition_score"]]) if len(boundary_only) else "None.")
    L.append("\n## Suspicious mid-season changes\n")
    L.append(_md_table(mid[["old_name", "new_name", "old_last_season", "new_first_season", "old_last_seen", "new_first_seen"]])
             if len(mid) else "None: no candidate pair switches names inside one season without overlap.")
    L.append("\n## Overlapping names that make naive aliasing dangerous\n")
    L.append("These candidate pairs coexist (overlapping dates, same day, or head-to-head series). "
             "`identity_conflict_flag` is true; they must not be merged automatically.\n")
    L.append(_md_table(conflicts[["old_name", "new_name", "string_similarity", "conflict_reasons"]]) if len(conflicts) else "None.")
    L.append("\n## Unresolved cases\n")
    L.append("Every observed name is unresolved until a registry row is reviewed with external evidence. "
             "Names involved in non-conflicting strong-name candidates, which need evidence first:\n")
    L.append("\n".join(f"- {n}" for n in unresolved) if unresolved else "None.")
    L.append("")
    return "\n".join(L)


def run_identity_audit(series, out_dir: Path, registry_path: Path):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    series = series.copy()
    series["start_time"] = pd.to_datetime(series.start_time)
    order = season_order(series)
    ap = team_appearances(series)
    inventory = build_inventory(ap, order)
    presence = build_presence(ap, order)
    matrix = build_matrix(presence, inventory, order)
    timeline = build_timeline(inventory)
    candidates = generate_candidates(ap, inventory, order)
    overlap = overlap_checks(ap, series, candidates, order)
    chains = candidate_chains(candidates, overlap)
    registry, added, created = write_or_update_registry(registry_path, inventory.observed_team_name)
    problems = validate_registry(registry)

    enc = "utf-8-sig"
    _fmt_times(inventory).to_csv(out_dir / "team_name_inventory.csv", index=False, encoding=enc)
    _fmt_times(presence).to_csv(out_dir / "team_season_presence.csv", index=False, encoding=enc)
    matrix.to_csv(out_dir / "team_season_matrix.csv", index=False, encoding=enc)
    _fmt_times(candidates).to_csv(out_dir / "team_transition_candidates.csv", index=False, encoding=enc)
    _fmt_times(timeline).to_csv(out_dir / "team_name_timeline.csv", index=False, encoding=enc)
    overlap.to_csv(out_dir / "team_name_overlap.csv", index=False, encoding=enc)

    ledger = boundary_ledger(presence, order)
    gaps = noncontiguous_names(presence, order)
    summary = summarize(inventory, candidates, overlap, chains, registry, order)
    summary.update({"registry_created": created, "registry_rows_added": added, "registry_problems": problems,
                    "noncontiguous_names": gaps.observed_team_name.tolist(),
                    "unbalanced_boundaries": int((ledger.left_count != ledger.arrived_count).sum())})
    (out_dir / "team_name_timeline.md").write_text(
        render_markdown(inventory, candidates, overlap, chains, summary, order, ledger, gaps), encoding="utf-8")
    return {"summary": summary, "inventory": inventory, "presence": presence, "matrix": matrix,
            "timeline": timeline, "candidates": candidates, "overlap": overlap, "chains": chains,
            "registry": registry, "ledger": ledger, "gaps": gaps}
