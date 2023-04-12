import requests
from nordstream.utils.log import logger


class GitLab:
    _auth = None
    _session = None
    _token = None
    _projects = []
    _outputDir = "nord-stream-logs"
    _header = None
    _gitlabURL = None
    _verifyCert = True
    # _header = {"Accept": "application/vnd.github+json"}

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
    def token(self):
        return self._token

    @property
    def url(self):
        return self._url

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
            # logger.debug(response.json())
            for variable in response.json():
                # print(variable['key'], variable['value'], variable['protected'])
                res.append({"key": variable["key"], "value": variable["value"], "protected": variable["protected"]})
        return res

    def addProject(self, project=None):
        logger.debug(f"Checking project: {project}")

        # username = self.retieveUsernameFromToken()
        # response = self._session.get(f"https://gitlab.com/api/v4/users/{username}/projects", headers=self._header)

        i = 1
        while True:

            if project == None:
                params = {"per_page": 100, "page": i}
            else:
                params = {"per_page": 100, "page": i, "search_namespaces": True, "search": project}

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
