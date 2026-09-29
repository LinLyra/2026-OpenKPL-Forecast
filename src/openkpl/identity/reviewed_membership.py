"""Reviewed season-membership facts applied on top of the derived membership table.

build_membership() derives continuity only from the data. Facts that come from
external review (slot type, entry route) are listed here and applied verbatim.
A NEW_ENTRY never carries a predecessor: temporary-seat succession is not identity.
"""
from openkpl.identity.membership import validate_membership

REVIEWED_MEMBERSHIP = [
    {"season": "KPL2026S2", "canonical_team_id": "TEAM_SYG", "slot_type": "TEMPORARY", "entry_type": "QUALIFIER",
     "continuity_type": "NEW_ENTRY", "predecessor_team_id": "", "qualification_method": "",
     "evidence_status": "EXTERNALLY_VERIFIED",
     "notes": "Independent organization; one of the two temporary-seat entrants of 2026 KPL Summer. entry_type "
              "QUALIFIER per reviewer instruction; the qualification route itself is not recorded. Not an alias or "
              "continuation of any KPL team."},
    {"season": "KPL2026S2", "canonical_team_id": "TEAM_WST", "slot_type": "TEMPORARY", "entry_type": "UNKNOWN",
     "continuity_type": "NEW_ENTRY", "predecessor_team_id": "", "qualification_method": "",
     "evidence_status": "EXTERNALLY_VERIFIED",
     "notes": "Independent organization; one of the two temporary-seat entrants of 2026 KPL Summer. Won KGL Spring "
              "2026 (4-3 vs SYG) before KPL Summer, but the evidence does not state that the KGL title was the entry "
              "route, so entry_type stays UNKNOWN (KGL_DIRECT not asserted). Not an alias or continuation of any KPL team."},
]


def apply_reviewed_membership(membership, events=REVIEWED_MEMBERSHIP):
    m = membership.copy()
    for e in events:
        hit = (m.season == e["season"]) & (m.canonical_team_id == e["canonical_team_id"])
        if hit.sum() != 1:
            raise ValueError(f"reviewed membership row not found exactly once: {e['season']} {e['canonical_team_id']}")
        if e["continuity_type"] == "NEW_ENTRY":
            if e["predecessor_team_id"]:
                raise ValueError(f"NEW_ENTRY {e['canonical_team_id']} must not name a predecessor")
            earlier = m[(m.canonical_team_id == e["canonical_team_id"]) & (m.index < m.index[hit][0])]
            if len(earlier):
                raise ValueError(f"NEW_ENTRY {e['canonical_team_id']} already appears in {sorted(set(earlier.season))}")
        for k in ["slot_type", "entry_type", "continuity_type", "predecessor_team_id", "qualification_method",
                  "evidence_status", "notes"]:
            m.loc[hit, k] = e[k]
    problems = validate_membership(m)
    if problems:
        raise ValueError(f"membership invalid after reviewed facts: {problems}")
    return m
