# Nord Stream

Nord Stream is a tool that allows you to list the secrets stored inside CI/CD environments and extract them by deploying _malicious_ pipelines.

It currently supports Azure DevOps and GitHub.

## Installation

```
$ pip3 install -r requirements.txt
```

`git` is also required (see https://git-scm.com/download/) and must exist in your `PATH`.

## Usage

More information in our article: https://www.synacktiv.com/publications/cicd-secrets-extraction-tips-and-tricks

By default, the tool will attempt to extract all secrets from all accessible projects or repositories. Several options are available to restrict the extraction of secrets.

### Azure DevOps

```
$ python3 nord-stream.py devops -h  
CICD pipeline exploitation tool

Usage:
    nord-stream.py devops [options] --token <pat> --org <org> [--project <project> --no-vg --no-gh --no-az --write-filter --no-clean]
    nord-stream.py devops [options] --token <pat> --org <org> --yaml <yaml> --project <project> [--write-filter]
    nord-stream.py devops [options] --token <pat> --org <org> --build-yaml <output> --build-type <type>
    nord-stream.py devops [options] --token <pat> --org <org> --clean-logs [--repo <repo>]
    nord-stream.py devops [options] --token <pat> --org <org> --list-projects [--write-filter]
    nord-stream.py devops [options] --token <pat> --org <org> --list-secrets [--project <project> --write-filter]

Options:
    -h --help                               Show this screen.
    --version                               Show version.
    -v, --verbose                           Verbose mode
    -d, --debug                             Debug mode

args
    --token <pat>                           Azure DevOps personal token
    --org <org>                             Org name
    -p, --project <project>                 Run on selected project (can be a file)
    -y, --yaml <yaml>                       Run arbitrary job
    --clean-logs                            Delete all pipeline created by this tool. This operation is done by default but can be manually triggered.
    --no-vg                                 Don't extract variable groups secrets
    --no-sf                                 Don't extract secure files
    --no-gh                                 Don't extract GitHub service connection secrets
    --no-az                                 Don't extract Azure service connection secrets
    --list-projects                         List all projects.
    --list-secrets                          List all secrets.
    --write-filter                          Filter projects where current user has write or admin access.
    --build-yaml <output>                   Create a pipeline yaml file with default configuration.
    --build-type <type>                     Type used to generate the yaml file can be: default, azurerm, github

Examples:
    Dump all secrets from all projects
    $ nord-stream.py devops --token "$PAT" --org myorg

Authors: @hugow @0hexit
```

### GitHUb

```
$ python3 nord-stream.py github -h
CICD pipeline exploitation tool

Usage:
    nord-stream.py github [options] --token <ghp> --org <org> [--repo <repo> --no-repo --no-env --env <env> --disable-protections --write-filter --branch-name <name>]
    nord-stream.py github [options] --token <ghp> --org <org> --yaml <yaml> --repo <repo> [--env <env> --disable-protections --write-filter --branch-name <name>]
    nord-stream.py github [options] --token <ghp> --org <org> ([--clean-logs] [--clean-branch-policy]) [--repo <repo> --branch-name <name>]
    nord-stream.py github [options] --token <ghp> --org <org> --build-yaml <filename> --repo <repo> [--env <env> --write-filter]
    nord-stream.py github [options] --token <ghp> --org <org> --exploit-oidc --azure-tenant-id <tenant> --azure-subscription-id <subscription> --azure-client-id <client> [--repo <repo> --env <env> --branch-name <name>]
    nord-stream.py github [options] --token <ghp> --org <org> --list-protections [--repo <repo> --write-filter --branch-name <name> --disable-protections]
    nord-stream.py github [options] --token <ghp> --org <org> --list-secrets [--repo <repo>]
    nord-stream.py github [options] --token <ghp> [--org <org>] --list-repos [--write-filter]

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
    --clean-branch-policy                   Remove branch policy, can be used with --repo. This operation is done by default but can be manually triggered.
    --build-yaml <filename>                 Create a pipeline yaml file with all secrets.
    --env <env>                             Specify env for the yaml file creation.
    --no-repo                               Don't extract repo secrets.
    --no-env                                Don't extract environnments secrets.
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

Examples:
    Dump all secrets from all repositories and try to disable branch protections
    $ nord-stream.py github --token "$GHP" --org myorg --disable-protections

Authors: @hugow @0hexit
```

## TODO

- [ ] Add support of URLs corresponding to Azure DevOps Server instances (on-premises solutions)
- [ ] Add an option to extract secrets via Windows hosts
- [ ] Add support of other CI/CD environments (GitLab/Jenkins/Bitbucket)
- [ ] Implement the extraction of organization secrets on GitHub
- [ ] Use the GitHub GraphQL API instead of the REST one to list the branch protection rules and temporarily disable them if they match the malicious branch about to be pushed
