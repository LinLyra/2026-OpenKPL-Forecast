"""B1: expanding smoothed historical win rate.

Team strength is the Beta-Binomial posterior mean of its series win rate over
all previously completed series (no season boundaries):

    s_i = (w_i + alpha) / (n_i + alpha + beta),   default alpha = beta = 5

i.e. a prior mean of 0.5 worth 10 pseudo-series, fixed a priori (not tuned). A
team with no history has s = 0.5, so no probability is ever 0 or 1. The two
strengths are combined with the log5 rule:

    P(A) = s_A (1 - s_B) / (s_A (1 - s_B) + s_B (1 - s_A))
"""
from openkpl.modeling.temporal.base import TemporalModel


class SmoothedWinRate(TemporalModel):
    model_id = "B1"

    def __init__(self, alpha=5.0, beta=5.0):
        super().__init__(alpha=alpha, beta=beta)

    def reset(self):
        self.w, self.n = {}, {}

    def strength(self, team):
        a, b = self.params["alpha"], self.params["beta"]
        return (self.w.get(team, 0.0) + a) / (self.n.get(team, 0.0) + a + b)

    def predict(self, a, b, t):
        sa, sb = self.strength(a), self.strength(b)
        num = sa * (1 - sb)
        return num / (num + sb * (1 - sa)), sa, sb

    def update_batch(self, records):
        for a, b, y, *_ in records:
            self.n[a] = self.n.get(a, 0.0) + 1; self.n[b] = self.n.get(b, 0.0) + 1
            self.w[a] = self.w.get(a, 0.0) + y; self.w[b] = self.w.get(b, 0.0) + (1 - y)
