# Nord Stream Refactor — Plan 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the shared, tested infrastructure for the modular refactor — a pytest harness, config dataclasses that replace hand-written property boilerplate, and a `BaseClient` that consolidates the duplicated HTTP/session/property scaffolding across the three platform clients.

**Architecture:** This is the first of several plans (see `docs/superpowers/specs/2026-07-08-nord-stream-modular-refactor-design.md`). It builds only genuinely-shared foundations that all three platforms will later sit on. Platform migrations (GitHub, GitLab, DevOps) and the `BaseRunner` lifecycle base are separate plans, written against the real code as each is reached. The `BaseRunner` shape is intentionally deferred: it is derived during the GitHub migration, once the lifecycle is visible in one concrete implementation rather than guessed up front.

**Tech Stack:** Python 3, `requests`, `dataclasses` (stdlib), `pytest`, `responses` (HTTP mocking). Formatting: `black --line-length 120`. Conventional commits.

## Global Constraints

- Formatter: `black --line-length 120` — run before every commit.
- Commit style: conventional commits (`feat`, `fix`, `refactor`, `test`, `chore`, `docs`, …).
- Commit message trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Branch: all work on `ai-refactor` (already checked out).
- No behavior change to the running tool in this plan — it adds new, unused modules and test infrastructure only. Existing `nordstream/` runtime code is not modified.
- New modules must not import `logger` for data display and must not perform network I/O in `config.py` (layer rules from the spec).
- Package layout: new shared modules live at `nordstream/config.py` and `nordstream/cicd/base.py`. Tests live under `tests/` mirroring the package.

---

### Task 1: Test harness + dev dependencies

Stand up pytest so later tasks have a place to put tests. Deliverable: `pytest` runs green on a trivial smoke test.

**Files:**
- Modify: `pyproject.toml` (add dev optional-deps + pytest config)
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`
- Modify: `.gitignore` (ignore pytest/coverage caches)

**Interfaces:**
- Consumes: nothing.
- Produces: a working `pytest` invocation; the `tests/` package root that every later task adds to.

- [ ] **Step 1: Add dev dependencies and pytest config to `pyproject.toml`**

Append these two sections to `pyproject.toml` (after the existing `[project.scripts]` block):

```toml
[project.optional-dependencies]
dev = ["pytest", "responses"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-ra"
```

- [ ] **Step 2: Create the tests package with a smoke test**

Create `tests/__init__.py` (empty file).

Create `tests/test_smoke.py`:

```python
def test_package_imports():
    import nordstream

    assert nordstream is not None
```

- [ ] **Step 3: Ignore test caches**

Append to `.gitignore`:

```
.pytest_cache/
.coverage
htmlcov/
```

- [ ] **Step 4: Install dev deps and run the smoke test**

Run:
```bash
pip install -e '.[dev]'
python -m pytest tests/test_smoke.py -v
```
Expected: `1 passed`.

- [ ] **Step 5: Format and commit**

```bash
black --line-length 120 tests/
git add pyproject.toml tests/ .gitignore
git commit -m "test: add pytest harness and dev dependencies

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Config dataclasses

Replace the scattered, hand-written config state with two dataclasses. This task adds them + tests only; wiring platforms onto them happens in the platform plans. Fields and defaults are copied from the current code (`nordstream/utils/constants.py`, `nordstream/git.py`, and the runner property blocks).

**Files:**
- Create: `nordstream/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: constants from `nordstream/utils/constants.py` (`OUTPUT_DIR`, `DEFAULT_BRANCH_NAME`, `GIT_USER`, `GIT_EMAIL`).
- Produces:
  - `CommitIdentity(user: str = GIT_USER, email: str = GIT_EMAIL, key_id: str | None = None)`
  - `RunnerConfig(branch_name: str = DEFAULT_BRANCH_NAME, output_dir: str = OUTPUT_DIR, clean_logs: bool = True, write_access_filter: bool = False, force_deploy: bool = False, sleep_time: int = 15, max_retry: int = 10, yaml_path: str | None = None, commit: CommitIdentity = <default CommitIdentity>)`
  - These are the shared fields only. Platform-specific extraction toggles (e.g. GitHub `extract_repo/env/org`, DevOps service-connection flags) are added in each platform's own plan, not here.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from nordstream.config import CommitIdentity, RunnerConfig
from nordstream.utils.constants import OUTPUT_DIR, DEFAULT_BRANCH_NAME, GIT_USER, GIT_EMAIL


def test_commit_identity_defaults():
    identity = CommitIdentity()
    assert identity.user == GIT_USER
    assert identity.email == GIT_EMAIL
    assert identity.key_id is None


def test_runner_config_defaults():
    config = RunnerConfig()
    assert config.branch_name == DEFAULT_BRANCH_NAME
    assert config.output_dir == OUTPUT_DIR
    assert config.clean_logs is True
    assert config.write_access_filter is False
    assert config.force_deploy is False
    assert config.sleep_time == 15
    assert config.max_retry == 10
    assert config.yaml_path is None
    assert isinstance(config.commit, CommitIdentity)
    assert config.commit.user == GIT_USER


def test_runner_config_is_mutable_and_overridable():
    config = RunnerConfig(branch_name="feature/x", clean_logs=False)
    assert config.branch_name == "feature/x"
    assert config.clean_logs is False
    config.output_dir = "/tmp/out"
    assert config.output_dir == "/tmp/out"


def test_each_runner_config_gets_its_own_commit_identity():
    a = RunnerConfig()
    b = RunnerConfig()
    a.commit.user = "changed"
    assert b.commit.user == GIT_USER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nordstream.config'`.

- [ ] **Step 3: Write minimal implementation**

Create `nordstream/config.py`:

```python
from dataclasses import dataclass, field

from nordstream.utils.constants import (
    OUTPUT_DIR,
    DEFAULT_BRANCH_NAME,
    GIT_USER,
    GIT_EMAIL,
)


@dataclass
class CommitIdentity:
    """Identity used when the tool creates git commits."""

    user: str = GIT_USER
    email: str = GIT_EMAIL
    key_id: str = None


@dataclass
class RunnerConfig:
    """Configuration shared by every platform runner.

    Platform-specific toggles are added by composing additional dataclasses
    in each platform's module; this holds only the common fields.
    """

    branch_name: str = DEFAULT_BRANCH_NAME
    output_dir: str = OUTPUT_DIR
    clean_logs: bool = True
    write_access_filter: bool = False
    force_deploy: bool = False
    sleep_time: int = 15
    max_retry: int = 10
    yaml_path: str = None
    commit: CommitIdentity = field(default_factory=CommitIdentity)
```

Note: `commit` uses `field(default_factory=CommitIdentity)` so each `RunnerConfig` gets its own identity instance (this is what `test_each_runner_config_gets_its_own_commit_identity` verifies — a plain default would share one instance across all configs).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: `4 passed`.

- [ ] **Step 5: Format and commit**

```bash
black --line-length 120 nordstream/config.py tests/test_config.py
git add nordstream/config.py tests/test_config.py
git commit -m "feat: add shared config dataclasses

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: BaseClient (shared HTTP/session scaffolding)

Consolidate the property/session boilerplate duplicated across `cicd/github.py`, `cicd/gitlab.py`, `cicd/devops.py` into a base class. Platform clients will subclass this in their own plans; this task adds the base + tests only and does not yet modify the existing clients.

**Files:**
- Create: `nordstream/cicd/base.py`
- Create: `tests/cicd/__init__.py`
- Create: `tests/cicd/test_base.py`

**Interfaces:**
- Consumes: `requests`, `nordstream.utils.constants` (`OUTPUT_DIR`, `DEFAULT_BRANCH_NAME`, `USER_AGENT`).
- Produces `BaseClient` with:
  - `__init__(self, token: str)` — stores `token`, creates a `requests.Session`, sets `outputDir=OUTPUT_DIR`, `branchName=DEFAULT_BRANCH_NAME`.
  - properties: `token` (read-only), `session` (read-only), `outputDir` (read/write), `branchName` (read/write), `defaultBranchName` (read-only, returns `DEFAULT_BRANCH_NAME`).
  - `_get(self, url, **kwargs) -> requests.Response` — `self.session.get(url, **kwargs)`.
  - `_post(self, url, **kwargs) -> requests.Response` — `self.session.post(url, **kwargs)`.
  - class attribute `_defaultHeaders = {"User-Agent": USER_AGENT}` applied to the session's headers in `__init__`.

  Property names deliberately match the existing camelCase (`outputDir`, `branchName`, `defaultBranchName`) so platform clients can inherit them without changing their many call sites. The internal config from Task 2 uses snake_case; the CLI layer bridges the two in a later plan.

- [ ] **Step 1: Write the failing test**

Create `tests/cicd/__init__.py` (empty file).

Create `tests/cicd/test_base.py`:

```python
import responses

from nordstream.cicd.base import BaseClient
from nordstream.utils.constants import OUTPUT_DIR, DEFAULT_BRANCH_NAME, USER_AGENT


def test_init_sets_defaults():
    client = BaseClient("tok123")
    assert client.token == "tok123"
    assert client.outputDir == OUTPUT_DIR
    assert client.branchName == DEFAULT_BRANCH_NAME
    assert client.defaultBranchName == DEFAULT_BRANCH_NAME


def test_output_dir_and_branch_are_writable():
    client = BaseClient("tok")
    client.outputDir = "/tmp/logs"
    client.branchName = "feature/y"
    assert client.outputDir == "/tmp/logs"
    assert client.branchName == "feature/y"


def test_default_branch_name_is_read_only():
    client = BaseClient("tok")
    # defaultBranchName has no setter
    import pytest

    with pytest.raises(AttributeError):
        client.defaultBranchName = "nope"


def test_session_sends_user_agent_header():
    client = BaseClient("tok")
    assert client.session.headers["User-Agent"] == USER_AGENT


@responses.activate
def test_get_issues_request_and_returns_response():
    responses.add(responses.GET, "https://example.test/data", json={"ok": True}, status=200)
    client = BaseClient("tok")
    resp = client._get("https://example.test/data")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@responses.activate
def test_post_issues_request_and_returns_response():
    responses.add(responses.POST, "https://example.test/submit", json={"id": 1}, status=201)
    client = BaseClient("tok")
    resp = client._post("https://example.test/submit", json={"x": 1})
    assert resp.status_code == 201
    assert resp.json() == {"id": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cicd/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nordstream.cicd.base'`.

- [ ] **Step 3: Write minimal implementation**

Create `nordstream/cicd/base.py`:

```python
import requests

from nordstream.utils.constants import OUTPUT_DIR, DEFAULT_BRANCH_NAME, USER_AGENT


class BaseClient:
    """Shared HTTP/session scaffolding for platform CI/CD clients.

    Owns the session and the config properties that were previously
    re-declared in each platform client. Subclasses implement the
    platform-specific endpoints; this base performs no display and holds
    no orchestration logic.
    """

    _defaultHeaders = {"User-Agent": USER_AGENT}

    def __init__(self, token):
        self._token = token
        self._session = requests.Session()
        self._session.headers.update(self._defaultHeaders)
        self._outputDir = OUTPUT_DIR
        self._branchName = DEFAULT_BRANCH_NAME

    @property
    def token(self):
        return self._token

    @property
    def session(self):
        return self._session

    @property
    def outputDir(self):
        return self._outputDir

    @outputDir.setter
    def outputDir(self, value):
        self._outputDir = value

    @property
    def branchName(self):
        return self._branchName

    @branchName.setter
    def branchName(self, value):
        self._branchName = value

    @property
    def defaultBranchName(self):
        return DEFAULT_BRANCH_NAME

    def _get(self, url, **kwargs):
        return self._session.get(url, **kwargs)

    def _post(self, url, **kwargs):
        return self._session.post(url, **kwargs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/cicd/test_base.py -v`
Expected: `6 passed`.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: all tests pass (smoke + config + base = 11 tests).

- [ ] **Step 6: Format and commit**

```bash
black --line-length 120 nordstream/cicd/base.py tests/cicd/
git add nordstream/cicd/base.py tests/cicd/
git commit -m "feat: add BaseClient for shared HTTP/session scaffolding

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage (this plan's slice = spec stages 1 & 2, foundation portion):**
- Spec "Scaffold" stage → Task 1 (pytest/responses harness + config). `models/`, `parsers/`, `report/`, `cli/` package scaffolding is deferred to the platform plans that first need them (YAGNI — creating empty packages now adds nothing testable). Noted as an intentional deviation in the handoff.
- Spec "Shared base + config" stage → Task 2 (`config.py` dataclasses) + Task 3 (`BaseClient`). `BaseRunner` is intentionally deferred to the GitHub plan (stated in Architecture) — derived from a concrete implementation rather than guessed.
- Spec test scope (parsers, YAML, mocked clients) → this plan sets up the harness and demonstrates the mocked-HTTP pattern (`responses`) that the client tests use; parser and YAML suites land in the platform plans alongside the code they cover.

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N". All code is complete and inline.

**Type consistency:** `CommitIdentity` / `RunnerConfig` field names are used identically in Task 2's tests and implementation. `BaseClient` property names (`token`, `session`, `outputDir`, `branchName`, `defaultBranchName`) match between the interface block, Task 3's tests, and implementation. `RunnerConfig.commit` uses `field(default_factory=CommitIdentity)`, consistent with the isolation test.

**Scope check:** Foundation only — no existing runtime module is modified, so the tool keeps working throughout. Each task ends in an independently testable, committable deliverable.
