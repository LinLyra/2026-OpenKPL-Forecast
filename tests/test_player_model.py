import copy
import unittest
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.evaluation.benchmark import PROSPECTIVE_HOLDOUT_START
from openkpl.player_model import data, experiment as E, features as F, lock, models as M
from openkpl.player_model.ratings import PlayerElo
from openkpl.roster import baseline

ROOT = Path(__file__).resolve().parents[1]
A = [f"a{i}" for i in range(7)]
B = [f"b{i}" for i in range(7)]


def _series(sid, day, a_lineups, b_lineups, winners, season="S1"):
    games = []
    for n, (la, lb, w) in enumerate(zip(a_lineups, b_lineups, winners), start=1):
        heroes = [(p, "TA", i + 1, w == "TA") for i, p in enumerate(la)] + \
                 [(p, "TB", i + 11, w == "TB") for i, p in enumerate(lb)]
        games.append({"game_number": n, "winner": w, "lineup": {"TA": frozenset(la), "TB": frozenset(lb)},
                      "heroes": heroes})
    played = {"TA": Counter(p for la in a_lineups for p in la), "TB": Counter(p for lb in b_lineups for p in lb)}
    y = int(sum(w == "TA" for w in winners) > len(winners) / 2)
    return {"series_id": sid, "t": pd.Timestamp("2024-01-01") + pd.Timedelta(days=day), "season": season,
            "stage": "x", "a": "TA", "b": "TB", "y": y, "games": games, "played": played, "has_lineup": True}


def _timeline():
    core_a, core_b = A[:5], B[:5]
    return [
        _series("S1", 0, [core_a] * 3, [core_b] * 3, ["TA", "TB", "TA"]),
        _series("S2", 2, [core_a, A[1:6], core_a], [core_b] * 3, ["TA", "TA", "TB"]),
        _series("S3", 4, [core_a] * 3, [core_b, B[1:6], B[1:6]], ["TB", "TA", "TA"]),
        _series("S4", 6, [core_a] * 2, [core_b] * 2, ["TA", "TA"]),
    ]


def _features(tl, cfg=("P2", "game", 16.0, 10.0)):
    rk, st, _ = F.history_pass(tl)
    out, orc = F.rating_pass(tl, rk, PlayerElo(*cfg))
    safe = {sid: {**out["DECAY"][sid], **st[(sid, "DECAY")]} for sid in out["DECAY"]}
    return safe, orc


def _equal(d1, d2):
    for k in d1:
        a, b = d1[k], d2[k]
        if not ((isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b)) or a == b):
            return False
    return True


class PreSeriesLeakageTest(unittest.TestCase):
    def test_target_series_lineup_excluded_from_safe_features(self):
        tl = _timeline()
        base, orc = _features(tl)
        tl2 = copy.deepcopy(tl)
        tl2[2] = _series("S3", 4, [A[2:7]] * 3, [B[2:7]] * 3, ["TB", "TA", "TA"])
        changed, orc2 = _features(tl2)
        self.assertTrue(_equal(base["S3"], changed["S3"]))
        self.assertNotEqual(orc["S3"]["oracle_players_a"], orc2["S3"]["oracle_players_a"])

    def test_future_appearances_cannot_alter_past_features(self):
        tl = _timeline()
        base, _ = _features(tl)
        extra = _series("S5", 8, [A[2:7]] * 3, [B[2:7]] * 3, ["TB", "TB", "TA"])
        more, _ = _features(tl + [extra])
        for sid in ["S1", "S2", "S3", "S4"]:
            self.assertTrue(_equal(base[sid], more[sid]), sid)

    def test_future_results_cannot_alter_player_ratings(self):
        tl = _timeline()
        base, _ = _features(tl)
        tl2 = copy.deepcopy(tl)
        tl2[3] = _series("S4", 6, [A[:5]] * 2, [B[:5]] * 2, ["TB", "TB"])
        flipped, _ = _features(tl2)
        for sid in ["S1", "S2", "S3", "S4"]:
            self.assertTrue(_equal(base[sid], flipped[sid]), sid)
        for mode in ("game", "series"):
            e1, e2 = PlayerElo("P2", mode), PlayerElo("P2", mode)
            for s in tl[:3]:
                e1.update_series(s)
                e2.update_series(s)
            self.assertEqual({p: e1.eff(p) for p in A + B}, {p: e2.eff(p) for p in A + B})

    def test_same_series_later_games_cannot_alter_preseries_feature(self):
        tl = _timeline()
        base, _ = _features(tl)
        tl2 = copy.deepcopy(tl)
        tl2[1] = _series("S2", 2, [A[:5], A[1:6], A[2:7]], [B[:5]] * 3, ["TA", "TB", "TB"])
        changed, _ = _features(tl2)
        self.assertTrue(_equal(base["S2"], changed["S2"]))
        self.assertTrue(_equal(base["S1"], changed["S1"]))

    def test_ratings_start_at_common_prior_and_shrink(self):
        e = PlayerElo("P2", "game", k=32, m=10)
        self.assertEqual(e.eff("new"), 1500.0)
        e.update_series(_timeline()[0])
        raw = e.R["a0"] - 1500
        self.assertAlmostEqual(e.eff("a0") - 1500, raw * e.n["a0"] / (e.n["a0"] + 10))


class TrainingOnlyTransformsTest(unittest.TestCase):
    def test_imputer_and_clipper_fit_on_training_rows_only(self):
        rng = np.random.default_rng(0)
        tr = pd.DataFrame({"logit_b5": rng.normal(size=200), "x_diff": rng.normal(size=200), "y": rng.integers(0, 2, 200)})
        tr.loc[:20, "x_diff"] = np.nan
        te = pd.DataFrame({"logit_b5": rng.normal(size=50), "x_diff": rng.normal(loc=100, size=50), "y": 0})
        model, _ = M.fit_predict(lambda: M.logistic(1.0), tr, te, ["logit_b5", "x_diff"])
        imp, clip = model.steps[0][1], model.steps[1][1]
        self.assertAlmostEqual(imp.statistics_[1], float(np.nanmedian(tr.x_diff)))
        self.assertLess(clip.hi_[1], 10)
        te2 = te.copy()
        te2["x_diff"] = 1e6
        m2, _ = M.fit_predict(lambda: M.logistic(1.0), tr, te2, ["logit_b5", "x_diff"])
        np.testing.assert_allclose(m2.steps[0][1].statistics_, imp.statistics_)

    def test_calibration_uses_only_prior_season_predictions(self):
        rng = np.random.default_rng(1)
        rows = []
        for s in ["V1", "V2", "V3"]:
            p = rng.uniform(0.2, 0.8, 300)
            rows.append(pd.DataFrame({"series_id": [f"{s}_{i}" for i in range(300)], "season": s, "model_id": "M",
                                      "p": p, "y": (rng.uniform(size=300) < p).astype(int)}))
        preds = pd.concat(rows, ignore_index=True)
        cal = E.calibrate(preds, ["V1", "V2", "V3"])
        self.assertTrue(cal[cal.season == "V1"].p_platt.isna().all())
        preds2 = preds.copy()
        preds2.loc[preds2.season == "V3", "y"] = 1 - preds2.loc[preds2.season == "V3", "y"]
        cal2 = E.calibrate(preds2, ["V1", "V2", "V3"])
        for s in ["V1", "V2", "V3"]:
            np.testing.assert_allclose(cal[cal.season == s].p_platt.fillna(-1), cal2[cal2.season == s].p_platt.fillna(-1))
        preds3 = preds.copy()
        preds3.loc[preds3.season == "V1", "y"] = 1 - preds3.loc[preds3.season == "V1", "y"]
        cal3 = E.calibrate(preds3, ["V1", "V2", "V3"])
        self.assertFalse(np.allclose(cal[cal.season == "V2"].p_platt, cal3[cal3.season == "V2"].p_platt))


class UniverseAndOracleTest(unittest.TestCase):
    def test_annual_finals_results_absent(self):
        c = pd.read_parquet(ROOT / data.CANONICAL)
        dev = data.dev_universe(c)
        self.assertFalse((dev.season == data.ANNUAL_FINALS_2026).any())
        self.assertTrue((dev.start_time < PROSPECTIVE_HOLDOUT_START).all())
        fake = c.head(1).copy()
        fake["season"], fake["start_time"] = data.ANNUAL_FINALS_2026, "2026-10-01 18:00:00"
        fake["series_id"] = "FAKE_AF"
        dev2 = data.dev_universe(pd.concat([c, fake], ignore_index=True))
        self.assertNotIn("FAKE_AF", set(dev2.series_id))
        p = ROOT / "data/processed/modeling/player_roster_predictions.parquet"
        if p.exists():
            preds = pd.read_parquet(p)
            self.assertFalse(preds.season.eq(data.ANNUAL_FINALS_2026).any())
            self.assertTrue(set(preds.series_id) <= set(dev.series_id))

    def test_oracle_features_never_enter_deployable_models(self):
        for groups in list(M.LADDER.values()) + [M.ALL_SAFE]:
            self.assertFalse([c for c in M.columns(groups) if c.startswith("oracle_")])
        for cols in (M.EXPLORATORY_X1, M.EXPLORATORY_X2):
            M.assert_deployable(cols)
        with self.assertRaises(ValueError):
            M.assert_deployable(["logit_b5", "oracle_actual_lineup_rating_mean_diff"])
        f = ROOT / "data/processed/modeling/player_roster_features.parquet"
        if f.exists():
            self.assertFalse([c for c in pd.read_parquet(f).columns if c.startswith("oracle_")])

    def test_models_share_identical_evaluation_rows(self):
        p = ROOT / "data/processed/modeling/player_roster_predictions.parquet"
        if not p.exists():
            self.skipTest("v0.5 run not executed")
        preds = pd.read_parquet(p)
        ids = {m: frozenset(g.series_id) for m, g in preds.groupby("model_id")}
        self.assertEqual(len(set(ids.values())), 1)


class ImmutabilityTest(unittest.TestCase):
    def test_v03_benchmark_artifacts_unchanged(self):
        self.assertEqual(lock.check(ROOT), [])

    def test_phase_b_data_unchanged(self):
        import json
        lk = json.loads((ROOT / "reports/roster_collection/phase_b_lock.json").read_text())
        self.assertEqual(baseline.check_lock(lk, ROOT), [])


if __name__ == "__main__":
    unittest.main()
