import requests
import time
from os import makedirs
from nordstream.utils.log import logger
from nordstream.utils.errors import GitLabError
from nordstream.git import Git
import urllib3

COMPLETED_STATES = ["success", "failed", "canceled", "skipped"]

# painfull warnings you know what you are doing right ?
requests.packages.urllib3.disable_warnings()


class GitLab:
    _DEFAULT_BRANCH_NAME = "dev_remote_ea5Eu/test/v1"
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
    _maxRetry = 10

    def __init__(self, url, token, verifCert):
        self._gitlabURL = url.strip("/")
        self._token = token
        self._header = {"PRIVATE-TOKEN": token}
        self._verifyCert = verifCert
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
    def checkToken(cls, token, gitlabURL, verifyCert):
        logger.verbose(f"Checking token: {token}")
        # from https://docs.gitlab.com/ee/api/rest/index.html#personalprojectgroup-access-tokens
        try:
            return (
                requests.get(
                    f"{gitlabURL.strip('/')}/api/v4/user",
                    headers={"PRIVATE-TOKEN": token},
                    verify=verifyCert,
                ).status_code
                == 200
            )
        except Exception as e:
            logger.error(e)
        return False

    def __getLogin(self):
        response = self.getUser()
        return response.get("username", "")

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
                logger.debug(f"Error {response.status_code} while retrieving data: {url}")
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

        params = {}

        if project != None:
            params["search_namespaces"] = True
            params["search"] = project

        if filterWrite:
            params["min_access_level"] = 30

        status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/projects", params)

        if status_code == 200:
            if len(response) == 0:
                return

            for p in response:
                if strict and p.get("path_with_namespace") != project:
                    continue
                p = {
                    "id": p.get("id"),
                    "path_with_namespace": p.get("path_with_namespace"),
                    "name": p.get("name"),
                }
                self._projects.append(p)

        else:
            logger.error("Error while retrieving projects")
            logger.debug(response)

    def addGroups(self, group=None):
        logger.debug(f"Checking group: {group}")

        params = {"all_available": True}

        if group != None:
            params["search_namespaces"] = True
            params["search"] = group

        status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/groups", params)

        if status_code == 200:
            if len(response) == 0:
                return

            for p in response:
                p = {
                    "id": p.get("id"),
                    "full_path": p.get("full_path"),
                    "name": p.get("name"),
                }
                self._groups.append(p)

        else:
            logger.error("Error while retrieving groups")
            logger.debug(response)

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

    def __getJobs(self, projectId, pipelineId):

        status_code, response = self.__paginatedGet(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines/{pipelineId}/jobs"
        )

        if status_code == 403:
            raise GitLabError(response.get("message"))

        # reverse the list to get the first job at the first position
        return response[::-1]

    def downloadPipelineOutput(self, project, pipelineId):
        projectPath = project.get("path_with_namespace")
        self.__createOutputDir(projectPath)

        projectId = project.get("id")

        jobs = self.__getJobs(projectId, pipelineId)

        date = time.strftime("%Y-%m-%d_%H-%M-%S")
        f = open(f"{self._outputDir}/{projectPath}/pipeline_{date}.log", "w")

        if len(jobs) == 0:
            return None

        for job in jobs:

            jobId = job.get("id")
            jobName = job.get("name", "")
            jobStage = job.get("stage", "")
            jobStatus = job.get("status", "")

            output = self.__getTraceForJobId(projectId, jobId)

            if jobStatus != "skipped":
                f.write(f"[+] {jobName} (stage={jobStage})\n")
                f.write(output)

        f.close()

        return f"pipeline_{date}.log"

    def __getTraceForJobId(self, projectId, jobId):

        response = self._session.get(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/jobs/{jobId}/trace",
            headers=self._header,
            verify=self._verifyCert,
        )

        if response.status_code != 200:
            for i in range(self._maxRetry):
                logger.warning(f"Output not ready, sleeping for {self._sleepTime}s")
                time.sleep(self._sleepTime)
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

        return response.text

    def __deletePipeline(self, projectId):
        logger.debug("Deleting pipeline")

        status_code, response = self.__paginatedGet(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines?ref={self._branchName}&username={self._gitlabLogin}"
        )

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

                if response.get("title") != (Git.ATTACK_COMMIT_MSG and Git.CLEAN_COMMIT_MSG):
                    continue

                if response.get("author_name") != Git.LOCAL_USERNAME:
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

        status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/projects/{projectId}/protected_branches")

        if status_code == 403:
            raise GitLabError(response.get("message"))

        return response

    def getBranches(self, projectId):
        logger.debug("Getting branch protection rules (limited)")

        status_code, response = self.__paginatedGet(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/repository/branches"
        )

        if status_code == 403:
            raise GitLabError(response.get("message"))

        return response

    def getFailureReasonPipeline(self, projectId, pipelineId):

        response = self._session.get(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines/{pipelineId}",
            headers=self._header,
            verify=self._verifyCert,
        ).json()

        return response.get("yaml_errors", None)

    def getFailureReasonJobs(self, projectId, pipelineId):

        res = []
        jobs = self.__getJobs(projectId, pipelineId)

        for job in jobs:

            failure = {}
            failure["name"] = job.get("name", "")
            failure["stage"] = job.get("stage", "")
            failure["failure_reason"] = job.get("failure_reason", "")

            if failure["failure_reason"] != "":
                res.append(failure)

        return res
