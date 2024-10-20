"""
CICD pipeline exploitation tool

Usage:
    nord-stream.py devops [options] --token <pat> --org <org> [extraction] [--project <project> --write-filter --no-clean --branch-name <name> --pipeline-name <name> --repo-name <name>]
    nord-stream.py devops [options] --token <pat> --org <org> --yaml <yaml> --project <project> [--write-filter --no-clean --branch-name <name> --pipeline-name <name> --repo-name <name>]
    nord-stream.py devops [options] --token <pat> --org <org> --build-yaml <output> [--build-type <type>]
    nord-stream.py devops [options] --token <pat> --org <org> --clean-logs [--project <project>]
    nord-stream.py devops [options] --token <pat> --org <org> --list-projects [--write-filter]
    nord-stream.py devops [options] --token <pat> --org <org> (--list-secrets [--project <project> --write-filter] | --list-users)
    nord-stream.py devops [options] --token <pat> --org <org> --describe-token

Options:
    -h --help                               Show this screen.
    --version                               Show version.
    -v, --verbose                           Verbose mode
    -d, --debug                             Debug mode
    --output-dir <dir>                      Output directory for logs
    --ignore-cert                           Allow insecure server connections

Commit:
    --user <user>                           User used to commit
    --email <email>                         Email address used commit
    --key-id <id>                           GPG primary key ID to sign commits

args:
    --token <pat>                           Azure DevOps personal token or JWT
    --org <org>                             Org name
    -p, --project <project>                 Run on selected project (can be a file)
    -y, --yaml <yaml>                       Run arbitrary job
    --clean-logs                            Delete all pipeline created by this tool. This operation is done by default but can be manually triggered.
    --no-clean                              Don't clean pipeline logs (default false)
    --list-projects                         List all projects.
    --list-secrets                          List all secrets.
    --list-users                            List all users.
    --write-filter                          Filter projects where current user has write or admin access.
    --build-yaml <output>                   Create a pipeline yaml file with default configuration.
    --build-type <type>                     Type used to generate the yaml file can be: default, azurerm, github, aws, sonar, ssh
    --describe-token                        Display information on the token
    --branch-name <name>                    Use specific branch name for deployment.
    --pipeline-name <name>                  Use pipeline for deployment.
    --repo-name <name>                      Use specific repo for deployment.

Exctraction:
    --extract <list>                        Extract following secrets [vg,sf,gh,az,aws,sonar,ssh]
    --no-extract <list>                     Don't extract following secrets [vg,sf,gh,az,aws,sonar,ssh]

Examples:
    List all secrets from all projects
    $ nord-stream.py devops --token "$PAT" --org myorg --list-secrets

    Dump all secrets from all projects
    $ nord-stream.py devops --token "$PAT" --org myorg

Authors: @hugow @0hexit
"""

from docopt import docopt
from nordstream.cicd.devops import DevOps
from nordstream.core.devops.devops import DevOpsRunner
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
    if not DevOps.checkToken(args["--token"], args["--org"], (not args["--ignore-cert"])):
        logger.critical("Invalid token or org.")

    # devops setup
    devops = DevOps(args["--token"], args["--org"], (not args["--ignore-cert"]))
    if args["--output-dir"]:
        devops.outputDir = args["--output-dir"] + "/"
    if args["--branch-name"]:
        devops.branchName = args["--branch-name"]
    if args["--pipeline-name"]:
        devops.pipelineName = args["--pipeline-name"]
    if args["--repo-name"]:
        devops.repoName = args["--repo-name"]

    devopsRunner = DevOpsRunner(devops)

    if args["--key-id"]:
        Git.KEY_ID = args["--key-id"]
    if args["--user"]:
        Git.USER = args["--user"]
    if args["--email"]:
        Git.EMAIL = args["--email"]

    if args["--yaml"]:
        devopsRunner.yaml = args["--yaml"]
    if args["--write-filter"]:
        devopsRunner.writeAccessFilter = args["--write-filter"]

    if args["--extract"] and args["--no-extract"]:
        logger.critical("Can't use both --service-connection and --no-service-connection option.")

    if args["--extract"]:
        devopsRunner.parseExtractList(args["--extract"])

    if args["--no-extract"]:
        devopsRunner.parseExtractList(args["--no-extract"], False)

    if args["--no-clean"]:
        devopsRunner.cleanLogs = not args["--no-clean"]

    if args["--describe-token"]:
        devopsRunner.describeToken()
        return

    devopsRunner.getProjects(args["--project"])

    # logic
    if args["--list-projects"]:
        devopsRunner.listDevOpsProjects()

    if args["--list-users"]:
        devopsRunner.listDevOpsUsers()

    elif args["--list-secrets"]:
        devopsRunner.listProjectSecrets()

    elif args["--clean-logs"]:
        devopsRunner.manualCleanLogs()

    elif args["--build-yaml"]:
        devopsRunner.output = args["--build-yaml"]
        devopsRunner.createYaml(args["--build-type"])

    else:
        devopsRunner.runPipeline()
