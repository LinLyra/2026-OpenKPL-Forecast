import csv
import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from openkpl.roster import baseline
from openkpl.tournament import engine as E
from openkpl.tournament import lock, provenance, run
from openkpl.tournament import strength as S

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "reports/tournament/rule_source_registry.csv"
COLUMNS = ["rule_id", "rule_description", "source_tier", "publisher", "title", "publication_date", "retrieved_at", "url",
           "quoted_evidence", "verification_status", "supports_current_implementation", "notes"]
STRENGTH_SHA = "49cacffc24c1eca84f78e4c1772e38b4a7be0d9ddca09bbdca78d85d69907dc7"
LEDGER_CONTENT_SHA = "dfe42a35d4b9b458928f9ae2c61d3c1a0deacbfcf2ba5a3f7760d4fc47a90638"


def _bit_play(n):
    state, rows = {"k": 0}, np.arange(n)

    def play(a, b, fmt):
        win_a = ((rows >> state["k"]) & 1).astype(bool)
        state["k"] += 1
        return np.where(win_a, a, b), np.where(win_a, b, a)
    return play


@unittest.skipUnless(REGISTRY.exists(), "registry not built")
class TestRegistry(unittest.TestCase):
    def setUp(self):
        with open(REGISTRY, encoding="utf-8") as f:
            self.reader = csv.DictReader(f)
            self.rows = list(self.reader)
            self.cols = self.reader.fieldnames

    def test_schema(self):
        self.assertEqual(self.cols, COLUMNS)
        self.assertTrue(self.rows)
        for r in self.rows:
            self.assertEqual(len(r), len(COLUMNS))
            self.assertTrue(r["url"].startswith("http"), r["rule_id"])
            self.assertTrue(r["verification_status"])

    def test_tier3_never_official(self):
        for r in self.rows:
            if r["source_tier"].startswith("3"):
                self.assertNotIn("VERIFIED_OFFICIAL", r["verification_status"], r)

    def test_historical_never_labelled_2026(self):
        for r in self.rows:
            if r["publication_date"][:4] in ("2024", "2025"):
                self.assertNotIn("2026", r["verification_status"], r)

    def test_every_gate_covered(self):
        ids = {r["rule_id"].split("_")[1] for r in self.rows}
        self.assertTrue({"A", "B", "C", "D"} <= ids)


class TestProxyMechanics(unittest.TestCase):
    def test_protected_breakthrough_is_legal(self):
        n = 20000
        r = np.random.default_rng(1).normal(1500, 100, 12)
        P = E.elo_matrix(r)
        for strat in ("OPTIMAL_SELECTION", "RANDOM_LEGAL_SELECTION", "ADVERSARIAL_SELECTION"):
            sim = E.Sim(P, P, r, n, np.random.default_rng(2))
            perm = np.argsort(sim.rng.random((n, 6)), axis=1)
            sel = np.column_stack([np.full(n, 4), np.full(n, 5), 6 + perm[:, 0]])
            pool = 6 + perm[:, 1:4]
            w, l, pairs = provenance.breakthrough_protected(sim, sel, pool, strat)
            self.assertTrue((pairs[:, :, 0] == sel).all())
            self.assertTrue((np.sort(pairs[:, :, 1], 1) == np.sort(pool, 1)).all())
            both = np.concatenate([w, l], 1)
            self.assertTrue((np.sort(both, 1) == np.sort(np.concatenate([sel, pool], 1), 1)).all())
        opt = E.Sim(P, P, r, 1, np.random.default_rng(0))
        _, _, pr = provenance.breakthrough_protected(opt, np.array([[4, 5, 6]]), np.array([[7, 8, 9]]), "OPTIMAL_SELECTION")
        self.assertEqual(pr[0, 0, 1], [7, 8, 9][int(np.argmin(r[[7, 8, 9]]))])

    def test_alternative_wiring_terminates_legally(self):
        n = 2 ** 14
        slots = np.tile(np.arange(8), (n, 1))
        res = provenance.double_elimination_wired(slots, _bit_play(n), provenance.BRACKET_ALT)
        self.assertEqual(len(np.unique(res["champion"])), 8)
        self.assertTrue((res["losses"][:, 8:] == 0).all())

    def test_alternative_wiring_differs_only_in_lower_bracket(self):
        base = {m: (a, b) for m, a, b in E.BRACKET}
        alt = {m: (a, b) for m, a, b in provenance.BRACKET_ALT}
        self.assertEqual(set(base), set(alt))
        self.assertEqual({m for m in base if base[m] != alt[m]}, {"LB1A", "LB1B", "LB2A", "LB2B"})

    def test_classification(self):
        self.assertEqual(provenance.classify(0.0049), "IMMATERIAL")
        self.assertEqual(provenance.classify(0.01), "LOW")
        self.assertEqual(provenance.classify(0.021), "MATERIAL")


@unittest.skipUnless((ROOT / S.STRENGTH_FILE).exists() and (ROOT / lock.LOCK_PATH).exists(), "v1.0 artifacts not built")
class TestFreezeIntegrity(unittest.TestCase):
    def test_strength_and_ledger_hashes_unchanged(self):
        self.assertEqual(baseline.sha256_file(ROOT / S.STRENGTH_FILE), STRENGTH_SHA)
        d = pd.read_csv(ROOT / run.LEDGER).drop(columns="generated_at")
        self.assertEqual(hashlib.sha256(d.to_csv(index=False).encode()).hexdigest(), LEDGER_CONTENT_SHA)

    def test_lock_and_candidate_manifest(self):
        self.assertEqual(lock.check(ROOT), [])
        man = json.loads((ROOT / lock.CANDIDATE_MANIFEST).read_text())
        files = man.get("files", man)
        for rel, h in files.items():
            if isinstance(h, str) and len(h) == 64 and (ROOT / rel).exists():
                self.assertEqual(baseline.sha256_file(ROOT / rel), h, rel)

    def test_provenance_captures_unchanged(self):
        d = ROOT / provenance.CAPTURES
        man = json.loads((d / "CAPTURE_MANIFEST.json").read_text())
        for name, h in man["files"].items():
            self.assertEqual(baseline.sha256_file(d / name), h, name)

    def test_materiality_all_rules_classified(self):
        p = ROOT / provenance.MATERIALITY
        if not p.exists():
            self.skipTest("materiality not built")
        m = pd.read_csv(p)
        self.assertTrue(m.classification.isin(["IMMATERIAL", "LOW", "MATERIAL"]).all())
        self.assertTrue((m.classification == m.max_abs_championship_delta.map(provenance.classify)).all())


if __name__ == "__main__":
    unittest.main()
