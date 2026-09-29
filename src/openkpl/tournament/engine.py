"""Vectorized Monte Carlo engine for the 2026 KPL Annual Finals (structure from config/2026_annual_finals_rules.yaml).

Every function operates on N simulations at once. Team indices 0-5 are Master seeds 1-6 and 6-11 are Elite
seeds 7-12. Series outcomes come only from a frozen pairwise probability matrix (no within-tournament updating).
The bracket code takes an injected `play(a, b, fmt)` so tests can drive it with deterministic winners.
"""
import numpy as np

N_TEAMS = 12
MASTER = np.arange(6)
ELITE = np.arange(6, 12)
BO5, BO7 = "BO5", "BO7"
ELIM_CODES = {"STAGE1": 0, "BREAKTHROUGH": 1, "LB_R1": 2, "LB_R2": 3, "LB_SF": 4, "LB_F": 5, "FINAL": 6, "CHAMPION": 7}


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def logit(p):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return np.log(p / (1 - p))


def elo_matrix(ratings, scale=400.0):
    r = np.asarray(ratings, float)
    return 1.0 / (1.0 + 10.0 ** ((r[None, :] - r[:, None]) / scale))


def transform(P, lam):
    Q = sigmoid(lam * logit(P))
    np.fill_diagonal(Q, 0.5)
    return Q


def bo5_game_prob(p_series, tol=1e-13):
    """Constant per-game p whose BO5 series probability equals p_series (only used to draw game scores)."""
    lo, hi = np.zeros_like(p_series), np.ones_like(p_series)
    for _ in range(60):
        mid = (lo + hi) / 2
        s = mid ** 3 * (1 + 3 * (1 - mid) + 6 * (1 - mid) ** 2)
        lo, hi = np.where(s < p_series, mid, lo), np.where(s < p_series, hi, mid)
    return (lo + hi) / 2


class Recorder:
    """Per-team path accounting: series counts by format, opponent rating and (1 - p_win) sums."""

    def __init__(self, n, ratings, P_ref):
        self.n, self.r, self.P = n, np.asarray(ratings, float), P_ref
        z = np.zeros(N_TEAMS)
        self.series, self.bo5, self.bo7, self.opp_rating, self.difficulty = z.copy(), z.copy(), z.copy(), z.copy(), z.copy()

    def add(self, a, b, fmt):
        for x, y in ((a, b), (b, a)):
            self.series += np.bincount(x, minlength=N_TEAMS)
            (self.bo5 if fmt == BO5 else self.bo7).__iadd__(np.bincount(x, minlength=N_TEAMS))
            self.opp_rating += np.bincount(x, weights=self.r[y], minlength=N_TEAMS)
            self.difficulty += np.bincount(x, weights=1.0 - self.P[x, y], minlength=N_TEAMS)


class Sim:
    def __init__(self, P5, P7, ratings, n, rng, recorder=None, check=True):
        self.P = {BO5: P5, BO7: P7}
        self.r = np.asarray(ratings, float)
        self.n, self.rng, self.rec, self.check = n, rng, recorder, check

    def play(self, a, b, fmt):
        if self.check and np.any(a == b):
            raise AssertionError("team scheduled against itself")
        win_a = self.rng.random(self.n) < self.P[fmt][a, b]
        if self.rec is not None:
            self.rec.add(a, b, fmt)
        return np.where(win_a, a, b), np.where(win_a, b, a)


# ----------------------------------------------------------------------------------------------- stage 1
def stage1(sim, schedule, tiebreak):
    """schedule: list of (master_idx, elite_idx). Returns dict with ranks per group, wins, game diff, audit."""
    n, rng = sim.n, sim.rng
    wins = np.zeros((n, N_TEAMS), np.int16)
    gd = np.zeros((n, N_TEAMS), np.int16)
    rows = np.arange(n)
    for m, e in schedule:
        a, b = np.full(n, m), np.full(n, e)
        w, l = sim.play(a, b, BO5)
        p = sim.P[BO5][m, e]
        q = bo5_game_prob(np.array([p]))[0]
        gw = np.where(w == m, q, 1 - q)
        c0, c1, c2 = gw ** 3, 3 * gw ** 3 * (1 - gw), 6 * gw ** 3 * (1 - gw) ** 2
        u = rng.random(n) * (c0 + c1 + c2)
        lost_games = (u >= c0).astype(np.int16) + (u >= c0 + c1).astype(np.int16)
        margin = 3 - lost_games
        wins[rows, w] += 1
        gd[rows, w] += margin
        gd[rows, l] -= margin
    out = {"wins": wins, "gd": gd}
    for name, grp in (("master", MASTER), ("elite", ELITE)):
        order, audit = rank_group(wins[:, grp], gd[:, grp], tiebreak, rng, sim.r[grp])
        out[name] = grp[order]
        out[f"{name}_audit"] = audit
    return out


TIEBREAKS = ("T1_WINS_GAMEDIFF_LOT", "T2_WINS_LOT", "T3_WINS_GAMEDIFF_STRENGTH")


def rank_group(wins, gd, tiebreak, rng, ratings):
    """Rank one group (N,k): series wins, then (T1/T3) game differential, then lot (T1/T2) or strength-weighted
    playoff proxy (T3). Returns positional order (N,k) best first and the per-boundary audit."""
    n, k = wins.shape
    W, G = wins.astype(float), gd.astype(float)
    if tiebreak == "T1_WINS_GAMEDIFF_LOT":
        key = W * 100 + G + rng.random((n, k)) * 0.5
    elif tiebreak == "T2_WINS_LOT":
        key = W * 100 + rng.random((n, k)) * 0.5
    elif tiebreak == "T3_WINS_GAMEDIFF_STRENGTH":
        s = np.log(10) * np.asarray(ratings, float) / 400.0
        g = s[None, :] - np.log(-np.log(rng.random((n, k))))
        key = W * 100 + G + 0.5 * sigmoid(g - g.mean(axis=1, keepdims=True))
    else:
        raise ValueError(tiebreak)
    order = np.argsort(-key, axis=1, kind="stable")
    Ws, Gs = np.take_along_axis(W, order, 1), np.take_along_axis(G, order, 1)
    tied = Ws[:, :-1] == Ws[:, 1:]
    by_gd = tied & (Gs[:, :-1] != Gs[:, 1:]) if tiebreak != "T2_WINS_LOT" else np.zeros_like(tied)
    return order, {"tied_on_wins": tied, "resolved_by_game_diff": by_gd, "fallback": tied & ~by_gd}


# ----------------------------------------------------------------------------------------------- breakthrough
def breakthrough(sim, m5, m6, elite_2_5, strategy, pool, rng=None):
    """Sequential opponent selection then three BO7s. elite_2_5: (N,4) team indices in rank order.
    Returns winners (N,3), losers (N,3), pairs (N,3,2) in match order."""
    rng = rng or sim.rng
    n = sim.n
    order = np.column_stack([m5, m6, elite_2_5])          # 顺位 order
    avail = np.ones((n, 6), bool)
    pairs = np.zeros((n, 3, 2), int)
    rows = np.arange(n)
    for k in range(3):
        sel_pos = np.argmax(avail, axis=1)                   # highest remaining 顺位 selects
        avail[rows, sel_pos] = False
        selector = order[rows, sel_pos]
        legal = avail.copy()
        if pool == "ELITE_2_TO_5":
            legal[:, :2] = False                             # Masters can only choose Elite #2-#5
            if k == 2:
                legal = avail.copy()                         # last two automatically play each other
        elif pool != "SELECTION_POOL_ANY":
            raise ValueError(pool)
        opp_r = sim.r[order]
        if strategy == "OPTIMAL_SELECTION":
            score = np.where(legal, opp_r, np.inf); pick = np.argmin(score, axis=1)
        elif strategy == "ADVERSARIAL_SELECTION":
            score = np.where(legal, opp_r, -np.inf); pick = np.argmax(score, axis=1)
        elif strategy == "RANDOM_LEGAL_SELECTION":
            score = np.where(legal, rng.random((n, 6)), -1.0); pick = np.argmax(score, axis=1)
        else:
            raise ValueError(strategy)
        if sim.check and not legal[rows, pick].all():
            raise AssertionError("illegal breakthrough selection")
        avail[rows, pick] = False
        pairs[:, k, 0], pairs[:, k, 1] = selector, order[rows, pick]
    winners, losers = np.zeros((n, 3), int), np.zeros((n, 3), int)
    for k in range(3):
        winners[:, k], losers[:, k] = sim.play(pairs[:, k, 0], pairs[:, k, 1], BO7)
    return winners, losers, pairs


# ----------------------------------------------------------------------------------------------- knockout draw
def _fill(slots, teams, rng):
    """Fill the -1 slots of each row with a random permutation of `teams` (N,k)."""
    n = slots.shape[0]
    if not np.all((slots < 0).sum(axis=1) == teams.shape[1]):
        raise AssertionError("number of free slots does not match number of teams to place")
    free = np.argsort(slots >= 0, axis=1, kind="stable")[:, :teams.shape[1]]
    perm = np.argsort(rng.random(teams.shape), axis=1)
    slots[np.arange(n)[:, None], free] = np.take_along_axis(teams, perm, 1)
    return slots


def draw(rng, seeds, others, bt, scenario):
    """seeds (N,2) = Master #1, #2; others (N,6) = [M3, M4, E1, bt0, bt1, bt2]; bt (N,3) breakthrough winners.
    Returns slots (N,8): QF1=(s0,s1), QF2=(s2,s3), QF3=(s4,s5), QF4=(s6,s7)."""
    n = seeds.shape[0]
    rows = np.arange(n)
    slots = np.full((n, 8), -1)
    if scenario in ("K1_SEEDS_OPPOSITE_HALVES", "K3_SEEDS_OPPOSITE_HALVES_VS_BREAKTHROUGH"):
        flip = rng.random(n) < 0.5
        sa, sb = np.where(flip, seeds[:, 1], seeds[:, 0]), np.where(flip, seeds[:, 0], seeds[:, 1])
        qa, qb = rng.integers(0, 2, n), 2 + rng.integers(0, 2, n)
        slots[rows, 2 * qa], slots[rows, 2 * qb] = sa, sb
        if scenario == "K3_SEEDS_OPPOSITE_HALVES_VS_BREAKTHROUGH":
            perm = np.argsort(rng.random((n, 3)), axis=1)
            b3 = np.take_along_axis(bt, perm, 1)
            slots[rows, 2 * qa + 1], slots[rows, 2 * qb + 1] = b3[:, 0], b3[:, 1]
            rest = np.column_stack([others[:, :3], b3[:, 2]])
            return _fill(slots, rest, rng)
        return _fill(slots, others, rng)
    if scenario == "K2_SEEDS_NOT_PAIRED":
        s1 = rng.integers(0, 8, n)
        partner = s1 ^ 1
        cand = np.argsort(rng.random((n, 8)) + (np.arange(8)[None, :] == s1[:, None]) + (np.arange(8)[None, :] == partner[:, None]), axis=1)[:, 0]
        slots[rows, s1], slots[rows, cand] = seeds[:, 0], seeds[:, 1]
        return _fill(slots, others, rng)
    if scenario == "RANDOM_NO_SEEDS":
        return _fill(slots, np.column_stack([seeds, others]), rng)
    raise ValueError(scenario)


# ----------------------------------------------------------------------------------------------- double elimination
BRACKET = [  # (match, side_a, side_b); sources: ("S", slot) | ("W", match) | ("L", match)
    ("QF1", ("S", 0), ("S", 1)), ("QF2", ("S", 2), ("S", 3)), ("QF3", ("S", 4), ("S", 5)), ("QF4", ("S", 6), ("S", 7)),
    ("LB1A", ("L", "QF1"), ("L", "QF3")), ("LB1B", ("L", "QF2"), ("L", "QF4")),
    ("SF1", ("W", "QF1"), ("W", "QF2")), ("SF2", ("W", "QF3"), ("W", "QF4")),
    ("LB2A", ("W", "LB1A"), ("L", "SF1")), ("LB2B", ("W", "LB1B"), ("L", "SF2")),
    ("UBF", ("W", "SF1"), ("W", "SF2")),
    ("LBSF", ("W", "LB2A"), ("W", "LB2B")),
    ("LBF", ("L", "UBF"), ("W", "LBSF")),
    ("FINAL", ("W", "UBF"), ("W", "LBF")),
]
UPPER = {"QF1", "QF2", "QF3", "QF4", "SF1", "SF2", "UBF"}
ELIMINATING = {"LB1A": "LB_R1", "LB1B": "LB_R1", "LB2A": "LB_R2", "LB2B": "LB_R2", "LBSF": "LB_SF", "LBF": "LB_F",
               "FINAL": "FINAL"}


def double_elimination(slots, play, check=True):
    """Run the 8-team BO7 double-elimination bracket. `play(a, b, fmt)` -> (winner, loser) arrays.
    Returns dict of match -> (a, b, winner, loser) plus 'champion'. Enforces: upper-bracket teams are unbeaten,
    no team plays after its second loss, every team is eliminated exactly once or crowned."""
    n = slots.shape[0]
    rows = np.arange(n)
    losses = np.zeros((n, N_TEAMS), np.int8)
    res = {}
    for m, sa, sb in BRACKET:
        side = []
        for kind, ref in (sa, sb):
            side.append(slots[:, ref] if kind == "S" else res[ref][2 if kind == "W" else 3])
        a, b = side
        if check:
            if np.any(losses[rows, a] >= 2) or np.any(losses[rows, b] >= 2):
                raise AssertionError(f"{m}: eliminated team re-entered the bracket")
            if m in UPPER and (np.any(losses[rows, a] > 0) or np.any(losses[rows, b] > 0)):
                raise AssertionError(f"{m}: team with a loss in the upper bracket")
        w, l = play(a, b, BO7)
        losses[rows, l] += 1
        res[m] = (a, b, w, l)
    res["champion"] = res["FINAL"][2]
    res["losses"] = losses
    if check:
        champ, runner = res["champion"], res["FINAL"][3]
        lz = losses[rows[:, None], slots]
        is_c = slots == champ[:, None]
        is_r = slots == runner[:, None]
        if np.any(losses[rows, champ] > 1):
            raise AssertionError("champion has two losses")
        if np.any((losses[rows, runner] < 1) | (losses[rows, runner] > 2)):
            raise AssertionError("runner-up loss count invalid")
        if np.any(lz[~(is_c | is_r)].reshape(n, 6) != 2):
            raise AssertionError("a non-finalist was not eliminated by exactly its second loss")
    return res


# ----------------------------------------------------------------------------------------------- full tournament
def tournament(sim, schedule, scenario, collect=True):
    """Run all four stages for sim.n simulations. scenario keys: stage1_tiebreak, breakthrough_selection,
    selection_pool, knockout_draw. Returns per-team outcome indicator arrays and audit info."""
    n, rng = sim.n, sim.rng
    rows = np.arange(n)
    s1 = stage1(sim, schedule, scenario["stage1_tiebreak"])
    M, E = s1["master"], s1["elite"]
    direct = np.column_stack([M[:, :4], E[:, :1]])
    bt_teams = np.column_stack([M[:, 4:6], E[:, 1:5]])
    elim1 = E[:, 5]
    bw, bl, pairs = breakthrough(sim, M[:, 4], M[:, 5], E[:, 1:5], scenario["breakthrough_selection"],
                                 scenario["selection_pool"])
    others = np.column_stack([M[:, 2:4], E[:, :1], bw])
    slots = draw(rng, M[:, :2], others, bw, scenario["knockout_draw"])
    if sim.check:
        ko = np.sort(slots, axis=1)
        if np.any(ko[:, 1:] == ko[:, :-1]):
            raise AssertionError("duplicate team in knockout draw")
        if np.any((slots == elim1[:, None]).any(axis=1)) or np.any((slots[:, :, None] == bl[:, None, :]).any(axis=(1, 2))):
            raise AssertionError("eliminated team re-entered the knockout")
    de = double_elimination(slots, sim.play, check=sim.check)
    out = {"stage1": s1, "direct": direct, "bt_teams": bt_teams, "elim1": elim1, "bt_winners": bw, "bt_losers": bl,
           "bt_pairs": pairs, "slots": slots, "de": de, "champion": de["champion"]}
    return out


def team_indicators(out, n):
    """(N,12) boolean indicator matrices for every milestone and the elimination-stage code per team."""
    rows = np.arange(n)
    ind = {}

    def mark(teams):
        x = np.zeros((n, N_TEAMS), bool)
        teams = teams if teams.ndim == 2 else teams[:, None]
        x[rows[:, None], teams] = True
        return x

    de = out["de"]
    ind["direct_knockout"] = mark(out["direct"])
    ind["breakthrough"] = mark(out["bt_teams"])
    ind["stage1_elimination"] = mark(out["elim1"])
    ind["breakthrough_win"] = mark(out["bt_winners"])
    ind["breakthrough_elimination"] = mark(out["bt_losers"])
    ind["knockout"] = mark(out["slots"])
    ind["upper_semifinal"] = mark(np.column_stack([de[m][2] for m in ("QF1", "QF2", "QF3", "QF4")]))
    ind["upper_final"] = mark(np.column_stack([de["SF1"][2], de["SF2"][2]]))
    ind["upper_final_win"] = mark(de["UBF"][2])
    ind["drop_to_lower"] = mark(np.column_stack([de[m][3] for m in ("QF1", "QF2", "QF3", "QF4", "SF1", "SF2", "UBF")]))
    ind["lower_final"] = mark(np.column_stack([de["LBF"][0], de["LBF"][1]]))
    ind["final"] = mark(np.column_stack([de["FINAL"][0], de["FINAL"][1]]))
    ind["champion"] = mark(de["champion"])
    code = np.full((n, N_TEAMS), -1, np.int8)
    code[rows, out["elim1"]] = ELIM_CODES["STAGE1"]
    for k in range(3):
        code[rows, out["bt_losers"][:, k]] = ELIM_CODES["BREAKTHROUGH"]
    for m, stage in ELIMINATING.items():
        code[rows, de[m][3]] = ELIM_CODES[stage]
    code[rows, de["champion"]] = ELIM_CODES["CHAMPION"]
    ind["elimination_code"] = code
    return ind


# ----------------------------------------------------------------------------------------------- neutral format
def neutral_tournament(sim):
    """NEUTRAL_FORMAT: 12-team single round robin BO5 -> top 8 by wins, game diff, lot -> random-draw
    double elimination (BO7)."""
    n, rng = sim.n, sim.rng
    pairs = [(i, j) for i in range(N_TEAMS) for j in range(i + 1, N_TEAMS)]
    wins = np.zeros((n, N_TEAMS), np.int16)
    gd = np.zeros((n, N_TEAMS), np.int16)
    rows = np.arange(n)
    for i, j in pairs:
        w, l = sim.play(np.full(n, i), np.full(n, j), BO5)
        q = bo5_game_prob(np.array([sim.P[BO5][i, j]]))[0]
        gw = np.where(w == i, q, 1 - q)
        c0, c1, c2 = gw ** 3, 3 * gw ** 3 * (1 - gw), 6 * gw ** 3 * (1 - gw) ** 2
        u = rng.random(n) * (c0 + c1 + c2)
        margin = 3 - ((u >= c0).astype(np.int16) + (u >= c0 + c1).astype(np.int16))
        wins[rows, w] += 1
        gd[rows, w] += margin
        gd[rows, l] -= margin
    key = wins * 100.0 + gd + rng.random((n, N_TEAMS)) * 0.5
    top8 = np.argsort(-key, axis=1, kind="stable")[:, :8]
    slots = draw(rng, top8[:, :2], top8[:, 2:], None, "RANDOM_NO_SEEDS")
    de = double_elimination(slots, sim.play, check=sim.check)
    return {"slots": slots, "de": de, "champion": de["champion"]}
