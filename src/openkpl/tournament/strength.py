"""Frozen pre-tournament B5 team strength and pairwise series probabilities (write-once)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from openkpl.evaluation.benchmark import MODEL_FREEZE_DATE, PROSPECTIVE_HOLDOUT_START, split_universe
from openkpl.modeling.temporal import SeasonResetElo, prepare_batches, run_online
from openkpl.modeling.temporal.base import to_days
from openkpl.roster import baseline

RULES = "config/2026_annual_finals_rules.yaml"
REGISTRY = "data/dimensions/team_identity_registry.csv"
CANONICAL = "data/processed/temporal/v2026_09_28/canonical_series.parquet"
HYPER = "reports/benchmark/v2026_09_28/hyperparameters.json"
BENCH_PRED = "reports/benchmark/v2026_09_28/temporal_predictions.parquet"
OUT_DIR = "data/processed/tournament"
TEAMS_FILE = f"{OUT_DIR}/annual_finals_2026_teams.parquet"
STRENGTH_FILE = f"{OUT_DIR}/frozen_team_strength_2026.parquet"
STRENGTH_HASH = f"{OUT_DIR}/frozen_team_strength_2026.sha256.json"
ANNUAL_FINALS_SEASON = "KPL2026S3"
CUTOFF_LABEL = f"{MODEL_FREEZE_DATE} 00:00:00 Asia/Shanghai (exclusive)"


def load_rules(root="."):
    return yaml.safe_load((Path(root) / RULES).read_text(encoding="utf-8"))


def b5_params(root="."):
    h = json.loads((Path(root) / HYPER).read_text())
    sel = h["final_development_selected"]["B5"]["selected"]
    return {"k": float(sel["k"]), "rho": float(sel["rho"]), "scale": 400.0}


def resolve_teams(root="."):
    """Exact observed-name lookup in the verified registry; any miss or ambiguity raises."""
    rules = load_rules(root)
    reg = pd.read_csv(Path(root) / REGISTRY)
    reg = reg[reg.review_status == "VERIFIED"]
    rows = []
    for grp in ("master", "elite"):
        for t in rules["teams"][grp]:
            hit = reg[reg.observed_name == t["official_name"]]
            if hit.canonical_team_id.nunique() != 1:
                raise ValueError(f"unresolved or ambiguous team identity: {t['official_name']}")
            rows.append({"official_name": t["official_name"], "group": grp.upper(), "group_rank_seed": int(t["seed"]),
                         "canonical_team_id": hit.canonical_team_id.iloc[0],
                         "canonical_name": hit.canonical_name.iloc[0]})
    d = pd.DataFrame(rows)
    if d.canonical_team_id.nunique() != 12 or len(d) != 12:
        raise ValueError("expected 12 distinct canonical teams")
    return d


def replay_b5(root="."):
    """Online B5 over every label-eligible series before the cutoff, then B5's own season reset for the
    Annual Finals season. Returns (model, ordered dev frame, predictions)."""
    canonical = pd.read_parquet(Path(root) / CANONICAL)
    dev, _ = split_universe(canonical, PROSPECTIVE_HOLDOUT_START)
    dev = dev[dev.season != ANNUAL_FINALS_SEASON]
    if (pd.to_datetime(dev.start_time) >= PROSPECTIVE_HOLDOUT_START).any():
        raise AssertionError("post-cutoff series reached B5")
    d, batches = prepare_batches(dev)
    model = SeasonResetElo(**b5_params(root))
    p, ra, rb, _ = run_online(batches, len(d), model)
    return model, d, p


def verify_reproduction(d, p, root="."):
    """The replay must reproduce the locked v0.3.1 B5 predictions of fold F11 (same hyperparameters)."""
    bp = pd.read_parquet(Path(root) / BENCH_PRED)
    b = bp[(bp.model_id == "B5") & (bp.fold_id == "F11")].set_index("series_id").predicted_p_team_a
    mine = pd.Series(p, index=d.series_id.values).loc[b.index]
    return float(np.max(np.abs(mine.values - b.values))), len(b)


def build_strength(root="."):
    teams = resolve_teams(root)
    model, d, p = replay_b5(root)
    pre_reset = dict(model.r)
    model.start_batch(float(to_days([PROSPECTIVE_HOLDOUT_START])[0]), ANNUAL_FINALS_SEASON)
    rows = []
    for t in teams.itertuples(index=False):
        m = (d.canonical_team_a_id == t.canonical_team_id) | (d.canonical_team_b_id == t.canonical_team_id)
        if not m.any():
            raise ValueError(f"{t.canonical_team_id} has no eligible history")
        rows.append({"canonical_team_id": t.canonical_team_id, "official_name": t.official_name, "group": t.group,
                     "group_rank_seed": t.group_rank_seed,
                     "rating_before_season_reset": float(pre_reset[t.canonical_team_id]),
                     "pre_tournament_rating": float(model.r[t.canonical_team_id]),
                     "last_eligible_match": pd.Timestamp(d.loc[m, "start_time"].max()),
                     "last_training_series": d.loc[m].iloc[-1].series_id,
                     "n_historical_eligible_series": int(m.sum()),
                     "model": "B5 SeasonResetElo", **{f"b5_{k}": v for k, v in b5_params(root).items()},
                     "season_reset_applied_for": ANNUAL_FINALS_SEASON, "information_cutoff": CUTOFF_LABEL})
    return pd.DataFrame(rows), teams, (d, p)


def freeze(root="."):
    """Write-once: create the frozen strength file and its hash, or verify an existing one is unchanged and
    still reproducible. Never updates an existing file."""
    root = Path(root)
    strength, teams, (d, p) = build_strength(root)
    path, hpath = root / STRENGTH_FILE, root / STRENGTH_HASH
    if path.exists():
        stored = pd.read_parquet(path)
        h = json.loads(hpath.read_text())
        if baseline.sha256_file(path) != h["sha256"]:
            raise RuntimeError("frozen_team_strength_2026.parquet hash mismatch: frozen file was modified")
        pd.testing.assert_frame_equal(stored.reset_index(drop=True), strength.reset_index(drop=True), check_dtype=False)
        return stored, teams, h
    path.parent.mkdir(parents=True, exist_ok=True)
    strength.to_parquet(path, index=False)
    diff, n = verify_reproduction(d, p, root)
    h = {"file": STRENGTH_FILE, "sha256": baseline.sha256_file(path), "information_cutoff": CUTOFF_LABEL,
         "b5_params": b5_params(root), "reproduces_v031_B5_F11_max_abs_diff": diff, "reproduction_rows": n}
    with open(hpath, "x", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2, default=str)
    t = teams.merge(strength[["canonical_team_id", "pre_tournament_rating", "rating_before_season_reset",
                              "last_training_series", "last_eligible_match", "n_historical_eligible_series"]],
                    on="canonical_team_id")
    t["pre_tournament_B5_rating_inputs"] = t.apply(
        lambda r: json.dumps({"rating_before_season_reset": round(r.rating_before_season_reset, 6),
                              "rho": b5_params(root)["rho"], "k": b5_params(root)["k"], "scale": 400.0,
                              "pre_tournament_rating": round(r.pre_tournament_rating, 6),
                              "n_historical_eligible_series": int(r.n_historical_eligible_series)}), axis=1)
    t["information_cutoff"] = CUTOFF_LABEL
    t = t[["canonical_team_id", "official_name", "group", "group_rank_seed", "pre_tournament_B5_rating_inputs",
           "last_training_series", "last_eligible_match", "information_cutoff"]]
    t.to_parquet(root / TEAMS_FILE, index=False)
    return strength, teams, h


def pairwise(strength, lam5=1.0, lam7=1.0):
    from openkpl.tournament.engine import elo_matrix, transform
    s = strength.sort_values("group_rank_seed").reset_index(drop=True)
    P = elo_matrix(s.pre_tournament_rating.to_numpy())
    np.fill_diagonal(P, 0.5)
    return s, transform(P, lam5), transform(P, lam7)


def pairwise_long(s, P, fmt):
    rows = []
    for i in range(len(s)):
        for j in range(len(s)):
            if i != j:
                rows.append({"team_i": s.canonical_team_id[i], "team_i_name": s.official_name[i],
                             "team_j": s.canonical_team_id[j], "team_j_name": s.official_name[j], "format": fmt,
                             "p_i_beats_j": float(P[i, j]), "source": "raw frozen B5 (no BO7 correction)"})
    return pd.DataFrame(rows)
