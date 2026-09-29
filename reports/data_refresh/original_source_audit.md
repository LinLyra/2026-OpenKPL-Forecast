# Original temporal source audit (v0.3.1)

Scope: where `data/processed/temporal/series.parquet` came from, why it stops in early 2026, and whether the
same source can refresh it. The original checkout (`data/raw/external/PythonMajor-assignment/`) was read only;
nothing in it was modified. SQLite was opened with `-readonly`.

## 1. Original acquisition path

| Item | Value (verified from the checkout) |
|---|---|
| Code | `PythonMajor-assignment/src/crawler.py`, config in `src/config.py`, entry `main.py` |
| Endpoint | `https://kplshop-op.timi-esports.qq.com/kplow/getScheduleList` (`config.API_URL`) |
| Method | `POST`, JSON body (`session.post(API_URL, headers=HEADERS, json=payload, timeout=10)`, crawler.py:24) |
| Parameters | `{"seasonid": <id>, "stageid": "", "team_id": ""}` (crawler.py:21) |
| Season IDs | Hard-coded, not discovered: `KPL{year}S3`, `S2`, `S1` for `year` in `range(START_YEAR, END_YEAR - 1, -1)` with `START_YEAR = 2026`, `END_YEAR = 2022` (crawler.py:70, config.py) |
| Headers | Desktop Chrome User-Agent, `Referer: https://kpl.qq.com/`, `Origin: https://kpl.qq.com`, `Content-Type: application/json`. No token, cookie, signature or API key. |
| Pacing | `time.sleep(random.uniform(0.5, 1.5))` between seasons; HTTPS retry adapter |
| Storage | SQLite `data/kpl_data.db`, table `kpl_matches(id PK, season, stage, match_time, team_a, team_b, score_a, score_b, status, update_time DEFAULT CURRENT_TIMESTAMP)`, written with `INSERT OR REPLACE` |
| Time field | `match_time = datetime.fromtimestamp(start_timestamp)` (crawler.py:43), i.e. the crawler machine's local time |

Response schema (re-verified 2026-09-28): `{"result": 0, "msg": "", "data": {"list": [...]}}`. Each record carries
`scheduleid, seasonid, stageid, stage_name, start_timestamp (epoch s), team_a_id/name/group/score/logo,
team_b_*, bo_total, schedule_status, competition_format, location_name, round_settle_nums, has_starter_info,
arenas`. `schedule_status` 4 = completed, 1 = scheduled. An unknown season returns HTTP 200 with
`{"result": 10010001, "msg": "season not found"}`; the crawler logs that as "0 rows", not as an error.

## 2. Last run and why the data is stale

- `logs/spider.log` records several runs on **2026-02-04** between 15:31 and 15:40 local time. The last complete
  run is 15:40:10–15:40:31 and ends with `数据库当前状态: 总数据 1284 条 (已完赛 1239 条)`.
- In that run `KPL2026S3` and `KPL2026S2` returned 0 rows (not yet created) and `KPL2026S1` returned 90 rows, of
  which 45 were completed (schedule published through 2026-03-01).
- Database `update_time` spans 2026-02-04 07:40:12–07:40:30 (SQLite `CURRENT_TIMESTAMP`, UTC) for all 1,284
  rows, i.e. the last run rewrote every row.
- **Cause of staleness: the crawler was simply never rerun.** The same endpoint today returns KPL2026S1 complete
  (136 series) and KPL2026S2 complete (136 series). There is no evidence of an API limitation, pagination cut-off or
  access change.

## 3. Timezone

Log time 15:40:12 (local) and SQLite UTC `update_time` 07:40:12 for the same write → the crawler machine ran at
**UTC+8**. So `match_time` in the old DB = `start_timestamp` rendered at UTC+8. The refresh keeps the epoch
(`start_timestamp`) and renders `start_time_raw` at fixed UTC+8, which reproduces all 1,239 previously completed
rows exactly (0 DATE_CONFLICT).

## 4. Read-only discovery endpoints

Found in the official site bundle (`kpl.qq.com/static/index-DLQZLYyn.js`), same host/path family, same headers,
no credentials:

| Endpoint | Body | Returns |
|---|---|---|
| `getSeasonAndStageAndTeamList` | `{"seasonid": ""}` | season list (23 seasons, 2016QJS–2026S2) with names, declared start/end, `season_time_desc` |
| `getSeasonAndStageAndTeamList` | `{"seasonid": id}` | that season's stages and teams |
| `getScheduleProgress` | `{"seasonid": id}` | per-stage standings with groups (used for structural expected counts) |
| `getKVConfig` | `{"configids": ["kpl_jhs_match", "kpl_js_match", "kpl_season_select_list"]}` | playoff bracket schedule IDs, final schedule ID, season-selector names |

All 32 requests of the snapshot returned HTTP 200. Snapshot: `data/raw/snapshots/2026-09-28/`
(`SNAPSHOT_MANIFEST.json`, retrieved 2026-09-28T12:23:42Z–12:25:33Z, one SHA256 per raw body).

## 5. Source metadata conflict (KPL2026S2)

- Season list: `season_name` = "2026年KPL年度总决赛", `season_time_desc` = "10月2日至11月14日", but declared
  start/end = 2026-06-12 / 2026-09-13.
- `kpl_season_select_list` names it "2026KPL夏季赛".
- Schedule content: 136 series, 3 round-robin group stages + 卡位赛 + playoffs + final, 2026-06-17 to 2026-09-12,
  i.e. a Summer season (same structure as KPL2022S2–KPL2025S2).
- Treated as: **KPL2026S2 = 2026 Summer** (content and selector agree); the Annual Finals name/description on the
  season record is recorded as a source metadata conflict, not used. The 2026 Annual Finals have **no published
  schedule** (`KPL2026S3` → "season not found").

## 6. Other observations

- `KPL2022S3` and `KPL2023S3` are absent from the source itself ("season not found", not in the season list); the
  gap in the existing data is a source gap, not a crawl failure.
- 2016QJS–2021S2 (11 seasons, 1,409 completed series) are **available** from the same endpoint but were never
  ingested (`END_YEAR = 2022`). Not merged; outside the benchmark universe.
- The source renamed the playoff stage label "季后赛" → "淘汰赛" for 33 already-stored series (KPL2024S2 11,
  KPL2024S3 9, KPL2025S3 13). Teams, times and scores are identical; it is recorded in `refresh_diff.csv` `detail`
  and is not a conflict.
- `location_name` is "0" (not recorded) for every 2022–2025 series; real cities appear from KPL2026S1.
- 4 KPL2026S2 卡位赛 records have an empty `stage_name` (stage_id `kws` present); kept empty and flagged
  `STAGE_NAME_MISSING`.
- Source `team_id` values are season-scoped slot IDs (e.g. `KPL2026S1_vg` for 北京JDG, `KPL20xxSx_ytg` for
  苏州KSG/KSG). The two new 2026S2 names carry new IDs (`KPL2026S2_syg` for SYG, `KPL2026S2_wst` for WST), not the
  IDs of 无锡TCG (`_tcg`) or 桐乡情久 (`_qj`). IDs are review evidence only; they are not used to create aliases.

## 7. Verdict on the source

The original source works, needs no credentials, and returns KPL2026S1 and KPL2026S2 in full with structural
completeness evidence (standings round-robin counts and bracket schedule-ID lists). It is suitable as the refresh
source; no replacement source is needed.
