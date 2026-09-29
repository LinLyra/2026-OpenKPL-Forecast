"""Sequential player ratings.

Every player starts at BASE = 1500 with n = 0 rated events. The rating used for
prediction shrinks toward the league mean until the player has history:

    eff(i) = BASE + (R_i - BASE) * n_i / (n_i + m)          (m = 0: no shrinkage)

Team strength for a lineup L is S(L) = mean_{i in L} eff(i).

P1 (win Elo, not opponent-adjusted): each side is scored against a league-average
opponent,
    E_A = 1 / (1 + 10^((BASE - S_A) / scale)),  E_B = 1 / (1 + 10^((BASE - S_B) / scale))
P2 (opponent-adjusted):
    E_A = 1 / (1 + 10^((S_B - S_A) / scale)),   E_B = 1 - E_A
Update for every i in L_A: R_i += K (y_A - E_A), n_i += 1 (same for B with y_B = 1 - y_A).

mode "game": one update per game with a known winner and both lineups, in game
order. mode "series": one update per series using the series label, with L = the
players who appeared for the team in at least one game of the series.
Updates happen only after the series is complete, so a pre-series snapshot never
contains the target series or anything later.
"""
BASE = 1500.0
SCALE = 400.0


class PlayerElo:
    def __init__(self, variant="P2", mode="game", k=16.0, m=10.0, scale=SCALE):
        if variant not in ("P1", "P2") or mode not in ("game", "series"):
            raise ValueError("bad rating configuration")
        self.variant, self.mode, self.k, self.m, self.scale = variant, mode, float(k), float(m), scale
        self.R, self.n = {}, {}

    def eff(self, p):
        r, n = self.R.get(p, BASE), self.n.get(p, 0)
        if self.m == 0:
            return r
        return BASE + (r - BASE) * n / (n + self.m)

    def strength(self, players):
        players = list(players)
        return sum(self.eff(p) for p in players) / len(players) if players else BASE

    def _expect(self, sa, sb):
        if self.variant == "P2":
            ea = 1.0 / (1.0 + 10 ** ((sb - sa) / self.scale))
            return ea, 1.0 - ea
        return (1.0 / (1.0 + 10 ** ((BASE - sa) / self.scale)), 1.0 / (1.0 + 10 ** ((BASE - sb) / self.scale)))

    def _update(self, la, lb, ya):
        sa, sb = self.strength(la), self.strength(lb)
        ea, eb = self._expect(sa, sb)
        for ps, y, e in ((la, ya, ea), (lb, 1 - ya, eb)):
            for p in ps:
                self.R[p] = self.R.get(p, BASE) + self.k * (y - e)
                self.n[p] = self.n.get(p, 0) + 1

    def update_series(self, s):
        a, b = s["a"], s["b"]
        if self.mode == "game":
            for g in s["games"]:
                la, lb = g["lineup"].get(a), g["lineup"].get(b)
                if g["winner"] in (a, b) and la and lb:
                    self._update(la, lb, 1 if g["winner"] == a else 0)
        else:
            la, lb = s["played"][a], s["played"][b]
            if la and lb:
                self._update(list(la), list(lb), s["y"])

    def config_id(self):
        return f"{self.variant}|{self.mode}|k={self.k:g}|m={self.m:g}"
