# Nord Stream Refactor — Plan 2: GitHub Pilot Migration

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Migrate the GitHub subsystem onto the layered architecture (fetch / manipulate / display / orchestrate) using the Plan 1 foundations, locking behavior with tests first. This is the reference pattern GitLab and DevOps will copy.

**Architecture:** Characterize-then-refactor. Each stage lands behavior-locking tests *before or with* the code move, stays green, and is committed. No real GitHub API is contacted — clients are tested with mocked HTTP (`responses`); the orchestration layer is verified with offline smoke tests (`import` + `nord-stream github --help`).

**Tech Stack:** Python 3, `requests`, `PyYAML`, `pytest`, `responses`, `black --line-length 120`, conventional commits.

## Global Constraints

- All work on `ai-refactor`. Formatter `black --line-length 120` before every commit.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- CLI behavior stays identical (Plan 2 does not change flags or output text).
- Layer rules: `cicd/` no display, `parsers/` no I/O, `report/` display only, `core/` no string-formatting for display.
- After every stage: `python -m pytest` green, `python -c "from nordstream.core.github.github import GitHubWorkflowRunner"` ok, `nord-stream github --help` exit 0.

## Offline smoke command (used as "does it still load" gate)

```bash
python -c "from nordstream.core.github.github import GitHubWorkflowRunner; from nordstream.commands import github" \
  && nord-stream github --help >/dev/null && echo SMOKE_OK
```

---

### Stage 1 — Characterization tests for the YAML generator (safety net, no code change)

Locks the exact generated pipeline YAML for all build types before anything is refactored.

**Files:**
- Create: `tests/yaml/__init__.py`, `tests/yaml/test_github_generator.py`

**Interfaces consumed:** `nordstream.yaml.github.WorkflowGenerator` with `generateWorkflowForSecretsExtraction(secrets, env=None)`, `generateWorkflowForOIDCAzureTokenGeneration(tenant, subscription, client, env=None)`, `generateWorkflowForOIDCAWSTokenGeneration(role, region, env=None)`, and `.defaultTemplate`.

- [ ] Write `tests/yaml/test_github_generator.py` asserting the produced `defaultTemplate` dict for: (a) repo secrets, (b) secrets + env, (c) Azure OIDC, (d) AWS OIDC. Assert on the dict structure (not YAML string) to avoid formatting brittleness. Each test constructs a fresh `WorkflowGenerator()`.
- [ ] Run `python -m pytest tests/yaml -v` → all pass (documents current behavior, including the shared-template quirk).
- [ ] `black` + commit: `test: characterize GitHub workflow YAML generation`.

---

### Stage 2 — Extract the "manipulate" layer → `nordstream/parsers/github.py`

The base64 double-decode of workflow output currently lives inside the runner's `__extractSensitiveInformationFromWorkflowResult`. Extract the pure logic.

**Files:**
- Create: `nordstream/parsers/__init__.py`, `nordstream/parsers/github.py`
- Create: `tests/parsers/__init__.py`, `tests/parsers/test_github.py`
- Modify: `nordstream/core/github/github.py` (use the parser)

**Produces:** `decode_workflow_secret_line(last_line: str) -> bytes` — takes the last line of the workflow output file (`"<label> <b64b64>"`), returns the doubly-base64-decoded bytes. Raises `ValueError` on malformed input.

- [ ] Write `tests/parsers/test_github.py`: round-trip a known secret (`base64(base64(b"secret_X=val"))`) → decodes back; malformed input raises `ValueError`.
- [ ] Run → fails (module missing).
- [ ] Implement `nordstream/parsers/github.py::decode_workflow_secret_line`.
- [ ] Run → passes.
- [ ] Refactor `__extractSensitiveInformationFromWorkflowResult` to read the last line and call `decode_workflow_secret_line`, keeping the same logging/file-write behavior.
- [ ] Smoke gate + full suite green.
- [ ] `black` + commit: `refactor(github): extract workflow-output decoding into parsers layer`.

---

### Stage 3 — Migrate `cicd/github.py` onto `BaseClient` + mocked-HTTP fetch tests

**Files:**
- Modify: `nordstream/cicd/github.py` (subclass `BaseClient`; drop duplicated `token/outputDir/branchName/defaultBranchName` properties and session creation)
- Create: `tests/cicd/test_github.py`

**Approach (conservative):** `class GitHub(BaseClient)`. Keep GitHub's own `_auth`/`_header` and all endpoint methods unchanged. Remove the now-inherited property/session boilerplate. `__init__` calls `super().__init__(token)` then sets GitHub-specific state (`_auth`, `_org`, GHS detection, login). Keep `_session`/`outputDir`/`branchName` usage working (they resolve to the base's).

- [ ] Write `tests/cicd/test_github.py` with `responses`: `listSecretsFromRepo` parses `{"secrets":[{"name":...}]}` across pagination; `listRepos` filters by org; `addRepo` raises `GitHubBadCredentials` on bad-credentials message. (Construct `GitHub` with a mocked login endpoint so `__init__` succeeds offline.)
- [ ] Run → fails where expected.
- [ ] Refactor `cicd/github.py` to subclass `BaseClient`.
- [ ] Run tests → pass. Smoke gate + full suite green.
- [ ] `black` + commit: `refactor(github): base GitHub client on BaseClient`.

---

### Stage 4 — Consolidate display into `nordstream/report/github.py`

Move `core/github/display.py` and the runner's private `__display*` secret-listing helpers into a single `report/` module so all GitHub display lives in one layer.

**Files:**
- Create: `nordstream/report/__init__.py`, `nordstream/report/github.py` (content of current `display.py` + the `__display*` helpers rewritten as module functions taking `cicd`)
- Modify: `nordstream/core/github/github.py` (import from `report.github`; delete moved helpers)
- Delete: `nordstream/core/github/display.py`
- Modify: `nordstream/core/github/protections.py` import site if needed

- [ ] Move display functions; rewrite the four `__displayRepoSecrets/__displayEnvSecrets/__displayOrgSecrets/__displayDependabotOrgSecrets` as `report.github` functions receiving `cicd`.
- [ ] Update runner to call the `report.github` functions.
- [ ] Smoke gate + full suite green.
- [ ] `black` + commit: `refactor(github): move all display into report layer`.

---

### Stage 5 — Extract `BaseRunner` lifecycle + wire `RunnerConfig` (capstone, review closely)

Extract the push→wait→download→post-process lifecycle into `nordstream/core/base.py::BaseRunner` with platform hooks; `GitHubWorkflowRunner` subclasses it. This is the highest-risk stage (no network unit-test possible) and is the pattern GitLab/DevOps inherit — flagged for close human review.

**Files:**
- Create: `nordstream/core/base.py`
- Modify: `nordstream/core/github/github.py`

**Produces `BaseRunner`:** holds a `RunnerConfig`; provides the generic `_launch_and_process(repo, generator, output_name, env)` skeleton calling abstract hooks `_launch(repo, generator)`, `_wait(repo)`, `_download(repo, name, workflow_id)`, `_post_process(...)` implemented by subclasses. Exact hook signatures finalized against the GitHub implementation during this stage.

- [ ] Extract the lifecycle keeping GitHub behavior identical; replace the `_env`/flag properties with reads from a `RunnerConfig` where mechanical.
- [ ] Smoke gate + full suite green.
- [ ] `black` + commit: `refactor(github): extract BaseRunner lifecycle and wire RunnerConfig`.
- [ ] STOP and report to human before replicating to GitLab/DevOps.

---

## Self-Review

- **Spec coverage:** fetch→Stage 3, manipulate→Stage 2, display→Stage 4, orchestrate/shared-core→Stage 5, tests (YAML+parser+client)→Stages 1/2/3. All spec test categories covered for GitHub.
- **Placeholder scan:** Stages 1–4 are fully specified with concrete files and gates. Stage 5's hook signatures are explicitly "finalized against the implementation" — a deliberate, disclosed emergent step for the risky capstone, not a hidden TODO.
- **Risk:** ordering puts safety-net tests first; every stage has an offline gate; the one un-unit-testable stage (5) is isolated, last, and flagged for review.
