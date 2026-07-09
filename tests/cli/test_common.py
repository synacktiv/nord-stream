import logging

import pytest

from nordstream.cli.common import configureVerbosity, configureGitIdentity
from nordstream.git import Git
from nordstream.utils.log import logger, NordStreamLog


def _args(**overrides):
    base = {
        "--verbose": False,
        "--debug": False,
        "--key-id": None,
        "--user": None,
        "--email": None,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _restore_state():
    level = logger.level
    user, email, key = Git.USER, Git.EMAIL, Git.KEY_ID
    yield
    logger.setLevel(level)
    Git.USER, Git.EMAIL, Git.KEY_ID = user, email, key


def test_verbose_sets_verbose_level():
    configureVerbosity(_args(**{"--verbose": True}))
    assert logger.level == NordStreamLog.VERBOSE


def test_debug_sets_debug_level():
    configureVerbosity(_args(**{"--debug": True}))
    assert logger.level == logging.DEBUG


def test_default_leaves_level_unchanged():
    logger.setLevel(logging.INFO)
    configureVerbosity(_args())
    assert logger.level == logging.INFO


def test_git_identity_applied_when_provided():
    configureGitIdentity(_args(**{"--user": "alice", "--email": "a@x", "--key-id": "KID"}))
    assert Git.USER == "alice"
    assert Git.EMAIL == "a@x"
    assert Git.KEY_ID == "KID"


def test_git_identity_untouched_when_absent():
    Git.USER = "sentinel"
    configureGitIdentity(_args())
    assert Git.USER == "sentinel"
