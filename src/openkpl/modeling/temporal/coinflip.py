"""B0: unconditional coin flip, P(team_a wins) = 0.5 for every series."""
import math

from openkpl.modeling.temporal.base import TemporalModel


class CoinFlip(TemporalModel):
    model_id = "B0"

    def predict(self, a, b, t):
        return 0.5, math.nan, math.nan

    def update_batch(self, records):
        pass
