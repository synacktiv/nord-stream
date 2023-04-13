import logging

from urllib.parse import urlparse
from os import makedirs, chdir
from os.path import exists, realpath
from nordstream.git import *
from nordstream.utils.errors import GitLabError
from nordstream.yaml.gitlab import GitLabPipelineGenerator


class GitLabRunner:
    _cicd = None
    _writeAccessFilter = False
    _extractProject = True
    _extractGroup = True
    _extractInstance = True
    _yaml = None
    _branchAlreadyExists = False
    _fileName = None
    _cleanLogs = True

    @property
    def writeAccessFilter(self):
        return self._writeAccessFilter

    @writeAccessFilter.setter
    def writeAccessFilter(self, value):
        self._writeAccessFilter = value

    @property
    def extractProject(self):
        return self._extractProject

    @extractProject.setter
    def extractProject(self, value):
        self._extractProject = value

    @property
    def extractGroup(self):
        return self._extractGroup

    @extractGroup.setter
    def extractGroup(self, value):
        self._extractGroup = value

    @property
    def extractInstance(self):
        return self._extractInstance

    @extractInstance.setter
    def extractInstance(self, value):
        self._extractInstance = value

    @property
    def yaml(self):
        return self._yaml

    @yaml.setter
    def yaml(self, value):
        self._yaml = value

    @property
    def branchAlreadyExists(self):
        return self._branchAlreadyExists

    @branchAlreadyExists.setter
    def branchAlreadyExists(self, value):
        self._branchAlreadyExists = value

    @property
    def cleanLogs(self):
        return self._cleanLogs

    @cleanLogs.setter
    def cleanLogs(self, value):
        self._cleanLogs = value

    def __init__(self, cicd):
        self._cicd = cicd
        self.__createLogDir()

    def __createLogDir(self):
        self._cicd.outputDir = realpath(self._cicd.outputDir) + "/gitlab"
        makedirs(self._cicd.outputDir, exist_ok=True)

    def getProjects(self, project, strict=False):
        if project:
            if exists(project):
                with open(project, "r") as file:
                    for p in file:
                        self._cicd.addProject(project=p.strip(), filterWrite=self._writeAccessFilter, strict=strict)

            else:
                self._cicd.addProject(project=project, filterWrite=self._writeAccessFilter, strict=strict)
        else:
            self._cicd.addProject(filterWrite=self._writeAccessFilter)

        if len(self._cicd.projects) == 0:
            logger.critical("No repository found.")

    def getGroups(self, group):
        if group:
            if exists(group):
                with open(group, "r") as file:
                    for p in file:
                        self._cicd.addGroups(group)

            else:
                self._cicd.addGroups(group)
        else:
            self._cicd.addGroups()

        if len(self._cicd.groups) == 0:
            logger.critical("No group found.")

    def listGitLabSecrets(self):
        logger.info("Listing GitLab secrets")

        if self._extractInstance:
            self.__listGitLabInstanceSecrets()

        if self._extractGroup:
            self.__listGitLabGroupSecrets()

        if self._extractProject:
            self.__listGitLabProjectSecrets()

    def __listGitLabProjectSecrets(self):
        for project in self._cicd.projects:
            try:
                projectName = project.get("path_with_namespace")
                logger.info(f'"{projectName}" secrets')
                self.__displayProjectVariables(project)
            except Exception as e:
                logger.error(f"Error while listing secrets for {project.name}: {e}")

    def __listGitLabGroupSecrets(self):
        for group in self._cicd.groups:
            try:
                groupPath = group.get("full_path")
                logger.info(f'"{groupPath}" secrets')
                self.__displayGroupVariables(group)
            except Exception as e:
                logger.error(f"Error while listing secrets for {group.name}: {e}")

    def __listGitLabInstanceSecrets(self):
        try:
            logger.info("Instance secrets")
            self.__displayInstanceVariables()
        except Exception as e:
            logger.error(f"Error while listing instance secrets: {e}")

    def __displayProjectVariables(self, project):
        try:
            variables = self._cicd.listVariablesFromProject(project)
            if len(variables) != 0:
                logger.info("Project variables:")
                for variable in variables:
                    value = variable.get("value")
                    protected = variable.get("protected")
                    logger.raw(
                        f'\t- {variable["key"]}={variable["value"]} (protected:{variable["protected"]})\n', logging.INFO
                    )
        except GitLabError as e:
            logger.error(f"\t{e}")

    def __displayGroupVariables(self, group):
        try:
            variables = self._cicd.listVariablesFromGroup(group)
            if len(variables) != 0:
                logger.info("Group variables:")
                for variable in variables:
                    value = variable.get("value")
                    protected = variable.get("protected")
                    logger.raw(
                        f'\t- {variable["key"]}={variable["value"]} (protected:{variable["protected"]})\n', logging.INFO
                    )
        except GitLabError as e:
            logger.error(f"\t{e}")

    def __displayInstanceVariables(self):
        try:
            variables = self._cicd.listVariablesFromInstance()
            if len(variables) != 0:
                logger.info("Instance variables:")
                for variable in variables:
                    value = variable.get("value")
                    protected = variable.get("protected")
                    logger.raw(
                        f'\t- {variable["key"]}={variable["value"]} (protected:{variable["protected"]})\n', logging.INFO
                    )
        except GitLabError as e:
            logger.error(f"\t{e}")

    def listGitLabProjects(self):
        logger.info("Listing GitLab projects")
        for project in self._cicd.projects:
            logger.raw(f'- {project["path_with_namespace"]}\n', level=logging.INFO)

    def listGitLabGroups(self):
        logger.info("Listing GitLab groups")
        for project in self._cicd.groups:
            logger.raw(f'- {project["full_path"]}\n', level=logging.INFO)

    def runPipeline(self):
        for project in self._cicd.projects:

            repoShortName = project.get("name")

            logger.success(f'"{repoShortName}"')

            domain = urlparse(self._cicd.url).netloc
            url = f"https://foo:{self._cicd.token}@{domain}/{project.get('path_with_namespace')}"
            gitClone(url)

            chdir(repoShortName)
            self._pushedCommitsCount = 0
            self._branchAlreadyExists = gitRemoteBranchExists(self._cicd.branchName)
            gitInitialization(self._cicd.branchName, branchAlreadyExists=self._branchAlreadyExists)

            try:
                # TODO: branch protections
                # if not self._forceDeploy:
                #    self.__checkAndDisableBranchProtectionRules(repo)

                if self._yaml:
                    self.__runCustomPipeline(project)
                else:
                    logger.error("No yaml specify")

            except Exception as e:
                logger.error(f"Error: {e}")
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.exception(e)

            finally:
                self.__clean(project)
                chdir("../")
                subprocess.Popen(f"rm -rfd ./{repoShortName}", shell=True).wait()

        logger.info(f"Check output: {self._cicd.outputDir}")

    def __runCustomPipeline(self, project):
        logger.info(f"Running custom pipeline: {self._yaml}")

        pipelineGenerator = GitLabPipelineGenerator()
        pipelineGenerator.loadFile(self._yaml)

        try:
            pipelineId = self.__launchPipeline(project, pipelineGenerator)
            if pipelineId:
                self._fileName = self._cicd.downloadPipelineOutput(project, pipelineId)
                if self._fileName:
                    self.__extractPipelineOutput(project)

                logger.empty_line()
        except Exception as e:
            logger.error(f"Error: {e}")

        finally:
            logger.empty_line()

    def __launchPipeline(self, project, pipelineGenerator):
        logger.verbose(f"Launching pipeline.")

        projectId = project.get("id")

        pipelineGenerator.writeFile(f".gitlab-ci.yml")
        pushOutput = gitPush(self._cicd.branchName)
        pushOutput.wait()

        try:
            if pushOutput.returncode != 0 or b"Everything up-to-date" in pushOutput.communicate()[1].strip():
                logger.error("Error when pushing code:")
                logger.raw(pushOutput.communicate()[1], logging.INFO)
            else:
                self._pushedCommitsCount += 1
                logger.raw(pushOutput.communicate()[1])

                pipelineId, pipelineStatus = self._cicd.waitPipeline(projectId)

                if pipelineStatus == "success":
                    logger.success("Pipeline has successfully terminated.")
                    return pipelineId

                elif pipelineStatus == "failed":
                    logger.error("Pipeline has failed.")
                    logger.error("#TODO: display failure reason")
                    # self.__displayFailureReasons(project, runId)
                    return None

        except Exception as e:
            logger.exception(e)
        finally:
            pass

    def __extractPipelineOutput(self, project, resultsFilename="secrets.txt"):

        projectPath = project.get("path_with_namespace")

        with open(
            f"{self._cicd.outputDir}/{projectPath}/{self._fileName}",
            "rb",
        ) as output:
            try:

                pipelineResults = output.read()

            except:
                output.seek(0)
                pipelineResults = output.read()

        logger.success("Output:")
        logger.raw(pipelineResults, logging.INFO)

    def __clean(self, project):
        projectId = project.get("id")
        if self._cleanLogs:
            logger.info(f"Cleaning logs for project: {project.get('path_with_namespace')}")
            self._cicd.cleanAllLogs(projectId)
        if self._branchAlreadyExists and self._cicd.branchName != self._cicd.defaultBranchName:
            gitUndoLastPushedCommits(self._cicd.branchName, self._pushedCommitsCount)
        else:
            self.__deleteRemoteBranch()

    def manualCleanLogs(self):
        logger.info("Deleting logs")
        for project in self._cicd.projects:
            logger.info(f"Cleaning logs for project: {project.get('path_with_namespace')}")
            self._cicd.cleanAllLogs(project.get("id"))

    def __deleteRemoteBranch(self):
        logger.info("Deleting remote branch")
        gitCleanRemote(self._cicd.branchName)
