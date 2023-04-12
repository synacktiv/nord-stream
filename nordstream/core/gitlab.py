import logging

from os.path import exists
from nordstream.git import *


class GitLabRunner:
    _cicd = None

    def __init__(self, cicd):
        self._cicd = cicd

    def getProjects(self, project):
        if project:
            if exists(project):
                with open(project, "r") as file:
                    for p in file:
                        self._cicd.addProject(p.strip())

            else:
                self._cicd.addProject(project)
        else:
            self._cicd.addProject()

    def listGitLabSecrets(self):
        logger.info("Listing GitLab secrets")
        for project in self._cicd.projects:
            try:
                self.__displayProjectVariables(project)
            except Exception as e:
                logger.error(f"Error while listing secrets for {project.name}: {e}")

    def __displayProjectVariables(self, project):
        variables = self._cicd.listVariablesFromProject(project)
        if len(variables) != 0:
            logger.info("Project variables:")
            for variable in variables:
                value = variable.get("value")
                protected = variable.get("protected")
                logger.raw(
                    f'\t- {variable["key"]}={variable["value"]} protected:{variable["protected"]}\n', logging.INFO
                )

    def listGitLabProjects(self):
        logger.info("Listing GitLab projects")
        for project in self._cicd.projects:
            logger.raw(f'- {project["path_with_namespace"]}\n', level=logging.INFO)

    def runPipeline(self):
        # TODO
        logger.debug("TODO")
