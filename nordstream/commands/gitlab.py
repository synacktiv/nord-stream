"""
CICD pipeline exploitation tool

Usage:
    nord-stream gitlab [options] --token <pat> (--list-secrets | --list-protections) [--project <project> --group <group> --no-project --no-group --no-instance --write-filter --sleep <seconds>]
    nord-stream gitlab [options] --token <pat> ( --list-groups | --list-projects | --list-users | --list-runners) [--project <project> --group <group> --write-filter]
    nord-stream gitlab [options] --token <pat> --yaml <yaml> --project <project> [--project-path <path> --no-clean]
    nord-stream gitlab [options] --token <pat> --clean-logs [--project <project>]
    nord-stream gitlab [options] --token <pat> --describe-token
    nord-stream gitlab [options] --token <pat> --circleci --project <project> [--no-project --no-org --branch-name <name> --no-clean]
    nord-stream gitlab [options] --token <pat> --circleci --yaml <yaml> --project <project> [--branch-name <name> --no-clean]
    nord-stream gitlab [options] --token <pat> --circleci --list-secrets [--project <project> --no-project --no-org]

Options:
    -h --help                               Show this screen.
    --version                               Show version.
    -v, --verbose                           Verbose mode
    -d, --debug                             Debug mode
    --output-dir <dir>                      Output directory for logs
    --url <gitlab_url>                      Gitlab URL [default: https://gitlab.com]
    --ignore-cert                           Allow insecure server connections
    --membership                            Limit by projects that the current user is a member of

Commit:
    --user <user>                           User used to commit
    --email <email>                         Email address used commit
    --key-id <id>                           GPG primary key ID to sign commits

args:
    --token <pat>                           GitLab personal access token or _gitlab_session cookie
    --project <project>                     Run on selected project (can be a file / project id)
    --group <group>                         Run on selected group (can be a file)
    --list-secrets                          List all secrets.
    --list-protections                      List branch protection rules.
    --list-projects                         List all projects.
    --list-groups                           List all groups.
    --list-users                            List all users.
    --list-runners                          List runners through project jobs (unprivileged, but non-exhaustive).
    --write-filter                          Filter repo where current user has developer access or more.
    --no-project                            Don't extract project secrets.
    --no-group                              Don't extract group secrets.
    --no-instance                           Don't extract instance secrets.
    --no-org                                Don't extract org-level CircleCI contexts (CircleCI mode only).
    -y, --yaml <yaml>                       Run arbitrary job
    --branch-name <name>                    Use specific branch name for deployment.
    --clean-logs                            Delete all pipeline logs created by this tool. This operation is done by default but can be manually triggered.
    --no-clean                              Don't clean pipeline logs (default false)
    --describe-token                        Display information on the token
    --sleep <seconds>                       Time to sleep in seconds between each secret request.
    --project-path <path>                   Local path of the git folder.
    --circleci                              Target CircleCI pipelines instead of GitLab CI
    --circleci-token <cct>                  CircleCI API token (required when --circleci is used)
    --circleci-vcs <vcs>                    CircleCI VCS type: 'gl', 'gh', or 'circleci' for GitHub App / GitLab App
                                            projects (default: gl)
    --circleci-org <org>                    CircleCI org name or ID (defaults to the GitLab group/namespace).
                                            Use the org UUID when --circleci-vcs circleci
    --circleci-project <project>            CircleCI project name or ID for a single target project.
                                            Use the project UUID when --circleci-vcs circleci

Examples:
    Dump all secrets
    $ nord-stream gitlab --token "$TOKEN" --url https://gitlab.local --list-secrets

    Deploy the custom pipeline on the master branch
    $ nord-stream gitlab --token "$TOKEN" --url https://gitlab.local --yaml exploit.yaml --branch master --project 'group/projectname'

    List CircleCI secrets for a GitLab-hosted project
    $ nord-stream gitlab --token "$TOKEN" --url https://gitlab.local --circleci --circleci-token "$CCT" --list-secrets --project 'group/projectname'

Authors: @hugow @0hexit
"""

from docopt import docopt
from nordstream.cicd.gitlab import GitLab
from nordstream.core.gitlab.gitlab import GitLabRunner
from nordstream.utils.log import logger, NordStreamLog
from nordstream.git import Git


def start(argv):
    args = docopt(__doc__, argv=argv)

    if args["--verbose"]:
        NordStreamLog.setVerbosity(verbose=1)
    if args["--debug"]:
        NordStreamLog.setVerbosity(verbose=2)

    logger.debug(args)

    # check validity of the token
    if not GitLab.checkToken(args["--token"], args["--url"], (not args["--ignore-cert"])):
        logger.critical('Invalid token or the token doesn\'t have the "api" scope.')

    # gitlab setup
    gitlab = GitLab(args["--url"], args["--token"], (not args["--ignore-cert"]))
    if args["--output-dir"]:
        gitlab.outputDir = args["--output-dir"] + "/"
    gitLabRunner = GitLabRunner(gitlab)

    if args["--key-id"]:
        Git.KEY_ID = args["--key-id"]
    if args["--user"]:
        Git.USER = args["--user"]
    if args["--email"]:
        Git.EMAIL = args["--email"]

    if args["--branch-name"]:
        gitlab.branchName = args["--branch-name"]
        logger.info(f'Using branch: "{gitlab.branchName}"')

    # config
    if args["--write-filter"]:
        gitLabRunner.writeAccessFilter = args["--write-filter"]
    if args["--no-project"]:
        gitLabRunner.extractProject = not args["--no-project"]
    if args["--no-group"]:
        gitLabRunner.extractGroup = not args["--no-group"]
    if args["--no-instance"]:
        gitLabRunner.extractInstance = not args["--no-instance"]
    if args["--no-clean"]:
        gitLabRunner.cleanLogs = not args["--no-clean"]
    if args["--yaml"]:
        gitLabRunner.yaml = args["--yaml"]
    if args["--sleep"]:
        gitLabRunner.sleepTime = args["--sleep"]
    if args["--project-path"]:
        gitLabRunner.localPath = args["--project-path"]

    # CircleCI mode — build a CircleCIRunner backed by the GitLab API client
    if args["--circleci"]:
        if not args["--circleci-token"]:
            logger.critical("--circleci-token is required when --circleci is used.")

        from nordstream.cicd.circleci import CircleCI
        from nordstream.core.circleci.circleci import CircleCIRunner

        if not CircleCI.checkToken(args["--circleci-token"]):
            logger.critical("Invalid CircleCI token.")

        circleCIClient = CircleCI(args["--circleci-token"])
        _circleCIVcs = args["--circleci-vcs"] or "gl"
        _circleCIOrg = args["--circleci-org"]  # caller must supply for gitlab
        _circleCIProject = args["--circleci-project"]
        # TODO: implement full GitLab-backed CircleCIRunner (vcsType="gl")
        # For now we raise a clear not-implemented message so the user knows
        # the feature is planned but not yet wired to GitLab-specific git ops.
        logger.critical(
            "CircleCI extraction via GitLab is not yet implemented. "
            "Please use the 'github' subcommand for CircleCI extraction on GitHub-hosted repositories."
        )
        return  # unreachable — logger.critical() calls exit(1)

    # logic
    if args["--describe-token"]:
        gitLabRunner.describeToken()

    elif args["--list-projects"]:
        gitLabRunner.getProjects(args["--project"], membership=args["--membership"])
        gitLabRunner.listGitLabProjects()

    elif args["--list-protections"]:
        gitLabRunner.getProjects(args["--project"], membership=args["--membership"])
        gitLabRunner.listBranchesProtectionRules()

    elif args["--list-groups"]:
        gitLabRunner.getGroups(args["--group"])
        gitLabRunner.listGitLabGroups()

    elif args["--list-users"]:
        gitLabRunner.listGitLabUsers()

    elif args["--list-runners"]:
        if gitLabRunner.extractProject:
            gitLabRunner.getProjects(args["--project"], membership=args["--membership"])
        if gitLabRunner.extractGroup:
            gitLabRunner.getGroups(args["--group"])

        gitLabRunner.listGitLabRunners()

    elif args["--list-secrets"]:
        if gitLabRunner.extractProject:
            gitLabRunner.getProjects(args["--project"], membership=args["--membership"])
        if gitLabRunner.extractGroup:
            gitLabRunner.getGroups(args["--group"])

        gitLabRunner.listGitLabSecrets()

    elif args["--clean-logs"]:
        gitLabRunner.getProjects(args["--project"], membership=args["--membership"])
        gitLabRunner.manualCleanLogs()

    else:
        gitLabRunner.getProjects(args["--project"], strict=True, membership=args["--membership"])
        gitLabRunner.runPipeline()
