"""Imperative-rule extraction and contradiction detection.

A rule is a sentence (from a SKILL.md body or its description) that
contains a modal/deontic marker. Each rule gets a polarity and a
normalised target phrase. Two rules contradict when they share a
target and have opposite polarity -- unless their scopes differ
(``in tests`` vs ``in production`` are different worlds, not a
contradiction).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Checked longest-first so "must not" wins over "must".
NEGATIVE_MARKERS = ["must not", "mustn't", "do not", "don't", "never", "avoid", "forbidden", "prohibit", "prohibited"]
POSITIVE_MARKERS = ["always", "must", "only", "prefer", "required"]

# Scope phrases ("in tests", "in production", ...). Only an explicit
# "in <environment>" phrase scopes a rule: merely mentioning tests does
# not scope it, or almost every testing rule would look scoped.
_SCOPE_RE = re.compile(r"\bin\s+(tests?|production|prod|dev|staging|docs|ci)\b")
_SCOPE_CANONICAL = {"tests": "test", "test": "test", "prod": "production"}


def _scopes_of(sentence):
    scopes = set()
    for match in _SCOPE_RE.finditer(sentence.lower()):
        word = match.group(1)
        scopes.add(_SCOPE_CANONICAL.get(word, word))
    return frozenset(scopes)

STOPWORDS = frozenset(
    """
    a an the to for in on with of by at from as is are was were be been
    being it its this that these those you your we our they their he she
    his her do does did should would could will shall may might then
    than so such into over under between through during before after
    and or but if when while per via
    """.split()
)

# Marker phrases removed before target extraction, longest first.
_MARKER_PHRASES = sorted(
    NEGATIVE_MARKERS + POSITIVE_MARKERS, key=len, reverse=True
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class Rule:
    skill: str
    file: str
    line: int
    text: str
    polarity: str  # "positive" or "negative"
    marker: str
    target_words: tuple
    scope: frozenset

    @property
    def target(self):
        return " ".join(self.target_words)


def _stem(word):
    """Crude plural stemming: drop a trailing 's' only when safe."""
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _content_words(text):
    words = re.findall(r"[a-z0-9']+", text.lower())
    out = []
    for word in words:
        word = word.strip("'")
        if not word or word in STOPWORDS:
            continue
        out.append(_stem(word))
    return out


def _detect_marker(sentence):
    lowered = sentence.lower()
    for marker in NEGATIVE_MARKERS:
        if re.search(r"\b" + re.escape(marker) + r"\b", lowered):
            return "negative", marker
    for marker in POSITIVE_MARKERS:
        if re.search(r"\b" + re.escape(marker) + r"\b", lowered):
            return "positive", marker
    return None, None


def _strip_markers(sentence):
    lowered = sentence.lower()
    for marker in _MARKER_PHRASES:
        lowered = re.sub(r"\b" + re.escape(marker) + r"\b", " ", lowered)
    return lowered


def extract_rules(skill_name, file_path, text, start_line=1):
    """Extract rules from *text*, tracking line numbers.

    Sentences are split on sentence-ending punctuation and newlines;
    line numbers are approximate for multi-sentence lines (the line the
    sentence starts on) and exact for one-sentence-per-line bodies,
    which is how SKILL.md files are normally written.
    """
    rules = []
    lines = text.splitlines()
    for offset, line in enumerate(lines):
        for sentence in _SENTENCE_SPLIT.split(line):
            sentence = sentence.strip()
            if not sentence:
                continue
            polarity, marker = _detect_marker(sentence)
            if polarity is None:
                continue
            stripped = _strip_markers(sentence)
            content = _content_words(stripped)
            if len(content) < 2:
                continue
            scope = _scopes_of(sentence)
            # Head noun phrase: first four content words (scope words
            # are kept in the phrase so "tests" stays visible in output,
            # but scope comparison uses the scope set).
            target = tuple(content[:4])
            rules.append(
                Rule(
                    skill=skill_name,
                    file=file_path,
                    line=start_line + offset,
                    text=sentence,
                    polarity=polarity,
                    marker=marker,
                    target_words=target,
                    scope=scope,
                )
            )
    return rules


def skill_rules(skill):
    """All rules from a skill's body plus its description."""
    rules = extract_rules(skill.name, skill.skill_file, skill.body)
    if skill.description:
        # Description rules are reported against the SKILL.md file; the
        # description lives in the frontmatter at the top of the file.
        for rule in extract_rules(skill.name, skill.skill_file, skill.description, start_line=1):
            rules.append(rule)
    return rules


def _targets_match(a, b):
    """Two targets match when they share at least 2 content words."""
    return len(set(a.target_words) & set(b.target_words)) >= 2


def _scopes_conflict(a, b):
    """True when both rules are scoped and the scopes do not overlap."""
    return bool(a.scope) and bool(b.scope) and not (a.scope & b.scope)


def _near_identical(a, b):
    """True when the two rule texts are identical once markers are removed."""
    return set(_content_words(_strip_markers(a.text))) == set(
        _content_words(_strip_markers(b.text))
    )


def find_contradictions(rules):
    """Pairwise contradictions across (and within) skills."""
    findings = []
    for i in range(len(rules)):
        for j in range(i + 1, len(rules)):
            a, b = rules[i], rules[j]
            if a.polarity == b.polarity:
                continue
            if _scopes_conflict(a, b):
                continue
            if not _targets_match(a, b):
                continue
            same_skill = a.skill == b.skill
            identical = _near_identical(a, b)
            evidence = (
                "%s (%s:%d): %r vs %s (%s:%d): %r -- shared target %r"
                % (
                    a.skill, a.file, a.line, a.text,
                    b.skill, b.file, b.line, b.text,
                    " ".join(sorted(set(a.target_words) & set(b.target_words))),
                )
            )
            if identical:
                evidence += " [near-identical wording, opposite polarity -- strongest signal]"
            if same_skill:
                evidence += " [within a single skill]"
            findings.append(
                {
                    "kind": "CONTRADICTION",
                    "severity": "critical",
                    "skills": sorted({a.skill, b.skill}),
                    "evidence": evidence,
                    "action": (
                        "REWRITE %s: pick one rule and delete or scope the "
                        "other (e.g. restrict one to tests or production)"
                        % (" and ".join(sorted({a.skill, b.skill})))
                    ),
                }
            )
    return findings
