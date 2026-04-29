#!/usr/bin/env python3
"""
CICD pipeline exploitation tool

Usage:
    nord-stream <command> [<args>...]

Commands
    github                                  command related to GitHub.
    devops                                  command related to Azure DevOps.
    gitlab                                  command related to GitLab.
    circleci                                command related to CircleCI (standalone, no git required).

Options:
    -h --help                               Show this screen.
    --version                               Show version.

Authors: @hugow @0hexit
"""

from docopt import docopt
from nordstream.utils.log import logger


def main():
    args = docopt(__doc__, version="0.1", options_first=True)

    argv = [args["<command>"]] + args["<args>"]

    # Command modules are imported lazily here to keep startup fast and avoid
    # loading heavy dependencies (requests, yaml, etc.) for commands not invoked.
    if args["<command>"] == "github":
        import nordstream.commands.github as github

        github.start(argv)
    elif args["<command>"] == "devops":
        import nordstream.commands.devops as devops

        devops.start(argv)
    elif args["<command>"] == "gitlab":
        import nordstream.commands.gitlab as gitlab

        gitlab.start(argv)
    elif args["<command>"] == "circleci":
        import nordstream.commands.circleci as circleci

        circleci.start(argv)
    else:
        logger.critical(f"{args['<command>']} is not a nord-stream command.")


if __name__ == "__main__":
    main()
