# Nord Stream — Modular Refactor Design

**Date:** 2026-07-08
**Branch:** `ai-refactor`
**Status:** Approved design — pending implementation plan

## Goal

Restructure nord-stream so that responsibilities are cleanly separated and each
platform (GitHub, GitLab, Azure DevOps; CircleCI later) is easy to maintain and
extend. Today the `core/*/*.py` "runner" classes (676–900 lines each) mix four
concerns — fetching data, manipulating it, displaying it, and orchestrating the
attack lifecycle — and carry ~120 hand-written property getter/setters of config
boilerplate. Display was extracted only for GitHub (`core/github/display.py`),
inconsistently.

The refactor introduces a consistent layered architecture with a **pragmatic
shared core**, and adds a **pytest** test suite so behavior can't silently
regress.

## Non-goals

- No change to what the tool does or which attacks it performs.
- No rewrite of the YAML payloads themselves (only their generators get tests).
- Display formatting is **not** unit-tested (explicitly out of scope), though it
  is still separated into its own layer.

## Constraints

- CLI flags/commands stay behavior-compatible through the migration. CLI-surface
  cleanups (reducing docopt boilerplate, unifying shared args) are allowed but
  land **only after** behavior is locked by tests.
- Tooling stays as-is: `black` (line-length 120), conventional commits,
  pre-commit. Tests use `pytest` + `responses` (new dev dependencies).
- Python package name/entry point (`nord-stream = nordstream.__main__:main`)
  unchanged.

## Architecture — five layers

Every platform is split into the same five layers, each with one responsibility:

| Layer | Package | Responsibility | Allowed to touch |
|---|---|---|---|
| **Client (fetch)** | `cicd/` | HTTP, auth, retries, pagination. Returns raw JSON/bytes. | network + endpoints |
| **Manipulate** | `models/`, `parsers/` | Pure functions: raw API JSON → typed dataclasses. No I/O. | dicts → dataclasses |
| **Display** | `report/` | Models → formatted output via `logger`. One reporter per platform. | models → strings |
| **Orchestrate** | `core/` | The deploy lifecycle (push → trigger → wait → download → decode → clean). Wires client + parsers + reporter + git. No display logic, no raw HTTP. | wiring |
| **Entry** | `cli/` | Parse argv → build a config object → dispatch an action. | argv → config |

**Rule of thumb enforced during review:** `cicd/` must not import `logger` for
data display; `core/` must not build formatted strings; `models/`/`parsers/`
must not do I/O. The "manipulate" layer being pure functions is what makes it the
high-value, network-free test target.

### Data flow (one enumerate action)

```
cli/ parses argv
  → builds RunnerConfig
  → core/ runner asks cicd/ client for raw JSON
      → parsers/ turn JSON into models (Secret, Repo, ProtectionRule, …)
      → core/ hands models to report/ reporter
          → reporter formats via logger
```

### Data flow (one deploy/extract action)

```
core/ BaseRunner.run():
  generate YAML (yaml/)          # platform hook: _generate_yaml
  push branch (git.py)
  trigger pipeline (cicd/)       # platform hook: _trigger
  wait for completion (cicd/)
  download output (cicd/)        # platform hook: _collect
  decode secrets (parsers/)
  report result (report/)
  clean logs/branch (cicd/ + git.py)
```

## Shared core (pragmatic)

Share only what is genuinely common; platform-specific features (DevOps service
connections, GitLab group/instance scopes, GitHub environments) live in their
own subclass methods rather than being forced into a leaky base.

- **`cicd/base.py` → `BaseClient`**: `requests.Session`, auth header assembly,
  retry/backoff, paginated GET helper, `outputDir` / `branchName` /
  `defaultBranchName`. Each platform client subclasses it and implements only its
  own endpoints.
- **`core/base.py` → `BaseRunner`**: the deploy/extract/clean lifecycle as a
  template method with the hooks shown above. Removes most of the duplicated
  orchestration across the three runners.
- **`config.py` → dataclasses** replacing the ~120 property getter/setters:
  - `ExtractionOptions` — the `extract*` / `no-*` toggles.
  - `RunnerConfig` — branch name, output dir, clean flags, sleep time, filters,
    OIDC parameters, yaml path.
  - `CommitIdentity` — user / email / GPG key id (currently on `Git`).

Platform-specific option groups (e.g. DevOps' seven `extract*ServiceConnections`
flags) become their own small dataclasses composed into `RunnerConfig`.

## Testing

`tests/` mirrors the package. Three suites (per approved scope):

1. **Parsers/models** — unit tests over saved API-JSON fixtures in
   `tests/fixtures/<platform>/`. Assert JSON → dataclass conversions, including
   edge cases (empty lists, missing keys, encoded values).
2. **YAML generators** — golden-file/snapshot tests locking generated pipeline
   output for each build type (default, azureoidc, awsoidc, custom).
3. **Clients (mocked HTTP)** — `responses`-mocked tests verifying request
   construction (URL, headers, pagination) and response handling, no real APIs.

Config added to `pyproject.toml`: `[project.optional-dependencies] dev` with
`pytest`, `responses`; a `[tool.pytest.ini_options]` section. `test` added to the
conventional-commit allowlist (already present).

## Migration strategy — staged, always-runnable

Landed as one conventional commit per stage on `ai-refactor`, opened as a single
PR at the end. Each stage keeps the tool runnable and CLI-compatible.

1. **Scaffold** — create `models/`, `parsers/`, `report/`, `cli/`, `tests/`
   packages; add pytest/responses dev deps and config. No behavior change.
2. **Shared base + config** — `BaseClient`, `BaseRunner`, `config.py`
   dataclasses. Not yet wired into platforms.
3. **GitHub migration** — split `cicd/github.py`, `core/github/*` onto the new
   layers; move display into `report/github.py`; add GitHub parser + client +
   YAML tests. This proves the pattern end-to-end.
4. **GitLab migration** — same shape; add tests.
5. **DevOps migration** — same shape; add tests.
6. **CLI thinning** — reduce docopt/arg boilerplate, unify shared args now that
   behavior is test-locked.

Each stage is reviewable independently; a reviewer can follow GitHub (stage 3) as
the reference implementation and confirm GitLab/DevOps mirror it.

## Risks & mitigations

- **Silent behavior change during a move.** Mitigation: migrate one platform at a
  time; land parser/client/YAML tests in the same stage as the code they cover;
  keep CLI identical until stage 6.
- **Over-abstraction.** Mitigation: pragmatic base — when a platform diverges,
  prefer a subclass method over widening the base interface.
- **Fixtures drifting from real APIs.** Mitigation: fixtures are captured from
  the current client responses / documented API shapes and committed under
  `tests/fixtures/`, reviewed alongside the parser tests.

## Definition of done

- All three platforms run through the five-layer architecture on shared base
  classes.
- No `logger` display calls remain in `cicd/`; no formatted-string building
  remains in `core/`.
- `pytest` green: parser, YAML, and mocked-client suites.
- CLI behavior unchanged (or intentionally, documented changes only in stage 6).
- Single PR from `ai-refactor` with stage-by-stage commits.
