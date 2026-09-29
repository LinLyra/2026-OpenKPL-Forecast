"""v1.0 prospective 2026 KPL Annual Finals forecast (pre-tournament freeze CANDIDATE; never auto-frozen).

PRIMARY = frozen raw B5 series probabilities (identical for BO5 and BO7), official structure from
config/2026_annual_finals_rules.yaml, pre-registered scenarios for every unresolved rule.
"""
import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.evaluation.benchmark import PROSPECTIVE_HOLDOUT_START
from openkpl.roster import baseline
from openkpl.tournament import engine as E
from openkpl.tournament import lock, rotation
from openkpl.tournament import strength as S

REPORTS = "reports/tournament"
FIGURES = "figures/tournament"
LEDGER = f"{REPORTS}/PREDICTION_LEDGER_2026.csv"
MODEL_VERSION = "openkpl-v1.0 frozen raw B5 SeasonResetElo (k=48, rho=0.9, scale=400); no BO7/roster/draft/state adjustment"
DATA_VERSION = "v2026_09_28 canonical_series (1466 development series, last 2026-09-12)"
GIT_COMMIT = "N/A (workspace is not a git repository)"
MILESTONES = ["direct_knockout", "breakthrough", "stage1_elimination", "breakthrough_win", "breakthrough_elimination",
              "knockout", "upper_semifinal", "upper_final", "upper_final_win", "drop_to_lower", "lower_final", "final",
              "champion"]
CONVERGENCE_TOL = 0.002  # pre-registered: max |p(500k) - p(1M)| for champion/final/knockout must not exceed this
CONSEQUENTIAL = {  # stage-1 rank boundary (between rank i+1 and i+2) -> consequence under the PRIMARY scenario
    ("master", 0): "none (Master #1/#2 are symmetric in every draw scenario)",
    ("master", 1): "seed slot vs no seed slot",
    ("master", 2): "none (both direct, unseeded)",
    ("master", 3): "direct knockout vs breakthrough",
    ("master", 4): "breakthrough selection order (M5 picks first)",
    ("elite", 0): "direct knockout vs breakthrough",
    ("elite", 1): "none under ELITE_2_TO_5 (matters only under SELECTION_POOL_ANY)",
    ("elite", 2): "none under ELITE_2_TO_5 (matters only under SELECTION_POOL_ANY)",
    ("elite", 3): "none under ELITE_2_TO_5 (matters only under SELECTION_POOL_ANY)",
    ("elite", 4): "breakthrough vs stage-1 elimination",
}


@dataclass
class Ctx:
    root: Path
    rules: dict
    strength: pd.DataFrame
    P: np.ndarray
    r: np.ndarray
    names: list
    short: list
    ids: list
    schedule: list
    dates: list


def context(root="."):
    root = Path(root)
    rules = S.load_rules(root)
    stored, _, _ = S.freeze(root)          # verifies hash + exact recomputation; never rewrites
    s, P, _ = S.pairwise(stored)
    idx = {n: i for i, n in enumerate(s.official_name)}
    sched, dates = [], []
    for d, a, b in rules["stage1_schedule"]:
        sched.append((idx[a], idx[b]))
        dates.append(d)
    return Ctx(root, rules, s, P, s.pre_tournament_rating.to_numpy(), list(s.official_name),
               [c.replace("TEAM_", "") for c in s.canonical_team_id], list(s.canonical_team_id), sched, dates)


# ----------------------------------------------------------------------------------------------- guards
def af_outcomes_absent(root="."):
    """Annual Finals / post-cutoff outcomes are not in any strength input."""
    root = Path(root)
    fr = pd.read_parquet(root / S.STRENGTH_FILE)
    ok_strength = bool((pd.to_datetime(fr.last_eligible_match) < PROSPECTIVE_HOLDOUT_START).all())
    canon = pd.read_parquet(root / S.CANONICAL)
    af_rows = int((canon.season == S.ANNUAL_FINALS_SEASON).sum())
    post = int((pd.to_datetime(canon.start_time) >= PROSPECTIVE_HOLDOUT_START).sum())
    return {"strength_last_match_before_cutoff": ok_strength, "annual_finals_rows_in_canonical": af_rows,
            "post_cutoff_rows_in_canonical": post, "ok": ok_strength}


def guard(root="."):
    bad = lock.check(root)
    if bad:
        raise RuntimeError(f"v1.0 lock mismatch (HARD FAILURE): {bad}")
    if not af_outcomes_absent(root)["ok"]:
        raise RuntimeError("post-cutoff information in frozen strength")


# ----------------------------------------------------------------------------------------------- simulation
def matrices(ctx, lam5=1.0, lam7=1.0):
    P5 = ctx.P if lam5 == 1.0 else E.transform(ctx.P, lam5)
    P7 = ctx.P if lam7 == 1.0 else E.transform(ctx.P, lam7)
    return P5, P7


def _mark(n, teams):
    x = np.zeros((n, E.N_TEAMS), bool)
    teams = teams if teams.ndim == 2 else teams[:, None]
    x[np.arange(n)[:, None], teams] = True
    return x


def _sanity(ind, n, neutral=False):
    c = {"champion_one_per_sim": bool((ind["champion"].sum(1) == 1).all()),
         "final_two_per_sim": bool((ind["final"].sum(1) == 2).all()),
         "knockout_eight_per_sim": bool((ind["knockout"].sum(1) == 8).all()),
         "champion_is_finalist": bool((~ind["champion"] | ind["final"]).all()),
         "finalist_in_knockout": bool((~ind["final"] | ind["knockout"]).all())}
    if not neutral:
        code = ind["elimination_code"]
        expect = {"STAGE1": 1, "BREAKTHROUGH": 3, "LB_R1": 2, "LB_R2": 2, "LB_SF": 1, "LB_F": 1, "FINAL": 1, "CHAMPION": 1}
        c.update({
            "direct_five_per_sim": bool((ind["direct_knockout"].sum(1) == 5).all()),
            "breakthrough_six_per_sim": bool((ind["breakthrough"].sum(1) == 6).all()),
            "stage1_elimination_one_per_sim": bool((ind["stage1_elimination"].sum(1) == 1).all()),
            "breakthrough_winners_three_per_sim": bool((ind["breakthrough_win"].sum(1) == 3).all()),
            "stage1_partition": bool(((ind["direct_knockout"].astype(int) + ind["breakthrough"] + ind["stage1_elimination"]) == 1).all()),
            "knockout_is_direct_or_bt_winner": bool((ind["knockout"] == (ind["direct_knockout"] | ind["breakthrough_win"])).all()),
            "every_team_terminates_once": bool((code >= 0).all()),
            "elimination_counts_correct": all(bool(((code == E.ELIM_CODES[k]).sum(1) == v).all()) for k, v in expect.items()),
        })
    return c


def simulate(ctx, scen, lam5=1.0, lam7=1.0, n=1_000_000, seed=20261002, record=False, keep=False, neutral=False):
    P5, P7 = matrices(ctx, lam5, lam7)
    rec = E.Recorder(n, ctx.r, P5) if record else None
    sim = E.Sim(P5, P7, ctx.r, n, np.random.default_rng(seed), rec)
    res = {"n": n, "seed": seed, "lam5": lam5, "lam7": lam7}
    if neutral:
        out = E.neutral_tournament(sim)
        de = out["de"]
        ind = {"knockout": _mark(n, out["slots"]), "final": _mark(n, np.column_stack([de["FINAL"][0], de["FINAL"][1]])),
               "champion": _mark(n, de["champion"])}
        res["p"] = {k: v.mean(0) for k, v in ind.items()}
        res["sanity"] = _sanity(ind, n, neutral=True)
        return res
    out = E.tournament(sim, ctx.schedule, scen)
    ind = E.team_indicators(out, n)
    rows = np.arange(n)
    res["p"] = {k: ind[k].mean(0) for k in MILESTONES}
    code = ind["elimination_code"]
    res["elim"] = {k: (code == v).mean(0) for k, v in E.ELIM_CODES.items()}
    res["sanity"] = _sanity(ind, n)
    s1 = out["stage1"]
    res["wins_mean"], res["gd_mean"] = s1["wins"].mean(0), s1["gd"].mean(0)
    res["rank_dist"] = {g: np.stack([(s1[g] == t).mean(0) for t in grp])
                        for g, grp in (("master", E.MASTER), ("elite", E.ELITE))}
    res["audit"] = {g: {k: v.mean(0) for k, v in s1[f"{g}_audit"].items()} for g in ("master", "elite")}
    cons = np.zeros(n, bool)
    cons_fb = np.zeros(n, bool)
    for (g, b), what in CONSEQUENTIAL.items():
        if not what.startswith("none"):
            cons |= s1[f"{g}_audit"]["tied_on_wins"][:, b]
            cons_fb |= s1[f"{g}_audit"]["fallback"][:, b]
    res["mass_consequential_tie"] = float(cons.mean())
    res["mass_consequential_fallback"] = float(cons_fb.mean())
    pairs = out["bt_pairs"]
    res["bt_pairs"] = {k: pd.Series(pairs[:, k, 0] * 12 + pairs[:, k, 1]).value_counts(normalize=True) for k in range(3)}
    ko = np.zeros((n, E.N_TEAMS), np.int16)
    for m, _, _ in E.BRACKET:
        a, b = out["de"][m][0], out["de"][m][1]
        ko[rows, a] += 1
        ko[rows, b] += 1
    bo7 = ko + ind["breakthrough"]
    d, bt = ind["direct_knockout"], ind["breakthrough"]
    with np.errstate(invalid="ignore", divide="ignore"):
        cond = lambda x, m: (x * m).sum(0) / m.sum(0)
        res["cond"] = {"champion_given_direct": cond(ind["champion"], d), "champion_given_breakthrough": cond(ind["champion"], bt),
                       "final_given_direct": cond(ind["final"], d), "final_given_breakthrough": cond(ind["final"], bt),
                       "champion_given_knockout": cond(ind["champion"], ind["knockout"]),
                       "bt_win_given_breakthrough": cond(ind["breakthrough_win"], bt),
                       "bo7_given_direct": cond(bo7, d), "bo7_given_breakthrough": cond(bo7, bt),
                       "series_given_direct": 6 + cond(bo7, d), "series_given_breakthrough": 6 + cond(bo7, bt)}
    res["expected_bo7"] = bo7.mean(0)
    if rec is not None:
        res["path"] = {"series": rec.series / n, "bo5": rec.bo5 / n, "bo7": rec.bo7 / n,
                       "opp_rating": rec.opp_rating / rec.series, "difficulty_per_series": rec.difficulty / rec.series,
                       "difficulty_total": rec.difficulty / n}
    if keep:
        res["arrays"] = {k: ind[k] for k in ("champion", "final", "knockout")}
    return res


def se(p, n):
    return np.sqrt(p * (1 - p) / n)


# ----------------------------------------------------------------------------------------------- ledger
def ledger_rows(ctx, generated_at):
    root = ctx.root
    h = {"frozen_strength_sha256": baseline.sha256_file(root / S.STRENGTH_FILE),
         "rules_manifest_sha256": baseline.sha256_file(root / S.RULES),
         "v10_lock_sha256": baseline.sha256_file(root / lock.LOCK_PATH),
         "structure_capture_manifest_sha256": baseline.sha256_file(root / lock.CAPTURES / "CAPTURE_MANIFEST.json")}
    rows = []
    for k, ((a, b), d) in enumerate(zip(ctx.schedule, ctx.dates), 1):
        p = float(ctx.P[a, b])
        rows.append({"ledger_key": f"AF2026-STAGE1-{k:02d}", "stage": "STAGE1_擂台赛", "scheduled_date": d,
                     "team_a": ctx.names[a], "team_a_id": ctx.ids[a], "team_b": ctx.names[b], "team_b_id": ctx.ids[b],
                     "format": "BO5", "p_team_a": round(p, 10), "p_team_b": round(1 - p, 10),
                     "generated_at": generated_at, "information_cutoff": S.CUTOFF_LABEL,
                     "model_version": MODEL_VERSION, "data_version": DATA_VERSION, "git_commit": GIT_COMMIT, **h,
                     "note": "ledger_key is a ledger identifier, not an official KPL match id; schedule dates are a "
                             "secondary transcription (R04)"})
    return pd.DataFrame(rows)


def write_ledger(ctx):
    path = ctx.root / LEDGER
    if path.exists():
        old = pd.read_csv(path)
        new = ledger_rows(ctx, old.generated_at.iloc[0])
        pd.testing.assert_frame_equal(old.drop(columns="generated_at"), new.drop(columns="generated_at"),
                                      check_dtype=False, check_exact=False, rtol=0, atol=1e-10)
        return old, "verified_existing"
    new = ledger_rows(ctx, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="") as f:
        new.to_csv(f, index=False)
    return new, "created"


# ----------------------------------------------------------------------------------------------- matrices
def write_matrices(ctx):
    root = ctx.root
    out = {}
    for fmt in ("BO5", "BO7"):
        P = ctx.P
        if not np.allclose(P + P.T, 1.0, atol=1e-12):
            raise AssertionError("pairwise matrix not complementary")
        long = S.pairwise_long(ctx.strength, P, fmt)
        pq = root / S.OUT_DIR / f"pairwise_{fmt.lower()}_probabilities.parquet"
        if pq.exists():
            pd.testing.assert_frame_equal(pd.read_parquet(pq), long)
        else:
            long.to_parquet(pq, index=False)
        mat = pd.DataFrame(P, index=ctx.names, columns=ctx.names)
        mat.index.name = "row_team_beats_column_team"
        mat.to_csv(root / REPORTS / f"{fmt.lower()}_matchup_matrix.csv")
        out[fmt] = {"max_complement_error": float(np.abs(P + P.T - 1).max()), "min": float(P[~np.eye(12, dtype=bool)].min()),
                    "max": float(P.max())}
    return out


# ----------------------------------------------------------------------------------------------- main
def main(root="."):
    root = Path(root)
    os.chdir(root)
    guard(root)
    ctx = context(root)
    rules = ctx.rules
    cfg, prim = rules["simulation"], rules["scenarios"]["primary"]
    N, SEED = int(cfg["n_sims_primary"]), int(cfg["seed"])
    (root / REPORTS).mkdir(parents=True, exist_ok=True)
    (root / FIGURES).mkdir(parents=True, exist_ok=True)
    tr = rules["scenarios"]["probability_transforms"]
    summary = {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "n": N, "seed": SEED,
               "primary_scenario": prim, "af_outcomes": af_outcomes_absent(root)}
    summary["matrices"] = write_matrices(ctx)

    runs = {}
    runs["PRIMARY"] = simulate(ctx, prim, n=N, seed=SEED, record=True, keep=True)
    variants = {
        "TIEBREAK_T2_WINS_LOT": dict(stage1_tiebreak="T2_WINS_LOT"),
        "TIEBREAK_T3_WINS_GAMEDIFF_STRENGTH": dict(stage1_tiebreak="T3_WINS_GAMEDIFF_STRENGTH"),
        "SELECTION_RANDOM_LEGAL": dict(breakthrough_selection="RANDOM_LEGAL_SELECTION"),
        "SELECTION_ADVERSARIAL": dict(breakthrough_selection="ADVERSARIAL_SELECTION"),
        "POOL_SELECTION_POOL_ANY": dict(selection_pool="SELECTION_POOL_ANY"),
        "POOL_ANY_RANDOM_LEGAL": dict(selection_pool="SELECTION_POOL_ANY", breakthrough_selection="RANDOM_LEGAL_SELECTION"),
        "POOL_ANY_ADVERSARIAL": dict(selection_pool="SELECTION_POOL_ANY", breakthrough_selection="ADVERSARIAL_SELECTION"),
        "DRAW_K2_SEEDS_NOT_PAIRED": dict(knockout_draw="K2_SEEDS_NOT_PAIRED"),
        "DRAW_K3_SEEDS_VS_BREAKTHROUGH": dict(knockout_draw="K3_SEEDS_OPPOSITE_HALVES_VS_BREAKTHROUGH"),
    }
    for name, ov in variants.items():
        runs[name] = simulate(ctx, {**prim, **ov}, n=int(cfg["n_sims_scenario"]), seed=SEED)
    for name in ("CONSERVATIVE", "AGGRESSIVE", "BO7_SENSITIVITY"):
        runs[name] = simulate(ctx, prim, tr[name]["bo5_lambda"], tr[name]["bo7_lambda"], n=int(cfg["n_sims_scenario"]), seed=SEED)
    runs["NEUTRAL_FORMAT"] = simulate(ctx, prim, n=int(cfg["n_sims_scenario"]), seed=SEED, neutral=True)
    runs["PRIMARY_INDEPENDENT_SEED"] = simulate(ctx, prim, n=N, seed=SEED + 1)

    # -------- sanity
    san = []
    for name, r in runs.items():
        for k, v in r["sanity"].items():
            san.append({"run": name, "check": k, "passed": v})
        p = r["p"]
        san += [{"run": name, "check": "sum_champion_probability_equals_1", "passed": bool(abs(p["champion"].sum() - 1) < 1e-9)},
                {"run": name, "check": "sum_final_probability_equals_2", "passed": bool(abs(p["final"].sum() - 2) < 1e-9)},
                {"run": name, "check": "sum_knockout_probability_equals_8", "passed": bool(abs(p["knockout"].sum() - 8) < 1e-9)},
                {"run": name, "check": "all_probabilities_in_0_1", "passed": bool(all(((v >= 0) & (v <= 1)).all() for v in p.values()))}]
    for fmt, m in summary["matrices"].items():
        san.append({"run": "MATRICES", "check": f"{fmt}_complementarity_max_error<1e-12", "passed": m["max_complement_error"] < 1e-12})
    san.append({"run": "ENGINE", "check": "no_reentry_and_termination_asserted_inside_engine(check=True)", "passed": True})
    san = pd.DataFrame(san)
    san.to_csv(root / REPORTS / "sanity_checks.csv", index=False)
    if not san.passed.all():
        raise AssertionError(f"sanity failures: {san[~san.passed]}")

    P0 = runs["PRIMARY"]
    team = pd.DataFrame({"team": ctx.names, "canonical_team_id": ctx.ids, "group": ctx.strength.group,
                         "frozen_b5_rating": ctx.r})

    # -------- convergence
    conv = []
    arr = P0["arrays"]
    full = {k: arr[k].mean(0) for k in arr}
    for c in cfg["convergence_checkpoints"]:
        for k in arr:
            pc = arr[k][:c].mean(0)
            conv.append({"n_sims": c, "quantity": k, "max_abs_diff_vs_full_1M": float(np.abs(pc - full[k]).max()),
                         "max_mc_se_at_n": float(se(pc, c).max())})
    conv = pd.DataFrame(conv)
    ind2 = runs["PRIMARY_INDEPENDENT_SEED"]["p"]
    indep = {k: float(np.abs(ind2[k] - full[k]).max()) for k in arr}
    indep_z = {k: float((np.abs(ind2[k] - full[k]) / np.sqrt(2 * se(full[k], N) ** 2 + 1e-300)).max()) for k in arr}
    step = conv.copy()
    prev = {}
    for i, row in step.iterrows():
        pc = arr[row.quantity][:row.n_sims].mean(0)
        step.loc[i, "max_abs_change_from_previous_checkpoint"] = (float(np.abs(pc - prev[row.quantity]).max())
                                                                   if row.quantity in prev else np.nan)
        prev[row.quantity] = pc
    step["independent_seed_max_abs_diff_at_1M"] = step.quantity.map(indep).where(step.n_sims == N)
    step["independent_seed_max_z_at_1M"] = step.quantity.map(indep_z).where(step.n_sims == N)
    step.to_csv(root / REPORTS / "monte_carlo_convergence.csv", index=False)
    last = step[step.n_sims == N].max_abs_change_from_previous_checkpoint.max()
    converged = bool(last <= CONVERGENCE_TOL and max(indep_z.values()) < 4.5)
    summary["convergence"] = {"max_change_500k_to_1M": float(last), "tolerance": CONVERGENCE_TOL,
                              "independent_seed_max_abs_diff": indep, "independent_seed_max_z": indep_z,
                              "converged": converged}

    # -------- forecast table
    n = N
    fc = team[["team", "canonical_team_id", "group", "frozen_b5_rating"]].copy()
    for col, key in (("direct_knockout_probability", "direct_knockout"), ("breakthrough_probability", "breakthrough"),
                     ("stage1_elimination_probability", "stage1_elimination"), ("breakthrough_win_probability", "breakthrough_win"),
                     ("knockout_probability", "knockout"), ("upper_semifinal_probability", "upper_semifinal"),
                     ("upper_final_probability", "upper_final"), ("drop_to_lower_bracket_probability", "drop_to_lower"),
                     ("lower_final_probability", "lower_final"), ("final_probability", "final"),
                     ("championship_probability", "champion")):
        fc[col] = P0["p"][key]
    fc["championship_probability_conservative"] = runs["CONSERVATIVE"]["p"]["champion"]
    fc["championship_probability_aggressive"] = runs["AGGRESSIVE"]["p"]["champion"]
    fc["championship_probability_bo7_sensitivity"] = runs["BO7_SENSITIVITY"]["p"]["champion"]
    for key in ("knockout", "final", "champion"):
        fc[f"mc_se_{key}"] = se(P0["p"][key], n)
    fc["n_simulations"] = n
    fc["label"] = "PRIMARY = frozen raw B5; conservative/aggressive/bo7_sensitivity are SENSITIVITY ONLY"
    fc = fc.sort_values("championship_probability", ascending=False)
    fc.to_csv(root / REPORTS / "team_forecast_2026.csv", index=False)

    # -------- stage 1
    st = team.copy()
    st["expected_series_wins"], st["expected_game_diff"] = P0["wins_mean"], P0["gd_mean"]
    for g, grp in (("master", E.MASTER), ("elite", E.ELITE)):
        for j, t in enumerate(grp):
            for rk in range(6):
                st.loc[t, f"p_group_rank_{rk + 1}"] = P0["rank_dist"][g][j][rk]
    st["p_direct_knockout"], st["p_breakthrough"], st["p_stage1_elimination"] = (
        P0["p"]["direct_knockout"], P0["p"]["breakthrough"], P0["p"]["stage1_elimination"])
    for nm in ("TIEBREAK_T2_WINS_LOT", "TIEBREAK_T3_WINS_GAMEDIFF_STRENGTH"):
        st[f"p_direct_knockout_{nm}"] = runs[nm]["p"]["direct_knockout"]
        st[f"p_stage1_elimination_{nm}"] = runs[nm]["p"]["stage1_elimination"]
    st.to_csv(root / REPORTS / "stage1_forecast.csv", index=False)

    tb = []
    for name in ("PRIMARY", "TIEBREAK_T2_WINS_LOT", "TIEBREAK_T3_WINS_GAMEDIFF_STRENGTH"):
        r = runs[name]
        for g in ("master", "elite"):
            for b in range(5):
                a = r["audit"][g]
                tb.append({"run": name, "group": g.upper(), "boundary": f"rank {b + 1} | rank {b + 2}",
                           "consequence_under_primary": CONSEQUENTIAL[(g, b)],
                           "p_tied_on_series_wins": a["tied_on_wins"][b], "p_resolved_by_game_diff": a["resolved_by_game_diff"][b],
                           "p_reached_final_fallback": a["fallback"][b]})
        tb.append({"run": name, "group": "ANY", "boundary": "any consequential boundary",
                   "consequence_under_primary": "affected probability mass",
                   "p_tied_on_series_wins": r["mass_consequential_tie"], "p_resolved_by_game_diff": np.nan,
                   "p_reached_final_fallback": r["mass_consequential_fallback"]})
    pd.DataFrame(tb).to_csv(root / REPORTS / "stage1_tiebreak_audit.csv", index=False)

    # -------- breakthrough
    bt = team.copy()
    bt["p_enter_breakthrough"] = P0["p"]["breakthrough"]
    for name in ("PRIMARY", "SELECTION_RANDOM_LEGAL", "SELECTION_ADVERSARIAL", "POOL_SELECTION_POOL_ANY",
                 "POOL_ANY_RANDOM_LEGAL", "POOL_ANY_ADVERSARIAL"):
        bt[f"p_breakthrough_win__{name}"] = runs[name]["p"]["breakthrough_win"]
        bt[f"p_champion__{name}"] = runs[name]["p"]["champion"]
    bt["p_bt_win_given_bt__PRIMARY"] = P0["cond"]["bt_win_given_breakthrough"]
    bt.to_csv(root / REPORTS / "breakthrough_scenarios.csv", index=False)
    mp = []
    for name in ("PRIMARY", "SELECTION_RANDOM_LEGAL", "SELECTION_ADVERSARIAL", "POOL_SELECTION_POOL_ANY"):
        for k in range(3):
            for code_, f in runs[name]["bt_pairs"][k].items():
                a, b = divmod(int(code_), 12)
                mp.append({"run": name, "match": ["M1 (10-20)", "M2 (10-21)", "M3 (10-22)"][k], "selector_or_side_a": ctx.names[a],
                           "opponent": ctx.names[b], "frequency": f, "p_side_a_wins_bo7": float(ctx.P[a, b])})
    pd.DataFrame(mp).sort_values(["run", "match", "frequency"], ascending=[True, True, False]).to_csv(
        root / REPORTS / "breakthrough_matchups.csv", index=False)

    # -------- knockout + path
    ko = team.copy()
    for k in ("knockout", "upper_semifinal", "upper_final", "upper_final_win", "drop_to_lower", "lower_final", "final", "champion"):
        ko[f"p_{k}"] = P0["p"][k]
    for k in E.ELIM_CODES:
        ko[f"p_terminal_{k}"] = P0["elim"][k]
    ko["p_champion_given_knockout"] = P0["cond"]["champion_given_knockout"]
    ko.to_csv(root / REPORTS / "knockout_forecast.csv", index=False)
    pa = team.copy()
    for k, v in P0["path"].items():
        pa[f"expected_{k}"] = v
    pa["expected_bo7_series"] = P0["expected_bo7"]
    pa["p_direct_entry"], pa["p_breakthrough_entry"] = P0["p"]["direct_knockout"], P0["p"]["breakthrough"]
    for k, v in P0["cond"].items():
        pa[k] = v
    pa["PATH_ADVANTAGE_champion_direct_minus_breakthrough"] = pa.champion_given_direct - pa.champion_given_breakthrough
    pa["PATH_COST_p_eliminated_in_breakthrough_given_entry"] = 1 - pa.bt_win_given_breakthrough
    pa["FORMAT_EXPOSURE_bo7_share_of_series"] = pa.expected_bo7 / pa.expected_series
    pa.to_csv(root / REPORTS / "path_metrics.csv", index=False)

    # -------- structural value, draw, sensitivity, materiality
    sv = team.copy()
    Nn = runs["NEUTRAL_FORMAT"]["p"]
    for k in ("knockout", "final", "champion"):
        sv[f"{k}_REAL_FORMAT"], sv[f"{k}_NEUTRAL_FORMAT"] = P0["p"][k], Nn[k]
        sv[f"{k}_STRUCTURAL_DIFFERENCE"] = P0["p"][k] - Nn[k]
        sv[f"{k}_difference_mc_se"] = np.sqrt(se(P0["p"][k], n) ** 2 + se(Nn[k], n) ** 2)
    sv["interpretation"] = "descriptive, non-causal: format dependence under frozen B5, not a causal effect"
    sv.to_csv(root / REPORTS / "structural_value.csv", index=False)

    sens = []
    for name, r in runs.items():
        for t in range(12):
            sens.append({"run": name, "team": ctx.names[t], **{f"p_{k}": float(r["p"][k][t]) for k in ("knockout", "final", "champion")}})
    sens = pd.DataFrame(sens)
    sens.to_csv(root / REPORTS / "sensitivity.csv", index=False)
    dr = team.copy()
    for name in ("PRIMARY", "DRAW_K2_SEEDS_NOT_PAIRED", "DRAW_K3_SEEDS_VS_BREAKTHROUGH"):
        for k in ("upper_final", "final", "champion"):
            dr[f"p_{k}__{name}"] = runs[name]["p"][k]
    dr.to_csv(root / REPORTS / "draw_scenarios.csv", index=False)

    thr = float(rules["materiality"]["championship_abs_threshold"])
    fam = {"R06_STAGE1_RANKING_AND_TIEBREAK": ["TIEBREAK_T2_WINS_LOT", "TIEBREAK_T3_WINS_GAMEDIFF_STRENGTH"],
           "R10_BREAKTHROUGH_SELECTION_DETAIL": ["POOL_SELECTION_POOL_ANY"],
           "R13_KNOCKOUT_DRAW_SEED_MEANING": ["DRAW_K2_SEEDS_NOT_PAIRED", "DRAW_K3_SEEDS_VS_BREAKTHROUGH"],
           "SELECTION_BEHAVIOUR (not a rule; OPTIMAL is PRIMARY)": ["SELECTION_RANDOM_LEGAL", "SELECTION_ADVERSARIAL"]}
    mat = []
    for rule, alts in fam.items():
        for alt in alts:
            d = runs[alt]["p"]["champion"] - P0["p"]["champion"]
            cse = np.sqrt(se(runs[alt]["p"]["champion"], n) ** 2 + se(P0["p"]["champion"], n) ** 2)
            t = int(np.argmax(np.abs(d)))
            mat.append({"rule": rule, "scenario": alt, "max_abs_championship_delta": float(abs(d[t])), "team_at_max": ctx.names[t],
                        "combined_mc_se": float(cse[t]), "threshold": thr,
                        "material": bool(abs(d[t]) > thr and abs(d[t]) > 4 * cse[t]),
                        "max_abs_final_delta": float(np.abs(runs[alt]["p"]["final"] - P0["p"]["final"]).max()),
                        "max_abs_knockout_delta": float(np.abs(runs[alt]["p"]["knockout"] - P0["p"]["knockout"]).max())})
    mat = pd.DataFrame(mat)
    mat.to_csv(root / REPORTS / "materiality.csv", index=False)
    unresolved_material = bool(mat[~mat.rule.str.startswith("SELECTION")].material.any())

    # -------- rotation, ledger
    teams_df = pd.read_parquet(root / S.TEAMS_FILE)
    rotation.master_rotation(teams_df, root).to_csv(root / REPORTS / "master_rotation_readiness.csv", index=False)
    led, led_status = write_ledger(ctx)
    summary["ledger"] = {"status": led_status, "rows": len(led),
                         "content_sha256_excluding_generated_at": hashlib.sha256(
                             led.drop(columns="generated_at").to_csv(index=False).encode()).hexdigest()}

    # -------- freeze gate (never freezes)
    status = {r["id"]: r["verification_status"] for r in rules["rules"]}
    gate = {
        "1_identities_resolve": True,
        "2_stage1_schedule_verified": status["R03_STAGE1_FORMAT"] == "VERIFIED_OFFICIAL" and status["R04_STAGE1_SCHEDULE_DATES"].startswith("VERIFIED"),
        "3_advancement_verified": status["R05_STAGE1_ADVANCEMENT"] == "VERIFIED_OFFICIAL" and status["R06_STAGE1_RANKING_AND_TIEBREAK"].startswith("VERIFIED"),
        "4_breakthrough_selection_verified": status["R10_BREAKTHROUGH_SELECTION_DETAIL"].startswith("VERIFIED"),
        # R13 seed-slot meaning is unpublished, so the draw stays unverified whatever the wiring status
        "5_draw_bracket_verified": False,
        "5a_bracket_wiring_status": status["R12_KNOCKOUT_BRACKET_WIRING"],
        "6_no_unresolved_rule_materially_changes_championship": not unresolved_material,
        "7_tests_pass": None,
        "8_locks_pass": None,
        "9_af_outcomes_absent": af_outcomes_absent(root)["ok"],
    }
    summary["freeze_gate_partial"] = gate
    summary["unresolved_rule_material"] = unresolved_material
    summary["sanity_all_passed"] = bool(san.passed.all())
    bad = lock.check(root)
    summary["lock_after_run"] = "PASS" if not bad else bad
    (root / REPORTS / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=float))

    from openkpl.tournament import figures
    figures.make_all(root, ctx, runs, fc, conv, step, pa)
    return summary


if __name__ == "__main__":
    print(json.dumps(main("."), ensure_ascii=False, indent=2, default=float))
