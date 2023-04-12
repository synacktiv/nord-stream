"""
CICD pipeline exploitation tool

Usage:
    nord-stream.py gitlab [options] --token <pat> [--url <gitlab_url>] [--project <project>]

Options:
    -h --help                               Show this screen.
    --version                               Show version.
    -v, --verbose                           Verbose mode
    -d, --debug                             Debug mode

args
    --token <pat>                           GitLab personal token
    --url <gitlab_url>                      Gitlab URL [default: https://gitlab.com]
    --project <project>                     Run on selected project (can be a file)
    --list-secrets                          List all secrets.
    --list-projects                         List all projects.
"""

from docopt import docopt
from nordstream.cicd.gitlab import GitLab
from nordstream.core.gitlab import GitLabRunner
from nordstream.utils.log import logger, NordStreamLog


def start(argv):
    args = docopt(__doc__, argv=argv)

    if args["--verbose"]:
        NordStreamLog.setVerbosity(verbose=1)
    if args["--debug"]:
        NordStreamLog.setVerbosity(verbose=2)

    logger.debug(args)

    # check validity of the token
    if not GitLab.checkToken(args["--token"], args["--url"]):
        logger.critical("Invalid token")

    # gitlab setup
    gitlab = GitLab(args["--url"], args["--token"])
    gitLabRunner = GitLabRunner(gitlab)

    gitLabRunner.getProjects(args["--project"])

    # # logic
    if args["--list-projects"]:
        gitLabRunner.listGitLabProjects()

    elif args["--list-secrets"]:
        gitLabRunner.listGitLabSecrets()

    else:
        gitLabRunner.runPipeline()
