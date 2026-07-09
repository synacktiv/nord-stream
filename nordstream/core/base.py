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

    def _deleteRemoteBranch(self):
        logger.verbose("Deleting remote branch")
        deleteOutput = Git.gitDeleteRemote(self._cicd.branchName)
        deleteOutput.wait()

        if deleteOutput.returncode != 0:
            logger.error(f"Error deleting remote branch {self._cicd.branchName}")
            logger.raw(deleteOutput.communicate()[1], logging.INFO)
            return False
        return True
