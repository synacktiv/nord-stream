import requests

from nordstream.utils.constants import OUTPUT_DIR, DEFAULT_BRANCH_NAME, USER_AGENT


class BaseClient:
    """Shared HTTP/session scaffolding for platform CI/CD clients.

    Owns the session and the config attributes that were previously re-declared
    in each platform client. Subclasses implement the platform-specific
    endpoints; this base performs no display and holds no orchestration logic.
    """

    _defaultHeaders = {"User-Agent": USER_AGENT}
    defaultBranchName = DEFAULT_BRANCH_NAME

    def __init__(self, token):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update(self._defaultHeaders)
        self.outputDir = OUTPUT_DIR
        self.branchName = DEFAULT_BRANCH_NAME

    def _get(self, url, **kwargs):
        return self.session.get(url, **kwargs)

    def _post(self, url, **kwargs):
        return self.session.post(url, **kwargs)
