import requests
from os import makedirs
from nordstream.utils.log import logger
from nordstream.utils.errors import GitLabError


class GitLab:
    _auth = None
    _session = None
    _token = None
    _projects = []
    _groups = []
    _outputDir = "nord-stream-logs"
    _header = None
    _gitlabURL = None
    _verifyCert = True

    def __init__(self, url, token):
        self._gitlabURL = url.strip("/")
        self._token = token
        self._header = {"PRIVATE-TOKEN": token}
        self._session = requests.Session()
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
        return self._url

    @property
    def outputDir(self):
        return self._outputDir

    @outputDir.setter
    def outputDir(self, value):
        self._outputDir = value

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

    def retieveUsernameFromToken(self):
        logger.verbose(f"Retrieving user from token")
        response = self._session.get(
            f"{self._gitlabURL}/api/v4/user",
            headers=self._header,
            verify=self._verifyCert,
        ).json()

        return response["username"]

    def listVariablesFromProject(self, project):
        id = project.get("id")
        res = []
        response = self._session.get(
            f"{self._gitlabURL}/api/v4/projects/{id}/variables",
            headers=self._header,
            verify=self._verifyCert,
        )
        if response.status_code == 200:

            path = self.__createOutputDir(project.get("path_with_namespace"))

            f = open(f"{path}/secrets.txt", "w")

            for variable in response.json():
                res.append({"key": variable["key"], "value": variable["value"], "protected": variable["protected"]})

                f.write(f"{variable['key']}={variable['value']}\n")

            f.close()
        elif response.status_code == 403:
            raise GitLabError(response.json().get("message"))
        return res

    def listVariablesFromGroup(self, group):
        id = group.get("id")
        res = []
        response = self._session.get(
            f"{self._gitlabURL}/api/v4/groups/{id}/variables",
            headers=self._header,
            verify=self._verifyCert,
        )
        if response.status_code == 200:

            path = self.__createOutputDir(group.get("full_path"))

            f = open(f"{path}/secrets.txt", "w")

            for variable in response.json():
                res.append({"key": variable["key"], "value": variable["value"], "protected": variable["protected"]})

                f.write(f"{variable['key']}={variable['value']}\n")

            f.close()
        elif response.status_code == 403:
            raise GitLabError(response.json().get("message"))
        return res

    def listVariablesFromInstance(self):
        res = []
        response = self._session.get(
            f"{self._gitlabURL}/api/v4/admin/ci/variables",
            headers=self._header,
            verify=self._verifyCert,
        )
        if response.status_code == 200:

            path = self.__createOutputDir("")

            f = open(f"{path}/secrets.txt", "w")

            for variable in response.json():
                res.append({"key": variable["key"], "value": variable["value"], "protected": variable["protected"]})

                f.write(f"{variable['key']}={variable['value']}\n")

            f.close()
        elif response.status_code == 403:
            raise GitLabError(response.json().get("message"))
        return res

    def addProject(self, project=None, filterWrite=False):
        logger.debug(f"Checking project: {project}")

        # username = self.retieveUsernameFromToken()
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
