import logging

from os import makedirs, chdir
from os.path import exists, realpath
from nordstream.git import *
from nordstream.utils.errors import GitLabError


class GitLabRunner:
    _cicd = None
    _writeAccessFilter = False

    @property
    def writeAccessFilter(self):
        return self._writeAccessFilter

    @writeAccessFilter.setter
    def writeAccessFilter(self, value):
        self._writeAccessFilter = value

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

    def listGitLabSecrets(self):
        logger.info("Listing GitLab secrets")
        for project in self._cicd.projects:
            try:
                projectName = project.get("path_with_namespace")
                logger.info(f'"{projectName}" secrets')
                self.__displayProjectVariables(project)
            except Exception as e:
                logger.error(f"Error while listing secrets for {project.name}: {e}")

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

    def listGitLabProjects(self):
        logger.info("Listing GitLab projects")
        for project in self._cicd.projects:
            logger.raw(f'- {project["path_with_namespace"]}\n', level=logging.INFO)

    def runPipeline(self):
        # TODO
        logger.debug("TODO")
