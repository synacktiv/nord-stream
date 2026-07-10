"""
CICD pipeline exploitation tool

Usage:
    nord-stream github [options] --token <ghp> --org <org> [--repo <repo> --no-repo --no-env --no-org --env <env> --disable-protections --branch-name <name> --no-clean]
    nord-stream github [options] --token <ghp> --org <org> --yaml <yaml> --repo <repo> [--env <env> --disable-protections --branch-name <name> --no-clean]
    nord-stream github [options] --token <ghp> --org <org> ([--clean-logs] [--clean-branch-policy]) [--repo <repo> --branch-name <name>]
    nord-stream github [options] --token <ghp> --org <org> --build-yaml <filename> --repo <repo> [--build-type <type> --env <env>]
    nord-stream github [options] --token <ghp> --org <org> --azure-tenant-id <tenant> --azure-client-id <client> [--repo <repo> --env <env> --disable-protections --branch-name <name> --no-clean]
    nord-stream github [options] --token <ghp> --org <org> --aws-role <role> --aws-region <region> [--repo <repo> --env <env> --disable-protections --branch-name <name> --no-clean]
    nord-stream github [options] --token <ghp> --org <org> --list-protections [--repo <repo> --branch-name <name> --disable-protections]
    nord-stream github [options] --token <ghp> --org <org> --list-secrets [--repo <repo> --no-repo --no-env --no-org]
    nord-stream github [options] --token <ghp> [--org <org>] --list-repos [--write-filter]
    nord-stream github [options] --token <ghp> --describe-token
    nord-stream github [options] --token <ghp> --org <org> --circleci [--repo <repo> --no-repo --no-org --branch-name <name> --no-clean]
    nord-stream github [options] --token <ghp> --org <org> --circleci --yaml <yaml> --repo <repo> [--branch-name <name> --no-clean]
    nord-stream github [options] --token <ghp> --org <org> --circleci --list-secrets [--repo <repo> --no-repo --no-org]

Options:
    -h --help                               Show this screen.
    --version                               Show version.
    -v, --verbose                           Verbose mode
    -d, --debug                             Debug mode
    --output-dir <dir>                      Output directory for logs

Commit:
    --user <user>                           User used to commit
    --email <email>                         Email address used commit
    --key-id <id>                           GPG primary key ID to sign commits

args:
    --token <ghp>                           Github personal token
    --org <org>                             Org name
    -r, --repo <repo>                       Run on selected repo (can be a file)
    -y, --yaml <yaml>                       Run arbitrary job
    --clean-logs                            Delete all logs created by this tool. This operation is done by default but can be manually triggered.
    --no-clean                              Don't clean workflow logs (default false)
    --clean-branch-policy                   Remove branch policy, can be used with --repo. This operation is done by default but can be manually triggered.
    --build-yaml <filename>                 Create a pipeline yaml file with all secrets.
    --build-type <type>                     Type used to generate the yaml file can be: default, azureoidc, awsoidc
    --env <env>                             Specify env for the yaml file creation.
    --no-repo                               Don't extract repo secrets.
    --no-env                                Don't extract environnments secrets.
    --no-org                                Don't extract organization secrets.
    --azure-tenant-id <tenant>              Identifier of the Azure tenant associated with the application having federated credentials (OIDC related).
    --azure-subscription-id <subscription>  Identifier of the Azure subscription associated with the application having federated credentials (OIDC related).
    --azure-client-id <client>              Identifier of the Azure application (client) associated with the application having federated credentials (OIDC related).
    --aws-role <role>                       AWS role to assume (OIDC related).
    --aws-region <region>                   AWS region (OIDC related).
    --list-protections                      List all protections.
    --list-repos                            List all repos.
    --list-secrets                          List all secrets.
    --disable-protections                   Disable the branch protection rules (needs admin rights)
    --write-filter                          Filter repo where current user has write or admin access.
    --force                                 Don't check environment and branch protections.
    --branch-name <name>                    Use specific branch name for deployment.
    --describe-token                        Display information on the token
    --circleci                              Target CircleCI pipelines instead of GitHub Actions
    --circleci-token <cct>                  CircleCI API token (required when --circleci is used)
    --circleci-vcs <vcs>                    CircleCI VCS type: 'gh', 'gl', or 'circleci' for GitHub App / GitLab App
                                            projects. Auto-detected from the CircleCI API when omitted.
    --circleci-org <corg>                   CircleCI org name or UUID (defaults to --org value).
                                            Use the org UUID when --circleci-vcs circleci
    --circleci-project <cproject>           CircleCI project name or UUID for a single target project.
                                            Use the project UUID when --circleci-vcs circleci

Examples:
    List all secrets from all repositories
    $ nord-stream github --token "$GHP" --org myorg --list-secrets

    Dump all secrets from all repositories and try to disable branch protections
    $ nord-stream github --token "$GHP" --org myorg --disable-protections

    List CircleCI secrets (project env vars + contexts) for all repositories
    $ nord-stream github --token "$GHP" --org myorg --circleci --circleci-token "$CCT" --list-secrets

    Dump CircleCI secrets from all repositories
    $ nord-stream github --token "$GHP" --org myorg --circleci --circleci-token "$CCT"

    Dump CircleCI secrets — GitHub App integration (org/project UUIDs, vcs=circleci)
    $ nord-stream github --token "$GHP" --org myorg --repo myrepo --circleci --circleci-token "$CCT" --circleci-vcs circleci --circleci-org <org-uuid> --circleci-project <project-uuid>

Authors: @hugow @0hexit
"""

from docopt import docopt
from nordstream.cicd.github import GitHub
from nordstream.cicd.circleci import CircleCI
from nordstream.core.github.github import GitHubWorkflowRunner
from nordstream.core.circleci.circleci import CircleCIRunner
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
        logger.info(f'Using branch: "{gitHub.branchName}"')

    if args["--key-id"]:
        Git.KEY_ID = args["--key-id"]
    if args["--user"]:
        Git.USER = args["--user"]
    if args["--email"]:
        Git.EMAIL = args["--email"]

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
    if args["--aws-role"] or args["--azure-tenant-id"]:
        gitHubWorkflowRunner.exploitOIDC = True
    if args["--azure-tenant-id"]:
        gitHubWorkflowRunner.tenantId = args["--azure-tenant-id"]
    if args["--azure-subscription-id"]:
        gitHubWorkflowRunner.subscriptionId = args["--azure-subscription-id"]
    if args["--azure-client-id"]:
        gitHubWorkflowRunner.clientId = args["--azure-client-id"]
    if args["--aws-role"]:
        gitHubWorkflowRunner.role = args["--aws-role"]
    if args["--aws-region"]:
        gitHubWorkflowRunner.region = args["--aws-region"]
    if args["--no-clean"]:
        gitHubWorkflowRunner.cleanLogs = not args["--no-clean"]

    # CircleCI mode — attach a CircleCIRunner to the workflow runner
    if args["--circleci"]:
        if not args["--circleci-token"]:
            logger.critical("--circleci-token is required when --circleci is used.")

        if not CircleCI.checkToken(args["--circleci-token"]):
            logger.critical("Invalid CircleCI token.")

        circleCIClient = CircleCI(args["--circleci-token"])
        # VCS type: None means auto-resolve from the CircleCI API.
        # Falls back to "gh" in the runner only when the project cannot be found.
        circleCIVcs = args["--circleci-vcs"] or None
        # Org: default to the GitHub --org value; override with --circleci-org
        circleCIOrg = args["--circleci-org"] or args["--org"]
        circleCIProject = args["--circleci-project"]  # None means "derive from repo name"
        # Note: docopt stores --circleci-org as args["--circleci-org"] and
        #       --circleci-project as args["--circleci-project"] regardless of metavar

        circleCIRunner = CircleCIRunner(
            gitHub, circleCIClient,
            vcsType=circleCIVcs,
            circleOrg=circleCIOrg,
            circleProject=circleCIProject,
        )

        circleCIRunner.extractProject = not args["--no-repo"]
        circleCIRunner.extractOrg = not args["--no-org"]
        circleCIRunner.cleanLogs = not args["--no-clean"]
        if args["--yaml"]:
            circleCIRunner.yaml = args["--yaml"]

        gitHubWorkflowRunner.circleCIRunner = circleCIRunner

    # logic
    if args["--describe-token"]:
        gitHubWorkflowRunner.describeToken()

    elif args["--list-repos"]:
        gitHubWorkflowRunner.getRepos(args["--repo"])
        gitHubWorkflowRunner.listGitHubRepos()

    elif args["--list-secrets"]:
        gitHubWorkflowRunner.getRepos(args["--repo"])
        gitHubWorkflowRunner.listGitHubSecrets()

    elif args["--build-yaml"]:
        gitHubWorkflowRunner.writeAccessFilter = True
        gitHubWorkflowRunner.workflowFilename = args["--build-yaml"]
        gitHubWorkflowRunner.createYaml(args["--repo"], args["--build-type"])

    # Cleaning
    elif args["--clean-logs"] or args["--clean-branch-policy"]:
        gitHubWorkflowRunner.getRepos(args["--repo"])
        if args["--clean-logs"]:
            gitHubWorkflowRunner.manualCleanLogs()
        if args["--clean-branch-policy"]:
            gitHubWorkflowRunner.manualCleanBranchPolicy()

    elif args["--list-protections"]:
        gitHubWorkflowRunner.writeAccessFilter = True
        gitHubWorkflowRunner.getRepos(args["--repo"])
        gitHubWorkflowRunner.checkBranchProtections()

    else:
        gitHubWorkflowRunner.writeAccessFilter = True
        gitHubWorkflowRunner.getRepos(args["--repo"])
        gitHubWorkflowRunner.start()
