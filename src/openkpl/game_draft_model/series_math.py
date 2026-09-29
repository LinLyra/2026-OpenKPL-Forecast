"""Exact best-of-(2n-1) series probabilities.

Constant, independent game probability p:
    P(series) = sum_{k=n}^{2n-1} C(2n-1, k) p^k (1-p)^(2n-1-k)
(identical to playing the series out and stopping at n wins).
State-dependent game probabilities are handled by exact recursion over the
series score (and previous-game winner).
"""
from functools import lru_cache
from math import comb

import numpy as np

WINS_NEEDED = {"BO3": 2, "BO5": 3, "BO7": 4}


def series_prob(p, fmt):
    n = WINS_NEEDED[fmt]
    m = 2 * n - 1
    p = np.asarray(p, float)
    return sum(comb(m, k) * p ** k * (1 - p) ** (m - k) for k in range(n, m + 1))


def bo3(p):
    return series_prob(p, "BO3")


def bo5(p):
    return series_prob(p, "BO5")


def bo7(p):
    return series_prob(p, "BO7")


def game_prob_from_series(ps, fmt, tol=1e-12):
    """Inverse of series_prob (monotone in p) by bisection; vectorized."""
    ps = np.asarray(ps, float)
    lo, hi = np.zeros_like(ps), np.ones_like(ps)
    for _ in range(80):
        mid = (lo + hi) / 2
        up = series_prob(mid, fmt) < ps
        lo, hi = np.where(up, mid, lo), np.where(up, hi, mid)
        if np.max(hi - lo) < tol:
            break
    return (lo + hi) / 2


def series_prob_state(game_p, fmt):
    """game_p(game_number, wins_a, wins_b, prev) -> P(team_a wins that game); prev in {+1, -1, 0}."""
    n = WINS_NEEDED[fmt]

    @lru_cache(maxsize=None)
    def win(wa, wb, prev):
        if wa == n:
            return 1.0
        if wb == n:
            return 0.0
        p = game_p(wa + wb + 1, wa, wb, prev)
        return p * win(wa + 1, wb, 1) + (1 - p) * win(wa, wb + 1, -1)

    return win(0, 0, 0)
