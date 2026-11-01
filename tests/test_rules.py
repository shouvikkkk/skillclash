"""Tests for rule extraction and contradiction detection."""

import unittest

from skillclash.rules import extract_rules, find_contradictions


def rules_for(skill, body):
    return extract_rules(skill, "/tmp/%s/SKILL.md" % skill, body)


class TestRuleExtraction(unittest.TestCase):
    def test_positive_and_negative_markers(self):
        rules = rules_for("a", "Always back up the database.\nNever delete backups.")
        self.assertEqual(len(rules), 2)
        self.assertEqual({r.polarity for r in rules}, {"positive", "negative"})

    def test_must_not_beats_must(self):
        rules = rules_for("a", "You must not edit production data directly.")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].polarity, "negative")
        self.assertEqual(rules[0].marker, "must not")

    def test_no_marker_no_rule(self):
        rules = rules_for("a", "This skill helps with databases and queries.")
        self.assertEqual(rules, [])

    def test_all_markers_recognised(self):
        bodies = [
            "Always use retries.",
            "Never use retries.",
            "You must use retries.",
            "You must not use retries.",
            "You mustn't use retries.",
            "Only use retries.",
            "Prefer retries over polling.",
            "Avoid polling the API.",
            "Do not poll the API.",
            "Don't poll the API.",
            "Polling is forbidden here.",
            "Retries are required here.",
        ]
        for body in bodies:
            with self.subTest(body=body):
                self.assertEqual(len(rules_for("a", body)), 1)

    def test_line_numbers_tracked(self):
        rules = rules_for("a", "Intro line.\n\nNever merge code without tests.")
        self.assertEqual(rules[0].line, 3)

    def test_plural_stemming_merges_targets(self):
        rules = rules_for("a", "Always run the test suites.")
        self.assertIn("test", rules[0].target_words)


class TestContradictions(unittest.TestCase):
    def assert_flags(self, body_a, body_b):
        rules = rules_for("a", body_a) + rules_for("b", body_b)
        findings = find_contradictions(rules)
        self.assertTrue(findings, "expected a contradiction, got none")
        return findings

    def assert_no_flag(self, body_a, body_b):
        rules = rules_for("a", body_a) + rules_for("b", body_b)
        self.assertEqual(find_contradictions(rules), [])

    def test_classic_pair_flags(self):
        findings = self.assert_flags(
            "Never merge code without tests.",
            "Always merge code without tests.",
        )
        self.assertEqual(findings[0]["kind"], "CONTRADICTION")
        self.assertIn("near-identical", findings[0]["evidence"])

    def test_within_single_skill_flags(self):
        rules = rules_for("a", "Always use SQLite for local storage.\nNever use SQLite for local storage.")
        findings = find_contradictions(rules)
        self.assertTrue(findings)
        self.assertIn("within a single skill", findings[0]["evidence"])

    def test_same_polarity_no_flag(self):
        self.assert_no_flag(
            "Always back up the database.",
            "Always back up the database before migrating.",
        )

    def test_different_targets_no_flag(self):
        self.assert_no_flag(
            "Always back up the database.",
            "Never deploy on Friday afternoon.",
        )

    def test_one_shared_word_not_enough(self):
        # Only "code" is shared; the 2-word minimum must block this.
        self.assert_no_flag(
            "Always document the code.",
            "Never ship code on Fridays.",
        )

    def test_scope_differing_rules_do_not_flag(self):
        self.assert_no_flag(
            "Always skip tests in tests.",
            "Never skip tests in production.",
        )

    def test_same_scope_rules_do_flag(self):
        self.assert_flags(
            "Always skip tests in production.",
            "Never skip tests in production.",
        )

    def test_scoped_vs_unscoped_flags(self):
        self.assert_flags(
            "Always merge code without tests.",
            "Never merge code without tests in production.",
        )

    def test_prefer_vs_avoid_flags(self):
        self.assert_flags(
            "Prefer retries over polling for API calls.",
            "Avoid retries over polling for API calls.",
        )


if __name__ == "__main__":
    unittest.main()
