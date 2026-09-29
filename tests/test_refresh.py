import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from openkpl.evaluation.benchmark import sha256_file
from openkpl.identity.registry import build_empty_registry
from openkpl.refresh.audit import build_diff, canonicalize_staging, decide
from openkpl.refresh.merge import MergeRefusedError, mask_prospective, merge_refresh
from openkpl.refresh.normalize import duplicate_source_ids, normalize_schedules
from openkpl.refresh.snapshot import Snapshot, SnapshotExistsError, load_snapshot, take_snapshot
from openkpl.transform.canonical import build_canonical_series

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT = pd.Timestamp("2026-09-28")
RETRIEVED = "2026-09-28T10:00:00Z"
REAL_SNAPSHOT = ROOT / "data/raw/snapshots/2026-09-28"


def _epoch(utc8):
    return int((pd.Timestamp(utc8) - pd.Timedelta(hours=8)).timestamp())


def _rec(sid, when, a, b, sa, sb, status=4, season="KPL2026S1", stage="常规赛", stageid="cgs1", a_id=None, b_id=None):
    return {"scheduleid": sid, "seasonid": season, "stageid": stageid, "stage_name": stage,
            "start_timestamp": _epoch(when), "team_a_id": a_id or f"{season}_{a}", "team_a_name": a,
            "team_a_group": "", "team_a_score": sa, "team_a_logo": "", "team_b_id": b_id or f"{season}_{b}",
            "team_b_name": b, "team_b_group": "", "team_b_score": sb, "team_b_logo": "", "bo_total": 5,
            "schedule_status": status, "competition_format": 1, "location_name": "0", "arenas": ""}


def _fake_source(schedules):
    """schedules: {seasonid: [records]}; any other season is 'season not found'."""
    def transport(url, payload):
        endpoint = url.rsplit("/", 1)[1]
        if endpoint == "getSeasonAndStageAndTeamList" and payload.get("seasonid") == "":
            j = {"result": 0, "msg": "", "data": {"seasons": [{"seasonid": s, "season_name": s} for s in schedules]}}
        elif endpoint == "getScheduleList":
            sid = payload["seasonid"]
            j = ({"result": 0, "msg": "", "data": {"list": schedules[sid]}} if sid in schedules
                 else {"result": 10010001, "msg": "season not found"})
        elif endpoint == "getKVConfig":
            j = {"result": 0, "msg": "", "data": {"config": {}}}
        else:
            j = {"result": 0, "msg": "", "data": {}}
        return 200, {"Content-Type": "application/json"}, json.dumps(j, ensure_ascii=False).encode("utf-8")
    return transport


BASE = {"KPL2026S1": [_rec("S1", "2026-01-15 17:00:00", "北京JDG", "无锡TCG", 3, 1),
                      _rec("S2", "2026-01-16 17:00:00", "无锡TCG", "北京JDG", 3, 2),
                      _rec("S3", "2026-01-17 17:00:00", "北京JDG", "无锡TCG", 0, 0, status=1)]}


def _registry(names):
    r = build_empty_registry(names)
    r["canonical_team_id"] = ["T_" + n for n in r.observed_name]
    r["canonical_name"] = r.canonical_team_id
    r["review_status"] = "VERIFIED"
    r["continuity_status"] = "SAME_COMPETITIVE_ENTITY"
    return r


def _snapshot(tmp, schedules=BASE, date="2026-09-28"):
    take_snapshot(tmp, date, transport=_fake_source(schedules), pause=0)
    return load_snapshot(Path(tmp) / date)


def _staging(schedules=BASE):
    with tempfile.TemporaryDirectory() as d:
        _, bodies = _snapshot(d, schedules)
        return normalize_schedules(bodies)[0]


class RefreshTests(unittest.TestCase):
    def test_01_raw_snapshot_files_are_write_once(self):
        with tempfile.TemporaryDirectory() as d:
            snap = Snapshot(d, "2026-09-28", transport=_fake_source(BASE), pause=0)
            body, meta = snap.fetch("season_list", "getSeasonAndStageAndTeamList", {"seasonid": ""})
            path = snap.root / meta["response_file"]
            self.assertEqual(path.read_bytes(), body)
            with self.assertRaises(FileExistsError):
                with open(path, "xb") as f:
                    f.write(b"tampered")
            snap.write_manifest()
            with self.assertRaises(FileExistsError):
                snap.write_manifest()
            self.assertEqual(path.read_bytes(), body)

    def test_02_snapshot_hashes_detect_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            manifest, bodies = _snapshot(d)
            for name, (b, meta) in bodies.items():
                self.assertEqual(hashlib.sha256(b).hexdigest(), meta["sha256"])
                self.assertEqual(manifest["sha256"][meta["response_file"]], meta["sha256"])
            target = Path(d) / "2026-09-28" / bodies["schedule_KPL2026S1"][1]["response_file"]
            target.chmod(0o644)
            target.write_bytes(target.read_bytes().replace("北京JDG".encode(), "北京XXX".encode()))
            with self.assertRaises(ValueError):
                load_snapshot(Path(d) / "2026-09-28")

    def test_03_scheduled_match_cannot_become_label(self):
        recs = {"KPL2026S1": BASE["KPL2026S1"] + [_rec("S4", "2026-01-18 17:00:00", "北京JDG", "无锡TCG", 2, 1, status=1)]}
        st = _staging(recs)
        sched = st[st.status != 4]
        self.assertTrue(sched.score_a.isna().all() and sched.score_b.isna().all())
        self.assertIn("NONZERO_SCORE_BEFORE_COMPLETION", st.set_index("source_series_id").loc["S4", "data_quality_flag"])
        self.assertEqual(int(st.set_index("source_series_id").loc["S4", "source_score_a"]), 2)
        canon, _, checks = canonicalize_staging(st, _registry(["北京JDG", "无锡TCG"]), RETRIEVED, HOLDOUT)
        c = canon.set_index("series_id")
        self.assertFalse(c.loc["S3", "is_label_eligible"])
        self.assertFalse(c.loc["S4", "is_label_eligible"])
        self.assertTrue(c.loc["S1", "is_label_eligible"])
        self.assertTrue(checks["no_label_from_status_not_4"])

    def test_04_duplicate_source_series_id_is_rejected(self):
        recs = {"KPL2026S1": BASE["KPL2026S1"] + [_rec("S1", "2026-01-19 17:00:00", "北京JDG", "无锡TCG", 3, 0)]}
        st = _staging(recs)
        self.assertEqual(duplicate_source_ids(st), ["S1"])
        _, audit, checks = canonicalize_staging(st, _registry(["北京JDG", "无锡TCG"]), RETRIEVED, HOLDOUT)
        self.assertFalse(checks["no_duplicate_source_series_id"])
        gate = decide(pd.DataFrame({"api_result": [0]}),
                      pd.DataFrame({"season": ["KPL2026S1", "KPL2026S2"], "stage_id": ["cgs1", "cgs1"],
                                    "coverage_status": ["COMPLETE", "COMPLETE"]}),
                      pd.DataFrame({"diff_class": ["EXACT_EXISTING"]}), st, audit, checks)
        self.assertFalse(gate["merge_allowed"])

    def test_05_source_result_conflicts_are_flagged(self):
        st = _staging({"KPL2026S1": [
            _rec("E1", "2026-01-15 17:00:00", "A", "B", 3, 1),   # exact
            _rec("E2", "2026-01-16 17:00:00", "A", "B", 3, 2),   # score changed
            _rec("E3", "2026-01-17 17:00:00", "A", "C", 3, 0),   # team changed
            _rec("E4", "2026-01-18 18:00:00", "A", "B", 3, 0),   # time changed
            _rec("E5", "2026-01-19 17:00:00", "A", "B", 0, 0, status=1),  # completed result retracted
            _rec("E7", "2026-01-20 17:00:00", "A", "B", 3, 1),   # was scheduled, now completed
            _rec("N1", "2026-01-21 17:00:00", "A", "B", 3, 1),   # new
        ]})
        ex = pd.DataFrame([("E1", "2026-01-15 17:00:00", "A", "B", 3, 1, 4), ("E2", "2026-01-16 17:00:00", "A", "B", 3, 1, 4),
                           ("E3", "2026-01-17 17:00:00", "A", "B", 3, 0, 4), ("E4", "2026-01-18 17:00:00", "A", "B", 3, 0, 4),
                           ("E5", "2026-01-19 17:00:00", "A", "B", 3, 2, 4), ("E6", "2026-01-19 20:00:00", "A", "B", 3, 2, 4),
                           ("E7", "2026-01-20 17:00:00", "A", "B", 0, 0, 1)],
                          columns=["series_id", "start_time_raw", "team_a", "team_b", "score_a", "score_b", "status"])
        ex["season"], ex["stage"] = "KPL2026S1", "常规赛"
        d = build_diff(st, ex)
        cls = dict(zip(d.source_series_id.where(d.source_series_id != "", d.existing_series_id), d.diff_class))
        self.assertEqual(cls, {"E1": "EXACT_EXISTING", "E2": "SCORE_CONFLICT", "E3": "TEAM_NAME_CONFLICT",
                               "E4": "DATE_CONFLICT", "E5": "SCORE_CONFLICT", "E6": "UNMATCHED",
                               "E7": "RESULT_UPDATED", "N1": "NEW_SERIES"})
        _, audit, checks = canonicalize_staging(st, _registry(["A", "B", "C"]), RETRIEVED, HOLDOUT)
        gate = decide(pd.DataFrame({"api_result": [0]}),
                      pd.DataFrame({"season": ["KPL2026S1", "KPL2026S2"], "stage_id": ["cgs1", "cgs1"],
                                    "coverage_status": ["COMPLETE", "COMPLETE"]}), d, st, audit, checks)
        self.assertFalse(gate["merge_allowed"])
        self.assertTrue(any("blocking diff" in b for b in gate["merge_blockers"]))

    def test_06_new_team_name_is_not_silently_canonicalized(self):
        recs = {"KPL2026S2": [_rec("X1", "2026-06-18 17:00:00", "北京JDG", "SYG", 3, 1, season="KPL2026S2",
                                   b_id="KPL2026S2_tcg")]}  # even a predecessor-looking slot id is not used to alias
        st = _staging(recs)
        reg = _registry(["北京JDG", "无锡TCG"])
        before = reg.copy()
        canon, audit, checks = canonicalize_staging(st, reg, RETRIEVED, HOLDOUT)
        row = canon.iloc[0]
        self.assertNotEqual(row.identity_resolution_status, "RESOLVED")
        self.assertTrue(pd.isna(row.canonical_team_b_id))
        self.assertFalse(row.is_label_eligible)
        self.assertEqual(audit["unresolved_series"], 1)
        pd.testing.assert_frame_equal(reg, before)
        self.assertNotIn("SYG", set(reg.observed_name))

    def test_07_annual_finals_outcomes_cannot_enter_development(self):
        future = _rec("AF1", "2026-10-03 17:00:00", "北京JDG", "无锡TCG", 4, 2, season="KPL2026S3", stage="年度总决赛")
        st = _staging({**BASE, "KPL2026S3": [future]})
        reg = _registry(["北京JDG", "无锡TCG"])
        _, _, checks = canonicalize_staging(st, reg, RETRIEVED, HOLDOUT)
        self.assertFalse(checks["no_label_at_or_after_prospective_holdout_start"])
        self.assertFalse(checks["no_completed_result_after_retrieval_time"])
        from openkpl.refresh.audit import staging_as_series
        masked = mask_prospective(staging_as_series(st).drop(columns=["stage_id_src"]), HOLDOUT)
        m = masked.set_index("series_id")
        self.assertTrue(pd.isna(m.loc["AF1", "score_a"]) and pd.isna(m.loc["AF1", "score_b"]))
        self.assertEqual(m.loc["AF1", "label_flag"], "PROSPECTIVE_SCHEDULED")
        canon, _, _ = build_canonical_series(masked, reg)
        self.assertFalse(canon.set_index("series_id").loc["AF1", "is_label_eligible"])
        self.assertFalse((canon[canon.is_label_eligible].start_time >= HOLDOUT).any())
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(MergeRefusedError):
                merge_refresh(None, st, reg, None, {"merge_allowed": False, "decision": "X", "merge_blockers": []},
                              Path(d) / "v", None, HOLDOUT)
            Path(d, "v").mkdir()
            with self.assertRaises(MergeRefusedError):
                merge_refresh(None, st, reg, None, {"merge_allowed": True}, Path(d) / "v", None, HOLDOUT)

    def test_08_refresh_cannot_overwrite_historical_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            _snapshot(d)
            f = Path(d) / "2026-09-28" / "original_api" / "002_schedule_KPL2026S1.json"
            original = f.read_bytes()
            changed = {"KPL2026S1": BASE["KPL2026S1"][:1]}
            with self.assertRaises(SnapshotExistsError):
                take_snapshot(d, "2026-09-28", transport=_fake_source(changed), pause=0)
            self.assertEqual(f.read_bytes(), original)
            take_snapshot(d, "2026-09-29", transport=_fake_source(changed), pause=0)
            self.assertEqual(f.read_bytes(), original)
        if REAL_SNAPSHOT.exists():
            manifest, bodies = load_snapshot(REAL_SNAPSHOT)
            self.assertEqual(len(bodies), len(manifest["requests"]))

    def test_09_benchmark_code_and_historical_dataset_unchanged(self):
        fixture = json.loads((ROOT / "tests/fixtures/benchmark_code_sha256.json").read_text(encoding="utf-8"))
        for rel, digest in fixture["files"].items():
            self.assertEqual(sha256_file(ROOT / rel), digest, f"benchmark code changed: {rel}")
        manifest = json.loads((ROOT / "reports/benchmark/benchmark_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(sha256_file(ROOT / "data/processed/temporal/canonical_series.parquet"),
                         manifest["canonical_series_hash"])

    def test_10_same_snapshot_gives_deterministic_normalized_output(self):
        with tempfile.TemporaryDirectory() as d:
            _, bodies = _snapshot(d)
            a, sa = normalize_schedules(bodies)
            b, sb = normalize_schedules(dict(reversed(list(bodies.items()))))
            _, bodies2 = load_snapshot(Path(d) / "2026-09-28")
            c, _ = normalize_schedules(bodies2)
        pd.testing.assert_frame_equal(a, b)
        pd.testing.assert_frame_equal(a, c)
        pd.testing.assert_frame_equal(sa, sb)
        ba, bc = io.BytesIO(), io.BytesIO()
        a.to_parquet(ba, index=False)
        c.to_parquet(bc, index=False)
        self.assertEqual(hashlib.sha256(ba.getvalue()).hexdigest(), hashlib.sha256(bc.getvalue()).hexdigest())


REGISTRY = ROOT / "data/dimensions/team_identity_registry.csv"
VERSION_DIR = ROOT / "data/processed/temporal/v2026_09_28"
VERSION_BENCH = ROOT / "reports/benchmark/v2026_09_28"


def _series_rows(rows):
    df = pd.DataFrame(rows, columns=["series_id", "season", "start_time", "team_a", "team_b", "score_a", "score_b", "status"])
    df["start_time_raw"] = df.start_time
    df["start_time"] = pd.to_datetime(df.start_time)
    df["stage"] = "常规赛第一轮"
    df["label_flag"] = "COMPLETED"
    df["start_time_is_epoch_fallback"] = False
    return df


class TemporarySeatIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from openkpl.identity.registry import read_registry
        cls.reg = read_registry(REGISTRY)
        cls.series = _series_rows([
            ("T1", "KPL2026S1", "2026-01-15 17:00:00", "无锡TCG", "桐乡情久", 3, 1, 4),
            ("T2", "KPL2026S1", "2026-01-16 17:00:00", "桐乡情久", "北京JDG", 3, 2, 4),
            ("T3", "KPL2026S1", "2026-01-17 17:00:00", "北京JDG", "无锡TCG", 3, 0, 4),
            ("T4", "KPL2026S2", "2026-06-18 17:00:00", "SYG", "北京JDG", 3, 1, 4),
            ("T5", "KPL2026S2", "2026-06-19 17:00:00", "WST", "SYG", 3, 2, 4),
            ("T6", "KPL2026S2", "2026-06-20 17:00:00", "北京JDG", "WST", 3, 0, 4),
        ])
        cls.canon, cls.audit, cls.checks = build_canonical_series(cls.series, cls.reg)

    def _ids(self, raw):
        c = self.canon
        return set(c.canonical_team_a_id[c.raw_team_a == raw]) | set(c.canonical_team_b_id[c.raw_team_b == raw])

    def test_syg_resolves_to_team_syg(self):
        self.assertEqual(self._ids("SYG"), {"TEAM_SYG"})
        self.assertEqual(sorted(self.reg.observed_name[self.reg.canonical_team_id == "TEAM_SYG"]), ["SYG"])

    def test_wst_resolves_to_team_wst(self):
        self.assertEqual(self._ids("WST"), {"TEAM_WST"})
        self.assertEqual(sorted(self.reg.observed_name[self.reg.canonical_team_id == "TEAM_WST"]), ["WST"])

    def test_syg_and_wst_are_different_entities(self):
        self.assertNotEqual(self._ids("SYG"), self._ids("WST"))
        t5 = self.canon.set_index("series_id").loc["T5"]
        self.assertNotEqual(t5.canonical_team_a_id, t5.canonical_team_b_id)
        self.assertTrue(t5.is_label_eligible)
        self.assertTrue(self.checks["no_self_play_after_canonicalization"])
        self.assertEqual(self.audit["unresolved_series"] + self.audit["conflicted_series"], 0)

    def test_temporary_seat_succession_is_not_identity_continuity(self):
        from openkpl.identity.membership import build_membership, slot_predecessors
        from openkpl.identity.reviewed_membership import REVIEWED_MEMBERSHIP, apply_reviewed_membership
        for new in ["TEAM_SYG", "TEAM_WST"]:
            for old in ["TEAM_TCG", "TEAM_QINGJIU"]:
                self.assertNotEqual(new, old)
                self.assertFalse(set(self.reg.observed_name[self.reg.canonical_team_id == new]) &
                                 set(self.reg.observed_name[self.reg.canonical_team_id == old]))
        m = apply_reviewed_membership(build_membership(self.canon, self.reg))
        rows = m[(m.season == "KPL2026S2") & m.canonical_team_id.isin(["TEAM_SYG", "TEAM_WST"])].set_index("canonical_team_id")
        self.assertEqual(set(rows.index), {"TEAM_SYG", "TEAM_WST"})
        self.assertTrue((rows.slot_type == "TEMPORARY").all())
        self.assertTrue((rows.continuity_type == "NEW_ENTRY").all())
        self.assertTrue((rows.predecessor_team_id == "").all())
        self.assertFalse({"TEAM_SYG", "TEAM_WST"} & set(slot_predecessors(m)))
        bad = [{**REVIEWED_MEMBERSHIP[0], "predecessor_team_id": "TEAM_TCG"}]
        with self.assertRaises(ValueError):
            apply_reviewed_membership(build_membership(self.canon, self.reg), bad)

    @unittest.skipUnless((VERSION_BENCH / "temporal_predictions.parquet").exists(), "refreshed benchmark not run")
    def test_refreshed_benchmark_includes_completed_summer(self):
        c = pd.read_parquet(VERSION_DIR / "canonical_series.parquet")
        self.assertEqual(int(c[(c.season == "KPL2026S2") & c.is_label_eligible].shape[0]), 136)
        self.assertEqual(int(c[(c.season == "KPL2026S1") & c.is_label_eligible].shape[0]), 136)
        p = pd.read_parquet(VERSION_BENCH / "temporal_predictions.parquet")
        dev = p[p.is_development & (p.season == "KPL2026S2")]
        self.assertEqual(dev.groupby("model_id").size().to_dict(), {m: 136 for m in ["B0", "B1", "B2", "B3", "B4", "B5"]})
        folds = pd.read_csv(VERSION_BENCH / "temporal_folds.csv", encoding="utf-8-sig")
        self.assertIn("KPL2026S2", set(folds.validation_season))

    @unittest.skipUnless((VERSION_BENCH / "temporal_predictions.parquet").exists(), "refreshed benchmark not run")
    def test_annual_finals_remain_excluded(self):
        s = pd.read_parquet(VERSION_DIR / "series.parquet")
        c = pd.read_parquet(VERSION_DIR / "canonical_series.parquet")
        self.assertFalse(s.season.eq("KPL2026S3").any())
        self.assertFalse((c[c.is_label_eligible].start_time >= HOLDOUT).any())
        p = pd.read_parquet(VERSION_BENCH / "temporal_predictions.parquet")
        self.assertFalse((p.is_development & (p.start_time >= HOLDOUT)).any())
        self.assertFalse(p.season.eq("KPL2026S3").any())
        manifest = json.loads((VERSION_BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["prospective_holdout_labeled_rows_present"], 0)


if __name__ == "__main__":
    unittest.main()
