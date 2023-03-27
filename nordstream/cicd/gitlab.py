import requests
from nordstream.utils.log import logger


class GitLab:
    _auth = None
    _session = None
    _token = None
    _projects = []
    _outputDir = "nord-stream-logs"
    _header = None
    # _header = {"Accept": "application/vnd.github+json"}

    def __init__(self, token, org):
        self._token = token
        self._header = {"PRIVATE-TOKEN": token}
        self._session = requests.Session()
        # self._session.headers.update({"PRIVATE-TOKEN": token})

    @property
    def projects(self):
        return self._projects

    @property
    def token(self):
        return self._token

    @classmethod
    def checkToken(cls, token):
        logger.verbose(f"Checking token: {token}")
        # from https://docs.gitlab.com/ee/api/rest/index.html#personalprojectgroup-access-tokens
        return (
            requests.get(
                f"https://gitlab.com/api/v4/projects",
                headers={"PRIVATE-TOKEN": token},
            ).status_code
            == 200
        )

    def retieveUsernameFromToken(self):
        logger.verbose(f"Retrieving user from token")
        response = self._session.get(f"https://gitlab.com/api/v4/user", headers=self._header).json()

        return response["username"]

    def listProjects(self):
        logger.verbose(f"Listing projects")

        username = self.retieveUsernameFromToken()

        response = self._session.get(f"https://gitlab.com/api/v4/users/{username}/projects", headers=self._header)

        # try catch on response.status_code
        if response.status_code == 200:
            # Print the project names and IDs
            for project in response.json():
                p = {
                    "id": project.get("id"),
                    "path_with_namespace": project.get("path_with_namespace"),
                    "name": project.get("name"),
                }
                self._projects.append(p)
        else:
            logger.error("Error while retrieving projects")
            logger.debug(response.json())

    def listVariablesFromProject(self, project):
        id = project.get("id")
        res = []
        response = self._session.get(f"https://gitlab.com/api/v4/projects/{id}/variables", headers=self._header)
        if response.status_code == 200:
            # logger.debug(response.json())
            for variable in response.json():
                # print(variable['key'], variable['value'], variable['protected'])
                res.append({"key": variable["key"], "value": variable["value"], "protected": variable["protected"]})
        return res
