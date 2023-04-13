import logging

from os import makedirs, chdir
from os.path import exists, realpath
from nordstream.git import *
from nordstream.utils.errors import GitLabError


class GitLabRunner:
    _cicd = None
    _writeAccessFilter = False
    _extractProject = True
    _extractGroup = True
    _extractInstance = True

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

    def __init__(self, cicd):
        self._cicd = cicd
        self.__createLogDir()

    def __createLogDir(self):
        self._cicd.outputDir = realpath(self._cicd.outputDir) + "/gitlab"
        makedirs(self._cicd.outputDir, exist_ok=True)

    def getProjects(self, project):
        if project:
            if exists(project):
                with open(project, "r") as file:
                    for p in file:
                        self._cicd.addProject(project=p.strip(), filterWrite=self._writeAccessFilter)

            else:
                self._cicd.addProject(project=project, filterWrite=self._writeAccessFilter)
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
            self.__displayInstanceVariables()

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
            logger.info(f"Instance secrets")
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
        # TODO
        logger.debug("TODO")
