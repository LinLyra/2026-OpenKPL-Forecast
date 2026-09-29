import copy
import itertools
import math
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.evaluation.benchmark import PROSPECTIVE_HOLDOUT_START
from openkpl.game_draft_model import draft as D
from openkpl.game_draft_model import elo as E
from openkpl.game_draft_model import experiment_a as A
from openkpl.game_draft_model import games as GM
from openkpl.game_draft_model import lock
from openkpl.game_draft_model.series_math import (bo3, bo5, bo7, game_prob_from_series, series_prob,
                                                  series_prob_state)
from openkpl.player_model import data

ROOT = Path(__file__).resolve().parents[1]


def _series(sid, day, winners, a="TA", b="TB", season="S1"):
    return {"series_id": sid, "t": pd.Timestamp("2024-01-01") + pd.Timedelta(days=day), "season": season,
            "stage": "x", "a": a, "b": b, "y": int(winners.count("a") > winners.count("b")), "format": "BO5",
            "format_source": "stage", "p_b5": 0.5,
            "games": [{"game_key": f"{sid}#G{i + 1}", "game_number": i + 1, "winner_side": w, "winner_source": "kplow"}
                      for i, w in enumerate(winners)]}


def _timeline():
    return [_series("S1", 0, list("aab" + "a")), _series("S2", 3, list("bab" + "b")),
            _series("S3", 6, list("aaa")), _series("S4", 9, list("babab"))]


PARAMS = [{"k": 32.0}, {"k": 32.0, "half_life_days": 5.0}, {"k": 32.0, "rho": 0.5}, {"k": 32.0, "series_aware": True}]


class GameEloLeakageTest(unittest.TestCase):
    def test_future_games_cannot_affect_past_predictions(self):
        for p in PARAMS:
            g1, _ = E.run(_timeline()[:3], p)
            g2, _ = E.run(_timeline(), p)
            pd.testing.assert_frame_equal(g1, g2.iloc[:len(g1)].reset_index(drop=True))

    def test_current_game_result_not_in_its_own_features(self):
        for p in PARAMS:
            base, _ = E.run(_timeline(), p)
            tl = _timeline()
            tl[1]["games"][2]["winner_side"] = "a"
            flip, _ = E.run(tl, p)
            row = lambda g: g[g.game_key == "S2#G3"][["p_pre", "p_live"]].to_numpy()  # noqa: E731
            np.testing.assert_allclose(row(base), row(flip))

    def test_later_series_games_cannot_enter_pre_series_mode(self):
        for p in PARAMS:
            base, _ = E.run(_timeline(), p)
            tl = _timeline()
            tl[1]["games"][1]["winner_side"] = "b"
            tl[1]["games"][3]["winner_side"] = "a"
            chg, _ = E.run(tl, p)
            b, c = base[base.series_id == "S2"], chg[chg.series_id == "S2"]
            np.testing.assert_allclose(b.p_pre, c.p_pre)
            self.assertEqual(b.p_pre.nunique(), 1)

    def test_live_series_mode_only_sees_earlier_games(self):
        p = {"k": 32.0}
        base, _ = E.run(_timeline(), p)
        tl = _timeline()
        tl[3]["games"][2]["winner_side"] = "a"
        chg, _ = E.run(tl, p)
        for k in (1, 2, 3):
            key = f"S4#G{k}"
            self.assertAlmostEqual(base.set_index("game_key").p_live[key], chg.set_index("game_key").p_live[key])
        self.assertNotAlmostEqual(base.set_index("game_key").p_live["S4#G4"], chg.set_index("game_key").p_live["S4#G4"])
        g1 = base[base.game_key == "S4#G1"].iloc[0]
        self.assertAlmostEqual(g1.p_live, g1.p_pre)


class SeriesMathTest(unittest.TestCase):
    def test_exact_values(self):
        self.assertAlmostEqual(float(bo3(0.6)), 0.648)
        self.assertAlmostEqual(float(bo5(0.6)), 0.68256)
        self.assertAlmostEqual(float(bo7(0.6)), 0.7102080)
        for f in (bo3, bo5, bo7):
            self.assertAlmostEqual(float(f(0.5)), 0.5)
            self.assertAlmostEqual(float(f(0.3) + f(0.7)), 1.0)

    def test_matches_brute_force_enumeration(self):
        for fmt, n in (("BO3", 2), ("BO5", 3), ("BO7", 4)):
            for p in (0.2, 0.55, 0.9):
                tot = 0.0
                for seq in itertools.product((0, 1), repeat=2 * n - 1):
                    a = b = 0
                    for x in seq:
                        a, b = a + x, b + (1 - x)
                        if a == n or b == n:
                            break
                    if a == n:
                        tot += p ** sum(seq) * (1 - p) ** (len(seq) - sum(seq))
                self.assertAlmostEqual(float(series_prob(p, fmt)), tot)
                self.assertAlmostEqual(series_prob_state(lambda *_: p, fmt), float(series_prob(p, fmt)))

    def test_inverse(self):
        for fmt in ("BO3", "BO5", "BO7"):
            p = np.array([0.1, 0.45, 0.8])
            np.testing.assert_allclose(game_prob_from_series(series_prob(p, fmt), fmt), p, atol=1e-9)


class DraftLeakageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hf, cls.sf, cls.cf, cls.ev = D.load(ROOT)
        keys = cls.hf.drop_duplicates("game_key").sort_values("temporal_rank").game_key.iloc[200:230].tolist()
        cls.keys = keys
        teams = cls.hf[cls.hf.game_key.isin(keys)].groupby("game_key").team_id.unique()
        cls.gt = pd.DataFrame({"game_key": keys, "team_a": [teams[k][0] for k in keys],
                               "team_b": [teams[k][1] for k in keys],
                               "date": pd.Timestamp("2023-01-01")}).set_index("game_key", drop=False)

    def test_static_features_exclude_current_game_outcome(self):
        base = D.static_features(self.gt, self.hf, self.sf, self.cf, 10.0, 0)
        hf2 = self.hf.copy()
        m = hf2.game_key == self.keys[5]
        hf2.loc[m, "won_current_game_label"] = hf2.loc[m, "won_current_game_label"].map(
            lambda x: None if x is None else (not x))
        pd.testing.assert_frame_equal(base, D.static_features(self.gt, hf2, self.sf, self.cf, 10.0, 0))

    def test_recency_feature_uses_only_earlier_games(self):
        hf = self.hf[self.hf.game_key.isin(self.keys)]
        base = D.recency_hero_strength(self.gt, hf, 10.0, 0, 180.0)
        hf2 = hf.copy()
        target = self.keys[10]
        m = hf2.game_key == target
        hf2.loc[m, "won_current_game_label"] = hf2.loc[m, "won_current_game_label"].map(
            lambda x: None if x is None else (not x))
        chg = D.recency_hero_strength(self.gt, hf2, 10.0, 0, 180.0)
        np.testing.assert_allclose(base.loc[self.keys[:11]], chg.loc[self.keys[:11]])

    def test_sequential_step_cannot_see_later_steps(self):
        g = self.keys[3]
        evs = sorted(self.ev[self.ev.game_key == g].to_dict("records"), key=lambda e: e["sequence"])
        lk = D.StepLookup(self.hf, self.sf, self.cf, 10.0, 0)
        a, b = self.gt.loc[g, "team_a"], self.gt.loc[g, "team_b"]
        for j in range(18):
            alt = copy.deepcopy(evs)
            for e in alt[j:]:
                e["hero_name"] = "UNSEEN_HERO"
                e["ban_or_pick"] = "pick"
            self.assertEqual(D.step_features(g, evs, j, a, b, lk), D.step_features(g, alt, j, a, b, lk))

    def test_wzry_winner_is_not_a_predictor(self):
        with self.assertRaises(ValueError):
            D.cols(["D1"], pre="winner_wzry")
        for groups in (D.LADDER["D4"], D.ALL_STATIC):
            self.assertFalse([c for c in D.cols(groups) if "wzry" in c or "winner" in c])
        idg = pd.read_parquet(ROOT / GM.IDENTIFIED)
        canonical, games, _ = data.load(ROOT)
        tl = GM.build(canonical, games, pd.read_parquet(ROOT / data.BENCH_PRED))
        gt1 = D.game_table(idg, tl)
        idg2 = idg.assign(winner_wzry="TEAM_NOBODY")
        gt2 = D.game_table(idg2, tl)
        pd.testing.assert_series_equal(gt1.y, gt2.y)


class BootstrapAndUniverseTest(unittest.TestCase):
    def test_bootstrap_clusters_games_by_series(self):
        rng = np.random.default_rng(0)
        rows = []
        for s in range(40):
            p1, p2, y = rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.7), int(rng.integers(0, 2))
            for gnum in range(3):
                rows += [{"game_key": f"s{s}g{gnum}", "series_id": f"s{s}", "season": "V", "model_id": "R", "p": p1, "y": y},
                         {"game_key": f"s{s}g{gnum}", "series_id": f"s{s}", "season": "V", "model_id": "M", "p": p2, "y": y}]
        df = pd.DataFrame(rows)
        r3 = A.cluster_bootstrap(df, "R", ["M"], "game_key", b=500).iloc[0]
        one = df[df.game_key.str.endswith("g0")]
        r1 = A.cluster_bootstrap(one, "R", ["M"], "game_key", b=500).iloc[0]
        self.assertEqual(r3.n_clusters, 40)
        self.assertAlmostEqual(r3.delta_log_loss_ci_low, r1.delta_log_loss_ci_low)
        self.assertAlmostEqual(r3.delta_log_loss_ci_high, r1.delta_log_loss_ci_high)

    def test_annual_finals_outcomes_absent(self):
        canonical, games, _ = data.load(ROOT)
        tl = GM.build(canonical, games, pd.read_parquet(ROOT / data.BENCH_PRED))
        self.assertFalse(any(s["season"] == data.ANNUAL_FINALS_2026 for s in tl))
        self.assertTrue(all(s["t"] < PROSPECTIVE_HOLDOUT_START for s in tl))
        for f in ("game_strength_predictions", "series_strength_predictions_v06", "draft_predictions"):
            p = ROOT / f"data/processed/modeling/{f}.parquet"
            if p.exists():
                self.assertFalse(pd.read_parquet(p).season.eq(data.ANNUAL_FINALS_2026).any())

    def test_series_format_from_stage(self):
        self.assertEqual(GM.series_format("季后赛", 4, 2)[0], "BO7")
        self.assertEqual(GM.series_format("常规赛第一轮", 3, 1)[0], "BO5")
        self.assertEqual(GM.series_format("", 4, 3), ("BO7", "final_score (stage blank)"))


class ImmutabilityTest(unittest.TestCase):
    def test_all_prior_locked_artifacts_unchanged(self):
        self.assertEqual(lock.check(ROOT), [])


if __name__ == "__main__":
    unittest.main()
