import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.evaluation.benchmark import PROSPECTIVE_HOLDOUT_START
from openkpl.roster import baseline
from openkpl.tournament import engine as E
from openkpl.tournament import lock, run
from openkpl.tournament import strength as S

ROOT = Path(__file__).resolve().parents[1]
HAVE = (ROOT / S.STRENGTH_FILE).exists() and (ROOT / lock.LOCK_PATH).exists()


def _bit_play(n):
    """Deterministic artificial winners: match k is won by side a iff bit k of the row index is set."""
    state = {"k": 0}
    rows = np.arange(n)

    def play(a, b, fmt):
        assert fmt == E.BO7
        win_a = ((rows >> state["k"]) & 1).astype(bool)
        state["k"] += 1
        return np.where(win_a, a, b), np.where(win_a, b, a)
    return play


@unittest.skipUnless(HAVE, "v1.0 frozen artifacts not built")
class TestInformationBoundary(unittest.TestCase):
    def test_annual_finals_and_post_cutoff_rows_cannot_enter_strength(self):
        canon = pd.read_parquet(ROOT / S.CANONICAL)
        fake = canon.iloc[-2:].copy()
        fake["series_id"] = ["FAKE_AF_1", "FAKE_AF_2"]
        fake["season"] = [S.ANNUAL_FINALS_SEASON, "KPL2026S2"]
        fake["start_time"] = [pd.Timestamp("2026-10-03 18:00"), pd.Timestamp("2026-09-30 18:00")]
        fake["label_team_a_win"] = 1 - fake["label_team_a_win"]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            for rel in (S.HYPER,):
                (t / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, t / rel)
            (t / S.CANONICAL).parent.mkdir(parents=True, exist_ok=True)
            pd.concat([canon, fake], ignore_index=True).to_parquet(t / S.CANONICAL, index=False)
            m_inj, d_inj, _ = S.replay_b5(t)
        m, d, _ = S.replay_b5(ROOT)
        self.assertFalse(d_inj.series_id.isin(["FAKE_AF_1", "FAKE_AF_2"]).any())
        self.assertEqual(dict(m.r), dict(m_inj.r))
        self.assertTrue((pd.to_datetime(d.start_time) < PROSPECTIVE_HOLDOUT_START).all())
        self.assertFalse((d.season == S.ANNUAL_FINALS_SEASON).any())

    def test_frozen_strength_is_pre_cutoff_and_unchanged(self):
        fr = pd.read_parquet(ROOT / S.STRENGTH_FILE)
        self.assertTrue((pd.to_datetime(fr.last_eligible_match) < PROSPECTIVE_HOLDOUT_START).all())
        import json
        h = json.loads((ROOT / S.STRENGTH_HASH).read_text())
        self.assertEqual(baseline.sha256_file(ROOT / S.STRENGTH_FILE), h["sha256"])
        self.assertEqual(h["reproduces_v031_B5_F11_max_abs_diff"], 0.0)
        mtime = (ROOT / S.STRENGTH_FILE).stat().st_mtime
        S.freeze(ROOT)                                     # must verify, never rewrite
        self.assertEqual(mtime, (ROOT / S.STRENGTH_FILE).stat().st_mtime)
        self.assertTrue(run.af_outcomes_absent(ROOT)["ok"])

    def test_primary_has_no_bo7_correction_roster_or_draft(self):
        ctx = run.context(ROOT)
        P5, P7 = run.matrices(ctx)
        self.assertIs(P5, P7)
        np.testing.assert_allclose(P5, E.elo_matrix(ctx.r) * (1 - np.eye(12)) + 0.5 * np.eye(12), atol=0)
        np.testing.assert_allclose(P5 + P5.T, 1.0, atol=1e-12)
        prim = ctx.rules["scenarios"]["primary"]
        self.assertEqual(ctx.rules["scenarios"]["probability_transforms"][prim["probability_transform"]],
                         {"bo5_lambda": 1.0, "bo7_lambda": 1.0})
        banned = re.compile(r"(player_model|game_draft|draft|series_state|bo7_audit\.audit|bo7_audit import audit)")
        for f in ("engine.py", "strength.py", "run.py", "figures.py"):
            src = (ROOT / "src/openkpl/tournament" / f).read_text()
            imports = "\n".join(l for l in src.splitlines() if l.startswith(("import", "from")))
            self.assertIsNone(banned.search(imports), f)

    def test_locks_unchanged(self):
        self.assertEqual(lock.check(ROOT), [])


class TestBracket(unittest.TestCase):
    def test_every_double_elimination_transition_is_legal_and_terminates(self):
        n = 2 ** len(E.BRACKET)
        slots = np.tile(np.arange(8), (n, 1))
        de = E.double_elimination(slots, _bit_play(n))
        losses = de["losses"][:, :8]
        champ, runner = de["champion"], de["FINAL"][3]
        self.assertTrue((losses[np.arange(n), champ] <= 1).all())
        self.assertTrue(np.isin(losses[np.arange(n), runner], [1, 2]).all())
        self.assertTrue((losses.sum(1) == 6 * 2 + losses[np.arange(n), champ] + losses[np.arange(n), runner]).all())
        self.assertEqual(len(np.unique(champ)), 8)          # every team can win the title

    def test_wiring_matches_config(self):
        rules = S.load_rules(ROOT)
        kb = rules["knockout_bracket"]
        code = {"S": lambda r: f"s{r}", "W": lambda r: f"W_{r}", "L": lambda r: f"L_{r}"}
        for m, a, b in E.BRACKET:
            self.assertEqual((kb[m]["a"], kb[m]["b"]), (code[a[0]](a[1]), code[b[0]](b[1])), m)

    def test_deterministic_lower_index_wins(self):
        slots = np.array([[0, 1, 2, 3, 4, 5, 6, 7]])
        de = E.double_elimination(slots, lambda a, b, f: (np.minimum(a, b), np.maximum(a, b)))
        got = {m: (int(de[m][2][0]), int(de[m][3][0])) for m, _, _ in E.BRACKET}
        self.assertEqual(got, {"QF1": (0, 1), "QF2": (2, 3), "QF3": (4, 5), "QF4": (6, 7), "LB1A": (1, 5), "LB1B": (3, 7),
                               "SF1": (0, 2), "SF2": (4, 6), "LB2A": (1, 2), "LB2B": (3, 6), "UBF": (0, 4),
                               "LBSF": (1, 3), "LBF": (1, 4), "FINAL": (0, 1)})

    def test_reentry_is_rejected(self):
        slots = np.array([[0, 1, 2, 3, 4, 5, 6, 7]])
        calls = {"k": 0}

        def bad(a, b, f):   # QF2 "advances" team 1, already beaten in QF1, into the upper semi-final
            calls["k"] += 1
            if calls["k"] == 2:
                return np.array([1]), b
            return np.minimum(a, b), np.maximum(a, b)
        with self.assertRaises(AssertionError):
            E.double_elimination(slots, bad)


class TestStage1AndSelection(unittest.TestCase):
    def test_tiebreak_matches_config(self):
        rules = S.load_rules(ROOT)
        self.assertEqual(set(rules["scenarios"]["stage1_tiebreak_scenarios"]), set(E.TIEBREAKS))
        W = np.array([[3, 3, 3, 2, 1, 0]])
        G = np.array([[2, 5, 5, 0, -3, -9]])
        rng = np.random.default_rng(0)
        orders = [E.rank_group(np.repeat(W, 2000, 0), np.repeat(G, 2000, 0), "T1_WINS_GAMEDIFF_LOT", rng, np.zeros(6))
                  for _ in range(1)]
        o, audit = orders[0]
        self.assertTrue((o[:, 2] == 0).all() and (o[:, 3:] == [3, 4, 5]).all())
        self.assertAlmostEqual((o[:, 0] == 1).mean(), 0.5, delta=0.05)     # exact tie on wins + gd -> lot
        self.assertTrue(audit["fallback"][:, 0].all() and audit["resolved_by_game_diff"][:, 1].all())
        o2, a2 = E.rank_group(np.repeat(W, 3000, 0), np.repeat(G, 3000, 0), "T2_WINS_LOT", rng, np.zeros(6))
        self.assertAlmostEqual((o2[:, 2] == 0).mean(), 1 / 3, delta=0.04)   # game diff ignored
        self.assertFalse(a2["resolved_by_game_diff"].any())
        o3, _ = E.rank_group(np.repeat(W, 20000, 0), np.repeat(G, 20000, 0), "T3_WINS_GAMEDIFF_STRENGTH", rng,
                             np.array([0, 1800, 1400, 0, 0, 0.0]))
        self.assertTrue((o3[:, 2] == 0).all())
        self.assertGreater((o3[:, 0] == 1).mean(), 0.85)                    # stronger team favoured on exact tie

    def test_selection_respects_legal_choices(self):
        r = np.array([1800, 1700, 1650, 1600, 1500, 1400, 1580, 1560, 1520, 1300, 1450, 1480.0])
        P = E.elo_matrix(r)
        np.fill_diagonal(P, 0.5)
        n = 5000
        m5, m6 = np.full(n, 4), np.full(n, 5)
        e = np.tile([7, 8, 9, 10], (n, 1))
        for strat in ("OPTIMAL_SELECTION", "RANDOM_LEGAL_SELECTION", "ADVERSARIAL_SELECTION"):
            sim = E.Sim(P, P, r, n, np.random.default_rng(1))
            w, l, pairs = E.breakthrough(sim, m5, m6, e, strat, "ELITE_2_TO_5")
            self.assertTrue((pairs[:, 0, 0] == 4).all() and (pairs[:, 1, 0] == 5).all())
            self.assertTrue(np.isin(pairs[:, :, 1], [7, 8, 9, 10]).all() and np.isin(pairs[:, 2, 0], [7, 8, 9, 10]).all())
            self.assertTrue((np.sort(pairs.reshape(n, 6), 1) == [4, 5, 7, 8, 9, 10]).all())
            self.assertTrue((np.sort(np.column_stack([w, l]), 1) == [4, 5, 7, 8, 9, 10]).all())
            if strat == "OPTIMAL_SELECTION":
                self.assertTrue((pairs[:, 0, 1] == 9).all() and (pairs[:, 1, 1] == 10).all())
            if strat == "ADVERSARIAL_SELECTION":
                self.assertTrue((pairs[:, 0, 1] == 7).all() and (pairs[:, 1, 1] == 8).all())
        r2 = r.copy()
        r2[5] = 1000                                        # M6 weakest: under SELECTION_POOL_ANY M5 may choose M6
        sim = E.Sim(P, P, r2, n, np.random.default_rng(1))
        _, _, pairs = E.breakthrough(sim, m5, m6, e, "OPTIMAL_SELECTION", "SELECTION_POOL_ANY")
        self.assertTrue((pairs[:, 0, 1] == 5).all())

    def test_draw_respects_constraints(self):
        n = 40000
        rng = np.random.default_rng(3)
        seeds = np.tile([0, 1], (n, 1))
        others = np.tile([2, 3, 6, 7, 8, 9], (n, 1))
        bt = others[:, 3:]
        half = lambda slots, t: (np.argmax(slots == t, 1) // 4)
        qf = lambda slots, t: (np.argmax(slots == t, 1) // 2)
        for sc in ("K1_SEEDS_OPPOSITE_HALVES", "K2_SEEDS_NOT_PAIRED", "K3_SEEDS_OPPOSITE_HALVES_VS_BREAKTHROUGH"):
            s = E.draw(rng, seeds, others, bt, sc)
            self.assertTrue((np.sort(s, 1) == [0, 1, 2, 3, 6, 7, 8, 9]).all(), sc)
            self.assertTrue((qf(s, 0) != qf(s, 1)).all(), sc)
            if sc != "K2_SEEDS_NOT_PAIRED":
                self.assertTrue((half(s, 0) != half(s, 1)).all(), sc)
            if sc == "K3_SEEDS_OPPOSITE_HALVES_VS_BREAKTHROUGH":
                for sd in (0, 1):
                    pos = np.argmax(s == sd, 1)
                    self.assertTrue(np.isin(s[np.arange(n), pos ^ 1], [7, 8, 9]).all())
            pool = [2, 3, 6] if sc.startswith("K3") else [2, 3, 6, 7, 8, 9]   # exchangeable non-seeds: same slot law
            freq = np.stack([np.bincount(np.argmax(s == t, 1), minlength=8) / n for t in pool])
            self.assertLess(np.abs(freq - freq.mean(0)).max(), 0.015, sc)
        with self.assertRaises(AssertionError):
            E._fill(np.full((1, 8), -1), np.arange(7)[None, :], rng)


@unittest.skipUnless(HAVE, "v1.0 frozen artifacts not built")
class TestFullSimulation(unittest.TestCase):
    def test_full_tournament_sums_and_advancement(self):
        ctx = run.context(ROOT)
        for sc in ("PRIMARY", "ALT"):
            scen = dict(ctx.rules["scenarios"]["primary"])
            if sc == "ALT":
                scen.update(stage1_tiebreak="T3_WINS_GAMEDIFF_STRENGTH", selection_pool="SELECTION_POOL_ANY",
                            breakthrough_selection="RANDOM_LEGAL_SELECTION", knockout_draw="K2_SEEDS_NOT_PAIRED")
            r = run.simulate(ctx, scen, n=20000, seed=7)
            self.assertTrue(all(r["sanity"].values()), r["sanity"])
            self.assertAlmostEqual(r["p"]["champion"].sum(), 1.0, places=12)
            self.assertAlmostEqual(r["p"]["final"].sum(), 2.0, places=12)
            self.assertAlmostEqual(r["p"]["knockout"].sum(), 8.0, places=12)
            self.assertTrue((r["p"]["stage1_elimination"][:6] == 0).all())
        a = run.simulate(ctx, ctx.rules["scenarios"]["primary"], n=5000, seed=11)
        b = run.simulate(ctx, ctx.rules["scenarios"]["primary"], n=5000, seed=11)
        np.testing.assert_array_equal(a["p"]["champion"], b["p"]["champion"])
        nt = run.simulate(ctx, None, n=5000, seed=5, neutral=True)
        self.assertTrue(all(nt["sanity"].values()))

    def test_schedule_is_complete_cross_group(self):
        ctx = run.context(ROOT)
        self.assertEqual(len(ctx.schedule), 36)
        self.assertEqual(set(ctx.schedule), {(m, e) for m in range(6) for e in range(6, 12)})


@unittest.skipUnless(HAVE and (ROOT / run.LEDGER).exists(), "ledger not built")
class TestLedger(unittest.TestCase):
    def test_ledger_is_deterministic_and_matches_file(self):
        ctx = run.context(ROOT)
        old = pd.read_csv(ROOT / run.LEDGER)
        a, b = run.ledger_rows(ctx, "X"), run.ledger_rows(ctx, "X")
        pd.testing.assert_frame_equal(a, b)
        pd.testing.assert_frame_equal(old.drop(columns="generated_at"), a.drop(columns="generated_at"),
                                      check_dtype=False, check_exact=False, rtol=0, atol=1e-10)
        self.assertEqual(len(old), 36)
        self.assertTrue(np.allclose(old.p_team_a + old.p_team_b, 1.0))
        mtime = (ROOT / run.LEDGER).stat().st_mtime
        _, status = run.write_ledger(ctx)
        self.assertEqual(status, "verified_existing")
        self.assertEqual(mtime, (ROOT / run.LEDGER).stat().st_mtime)


if __name__ == "__main__":
    unittest.main()
