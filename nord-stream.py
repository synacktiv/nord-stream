#!/usr/bin/env python3
"""
CICD pipeline exploitation tool

Usage:
    nord-stream.py <command> [<args>...]

Commands
    github                                  command related to GitHub.
    devops                                  command related to Azure DevOps.
    gitlab                                  command related to GitLab.

Options:
    -h --help                               Show this screen.
    --version                               Show version.

Authors: @hugow @0hexit
"""

from docopt import docopt
from nordstream.utils.log import logger


if __name__ == "__main__":
    args = docopt(__doc__, version="0.1", options_first=True)

    argv = [args["<command>"]] + args["<args>"]

    if args["<command>"] == "github":
        import nordstream.commands.github as github

        github.start(argv)
    elif args["<command>"] == "devops":
        import nordstream.commands.devops as devops

        devops.start(argv)
    elif args["<command>"] == "gitlab":
        import nordstream.commands.gitlab as gitlab

        gitlab.start(argv)
    else:
        logger.error(f"{args['<command>']} is not a nord-stream.py command.")
