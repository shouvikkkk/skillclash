"""Tests for TF-IDF shadowing, budget simulation, and routing."""

import unittest

from skillclash.budget import discovery_order, simulate
from skillclash.discovery import Skill
from skillclash.report import shadow_findings
from skillclash.routing import run_routing
from skillclash.similarity import pairwise_similarities, tokenize


def make_skill(name, description, estate="estate", scope="unknown", disabled=False, dir_name=None):
    return Skill(
        name=name,
        dir_name=dir_name or name,
        path="/tmp/%s/%s" % (estate, name),
        skill_file="/tmp/%s/%s/SKILL.md" % (estate, name),
        estate=estate,
        scope=scope,
        description=description,
        disabled=disabled,
    )


class TestSimilarity(unittest.TestCase):
    def test_identical_docs_score_one(self):
        docs = [tokenize("call rest apis retries"), tokenize("call rest apis retries")]
        matrix = pairwise_similarities(docs)
        self.assertAlmostEqual(matrix[0][1], 1.0, places=6)

    def test_unrelated_docs_score_low(self):
        docs = [tokenize("call rest apis retries"), tokenize("bake sourdough bread starter")]
        matrix = pairwise_similarities(docs)
        self.assertLess(matrix[0][1], 0.2)

    def test_stopwords_removed(self):
        self.assertNotIn("the", tokenize("the quick brown fox"))
        self.assertIn("quick", tokenize("the quick brown fox"))

    def test_shadow_threshold(self):
        a = make_skill("api-helper", "Call REST APIs with retries, auth headers, and JSON parsing.")
        b = make_skill("api-client", "Call REST APIs with retries, auth headers, and JSON parsing.")
        findings = shadow_findings([a, b])
        kinds = {f["kind"] for f in findings}
        # Identical descriptions with differing names: at least a SHADOW
        # (in larger corpora this pair crosses the NEAR-DUPLICATE line).
        self.assertTrue(kinds & {"SHADOW", "NEAR-DUPLICATE"})

    def test_near_duplicate_identical(self):
        a = make_skill("api-helper", "Call REST APIs with retries, auth headers, and JSON parsing.")
        b = make_skill("api-helper", "Call REST APIs with retries, auth headers, and JSON parsing.")
        findings = shadow_findings([a, b])
        kinds = {f["kind"] for f in findings}
        self.assertIn("NEAR-DUPLICATE", kinds)

    def test_clearly_different_skills_no_shadow(self):
        a = make_skill("api-helper", "Call REST APIs with retries and auth headers.")
        b = make_skill("bread-baker", "Bake sourdough bread with a live starter culture.")
        self.assertEqual(shadow_findings([a, b]), [])

    def test_duplicate_name_shadowed(self):
        a = make_skill("db-migrate", "Migrate Postgres schemas.", estate="global-skills", scope="global")
        b = make_skill("db-migrate", "Migrate Postgres schemas.", estate="project-skills", scope="project")
        findings = shadow_findings([a, b])
        self.assertTrue(any(f["kind"] == "SHADOWED" for f in findings))

    def test_duplicate_slug_shadow(self):
        a = make_skill("my_skill", "Do the first thing with databases.")
        b = make_skill("my-skill", "Do a second thing with networking.")
        findings = shadow_findings([a, b])
        self.assertTrue(any("slug" in f["evidence"] for f in findings))

    def test_disabled_skills_excluded_from_shadowing(self):
        a = make_skill("api-helper", "Call REST APIs with retries.")
        b = make_skill("api-client", "Call REST APIs with retries.", disabled=True)
        self.assertEqual(shadow_findings([a, b]), [])


class TestBudget(unittest.TestCase):
    def test_discovery_order_global_first(self):
        project = make_skill("p-skill", "Project skill.", estate="project-skills", scope="project")
        global_skill = make_skill("g-skill", "Global skill.", estate="global-skills", scope="global")
        ordered = discovery_order([project, global_skill])
        self.assertEqual(ordered[0].name, "g-skill")

    def test_small_budget_drops_late_skills(self):
        skills = [make_skill("a-skill", "x" * 50), make_skill("b-skill", "y" * 50)]
        sim = simulate(skills, budget=70)
        self.assertEqual(sim["dropped"], ["b-skill"])
        self.assertEqual(sim["visible"], ["a-skill"])

    def test_per_entry_cap_truncates(self):
        skills = [make_skill("long-skill", "z" * 2000)]
        sim = simulate(skills, budget=16000)
        self.assertEqual(sim["truncated"], ["long-skill"])
        self.assertEqual(sim["total_cost"], 1536)

    def test_disabled_excluded_from_budget(self):
        skills = [
            make_skill("off-skill", "q" * 5000, disabled=True),
            make_skill("on-skill", "w" * 50),
        ]
        sim = simulate(skills, budget=100)
        self.assertEqual(sim["dropped"], [])
        self.assertEqual(sim["visible"], ["on-skill"])

    def test_exact_fit_is_visible(self):
        skill = make_skill("fit-skill", "d" * 40)
        cost = skill.entry_cost
        sim = simulate([skill], budget=cost)
        self.assertEqual(sim["visible"], ["fit-skill"])
        self.assertEqual(sim["dropped"], [])


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.a = make_skill("api-helper", "Call REST APIs with retries, auth headers, and JSON parsing.")
        self.b = make_skill("api-client", "Call REST APIs with retries, auth headers, and JSON parsing.")
        self.c = make_skill("bread-baker", "Bake sourdough bread with a live starter culture.")

    def test_coin_flip_on_tied_descriptions(self):
        _results, findings = run_routing(
            [self.a, self.b, self.c], ["call REST APIs with retries"], [], []
        )
        self.assertTrue(any(f["kind"] == "COIN-FLIP" for f in findings))

    def test_clear_winner_no_coin_flip(self):
        _results, findings = run_routing(
            [self.a, self.b, self.c], ["bake sourdough bread starter"], [], []
        )
        self.assertFalse(any(f["kind"] == "COIN-FLIP" for f in findings))

    def test_routing_blind_on_dropped_top_match(self):
        _results, findings = run_routing(
            [self.a, self.b, self.c], ["bake sourdough bread starter"], ["bread-baker"], []
        )
        self.assertTrue(any(f["kind"] == "ROUTING-BLIND" for f in findings))

    def test_routing_blind_on_truncated_top_match(self):
        _results, findings = run_routing(
            [self.a, self.b, self.c], ["bake sourdough bread starter"], [], ["bread-baker"]
        )
        self.assertTrue(any(f["kind"] == "ROUTING-BLIND" for f in findings))

    def test_routing_result_shape(self):
        results, _findings = run_routing([self.a, self.c], ["bake bread"], [], [])
        self.assertEqual(results[0]["top"], "bread-baker")
        self.assertGreaterEqual(results[0]["margin"], 0.0)


if __name__ == "__main__":
    unittest.main()
