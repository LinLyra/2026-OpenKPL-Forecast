"""Immutable raw snapshots of the original temporal source (v0.3.1).

The source is the endpoint family used by PythonMajor-assignment/src/crawler.py
(POST https://kplshop-op.timi-esports.qq.com/kplow/getScheduleList) plus the
read-only discovery endpoints the official site (kpl.qq.com) itself calls.
Every response body is written byte-for-byte before any parsing, with
exclusive-create file modes, so an existing snapshot can never be overwritten.
"""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import openkpl

SOURCE_NAME = "kplow (kplshop-op.timi-esports.qq.com), original PythonMajor-assignment source"
API_BASE = "https://kplshop-op.timi-esports.qq.com/kplow"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://kpl.qq.com/",
    "Origin": "https://kpl.qq.com",
    "Content-Type": "application/json",
}
KV_CONFIG_IDS = ["kpl_jhs_match", "kpl_js_match", "kpl_season_select_list"]


class SnapshotExistsError(FileExistsError):
    pass


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def requests_transport(url, payload, timeout=20):
    import requests
    r = requests.post(url, headers=HEADERS, json=payload, timeout=timeout)
    return r.status_code, dict(r.headers), r.content


class Snapshot:
    """One dated, write-once snapshot directory."""

    def __init__(self, root, snapshot_date, transport=requests_transport, pause=1.0, git_commit=None):
        self.root = Path(root) / snapshot_date
        self.raw_dir = self.root / "original_api"
        if self.root.exists():
            raise SnapshotExistsError(f"snapshot {self.root} already exists; snapshots are immutable")
        self.raw_dir.mkdir(parents=True)
        self.snapshot_date = snapshot_date
        self.transport, self.pause, self.git_commit = transport, pause, git_commit
        self.requests = []
        self.started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def fetch(self, name, endpoint, payload):
        url = f"{API_BASE}/{endpoint}"
        retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        try:
            status, headers, body = self.transport(url, payload)
            error = None
        except Exception as e:  # recorded, never hidden
            status, headers, body, error = None, {}, b"", f"{type(e).__name__}: {e}"
        fname = f"{len(self.requests):03d}_{name}.json"
        with open(self.raw_dir / fname, "xb") as f:
            f.write(body)
        meta = {"request_index": len(self.requests), "name": name, "endpoint": endpoint, "url": url,
                "http_method": "POST", "query_parameters": payload, "request_headers": HEADERS,
                "retrieved_at": retrieved_at, "http_status": status, "error": error,
                "response_content_type": headers.get("Content-Type") or headers.get("content-type"),
                "response_file": f"original_api/{fname}", "response_bytes": len(body),
                "sha256": sha256_bytes(body)}
        self.requests.append(meta)
        if self.pause:
            time.sleep(self.pause)
        return body, meta

    def write_manifest(self, extra=None):
        manifest = {
            "snapshot_date": self.snapshot_date,
            "retrieved_at": self.started,
            "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_name": SOURCE_NAME,
            "endpoint": f"{API_BASE}/getScheduleList (primary); discovery: getSeasonAndStageAndTeamList, "
                        "getScheduleProgress, getKVConfig",
            "requests": self.requests,
            "response_files": [r["response_file"] for r in self.requests],
            "sha256": {r["response_file"]: r["sha256"] for r in self.requests},
            "code_version": openkpl.__version__,
            "git_commit_if_available": self.git_commit,
            **(extra or {}),
        }
        with open(self.root / "SNAPSHOT_MANIFEST.json", "x", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        return manifest


def _json(body):
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def take_snapshot(root, snapshot_date, transport=requests_transport, pause=1.0, git_commit=None,
                  confirm_absent=("KPL2026S3", "KPL2022S3", "KPL2023S3")):
    """Discover seasons from the source, then fetch schedules, stages, standings and bracket config."""
    snap = Snapshot(root, snapshot_date, transport, pause, git_commit)
    body, _ = snap.fetch("season_list", "getSeasonAndStageAndTeamList", {"seasonid": ""})
    seasons = [s["seasonid"] for s in ((_json(body) or {}).get("data") or {}).get("seasons", [])]
    snap.fetch("kv_config", "getKVConfig", {"configids": KV_CONFIG_IDS})
    for sid in seasons:
        snap.fetch(f"schedule_{sid}", "getScheduleList", {"seasonid": sid, "stageid": "", "team_id": ""})
    for sid in [s for s in seasons if s.startswith("KPL2026")]:
        snap.fetch(f"stages_teams_{sid}", "getSeasonAndStageAndTeamList", {"seasonid": sid})
        snap.fetch(f"progress_{sid}", "getScheduleProgress", {"seasonid": sid})
    for sid in [s for s in confirm_absent if s not in seasons]:
        snap.fetch(f"schedule_{sid}", "getScheduleList", {"seasonid": sid, "stageid": "", "team_id": ""})
    return snap.write_manifest({"discovered_seasons": seasons, "probed_absent_seasons":
                                [s for s in confirm_absent if s not in seasons]})


def load_snapshot(snapshot_dir, verify=True):
    """Read a snapshot manifest and its raw bodies, verifying every SHA256."""
    d = Path(snapshot_dir)
    manifest = json.loads((d / "SNAPSHOT_MANIFEST.json").read_text(encoding="utf-8"))
    bodies = {}
    for r in manifest["requests"]:
        b = (d / r["response_file"]).read_bytes()
        if verify and sha256_bytes(b) != r["sha256"]:
            raise ValueError(f"hash mismatch for {r['response_file']}: raw snapshot was modified")
        bodies[r["name"]] = (b, r)
    return manifest, bodies
