"""Write-once raw store for v0.4 roster/game discovery.

Every response is written byte-for-byte with an exclusive-create mode and
recorded in an append-only JSONL manifest (one line per request) with the
request, retrieval time, HTTP status, SHA256 and discovery evidence. An
existing response file is never overwritten.
"""
import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from openkpl.refresh.snapshot import HEADERS

MANIFEST = "MANIFEST.jsonl"


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120]


def requests_transport(method, url, payload=None, timeout=25):
    import requests
    if method == "POST":
        r = requests.post(url, headers=HEADERS, json=payload, timeout=timeout)
    else:
        r = requests.get(url, headers={k: v for k, v in HEADERS.items() if k != "Content-Type"}, timeout=timeout)
    return r.status_code, dict(r.headers), r.content


class RawStore:
    def __init__(self, root, transport=requests_transport, pause=0.8):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.transport, self.pause = transport, pause
        self._lock = threading.Lock()

    def entries(self):
        p = self.root / MANIFEST
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    def fetch(self, name, method, url, payload=None, discovery="", source_ids=None, ext="json"):
        fname = f"{safe_name(name)}.{ext}"
        path = self.root / fname
        if path.exists():
            raise FileExistsError(f"{path} already exists; raw responses are never overwritten")
        retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        try:
            status, headers, body = self.transport(method, url, payload)
            error = None
        except Exception as e:  # recorded, never hidden
            status, headers, body, error = None, {}, b"", f"{type(e).__name__}: {e}"
        with open(path, "xb") as f:
            f.write(body)
        entry = {"name": name, "file": fname, "method": method, "url": url, "payload": payload,
                 "request_headers": HEADERS if method == "POST" else {k: v for k, v in HEADERS.items() if k != "Content-Type"},
                 "retrieved_at": retrieved, "http_status": status, "error": error,
                 "content_type": headers.get("Content-Type") or headers.get("content-type"),
                 "bytes": len(body), "sha256": sha256_bytes(body), "discovery": discovery,
                 "source_ids": source_ids or {}}
        with self._lock, open(self.root / MANIFEST, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if self.pause:
            time.sleep(self.pause)
        return body, entry

    def load(self, verify=True):
        out = {}
        for e in self.entries():
            b = (self.root / e["file"]).read_bytes()
            if verify and sha256_bytes(b) != e["sha256"]:
                raise ValueError(f"hash mismatch for {e['file']}: raw response was modified")
            out[e["name"]] = (b, e)
        return out
