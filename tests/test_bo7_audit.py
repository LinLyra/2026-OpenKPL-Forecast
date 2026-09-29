import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.bo7_audit import audit as AU
from openkpl.bo7_audit import lock
from openkpl.bo7_audit import run as R
from openkpl.evaluation.benchmark import PROSPECTIVE_HOLDOUT_START
from openkpl.player_model import data
from openkpl.roster import baseline

ROOT = Path(__file__).resolve().parents[1]


def _synthetic(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i, season in enumerate(["S1", "S2", "S3", "S4"]):
        for fmt, n in (("BO7", 12), ("BO5", 30)):
            p = rng.uniform(0.2, 0.8, n)
            y = (rng.uniform(size=n) < AU.sigmoid(1.8 * AU.logit(p))).astype(int)
            for j in range(n):
                rows.append({"series_id": f"{season}-{fmt}-{j}", "t": pd.Timestamp("2024-01-01") + pd.Timedelta(days=100 * i + j),
                             "season": season, "format": fmt, "y": int(y[j]), "p": float(p[j])})
    d = pd.DataFrame(rows)
    d["z"] = AU.logit(d.p)
    return d


class TemporalIsolationTest(unittest.TestCase):
    def test_validation_season_never_enters_calibration_fit(self):
        d = _synthetic()
        base, stab = AU.run_format(d, "BO7")
        for season in ("S2", "S3"):
            d2 = d.copy()
            m = (d2.season == season) & (d2.format == "BO7")
            d2.loc[m, "y"] = 1 - d2.loc[m, "y"]
            chg, stab2 = AU.run_format(d2, "BO7")
            keep = lambda x: x[(x.season == season) | (x.season < season)].drop(columns="y")  # noqa: E731
            pd.testing.assert_frame_equal(keep(base).reset_index(drop=True), keep(chg).reset_index(drop=True))
            cols = ["beta_raw", "beta_C2", "beta_C3", "beta_C4", "selected", "beta_shrunk"]
            pd.testing.assert_frame_equal(stab[stab.validation_season <= season][cols].reset_index(drop=True),
                                          stab2[stab2.validation_season <= season][cols].reset_index(drop=True))

    def test_training_rows_strictly_earlier(self):
        d = _synthetic()
        _, stab = AU.run_format(d, "BO7")
        s = stab[stab.model_family == "PRIMARY_zero_intercept"]
        self.assertEqual(s.n_train.tolist(), [12, 24, 36])
        self.assertEqual(s.n_validation.tolist(), [12, 12, 12])

    def test_bo5_control_cannot_affect_bo7_fitting(self):
        d = _synthetic()
        base, stab = AU.run_format(d, "BO7")
        d2 = d.copy()
        m = d2.format == "BO5"
        d2.loc[m, "y"] = 1 - d2.loc[m, "y"]
        d2.loc[m, "z"] = -d2.loc[m, "z"] * 3
        chg, stab2 = AU.run_format(d2, "BO7")
        pd.testing.assert_frame_equal(base, chg)
        pd.testing.assert_frame_equal(stab, stab2)


class ShrinkageTest(unittest.TestCase):
    def test_shrinkage_centered_at_one(self):
        d = _synthetic()
        z, y = d.z.to_numpy(), d.y.to_numpy()
        self.assertAlmostEqual(AU.fit(z, y, 1e9)[1], 1.0, places=5)
        a, b = AU.fit(z, y, 1e9, intercept=True)
        self.assertAlmostEqual(a, 0.0, places=5)
        self.assertAlmostEqual(b, 1.0, places=5)
        raw = AU.fit(z, y, 0.0)[1]
        prev = raw
        for lam in (2.0, 10.0, 50.0):
            b = AU.fit(z, y, lam)[1]
            self.assertTrue(min(1.0, raw) - 1e-9 <= b <= max(1.0, raw) + 1e-9)
            self.assertLessEqual(abs(b - 1), abs(prev - 1) + 1e-12)
            prev = b
        self.assertEqual(AU.fit(z, y, 0.0)[0], 0.0)

    def test_unregularized_fit_recovers_known_slope(self):
        rng = np.random.default_rng(1)
        z = rng.normal(0, 1, 20000)
        y = (rng.uniform(size=z.size) < AU.sigmoid(1.7 * z)).astype(float)
        self.assertAlmostEqual(AU.fit(z, y, 0.0)[1], 1.7, delta=0.06)


class BootstrapTest(unittest.TestCase):
    def test_bootstrap_compares_identical_series(self):
        preds, _ = AU.run_format(_synthetic(), "BO7")
        boot = AU.bootstrap(preds, ["C1", "CSEL"], b=200)
        self.assertTrue((boot.n_rows == preds[preds.model_id == "B5"].shape[0]).all())
        self.assertTrue((boot.n_clusters == boot.n_rows).all())
        broken = preds.drop(preds[(preds.model_id == "C1")].index[:1])
        with self.assertRaises(ValueError):
            AU.bootstrap(broken, ["C1"], b=10)

    def test_identical_model_has_zero_delta(self):
        preds, _ = AU.run_format(_synthetic(), "BO7")
        boot = AU.bootstrap(preds, ["C0"], b=200).iloc[0]
        self.assertAlmostEqual(boot.mean_delta_log_loss, 0.0, places=12)
        self.assertAlmostEqual(boot.delta_log_loss_ci_low, 0.0, places=12)
        self.assertAlmostEqual(boot.delta_log_loss_ci_high, 0.0, places=12)


class PreRegistrationAndUniverseTest(unittest.TestCase):
    def test_promotion_rule_exists_before_model_execution(self):
        rule = ROOT / lock.RULE_PATH
        self.assertTrue(rule.exists())
        lk = json.loads((ROOT / lock.LOCK_PATH).read_text())
        self.assertEqual(lk["groups"]["promotion_rule"][lock.RULE_PATH], baseline.sha256_file(rule))
        summ = ROOT / "reports/bo7_audit/run_summary.json"
        if summ.exists():
            s = json.loads(summ.read_text())
            self.assertEqual(s["promotion_rule_sha256"], baseline.sha256_file(rule))
            t = lambda x: dt.datetime.strptime(x, "%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
            self.assertLessEqual(t(lk["created_at"]), t(s["started_at"]))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                R.guard(tmp)

    def test_annual_finals_outcomes_absent(self):
        s = AU.load_series(ROOT)
        self.assertFalse(s.season.eq(data.ANNUAL_FINALS_2026).any())
        self.assertTrue((s.t < PROSPECTIVE_HOLDOUT_START).all())
        p = ROOT / "data/processed/modeling/bo7_audit_predictions.parquet"
        if p.exists():
            self.assertFalse(pd.read_parquet(p).season.eq(data.ANNUAL_FINALS_2026).any())

    def test_all_locked_artifacts_unchanged(self):
        self.assertEqual(lock.check(ROOT), [])


if __name__ == "__main__":
    unittest.main()
