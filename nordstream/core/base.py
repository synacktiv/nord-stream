import logging

from nordstream.git import Git
from nordstream.utils.log import logger


class BaseRunner:
    """Shared state and helpers for the platform workflow/pipeline runners.

    Holds the deploy-loop bookkeeping common to every platform and the identical
    remote-branch cleanup. Platform-specific orchestration (push/wait/trigger,
    protections, output extraction) stays in the subclasses, where it genuinely
    differs.
    """

    def __init__(self, cicd):
        self._cicd = cicd
        self._pushedCommitsCount = 0
        self._branchAlreadyExists = False

    def _deleteRemoteBranch(self):
        logger.verbose("Deleting remote branch")
        deleteOutput = Git.gitDeleteRemote(self._cicd.branchName)
        deleteOutput.wait()

        if deleteOutput.returncode != 0:
            logger.error(f"Error deleting remote branch {self._cicd.branchName}")
            logger.raw(deleteOutput.communicate()[1], logging.INFO)
            return False
        return True
