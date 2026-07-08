import requests

from nordstream.utils.constants import OUTPUT_DIR, DEFAULT_BRANCH_NAME, USER_AGENT


class BaseClient:
    """Shared HTTP/session scaffolding for platform CI/CD clients.

    Owns the session and the config properties that were previously
    re-declared in each platform client. Subclasses implement the
    platform-specific endpoints; this base performs no display and holds
    no orchestration logic.
    """

    _defaultHeaders = {"User-Agent": USER_AGENT}

    def __init__(self, token):
        self._token = token
        self._session = requests.Session()
        self._session.headers.update(self._defaultHeaders)
        self._outputDir = OUTPUT_DIR
        self._branchName = DEFAULT_BRANCH_NAME

    @property
    def token(self):
        return self._token

    @property
    def session(self):
        return self._session

    @property
    def outputDir(self):
        return self._outputDir

    @outputDir.setter
    def outputDir(self, value):
        self._outputDir = value

    @property
    def branchName(self):
        return self._branchName

    @branchName.setter
    def branchName(self, value):
        self._branchName = value

    @property
    def defaultBranchName(self):
        return DEFAULT_BRANCH_NAME

    def _get(self, url, **kwargs):
        return self._session.get(url, **kwargs)

    def _post(self, url, **kwargs):
        return self._session.post(url, **kwargs)
