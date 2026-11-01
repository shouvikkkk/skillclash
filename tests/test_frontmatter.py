"""Tests for stdlib frontmatter parsing."""

import unittest

from skillclash.frontmatter import parse_frontmatter


def doc(body="Some body text."):
    return "---\nname: my-skill\ndescription: Does things.\n---\n\n" + body


class TestFrontmatterBasics(unittest.TestCase):
    def test_basic_fields(self):
        result = parse_frontmatter(doc())
        self.assertEqual(result.data["name"], "my-skill")
        self.assertEqual(result.data["description"], "Does things.")
        self.assertEqual(result.errors, [])
        self.assertIn("Some body", result.body)

    def test_double_quoted_value_with_colon(self):
        text = '---\nname: my-skill\ndescription: "Use: the thing"\n---\n\nBody.'
        result = parse_frontmatter(text)
        self.assertEqual(result.data["description"], "Use: the thing")
        self.assertEqual(result.errors, [])

    def test_single_quoted_value(self):
        text = "---\nname: my-skill\ndescription: 'It''s fine'\n---\n\nBody."
        result = parse_frontmatter(text)
        self.assertEqual(result.data["description"], "It's fine")

    def test_inline_list(self):
        text = "---\nname: my-skill\ntags: [a, b, c]\n---\n\nBody."
        result = parse_frontmatter(text)
        self.assertEqual(result.data["tags"], ["a", "b", "c"])

    def test_block_list(self):
        text = "---\nname: my-skill\ntags:\n  - alpha\n  - beta\n---\n\nBody."
        result = parse_frontmatter(text)
        self.assertEqual(result.data["tags"], ["alpha", "beta"])

    def test_boolean_values(self):
        text = (
            "---\nname: my-skill\ndisable-model-invocation: true\n"
            "other: false\nthird: yes\nfourth: off\n---\n\nBody."
        )
        result = parse_frontmatter(text)
        self.assertIs(result.data["disable-model-invocation"], True)
        self.assertIs(result.data["other"], False)
        self.assertIs(result.data["third"], True)
        self.assertIs(result.data["fourth"], False)

    def test_comment_lines_ignored(self):
        text = "---\n# a comment\nname: my-skill\n---\n\nBody."
        result = parse_frontmatter(text)
        self.assertEqual(result.data["name"], "my-skill")
        self.assertEqual(result.errors, [])

    def test_empty_value(self):
        text = "---\nname: my-skill\nnote:\n---\n\nBody."
        result = parse_frontmatter(text)
        self.assertIn("note", result.data)
        self.assertEqual(result.errors, [])


class TestFrontmatterBroken(unittest.TestCase):
    def test_missing_opening_delimiter(self):
        result = parse_frontmatter("name: my-skill\n\nBody.")
        self.assertTrue(any("opening" in e for e in result.errors))
        self.assertEqual(result.data, {})

    def test_missing_closing_delimiter(self):
        result = parse_frontmatter("---\nname: my-skill\n\nBody.")
        self.assertTrue(any("closing" in e for e in result.errors))

    def test_unparseable_line_no_colon(self):
        text = "---\nname: my-skill\nthis line has no colon\n---\n\nBody."
        result = parse_frontmatter(text)
        self.assertTrue(any("unparseable" in e for e in result.errors))
        self.assertEqual(result.data["name"], "my-skill")

    def test_unquoted_colon_reported_not_crash(self):
        text = "---\nname: my-skill\ndescription: Use: the thing\n---\n\nBody."
        result = parse_frontmatter(text)
        self.assertTrue(any("unquoted colon" in e for e in result.errors))
        # Value is still kept on a best-effort basis.
        self.assertIn("Use", result.data["description"])

    def test_multiline_adjacent_body_intact(self):
        text = doc("Line one.\nLine two.\n\nLine three.")
        result = parse_frontmatter(text)
        self.assertIn("Line three.", result.body)

    def test_no_crash_on_empty_file(self):
        result = parse_frontmatter("")
        self.assertTrue(result.errors)
        self.assertEqual(result.data, {})


if __name__ == "__main__":
    unittest.main()
