"""Human-reviewable team identity registry.

The audit only ever adds UNREVIEWED rows for newly observed names. Existing
rows (which may carry human review) are never modified or removed.
"""
from pathlib import Path

import pandas as pd

REGISTRY_COLUMNS = [
    "observed_name", "canonical_team_id", "canonical_name", "valid_from", "valid_to",
    "identity_type", "continuity_status", "confidence", "evidence_type", "evidence_url",
    "evidence_note", "review_status",
]
IDENTITY_TYPES = {"EXACT", "CITY_RENAME", "BRAND_RENAME", "SPONSOR_RENAME", "ORG_RENAME", "SLOT_TRANSFER",
                  "SOURCE_ALIAS", "UNKNOWN"}
CONTINUITY_STATUSES = {"SAME_COMPETITIVE_ENTITY", "DIFFERENT_ENTITY", "UNCERTAIN"}
REVIEW_STATUSES = {"UNREVIEWED", "VERIFIED", "REJECTED"}


def unreviewed_row(name):
    return {
        "observed_name": name, "canonical_team_id": "", "canonical_name": "",
        "valid_from": "", "valid_to": "", "identity_type": "UNKNOWN",
        "continuity_status": "UNCERTAIN", "confidence": "", "evidence_type": "",
        "evidence_url": "", "evidence_note": "", "review_status": "UNREVIEWED",
    }


def build_empty_registry(observed_names):
    return pd.DataFrame([unreviewed_row(n) for n in sorted(observed_names)], columns=REGISTRY_COLUMNS)


def read_registry(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def merge_registry(existing, observed_names):
    """Append UNREVIEWED rows for names not yet registered. Returns (registry, added_names)."""
    have = set(existing.observed_name)
    added = sorted(n for n in set(observed_names) if n not in have)
    if not added:
        return existing[REGISTRY_COLUMNS].copy(), []
    out = pd.concat([existing[REGISTRY_COLUMNS], build_empty_registry(added)], ignore_index=True)
    return out, added


def validate_registry(reg):
    problems = []
    missing = [c for c in REGISTRY_COLUMNS if c not in reg.columns]
    if missing:
        return [f"missing columns: {missing}"]
    for col, allowed in [("identity_type", IDENTITY_TYPES), ("continuity_status", CONTINUITY_STATUSES),
                         ("review_status", REVIEW_STATUSES)]:
        bad = sorted(set(reg[col]) - allowed)
        if bad:
            problems.append(f"{col} has disallowed values: {bad}")
    dup = reg.observed_name[reg.observed_name.duplicated()].tolist()
    if dup:
        problems.append(f"duplicate observed_name rows: {dup}")
    unreviewed_with_canon = reg[(reg.review_status == "UNREVIEWED") & (reg.canonical_team_id != "")]
    if len(unreviewed_with_canon):
        problems.append(f"UNREVIEWED rows with canonical_team_id: {unreviewed_with_canon.observed_name.tolist()}")
    return problems


def write_or_update_registry(path: Path, observed_names):
    """Create the registry if absent; otherwise only append new names. Returns (registry, added, created)."""
    path = Path(path)
    if path.exists():
        reg, added = merge_registry(read_registry(path), observed_names)
        created = False
    else:
        reg, added, created = build_empty_registry(observed_names), sorted(set(observed_names)), True
    if created or added:
        path.parent.mkdir(parents=True, exist_ok=True)
        reg.to_csv(path, index=False, encoding="utf-8-sig")
    return reg, added, created
