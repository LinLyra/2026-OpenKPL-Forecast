"""B4: recency-aware Elo via inactivity regression to the mean.

Each team stores its post-update rating R and the time t_last of its last
completed series. Before a series at time t (the scheduled time, known before
play) the pre-match rating is

    R_pre(t) = R0 + (R - R0) * 2 ** (-(t - t_last) / h)

with half-life h in days (h = inf recovers plain Elo). The update is the usual
Elo step applied to R_pre, after which t_last = t. Information fades with
inactivity; no match is weighted by anything known only after it is played.
"""
import math

from openkpl.modeling.temporal.elo import Elo


class DecayElo(Elo):
    model_id = "B4"

    def __init__(self, k=24.0, scale=400.0, r0=1500.0, half_life_days=math.inf):
        super().__init__(k=k, scale=scale, r0=r0)
        self.params["half_life_days"] = half_life_days

    def reset(self):
        self.r, self.last = {}, {}

    def rating(self, team, t):
        r0, h = self.params["r0"], self.params["half_life_days"]
        if team not in self.r:
            return r0
        if math.isinf(h):
            return self.r[team]
        return r0 + (self.r[team] - r0) * 2.0 ** (-(t - self.last[team]) / h)

    def _store(self, team, value, t):
        self.r[team] = value
        self.last[team] = t
