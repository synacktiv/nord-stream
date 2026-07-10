# Contributing

Thanks for taking the time to contribute to Nord Stream! This guide covers how
to set up a development environment, run the tests, follow the code style, and
open a good pull request.

## Table of Contents

- [Getting started](#getting-started)
- [Running the tests](#running-the-tests)
- [Code style & pre-commit hooks](#code-style--pre-commit-hooks)
- [Conventional commits](#conventional-commits)
- [Project architecture](#project-architecture)
- [Adding support for a new platform](#adding-support-for-a-new-platform)
- [Opening a pull request](#opening-a-pull-request)

## Getting started

Clone the repository and install the project in editable mode with its
development dependencies (`pytest`, `responses`):

```bash
git clone https://github.com/synacktiv/nord-stream
cd nord-stream

python -m venv venv
source venv/bin/activate          # on Windows: venv\Scripts\activate

pip install -e '.[dev]'
```

`git` must also be installed and available in your `PATH`.

## Running the tests

The test suite is **fully offline** — HTTP is mocked with
[`responses`](https://github.com/getsentry/responses), so no network access,
tokens, or real GitHub/GitLab/Azure DevOps accounts are required.

```bash
pytest                       # run everything
pytest -v                    # one line per test
pytest -x                    # stop at the first failure
pytest -k secrets            # only tests whose name matches "secrets"

pytest tests/cicd/           # API clients (mocked HTTP)
pytest tests/parsers/        # pure data-manipulation functions
pytest tests/yaml/           # generated-pipeline snapshot tests
```

Configuration lives in `pyproject.toml` under `[tool.pytest.ini_options]`;
tests are auto-discovered under `tests/`.

**Please add or update tests when you change behavior.** The test layers that
should stay green (and grow) are:

- `tests/parsers/` — pure functions that turn API JSON/bytes into usable data.
- `tests/yaml/` — snapshot tests locking the generated malicious pipelines.
- `tests/cicd/` — clients tested against mocked HTTP responses.

## Code style & pre-commit hooks

Code is formatted with [Black](https://black.readthedocs.io/) using a line
length of **120**:

```bash
black --line-length 120 nordstream/ tests/
```

Install the [`pre-commit`](https://pre-commit.com/) hooks so formatting and the
commit-message format are checked automatically:

```bash
pip install pre-commit
pre-commit install                          # format / lint on commit
pre-commit install --hook-type commit-msg   # validate the commit message
```

You can run all hooks manually against the whole tree at any time:

```bash
pre-commit run --all-files
```

## Conventional commits

Commit messages **must** follow the
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) spec —
this is enforced by the `commit-msg` hook. The format is:

```
<type>(<optional scope>): <description>
```

Allowed types: `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`,
`refactor`, `revert`, `style`, `test`.

Examples:

```
feat(gitlab): add unprivileged runner enumeration
fix(devops): handle 403 when listing variable groups
refactor(core): hoist shared git-push logic into BaseRunner
docs: document the --list-runners option
test(github): cover dependabot secret listing
```

## Project architecture

Nord Stream is organised into layers with a single responsibility each, so that
fetching, manipulating, and displaying data stay separate. When adding code,
put it in the layer that matches its responsibility:

| Package | Responsibility |
|---|---|
| `nordstream/commands/` + `nordstream/cli/` | CLI entry points (docopt) and shared argument setup. |
| `nordstream/core/` | Orchestration — the deploy/extract/clean lifecycle. `core/base.py` (`BaseRunner`) holds logic shared by every platform. |
| `nordstream/cicd/` | HTTP API clients. `cicd/base.py` (`BaseClient`) holds the shared session/auth scaffolding; one subclass per platform. **No display logic here.** |
| `nordstream/parsers/` | Pure functions that turn raw API responses into usable data. **No I/O, no logging.** |
| `nordstream/report/` | Display only — formats already-fetched data via the logger. |
| `nordstream/yaml/` | Generators that build the malicious pipeline YAML. |
| `nordstream/utils/` | Logging, helpers, constants, errors. |
| `nordstream/git.py` | Thin wrapper around the `git` CLI. |

Rules of thumb enforced in review:

- `cicd/` must not format output for display (no user-facing `logger` calls for
  data); return raw data instead.
- `parsers/` must be pure — no network, no file/logging side effects — so it is
  trivially unit-testable.
- `core/` orchestrates and must not build display strings itself; it calls
  `report/`.

## Adding support for a new platform

The shared base classes make new platforms mostly a matter of filling in the
platform-specific pieces:

1. `cicd/<platform>.py` — subclass `BaseClient`; implement the endpoints
   (list secrets, trigger pipeline, download output, clean logs).
2. `parsers/<platform>.py` — pure functions to decode/normalise responses,
   with tests in `tests/parsers/`.
3. `report/<platform>.py` — display functions that take data and print it.
4. `yaml/<platform>.py` — the pipeline generator(s), with snapshot tests in
   `tests/yaml/`.
5. `core/<platform>/<platform>.py` — subclass `BaseRunner` and wire the
   lifecycle, using `_pushCode()`, `_createLogDir()`, `_deleteRemoteBranch()`.
6. `commands/<platform>.py` — the docopt entry point; reuse
   `cli/common.py` for verbosity and git-identity setup.

## Opening a pull request

- Make sure `pytest` is green and `pre-commit run --all-files` passes.
- Keep commits conventional and focused.
- Describe what the change does and how you verified it.
- New extraction techniques and platform support are very welcome — if you hit
  an unsupported service-connection type or platform, an issue or PR is great.

Please submit bugs, questions, and feature requests under **Issues**.
