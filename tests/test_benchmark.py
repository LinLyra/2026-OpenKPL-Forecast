import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.evaluation.benchmark import compute_benchmark, hyperparameter_record, split_universe, sha256_file
from openkpl.evaluation.calibration import evaluate
from openkpl.evaluation.freeze import FreezeExistsError, freeze
from openkpl.evaluation.temporal_cv import build_folds, select_hyperparameters
from openkpl.identity.audit import run_identity_audit
from openkpl.identity.membership import REVIEWED_SLOT_EVENTS, build_membership, slot_predecessors
from openkpl.identity.registry import build_empty_registry, read_registry, write_or_update_registry
from openkpl.modeling.temporal import (CoinFlip, DecayElo, Elo, SeasonResetElo, SlotInheritanceElo, SmoothedWinRate,
                                       prepare_batches, run_online)
from openkpl.transform.canonical import build_canonical_series

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/dimensions/team_identity_registry.csv"
ALL_MODELS = [CoinFlip(), SmoothedWinRate(), Elo(), DecayElo(half_life_days=30.0), SeasonResetElo(rho=0.5)]


def _series(rows):
    """rows: (series_id, season, start_time, team_a, team_b, score_a, score_b, status)"""
    df = pd.DataFrame(rows, columns=["series_id", "season", "start_time", "team_a", "team_b", "score_a", "score_b", "status"])
    df["start_time_raw"] = df.start_time
    df["start_time"] = pd.to_datetime(df.start_time)
    df["stage"] = "R1"
    decisive = df.score_a != df.score_b
    df["label_flag"] = np.where((df.status == 4) & decisive, "COMPLETED",
                                np.where(decisive, "STATUS_SCORE_CONFLICT", "NOT_FINISHED"))
    df["start_time_is_epoch_fallback"] = False
    return df


def _registry(names, aliases=None):
    """One VERIFIED canonical ID per name, except `aliases` {observed: canonical_id}."""
    r = build_empty_registry(names)
    aliases = aliases or {}
    r["canonical_team_id"] = [aliases.get(n, "T_" + n) for n in r.observed_name]
    r["canonical_name"] = r.canonical_team_id
    r["review_status"] = "VERIFIED"
    r["continuity_status"] = "SAME_COMPETITIVE_ENTITY"
    return r


def _league(seed=0, seasons=("KPL2020S1", "KPL2020S2", "KPL2021S1"), per_season=40, start="2020-01-01", extra=()):
    rng = np.random.default_rng(seed)
    teams = [f"X{i}" for i in range(6)]
    strength = dict(zip(teams, np.linspace(-1, 1, 6)))
    rows, t, i = [], pd.Timestamp(start), 0
    for s in seasons:
        for _ in range(per_season):
            a, b = rng.choice(teams, 2, replace=False)
            win = rng.random() < 1 / (1 + math.exp(-(strength[a] - strength[b])))
            rows.append((f"m{i:04d}", s, t.strftime("%Y-%m-%d %H:%M:%S"), a, b, 3 if win else 1, 1 if win else 3, 4))
            t += pd.Timedelta(days=2); i += 1
        t += pd.Timedelta(days=60)
    rows += list(extra)
    series = _series(rows)
    names = sorted(set(series.team_a) | set(series.team_b))
    canon, audit, checks = build_canonical_series(series, _registry(names))
    return canon


def _canon_simple(rows):
    """rows: (series_id, season, start_time, a, b, y) -> canonical frame via the real canonicalizer."""
    s = _series([(sid, se, t, a, b, 3 if y else 0, 0 if y else 3, 4) for sid, se, t, a, b, y in rows])
    names = sorted(set(s.team_a) | set(s.team_b))
    return build_canonical_series(s, _registry(names))[0]


def _run(model, canon):
    d, batches = prepare_batches(canon[canon.is_label_eligible])
    return d, run_online(batches, len(d), model)


class TestRegistryIdentities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = read_registry(REGISTRY).set_index("observed_name")

    def cid(self, name):
        return self.reg.loc[name, "canonical_team_id"]

    def test_01_ksg_source_alias_resolves(self):
        self.assertEqual(self.reg.loc["KSG", "identity_type"], "SOURCE_ALIAS")
        self.assertEqual(self.cid("KSG"), "TEAM_KSG")
        self.assertEqual(self.cid("苏州KSG"), "TEAM_KSG")
        s = _series([("a", "S1", "2025-01-01 10:00", "苏州KSG", "北京WB", 3, 1, 4),
                     ("b", "S2", "2026-01-01 10:00", "KSG", "北京WB", 1, 3, 4)])
        c, _, _ = build_canonical_series(s, read_registry(REGISTRY))
        self.assertEqual(set(c.canonical_team_a_id), {"TEAM_KSG"})

    def test_23_vg_jdg_separate(self):
        self.assertEqual(self.cid("厦门VG"), "TEAM_VG")
        self.assertEqual(self.cid("北京JDG"), "TEAM_JDG")

    def test_24_mtg_huobao_separate(self):
        self.assertNotEqual(self.cid("MTG"), self.cid("火豹"))
        self.assertEqual(self.cid("MTG"), self.cid("郑州MTG"))

    def test_25_tcg_tkl_separate(self):
        self.assertNotEqual(self.cid("TCG"), self.cid("九江TKL"))
        for a, b in [("BOA", "XYG"), ("深圳KLG", "情久"), ("深圳KLG", "常山UUG"), ("厦门VG", "北京JDG")]:
            self.assertNotEqual(self.cid(a), self.cid(b), (a, b))

    def test_previously_verified_entities_kept(self):
        groups = self.reg[self.reg.canonical_team_id.isin(
            ["TEAM_HERO", "TEAM_DRG", "TEAM_LGD_NBW", "TEAM_MTG", "TEAM_QINGJIU", "TEAM_TCG"])]
        self.assertEqual(len(groups), 14)
        self.assertTrue((groups.confidence == "HIGH").all())

    def test_18_identity_audit_rerun_keeps_reviewed_registry(self):
        with tempfile.TemporaryDirectory() as d:
            reg = Path(d) / "team_identity_registry.csv"
            shutil.copy(REGISTRY, reg)
            before = reg.read_bytes()
            write_or_update_registry(reg, list(read_registry(REGISTRY).observed_name))
            s = _series([("a", "S1", "2025-01-01 10:00", "苏州KSG", "北京WB", 3, 1, 4),
                         ("b", "S2", "2026-01-01 10:00", "KSG", "北京WB", 1, 3, 4)])
            run_identity_audit(s.assign(is_completed_labeled=True, winner_team=s.team_a), Path(d) / "out", reg)
            self.assertEqual(reg.read_bytes(), before)


class TestCanonicalization(unittest.TestCase):
    def test_02_alias_self_play_is_conflict_not_label(self):
        s = _series([("a", "S1", "2025-01-01 10:00", "苏州KSG", "KSG", 3, 1, 4),
                     ("b", "S1", "2025-01-02 10:00", "苏州KSG", "北京WB", 3, 1, 4)])
        c, audit, checks = build_canonical_series(s, read_registry(REGISTRY))
        row = c.set_index("series_id").loc["a"]
        self.assertEqual(row.identity_resolution_status, "CONFLICT")
        self.assertFalse(row.is_label_eligible)
        self.assertFalse(checks["no_self_play_after_canonicalization"])
        lab = c[c.is_label_eligible]
        self.assertTrue((lab.canonical_team_a_id != lab.canonical_team_b_id).all())

    def test_06_status_not_4_is_never_a_label(self):
        s = _series([("a", "S1", "2025-01-01 10:00", "X", "Y", 2, 0, 3),
                     ("b", "S1", "2025-01-02 10:00", "X", "Y", 0, 0, 1),
                     ("c", "S1", "2025-01-03 10:00", "X", "Y", 3, 0, 4)])
        c, audit, checks = build_canonical_series(s, _registry(["X", "Y"]))
        c = c.set_index("series_id")
        self.assertTrue(pd.isna(c.loc["a", "label_team_a_win"]))
        self.assertFalse(c.loc["a", "is_label_eligible"])
        self.assertFalse(c.loc["b", "is_label_eligible"])
        self.assertEqual(int(c.loc["c", "label_team_a_win"]), 1)
        self.assertTrue(checks["no_label_from_status_not_4"])
        d, batches = prepare_batches(c.reset_index()[c.reset_index().is_label_eligible])
        self.assertEqual(list(d.series_id), ["c"])

    def test_16_raw_names_preserved(self):
        s = _series([("a", "S1", "2025-01-01 10:00", "苏州KSG", "北京WB", 3, 1, 4),
                     ("b", "S2", "2026-01-01 10:00", "KSG", "北京WB", 1, 3, 4)])
        c, _, checks = build_canonical_series(s, read_registry(REGISTRY))
        self.assertEqual(list(c.raw_team_a), ["苏州KSG", "KSG"])
        self.assertTrue(checks["raw_names_preserved"])

    def test_17_unresolved_rows_retained(self):
        s = _series([("a", "S1", "2025-01-01 10:00", "X", "UNKNOWN_TEAM", 3, 1, 4),
                     ("b", "S1", "2025-01-02 10:00", "X", "Y", 3, 1, 4)])
        c, audit, _ = build_canonical_series(s, _registry(["X", "Y"]))
        self.assertEqual(len(c), 2)
        self.assertEqual(audit["unresolved_series"], 1)
        row = c.set_index("series_id").loc["a"]
        self.assertEqual(row.identity_resolution_status, "UNRESOLVED")
        self.assertFalse(row.is_label_eligible)
        self.assertIn("UNRESOLVED_TEAM_NAME", row.data_quality_flag)

    def test_unreviewed_rows_do_not_resolve(self):
        r = _registry(["X", "Y"])
        r.loc[r.observed_name == "Y", ["canonical_team_id", "review_status"]] = ["", "UNREVIEWED"]
        c, audit, _ = build_canonical_series(_series([("a", "S1", "2025-01-01 10:00", "X", "Y", 3, 1, 4)]), r)
        self.assertEqual(audit["unresolved_series"], 1)

    def test_interleaved_alias_names_flagged(self):
        s = _series([("a", "S1", "2025-01-01 10:00", "N1", "Z", 3, 1, 4),
                     ("b", "S1", "2025-01-02 10:00", "N2", "Z", 3, 1, 4),
                     ("c", "S1", "2025-01-03 10:00", "N1", "Z", 3, 1, 4)])
        c, audit, checks = build_canonical_series(s, _registry(["N1", "N2", "Z"], {"N1": "T", "N2": "T"}))
        self.assertFalse(checks["no_simultaneous_alias_ambiguity"])
        self.assertEqual(audit["conflicted_series"], 3)


class TestModels(unittest.TestCase):
    ROWS = [("s1", "S1", "2025-01-01 10:00", "A", "B", 1), ("s2", "S1", "2025-01-02 10:00", "A", "C", 0),
            ("s3", "S1", "2025-01-03 10:00", "B", "C", 1), ("s4", "S2", "2025-03-01 10:00", "A", "B", 0),
            ("s5", "S2", "2025-03-02 10:00", "C", "A", 1), ("s6", "S2", "2025-03-03 10:00", "B", "C", 0)]

    def test_03_current_outcome_cannot_affect_own_prediction(self):
        base = _canon_simple(self.ROWS)
        for i in range(len(self.ROWS)):
            flipped = [r if j != i else r[:5] + (1 - r[5],) for j, r in enumerate(self.ROWS)]
            for model in ALL_MODELS:
                _, (p0, ra0, rb0, _) = _run(model, base)
                _, (p1, ra1, rb1, _) = _run(model, _canon_simple(flipped))
                np.testing.assert_array_equal(p0[:i + 1], p1[:i + 1])
                np.testing.assert_array_equal(ra0[:i + 1], ra1[:i + 1])

    def test_04_future_matches_cannot_affect_earlier_ratings(self):
        future = self.ROWS + [("s7", "S2", "2025-03-10 10:00", "A", "D", 1), ("s8", "S3", "2025-06-01 10:00", "D", "B", 1)]
        for model in ALL_MODELS:
            _, (p0, ra0, rb0, _) = _run(model, _canon_simple(self.ROWS))
            _, (p1, ra1, rb1, _) = _run(model, _canon_simple(future))
            n = len(self.ROWS)
            np.testing.assert_array_equal(p0, p1[:n]); np.testing.assert_array_equal(ra0, ra1[:n])
            np.testing.assert_array_equal(rb0, rb1[:n])

    def test_05_same_timestamp_batch_predicted_before_update(self):
        rows = [("s1", "S1", "2025-01-01 10:00", "A", "B", 1), ("s2", "S1", "2025-01-01 10:00", "A", "C", 1),
                ("s3", "S1", "2025-01-02 10:00", "A", "D", 1)]
        c = _canon_simple(rows)
        self.assertEqual(set(c[c.series_id.isin(["s1", "s2"])].identity_resolution_status), {"CONFLICT"})
        c["is_label_eligible"] = True
        c["label_team_a_win"] = c.label_team_a_win.fillna(1)
        d, (p, ra, rb, through) = _run(Elo(k=32.0), c)
        self.assertEqual(p[0], 0.5); self.assertEqual(p[1], 0.5)
        self.assertEqual(ra[1], 1500.0)
        self.assertTrue(np.isnan(through[0]) and np.isnan(through[1]))
        self.assertAlmostEqual(ra[2], 1500.0 + 16.0 + 16.0)
        for model in ALL_MODELS:
            _, (p2, *_) = _run(model, c)
            self.assertEqual(p2[0], p2[1])

    def test_07_b0_always_half(self):
        d, (p, *_) = _run(CoinFlip(), _canon_simple(self.ROWS))
        self.assertTrue((p == 0.5).all())

    def test_08_new_elo_team_starts_at_1500(self):
        for model in [Elo(), DecayElo(half_life_days=30.0), SeasonResetElo(rho=0.3)]:
            d, (p, ra, rb, _) = _run(model, _canon_simple(self.ROWS + [("s9", "S2", "2025-03-09 10:00", "NEW", "A", 1)]))
            self.assertEqual(ra[-1], 1500.0)

    def test_09_elo_update_direction(self):
        m = Elo(k=20.0)
        p, ra, rb = m.predict("A", "B", 0.0)
        m.update_batch([("A", "B", 1.0, p, 0.0, ra, rb)])
        self.assertAlmostEqual(m.r["A"], 1510.0); self.assertAlmostEqual(m.r["B"], 1490.0)
        m.update_batch([("A", "B", 0.0, m.predict("A", "B", 1.0)[0], 1.0, m.r["A"], m.r["B"])])
        self.assertLess(m.r["A"], 1510.0); self.assertAlmostEqual(m.r["A"] + m.r["B"], 3000.0)

    def _reset(self, rho):
        m = SeasonResetElo(rho=rho)
        m.start_batch(0.0, "S1"); m.r = {"A": 1600.0, "B": 1400.0}
        m.start_batch(10.0, "S1")
        self.assertEqual(m.r["A"], 1600.0)
        m.start_batch(20.0, "S2")
        return m

    def test_10_season_reset_formula(self):
        m = self._reset(0.25)
        self.assertAlmostEqual(m.r["A"], 1500 + 0.25 * 100); self.assertAlmostEqual(m.r["B"], 1500 - 0.25 * 100)

    def test_11_rho_one_preserves(self):
        m = self._reset(1.0)
        self.assertEqual(m.r, {"A": 1600.0, "B": 1400.0})

    def test_12_rho_zero_resets(self):
        m = self._reset(0.0)
        self.assertEqual(m.r, {"A": 1500.0, "B": 1500.0})

    def test_rho_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            SeasonResetElo(rho=1.5)

    def test_decay_formula(self):
        m = DecayElo(half_life_days=10.0)
        m.r, m.last = {"A": 1600.0}, {"A": 0.0}
        self.assertAlmostEqual(m.rating("A", 10.0), 1550.0)
        self.assertEqual(DecayElo().rating("Z", 5.0), 1500.0)

    def test_winrate_never_extreme(self):
        m = SmoothedWinRate()
        self.assertEqual(m.predict("A", "B", 0)[0], 0.5)
        m.update_batch([("A", "B", 1.0, 0.5, 0, 0.5, 0.5)] * 50)
        p = m.predict("A", "B", 1)[0]
        self.assertTrue(0 < p < 1)


class TestBenchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canon = _league()
        cls.res = compute_benchmark(cls.canon)

    def test_13_tuning_cannot_inspect_future(self):
        dev = split_universe(self.canon)[0]
        cutoff = dev[dev.season == "KPL2020S2"].start_time.min()
        grid = {"k": [8.0, 24.0, 64.0], "scale": [400.0]}
        a, ta = select_hyperparameters(dev, cutoff, Elo, grid, {"k": 24.0, "scale": 400.0})
        garbage = dev[dev.start_time >= cutoff].copy()
        garbage["label_team_a_win"] = 1 - garbage.label_team_a_win
        b, tb = select_hyperparameters(pd.concat([dev[dev.start_time < cutoff], garbage]), cutoff, Elo, grid,
                                       {"k": 24.0, "scale": 400.0})
        self.assertEqual(a, b)
        pd.testing.assert_frame_equal(ta, tb)
        self.assertLess(ta.inner_data_through.iloc[0], cutoff)
        for sel in self.res["selections"].values():
            for r in sel:
                self.assertLess(r["inner_data_through"], r["inner_cutoff_exclusive"])

    def test_14_fold_boundaries(self):
        f = self.res["folds"]
        self.assertTrue((f.train_end < f.validation_start).all())
        self.assertTrue((f.validation_end.iloc[:-1].values < f.validation_start.iloc[1:].values).all())
        self.assertEqual(f.validation_season.nunique(), len(f))
        dev = split_universe(self.canon)[0]
        for r in f.itertuples():
            self.assertEqual(r.n_train, int((dev.start_time < r.validation_start).sum()))
        refolded = build_folds(dev, self.canon)
        pd.testing.assert_frame_equal(f, refolded)

    def test_15_data_through_before_prediction_time(self):
        p = self.res["predictions"]
        th = pd.to_datetime(p.prediction_generated_from_data_through)
        st = pd.to_datetime(p.start_time)
        self.assertTrue((th.dropna() < st[th.notna()]).all())
        self.assertTrue(th.notna().all())

    def test_19_deterministic(self):
        again = compute_benchmark(self.canon.sample(frac=1.0, random_state=3))
        pd.testing.assert_frame_equal(self.res["predictions"], again["predictions"])
        pd.testing.assert_frame_equal(self.res["metrics"], again["metrics"])
        self.assertEqual(json.dumps(hyperparameter_record(self.res), default=str),
                         json.dumps(hyperparameter_record(again), default=str))

    def test_20_prospective_holdout_cannot_enter_tuning(self):
        extra = [(f"h{i}", "KPL2023S3", f"2023-10-{i + 1:02d} 10:00:00", "X0", "X5", 0, 3, 4) for i in range(20)]
        with_holdout = _league(extra=extra)
        res2 = compute_benchmark(with_holdout, holdout_start=pd.Timestamp("2023-09-28"))
        self.assertEqual(len(res2["holdout"]), 20)
        self.assertFalse(res2["predictions"].series_id.str.startswith("h").any())
        self.assertFalse(res2["predictions"].is_prospective_holdout.any())
        pd.testing.assert_frame_equal(self.res["predictions"], res2["predictions"])
        self.assertEqual(self.res["selections"], res2["selections"])
        self.assertEqual(self.res["final"], res2["final"])

    def test_all_models_present_and_metrics_defined(self):
        m = self.res["metrics"].set_index("model_id")
        self.assertEqual(list(m.index), ["B0", "B1", "B2", "B3", "B4", "B5"])
        self.assertTrue(math.isnan(m.loc["B0", "calibration_slope"]))
        self.assertAlmostEqual(m.loc["B0", "log_loss"], math.log(2))

    def test_metrics_undefined_returns_nan(self):
        r = evaluate([1, 1, 1], [0.6, 0.7, 0.8])
        self.assertTrue(math.isnan(r["roc_auc"])); self.assertIn("one outcome class", r["notes"])


class TestSlotAndFreeze(unittest.TestCase):
    def test_22_slot_continuity_never_becomes_identity(self):
        rows = [("v1", "KPL2030S1", "2030-01-01 10:00", "厦门VG", "北京WB", 3, 0, 4),
                ("v2", "KPL2030S1", "2030-01-02 10:00", "厦门VG", "北京WB", 3, 0, 4),
                ("j1", "KPL2030S2", "2030-06-01 10:00", "北京JDG", "北京WB", 3, 0, 4)]
        reg = read_registry(REGISTRY)
        c, _, _ = build_canonical_series(_series(rows), reg)
        self.assertEqual(c.set_index("series_id").loc["j1", "canonical_team_a_id"], "TEAM_JDG")
        events = [{**REVIEWED_SLOT_EVENTS[0], "season": "KPL2030S2"}]
        m = build_membership(c, reg, events)
        j = m[m.canonical_team_id == "TEAM_JDG"].iloc[0]
        self.assertEqual(j.continuity_type, "SLOT_CONTINUITY_ONLY")
        self.assertEqual(j.predecessor_team_id, "TEAM_VG")
        c2, _, _ = build_canonical_series(_series(rows), reg)
        pd.testing.assert_frame_equal(c, c2)
        d, (p, ra, rb, _) = _run(Elo(), c)
        self.assertEqual(ra[2], 1500.0)
        d, (p, ra, rb, _) = _run(SlotInheritanceElo(lambda_slot=1.0, predecessors=slot_predecessors(m)), c)
        self.assertGreater(ra[2], 1500.0)

    def test_21_freeze_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            paths = {k: d / f"{k}.bin" for k in ["source_db", "canonical", "registry", "membership"]}
            for k, p in paths.items():
                p.write_bytes(k.encode())
            bench = d / "bench"; bench.mkdir()
            (bench / "benchmark_manifest.json").write_text(json.dumps({
                "source_dataset_hash": sha256_file(paths["source_db"]), "canonical_series_hash": sha256_file(paths["canonical"]),
                "membership_table_hash": sha256_file(paths["membership"]), "identity_registry_hash": sha256_file(paths["registry"]),
                "model_freeze_date": "2026-09-28", "prospective_holdout_start": "2026-09-28 00:00:00",
                "prospective_holdout_rule": "x", "benchmark_version": "t"}))
            (bench / "hyperparameters.json").write_text(json.dumps({"final_development_selected": {"B3": {"selected": {"k": 24}}}}))
            pd.DataFrame([{"model_id": "B3", "n": 10, "log_loss": 0.6, "brier": 0.2}]).to_csv(bench / "temporal_metrics.csv", index=False)
            fz = d / "freeze"
            freeze("B3", bench, fz, paths, d)
            first = (fz / "model_freeze_manifest.json").read_bytes()
            with self.assertRaises(FreezeExistsError):
                freeze("B3", bench, fz, paths, d)
            self.assertEqual((fz / "model_freeze_manifest.json").read_bytes(), first)
            freeze("B3", bench, fz, paths, d, force=True)
            with self.assertRaises(ValueError):
                freeze("E_SLOT", bench, d / "freeze2", paths, d)
            paths["canonical"].write_bytes(b"changed")
            with self.assertRaises(ValueError):
                freeze("B3", bench, d / "freeze3", paths, d)


if __name__ == "__main__":
    unittest.main()
