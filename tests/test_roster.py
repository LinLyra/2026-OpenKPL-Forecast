import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from openkpl.roster import baseline, collect, parse, wzry_link
from openkpl.roster.audit import display_handle
from openkpl.roster.raw_store import RawStore, sha256_bytes

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "reports/roster_audit/baseline_lock.json"
HEROES_A, HEROES_B = [101, 102, 103, 104, 105], [201, 202, 203, 204, 205]


def _detail(sid="KPL2026S1M1W1D1", rounds=2, players=True, winner=True, drop_player=False, pos=True):
    a = [{"playerid": f"a{i}", "team_id": "KPL2026S1_a", "player_name": f"A.p{i}", "player_name_short": f"p{i}",
          "player_name_real": f"ra{i}", "position": i} for i in range(1, 6)]
    b = [{"playerid": f"b{i}", "team_id": "KPL2026S1_b", "player_name": f"B.q{i}", "player_name_short": f"q{i}",
          "player_name_real": f"rb{i}", "position": i} for i in range(1, 6)]
    rds = []
    for r in range(1, rounds + 1):
        ps = [{"playerid": p["playerid"], "position": p["position"] if pos else 0, "hero_id": h, "hero_name": f"h{h}", "vid": ""}
              for p, h in zip(a + b, HEROES_A + HEROES_B)] if players else []
        if drop_player:
            ps = ps[:-1]
        rds.append({"round": r, "win_team": "KPL2026S1_a" if winner else "", "win_team_name": "A" if winner else "",
                    "vid": "v", "players": ps})
    return json.dumps({"result": 0, "msg": "", "data": {"title": sid, "players": a + b if players else [],
                                                        "round_details": rds}}).encode()


def _fake_transport(bodies):
    calls = []

    def t(method, url, payload=None):
        calls.append((method, url, payload))
        return 200, {"Content-Type": "application/json"}, bodies.pop(0)
    t.calls = calls
    return t


class RawPreservationTest(unittest.TestCase):
    def test_write_once_manifest_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as d:
            st = RawStore(d, transport=_fake_transport([b'{"result":0}', b'{"result":1}']), pause=0)
            body, e = st.fetch("x", "POST", "https://example/kplow/getScheduleDetail", {"seasonid": "S"},
                               discovery="test", source_ids={"seasonid": "S"})
            self.assertEqual(e["sha256"], sha256_bytes(body))
            self.assertEqual((Path(d) / "x.json").read_bytes(), b'{"result":0}')
            with self.assertRaises(FileExistsError):
                st.fetch("x", "POST", "https://example/kplow/getScheduleDetail")
            self.assertEqual((Path(d) / "x.json").read_bytes(), b'{"result":0}')
            self.assertEqual(len(st.entries()), 1)
            (Path(d) / "x.json").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                st.load(verify=True)

    def test_transport_error_is_recorded_not_hidden(self):
        def boom(method, url, payload=None):
            raise ConnectionError("refused")
        with tempfile.TemporaryDirectory() as d:
            _, e = RawStore(d, transport=boom, pause=0).fetch("y", "POST", "u")
            self.assertIsNone(e["http_status"])
            self.assertIn("refused", e["error"])

    def test_collect_skips_existing_and_uses_site_payload(self):
        with tempfile.TemporaryDirectory() as d:
            t = _fake_transport([_detail(), _detail()])
            st = RawStore(d, transport=t, pause=0)
            jobs = collect.schedule_detail_jobs([("KPL2026S1", "KPL2026S1M1W1D1")])
            self.assertEqual(collect.collect(st, jobs, workers=1)[0][1], 200)
            self.assertEqual(collect.collect(st, jobs, workers=1)[0][1], "SKIPPED_EXISTS")
            self.assertEqual(t.calls[0][2], {"seasonid": "KPL2026S1", "scheduleid": "KPL2026S1M1W1D1"})
            self.assertEqual(len(t.calls), 1)


class ParsingTest(unittest.TestCase):
    def test_stable_parsing(self):
        body = _detail(rounds=3)
        first, second = parse.parse_schedule_detail("S1", body), parse.parse_schedule_detail("S1", body)
        self.assertEqual(first, second)
        sp, games, gp = first
        self.assertEqual((len(sp), len(games), len(gp)), (10, 3, 30))
        self.assertEqual({r["team_slot"] for r in gp if r["playerid"].startswith("a")}, {"KPL2026S1_a"})
        self.assertEqual(games[0]["win_team_slot"], "KPL2026S1_a")

    def test_empty_schema_kept_empty(self):
        sp, games, gp = parse.parse_schedule_detail("S0", _detail(players=False, winner=False))
        self.assertEqual((len(sp), len(games), len(gp)), (0, 2, 0))
        self.assertEqual(games[0]["win_team_slot"], "")
        self.assertEqual(games[0]["n_players"], 0)

    def test_combo_matches(self):
        body = json.dumps({"result": 0, "data": [{"team_id": "T1", "matches": [{
            "battle_id": "1782972301_1_2", "schedule_id": "S1", "schedule_date": "2026-07-02", "match_num": 1,
            "rival_team_id": "T2", "schedule_result": 1, "bp_picks_left": [{"hero_id": 1, "order": 6}],
            "bp_picks_right": [{"hero_id": 2, "order": 5}], "kill_left": 3, "kill_right": 1, "duration": 900}]}]})
        rows = parse.parse_combo_matches("S", "1,2", body)
        self.assertEqual(rows[0]["picks_left"], ((1, 6),))
        self.assertEqual(rows[0]["scheduleid"], "S1")

    def test_display_handle_exact_prefix_only(self):
        self.assertEqual(display_handle("杭州LGD.NBW.断雨", {"杭州LGD", "杭州LGD.NBW"}), "断雨")
        self.assertEqual(display_handle("西安WE.百兽（房庆友）", "西安WE"), "百兽")
        self.assertEqual(display_handle("上海EDGM.柠栀", "上海EDG.M"), "上海EDGM.柠栀")


class LinkageAndValidationTest(unittest.TestCase):
    def test_game_series_linkage(self):
        games = [{"scheduleid": "S1", "round": 1}, {"scheduleid": "S1", "round": 2}, {"scheduleid": "SX", "round": 1}]
        self.assertEqual(parse.link_games(games, ["S1", "S2"]),
                         {"games_total": 3, "games_with_parent_series": 2, "orphan_games": 1})

    def test_lineup_validation(self):
        _, _, gp = parse.parse_schedule_detail("S", _detail(rounds=1))
        self.assertEqual(parse.validate_lineup(gp), [])
        _, _, gp9 = parse.parse_schedule_detail("S", _detail(rounds=1, drop_player=True))
        self.assertIn("PLAYER_COUNT_9", parse.validate_lineup(gp9))
        self.assertIn("NOT_5V5", parse.validate_lineup(gp9))
        _, _, gp0 = parse.parse_schedule_detail("S", _detail(rounds=1, pos=False))
        self.assertIn("POSITION_UNLABELED", parse.validate_lineup(gp0))
        self.assertEqual(parse.validate_lineup([]), ["NO_LINEUP"])

    def test_player_uniqueness(self):
        _, _, gp = parse.parse_schedule_detail("S", _detail(rounds=1))
        gp[1] = dict(gp[1], playerid=gp[0]["playerid"])
        self.assertIn("DUPLICATE_PLAYER_IN_GAME", parse.validate_lineup(gp))
        gp2 = [dict(r) for r in parse.parse_schedule_detail("S", _detail(rounds=1))[2]]
        gp2[5]["hero_id"] = gp2[0]["hero_id"]
        self.assertIn("DUPLICATE_HERO_IN_GAME", parse.validate_lineup(gp2))

    def test_duplicate_id_detection(self):
        df = pd.DataFrame({"battle_id": ["b1", "b1", "b2"], "scheduleid": ["S1", "S2", "S1"], "match_num": [1, 1, 2]})
        self.assertEqual(list(parse.duplicate_ids(df, "battle_id", ["scheduleid", "match_num"]).index), ["b1"])


class WzryFingerprintTest(unittest.TestCase):
    CANON = {"A": "TEAM_A", "B": "TEAM_B", "C": "TEAM_C"}

    @staticmethod
    def rec(t1, t2, h1, h2, winner="", **extra):
        return dict(team1=t1, team2=t2, winner=winner, heroes1=frozenset(h1), heroes2=frozenset(h2), **extra)

    def test_unique_multiple_none_and_untestable(self):
        H1, H2, H3 = "abcde", "fghij", "klmno"
        right = pd.DataFrame([
            self.rec("A", "B", H1, H2, "A", scheduleid="S1", round=1),
            self.rec("A", "B", H1, H3, "B", scheduleid="S1", round=2),
            self.rec("A", "B", H1, H3, "B", scheduleid="S2", round=1),
        ])
        left = pd.DataFrame([
            self.rec("B", "A", H2, H1, "A", wzry_row=0),
            self.rec("A", "B", H1, H3, "B", wzry_row=1),
            self.rec("A", "C", H1, H2, "A", wzry_row=2),
            self.rec("A", "Z", H1, H2, "A", wzry_row=3),
        ])
        r = wzry_link.match_counts(left, right, "F3_pair_team_heroes", self.CANON)
        self.assertEqual((r["sample_rows_tested"], r["unique_exact_match"], r["multiple_matches"], r["no_match"]), (3, 1, 1, 1))
        pair = wzry_link.match_counts(left, right, "F1_team_pair", self.CANON)
        self.assertEqual(pair["unique_exact_match"], 0)
        self.assertEqual(pair["multiple_matches"], 2)
        pairs = wzry_link.matched_pairs(left, right, "F3_pair_team_heroes", self.CANON)
        self.assertEqual(pairs.set_index("wzry_row").candidate.to_dict(), {0: "S1#1", 1: "", 2: "", 3: ""})

    def test_side_assignment_matters(self):
        right = pd.DataFrame([self.rec("A", "B", "abcde", "fghij", scheduleid="S", round=1)])
        swapped = pd.DataFrame([self.rec("A", "B", "fghij", "abcde", wzry_row=0)])
        self.assertEqual(wzry_link.match_counts(swapped, right, "F2_pair_hero10", self.CANON)["unique_exact_match"], 1)
        self.assertEqual(wzry_link.match_counts(swapped, right, "F3_pair_team_heroes", self.CANON)["no_match"], 1)

    def test_wzry_parsing(self):
        bp = [{"team": "A", "hero": h, "equiplist": [], "position": "x"} for h in "abcde"] + \
             [{"team": "B", "hero": h, "equiplist": [], "position": "x"} for h in "fghij"]
        df = pd.DataFrame([{"team1": "A", "team1_win": True, "team2": "B", "team2_win": False,
                            "battle_process": repr(bp), "BP_process": "[]"}])
        g = wzry_link.wzry_games(df).iloc[0]
        self.assertEqual((g.winner, g.heroes1, g.heroes2), ("A", frozenset("abcde"), frozenset("fghij")))


class BaselineLockTest(unittest.TestCase):
    def test_check_lock_detects_change(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.csv"
            p.write_text("a\n1\n")
            lock = {"artifacts": [{"path": "f.csv", "sha256": baseline.sha256_file(p)}]}
            self.assertEqual(baseline.check_lock(lock, d), [])
            p.write_text("a\n2\n")
            self.assertEqual(baseline.check_lock(lock, d), ["f.csv"])

    @unittest.skipUnless(LOCK.exists(), "baseline lock not generated")
    def test_validated_v03_artifacts_unchanged(self):
        lock = json.loads(LOCK.read_text())
        self.assertEqual(baseline.check_lock(lock, ROOT), [])
        self.assertEqual(lock["state"]["completed_series"], 1466)
        self.assertEqual(lock["state"]["KPL2026_annual_finals_completed"], 0)


if __name__ == "__main__":
    unittest.main()
