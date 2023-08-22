import logging

from urllib.parse import urlparse
from os import makedirs, chdir
from os.path import exists, realpath
from nordstream.utils.log import logger
from nordstream.git import Git
import subprocess
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
        self._yaml = realpath(value)

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
            if self._writeAccessFilter:
                logger.critical("No repository with write access found.")
            else:
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
                self.__displayProjectVariables(project)
            except Exception as e:
                logger.error(f"Error while listing secrets for {project.get('name')}: {e}")

    def __listGitLabGroupSecrets(self):
        for group in self._cicd.groups:
            try:
                self.__displayGroupVariables(group)
            except Exception as e:
                logger.error(f"Error while listing secrets for {group.get('name')}: {e}")

    def __listGitLabInstanceSecrets(self):
        try:
            self.__displayInstanceVariables()
        except Exception as e:
            logger.error(f"Error while listing instance secrets: {e}")

    def __displayProjectVariables(self, project):

        projectName = project.get("path_with_namespace")

        try:
            variables = self._cicd.listVariablesFromProject(project)
            if len(variables) != 0:

                logger.info(f'"{projectName}" project variables')

                for variable in variables:
                    value = variable.get("value")
                    protected = variable.get("protected")
                    logger.raw(
                        f'\t- {variable["key"]}={variable["value"]} (protected:{variable["protected"]})\n', logging.INFO
                    )
        except GitLabError as e:
            logger.info(f'"{projectName}" variables')
            logger.error(f"\t{e}")

    def __displayGroupVariables(self, group):

        groupPath = group.get("full_path")

        try:
            variables = self._cicd.listVariablesFromGroup(group)
            if len(variables) != 0:
                logger.info(f'"{groupPath}" group variables:')

                for variable in variables:
                    value = variable.get("value")
                    protected = variable.get("protected")
                    logger.raw(
                        f'\t- {variable["key"]}={variable["value"]} (protected:{variable["protected"]})\n', logging.INFO
                    )
        except GitLabError as e:
            logger.info(f'"{groupPath}" group variables:')
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
            logger.info("Instance variables:")
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
            Git.gitClone(url)

            chdir(repoShortName)
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
            try:

                pipelineResults = output.read()

            except:
                output.seek(0)
                pipelineResults = output.read()

        logger.success("Output:")
        logger.raw(pipelineResults, logging.INFO)

    def __clean(self, project):

        if self._pushedCommitsCount > 0:

            projectId = project.get("id")
            if self._cleanLogs:
                logger.info(f"Cleaning logs for project: {project.get('path_with_namespace')}")
                self._cicd.cleanAllLogs(projectId)

            logger.verbose("Cleaning commits.")
            if self._branchAlreadyExists and self._cicd.branchName != self._cicd.defaultBranchName:
                Git.gitUndoLastPushedCommits(self._cicd.branchName, self._pushedCommitsCount)
            else:
                if not self.__deleteRemoteBranch():
                    logger.info("Cleaning remote branch.")
                    # rm everything if we can't delete the branch (only leave one file otherwise it will try to rm the branch)
                    Git.gitCleanRemote(self._cicd.branchName, leaveOneFile=True)

    def manualCleanLogs(self):
        logger.info("Deleting logs")
        for project in self._cicd.projects:
            logger.info(f"Cleaning logs for project: {project.get('path_with_namespace')}")
            self._cicd.cleanAllLogs(project.get("id"))

    def __deleteRemoteBranch(self):
        logger.verbose("Deleting remote branch")
        deleteOutput = Git.gitDeleteRemote(self._cicd.branchName)
        deleteOutput.wait()

        if deleteOutput.returncode != 0:
            logger.error(f"Error deleting remote branch {self._cicd.branchName}")
            logger.raw(deleteOutput.communicate()[1], logging.INFO)
            return False
        return True

    def describeToken(self):
        response = self._cicd.getUser()
        logger.info("Token information:")

        username = response.get("username")
        if username != "":
            logger.raw(f"\t- Username: {username}\n", logging.INFO)

        isAdmin = response.get("is_admin")
        if isAdmin == None:
            logger.raw(f"\t- IsAdmin: False\n", logging.INFO)
        else:
            logger.raw(f"\t- IsAdmin: {isAdmin}\n", logging.INFO)

        email = response.get("email")
        if email != "":
            logger.raw(f"\t- Email: {email}\n", logging.INFO)

        id = response.get("id")
        if id != "":
            logger.raw(f"\t- Id: {id}\n", logging.INFO)

        note = response.get("note")
        if note != "" and note != None:
            logger.raw(f"\t- Note: {note}\n", logging.INFO)

    def listBranchesProtectionRules(self):
        logger.info("Listing branch protection rules.")
        for project in self._cicd.projects:

            projectName = project.get("path_with_namespace")
            logger.info(f"{projectName}:")

            try:
                protections = self._cicd.getBranchesProtectionRules(project.get("id"))
                self.__displayBranchesProtectionRulesPriv(protections)
            except GitLabError as e:
                logger.verbose(
                    "Not enough privileges to get full details on the branch protection rules for this project, trying to get limited information."
                )
                try:
                    branches = self._cicd.getBranches(project.get("id"))
                    self.__displayBranchesProtectionRulesUnpriv(branches)
                except GitLabError as e:
                    logger.error(f"\t{e}")

            logger.empty_line()

    def __displayBranchesProtectionRulesPriv(self, protections):
        if len(protections) == 0:
            logger.success(f"No protection")

        for protection in protections:

            name = protection.get("name")
            logger.info(f'branch: "{name}"')

            allow_force_push = protection.get("allow_force_push")
            logger.raw(f"\t- Allow force push: {allow_force_push}\n", logging.INFO)

            code_owner_approval_required = protection.get("code_owner_approval_required", None)
            if code_owner_approval_required != None:
                logger.raw(f"\t- Code Owner approval required: {code_owner_approval_required}\n", logging.INFO)

            push_access_levels = protection.get("push_access_levels")
            logger.raw(f"\t- Push access level:\n", logging.INFO)
            self.__displayAccessLevel(push_access_levels)

            unprotect_access_levels = protection.get("unprotect_access_levels")
            logger.raw(f"\t- Unprotect access level:\n", logging.INFO)
            self.__displayAccessLevel(unprotect_access_levels)

            merge_access_levels = protection.get("merge_access_levels")
            logger.raw(f"\t- Merge access level:\n", logging.INFO)
            self.__displayAccessLevel(merge_access_levels)

    def __displayBranchesProtectionRulesUnpriv(self, branches):

        for branch in branches:

            isProtected = branch.get("protected")
            if isProtected:

                name = branch.get("name")
                logger.info(f'branch: "{name}"')

                logger.raw(f"\t- Protected: True\n", logging.INFO)

                developers_can_push = branch.get("developers_can_push")
                logger.raw(f"\t- Developers can push: {developers_can_push}\n", logging.INFO)

                developers_can_merge = branch.get("developers_can_merge")
                logger.raw(f"\t- Developers can merge: {developers_can_merge}\n", logging.INFO)

    def __displayAccessLevel(self, access_levels):
        for al in access_levels:
            access_level = al.get("access_level", None)
            user_id = al.get("user_id", None)
            group_id = al.get("group_id", None)
            access_level_description = al.get("access_level_description")

            res = f"\t\t{access_level_description}"

            if access_level != None:
                res += f" (access_level={access_level})"
            if user_id != None:
                res += f" (user_id={user_id})"
            if group_id != None:
                res += f" (group_id={group_id})"

            logger.raw(f"{res}\n", logging.INFO)

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
