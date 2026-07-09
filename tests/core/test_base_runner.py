"""Tests for the shared BaseRunner.

These verify the common bookkeeping/state contract and that every platform
runner inherits it. The remote-branch deletion itself shells out to git and is
exercised only structurally here (via a fake cicd) to confirm return-value
semantics without touching a real repo.
"""

from unittest.mock import patch, MagicMock

from nordstream.core.base import BaseRunner


class _FakeCICD:
    branchName = "dev_remote/test"


def test_init_sets_shared_state():
    runner = BaseRunner(_FakeCICD())
    assert runner._pushedCommitsCount == 0
    assert runner._branchAlreadyExists is False


def test_delete_remote_branch_returns_true_on_success():
    runner = BaseRunner(_FakeCICD())
    proc = MagicMock()
    proc.returncode = 0
    with patch("nordstream.core.base.Git.gitDeleteRemote", return_value=proc):
        assert runner._deleteRemoteBranch() is True


def test_delete_remote_branch_returns_false_on_failure():
    runner = BaseRunner(_FakeCICD())
    proc = MagicMock()
    proc.returncode = 1
    proc.communicate.return_value = (b"", b"error")
    with patch("nordstream.core.base.Git.gitDeleteRemote", return_value=proc):
        assert runner._deleteRemoteBranch() is False


def test_all_platform_runners_subclass_base_runner():
    from nordstream.core.github.github import GitHubWorkflowRunner
    from nordstream.core.gitlab.gitlab import GitLabRunner
    from nordstream.core.devops.devops import DevOpsRunner

    assert issubclass(GitHubWorkflowRunner, BaseRunner)
    assert issubclass(GitLabRunner, BaseRunner)
    assert issubclass(DevOpsRunner, BaseRunner)
