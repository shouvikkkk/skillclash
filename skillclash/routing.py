"""Routing simulation: TF-IDF retrieval of queries against skills.

This is a TF-IDF proxy, NOT the real model router. It flags two risks
and nothing more:

* COIN-FLIP: the top two descriptions are near-tied (margin < 0.10)
  for a query, so the model may pick either;
* ROUTING-BLIND: the top-scoring skill is DROPPED or TRUNCATED in the
  discovery listing, so the skill that should win cannot be (fully) seen.

Disabled skills are excluded from routing. Findings never claim the
model WOULD pick wrong.
"""

from __future__ import annotations

from .similarity import query_scores, tokenize

COIN_FLIP_MARGIN = 0.10


def run_routing(skills, queries, dropped, truncated):
    """Score each query; return (per-query results, findings)."""
    routable = [s for s in skills if not s.disabled]
    documents = [tokenize("%s %s" % (s.name, s.description)) for s in routable]
    dropped_set = set(dropped)
    truncated_set = set(truncated)
    results = []
    findings = []
    for query in queries:
        query = query.strip()
        if not query:
            continue
        scores = query_scores(tokenize(query), documents) if documents else []
        ranked = sorted(
            zip(routable, scores), key=lambda pair: pair[1], reverse=True
        )
        if not ranked:
            results.append({"query": query, "top": None, "runner_up": None, "margin": None})
            continue
        top, top_score = ranked[0]
        runner_up, runner_score = ranked[1] if len(ranked) > 1 else (None, 0.0)
        margin = top_score - runner_score
        results.append(
            {
                "query": query,
                "top": top.name,
                "top_score": round(top_score, 4),
                "runner_up": runner_up.name if runner_up else None,
                "runner_up_score": round(runner_score, 4) if runner_up else None,
                "margin": round(margin, 4),
            }
        )
        if top.name in dropped_set or top.name in truncated_set:
            state = "dropped" if top.name in dropped_set else "truncated"
            findings.append(
                {
                    "kind": "ROUTING-BLIND",
                    "severity": "high",
                    "skills": [top.name],
                    "evidence": "query %r retrieves %s first (score %.4f), but "
                    "that skill is %s from the discovery listing"
                    % (query, top.name, top_score, state),
                    "action": "REWRITE %s: shorten its description so it fits "
                    "the discovery budget, or DISABLE a lower-value skill"
                    % top.name,
                }
            )
        if runner_up is not None and margin < COIN_FLIP_MARGIN:
            findings.append(
                {
                    "kind": "COIN-FLIP",
                    "severity": "medium",
                    "skills": sorted({top.name, runner_up.name}),
                    "evidence": "query %r near-ties %s (%.4f) and %s (%.4f); "
                    "margin %.4f < %.2f"
                    % (query, top.name, top_score, runner_up.name, runner_score, margin, COIN_FLIP_MARGIN),
                    "action": "REWRITE %s and %s: differentiate their "
                    "descriptions with distinct trigger keywords"
                    % (top.name, runner_up.name),
                }
            )
    return results, findings
