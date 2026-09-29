# HoK-BP-LLM forensic audit: lineage of `WZRY.csv`

Audit date: 2026-09-28. Raw files under `data/raw/external/` were read only. `WZRY.csv` was not rewritten.

Labels used below:

- **VERIFIED**: measured from files in this workspace, or from the git history of `data/raw/external/HoK-BP-LLM`.
- **INFERENCE**: a conclusion that the files do not state directly.

Machine-readable outputs:

- `reports/audit/hok_bp_sequence_profile.csv` — one row per `WZRY.csv` data row (5,586 rows). `row_index` is the 0-based data-row index.
- `reports/audit/hok_bp_field_inventory.csv` — columns, nested keys, text-search hits, and keyword hits elsewhere in the repo.

Parsing of `BP_process` and `battle_process` used `ast.literal_eval` only.

## 1. What the checkout actually contains

**VERIFIED.** `data/raw/external/HoK-BP-LLM` is a git checkout of `https://github.com/YuWangyin/HoK-BP-LLM.git`. Ignoring `.git`, the tree is data and READMEs only. There is no Python, SQL, notebook, or Excel file. Git history from the initial commit (`ddb8415`, 2024-03-26, YuWangyin) through `f0d9955` (2024-04-09) never adds a `.py` file.

| Path | What it is | Commit |
| --- | --- | --- |
| `王者荣耀KPL历年比赛数据/WZRY.csv` | 5,586-row match table, GB18030 | `5ca05a5`, 2024-03-31, shenfei, message `提交KPL比赛数据，并添加了字段说明与README文件` |
| `王者荣耀KPL历年比赛数据/README.md` plus one screenshot | Field notes for that CSV | same commit; screenshot added in `18a4fbb` |
| `crawler_data/` | 1 CSV of guide prose, 25 JPEGs, a one-line README | `816c880`, 2024-04-01, ScapperEthen, message `王者阵营爬取的数据` |
| `王者荣耀攻略/WZtrick.jsonl` | 148 Zhihu guide records | `ec2fb15`, 2024-04-03, shenfei |
| Root `README.md` | Project plan for an LLM BP assistant | YuWangyin, later edited by HongCheng |

**VERIFIED.** `WZRY.csv` enters the repository already finished: the adding commit inserts 5,587 lines (header plus 5,586 records) and no generator. Later commits do not modify the CSV.

**INFERENCE.** A script outside this repository produced the CSV, then someone committed the result. This checkout cannot name that script, its source URL, or any columns it dropped.

The root README says the first action is “爬虫收集lpl对局阵容信息” and then points at the KPL CSV. **VERIFIED** wording mismatch: the sentence says LPL; the folder title and README say KPL. No LPL file is in the tree.

## 2. File format of `WZRY.csv`

**VERIFIED.**

- Size 14,432,015 bytes. 5,586 data rows, 6 columns, LF line endings, no UTF-8 BOM.
- The full file decodes as GB18030 and as GBK. UTF-8 fails at byte `0xc9` (position 58), which is the first byte of 深 in 深圳DYG.
- Header: `team1,team1_win,team2,team2_win,battle_process,BP_process`.
- No blank cells in any column.
- Nested cells are Python literal syntax (single quotes, lists, dicts). They are not JSON. `json.loads` is not how they were parsed for this audit. Every one of the 5,586 `BP_process` values and every one of the 5,586 `battle_process` values parses with `ast.literal_eval` into a list of dicts.
- Win cells are the unquoted CSV tokens `TRUE` and `FALSE`.

The dataset README names the columns `team_1`, `team_2`, `team_1_win`, `team_2_win`. **VERIFIED** the file and the bundled screenshot use `team1`, `team2`, `team1_win`, `team2_win` with no underscore. The README’s row count, 5,586, matches the file. Its printed `battle_process` / `BP_process` example matches data row 0 (深圳DYG vs 上海RNG.M).

The README states the games run from 2020 through March 2024. **VERIFIED** that sentence is only in the README. The CSV contains no year token `2015`–`2026` and no `YYYY-MM` or `YYYY年M` pattern.

## 3. Lineage

### Generator

**VERIFIED.** No script in `HoK-BP-LLM` generates `WZRY.csv`. The file is a committed artifact.

**VERIFIED.** The only KPL crawler in the wider OpenKPL-Analytics workspace is `data/raw/external/PythonMajor-assignment`. It is a different pipeline:

- It POSTs `https://kplshop-op.timi-esports.qq.com/kplow/getScheduleList` (`src/config.py`, `src/crawler.py`).
- It stores one row per scheduled series in `kpl_matches`: `id` (from `scheduleid`), `season` (`seasonid`), `stage` (`stage_name`), `match_time` (from `start_timestamp`), `team_a`, `team_b`, `score_a`, `score_b`, `status`, `update_time`.
- It never writes drafts, heroes, equipment, or per-game rows.

**INFERENCE.** That schedule endpoint is the wrong shape to be the source of `WZRY.csv`. The crawler’s code never reads ban, pick, hero, or equipment fields. If the JSON response contains extra keys, those keys are not persisted. This audit did not capture a live response, so the unused keys are not listed here.

### Upstream fields that might have been discarded

**VERIFIED** absence inside `WZRY.csv`, after decoding as GB18030 and parsing both nested columns:

| Candidate | In `WZRY.csv` |
| --- | --- |
| `match_id`, `game_id`, `scheduleid`, `seasonid` | absent as columns, dict keys, and raw tokens |
| date, time, season, stage, tournament, patch, version | absent |
| player, nickname, 选手, 昵称 | absent |
| kills, deaths, assists, gold, damage, and the Chinese 击杀 / 死亡 / 助攻 / 经济 / 金币 / 伤害 | absent |
| series number, game number, blue/red side | absent |

**VERIFIED.** Nested keys are closed:

- `BP_process` dicts have only `team`, `ban_or_pick`, `hero` (100,531 events, each key present on every event).
- `battle_process` dicts have only `team`, `hero`, `equiplist`, `position` (55,860 events, each key present on every event).

**INFERENCE.** Because the producer script is not in the repo, this audit cannot show that `match_id`, date, season, stage, or game number existed upstream and were then dropped. It can show that they are not recoverable from `WZRY.csv` or from any sibling file in `HoK-BP-LLM`.

`crawler_data` and `WZtrick.jsonl` were committed on different days by different authors and do not contain a row key that joins to `WZRY.csv`. They are not an upstream layer of the CSV.

## 4. `crawler_data`

**VERIFIED.**

- `README.md` is the single heading `# crawler数据集`.
- `text_content.csv` is UTF-8 (CRLF), one column `Text`, 310 data rows, 1 of them empty. The text is hero-guide prose (the file opens with a 米莱狄 guide, then moves on to 上官婉儿). It is not a match table. Non-zero keyword hits are prose: 英雄 47, 伤害 47, 版本 13, 时间 12, 经济 9, 赛季 5, 阶段 5, 选手 2, 击杀 2. No `match_id`, `game_id`, date column, or BP record.
- 25 JPEGs. `image_3.jpg`, `image_6.jpg`, `image_11.jpg`, and `image_13.jpg` are byte-identical (8,472 bytes, same SHA-256).
- Two images were opened for this audit. `image_0.jpg` is a 王者营地 banner (稷下学社 / 王者Alex). `pvp_picture_picture1.jpg` is a 王者荣耀 hero guide poster for 艾琳 (skills, combos, emblems, items). The remaining JPEGs were not OCR’d. Filenames and the commit message classify the folder as a camp/guide scrape, not a match dump.

**INFERENCE.** `text_content.csv` is paragraph text extracted from the same guide pages as the images. Nothing in the folder reconstructs a KPL game.

## 5. Semantics of the four nested / win fields

### `team1_win` and `team2_win`

**VERIFIED.**

- Tokens are only `TRUE` and `FALSE`.
- 2,815 rows are `TRUE|FALSE`. 2,771 rows are `FALSE|TRUE`.
- Zero rows have both true, both false, or any other token.
- `team1` never equals `team2`.
- On all 5,586 rows, the first dict in `BP_process` has `team` equal to `team1`.

So `team1_win` is a boolean win flag for the team stored in `team1`, and `team2_win` is the complementary flag for `team2`. The flags are mutually exclusive and exhaustive in this file: every row has one winner.

**INFERENCE.** `team1` is the side that acts first in the stored BP list. The file does not say whether that side is blue, red, or the higher seed. Do not treat `team1` as “blue side” without another source.

### `BP_process`

**VERIFIED.** A list, in stored order, of `{team, ban_or_pick, hero}`.

- `ban_or_pick` takes only `ban` (44,674) and `pick` (55,857).
- Every `team` value on a row is either that row’s `team1` or `team2` (0 rows with an outside team).
- The dataset README says this list is in BP order. The dominant shape matches that claim: 5,579 / 5,586 rows are `4B-6P-4B-4P` (four bans, six picks, four bans, four picks), length 18.
- Zero rows ban and pick the same hero. Zero rows pick the same hero twice.
- 23 events have an empty `hero` string. All 23 are bans, on 23 different rows. Empty heroes were excluded from unique-hero counts.

**INFERENCE.** The `4B-6P-4B-4P` shape is the global-ban era draft (phase-1 bans, first pick phase, phase-2 bans, second pick phase). The file itself does not name the rule version. The seven shorter rows are incomplete records of that same shape, not a second legal format: they still have 10 heroes in `battle_process`.

### `battle_process`

**VERIFIED.** A list of `{team, hero, equiplist, position}`. The README says the list is not in BP order, and that it records the hero, item list, and position for the 10 participants.

Measured:

- Every row has exactly 10 dicts.
- On 5,584 rows the set of `pick` heroes equals the set of `battle_process` heroes. The only mismatches are row 869 (9 picks; the battle list is those 9 plus 牛魔) and row 1731 (8 picks; the battle list is those 8 plus 元歌 and 蒙犽).
- Pick order equals battle order on 0 of 5,586 rows. The README’s “not in BP order” claim holds for every row.
- `equiplist` is present on all 55,860 hero entries, always a non-empty list of item-name strings. Lengths: 6 items on 52,643 heroes, 5 on 2,910, 4 on 285, 3 on 21, 2 on 1.
- `position` values: 游走 13,922, 打野 10,758, 对抗路 10,738, 中路 10,308, 发育路 9,826, `未知` 286, empty string 22. These sum to 55,860.
- A strict role split (each of the two teams has each of 对抗路, 打野, 中路, 发育路, 游走 exactly once) holds on 3,007 rows and fails on 2,579 rows. 144 rows contain at least one `未知`. 18 rows contain at least one blank position. There are 145 distinct position multisets.

**INFERENCE.** `position` was intended as a lane label, but on almost half the rows it is not a clean 5-role assignment. Duplicate lanes and `未知` are in the data. Treat position as a noisy label.

### Players, KDA, gold, damage

**VERIFIED.** No player name, player id, nickname, kill, death, assist, gold, or damage field exists in either nested structure or in the raw CSV text. Equipment is item names only.

## 6. Distributions

All figures are **VERIFIED** from the `ast.literal_eval` parse.

### BP sequence length

| Length | Rows |
| --- | ---: |
| 18 | 5,579 |
| 17 | 1 |
| 16 | 2 |
| 15 | 4 |

### Bans per row

| Bans | Rows |
| --- | ---: |
| 8 | 5,580 |
| 7 | 2 |
| 5 | 4 |

### Picks per row

| Picks | Rows |
| --- | ---: |
| 10 | 5,584 |
| 9 | 1 |
| 8 | 1 |

### Action signatures (run length)

| Signature | Rows |
| --- | ---: |
| `4B-6P-4B-4P` | 5,579 |
| `3B-6P-2B-4P` | 4 |
| `4B-6P-3B-4P` | 1 |
| `4B-6P-3B-3P` | 1 |
| `4B-6P-4B-2P` | 1 |

Rows that are not length 18:

| row_index | teams | team1_win | bans | picks | signature | pick set vs battle |
| ---: | --- | --- | ---: | ---: | --- | --- |
| 103 | 长沙TES.A vs 南京Hero久竞 | FALSE | 5 | 10 | `3B-6P-2B-4P` | equal |
| 869 | 西安WE vs 上海EDG.M | TRUE | 7 | 9 | `4B-6P-3B-3P` | unequal |
| 1731 | 广州TTG vs 重庆狼队 | FALSE | 8 | 8 | `4B-6P-4B-2P` | unequal |
| 1779 | 济南RW侠 vs 长沙TES.A | FALSE | 5 | 10 | `3B-6P-2B-4P` | equal |
| 2118 | 上海RNG.M vs 北京WB | FALSE | 5 | 10 | `3B-6P-2B-4P` | equal |
| 2746 | 广州TTG vs 武汉eStarPro | TRUE | 7 | 10 | `4B-6P-3B-4P` | equal |
| 4698 | 深圳DYG vs 成都AG超玩会 | FALSE | 5 | 10 | `3B-6P-2B-4P` | equal |

The per-row `bp_signature` column in the sequence CSV is the ungrouped `B`/`P` string, for example `BBBBPPPPPPBBBBPPPP`.

### Heroes and teams

| Quantity | Count |
| --- | ---: |
| Distinct non-empty heroes in ban or pick events | 118 |
| Distinct picked heroes | 117 |
| Distinct non-empty banned heroes | 112, plus 23 bans whose hero string is empty |
| Distinct battle heroes | 117 |
| Heroes in BP but never in `battle_process` | 阿轲 only (2 ban events) |
| Heroes in `battle_process` but never in BP | none |
| Distinct teams on either side | 45 |
| `team1` uniques | 42 |
| `team2` uniques | 45 |

Most frequent teams by side-appearance (a team is counted once per row it plays): 广州TTG 778, 重庆狼队 767, 佛山DRG 752, 武汉eStarPro 718, 成都AG超玩会 708, 北京WB 705, 深圳DYG 642, 长沙TES.A 632, 南京Hero久竞 613, 杭州LGD.NBW 606. The long tail includes short-lived or non-league names (喵鱼 63, BOA 58, 东莞Wz 51, 斗鱼XHW 22, 虎牙小当家 16, and several names with fewer than 15 games). Full counts are in the audit run; the sequence CSV carries the team on every row.

Highest BP event counts (bans plus picks): 鲁班大师 4,380, 大乔 4,226, 公孙离 3,691, 沈梦溪 3,386, 镜 2,929.

### Missing, malformed, duplicates

| Check | Result |
| --- | --- |
| Missing `BP_process` | 0 |
| Malformed `BP_process` (`literal_eval` failure, or value not a list of dicts) | 0 |
| Missing `battle_process` | 0 |
| Malformed `battle_process` | 0 |
| Missing nested keys | 0 |
| Exact duplicate rows on all 6 columns | 0 extra rows; 0 rows sit in a duplicate group |
| Duplicate `BP_process` text | 0 |
| Duplicate `battle_process` text | 0 |
| Duplicate `(team1, team2, BP_process)` | 0 |

## 7. `battle_process` checks requested

| Question | VERIFIED result |
| --- | --- |
| Heroes per game | 10 on every row |
| Positions | 中路, 打野, 发育路, 游走, 对抗路, plus `未知` (286) and blank (22). Strict 5-role split on 3,007 / 5,586 rows |
| Equipment | Present and non-empty for all 55,860 hero entries. Mostly 6 items |
| Player names or ids | Not present |
| Kills, deaths, assists, gold, damage | Not present |

## 8. Repository-wide field search

Search scope: text files (`.py`, `.md`, `.csv`, `.json`, `.jsonl`, `.txt`, `.yml`, `.yaml`, `.sql`, `.toml`) outside `.venv`, `.git`, and `reports`. SQLite `kpl_matches` was inspected separately. Latin terms used word boundaries. CJK terms used substring counts.

### Inside `WZRY.csv`

**VERIFIED** hits: the token `hero` occurs 165,583 times. That count mixes the dict key `hero` (100,531 BP events + 55,860 battle events) with the team string `南京Hero久竞`. Every other requested token is 0: `date`, `time`, `match_id`, `game_id`, `season`, `stage`, `tournament`, `player`, `nickname`, `kills`, `deaths`, `assists`, `gold`, `damage`, `patch`, `version`, and the Chinese list in section 3.

### Elsewhere in HoK-BP-LLM

**VERIFIED.** `WZtrick.jsonl` has 148 lines, 0 of which parse as JSON. Each line is a Python-ish `{content: "...", url: '...'}` record. All 148 URLs are Zhihu (`www.zhihu.com` 83, `zhuanlan.zhihu.com` 65). Prose mentions 英雄, 伤害, 击杀, 时间, 经济, 版本, 选手, 赛季. There is no match id and no row that joins to `WZRY.csv`.

### Dated KPL fields that do exist in this workspace

**VERIFIED.** They live only in `PythonMajor-assignment`, not in `WZRY.csv`.

| Location | Fields present |
| --- | --- |
| `kpl_matches` (1,284 rows) | `id`, `season`, `stage`, `match_time`, `team_a`, `team_b`, `score_a`, `score_b`, `status`, `update_time` |
| `src/crawler.py` | reads `scheduleid`, `seasonid`, `stage_name`, `start_timestamp`, team names, scores, `schedule_status` |
| `docs/DATA_DICTIONARY.md` | target schema only (`game_id`, `series_id`, `kills`, `deaths`, `assists`, `gold`, `damage`, `patch`, `player_id`). These columns are not populated from `WZRY.csv` |

`kpl_matches.match_time` ranges from `2022-02-09 15:00:00` to `2026-03-01 20:00:00`. Seasons present: `KPL2022S1` through `KPL2026S1` (no 2020 or 2021). Status counts: 1,239 with status 4, 44 with status 1, 1 with status 3. Stages include 常规赛第一轮/第二轮/第三轮, 季后赛, 擂台赛, 卡位赛, 总决赛.

Keyword `match_id` has 0 hits in the scanned tree. The schedule primary key is column `id`. `nickname` and `tournament` have 0 hits. `game_id` appears only in `docs/DATA_DICTIONARY.md`.

## 9. Can a `WZRY.csv` row be linked to a dated match?

**VERIFIED.** Not from the HoK-BP-LLM files. A row has two team names, two complementary win flags, a draft list, and a lineup/item list. It has no date, season, stage, series id, or game number. Sibling guide files add no key.

**VERIFIED** comparison with `kpl_matches`, after removing whitespace and uppercasing names:

- 45 names appear in `WZRY.csv`. 35 names appear in `kpl_matches`. 21 names are in both.
- 24 `WZRY.csv` names are absent from the schedule table, including 喵鱼, 东莞Wz, 斗鱼XHW, 虎牙小当家, 嵊州SZG, 昆山SC, 镇江VTG, and several short alphabetic tags. BOA is one of the 21 shared names.
- 5,586 rows group into team-pair buckets. 520 rows have a pair that never appears in `kpl_matches`. 258 rows have a pair that appears in exactly one schedule series. 4,808 rows have a pair that appears in more than one series.

A single schedule row is a series (scores such as 3–1), not a game. Even the 258 rows attached to one series still have no game index, so those rows cannot be ordered into game 1..N or given a per-game time. `match_time` is the series timestamp.

The strongest count coincidence, still not an id join: for 2 pairs, the number of `WZRY.csv` rows equals `score_a + score_b` of exactly one schedule series.

| WZRY rows | Schedule id | When | Series | Score |
| ---: | --- | --- | --- | --- |
| 3 | `KPL2024S1M6W2D1` | 2024-03-21 17:00 | KPL2024S1 常规赛第二轮, BOA vs 上海EDG.M | 3–0 |
| 4 | `KPL2024S1M2W5D1` | 2024-02-25 14:00 | KPL2024S1 常规赛第一轮, 重庆狼队 vs BOA | 3–1 |

**INFERENCE.** Those 7 rows are compatible with those two series. They are not verified as those games: `WZRY.csv` has no date to confirm the assignment, and nothing orders the rows inside the series. The other 5,579 rows cannot be attached even at series level without a many-to-many team-pair collision or a name that the schedule table does not contain.

**INFERENCE.** The README’s “2020 through March 2024” window is not testable from the CSV. The schedule database starts in February 2022 and continues into 2026, so it neither covers the claimed start nor stops at the claimed end. Team names such as 情久 are consistent with older KPL branding, but that is not a date.

## 10. What this audit does not support yet

No model was trained. No raw file was edited.

Do not use `WZRY.csv` as a time-aware or leakage-safe match table until a dated game key is joined from another source. The columns that are actually usable now are team identity, a complementary win flag, ordered ban/pick heroes, and a 10-hero lineup with item names. Position is only usable with the missing and duplicate-role rate above.
