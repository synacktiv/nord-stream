import logging
from os import makedirs
from os.path import realpath

from nordstream.git import Git
from nordstream.utils.log import logger


class BaseRunner:
    """Shared state and helpers for the platform workflow/pipeline runners.

    Holds the deploy-loop bookkeeping and config common to every platform, plus
    the identical log-dir creation and remote-branch cleanup. Platform-specific
    orchestration (push/wait/trigger, protections, output extraction) stays in
    the subclasses, where it genuinely differs.
    """

    # Config shared by every platform (plain public attributes — set by the CLI).
    writeAccessFilter = False
    cleanLogs = True

    _yaml = None

    def __init__(self, cicd):
        self._cicd = cicd
        self._fileName = None
        self._pushedCommitsCount = 0
        self._branchAlreadyExists = False

    @property
    def yaml(self):
        return self._yaml

    @yaml.setter
    def yaml(self, value):
        # resolved eagerly so a later chdir() during deployment can't change it
        self._yaml = realpath(value)

    def _createLogDir(self, subdir):
        self._cicd.outputDir = realpath(self._cicd.outputDir) + f"/{subdir}"
        makedirs(self._cicd.outputDir, exist_ok=True)

    def _pushCode(self):
        """Push the working tree to the deployment branch.

        Returns True on a successful push (and bumps the pushed-commit counter),
        or False when the branch is already up to date or the push failed.
        Callers that require the push to happen (e.g. GitHub) raise on False.
        """
        pushOutput = Git.gitPush(self._cicd.branchName)
        pushOutput.wait()
        stderr = pushOutput.communicate()[1]

        if b"Everything up-to-date" in stderr.strip():
            logger.error("Error when pushing code: Everything up-to-date")
            logger.warning("Your trying to push the same code on an existing branch, modify the yaml file to push it.")
            return False

        if pushOutput.returncode != 0:
            logger.error("Error when pushing code:")
            logger.raw(stderr, logging.INFO)
            return False

        self._pushedCommitsCount += 1
        logger.raw(stderr)
        return True

    def _deleteRemoteBranch(self):
        logger.verbose("Deleting remote branch")
        deleteOutput = Git.gitDeleteRemote(self._cicd.branchName)
        deleteOutput.wait()

        if deleteOutput.returncode != 0:
            logger.error(f"Error deleting remote branch {self._cicd.branchName}")
            logger.raw(deleteOutput.communicate()[1], logging.INFO)
            return False
        return True
