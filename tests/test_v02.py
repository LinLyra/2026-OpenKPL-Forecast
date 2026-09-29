import tempfile
import unittest
from pathlib import Path

import pandas as pd

from openkpl.transform.draft import phase, boolish, literal, build_draft_tables, clean_five_role
from openkpl.transform.temporal import build_series_table
from openkpl.modeling.elo import build_series_elo
from openkpl.features.hero import role_features, synergy, counter

ROLES = ["对抗路", "打野", "中路", "发育路", "游走"]


def _bp(t1, t2, heroes, n_first_bans=4):
    seq = ([("ban", t1), ("ban", t2)] * 2 + [("pick", t1), ("pick", t2), ("pick", t2), ("pick", t1), ("pick", t1), ("pick", t2)]
           + [("ban", t2), ("ban", t1)] * 2 + [("pick", t2), ("pick", t1), ("pick", t1), ("pick", t2)])
    return [{"team": t, "ban_or_pick": a, "hero": h} for (a, t), h in zip(seq, heroes)]


def _battle(t1, t2, picks_t1, picks_t2, pos1=ROLES, pos2=ROLES):
    out = []
    for h, p in zip(picks_t1, pos1):
        out.append({"team": t1, "hero": h, "equiplist": ["鞋", "剑"], "position": p})
    for h, p in zip(picks_t2, pos2):
        out.append({"team": t2, "hero": h, "equiplist": ["鞋"], "position": p})
    return out


def _write_wzry(path, rows):
    df = pd.DataFrame(rows, columns=["team1", "team1_win", "team2", "team2_win", "battle_process", "BP_process"])
    df.to_csv(path, index=False, encoding="gb18030")


class TestDraftParsing(unittest.TestCase):
    def test_phase(self):
        self.assertEqual(phase(1, 18), "BAN_1")
        self.assertEqual(phase(5, 18), "PICK_1")
        self.assertEqual(phase(11, 18), "BAN_2")
        self.assertEqual(phase(18, 18), "PICK_2")
        self.assertEqual(phase(1, 15), "NONSTANDARD")

    def test_bool(self):
        self.assertTrue(boolish("TRUE"))
        self.assertFalse(boolish("FALSE"))
        with self.assertRaises(ValueError):
            boolish("maybe")

    def test_literal_rejects_code(self):
        with self.assertRaises(ValueError):
            literal("__import__('os').system('echo pwned')", "BP_process", 0)
        with self.assertRaises(TypeError):
            literal("{'a': 1}", "BP_process", 0)

    def test_clean_five_role_is_per_team(self):
        # Globally two of each role, but team1 has two 中路 and team2 has two 打野.
        pos1 = ["对抗路", "中路", "中路", "发育路", "游走"]
        pos2 = ["对抗路", "打野", "打野", "发育路", "游走"]
        b = _battle("A", "B", list("abcde"), list("fghij"), pos1, pos2)
        self.assertFalse(clean_five_role(b, "A", "B"))
        self.assertTrue(clean_five_role(_battle("A", "B", list("abcde"), list("fghij")), "A", "B"))


class TestDraftETL(unittest.TestCase):
    def test_build_tables_flags_and_synthetic_ids(self):
        heroes = [f"h{i}" for i in range(18)]
        bp = _bp("A", "B", heroes)
        picks_a = [e["hero"] for e in bp if e["ban_or_pick"] == "pick" and e["team"] == "A"]
        picks_b = [e["hero"] for e in bp if e["ban_or_pick"] == "pick" and e["team"] == "B"]
        good = ["A", "TRUE", "B", "FALSE", repr(_battle("A", "B", picks_a, picks_b)), repr(bp)]
        bp_missing = [dict(e) for e in bp]; bp_missing[0]["hero"] = ""
        pos_bad = ["对抗路", "中路", "中路", "", "未知"]
        bad = ["A", "FALSE", "B", "TRUE", repr(_battle("A", "B", picks_a, picks_b, pos_bad)), repr(bp_missing[:15])]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "WZRY.csv"
            _write_wzry(p, [good, bad])
            g, e, l, o, t, h = build_draft_tables(p)
        self.assertEqual(list(g.draft_game_id), ["wzry_000000", "wzry_000001"])
        self.assertTrue(g.draft_game_id_is_synthetic.all())
        self.assertFalse(g.temporal_identity_available.any())
        self.assertEqual(list(g.bp_quality_flag), ["STANDARD_18", "NONSTANDARD"])
        self.assertEqual(list(g.lineup_quality_flag), ["CLEAN_FIVE_ROLE", "NONSTANDARD_ROLE_ASSIGNMENT"])
        self.assertEqual(list(g.has_missing_hero), [False, True])
        self.assertEqual(g.source_row_sha256.str.len().tolist(), [64, 64])
        self.assertEqual(list(g.winner_team), ["A", "B"])
        self.assertEqual(int(e.hero_missing.sum()), 1)
        self.assertEqual(len(l), 20)
        # Raw position is retained; blank normalizes to 未知.
        row1 = l[l.draft_game_id == "wzry_000001"]
        self.assertIn("", set(row1.position_raw))
        self.assertEqual(int((row1.position_normalized == "未知").sum()), 2)
        self.assertEqual(len(o), 5 * 2 + 5 * 1 + 5 * 2 + 5 * 1)


class TestTemporal(unittest.TestCase):
    def _db(self, d, rows):
        import sqlite3
        p = Path(d) / "kpl.db"
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE kpl_matches (id TEXT PRIMARY KEY, season TEXT, stage TEXT, match_time TEXT,"
                    " team_a TEXT, team_b TEXT, score_a INTEGER, score_b INTEGER, status INTEGER,"
                    " update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        con.executemany("INSERT INTO kpl_matches (id,season,stage,match_time,team_a,team_b,score_a,score_b,status)"
                        " VALUES (?,?,?,?,?,?,?,?,?)", rows)
        con.commit(); con.close()
        return p

    def test_status_score_conflict_is_flagged_not_labeled(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._db(d, [
                ("s1", "S", "R1", "2024-01-01 10:00:00", "A", "B", 3, 1, 4),
                ("s2", "S", "R1", "2024-01-02 10:00:00", "A", "B", 2, 0, 3),
                ("s3", "S", "R1", "2024-01-03 10:00:00", "A", "B", 0, 0, 1),
            ])
            s = build_series_table(p).set_index("series_id")
        self.assertEqual(s.loc["s1", "label_flag"], "COMPLETED")
        self.assertEqual(s.loc["s1", "winner_team"], "A")
        self.assertEqual(s.loc["s2", "label_flag"], "STATUS_SCORE_CONFLICT")
        self.assertFalse(bool(s.loc["s2", "is_completed_labeled"]))
        self.assertTrue(pd.isna(s.loc["s2", "winner_team"]))
        self.assertEqual(s.loc["s3", "label_flag"], "NOT_FINISHED")


class TestSeriesElo(unittest.TestCase):
    def test_no_future_leakage(self):
        s = pd.DataFrame({
            "series_id": ["x2", "x1", "x3"],
            "start_time": pd.to_datetime(["2024-01-02", "2024-01-01", "2024-01-02"]),
            "team_a": ["A", "A", "C"], "team_b": ["B", "B", "D"],
            "winner_team": ["A", "A", "C"], "is_completed_labeled": [True, True, True],
        })
        p = build_series_elo(s).set_index("series_id")
        self.assertAlmostEqual(p.loc["x1", "p_team_a"], 0.5)
        self.assertGreater(p.loc["x2", "p_team_a"], 0.5)
        self.assertAlmostEqual(p.loc["x3", "p_team_a"], 0.5)
        self.assertEqual(list(build_series_elo(s).series_id), ["x1", "x2", "x3"])

    def test_same_timestamp_uses_pre_group_ratings(self):
        s = pd.DataFrame({
            "series_id": ["a", "b"],
            "start_time": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "team_a": ["A", "A"], "team_b": ["B", "C"],
            "winner_team": ["A", "A"], "is_completed_labeled": [True, True],
        })
        p = build_series_elo(s)
        self.assertTrue((p.p_team_a == 0.5).all())

    def test_unlabeled_series_excluded(self):
        s = pd.DataFrame({
            "series_id": ["a", "b"], "start_time": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "team_a": ["A", "A"], "team_b": ["B", "B"], "winner_team": ["A", None],
            "is_completed_labeled": [True, False],
        })
        self.assertEqual(len(build_series_elo(s)), 1)


class TestHeroFeatures(unittest.TestCase):
    def setUp(self):
        self.l = pd.DataFrame({
            "draft_game_id": ["g1"] * 4 + ["g2"] * 4,
            "team": ["A", "A", "B", "B"] * 2,
            "hero": ["x", "y", "z", "w", "x", "y", "z", "w"],
            "position_normalized": ["中路", "打野", "中路", "打野", "对抗路", "打野", "未知", "打野"],
        })
        self.g = pd.DataFrame({"draft_game_id": ["g1", "g2"], "winner_team": ["A", "B"]})

    def test_hfi_bounds_and_unknown_excluded(self):
        _, h = role_features(self.l)
        h = h.set_index("hero")
        self.assertAlmostEqual(h.loc["y", "hero_flexibility_index"], 0.0)
        self.assertGreater(h.loc["x", "hero_flexibility_index"], 0.0)
        self.assertLessEqual(h.hero_flexibility_index.max(), 1.0)
        self.assertEqual(h.loc["z", "unknown_role_slots"], 1)
        self.assertEqual(h.loc["z", "known_role_slots"], 1)

    def test_shrinkage(self):
        sy = synergy(self.g, self.l, prior=20.0).set_index(["hero_a", "hero_b"])
        self.assertEqual(sy.loc[("x", "y"), "games"], 2)
        self.assertAlmostEqual(sy.loc[("x", "y"), "shrunk_win_rate"], (1 + 10) / 22)
        co = counter(self.g, self.l, prior=20.0).set_index(["hero", "opponent_hero"])
        self.assertEqual(co.loc[("x", "z"), "games"], 2)
        self.assertAlmostEqual(co.loc[("x", "z"), "shrunk_win_rate"] + co.loc[("z", "x"), "shrunk_win_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
