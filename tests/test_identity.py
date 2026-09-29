import hashlib
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from openkpl.identity.audit import (build_inventory, run_identity_audit, season_order, team_appearances)
from openkpl.identity.candidates import name_features, transition_score
from openkpl.identity.registry import (REGISTRY_COLUMNS, build_empty_registry, read_registry, validate_registry,
                                       write_or_update_registry)


def _series(rows):
    """rows: (series_id, season, start_time, team_a, team_b, score_a, score_b, status)"""
    df = pd.DataFrame(rows, columns=["series_id", "season", "start_time", "team_a", "team_b", "score_a", "score_b", "status"])
    df["start_time"] = pd.to_datetime(df.start_time)
    df["stage"] = "R1"
    done = (df.status == 4) & (df.score_a != df.score_b)
    df["is_completed_labeled"] = done
    df["winner_team"] = None
    df.loc[done & (df.score_a > df.score_b), "winner_team"] = df.team_a
    df.loc[done & (df.score_b > df.score_a), "winner_team"] = df.team_b
    return df


# 苏州KSG plays S1, KSG appears in S2 (clean boundary, shared token).
# 上海EDG.M / 上海RNG.M coexist and play each other.
# 北京WB / 北京 WB-like overlap: 北京WB and 北京WB.X coexist but never meet (date overlap only).
FIXTURE = [
    ("s1", "S1", "2024-01-01 10:00", "苏州KSG", "上海EDG.M", 3, 1, 4),
    ("s2", "S1", "2024-01-02 10:00", "上海RNG.M", "上海EDG.M", 0, 3, 4),
    ("s3", "S1", "2024-01-03 10:00", "苏州KSG", "上海RNG.M", 1, 3, 4),
    ("s4", "S1", "2024-01-04 10:00", "北京WB", "上海RNG.M", 3, 0, 4),
    ("s5", "S1", "2024-01-05 10:00", "北京WB.X", "上海EDG.M", 3, 2, 4),
    ("s6", "S2", "2024-06-01 10:00", "KSG", "上海EDG.M", 3, 0, 4),
    ("s7", "S2", "2024-06-02 10:00", "KSG", "上海RNG.M", 0, 0, 1),
    ("s8", "S2", "2024-06-03 10:00", "上海RNG.M", "北京WB", 3, 2, 4),
]


def _run(rows=FIXTURE, registry=None):
    d = tempfile.TemporaryDirectory()
    out = Path(d.name) / "identity"
    reg = Path(registry) if registry else Path(d.name) / "team_identity_registry.csv"
    res = run_identity_audit(_series(rows), out, reg)
    return d, out, reg, res


class TestInventory(unittest.TestCase):
    def test_A_inventory_aggregation(self):
        s = _series(FIXTURE)
        inv = build_inventory(team_appearances(s), season_order(s)).set_index("observed_team_name")
        ksg = inv.loc["苏州KSG"]
        self.assertEqual(ksg.series_count, 2)
        self.assertEqual((ksg.wins, ksg.losses), (1, 1))
        rng = inv.loc["上海RNG.M"]
        self.assertEqual(rng.series_count, 5)
        self.assertEqual(rng.completed_series_count, 4)
        self.assertEqual((rng.wins, rng.losses), (2, 2))  # won s3, s8; lost s2, s4; s7 unfinished
        self.assertEqual(rng.seasons_list, "S1|S2")
        self.assertEqual(rng.opponents_count, 4)
        self.assertEqual(inv.loc["KSG", "completed_series_count"], 1)

    def test_G_observed_names_unchanged(self):
        rows = FIXTURE + [("s9", "S2", "2024-06-04 10:00", " 广州TTG ", "上海EDG.M", 3, 0, 4)]
        d, out, reg, res = _run(rows)
        with d:
            names = set(res["inventory"].observed_team_name)
            self.assertIn(" 广州TTG ", names)
            csv = pd.read_csv(out / "team_name_inventory.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
            self.assertIn(" 广州TTG ", set(csv.observed_team_name))
            self.assertIn(" 广州TTG ", set(read_registry(reg).observed_name))
            self.assertEqual(set(csv.observed_team_name), set(_series(rows).team_a) | set(_series(rows).team_b))

    def test_I_chronological_sorting(self):
        d, out, reg, res = _run()
        with d:
            tl = pd.read_csv(out / "team_name_timeline.csv", encoding="utf-8-sig")
            self.assertEqual(list(tl.first_seen), sorted(tl.first_seen))
            self.assertEqual(tl.observed_team_name.iloc[-1], "KSG")
            mx = pd.read_csv(out / "team_season_matrix.csv", encoding="utf-8-sig")
            self.assertEqual(list(mx.columns[1:]), ["S1", "S2"])


class TestCandidates(unittest.TestCase):
    def test_B_transition_candidate_generated(self):
        d, out, reg, res = _run()
        with d:
            c = res["candidates"]
            row = c[(c.old_name == "苏州KSG") & (c.new_name == "KSG")]
            self.assertEqual(len(row), 1)
            r = row.iloc[0]
            self.assertTrue(r.strong_name_evidence)
            self.assertEqual(r.shared_latin_tokens, "ksg")
            self.assertIn("SIMILAR_NAME_AFTER_DISAPPEARANCE", r.candidate_reason)
            self.assertGreater(r.days_between, 0)
            self.assertTrue(r.score_is_triage_only)

    def test_short_tag_similarity_is_not_name_evidence(self):
        f = name_features("MTG", "TCG")
        self.assertGreaterEqual(f["string_similarity"], 0.6)
        self.assertFalse(f["strong_name_evidence"])

    def test_city_prefix_alone_is_not_name_evidence(self):
        self.assertFalse(name_features("佛山GK", "佛山DRG")["strong_name_evidence"])
        self.assertTrue(name_features("情久", "桐乡情久")["strong_name_evidence"])

    def test_C_overlapping_names_flagged_not_merged(self):
        d, out, reg, res = _run()
        with d:
            o = res["overlap"].set_index(["old_name", "new_name"])
            r = o.loc[("北京WB", "北京WB.X")]
            self.assertTrue(r.date_ranges_overlap)
            self.assertFalse(r.played_each_other)
            self.assertTrue(r.identity_conflict_flag)
            self.assertNotIn("北京WB.X", set(res["registry"].canonical_name))
            self.assertEqual(res["registry"].canonical_team_id.tolist(), [""] * len(res["registry"]))

    def test_D_head_to_head_triggers_conflict(self):
        d, out, reg, res = _run()
        with d:
            o = res["overlap"]
            r = o[(o.old_name == "上海EDG.M") & (o.new_name == "上海RNG.M")]
            if r.empty:
                r = o[(o.old_name == "上海RNG.M") & (o.new_name == "上海EDG.M")]
            self.assertEqual(len(r), 1)
            self.assertTrue(r.iloc[0].played_each_other)
            self.assertTrue(r.iloc[0].identity_conflict_flag)
            self.assertIn("PLAYED_EACH_OTHER", r.iloc[0].conflict_reasons)
            self.assertFalse(o[o.played_each_other & ~o.identity_conflict_flag].shape[0])

    def test_H_score_cannot_verify_continuity(self):
        self.assertLessEqual(transition_score(name_features("苏州KSG", "KSG"), 1.0, 1.0), 1.0)
        d, out, reg, res = _run()
        with d:
            c = res["candidates"]
            self.assertNotIn("continuity_status", c.columns)
            self.assertNotIn("review_status", c.columns)
            top = c.iloc[0]
            r = res["registry"].set_index("observed_name")
            for n in (top.old_name, top.new_name):
                self.assertEqual(r.loc[n, "continuity_status"], "UNCERTAIN")
                self.assertEqual(r.loc[n, "review_status"], "UNREVIEWED")
            self.assertTrue(c.review_required.all())


class TestRegistry(unittest.TestCase):
    def test_E_registry_starts_unreviewed(self):
        d, out, reg, res = _run()
        with d:
            r = read_registry(reg)
            self.assertEqual(list(r.columns), REGISTRY_COLUMNS)
            self.assertEqual(len(r), len(res["inventory"]))
            self.assertTrue((r.review_status == "UNREVIEWED").all())
            self.assertTrue((r.identity_type == "UNKNOWN").all())
            self.assertTrue((r.continuity_status == "UNCERTAIN").all())
            self.assertEqual(validate_registry(r), [])

    def test_F_no_canonical_ids_generated(self):
        d, out, reg, res = _run()
        with d:
            r = read_registry(reg)
            for col in ["canonical_team_id", "canonical_name", "confidence", "evidence_type", "evidence_url",
                        "evidence_note", "valid_from", "valid_to"]:
                self.assertTrue((r[col] == "").all(), col)
            self.assertEqual(res["summary"]["registry_rows_with_canonical_id"], 0)

    def test_existing_reviewed_rows_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            reg = Path(d) / "team_identity_registry.csv"
            r = build_empty_registry(["苏州KSG"])
            r.loc[0, ["canonical_team_id", "canonical_name", "review_status", "continuity_status", "evidence_url"]] = \
                ["T001", "KSG", "VERIFIED", "SAME_COMPETITIVE_ENTITY", "https://example.org"]
            r.to_csv(reg, index=False, encoding="utf-8-sig")
            out, added, created = write_or_update_registry(reg, ["苏州KSG", "KSG"])
            self.assertFalse(created)
            self.assertEqual(added, ["KSG"])
            kept = read_registry(reg).set_index("observed_name")
            self.assertEqual(kept.loc["苏州KSG", "canonical_team_id"], "T001")
            self.assertEqual(kept.loc["苏州KSG", "review_status"], "VERIFIED")
            self.assertEqual(kept.loc["KSG", "review_status"], "UNREVIEWED")


class TestDeterminism(unittest.TestCase):
    def test_J_deterministic_output(self):
        digests = []
        for rows in (FIXTURE, list(reversed(FIXTURE))):
            d, out, reg, res = _run(rows)
            with d:
                h = hashlib.sha256()
                for p in sorted(out.iterdir()):
                    h.update(p.name.encode()); h.update(p.read_bytes())
                h.update(reg.read_bytes())
                digests.append(h.hexdigest())
        self.assertEqual(digests[0], digests[1])


if __name__ == "__main__":
    unittest.main()
