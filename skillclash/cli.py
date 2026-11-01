"""Command-line interface for skillclash.

Usage:
    python -m skillclash audit <dir>... [--budget N] [--queries FILE]
        [--format text|json] [--strict]

Exit codes: 0 clean, 1 warnings only, 2 serious findings
(CONTRADICTION / DROPPED / SHADOW / NEAR-DUPLICATE / SHADOWED /
COIN-FLIP / ROUTING-BLIND), 3 usage/estate errors. ``--strict``
upgrades warnings to exit code 2.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .budget import DEFAULT_BUDGET, budget_findings, simulate
from .discovery import discover, frontmatter_findings
from .report import build_report, exit_code, render_json, render_text, shadow_findings
from .routing import run_routing
from .rules import find_contradictions, skill_rules


def build_parser():
    parser = argparse.ArgumentParser(
        prog="skillclash",
        description="Audit installed agent skills for contradictions, "
        "shadowing, and discovery-budget overflow.",
    )
    parser.add_argument("--version", action="version", version="skillclash %s" % __version__)
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit", help="audit one or more skill estates")
    audit.add_argument("dirs", nargs="+", help="skill estate directories")
    audit.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_BUDGET,
        help="discovery budget in characters (default: %d)" % DEFAULT_BUDGET,
    )
    audit.add_argument(
        "--queries",
        help="file with one task query per line for routing simulation",
    )
    audit.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="report format (default: text)",
    )
    audit.add_argument(
        "--strict",
        action="store_true",
        help="upgrade warnings to exit code 2",
    )
    return parser


def _read_queries(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]
    except OSError as exc:
        print("skillclash: cannot read queries file: %s (%s)" % (path, exc), file=sys.stderr)
        return None


def run_audit(args):
    if args.budget < 0:
        print("skillclash: --budget must be >= 0", file=sys.stderr)
        return 3
    queries = []
    if args.queries:
        queries = _read_queries(args.queries)
        if queries is None:
            return 3
    skills, ignored, errors = discover(args.dirs)
    for err in errors:
        print("skillclash: %s" % err, file=sys.stderr)
    if errors and not skills:
        return 3
    if not skills:
        print(
            "skillclash: no skills found in %s" % ", ".join(args.dirs),
            file=sys.stderr,
        )
        return 3

    findings = []
    findings.extend(frontmatter_findings(skills))
    all_rules = []
    for skill in skills:
        all_rules.extend(skill_rules(skill))
    findings.extend(find_contradictions(all_rules))
    findings.extend(shadow_findings(skills))
    simulation = simulate(skills, budget=args.budget)
    findings.extend(budget_findings(skills, simulation))
    routing_results, routing_findings = run_routing(
        skills, queries, simulation["dropped"], simulation["truncated"]
    )
    findings.extend(routing_findings)

    report = build_report(skills, findings, simulation, routing_results, ignored)
    if args.format == "json":
        sys.stdout.write(render_json(report))
    else:
        sys.stdout.write(render_text(report))
    return exit_code(findings, strict=args.strict)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "audit":
        return run_audit(args)
    parser.error("unknown command")
    return 3


if __name__ == "__main__":
    sys.exit(main())
