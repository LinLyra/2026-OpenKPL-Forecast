"""Experiment B: does the observed draft add information beyond pre-draft team strength?

Universe: the 1,942 uniquely identified WZRY games; primary target = kplow game winner
(team_a = the series' canonical team_a). WZRY's winner is never a feature or a target here.
All hero statistics are the Phase B leakage-safe prior tables (strictly earlier identified
games, kplow winners only); this module only re-shrinks their raw prior counts:

    shr(w, d) = (w + K * 0.5) / (d + K)   if d >= min_n,   else 0.5

(K, min_n) is selected per fold on training seasons only (inner last-season holdout).
"""
import math
from collections import defaultdict

import numpy as np
import pandas as pd

from openkpl.game_draft_model.series_math import game_prob_from_series
from openkpl.player_model import models as M

HF = "data/processed/features/hero_temporal_features.parquet"
SF = "data/processed/features/hero_synergy_temporal.parquet"
CF = "data/processed/features/hero_counter_temporal.parquet"
EV = "data/processed/drafts/draft_events_identified.parquet"

K_GRID = [2.0, 5.0, 10.0, 20.0, 50.0]
MIN_N_GRID = [0, 5, 10]
DEFAULT_SHRINK = (10.0, 0)
RECENCY_GRID = [math.inf, 60.0, 180.0, 365.0]
D5_C_GRID = [0.01, 0.03, 0.1, 0.3, 1.0]
D6_GRID = [{"max_iter": it, "max_depth": d} for it in (50, 100, 200) for d in (2, 3)]
FEATS = {
    "D1": ["hero_strength", "hero_pick_rate", "hero_winrate_raw"],
    "D2": ["team_hero_familiarity", "team_hero_strength"],
    "D3": ["synergy", "pair_novelty"],
    "D4": ["counter"],
    "D5_extra": ["ban_strength"],
}
LADDER = {"D1": ["D1"], "D2": ["D1", "D2"], "D3": ["D1", "D2", "D3"], "D4": ["D1", "D2", "D3", "D4"]}
ALL_STATIC = ["D1", "D2", "D3", "D4", "D5_extra"]
CHECKPOINTS = {0: "PRE_DRAFT", 4: "AFTER_FIRST_BAN_PHASE", 10: "AFTER_FIRST_PICK_PHASE",
               14: "AFTER_SECOND_BAN_PHASE", 18: "FINAL_DRAFT (= AFTER_SECOND_PICK_PHASE in 4B-6P-4B-4P)"}
STEP_FEATS = ["hero_strength_sum", "team_hero_strength_sum", "familiarity_sum", "synergy_sum", "counter_sum", "n_picks"]


def shr(w, d, k, min_n):
    w, d = np.asarray(w, float), np.asarray(d, float)
    return np.where(d >= max(min_n, 0), (w + k * 0.5) / (d + k), 0.5)


def cols(groups, pre="logit_d0"):
    c = [pre] + [f"{f}_diff" for g in groups for f in FEATS[g]]
    M.assert_deployable(c)
    if any("wzry" in x for x in c):
        raise ValueError("WZRY winner-derived column in draft model")
    return c


def load(root="."):
    from pathlib import Path
    root = Path(root)
    return tuple(pd.read_parquet(root / p) for p in (HF, SF, CF, EV))


def game_table(identified, timeline):
    """Identified games joined to kplow series orientation and kplow winner."""
    info = {}
    for s in timeline:
        for g in s["games"]:
            info[g["game_key"]] = (s["series_id"], s["a"], s["b"], s["format"], s["p_b5"], g["winner_side"], s["season"])
    rows = []
    for r in identified.itertuples(index=False):
        sid, a, b, fmt, pb5, side, season = info[r.game_key]
        if {r.team1, r.team2} != {a, b}:
            raise AssertionError(f"team mismatch for {r.game_key}")
        rows.append({"game_key": r.game_key, "series_id": sid, "season": season, "date": pd.Timestamp(r.date),
                     "game_number": int(r.game_number), "format": fmt, "team_a": a, "team_b": b, "p_b5": pb5,
                     "y": None if side is None else int(side == "a"), "kplow_winner_known": side is not None})
    return pd.DataFrame(rows).set_index("game_key", drop=False)


def static_features(gt, hf, sf, cf, k, min_n):
    picks = hf[hf.ban_or_pick == "pick"].copy()
    rank = picks.groupby("game_key").temporal_rank.first()
    picks["hero_s"] = shr(picks.hero_prior_wins, picks.hero_prior_decided, k, min_n) - 0.5
    picks["hero_raw"] = np.where(picks.hero_prior_decided >= max(min_n, 1),
                                 picks.hero_prior_wins / picks.hero_prior_decided.clip(lower=1), 0.5) - 0.5
    picks["pick_rate"] = picks.hero_prior_pick_count / picks.game_key.map(rank).clip(lower=1)
    picks["fam"] = np.log1p(picks.team_hero_prior_games)
    picks["th_s"] = shr(picks.team_hero_prior_wins, picks.team_hero_prior_decided, k, min_n) - 0.5
    agg = picks.groupby(["game_key", "team_id"]).agg(hero_strength=("hero_s", "mean"), hero_winrate_raw=("hero_raw", "mean"),
                                                     hero_pick_rate=("pick_rate", "mean"), team_hero_familiarity=("fam", "mean"),
                                                     team_hero_strength=("th_s", "mean"))
    bans = hf[hf.ban_or_pick == "ban"].copy()
    bans["ban_s"] = shr(bans.hero_prior_wins, bans.hero_prior_decided, k, min_n) - 0.5
    agg = agg.join(bans.groupby(["game_key", "team_id"]).ban_s.mean().rename("ban_strength"), how="left")
    s = sf.assign(v=shr(sf.pair_prior_wins, sf.pair_prior_decided, k, min_n) - 0.5, nov=(sf.pair_prior_games == 0).astype(float))
    agg = agg.join(s.groupby(["game_key", "team_id"]).agg(synergy=("v", "mean"), pair_novelty=("nov", "mean")), how="left")
    c = cf.assign(v=shr(cf.vs_prior_wins, cf.vs_prior_decided, k, min_n) - 0.5)
    agg = agg.join(c.groupby(["game_key", "team_id"]).v.mean().rename("counter"), how="left")
    names = [f for g in ALL_STATIC for f in FEATS[g]]
    out = gt[["game_key"]].copy()
    for side in ("a", "b"):
        idx = pd.MultiIndex.from_arrays([gt.game_key, gt[f"team_{side}"]])
        vals = agg.reindex(idx)
        for n in names:
            out[f"{n}_{side}"] = vals[n].to_numpy()
    for n in names:
        out[f"{n}_diff"] = out[f"{n}_a"] - out[f"{n}_b"]
    return out.drop(columns="game_key")


def recency_hero_strength(gt, hf, k, min_n, half_life):
    """Hero strength from strictly earlier identified games with weights 0.5 ** (days / half_life)."""
    picks = hf[hf.ban_or_pick == "pick"][["game_key", "temporal_rank", "team_id", "hero_name", "won_current_game_label"]]
    picks = picks.assign(date=picks.game_key.map(gt.date)).sort_values("temporal_rank", kind="stable")
    hist = defaultdict(list)
    res = {}
    for rank, g in picks.groupby("temporal_rank", sort=True):
        for r in g.itertuples(index=False):
            h = hist[r.hero_name]
            if h:
                dts = np.array([(r.date - x[0]).days for x in h], float)
                wt = np.ones_like(dts) if math.isinf(half_life) else 0.5 ** (dts / half_life)
                won = np.array([x[1] for x in h], float)
                w, d = float((wt * won).sum()), float(wt.sum())
            else:
                w, d = 0.0, 0.0
            res.setdefault((r.game_key, r.team_id), []).append(float(shr(w, d, k, min_n)) - 0.5)
        for r in g.itertuples(index=False):
            if r.won_current_game_label is not None and not pd.isna(r.won_current_game_label):
                hist[r.hero_name].append((r.date, bool(r.won_current_game_label)))
    a = [np.mean(res.get((gk, t), [np.nan])) for gk, t in zip(gt.game_key, gt.team_a)]
    b = [np.mean(res.get((gk, t), [np.nan])) for gk, t in zip(gt.game_key, gt.team_b)]
    return pd.Series(np.array(a) - np.array(b), index=gt.index)


# ---- sequential ------------------------------------------------------------------

class StepLookup:
    def __init__(self, hf, sf, cf, k, min_n):
        p = hf[hf.ban_or_pick == "pick"]
        self.hero = {(g, t, h): (float(shr(w, d, k, min_n)) - 0.5, float(shr(tw, td, k, min_n)) - 0.5, math.log1p(tg))
                     for g, t, h, w, d, tw, td, tg in zip(p.game_key, p.team_id, p.hero_name, p.hero_prior_wins,
                                                          p.hero_prior_decided, p.team_hero_prior_wins,
                                                          p.team_hero_prior_decided, p.team_hero_prior_games)}
        self.pair = {(g, t, frozenset((x, y))): float(shr(w, d, k, min_n)) - 0.5
                     for g, t, x, y, w, d in zip(sf.game_key, sf.team_id, sf.hero_a, sf.hero_b,
                                                 sf.pair_prior_wins, sf.pair_prior_decided)}
        self.vs = {(g, t, x, y): float(shr(w, d, k, min_n)) - 0.5
                   for g, t, x, y, w, d in zip(cf.game_key, cf.team_id, cf.hero, cf.opponent_hero,
                                               cf.vs_prior_wins, cf.vs_prior_decided)}


def step_features(game_key, events, j, team_a, team_b, lk):
    """Features from the first j draft events only (events sorted by sequence)."""
    picks = {team_a: [], team_b: []}
    for e in events[:j]:
        if e["ban_or_pick"] == "pick" and e["team_id"] in picks:
            picks[e["team_id"]].append(e["hero_name"])
    f = {}
    for side, team, opp in (("a", team_a, team_b), ("b", team_b, team_a)):
        ps = picks[team]
        hv = [lk.hero.get((game_key, team, h), (0.0, 0.0, 0.0)) for h in ps]
        f[f"hero_strength_sum_{side}"] = sum(x[0] for x in hv)
        f[f"team_hero_strength_sum_{side}"] = sum(x[1] for x in hv)
        f[f"familiarity_sum_{side}"] = sum(x[2] for x in hv)
        f[f"synergy_sum_{side}"] = sum(lk.pair.get((game_key, team, frozenset((x, y))), 0.0)
                                       for i, x in enumerate(ps) for y in ps[i + 1:])
        f[f"counter_sum_{side}"] = sum(lk.vs.get((game_key, team, x, y), 0.0) for x in ps for y in picks[opp])
        f[f"n_picks_{side}"] = len(ps)
    for n in STEP_FEATS:
        f[f"{n}_diff"] = f[f"{n}_a"] - f[f"{n}_b"]
    return f


def first_pick_team(events):
    for e in events:
        if e["ban_or_pick"] == "pick":
            return e["team_id"]
    return None
