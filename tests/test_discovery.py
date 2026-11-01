"""Tests for estate discovery and frontmatter validation."""

import os
import tempfile
import unittest

from skillclash.discovery import discover, frontmatter_findings


def write_skill(root, name, description="Does things.", body="Body.", extra=""):
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "SKILL.md"), "w") as handle:
        handle.write(
            "---\nname: %s\ndescription: %s\n%s---\n\n%s\n"
            % (name, description, extra, body)
        )
    return path


class DiscoveryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.estate = os.path.join(self.tmp.name, "estate")
        os.makedirs(self.estate)

    def test_discovers_skills_alphabetically(self):
        write_skill(self.estate, "zeta")
        write_skill(self.estate, "alpha")
        skills, _ignored, errors = discover([self.estate])
        self.assertEqual(errors, [])
        self.assertEqual([s.name for s in skills], ["alpha", "zeta"])

    def test_missing_name_falls_back_to_dir(self):
        path = os.path.join(self.estate, "fallback-skill")
        os.makedirs(path)
        with open(os.path.join(path, "SKILL.md"), "w") as handle:
            handle.write("---\ndescription: No name here.\n---\n\nBody.\n")
        skills, _ignored, _errors = discover([self.estate])
        self.assertEqual(skills[0].name, "fallback-skill")
        findings = frontmatter_findings(skills)
        self.assertTrue(any("missing frontmatter name" in f["evidence"] for f in findings))

    def test_name_dir_mismatch(self):
        path = os.path.join(self.estate, "dir-name")
        os.makedirs(path)
        with open(os.path.join(path, "SKILL.md"), "w") as handle:
            handle.write("---\nname: other-name\ndescription: X.\n---\n\nBody.\n")
        skills, _ignored, _errors = discover([self.estate])
        findings = frontmatter_findings(skills)
        self.assertTrue(any("does not match directory" in f["evidence"] for f in findings))

    def test_invalid_name_flagged(self):
        write_skill(self.estate, "Bad_Name")
        skills, _ignored, _errors = discover([self.estate])
        findings = frontmatter_findings(skills)
        self.assertTrue(any("lowercase-hyphen" in f["evidence"] for f in findings))

    def test_missing_description_flagged(self):
        path = os.path.join(self.estate, "nodesc")
        os.makedirs(path)
        with open(os.path.join(path, "SKILL.md"), "w") as handle:
            handle.write("---\nname: nodesc\n---\n\nBody.\n")
        skills, _ignored, _errors = discover([self.estate])
        findings = frontmatter_findings(skills)
        self.assertTrue(any("missing frontmatter description" in f["evidence"] for f in findings))

    def test_long_description_over_spec_flagged(self):
        write_skill(self.estate, "wordy", description="x" * 1100)
        skills, _ignored, _errors = discover([self.estate])
        findings = frontmatter_findings(skills)
        self.assertTrue(any("1024-char spec" in f["evidence"] for f in findings))

    def test_broken_frontmatter_never_crashes(self):
        path = os.path.join(self.estate, "broken")
        os.makedirs(path)
        with open(os.path.join(path, "SKILL.md"), "w") as handle:
            handle.write("---\nname: broken\ndescription: Use: it\n---\n\nBody.\n")
        skills, _ignored, errors = discover([self.estate])
        self.assertEqual(errors, [])
        self.assertEqual(len(skills), 1)
        findings = frontmatter_findings(skills)
        self.assertTrue(any("broken frontmatter" in f["evidence"] for f in findings))

    def test_double_nested_detected_and_inner_found(self):
        outer = os.path.join(self.estate, "wrapped")
        write_skill(outer, "inner-skill")
        skills, ignored, _errors = discover([self.estate])
        self.assertEqual([s.name for s in skills], ["inner-skill"])
        self.assertTrue(any("double-nested" in i.reason for i in ignored))

    def test_estate_root_skill_md_ignored(self):
        with open(os.path.join(self.estate, "SKILL.md"), "w") as handle:
            handle.write("---\nname: root\ndescription: Root.\n---\n\nBody.\n")
        write_skill(self.estate, "real-skill")
        skills, ignored, _errors = discover([self.estate])
        self.assertEqual([s.name for s in skills], ["real-skill"])
        self.assertTrue(any("estate root" in i.reason for i in ignored))

    def test_subdir_without_skill_md_reported_as_info(self):
        notes = os.path.join(self.estate, "notes")
        os.makedirs(notes)
        with open(os.path.join(notes, "README.md"), "w") as handle:
            handle.write("Just notes.\n")
        write_skill(self.estate, "real-skill")
        _skills, ignored, _errors = discover([self.estate])
        self.assertTrue(any(i.path == notes for i in ignored))

    def test_disabled_skill_flagged(self):
        write_skill(self.estate, "off-skill", extra="disable-model-invocation: true\n")
        skills, _ignored, _errors = discover([self.estate])
        self.assertTrue(skills[0].disabled)

    def test_missing_estate_is_error(self):
        _skills, _ignored, errors = discover([os.path.join(self.tmp.name, "nope")])
        self.assertTrue(errors)

    def test_scope_inference(self):
        global_estate = os.path.join(self.tmp.name, "global-skills")
        project_estate = os.path.join(self.tmp.name, "project-skills")
        write_skill(global_estate, "g-skill")
        write_skill(project_estate, "p-skill")
        skills, _ignored, _errors = discover([global_estate, project_estate])
        by_name = {s.name: s.scope for s in skills}
        self.assertEqual(by_name["g-skill"], "global")
        self.assertEqual(by_name["p-skill"], "project")


if __name__ == "__main__":
    unittest.main()
