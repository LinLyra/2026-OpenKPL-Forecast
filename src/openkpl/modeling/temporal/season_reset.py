"""B5: season-reset Elo.

At the first timestamp batch of a new season label (chronological order),
every existing rating is shrunk toward the mean before any prediction:

    R_new = R0 + rho * (R_old - R0),   0 <= rho <= 1

rho = 1 keeps ratings (plain Elo); rho = 0 resets everyone to R0. Every season
label change counts as a transition, including regular season -> annual finals.
"""
from openkpl.modeling.temporal.elo import Elo


class SeasonResetElo(Elo):
    model_id = "B5"

    def __init__(self, k=24.0, scale=400.0, r0=1500.0, rho=1.0):
        if not 0.0 <= rho <= 1.0:
            raise ValueError("rho must be in [0, 1]")
        super().__init__(k=k, scale=scale, r0=r0)
        self.params["rho"] = rho

    def reset(self):
        self.r = {}
        self.season = None

    def start_batch(self, t, season):
        if self.season is not None and season != self.season:
            r0, rho = self.params["r0"], self.params["rho"]
            self.r = {team: r0 + rho * (v - r0) for team, v in self.r.items()}
        self.season = season
