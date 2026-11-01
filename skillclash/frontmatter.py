"""Frontmatter parsing for SKILL.md files, standard library only.

The parser intentionally implements a small, documented subset of YAML:
single-line ``key: value`` pairs, quoted scalars (single and double),
inline lists (``[a, b]``), block lists (``- item`` lines under a bare key),
and boolean-ish scalars (``true``/``false``/``yes``/``no``/``on``/``off``).

Anything outside that subset is reported as a parse error instead of
raising: a broken frontmatter block must never crash an audit.
"""

from __future__ import annotations

import re

_BOOL_TRUE = {"true", "yes", "on"}
_BOOL_FALSE = {"false", "no", "off"}

# A plain (unquoted) scalar may not contain ": " in YAML: the colon would
# start a new mapping. A quoted scalar may contain anything.
_UNQUOTED_COLON = re.compile(r":\s")


class FrontmatterResult:
    """Parsed frontmatter plus any problems found while parsing."""

    def __init__(self, data, errors, body):
        self.data = data  # dict[str, object]
        self.errors = errors  # list[str]
        self.body = body  # str: everything after the closing delimiter


def _strip_quotes(value):
    """Remove one layer of matching quotes, handling basic escapes."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        else:
            inner = inner.replace("''", "'")
        return inner, True
    return value, False


def _parse_scalar(raw):
    """Parse one scalar value. Returns (value, error_or_None)."""
    value = raw.strip()
    if not value:
        return None, None
    unquoted, was_quoted = _strip_quotes(value)
    if was_quoted:
        return unquoted, None
    lowered = value.lower()
    if lowered in _BOOL_TRUE:
        return True, None
    if lowered in _BOOL_FALSE:
        return False, None
    if _UNQUOTED_COLON.search(value):
        # Unquoted colon-space: not a valid plain scalar in YAML.
        return value, (
            "unquoted colon in value %r; quote the value to keep the colon" % value
        )
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return [], None
        items = []
        for part in inner.split(","):
            item, _quoted = _strip_quotes(part.strip())
            items.append(item)
        return items, None
    return value, None


def parse_frontmatter(text):
    """Split *text* into frontmatter data, errors, and body.

    Missing delimiters, a missing closing delimiter, a line without a
    colon, and an unquoted colon inside a value are all recorded in
    ``errors``; the body is returned on a best-effort basis and the
    caller decides how to report the errors.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return FrontmatterResult({}, ["missing opening frontmatter delimiter '---'"], text)
    closing = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            closing = idx
            break
    if closing is None:
        return FrontmatterResult(
            {}, ["missing closing frontmatter delimiter '---'"], text
        )

    data = {}
    errors = []
    current_list_key = None
    for lineno, raw in enumerate(lines[1:closing], start=2):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list_key is not None:
            item, _quoted = _strip_quotes(stripped[2:].strip())
            data[current_list_key].append(item)
            continue
        if ":" not in stripped:
            errors.append("line %d: unparseable frontmatter line %r (no ':')" % (lineno, raw))
            current_list_key = None
            continue
        key, _, raw_value = stripped.partition(":")
        key = key.strip()
        if not key:
            errors.append("line %d: empty frontmatter key in %r" % (lineno, raw))
            current_list_key = None
            continue
        value = raw_value.strip()
        if value == "":
            # Bare key: either a block list follows or the value is empty.
            data[key] = []
            current_list_key = key
            continue
        current_list_key = None
        parsed, err = _parse_scalar(value)
        if err is not None:
            errors.append("line %d: %s" % (lineno, err))
        data[key] = parsed
    # A trailing bare key with no list items is an empty value, not a list.
    # Leave it as [] only if items were appended; distinguish by checking
    # whether the key's list stayed empty AND the next content was not a
    # list -- there is no way to tell, so normalise empty lists to None
    # only when the key never received an item and it is not a known
    # list-valued key. Keep [] as-is: callers treat it as "no value".
    body = "\n".join(lines[closing + 1 :])
    return FrontmatterResult(data, errors, body)
