"""
CICD pipeline exploitation tool

Usage:
    nord-stream circleci [options] --circleci-token <cct> --org <org> [--repo <repo> --no-repo --no-org --no-clean --vcs <vcs> --git-token <tok> --git-url <url>]
    nord-stream circleci [options] --circleci-token <cct> --org <org> --yaml <yaml> [--repo <repo> --no-clean --vcs <vcs> --git-token <tok> --git-url <url>]
    nord-stream circleci [options] --circleci-token <cct> --org <org> --list-secrets [--repo <repo> --no-repo --no-org --vcs <vcs>]
    nord-stream circleci [options] --circleci-token <cct> --describe-token

Options:
    -h --help                Show this screen.
    --version                Show version.
    -v, --verbose            Verbose mode
    -d, --debug              Debug mode
    --output-dir <dir>       Output directory for logs

args:
    --circleci-token <cct>   CircleCI API token
    --org <org>              CircleCI org slug or UUID
    --git-token <tok>        GitHub or GitLab PAT for the VCS contents API.
                             Required for extraction. Not needed for --list-secrets.
    --git-url <url>          Override git API base URL.
                             Default: https://api.github.com for gh/circleci vcs;
                             https://gitlab.com for gl vcs.
    --vcs <vcs>              CircleCI VCS type: gh, gl, or circleci (default: circleci)
    --repo <repo>            Target a single project by name or UUID.
                             If omitted, all projects under --org are discovered.
    --no-repo                Don't extract project environment variables.
    --no-org                 Don't extract org-level contexts.
    -y, --yaml <yaml>        Inject a custom CircleCI pipeline YAML file.
    --no-clean               Don't delete the config file or pipeline definition.
    --list-secrets           List secret names only (no git token required).
    --describe-token         Display CircleCI token and org information.

Examples:
    Describe the CircleCI token
    $ nord-stream circleci --circleci-token "$CCT" --describe-token

    List all CircleCI secrets for an org (no git token needed)
    $ nord-stream circleci --circleci-token "$CCT" --org H3xy1JwUnkBcQApbzLKwzq --list-secrets

    Extract secrets from all projects under an org
    $ nord-stream circleci --circleci-token "$CCT" --org H3xy1JwUnkBcQApbzLKwzq --git-token "$GHP"

    Extract secrets from a single project
    $ nord-stream circleci --circleci-token "$CCT" --org H3xy1JwUnkBcQApbzLKwzq --git-token "$GHP" --repo RZ3kVnuJPyfqHsaSrRhcCK

    Extract secrets from a classic GitHub OAuth project
    $ nord-stream circleci --circleci-token "$CCT" --org myorg --git-token "$GHP" --vcs gh

    Extract secrets from a GitLab-hosted project
    $ nord-stream circleci --circleci-token "$CCT" --org mygroup --git-token "$GLPAT" --vcs gl

Authors: @hugow @0hexit
"""

from docopt import docopt
from nordstream.cicd.circleci import CircleCI
from nordstream.core.circleci.standalone import CircleCIStandaloneRunner
from nordstream.utils.log import logger, NordStreamLog


def start(argv):
    args = docopt(__doc__, argv=argv)

    if args["--verbose"]:
        NordStreamLog.setVerbosity(verbose=1)
    if args["--debug"]:
        NordStreamLog.setVerbosity(verbose=2)

    logger.debug(args)

    # --- Validate CircleCI token ---
    circleCIToken = args["--circleci-token"]
    if not CircleCI.checkToken(circleCIToken):
        logger.critical("Invalid CircleCI token.")

    circleCIClient = CircleCI(circleCIToken)
    if args["--output-dir"]:
        circleCIClient.outputDir = args["--output-dir"] + "/"

    # --- describe-token needs nothing else ---
    if args["--describe-token"]:
        runner = CircleCIStandaloneRunner(
            circleCicd=circleCIClient,
            gitClient=None,
            vcsType="circleci",
            org="",
            gitOrg="",
        )
        runner.describeToken()
        return

    # --- Everything else requires --org ---
    org = args["--org"]
    if not org:
        logger.critical("--org is required.")

    vcsType = args["--vcs"] or "circleci"
    if vcsType not in ("gh", "gl", "circleci"):
        logger.critical(f"Invalid --vcs value '{vcsType}'. Must be gh, gl, or circleci.")

    # --- Build git client if --git-token is provided ---
    gitClient = None
    gitOrg = org  # default: use CircleCI org name as git org name

    if args["--git-token"]:
        gitToken = args["--git-token"]
        gitApiUrl = args["--git-url"]

        if vcsType == "gl":
            # GitLab client
            from nordstream.cicd.gitlab import GitLab
            gitLabUrl = gitApiUrl or "https://gitlab.com"
            if not GitLab.checkToken(gitToken, gitLabUrl):
                logger.critical("Invalid GitLab token.")
            gitClient = GitLab(gitLabUrl, gitToken)
        else:
            # GitHub client (for both "gh" and "circleci" vcsType)
            from nordstream.cicd.github import GitHub
            if not GitHub.checkToken(gitToken):
                logger.critical("Invalid GitHub token.")
            gitClient = GitHub(gitToken)
            if gitApiUrl:
                # Allow overriding the GitHub API base URL for GHES
                gitClient._repoURL = gitApiUrl.rstrip("/") + "/repos"
            # Use GitHub org name from token if available, else fall back to org arg
            gitOrg = org

    # --- Extraction requires a git client ---
    if not args["--list-secrets"] and gitClient is None:
        logger.critical(
            "--git-token is required for secret extraction. "
            "Use --list-secrets to list secret names without a git token."
        )

    # --- Build runner ---
    runner = CircleCIStandaloneRunner(
        circleCicd=circleCIClient,
        gitClient=gitClient,
        vcsType=vcsType,
        org=org,
        gitOrg=gitOrg,
    )

    if args["--no-repo"]:
        runner.extractProject = False
    if args["--no-org"]:
        runner.extractOrg = False
    if args["--no-clean"]:
        runner.cleanLogs = False
    if args["--yaml"]:
        runner.yaml = args["--yaml"]

    # --- Discover / load projects ---
    if not args["--describe-token"]:
        runner.loadProjects(repoOverride=args["--repo"])

    # --- Dispatch ---
    if args["--list-secrets"]:
        runner.listCircleCISecrets()
    else:
        runner.start()
