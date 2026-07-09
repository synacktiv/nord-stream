"""Shared CLI setup used by every platform command.

These helpers remove the identical verbosity / git-identity plumbing that was
copy-pasted into each ``commands/*.py`` entry point.
"""

from nordstream.git import Git
from nordstream.utils.log import logger, NordStreamLog


def configureVerbosity(args):
    """Set the log level from ``--verbose`` / ``--debug`` and echo parsed args."""
    if args["--verbose"]:
        NordStreamLog.setVerbosity(verbose=1)
    if args["--debug"]:
        NordStreamLog.setVerbosity(verbose=2)

    logger.debug(args)


def configureGitIdentity(args):
    """Apply the commit identity (``--user`` / ``--email`` / ``--key-id``) to Git."""
    if args["--key-id"]:
        Git.KEY_ID = args["--key-id"]
    if args["--user"]:
        Git.USER = args["--user"]
    if args["--email"]:
        Git.EMAIL = args["--email"]
