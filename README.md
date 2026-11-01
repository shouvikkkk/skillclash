# skillclash

Audit your installed agent skills — offline, before a session starts — for
the problems that silently degrade an agent: skills that contradict each
other, skills that shadow each other, and skills that never even make it
into the discovery listing because the budget ran out.

Stdlib-only Python. No third-party dependencies, no network calls, no
model runs.

## The problem

Installed agent skills silently contradict, shadow, and crowd each other
out, and no local tool detects that before a session starts.

**Evidence 1 — skills get silently truncated.** From
dev.to/shimo4228, "15 Days of Skill Sprawl in Claude Code" (verified
first-hand):

> "if you have too many skills, they get silently truncated"

The same account reports a discovery-stage character budget of roughly
2% of the context window (~16,000 chars), with a reported case where
only 42 of 63 skills were displayed.

**Evidence 2 — shadowing dominates skill-library degradation.** From
dev.to/thomastartrau, "Why More Than 30 Skills Kill Your AI Agent"
(verified first-hand), citing a 2026 study "More Skills, Worse Agents?"
and the SkillRouter paper:

> "The agent chooses confidently, and it chooses wrong."

Reported numbers: up to 68% of skill-library degradation comes from
shadowing; 21 pass-rate points lost going from an oracle skill set to
202 skills; 26.4% of public skills have no usable routing description;
the router sees only name + description while 91.7% of routing signal
lives in the skill body.

**Evidence 3 — nobody checks before installation.** From the
natashatherobot Claude skills setup guide: "similar ones can overlap
and worse, contradict each other". From the skillsmith competitive
landscape: "No registry detects conflicts before installation".

## Honest caveats (read these before trusting a number)

- The budget numbers (~16,000 chars, ~1–2% of window, 1,536-char
  per-entry cap) are **community-reported measurements, not an official
  Claude Code spec**. The defaults are overridable with `--budget`.
- Skill precedence rules **vary by harness**. The project-beats-global
  assumption used for `SHADOWED` findings is Claude Code's documented
  behaviour and is marked harness-dependent wherever it appears.
- The routing simulation is a **TF-IDF proxy, NOT the real model
  router**. It flags coin-flip risk (two descriptions near-tied for a
  query) and routing blindness (the winning skill is dropped or
  truncated). It never certifies that the model would pick wrong.
- No live Claude Code verification was run for this tool: no real agent
  session was used to confirm any finding end to end. Treat every
  finding as a lead to inspect, not a verdict.

## What it checks

1. **Discovery** — walks each estate directory; a skill is a
   subdirectory containing `SKILL.md` directly. Also reports structural
   problems: double-nested folders (a directory whose only content is a
   subdirectory holding the `SKILL.md`), subdirectories without
   `SKILL.md` (ignored, info), and a `SKILL.md` at the estate root
   (ignored). Frontmatter is parsed without PyYAML (stdlib only):
   `---` delimiters, single-line `key: value`, quoted values, simple
   lists, boolean-ish values. Broken frontmatter (missing delimiters,
   an unparseable line, an unquoted colon breaking a value) is reported
   as a finding, never a crash.
2. **Frontmatter checks** — missing name or description; name not
   matching the parent directory; names violating lowercase-hyphen
   rules; descriptions over 1,024 chars (spec) and over 1,536 chars
   (listing cap — truncated regardless of budget). Skills with
   `disable-model-invocation: true` are excluded from routing and
   budget but still listed.
3. **Contradictions** — imperative rules are extracted from each
   `SKILL.md` body and description: sentences containing modal/deontic
   markers (`always`, `never`, `must`, `must not`, `mustn't`, `only`,
   `prefer`, `avoid`, `do not`, `don't`, `required`, `forbidden`,
   `prohibit`). Rule targets are normalised (lowercased, stopwords and
   articles stripped, plurals stemmed crudely by dropping a trailing
   `s` only when safe, head noun phrase of up to ~4 content words).
   Rules across skills — and within one skill — with the same target
   (at least 2 shared content words) and opposite polarity are flagged,
   with both quotes, files, and line numbers. Near-identical rule text
   with opposite polarity is marked as the strongest signal. Rules
   explicitly scoped to different environments do **not** flag: scope
   phrases are `in tests`, `in production`, `in dev`, `in staging`,
   `in docs`, `in ci`.
4. **Shadowing** — TF-IDF cosine similarity over name + description
   tokens (stopword-filtered) between every skill pair: >= 0.55 is a
   `SHADOW`, >= 0.85 a `NEAR-DUPLICATE`. Duplicate skill names across
   scopes are `SHADOWED`, and duplicate slash-command slugs (name with
   underscores normalised to hyphens) are flagged too.
5. **Discovery-budget simulation** — entry cost is
   `len("name: description")`. Default budget 16,000, overridable with
   `--budget`. Per-entry cap 1,536: longer descriptions are cut at
   1,536 and flagged `TRUNCATED`, with the lost tail quoted (first 60
   chars of the lost part). Then entries are simulated in discovery
   order (see ordering assumption below); entries that don't fit the
   remaining budget are flagged `DROPPED` (name-only/invisible) and
   named explicitly. Total cost, budget, and the exact dropped list are
   reported.
6. **Routing simulation** (only with `--queries FILE`, one task query
   per line) — TF-IDF retrieval of each query against name +
   description; per query the top match, runner-up, and margin are
   reported. Margin < 0.10 is a `COIN-FLIP`. If the top match is a
   `DROPPED`/`TRUNCATED` skill, it is `ROUTING-BLIND`.
7. **Remediation plan** — every finding carries a concrete action:
   `DISABLE` (add `disable-model-invocation: true`), `MERGE` (for
   near-duplicate/shadow pairs), `RELOCATE` (project-vs-global),
   `REWRITE` (front-load trigger keywords, shorten the description),
   naming the exact skills.

### Ordering assumption

Discovery order is simulated as: global estates first in CLI argument
order, then project estates, alphabetical within an estate. Real
invocation-count ordering is unknown, so pass your global estate first
and treat the dropped list as "dropped under this ordering", not as a
certainty about any particular harness.

## Setup

```sh
python3 -m skillclash audit ~/.claude/skills .claude/skills
```

No installation step is required: the package runs from a checkout with
the standard library only. Python 3.9+ is supported. (A `pyproject.toml`
is included, so `pip install .` also works and provides a `skillclash`
command.)

## Usage

```
python -m skillclash audit <dir>... [--budget N] [--queries FILE]
    [--format text|json] [--strict]
```

Exit codes: `0` clean, `1` warnings only, `2` any
`CONTRADICTION` / `DROPPED` / `SHADOW` / `NEAR-DUPLICATE` / `SHADOWED` /
`COIN-FLIP` / `ROUTING-BLIND` finding, `3` usage/estate errors (no
skills found, unreadable directory). `--strict` upgrades warnings to
exit code 2.

Text reports group findings by severity:
`CONTRADICTION > DROPPED > ROUTING-BLIND > SHADOW > TRUNCATED >
COIN-FLIP > WARNING`.

`--format json` emits a stable schema:

```json
{
  "skills": [{"name": "...", "dir_name": "...", "path": "...",
              "estate": "...", "scope": "...", "description": "...",
              "description_chars": 0, "disabled": false}],
  "findings": [{"kind": "...", "severity": "...", "skills": ["..."],
                "evidence": "...", "action": "..."}],
  "budget": {"limit": 16000, "total_cost": 0, "visible": ["..."],
             "truncated": ["..."], "dropped": ["..."]},
  "routing": [{"query": "...", "top": "...", "top_score": 0.0,
               "runner_up": "...", "runner_up_score": 0.0, "margin": 0.0}],
  "ignored": [{"path": "...", "reason": "..."}]
}
```

## Example: the demo estate

`examples/demo/` is a small estate with planted problems: a
contradiction pair, a shadow pair, an over-long description, and a
global/project name clash, plus a disabled skill and a `queries.txt`.

```sh
python -m skillclash audit examples/demo/global-skills examples/demo/project-skills \
    --queries examples/demo/queries.txt
```

Real output (exit code 2):

```
skillclash audit: 8 skill(s) found

  - api-helper (global, examples/demo/global-skills)
  - code-reviewer (global, examples/demo/global-skills)
  - db-migrate (global, examples/demo/global-skills)
  - api-client (project, examples/demo/project-skills)
  - db-migrate (project, examples/demo/project-skills)
  - deploy-helper (project, examples/demo/project-skills)
  - fast-shipper (project, examples/demo/project-skills)
  - legacy-linter (project, examples/demo/project-skills) [disabled]

Discovery budget: 1961 / 16000 chars used; 7 visible, 1 truncated, 0 dropped
  Truncated: deploy-helper

[CONTRADICTION]
  code-reviewer (examples/demo/global-skills/code-reviewer/SKILL.md:4): 'Never merge code without tests.' vs fast-shipper (examples/demo/project-skills/fast-shipper/SKILL.md:4): 'Always merge code without tests.' -- shared target 'code merge test without' [near-identical wording, opposite polarity -- strongest signal]
    -> REWRITE code-reviewer and fast-shipper: pick one rule and delete or scope the other (e.g. restrict one to tests or production)

[ROUTING-BLIND]
  query 'deploy services with blue-green releases and automatic rollback' retrieves deploy-helper first (score 0.7552), but that skill is truncated from the discovery listing
    -> REWRITE deploy-helper: shorten its description so it fits the discovery budget, or DISABLE a lower-value skill

[NEAR-DUPLICATE]
  descriptions of api-helper and api-client score 0.880 TF-IDF cosine similarity (>= 0.85)
    -> MERGE api-helper and api-client: keep one skill and fold the other's rules into it
  descriptions of db-migrate and db-migrate score 1.000 TF-IDF cosine similarity (>= 0.85)
    -> MERGE db-migrate and db-migrate: keep one skill and fold the other's rules into it

[SHADOWED]
  skill name 'db-migrate' appears 2 times (scopes: global, project; estates: examples/demo/global-skills, examples/demo/project-skills). Precedence assumption: project scope wins over global in Claude Code (harness-dependent), so the global copy is shadowed
    -> RELOCATE db-migrate: keep one copy (project scope wins) and delete or rename the other

[TRUNCATED]
  description of deploy-helper is 1651 chars; listing cuts it at 1536 chars. Lost tail starts: ' on failure. Deploy services to staging and production with '
    -> REWRITE deploy-helper: shorten the description to under 1536 chars, front-loading trigger keywords

[COIN-FLIP]
  query 'call REST APIs with retries and auth headers' near-ties api-helper (0.7746) and api-client (0.7577); margin 0.0169 < 0.10
    -> REWRITE api-helper and api-client: differentiate their descriptions with distinct trigger keywords
  query 'merge code without tests' near-ties code-reviewer (0.0998) and fast-shipper (0.0944); margin 0.0055 < 0.10
    -> REWRITE code-reviewer and fast-shipper: differentiate their descriptions with distinct trigger keywords
  query 'manage Postgres schema migrations with rollback' near-ties db-migrate (0.7361) and db-migrate (0.7361); margin 0.0000 < 0.10
    -> REWRITE db-migrate and db-migrate: differentiate their descriptions with distinct trigger keywords

[WARNING]
  description is 1651 chars, over the 1024-char spec limit
    -> REWRITE deploy-helper: shorten the description to under 1024 chars, front-loading trigger keywords

Routing simulation (TF-IDF proxy, not the real router):
  'call REST APIs with retries and auth headers' -> api-helper (0.7746), runner-up api-client (0.7577), margin 0.0169
  'manage Postgres schema migrations with rollback' -> db-migrate (0.7361), runner-up db-migrate (0.7361), margin 0.0000
  'merge code without tests' -> code-reviewer (0.0998), runner-up fast-shipper (0.0944), margin 0.0055
  'review pull requests for security issues' -> code-reviewer (0.7481), runner-up fast-shipper (0.1039), margin 0.6442
  'deploy services with blue-green releases and automatic rollback' -> deploy-helper (0.7552), runner-up db-migrate (0.0805), margin 0.6747
```

With a tight budget the dropped case appears too — at `--budget 600`,
`deploy-helper` is both truncated and dropped, and its deploy query
becomes `ROUTING-BLIND` (dropped, not just truncated).

## How this differs from existing tools (honestly)

- **skillclone** finds verbatim copies and staleness; it does not parse
  two `SKILL.md` files against each other for contradictions.
- **skillbound** checks a skill's promises against its own bundled
  scripts; it does not compare skills with each other.
- **`claude plugin eval` / SkillRouter** need live model runs or are
  papers, not an offline CLI for your own folder.
- **skills-check** validates single skills, not cross-skill conflicts.
- Nothing parses two `SKILL.md` files against each other for
  contradictions, shadowing, and budget overflow. That gap is what
  skillclash fills.

## Limitations

- Rule extraction is heuristic: it only sees sentences with the listed
  modal markers, and target matching needs at least 2 shared content
  words, so subtle contradictions phrased without those markers are
  missed, and some flagged pairs will need human judgement.
- TF-IDF similarity is a lexical proxy: two skills can be near-duplicates
  in meaning with different wording and score low, or share vocabulary
  and score high without truly competing.
- The budget simulation assumes one listing format (`name:
  description`), one ordering (global first, alphabetical within an
  estate), and community-reported numbers — a real harness may list
  skills differently.
- Scope inference from estate paths (`global` / `project` in the path,
  `.claude` under home) is a heuristic; pass estates in the order that
  matches your setup if the labels look wrong.
- No live Claude Code verification was run: no real agent session was
  used, so nothing here is confirmed against a live router.

## Tests

```sh
python3 -m unittest discover -s tests -t .
```

73 tests, all green, covering frontmatter parsing (including broken,
quoted, and multiline-adjacent cases), name/directory mismatch,
double-nested detection, contradiction pairs (positive and negative
controls, including scope-differing rules that must not flag), TF-IDF
shadowing thresholds, budget simulation (per-entry cap, dropped list),
routing coin-flip and routing-blind, JSON schema shape, exit codes,
and the empty-estate error.

## License

MIT — see [LICENSE](LICENSE).
