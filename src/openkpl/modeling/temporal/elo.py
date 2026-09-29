"""B2/B3: canonical series-level Elo.

    P(A) = 1 / (1 + 10 ** ((R_B - R_A) / scale)),   new teams start at R0 = 1500
    R_A <- R_A + K (y - P(A)),   R_B <- R_B - K (y - P(A))

Score margin is not used. Predictions depend on K and scale only through
K / scale (scaling R - R0, K and scale by one constant leaves every probability
unchanged), so tuning both is partly redundant; ties are broken explicitly in
the tuner.
"""
from openkpl.modeling.temporal.base import R0, TemporalModel


class Elo(TemporalModel):
    model_id = "B2"

    def __init__(self, k=24.0, scale=400.0, r0=R0):
        super().__init__(k=k, scale=scale, r0=r0)

    def reset(self):
        self.r = {}

    def rating(self, team, t):
        return self.r.get(team, self.params["r0"])

    def expected(self, ra, rb):
        return 1.0 / (1.0 + 10.0 ** ((rb - ra) / self.params["scale"]))

    def predict(self, a, b, t):
        ra, rb = self.rating(a, t), self.rating(b, t)
        return self.expected(ra, rb), ra, rb

    def _store(self, team, value, t):
        self.r[team] = value

    def update_batch(self, records):
        k = self.params["k"]
        new = {}
        for a, b, y, p, t, ra, rb in records:
            d = k * (y - p)
            new[a] = (new.get(a, (ra, t))[0] + d, t)
            new[b] = (new.get(b, (rb, t))[0] - d, t)
        for team, (v, t) in new.items():
            self._store(team, v, t)


class SlotInheritanceElo(Elo):
    """E_SLOT (optional experiment, not part of B0-B5).

    A team with a reviewed predecessor league slot starts at
        R_new = R0 + lambda_slot * (R_predecessor - R0)
    instead of R0. Identity is unchanged: the team keeps its own canonical ID.
    """
    model_id = "E_SLOT"

    def __init__(self, k=24.0, scale=400.0, r0=R0, lambda_slot=0.0, predecessors=None):
        TemporalModel.__init__(self, k=k, scale=scale, r0=r0, lambda_slot=lambda_slot)
        self.predecessors = dict(predecessors or {})

    def rating(self, team, t):
        if team not in self.r and team in self.predecessors:
            pred = self.predecessors[team]
            r0 = self.params["r0"]
            return r0 + self.params["lambda_slot"] * (self.r.get(pred, r0) - r0)
        return super().rating(team, t)
