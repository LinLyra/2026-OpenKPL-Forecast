"""Transition-candidate generation and coexistence checks.

Candidates are triage only. `transition_score` ranks pairs for external review;
it never establishes identity continuity. String similarity is used to FIND
candidates, never to decide them.
"""
import re
from difflib import SequenceMatcher

import pandas as pd

BOUNDARY_MAX_GAP_DAYS = 270   # an off-season plus a skipped annual-finals season
NAMED_MAX_GAP_DAYS = 540      # similar names may return after a longer absence
STRONG_SIMILARITY = 0.6

_LATIN = re.compile(r"[A-Za-z]{2,}")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def latin_tokens(name):
    return {t.casefold() for t in _LATIN.findall(name)}


def _longest_common_cjk(a, b):
    best = ""
    for ra in _CJK_RUN.findall(a):
        for rb in _CJK_RUN.findall(b):
            m = SequenceMatcher(None, ra, rb, autojunk=False).find_longest_match(0, len(ra), 0, len(rb))
            if m.size > len(best):
                best = ra[m.a:m.a + m.size]
    return best


def name_features(a, b):
    """Descriptive name-comparison features. Names are compared casefolded; raw values are untouched."""
    sim = SequenceMatcher(None, a.casefold(), b.casefold(), autojunk=False).ratio()
    shared_latin = sorted(latin_tokens(a) & latin_tokens(b))
    cjk = _longest_common_cjk(a, b)
    prefix_only = len(cjk) == 2 and a.startswith(cjk) and b.startswith(cjk)
    cjk_core = cjk if len(cjk) >= 2 and not prefix_only else ""
    return {
        "string_similarity": round(sim, 6),
        "shared_latin_tokens": "|".join(shared_latin),
        "shared_cjk_substring": cjk if len(cjk) >= 2 else "",
        "shared_prefix_only": prefix_only and not shared_latin,
        # Whole shared tokens only; raw similarity is noisy on 3-letter tags (e.g. MTG vs TCG).
        "strong_name_evidence": bool(shared_latin) or bool(cjk_core),
        "similar_string_flag": sim >= STRONG_SIMILARITY,
    }


def _name_strength(f):
    if f["shared_latin_tokens"]:
        return 1.0
    s = min(f["string_similarity"], 0.5)
    if f["shared_cjk_substring"] and not f["shared_prefix_only"]:
        s = max(s, 0.8)
    if f["shared_prefix_only"]:
        s = max(s, 0.3)
    return s


def transition_score(features, gap_days, shared_ratio):
    """Triage score in [0, 1]. Ranking aid only; never evidence of identity."""
    gap_score = max(0.0, 1.0 - gap_days / NAMED_MAX_GAP_DAYS) if gap_days > 0 else 0.0
    disjoint = 1.0 if gap_days > 0 else 0.0
    return round(0.45 * _name_strength(features) + 0.25 * gap_score + 0.15 * shared_ratio + 0.15 * disjoint, 4)


def generate_candidates(appearances, inventory, season_order):
    """Candidate (old, new) pairs, old = earlier first_seen.

    Included when:
      BOUNDARY_WITHIN_270D              old stops, new starts <= 270 days later
      SIMILAR_NAME_AFTER_DISAPPEARANCE  strong name evidence, new starts <= 540 days after old stops
      SIMILAR_NAME_COEXISTING           strong name evidence or similarity >= 0.6, active periods overlap

    Strong name evidence = a shared whole Latin token or a shared non-city-prefix CJK substring.
    """
    inv = inventory.set_index("observed_team_name")
    names = sorted(inv.index, key=lambda n: (inv.loc[n, "first_seen"], n))
    rows = []
    for i, old in enumerate(names):
        for new in names[i + 1:]:
            o, n = inv.loc[old], inv.loc[new]
            gap = (n.first_seen - o.last_seen).total_seconds() / 86400.0
            f = name_features(old, new)
            reasons = []
            if 0 < gap <= BOUNDARY_MAX_GAP_DAYS:
                reasons.append("BOUNDARY_WITHIN_270D")
            if f["strong_name_evidence"] and 0 < gap <= NAMED_MAX_GAP_DAYS:
                reasons.append("SIMILAR_NAME_AFTER_DISAPPEARANCE")
            if (f["strong_name_evidence"] or f["similar_string_flag"]) and gap <= 0:
                reasons.append("SIMILAR_NAME_COEXISTING")
            if not reasons:
                continue
            old_last = appearances[(appearances.team == old) & (appearances.season == o.last_season)]
            new_first = appearances[(appearances.team == new) & (appearances.season == n.first_season)]
            opp_old = set(old_last.opponent) - {old, new}
            opp_new = set(new_first.opponent) - {old, new}
            shared = opp_old & opp_new
            denom = min(len(opp_old), len(opp_new))
            ratio = len(shared) / denom if denom else 0.0
            rows.append({
                "old_name": old, "new_name": new,
                "old_last_seen": o.last_seen, "new_first_seen": n.first_seen,
                "days_between": round(gap, 2),
                "old_last_season": o.last_season, "new_first_season": n.first_season,
                "season_index_gap": season_order[n.first_season] - season_order[o.last_season],
                "string_similarity": f["string_similarity"],
                "shared_latin_tokens": f["shared_latin_tokens"],
                "shared_cjk_substring": f["shared_cjk_substring"],
                "shared_prefix_only": f["shared_prefix_only"],
                "strong_name_evidence": f["strong_name_evidence"],
                "similar_string_flag": f["similar_string_flag"],
                "shared_opponents_before_after": len(shared),
                "shared_opponent_ratio": round(ratio, 6),
                "old_recent_series_count": len(old_last),
                "new_early_series_count": len(new_first),
                "transition_score": transition_score(f, gap, ratio),
                "candidate_reason": "|".join(reasons),
                "score_is_triage_only": True,
                "review_required": True,
            })
    cols = ["old_name", "new_name", "old_last_seen", "new_first_seen", "days_between", "old_last_season",
            "new_first_season", "season_index_gap", "string_similarity", "shared_latin_tokens",
            "shared_cjk_substring", "shared_prefix_only", "strong_name_evidence", "similar_string_flag",
            "shared_opponents_before_after", "shared_opponent_ratio", "old_recent_series_count",
            "new_early_series_count", "transition_score", "candidate_reason", "score_is_triage_only",
            "review_required"]
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values(["transition_score", "old_name", "new_name"], ascending=[False, True, True],
                           kind="stable").reset_index(drop=True)


def overlap_checks(appearances, series, candidates, season_order):
    """Coexistence evidence per candidate. Any coexistence sets identity_conflict_flag."""
    rows = []
    for c in candidates.itertuples(index=False):
        a = appearances[appearances.team == c.old_name]
        b = appearances[appearances.team == c.new_name]
        same_season = bool(set(a.season) & set(b.season))
        overlap = bool(a.start_time.min() <= b.start_time.max() and b.start_time.min() <= a.start_time.max())
        played = bool(((series.team_a == c.old_name) & (series.team_b == c.new_name)).any()
                      or ((series.team_a == c.new_name) & (series.team_b == c.old_name)).any())
        same_day = bool(set(a.start_time.dt.date) & set(b.start_time.dt.date))
        gap = season_order[c.new_first_season] - season_order[c.old_last_season]
        adjacent = gap in (0, 1) and not overlap
        reasons = [r for r, v in [("PLAYED_EACH_OTHER", played), ("SAME_DAY_PRESENCE", same_day),
                                  ("DATE_RANGES_OVERLAP", overlap)] if v]
        rows.append({
            "old_name": c.old_name, "new_name": c.new_name,
            "same_season": same_season, "date_ranges_overlap": overlap,
            "played_each_other": played, "same_day_presence": same_day,
            "adjacent_transition": adjacent,
            "mid_season_change": same_season and not overlap,
            "identity_conflict_flag": bool(reasons),
            "conflict_reasons": "|".join(reasons),
        })
    return pd.DataFrame(rows, columns=["old_name", "new_name", "same_season", "date_ranges_overlap",
                                       "played_each_other", "same_day_presence", "adjacent_transition",
                                       "mid_season_change", "identity_conflict_flag", "conflict_reasons"])


def candidate_chains(candidates, overlap):
    """Maximal A -> B -> C paths over non-conflicting candidates with strong name evidence.

    A chain is a hypothesis for review, not an identity.
    """
    m = candidates.merge(overlap[["old_name", "new_name", "identity_conflict_flag"]], on=["old_name", "new_name"])
    m = m[m.strong_name_evidence & ~m.identity_conflict_flag & (m.days_between > 0)]
    edges = {}
    for r in m.itertuples(index=False):
        edges.setdefault(r.old_name, []).append(r.new_name)
    targets = {t for v in edges.values() for t in v}
    chains = []

    def walk(path):
        nxt = sorted(edges.get(path[-1], []))
        if not nxt:
            if len(path) >= 3:
                chains.append(path)
            return
        for n in nxt:
            if n not in path:
                walk(path + [n])

    for start in sorted(set(edges) - targets):
        walk([start])
    return sorted(chains)
