"""League membership / slot layer (v0.3 Phase B).

Team identity (who a team is) and league-slot continuity (whose place a team
took) are different concepts. This table records season membership per
canonical team and only the continuity facts supported by reviewed evidence.
It is metadata for optional experiments and never changes canonical IDs or the
B0-B5 ratings.

Derivation rules (applied per season, per canonical team):
- first season in source coverage: entry/continuity UNKNOWN (2020-2021 missing);
- canonical team present in the previous league season: TEAM_CONTINUITY, with
  entry RENAME when the observed name changed via a verified *_RENAME row,
  otherwise EXISTING (a SOURCE_ALIAS change is not a rename);
- a reviewed slot event: SLOT_CONTINUITY_ONLY / SLOT_ACQUISITION;
- otherwise entry UNKNOWN; continuity TEAM_CONTINUITY if the verified canonical
  team was seen in an earlier season, else UNKNOWN.
slot_type and qualification_method are never inferred.
"""
from pathlib import Path

import pandas as pd

MEMBERSHIP_COLUMNS = [
    "season", "canonical_team_id", "canonical_name", "observed_name", "slot_type", "entry_type",
    "predecessor_team_id", "continuity_type", "qualification_method", "evidence_status", "notes",
]
SLOT_TYPES = {"FIXED", "TEMPORARY", "UNKNOWN"}
ENTRY_TYPES = {"EXISTING", "QUALIFIER", "KGL_DIRECT", "SLOT_ACQUISITION", "RENAME", "UNKNOWN"}
CONTINUITY_TYPES = {"TEAM_CONTINUITY", "SLOT_CONTINUITY_ONLY", "NEW_ENTRY", "UNKNOWN"}
RENAME_TYPES = {"CITY_RENAME", "BRAND_RENAME", "SPONSOR_RENAME", "ORG_RENAME"}

REVIEWED_SLOT_EVENTS = [
    {"season": "KPL2024S2", "canonical_team_id": "TEAM_JDG", "predecessor_team_id": "TEAM_VG",
     "evidence_status": "REVIEWER_STATED_NO_SOURCE_URL",
     "notes": "北京JDG entered by acquiring the 厦门VG league slot. Slot continuity only: TEAM_JDG and TEAM_VG "
              "are different competitive entities."},
]


def _season_members(canonical):
    long = pd.concat([
        canonical[["season", "start_time", "canonical_team_a_id", "raw_team_a"]].set_axis(["season", "t", "cid", "raw"], axis=1),
        canonical[["season", "start_time", "canonical_team_b_id", "raw_team_b"]].set_axis(["season", "t", "cid", "raw"], axis=1),
    ]).dropna(subset=["cid"])
    order = long.groupby("season").t.min().sort_values(kind="stable").index.tolist()
    names = long.sort_values("t", kind="stable").groupby(["season", "cid"]).raw.agg(lambda s: "|".join(dict.fromkeys(s)))
    return order, names


def build_membership(canonical, registry, slot_events=REVIEWED_SLOT_EVENTS):
    order, names = _season_members(canonical)
    teams = {s: set(names.loc[s].index) for s in order}
    n_max = max(len(v) for v in teams.values())
    league = [s for s in order if len(teams[s]) == n_max]
    reg = registry.set_index("observed_name")
    id_to_name = dict(zip(registry.canonical_team_id, registry.canonical_name))
    events = {(e["season"], e["canonical_team_id"]): e for e in slot_events}
    rows, seen = [], set()
    for s in order:
        prior_league = [x for x in league if order.index(x) < order.index(s)]
        prev = prior_league[-1] if prior_league else None
        for cid in sorted(teams[s]):
            obs = names.loc[(s, cid)]
            row = {"season": s, "canonical_team_id": cid, "canonical_name": id_to_name.get(cid, ""),
                   "observed_name": obs, "slot_type": "UNKNOWN", "entry_type": "UNKNOWN", "predecessor_team_id": "",
                   "continuity_type": "UNKNOWN", "qualification_method": "", "evidence_status": "UNREVIEWED", "notes": ""}
            ev = events.get((s, cid))
            if prev is None:
                row["notes"] = "First season in source coverage (2020-2021 not covered); entry unknown."
            elif cid in teams[prev]:
                prev_names = set(names.loc[(prev, cid)].split("|"))
                cur_names = obs.split("|")
                types = {reg.loc[n, "identity_type"] for n in cur_names if n not in prev_names and n in reg.index}
                row["continuity_type"] = "TEAM_CONTINUITY"
                row["evidence_status"] = "DERIVED_FROM_VERIFIED_IDENTITY"
                if types & RENAME_TYPES:
                    row["entry_type"] = "RENAME"
                    row["notes"] = f"Observed name changed from {'|'.join(sorted(prev_names))} ({'|'.join(sorted(types))})."
                else:
                    row["entry_type"] = "EXISTING"
                    if "SOURCE_ALIAS" in types:
                        row["notes"] = "Observed name differs only by a SOURCE_ALIAS; not a verified rename."
            elif ev is not None:
                row.update(entry_type="SLOT_ACQUISITION", continuity_type="SLOT_CONTINUITY_ONLY",
                           predecessor_team_id=ev["predecessor_team_id"], evidence_status=ev["evidence_status"],
                           notes=ev["notes"])
            elif cid in seen:
                row["continuity_type"] = "TEAM_CONTINUITY"
                row["evidence_status"] = "DERIVED_FROM_VERIFIED_IDENTITY"
                row["notes"] = f"Absent from previous league season {prev}; how it re-entered is not reviewed."
            else:
                row["notes"] = "First appearance in source coverage; entry route not reviewed."
            rows.append(row)
        seen |= teams[s]
    return pd.DataFrame(rows, columns=MEMBERSHIP_COLUMNS)


def validate_membership(m):
    problems = []
    for col, allowed in [("slot_type", SLOT_TYPES), ("entry_type", ENTRY_TYPES), ("continuity_type", CONTINUITY_TYPES)]:
        bad = sorted(set(m[col]) - allowed)
        if bad:
            problems.append(f"{col} has disallowed values: {bad}")
    if m.duplicated(["season", "canonical_team_id"]).any():
        problems.append("duplicate (season, canonical_team_id) rows")
    slot = m[m.continuity_type == "SLOT_CONTINUITY_ONLY"]
    if (slot.predecessor_team_id == slot.canonical_team_id).any():
        problems.append("slot continuity row names itself as predecessor")
    return problems


def read_membership(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def write_membership_if_absent(path: Path, canonical, registry):
    """Create the membership table once. An existing (possibly hand-edited) table is kept and only validated."""
    path = Path(path)
    if path.exists():
        return read_membership(path), False
    m = build_membership(canonical, registry)
    path.parent.mkdir(parents=True, exist_ok=True)
    m.to_csv(path, index=False, encoding="utf-8-sig")
    return m, True


def slot_predecessors(membership):
    """{new_team_id: predecessor_team_id} for reviewed slot-continuity rows (for the optional E_SLOT experiment)."""
    s = membership[(membership.continuity_type == "SLOT_CONTINUITY_ONLY") & (membership.predecessor_team_id != "")]
    return dict(zip(s.canonical_team_id, s.predecessor_team_id))
