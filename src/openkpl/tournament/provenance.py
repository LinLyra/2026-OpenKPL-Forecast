"""v1.0a rule-provenance sensitivity (SENSITIVITY ONLY; never replaces PRIMARY, never touches the frozen ledger).

Runs structural interpretations suggested by HISTORICAL_RULE_PROXY evidence (2024/2025 official rulebooks) that the
v1.0 scenario set did not cover, reusing the unchanged v1.0 engine and frozen B5 matrix, then classifies every
unresolved rule by its maximum championship-probability change.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.tournament import engine as E
from openkpl.tournament import lock, run

OUT = "reports/tournament/rule_proxy_sensitivity.csv"
MATERIALITY = "reports/tournament/rule_materiality_v10a.csv"
CAPTURES = "data/raw/tournament_structure/2026-09-29_provenance"
IMMATERIAL, MATERIAL = 0.005, 0.02

# alternative wiring: same-half lower round 1 and crossed lower round 2 (a common 8-team double-elimination layout)
BRACKET_ALT = [
    ("QF1", ("S", 0), ("S", 1)), ("QF2", ("S", 2), ("S", 3)), ("QF3", ("S", 4), ("S", 5)), ("QF4", ("S", 6), ("S", 7)),
    ("LB1A", ("L", "QF1"), ("L", "QF2")), ("LB1B", ("L", "QF3"), ("L", "QF4")),
    ("SF1", ("W", "QF1"), ("W", "QF2")), ("SF2", ("W", "QF3"), ("W", "QF4")),
    ("LB2A", ("W", "LB1A"), ("L", "SF2")), ("LB2B", ("W", "LB1B"), ("L", "SF1")),
    ("UBF", ("W", "SF1"), ("W", "SF2")),
    ("LBSF", ("W", "LB2A"), ("W", "LB2B")),
    ("LBF", ("L", "UBF"), ("W", "LBSF")),
    ("FINAL", ("W", "UBF"), ("W", "LBF")),
]


def classify(delta):
    return "IMMATERIAL" if delta < IMMATERIAL else ("LOW" if delta <= MATERIAL else "MATERIAL")


def breakthrough_protected(sim, selectors, pool, strategy):
    """2025-rulebook reading: selectors (N,3) = [M5, M6, E2] choose in order from pool (N,3) = [E3, E4, E5];
    selectors never meet each other; the last selector receives the remaining team."""
    n, rows = sim.n, np.arange(sim.n)
    avail = np.ones((n, 3), bool)
    pairs = np.zeros((n, 3, 2), int)
    for k in range(3):
        opp_r = sim.r[pool]
        if strategy == "OPTIMAL_SELECTION":
            pick = np.argmin(np.where(avail, opp_r, np.inf), axis=1)
        elif strategy == "ADVERSARIAL_SELECTION":
            pick = np.argmax(np.where(avail, opp_r, -np.inf), axis=1)
        elif strategy == "RANDOM_LEGAL_SELECTION":
            pick = np.argmax(np.where(avail, sim.rng.random((n, 3)), -1.0), axis=1)
        else:
            raise ValueError(strategy)
        if not avail[rows, pick].all():
            raise AssertionError("illegal breakthrough selection")
        avail[rows, pick] = False
        pairs[:, k, 0], pairs[:, k, 1] = selectors[:, k], pool[rows, pick]
    winners, losers = np.zeros((n, 3), int), np.zeros((n, 3), int)
    for k in range(3):
        winners[:, k], losers[:, k] = sim.play(pairs[:, k, 0], pairs[:, k, 1], E.BO7)
    return winners, losers, pairs


def double_elimination_wired(slots, play, bracket):
    """Same state machine and assertions as engine.double_elimination, with an injectable wiring."""
    n = slots.shape[0]
    rows = np.arange(n)
    losses = np.zeros((n, E.N_TEAMS), np.int8)
    res = {}
    for m, sa, sb in bracket:
        a, b = (slots[:, ref] if kind == "S" else res[ref][2 if kind == "W" else 3] for kind, ref in (sa, sb))
        if np.any(losses[rows, a] >= 2) or np.any(losses[rows, b] >= 2):
            raise AssertionError(f"{m}: eliminated team re-entered the bracket")
        if m in E.UPPER and (np.any(losses[rows, a] > 0) or np.any(losses[rows, b] > 0)):
            raise AssertionError(f"{m}: team with a loss in the upper bracket")
        w, l = play(a, b, E.BO7)
        losses[rows, l] += 1
        res[m] = (a, b, w, l)
    res["champion"], res["losses"] = res["FINAL"][2], losses
    champ, runner = res["champion"], res["FINAL"][3]
    lz = losses[rows[:, None], slots]
    other = ~((slots == champ[:, None]) | (slots == runner[:, None]))
    if np.any(losses[rows, champ] > 1) or np.any((losses[rows, runner] < 1) | (losses[rows, runner] > 2)) \
            or np.any(lz[other].reshape(n, 6) != 2):
        raise AssertionError("invalid double-elimination termination")
    return res


def tournament_variant(sim, schedule, scenario, bt_mode="ENGINE", bracket=None):
    """engine.tournament with an optional protected-selector breakthrough and/or alternative wiring."""
    s1 = E.stage1(sim, schedule, scenario["stage1_tiebreak"])
    M, Q = s1["master"], s1["elite"]
    if bt_mode == "ENGINE":
        bw, bl, pairs = E.breakthrough(sim, M[:, 4], M[:, 5], Q[:, 1:5], scenario["breakthrough_selection"],
                                       scenario["selection_pool"])
    elif bt_mode == "PROTECTED_M5_M6_E2":
        bw, bl, pairs = breakthrough_protected(sim, np.column_stack([M[:, 4], M[:, 5], Q[:, 1]]), Q[:, 2:5],
                                               scenario["breakthrough_selection"])
    else:
        raise ValueError(bt_mode)
    slots = E.draw(sim.rng, M[:, :2], np.column_stack([M[:, 2:4], Q[:, :1], bw]), bw, scenario["knockout_draw"])
    ko = np.sort(slots, axis=1)
    if np.any(ko[:, 1:] == ko[:, :-1]):
        raise AssertionError("duplicate team in knockout draw")
    de = E.double_elimination(slots, sim.play) if bracket is None else double_elimination_wired(slots, sim.play, bracket)
    return {"stage1": s1, "direct": np.column_stack([M[:, :4], Q[:, :1]]), "bt_teams": np.column_stack([M[:, 4:6], Q[:, 1:5]]),
            "elim1": Q[:, 5], "bt_winners": bw, "bt_losers": bl, "bt_pairs": pairs, "slots": slots, "de": de,
            "champion": de["champion"]}


VARIANTS = {  # name: (rule, scenario overrides, breakthrough mode, bracket)
    "BT_PROTECTED_M5_M6_E2_OPTIMAL": ("R10_BREAKTHROUGH_SELECTION_DETAIL", {}, "PROTECTED_M5_M6_E2", None),
    "BT_PROTECTED_M5_M6_E2_RANDOM": ("R10_BREAKTHROUGH_SELECTION_DETAIL", {"breakthrough_selection": "RANDOM_LEGAL_SELECTION"},
                                     "PROTECTED_M5_M6_E2", None),
    "BT_PROTECTED_M5_M6_E2_ADVERSARIAL": ("R10_BREAKTHROUGH_SELECTION_DETAIL", {"breakthrough_selection": "ADVERSARIAL_SELECTION"},
                                          "PROTECTED_M5_M6_E2", None),
    "WIRING_ALT_SAMEHALF_LB1_CROSSED_LB2": ("R12_KNOCKOUT_BRACKET_WIRING", {}, "ENGINE", BRACKET_ALT),
    "PROXY_COMBINED_T3_PROTECTED_OPTIMAL": ("COMBINED_HISTORICAL_PROXY", {"stage1_tiebreak": "T3_WINS_GAMEDIFF_STRENGTH"},
                                            "PROTECTED_M5_M6_E2", None),
}


V10_RULE_RUNS = {
    "TIEBREAK_T2_WINS_LOT": "R06_STAGE1_RANKING_AND_TIEBREAK",
    "TIEBREAK_T3_WINS_GAMEDIFF_STRENGTH": "R06_STAGE1_RANKING_AND_TIEBREAK",
    "POOL_SELECTION_POOL_ANY": "R10_BREAKTHROUGH_SELECTION_DETAIL",
    "POOL_ANY_RANDOM_LEGAL": "R10_BREAKTHROUGH_SELECTION_DETAIL",
    "POOL_ANY_ADVERSARIAL": "R10_BREAKTHROUGH_SELECTION_DETAIL",
    "SELECTION_RANDOM_LEGAL": "R10_BREAKTHROUGH_SELECTION_BEHAVIOUR (not a rule; OPTIMAL is PRIMARY)",
    "SELECTION_ADVERSARIAL": "R10_BREAKTHROUGH_SELECTION_BEHAVIOUR (not a rule; OPTIMAL is PRIMARY)",
    "DRAW_K2_SEEDS_NOT_PAIRED": "R13_KNOCKOUT_DRAW_SEED_MEANING",
    "DRAW_K3_SEEDS_VS_BREAKTHROUGH": "R13_KNOCKOUT_DRAW_SEED_MEANING",
}


def simulate_variant(ctx, overrides, bt_mode, bracket, n, seed):
    sim = E.Sim(ctx.P, ctx.P, ctx.r, n, np.random.default_rng(seed))
    out = tournament_variant(sim, ctx.schedule, {**ctx.rules["scenarios"]["primary"], **overrides}, bt_mode, bracket)
    ind = E.team_indicators(out, n)
    for k, v in {"champion": 1, "final": 2, "knockout": 8, "direct_knockout": 5, "breakthrough_win": 3}.items():
        if not (ind[k].sum(1) == v).all():
            raise AssertionError(f"sanity: {k}")
    if not (ind["elimination_code"] >= 0).all():
        raise AssertionError("sanity: termination")
    return {k: ind[k].mean(0) for k in ("knockout", "final", "champion", "breakthrough_win")}


def main(root="."):
    root = Path(root)
    run.guard(root)
    ctx = run.context(root)
    cfg = ctx.rules["simulation"]
    n, seed = int(cfg["n_sims_scenario"]), int(cfg["seed"])
    sens = pd.read_csv(root / run.REPORTS / "sensitivity.csv")
    prim = sens[sens.run == "PRIMARY"].set_index("team").loc[ctx.names]
    se = lambda p: np.sqrt(p * (1 - p) / n)
    rows, mat = [], []
    for name, (rule, ov, bt_mode, bracket) in VARIANTS.items():
        p = simulate_variant(ctx, ov, bt_mode, bracket, n, seed)
        for t in range(12):
            rows.append({"scenario": name, "rule": rule, "team": ctx.names[t], **{f"p_{k}": float(v[t]) for k, v in p.items()},
                         **{f"delta_{k}_vs_primary": float(p[k][t] - prim[f"p_{k}"].iloc[t]) for k in ("knockout", "final", "champion")}})
        d = {k: np.abs(p[k] - prim[f"p_{k}"].to_numpy()) for k in ("knockout", "final", "champion")}
        t = int(np.argmax(d["champion"]))
        mat.append({"rule": rule, "scenario": name, "source_of_scenario": "v1.0a (HISTORICAL_RULE_PROXY-motivated)",
                    "max_abs_championship_delta": float(d["champion"][t]), "team_at_max": ctx.names[t],
                    "combined_mc_se": float(np.sqrt(se(p["champion"][t]) ** 2 + se(prim.p_champion.iloc[t]) ** 2)),
                    "max_abs_final_delta": float(d["final"].max()), "max_abs_knockout_delta": float(d["knockout"].max())})
    pd.DataFrame(rows).to_csv(root / OUT, index=False)
    old = []
    for scen, rule in V10_RULE_RUNS.items():
        s = sens[sens.run == scen].set_index("team").loc[ctx.names]
        d = {k: (s[f"p_{k}"] - prim[f"p_{k}"]).abs() for k in ("knockout", "final", "champion")}
        t = d["champion"].idxmax()
        old.append({"rule": rule, "scenario": scen, "source_of_scenario": "v1.0 stored sensitivity.csv (not rerun)",
                    "max_abs_championship_delta": float(d["champion"].max()), "team_at_max": t,
                    "combined_mc_se": float(np.sqrt(se(s.p_champion[t]) ** 2 + se(prim.p_champion[t]) ** 2)),
                    "max_abs_final_delta": float(d["final"].max()), "max_abs_knockout_delta": float(d["knockout"].max())})
    allm = pd.concat([pd.DataFrame(old), pd.DataFrame(mat)], ignore_index=True)
    allm["classification"] = allm.max_abs_championship_delta.map(classify)
    allm["note"] = "descriptive only; thresholds IMMATERIAL <0.005, LOW 0.005-0.02, MATERIAL >0.02 (championship)"
    allm.to_csv(root / MATERIALITY, index=False)
    if lock.check(root):
        raise RuntimeError("v1.0 lock mismatch after provenance run")
    return allm


if __name__ == "__main__":
    print(main(".").drop(columns="note").round(4).to_string())
