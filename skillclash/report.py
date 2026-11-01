"""Findings assembly, shadowing detection, remediation, and output.

Severity order for the text report (most severe first):
CONTRADICTION > DROPPED > ROUTING-BLIND > SHADOW (including
NEAR-DUPLICATE and SHADOWED) > TRUNCATED > COIN-FLIP > WARNING.

Exit codes: 0 clean, 1 warnings only, 2 any CONTRADICTION / DROPPED /
SHADOW / NEAR-DUPLICATE / SHADOWED / COIN-FLIP / ROUTING-BLIND
finding, 3 usage/estate errors. ``--strict`` upgrades warnings to 2.
"""

from __future__ import annotations

import json

from .similarity import pairwise_similarities, tokenize

SHADOW_THRESHOLD = 0.55
NEAR_DUPLICATE_THRESHOLD = 0.85

_KIND_ORDER = {
    "CONTRADICTION": 0,
    "DROPPED": 1,
    "ROUTING-BLIND": 2,
    "SHADOW": 3,
    "NEAR-DUPLICATE": 3,
    "SHADOWED": 3,
    "TRUNCATED": 4,
    "COIN-FLIP": 5,
    "WARNING": 6,
}

_EXIT_2_KINDS = {
    "CONTRADICTION",
    "DROPPED",
    "SHADOW",
    "NEAR-DUPLICATE",
    "SHADOWED",
    "COIN-FLIP",
    "ROUTING-BLIND",
}


def sort_findings(findings):
    return sorted(
        findings,
        key=lambda f: (_KIND_ORDER.get(f["kind"], 99), f["kind"], sorted(f["skills"])),
    )


def shadow_findings(skills):
    """TF-IDF shadowing, duplicate names, and duplicate command slugs."""
    findings = []
    routable = [s for s in skills if not s.disabled]
    documents = [tokenize("%s %s" % (s.name, s.description)) for s in routable]
    matrix = pairwise_similarities(documents) if len(documents) > 1 else []
    for i in range(len(routable)):
        for j in range(i + 1, len(routable)):
            sim = matrix[i][j]
            a, b = routable[i], routable[j]
            if sim >= NEAR_DUPLICATE_THRESHOLD:
                findings.append(
                    {
                        "kind": "NEAR-DUPLICATE",
                        "severity": "high",
                        "skills": sorted([a.name, b.name]),
                        "evidence": "descriptions of %s and %s score %.3f "
                        "TF-IDF cosine similarity (>= %.2f)"
                        % (a.name, b.name, sim, NEAR_DUPLICATE_THRESHOLD),
                        "action": "MERGE %s and %s: keep one skill and fold "
                        "the other's rules into it" % (a.name, b.name),
                    }
                )
            elif sim >= SHADOW_THRESHOLD:
                findings.append(
                    {
                        "kind": "SHADOW",
                        "severity": "high",
                        "skills": sorted([a.name, b.name]),
                        "evidence": "descriptions of %s and %s score %.3f "
                        "TF-IDF cosine similarity (>= %.2f); they compete "
                        "for the same queries" % (a.name, b.name, sim, SHADOW_THRESHOLD),
                        "action": "MERGE %s and %s, or REWRITE one description "
                        "to cover a clearly different trigger" % (a.name, b.name),
                    }
                )
    # Duplicate names across estates/scopes: the later/lower-precedence
    # copy is shadowed. Precedence assumption (harness-dependent):
    # project scope wins over global scope in Claude Code.
    by_name = {}
    for skill in skills:
        by_name.setdefault(skill.name, []).append(skill)
    for name, copies in by_name.items():
        if len(copies) < 2:
            continue
        scopes = sorted({c.scope for c in copies})
        findings.append(
            {
                "kind": "SHADOWED",
                "severity": "high",
                "skills": [name],
                "evidence": "skill name %r appears %d times (scopes: %s; "
                "estates: %s). Precedence assumption: project scope wins "
                "over global in Claude Code (harness-dependent), so the "
                "global copy is shadowed"
                % (
                    name,
                    len(copies),
                    ", ".join(scopes),
                    ", ".join(sorted({c.estate for c in copies})),
                ),
                "action": "RELOCATE %s: keep one copy (project scope wins) "
                "and delete or rename the other" % name,
            }
        )
    # Duplicate slash-command slugs (underscores normalised to hyphens).
    by_slug = {}
    for skill in skills:
        by_slug.setdefault(skill.slug, []).append(skill)
    for slug, copies in by_slug.items():
        names = sorted({c.name for c in copies})
        if len(names) < 2:
            continue
        findings.append(
            {
                "kind": "SHADOW",
                "severity": "high",
                "skills": names,
                "evidence": "names %s all normalise to slash-command slug %r"
                % (", ".join(names), slug),
                "action": "REWRITE %s: rename so the slash-command slugs differ"
                % " and ".join(names),
            }
        )
    return findings


def exit_code(findings, strict=False):
    kinds = {f["kind"] for f in findings}
    if kinds & _EXIT_2_KINDS:
        return 2
    if findings and (strict or any(f["kind"] != "WARNING" for f in findings)):
        return 2 if strict else 1
    if findings:
        return 2 if strict else 1
    return 0


def build_report(skills, findings, simulation, routing_results, ignored):
    """Assemble the stable JSON report dict."""
    return {
        "skills": [
            {
                "name": s.name,
                "dir_name": s.dir_name,
                "path": s.path,
                "estate": s.estate,
                "scope": s.scope,
                "description": s.description,
                "description_chars": len(s.description),
                "disabled": s.disabled,
            }
            for s in skills
        ],
        "findings": sort_findings(findings),
        "budget": {
            "limit": simulation["limit"],
            "total_cost": simulation["total_cost"],
            "visible": simulation["visible"],
            "truncated": simulation["truncated"],
            "dropped": simulation["dropped"],
        },
        "routing": routing_results,
        "ignored": [{"path": i.path, "reason": i.reason} for i in ignored],
    }


def render_text(report):
    """Human-readable report grouped by severity."""
    lines = []
    skills = report["skills"]
    lines.append("skillclash audit: %d skill(s) found" % len(skills))
    lines.append("")
    for skill in skills:
        flag = " [disabled]" if skill["disabled"] else ""
        lines.append(
            "  - %s (%s, %s)%s"
            % (skill["name"], skill["scope"], skill["estate"], flag)
        )
    budget = report["budget"]
    lines.append("")
    lines.append(
        "Discovery budget: %d / %d chars used; %d visible, %d truncated, %d dropped"
        % (
            budget["total_cost"],
            budget["limit"],
            len(budget["visible"]),
            len(budget["truncated"]),
            len(budget["dropped"]),
        )
    )
    if budget["dropped"]:
        lines.append("  Dropped (invisible): %s" % ", ".join(budget["dropped"]))
    if budget["truncated"]:
        lines.append("  Truncated: %s" % ", ".join(budget["truncated"]))
    findings = report["findings"]
    if not findings:
        lines.append("")
        lines.append("No findings. Clean.")
    else:
        current_kind = None
        for finding in findings:
            if finding["kind"] != current_kind:
                current_kind = finding["kind"]
                lines.append("")
                lines.append("[%s]" % current_kind)
            lines.append("  %s" % finding["evidence"])
            lines.append("    -> %s" % finding["action"])
    if report["routing"]:
        lines.append("")
        lines.append("Routing simulation (TF-IDF proxy, not the real router):")
        for entry in report["routing"]:
            if entry["top"] is None:
                lines.append("  %r: no routable skills" % entry["query"])
            else:
                lines.append(
                    "  %r -> %s (%.4f), runner-up %s (%.4f), margin %.4f"
                    % (
                        entry["query"],
                        entry["top"],
                        entry["top_score"],
                        entry["runner_up"],
                        entry["runner_up_score"] if entry["runner_up_score"] is not None else 0.0,
                        entry["margin"],
                    )
                )
    if report["ignored"]:
        lines.append("")
        lines.append("Ignored (info):")
        for item in report["ignored"]:
            lines.append("  %s: %s" % (item["path"], item["reason"]))
    return "\n".join(lines) + "\n"


def render_json(report):
    return json.dumps(report, indent=2, sort_keys=False) + "\n"
