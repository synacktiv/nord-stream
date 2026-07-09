"""Config-API tests for the runners after the property->attribute cleanup.

They confirm the plain public config attributes work, the shared BaseRunner
defaults are inherited, and the one property that still carries logic (`yaml`,
which resolves to an absolute path) behaves correctly.
"""

import os


class _FakeCICD:
    """Minimal stand-in: runners only touch ``outputDir`` during construction."""

    def __init__(self, output_dir):
        self.outputDir = output_dir


def test_github_runner_config(tmp_path):
    from nordstream.core.github.github import GitHubWorkflowRunner

    runner = GitHubWorkflowRunner(_FakeCICD(str(tmp_path)), env=None)

    # platform config defaults (plain public attributes)
    assert runner.extractRepo is True
    assert runner.exploitOIDC is False
    runner.extractRepo = False
    runner.tenantId = "tid"
    assert runner.extractRepo is False
    assert runner.tenantId == "tid"

    # shared BaseRunner config
    assert runner.cleanLogs is True
    assert runner.writeAccessFilter is False

    # yaml property still resolves to an absolute path
    runner.yaml = "pipeline.yml"
    assert os.path.isabs(runner.yaml)
    assert runner.yaml.endswith("pipeline.yml")


def test_createlogdir_appends_platform_subdir(tmp_path):
    from nordstream.core.github.github import GitHubWorkflowRunner

    cicd = _FakeCICD(str(tmp_path))
    GitHubWorkflowRunner(cicd, env=None)
    assert cicd.outputDir.endswith("/github")
    assert os.path.isdir(cicd.outputDir)
