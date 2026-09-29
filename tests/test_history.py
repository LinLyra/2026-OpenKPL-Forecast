import json
import unittest
from pathlib import Path

import pandas as pd

from openkpl.history import drafts, players, wzry_full
from openkpl.roster import baseline

ROOT = Path(__file__).resolve().parents[1]
LOCK_A = ROOT / "reports/roster_audit/baseline_lock.json"
LOCK_B = ROOT / "reports/roster_collection/phase_b_lock.json"
WZRY_PATH = "data/raw/external/HoK-BP-LLM/王者荣耀KPL历年比赛数据/WZRY.csv"
HA, HB, HC = list("abcde"), list("fghij"), list("klmno")


def _games(spec):
    """spec: list of (series_id, start, chron, game_number, winner)."""
    return pd.DataFrame([{"game_key": f"{s}#G{n}", "series_id": s, "season_id": "S", "stage": "x",
                          "series_start_time": pd.Timestamp(t), "chronological_order": c, "game_number": n,
                          "winner_team_id": w} for s, t, c, n, w in spec])


def _apps(games, lineups):
    """lineups: {game_key: {team: [(player, hero), ...]}}"""
    g = games.set_index("game_key")
    rows = []
    for key, teams in lineups.items():
        for team, ps in teams.items():
            for pid, hero in ps:
                w = g.loc[key, "winner_team_id"]
                rows.append({"game_key": key, "series_id": g.loc[key, "series_id"], "game_number": g.loc[key, "game_number"],
                             "canonical_team_id": team, "player_id": pid, "hero_id": ord(hero), "hero_name": hero,
                             "position_raw": 0, "won": None if w is None else w == team})
    return pd.DataFrame(rows)


def _lineup(ha, hb, pa="A", pb="B"):
    return {"T1": [(f"{pa}{i}", h) for i, h in enumerate(ha)], "T2": [(f"{pb}{i}", h) for i, h in enumerate(hb)]}


class PlayerHeroLeakageTest(unittest.TestCase):
    def setUp(self):
        self.games = _games([("S1", "2024-01-01", 1, 1, "T1"), ("S1", "2024-01-01", 1, 2, "T1"),
                             ("S1", "2024-01-01", 1, 3, "T2"), ("S2", "2024-01-05", 2, 1, "T1")])
        self.lineups = {k: _lineup(HA, HB) for k in self.games.game_key}
        self.apps = _apps(self.games, self.lineups)

    def feats(self, games=None, apps=None):
        f = players.player_hero_temporal(self.apps if apps is None else apps, self.games if games is None else games)
        return f.set_index(["game_key", "player_id"])

    def test_player_and_hero_prior_exclude_current_game(self):
        f = self.feats()
        self.assertEqual(f.loc[("S1#G1", "A0"), "player_prior_games"], 0)
        self.assertEqual(f.loc[("S1#G2", "A0"), "player_prior_games"], 1)
        self.assertEqual(f.loc[("S1#G2", "A0"), "player_prior_wins"], 1)
        self.assertEqual(f.loc[("S1#G3", "A0"), "player_hero_prior_wins"], 2)
        self.assertEqual(f.loc[("S1#G3", "A0"), "hero_prior_games"], 2)
        self.assertEqual(f.loc[("S2#G1", "A0"), "team_hero_prior_wins"], 2)
        self.assertEqual(f.loc[("S2#G1", "A0"), "team_hero_prior_games"], 3)

    def test_preseries_excludes_same_series_games(self):
        f = self.feats()
        self.assertEqual(f.loc[("S1#G3", "A0"), "player_preseries_games"], 0)
        self.assertEqual(f.loc[("S2#G1", "A0"), "player_preseries_games"], 3)

    def test_later_same_series_game_cannot_affect_earlier(self):
        base = self.feats()
        g2 = self.games.copy()
        g2.loc[g2.game_key == "S1#G3", "winner_team_id"] = "T1"
        changed = self.feats(g2, _apps(g2, self.lineups))
        for k in ["S1#G1", "S1#G2", "S1#G3"]:
            pd.testing.assert_series_equal(base.loc[(k, "A0")].drop("won"), changed.loc[(k, "A0")].drop("won"))

    def test_missing_hero_excluded_from_hero_keyed_stats(self):
        apps = self.apps.copy()
        mask = (apps.game_key == "S1#G1") & (apps.player_id == "A0")
        apps.loc[mask, ["hero_id", "hero_name"]] = None
        f = self.feats(apps=apps)
        self.assertEqual(f.loc[("S1#G2", "A0"), "hero_prior_games"], 0)
        self.assertEqual(f.loc[("S1#G2", "A0"), "player_prior_games"], 1)
        self.assertTrue(pd.isna(f.loc[("S1#G1", "A0"), "player_hero_prior_games"]))

    def test_later_series_cannot_affect_earlier(self):
        base = self.feats()
        g2 = pd.concat([self.games, _games([("S3", "2024-02-01", 3, 1, "T2")])], ignore_index=True)
        l2 = dict(self.lineups, **{"S3#G1": _lineup(HA, HB)})
        more = self.feats(g2, _apps(g2, l2))
        cols = [c for c in base.columns if c != "temporal_rank"]
        pd.testing.assert_frame_equal(base[cols], more.loc[base.index, cols])


class DraftFeatureLeakageTest(unittest.TestCase):
    def setUp(self):
        self.games = _games([("S1", "2024-01-01", 1, 1, "T1"), ("S1", "2024-01-01", 1, 2, "T2"),
                             ("S2", "2024-01-03", 2, 1, "T1")])
        self.idg = self.games.assign(team1="T1", team2="T2", winner=self.games.winner_team_id)
        ev = []
        for key in self.games.game_key:
            for t, hs in (("T1", HA), ("T2", HB)):
                ev += [{"game_key": key, "sequence": i, "team_id": t, "ban_or_pick": "pick", "hero_name": h, "hero_id": ord(h)}
                       for i, h in enumerate(hs)]
            ev.append({"game_key": key, "sequence": 99, "team_id": "T1", "ban_or_pick": "ban", "hero_name": "z", "hero_id": None})
        self.ev = pd.DataFrame(ev)
        self.apps = _apps(self.games, {k: _lineup(HA, HB) for k in self.games.game_key})

    def run_features(self, idg=None):
        return drafts.temporal_features(self.idg if idg is None else idg, self.ev, self.apps)

    def test_hero_prior_excludes_current(self):
        hf, _, _ = self.run_features()
        a = hf[(hf.hero_name == "a")].set_index("game_key")
        self.assertEqual(list(a.hero_prior_games), [0, 1, 2])
        self.assertEqual(list(a.hero_prior_wins), [0, 1, 1])
        self.assertEqual(list(hf[hf.hero_name == "z"].hero_prior_ban_count), [0, 1, 2])
        self.assertEqual(list(a.player_hero_prior_games), [0, 1, 2])

    def test_synergy_prior_excludes_current(self):
        _, sf, _ = self.run_features()
        ab = sf[(sf.hero_a == "a") & (sf.hero_b == "b")]
        self.assertEqual(list(ab.pair_prior_games), [0, 1, 2])
        self.assertEqual(list(ab.pair_prior_wins), [0, 1, 1])

    def test_counter_prior_excludes_current(self):
        _, _, cf = self.run_features()
        af = cf[(cf.hero == "a") & (cf.opponent_hero == "f")]
        self.assertEqual(list(af.vs_prior_games), [0, 1, 2])
        self.assertEqual(list(af.vs_prior_wins), [0, 1, 1])

    def test_later_results_cannot_change_earlier_features(self):
        base = self.run_features()
        idg2 = self.idg.copy()
        idg2.loc[idg2.game_key == "S2#G1", "winner"] = "T2"
        changed = self.run_features(idg2)
        for b, c in zip(base, changed):
            cols = [x for x in b.columns if x != "won_current_game_label"]
            early = b.game_key != "S2#G1"
            pd.testing.assert_frame_equal(b.loc[early, cols].reset_index(drop=True), c.loc[early, cols].reset_index(drop=True))


class WzryLinkageTest(unittest.TestCase):
    CANON = {"A": "T1", "B": "T2"}

    @staticmethod
    def wz(rows):
        out = []
        for t1, t2, h1, h2, w1 in rows:
            bp = [{"team": t1, "hero": h, "equiplist": [], "position": ""} for h in h1] + \
                 [{"team": t2, "hero": h, "equiplist": [], "position": ""} for h in h2]
            out.append({"team1": t1, "team1_win": w1, "team2": t2, "team2_win": not w1,
                        "battle_process": repr(bp), "BP_process": "[]"})
        return pd.DataFrame(out)

    def setUp(self):
        self.games = _games([("S1", "2023-01-01", 1, 1, "T1"), ("S1", "2023-01-01", 1, 2, "T2"),
                             ("S9", "2025-06-01", 9, 1, "T1")])
        lu = {"S1#G1": _lineup(HA, HB), "S1#G2": _lineup(HC, HB), "S9#G1": _lineup(HC, HB)}
        self.apps = _apps(self.games, lu)
        self.cand = wzry_full.kplow_candidates(self.apps, self.games)

    def link(self, wz):
        return wzry_full.link(wz, self.cand, self.CANON, self.games)

    def test_global_uniqueness_across_seasons(self):
        out = self.link(self.wz([("A", "B", HA, HB, True), ("A", "B", HC, HB, False)]))
        self.assertEqual(list(out.linkage_status), ["UNIQUE_EXACT_MATCH", "MULTIPLE_EXACT_MATCHES"])
        self.assertEqual(out.candidate_count.iloc[1], 2)
        self.assertEqual(out.game_key.iloc[0], "S1#G1")

    def test_winner_is_not_a_matching_key(self):
        a = self.link(self.wz([("A", "B", HA, HB, True)]))
        b = self.link(self.wz([("A", "B", HA, HB, False)]))
        self.assertEqual(a.game_key.iloc[0], b.game_key.iloc[0])
        self.assertEqual(a.candidate_count.iloc[0], b.candidate_count.iloc[0])
        self.assertEqual(b.winner_agreement.iloc[0], "CONTRADICTION")
        self.assertEqual(b.linkage_status.iloc[0], "SOURCE_CONFLICT")

    def test_row_order_is_not_time(self):
        rows = [("A", "B", HA, HB, True), ("A", "B", HC, HB, False), ("B", "A", HB, HA, False)]
        a = self.link(self.wz(rows)).set_index("wzry_row_hash")
        b = self.link(self.wz(rows[::-1])).set_index("wzry_row_hash")
        cols = ["linkage_status", "game_key", "candidate_count"]
        pd.testing.assert_frame_equal(a[cols].sort_index(), b.loc[a.index, cols].sort_index())

    def test_unresolved_team_identity(self):
        out = self.link(self.wz([("A", "ZZZ", HA, HB, True)]))
        self.assertEqual(out.linkage_status.iloc[0], "UNRESOLVED_TEAM_IDENTITY")
        self.assertIsNone(out.game_key.iloc[0])


class ImmutabilityTest(unittest.TestCase):
    @unittest.skipUnless(LOCK_A.exists(), "Phase A lock missing")
    def test_original_wzry_byte_identical(self):
        lock = json.loads(LOCK_A.read_text())
        entry = next(a for a in lock["artifacts"] if a["path"] == WZRY_PATH)
        self.assertEqual(baseline.sha256_file(ROOT / WZRY_PATH), entry["sha256"])

    @unittest.skipUnless(LOCK_A.exists(), "Phase A lock missing")
    def test_v03_benchmark_artifacts_byte_identical(self):
        lock = json.loads(LOCK_A.read_text())
        bench = [a for a in lock["artifacts"] if a["path"].startswith(("reports/benchmark", "data/processed/temporal"))]
        self.assertGreaterEqual(len(bench), 10)
        self.assertEqual(baseline.check_lock({"artifacts": bench}, ROOT), [])

    @unittest.skipUnless(LOCK_B.exists(), "Phase B lock missing")
    def test_phase_b_lock(self):
        self.assertEqual(baseline.check_lock(json.loads(LOCK_B.read_text()), ROOT), [])


class RotationTest(unittest.TestCase):
    def test_continuity_formula(self):
        l1, l2 = frozenset("abcde"), frozenset("abcdf")
        self.assertEqual(players.continuity_score([l1, l1, l1]), 1.0)
        self.assertAlmostEqual(players.continuity_score([l1, l2, l1]), (0.8 + 1.0) / 2)


if __name__ == "__main__":
    unittest.main()
