import requests
import time
from os import makedirs
from nordstream.utils.log import logger
from nordstream.yaml.devops import DevOpsPipelineGenerator
from nordstream.git import Git
from nordstream.utils.errors import DevOpsError


class DevOps:
    _DEFAULT_PIPELINE_NAME = "Build_pipeline_58675"
    _DEFAULT_BRANCH_NAME = "dev_remote_ea5Eu/test/v1"
    _token = None
    _auth = None
    _org = None
    _devopsLoginId = None
    _projects = []
    _baseURL = "https://dev.azure.com/"
    _header = {"Accept": "application/json; api-version=6.0-preview"}
    _session = None
    _repoName = "TestDev_ea5Eu"
    _outputDir = "nord-stream-logs"
    _pipelineName = _DEFAULT_PIPELINE_NAME
    _branchName = _DEFAULT_BRANCH_NAME
    _sleepTime = 15
    _maxRetry = 10
    _verifyCert = True

    def __init__(self, token, org):
        self._token = token
        self._org = org
        self._baseURL += f"{org}/"
        self._auth = ("", self._token)
        self._session = requests.Session()
        self._devopsLoginId = self.__getLogin()

    @property
    def projects(self):
        return self._projects

    @property
    def org(self):
        return self._org

    @property
    def branchName(self):
        return self._branchName

    @branchName.setter
    def branchName(self, value):
        self._branchName = value

    @property
    def repoName(self):
        return self._repoName

    @repoName.setter
    def repoName(self, value):
        self._repoName = value

    @property
    def pipelineName(self):
        return self._pipelineName

    @pipelineName.setter
    def pipelineName(self, value):
        self._pipelineName = value

    @property
    def token(self):
        return self._token

    @property
    def outputDir(self):
        return self._outputDir

    @outputDir.setter
    def outputDir(self, value):
        self._outputDir = value

    @property
    def defaultPipelineName(self):
        return self._DEFAULT_PIPELINE_NAME

    @property
    def defaultBranchName(self):
        return self._DEFAULT_BRANCH_NAME

    def __getLogin(self):
        return self.getUser().get("authenticatedUser").get("id")

    def getUser(self):
        logger.debug("Retrieving user informations")
        return self._session.get(
            f"{self._baseURL}/_apis/ConnectionData",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()

    def listProjects(self):
        logger.debug("Listing projects")
        continuationToken = 0
        # Azure DevOps pagination
        while True:
            params = {"continuationToken": continuationToken}
            response = self._session.get(
                f"{self._baseURL}/_apis/projects",
                params=params,
                auth=self._auth,
                headers=self._header,
                verify=self._verifyCert,
            ).json()

            if len(response.get("value")) != 0:
                for repo in response.get("value"):
                    p = {"id": repo.get("id"), "name": repo.get("name")}
                    self._projects.append(p)
                continuationToken += response.get("count")
            else:
                break

    # TODO: crappy code I know
    def filterWriteProjects(self):
        continuationToken = None
        res = []
        params = {}
        # Azure DevOps pagination
        while True:
            if continuationToken:
                params = {"continuationToken": continuationToken}
            response = self._session.get(
                f"https://vssps.dev.azure.com/{self._org}/_apis/graph/groups",
                params=params,
                auth=self._auth,
                headers=self._header,
                verify=self._verifyCert,
            )

            headers = response.headers
            response = response.json()

            if len(response.get("value")) != 0:
                for project in self._projects:
                    for group in response.get("value"):
                        name = project.get("name")
                        if self.__checkProjectPrivs(self._devopsLoginId, name, group):
                            duplicate = False
                            for p in res:
                                if p.get("id") == project.get("id"):
                                    duplicate = True
                            if not duplicate:
                                res.append(project)

                continuationToken = headers.get("x-ms-continuationtoken", None)
                if not continuationToken:
                    break

            else:
                break
        self._projects = res

    def __checkProjectPrivs(self, login, projectName, group):
        groupPrincipalName = group.get("principalName")

        writeGroups = [
            f"[{projectName}]\\{projectName} Team",
            f"[{projectName}]\\Contributors",
            f"[{projectName}]\\Project Administrators",
        ]
        pagingToken = None
        params = {}

        for g in writeGroups:
            if groupPrincipalName == g:
                originId = group.get("originId")
                while True:
                    if pagingToken:
                        params = {"pagingToken": pagingToken}
                    response = self._session.get(
                        f"https://vsaex.dev.azure.com/{self._org}/_apis/GroupEntitlements/{originId}/members",
                        params=params,
                        auth=self._auth,
                        headers=self._header,
                        verify=self._verifyCert,
                    ).json()

                    pagingToken = response.get("continuationToken")
                    if len(response.get("items")) != 0:
                        for user in response.get("items"):
                            if user.get("id") == login:
                                return True

                    else:
                        return False

    def listRepositories(self, project):
        logger.debug("Listing repositories")
        response = self._session.get(
            f"{self._baseURL}/{project}/_apis/git/repositories",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()
        return response.get("value")

    def listPipelines(self, project):
        logger.debug("Listing pipelines")
        response = self._session.get(
            f"{self._baseURL}/{project}/_apis/pipelines",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()
        return response.get("value")

    def addProject(self, project):
        logger.debug(f"Checking project: {project}")

        response = self._session.get(
            f"{self._baseURL}/_apis/projects/{project}",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()

        if response.get("id"):
            p = {"id": response.get("id"), "name": response.get("name")}
            self._projects.append(p)

    @classmethod
    def checkToken(cls, token, org):
        logger.verbose(f"Checking token: {token}")
        try:
            return (
                requests.get(
                    f"https://dev.azure.com/{org}/_apis/ConnectionData",
                    auth=("foo", token),
                    verify=cls._verifyCert,
                ).status_code
                == 200
            )
        except Exception as e:
            logger.error(e)
            return False

    def listProjectVariableGroupsSecrets(self, project):
        logger.debug(f"Listing variable groups for: {project}")
        response = self._session.get(
            f"{self._baseURL}/{project}/_apis/distributedtask/variablegroups",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        )

        if response.status_code != 200:
            raise DevOpsError("Can't list variable groups secrets.")

        response = response.json()

        res = []

        if response.get("count", 0) != 0:
            for variableGroup in response.get("value"):
                name = variableGroup.get("name")
                id = variableGroup.get("id")
                variables = []
                for var in variableGroup.get("variables").keys():
                    variables.append(var)
                res.append({"name": name, "id": id, "variables": variables})
        return res

    def listProjectSecureFiles(self, project):
        logger.debug(f"Listing secure files for: {project}")
        response = self._session.get(
            f"{self._baseURL}/{project}/_apis/distributedtask/securefiles",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        )

        if response.status_code != 200:
            raise DevOpsError("Can't list secure files.")

        response = response.json()

        res = []

        if response["count"]:
            for secureFile in response["value"]:
                res.append({"name": secureFile["name"], "id": secureFile["id"]})
        return res

    def authorizePipelineForResourceAccess(self, projectId, pipelineId, resource, resourceType):
        resourceId = resource["id"]

        logger.debug(f"Checking current pipeline permissions for: \"{resource['name']}\"")
        response = self._session.get(
            f"{self._baseURL}/{projectId}/_apis/pipelines/pipelinePermissions/{resourceType}/{resourceId}",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()

        allPipelines = response.get("allPipelines")
        if allPipelines and allPipelines.get("authorized"):
            return True

        for pipeline in response.get("pipelines"):
            if pipeline.get("id") == pipelineId:
                return True

        logger.debug(f"\"{resource['name']}\" has restricted permissions. Adding access permissions for the pipeline")
        response = self._session.patch(
            f"{self._baseURL}/{projectId}/_apis/pipelines/pipelinePermissions/{resourceType}/{resourceId}",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
            json={"pipelines": [{"id": pipelineId, "authorized": True}]},
        )

        if response.status_code != 200:
            logger.error(f"Error: unable to give the custom pipeline access to {resourceType}: \"{resource['name']}\"")
            return False
        return True

    def createGit(self, project):
        logger.debug(f"Creating git repo for: {project}")
        data = {"name": self._repoName, "project": {"id": project}}
        response = self._session.post(
            f"{self._baseURL}/{project}/_apis/git/repositories",
            json=data,
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()

        return response

    def deleteGit(self, project, repoId):
        logger.debug(f"Deleting git repo for: {project}")
        response = self._session.delete(
            f"{self._baseURL}/{project}/_apis/git/repositories/{repoId}",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        )
        return response.status_code == 204

    def createPipeline(self, project, repoId, path):
        logger.debug("creating pipeline")
        data = {
            "folder": None,
            "name": self._pipelineName,
            "configuration": {
                "type": "yaml",
                "path": path,
                "repository": {
                    "id": repoId,
                    "type": "azureReposGit",
                    "defaultBranch": self._branchName,
                },
            },
        }
        response = self._session.post(
            f"{self._baseURL}/{project}/_apis/pipelines",
            json=data,
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()
        return response.get("id")

    def runPipeline(self, project, pipelineId):
        logger.debug(f"Running pipeline: {pipelineId}")
        params = {
            "definition": {"id": pipelineId},
            "sourceBranch": f"refs/heads/{self._branchName}",
        }

        response = self._session.post(
            f"{self._baseURL}/{project}/_apis/build/Builds",
            json=params,
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()

        return response

    def __getBuilds(self, project):
        logger.debug(f"Getting builds.")

        return (
            self._session.get(
                f"{self._baseURL}/{project}/_apis/build/Builds",
                auth=self._auth,
                headers=self._header,
                verify=self._verifyCert,
            )
            .json()
            .get("value")
        )

    def __getBuildSources(self, project, buildId):

        return self._session.get(
            f"{self._baseURL}/{project}/_apis/build/Builds/{buildId}/sources",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()

    def getRunId(self, project, pipelineId):
        logger.debug(f"Getting RunId for pipeline: {pipelineId}")

        found = False

        for i in range(self._maxRetry):

            # Don't wait first time
            if i != 0:
                logger.warning(f"Run not available, sleeping for {self._sleepTime}s")
                time.sleep(self._sleepTime)

            for build in self.__getBuilds(project):

                if build.get("definition").get("id") == pipelineId:

                    buildId = build.get("id")
                    buildSource = self.__getBuildSources(project, buildId)

                    if (
                        buildSource.get("comment") == Git.ATTACK_COMMIT_MSG
                        and buildSource.get("author").get("email") == Git.EMAIL
                    ):
                        return buildId

            if i == (self._maxRetry):
                logger.error("Error: run still not ready.")

        return None

    def waitPipeline(self, project, pipelineId, runId):
        logger.info("Getting pipeline output")

        for i in range(self._maxRetry):

            if i != 0:
                logger.warning(f"Pipeline still running, sleeping for {self._sleepTime}s")
                time.sleep(self._sleepTime)

            response = self._session.get(
                f"{self._baseURL}/{project}/_apis/pipelines/{pipelineId}/runs/{runId}",
                json={},
                auth=self._auth,
                headers=self._header,
                verify=self._verifyCert,
            ).json()

            if response.get("state") == "completed":
                return response.get("result")
            if i == (self._maxRetry - 1):
                logger.error("Error: pipeline still not finished.")

        return None

    def __createPipelineOutputDir(self, projectName):
        makedirs(f"{self._outputDir}/{self._org}/{projectName}", exist_ok=True)

    def downloadPipelineOutput(self, projectId, runId):
        self.__createPipelineOutputDir(projectId)

        for i in range(self._maxRetry):

            if i != 0:
                logger.warning(f"Output not ready, sleeping for {self._sleepTime}s")
                time.sleep(self._sleepTime)

            buildTimeline = self._session.get(
                f"{self._baseURL}/{projectId}/_apis/build/builds/{runId}/timeline",
                json={},
                auth=self._auth,
                headers=self._header,
                verify=self._verifyCert,
            ).json()

            logs = [
                record["log"]["id"]
                for record in buildTimeline["records"]
                if record["name"] == DevOpsPipelineGenerator.taskName
            ]
            if len(logs) != 0:
                break

            if i == (self._maxRetry - 1):
                logger.error("Output still no ready, error !")
                return None

        logId = logs[0]

        logger.debug(f"Log ID of the extraction task: {logId}")

        for i in range(self._maxRetry):

            if i != 0:
                logger.warning(f"Output not ready, sleeping for {self._sleepTime}s")
                time.sleep(self._sleepTime)

            logOutput = self._session.get(
                f"{self._baseURL}/{projectId}/_apis/build/builds/{runId}/logs/{logId}",
                json={},
                auth=self._auth,
                headers=self._header,
                verify=self._verifyCert,
            ).json()
            if len(logOutput.get("value")) != 0:
                break
            if i == (self._maxRetry - 1):
                logger.error("Output still no ready, error !")
                return None

        date = time.strftime("%Y-%m-%d_%H-%M-%S")
        with open(f"{self._outputDir}/{self._org}/{projectId}/pipeline_{date}.log", "w") as f:
            for line in logOutput.get("value"):
                f.write(line + "\n")
        f.close()
        return f"pipeline_{date}.log"

    def __cleanRunLogs(self, projectId):
        logger.verbose("Cleaning run logs.")

        builds = self.__getBuilds(projectId)

        if len(builds) != 0:
            for build in builds:

                buildId = build.get("id")
                buildSource = self.__getBuildSources(projectId, buildId)

                if (
                    buildSource.get("comment") == (Git.ATTACK_COMMIT_MSG or Git.CLEAN_COMMIT_MSG)
                    and buildSource.get("author").get("email") == Git.EMAIL
                ):
                    return buildId

                self._session.delete(
                    f"{self._baseURL}/{projectId}/_apis/build/builds/{buildId}",
                    auth=self._auth,
                    headers=self._header,
                    verify=self._verifyCert,
                )

    def __cleanPipeline(self, projectId):
        logger.verbose(f"Removing pipeline.")

        response = self._session.get(
            f"{self._baseURL}/{projectId}/_apis/pipelines",
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()
        if response.get("count", 0) != 0:
            for pipeline in response.get("value"):
                if pipeline.get("name") == self._pipelineName:
                    pipelineId = pipeline.get("id")
                    self._session.delete(
                        f"{self._baseURL}/{projectId}/_apis/pipelines/{pipelineId}",
                        auth=self._auth,
                        headers=self._header,
                        verify=self._verifyCert,
                    )

    def deletePipeline(self, projectId):
        logger.debug("Deleting pipeline")
        response = self._session.get(
            f"{self._baseURL}/{projectId}/_apis/build/Definitions",
            json={},
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        ).json()
        if response.get("count", 0) != 0:
            for pipeline in response.get("value"):
                if pipeline.get("name") == self._pipelineName:
                    definitionId = pipeline.get("id")
                    self._session.delete(
                        f"{self._baseURL}/{projectId}/_apis/build/definitions/{definitionId}",
                        json={},
                        auth=self._auth,
                        headers=self._header,
                        verify=self._verifyCert,
                    )

    def cleanAllLogs(self, projectId):
        self.__cleanRunLogs(projectId)

    def listServiceConnections(self, projectId):
        logger.debug("Listing service connections")
        res = []
        response = self._session.get(
            f"{self._baseURL}/{projectId}/_apis/serviceendpoint/endpoints",
            json={},
            auth=self._auth,
            headers=self._header,
            verify=self._verifyCert,
        )

        if response.status_code != 200:
            raise DevOpsError("Can't list service connections.")

        response = response.json()

        if response.get("count", 0) != 0:
            res = response.get("value")
        return res

    def getFailureReason(self, projectId, runId):
        res = []

        response = self._session.get(
            f"{self._baseURL}/{projectId}/_apis/build/builds/{runId}",
            auth=self._auth,
            headers=self._header,
        ).json()
        for result in response.get("validationResults"):
            res.append(result.get("message"))

        try:
            timeline = self._session.get(
                f"{self._baseURL}/{projectId}/_apis/build/builds/{runId}/Timeline",
                auth=self._auth,
                headers=self._header,
            ).json()
            for record in timeline.get("records", []):
                if record.get("issues"):
                    for issue in record.get("issues"):
                        res.append(issue.get("message"))
        except:
            pass
        return res
