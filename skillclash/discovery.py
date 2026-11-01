"""Discovery of skill estates: walking directories, finding SKILL.md files.

A skill is a subdirectory containing a ``SKILL.md`` file directly.
Structural problems are collected, not fatal:

* double-nested folder: a directory whose only content is one
  subdirectory that itself holds a SKILL.md (the outer folder is not a
  skill, the inner one is -- but the layout is almost certainly a
  mistake, e.g. an unzipped archive, so it is reported);
* subdirectories without SKILL.md: ignored, reported as info;
* a SKILL.md at the estate root: ignored (it belongs to no skill
  directory), reported as info.

Scope inference (used only for ordering and for the project-vs-global
precedence note): an estate path containing ``global`` is global; one
containing ``project`` is project; otherwise an absolute path under the
user's home containing ``.claude`` is global, a relative ``.claude``
path is project, and anything else is unknown. Scope is
harness-dependent and this heuristic is documented, not asserted.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .frontmatter import parse_frontmatter

NAME_RULE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_DESCRIPTION_SPEC = 1024
LISTING_CAP = 1536


@dataclass
class Skill:
    """One discovered skill."""

    name: str  # frontmatter name, falling back to the directory name
    dir_name: str
    path: str  # directory containing SKILL.md
    skill_file: str
    estate: str
    scope: str
    description: str = ""
    disabled: bool = False
    frontmatter: dict = field(default_factory=dict)
    frontmatter_errors: list = field(default_factory=list)
    body: str = ""

    @property
    def slug(self):
        """Slash-command slug: name with underscores normalised to hyphens."""
        return self.name.replace("_", "-")

    @property
    def entry_text(self):
        """Discovery-listing entry: ``name: description``."""
        return "%s: %s" % (self.name, self.description)

    @property
    def entry_cost(self):
        return len(self.entry_text)


@dataclass
class Ignored:
    path: str
    reason: str


def infer_scope(estate_path):
    lowered = estate_path.replace(os.sep, "/").lower()
    if "global" in lowered:
        return "global"
    if "project" in lowered:
        return "project"
    if ".claude" in lowered:
        home = os.path.expanduser("~").replace(os.sep, "/")
        if os.path.isabs(estate_path) and lowered.startswith(home.lower()):
            return "global"
        return "project"
    return "unknown"


def _read_skill_file(skill_file):
    with open(skill_file, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def discover(estates):
    """Walk *estates* (list of directory paths) in argument order.

    Returns ``(skills, ignored, errors)``. ``errors`` holds fatal
    per-estate problems (missing/unreadable directory); an empty skill
    list is not an error here -- the CLI turns it into exit code 3.
    Within an estate, skills are alphabetical by directory name.
    """
    skills = []
    ignored = []
    errors = []
    for estate in estates:
        if not os.path.isdir(estate):
            errors.append("estate not found or not a directory: %s" % estate)
            continue
        scope = infer_scope(estate)
        root_skill = os.path.join(estate, "SKILL.md")
        if os.path.isfile(root_skill):
            ignored.append(
                Ignored(root_skill, "SKILL.md at estate root belongs to no skill directory")
            )
        for dirpath, dirnames, filenames in os.walk(estate):
            dirnames.sort()
            if dirpath == estate:
                # Estate root itself is not a skill; children are handled
                # by the walk. Still record non-skill top-level dirs below.
                pass
            if "SKILL.md" in filenames and dirpath != estate:
                skill_file = os.path.join(dirpath, "SKILL.md")
                try:
                    text = _read_skill_file(skill_file)
                except OSError as exc:
                    errors.append("unreadable SKILL.md: %s (%s)" % (skill_file, exc))
                    continue
                parsed = parse_frontmatter(text)
                data = parsed.data
                dir_name = os.path.basename(dirpath)
                name = data.get("name")
                if not isinstance(name, str) or not name:
                    name = dir_name
                description = data.get("description")
                if not isinstance(description, str):
                    description = ""
                disabled = data.get("disable-model-invocation")
                if isinstance(disabled, str):
                    disabled = disabled.strip().lower() in ("true", "yes", "on")
                skills.append(
                    Skill(
                        name=name,
                        dir_name=dir_name,
                        path=dirpath,
                        skill_file=skill_file,
                        estate=estate,
                        scope=scope,
                        description=description,
                        disabled=bool(disabled),
                        frontmatter=data,
                        frontmatter_errors=list(parsed.errors),
                        body=parsed.body,
                    )
                )
                # Do not descend into a skill directory: nested SKILL.md
                # files inside a skill are part of that skill, not new ones.
                dirnames[:] = []
                continue
            # Not a skill directory.
            if dirpath != estate:
                subdirs = [
                    d
                    for d in dirnames
                    if os.path.isfile(os.path.join(dirpath, d, "SKILL.md"))
                ]
                if len(dirnames) == 1 and len(subdirs) == 1:
                    ignored.append(
                        Ignored(
                            dirpath,
                            "double-nested folder: only content is %s/ which holds "
                            "the SKILL.md; the skill probably lives one level too deep"
                            % subdirs[0],
                        )
                    )
                elif not filenames and not dirnames:
                    ignored.append(Ignored(dirpath, "empty directory, no SKILL.md"))
                # Directories that merely contain skills deeper down are
                # not reported: the walk reaches the skills themselves.
        # Second pass: every remaining non-skill directory that is not
        # an ancestor of a skill is ignored info (e.g. a notes folder).
        skill_paths = {s.path for s in skills if s.estate == estate}
        seen_ignored = {i.path for i in ignored}
        for dirpath, dirnames, _filenames in os.walk(estate):
            if dirpath in skill_paths:
                dirnames[:] = []
                continue
            if dirpath != estate and dirpath not in seen_ignored:
                if not any(p.startswith(dirpath + os.sep) for p in skill_paths):
                    ignored.append(
                        Ignored(dirpath, "directory without SKILL.md, ignored")
                    )
                    seen_ignored.add(dirpath)
    # Sort: alphabetical within each estate, estates in argument order.
    # The budget module re-orders global estates before project estates.
    estate_order = {estate: idx for idx, estate in enumerate(estates)}
    skills.sort(key=lambda s: (estate_order.get(s.estate, 0), s.dir_name.lower()))
    return skills, ignored, errors


def frontmatter_findings(skills):
    """Validate frontmatter fields; returns list of finding dicts.

    Kinds here are all WARNING: none of these alone is a contradiction,
    a shadow, or a budget overflow.
    """
    findings = []
    for skill in skills:
        for err in skill.frontmatter_errors:
            findings.append(
                {
                    "kind": "WARNING",
                    "severity": "low",
                    "skills": [skill.name],
                    "evidence": "broken frontmatter in %s: %s" % (skill.skill_file, err),
                    "action": "REWRITE %s: fix the frontmatter (quote values "
                    "containing colons, keep the --- delimiters)" % skill.name,
                }
            )
        if "name" not in skill.frontmatter or not skill.frontmatter.get("name"):
            findings.append(
                {
                    "kind": "WARNING",
                    "severity": "low",
                    "skills": [skill.name],
                    "evidence": "missing frontmatter name in %s; directory name "
                    "%r used as fallback" % (skill.skill_file, skill.dir_name),
                    "action": "REWRITE %s: add an explicit name field matching "
                    "its directory name" % skill.name,
                }
            )
        elif skill.frontmatter.get("name") != skill.dir_name:
            findings.append(
                {
                    "kind": "WARNING",
                    "severity": "low",
                    "skills": [skill.name],
                    "evidence": "frontmatter name %r does not match directory name %r"
                    % (skill.frontmatter.get("name"), skill.dir_name),
                    "action": "REWRITE %s: rename the directory or the name "
                    "field so they match" % skill.name,
                }
            )
        if not NAME_RULE.match(skill.name):
            findings.append(
                {
                    "kind": "WARNING",
                    "severity": "low",
                    "skills": [skill.name],
                    "evidence": "skill name %r violates lowercase-hyphen rules "
                    "(lowercase letters, digits, single hyphens)" % skill.name,
                    "action": "REWRITE %s: rename it to a lowercase-hyphen name" % skill.name,
                }
            )
        if "description" not in skill.frontmatter or not skill.description:
            findings.append(
                {
                    "kind": "WARNING",
                    "severity": "low",
                    "skills": [skill.name],
                    "evidence": "missing frontmatter description in %s" % skill.skill_file,
                    "action": "REWRITE %s: add a description -- the router sees "
                    "only name + description" % skill.name,
                }
            )
        elif len(skill.description) > MAX_DESCRIPTION_SPEC:
            findings.append(
                {
                    "kind": "WARNING",
                    "severity": "low",
                    "skills": [skill.name],
                    "evidence": "description is %d chars, over the %d-char spec limit"
                    % (len(skill.description), MAX_DESCRIPTION_SPEC),
                    "action": "REWRITE %s: shorten the description to under %d chars, "
                    "front-loading trigger keywords" % (skill.name, MAX_DESCRIPTION_SPEC),
                }
            )
    return findings
