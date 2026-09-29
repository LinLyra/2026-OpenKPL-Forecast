"""v0.4 Phase B: collect getScheduleDetail for every validated series not yet stored.

Write-once: failed attempts stay on disk and in the manifest; retries are
separate artifacts named `<name>_retryN`.
"""
import json
import time
from pathlib import Path

import pandas as pd

from openkpl.roster import collect as C
from openkpl.roster.raw_store import RawStore

PHASE_A_STORE = "data/raw/roster_discovery/2026-09-29/api_sample"
PHASE_B_STORE = "data/raw/roster_collection/2026-09-29/schedule_detail"
MAX_RETRIES = 2


def stored_ok(roots):
    """{scheduleid: (root, entry)} for series with an HTTP-200, result-0 detail response."""
    out = {}
    for root in roots:
        st = RawStore(root, transport=None, pause=0)
        for e in st.entries():
            sid = (e.get("source_ids") or {}).get("scheduleid")
            if not sid or e["http_status"] != 200 or "getScheduleDetail" not in e["url"]:
                continue
            try:
                ok = json.loads((Path(root) / e["file"]).read_bytes()).get("result") == 0
            except ValueError:
                ok = False
            if ok:
                out[sid] = (root, e)
    return out


def run(canonical, workers=3):
    have = stored_ok([PHASE_A_STORE, PHASE_B_STORE])
    todo = canonical[~canonical.series_id.isin(have)]
    st = RawStore(PHASE_B_STORE, pause=1.0)
    jobs = [(n, e, p, d.replace("validated temporal dataset", "validated temporal dataset; v0.4 Phase B full collection"), i)
            for n, e, p, d, i in C.schedule_detail_jobs(zip(todo.season, todo.series_id))]
    C.collect(st, jobs, workers=workers)
    for attempt in range(1, MAX_RETRIES + 1):
        have = stored_ok([PHASE_A_STORE, PHASE_B_STORE])
        missing = [j for j in jobs if j[4]["scheduleid"] not in have]
        if not missing:
            break
        time.sleep(5 * attempt)
        retry = [(f"{n}_retry{attempt}", e, p, f"{d}; retry {attempt} after failed attempt", i) for n, e, p, d, i in missing]
        C.collect(st, retry, workers=1)
    return len(todo)


if __name__ == "__main__":
    c = pd.read_parquet("data/processed/temporal/v2026_09_28/canonical_series.parquet")
    print("attempted", run(c))
