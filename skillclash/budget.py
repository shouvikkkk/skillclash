"""Discovery-budget simulation.

Listing format: ``name: description``. Default budget 16,000 characters
(community-reported discovery-stage budget, not an official spec --
see the README caveats). Per-entry cap 1,536 characters: a longer
description is cut at 1,536 and the lost tail is reported.

Ordering assumption (documented, because real invocation-count
ordering is unknown): global estates first in CLI argument order,
then project estates, then unknown-scope estates, alphabetical within
an estate. Skills with ``disable-model-invocation: true`` are excluded
from routing and budget entirely but are still listed in the report.
"""

from __future__ import annotations

from .discovery import LISTING_CAP

DEFAULT_BUDGET = 16000

_SCOPE_ORDER = {"global": 0, "project": 1, "unknown": 2}


def discovery_order(skills):
    """Skills in simulated discovery order (see module docstring)."""
    return sorted(
        skills,
        key=lambda s: (_SCOPE_ORDER.get(s.scope, 2), s.estate, s.dir_name.lower()),
    )


def simulate(skills, budget=DEFAULT_BUDGET):
    """Simulate the discovery listing.

    Returns a dict with the budget limit, the cost of everything that
    fit, the visible/truncated/dropped skill names, and per-skill
    detail. Disabled skills never consume budget and never drop.
    """
    ordered = discovery_order(skills)
    remaining = budget
    visible = []
    truncated = []
    dropped = []
    total_cost = 0
    details = []
    for skill in ordered:
        if skill.disabled:
            details.append(
                {"name": skill.name, "status": "disabled", "cost": 0}
            )
            continue
        cost = skill.entry_cost
        capped = min(cost, LISTING_CAP)
        if cost > LISTING_CAP:
            truncated.append(skill.name)
        if capped > remaining:
            dropped.append(skill.name)
            details.append(
                {"name": skill.name, "status": "dropped", "cost": capped}
            )
            continue
        remaining -= capped
        total_cost += capped
        visible.append(skill.name)
        details.append(
            {"name": skill.name, "status": "truncated" if cost > LISTING_CAP else "visible", "cost": capped}
        )
    return {
        "limit": budget,
        "total_cost": total_cost,
        "visible": visible,
        "truncated": truncated,
        "dropped": dropped,
        "details": details,
    }


def budget_findings(skills, simulation):
    """TRUNCATED and DROPPED findings for one simulation."""
    by_name = {s.name: s for s in skills}
    findings = []
    for name in simulation["truncated"]:
        skill = by_name[name]
        # The listing is "name: description"; the visible description
        # slice is what fits after the name prefix.
        visible_desc_len = max(0, LISTING_CAP - len(skill.name) - 2)
        lost = skill.description[visible_desc_len:]
        findings.append(
            {
                "kind": "TRUNCATED",
                "severity": "medium",
                "skills": [name],
                "evidence": "description of %s is %d chars; listing cuts it at "
                "%d chars. Lost tail starts: %r"
                % (name, len(skill.description), LISTING_CAP, lost[:60]),
                "action": "REWRITE %s: shorten the description to under %d chars, "
                "front-loading trigger keywords" % (name, LISTING_CAP),
            }
        )
    for name in simulation["dropped"]:
        findings.append(
            {
                "kind": "DROPPED",
                "severity": "critical",
                "skills": [name],
                "evidence": "%s does not fit the remaining discovery budget "
                "and is invisible (name-only) in the listing" % name,
                "action": "REWRITE %s: shorten its description, or DISABLE a "
                "lower-value skill to free budget" % name,
            }
        )
    return findings
