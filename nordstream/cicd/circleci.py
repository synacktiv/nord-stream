import requests
import time
from os import makedirs
from nordstream.utils.log import logger
from nordstream.utils.constants import CIRCLECI_API_URL, OUTPUT_DIR, USER_AGENT


class CircleCIError(Exception):
    pass


class CircleCIBadCredentials(CircleCIError):
    pass


class CircleCI:
    """
    Thin wrapper around the CircleCI REST API v2.
    Authentication uses the `Circle-Token` header.

    Project slugs follow the pattern:
        github  → "gh/<org>/<repo>"
        gitlab  → "gl/<group>/<project>"
    """

    _token = None
    _session = None
    _outputDir = OUTPUT_DIR
    _header = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    _sleepTime = 15
    _maxRetry = 20

    def __init__(self, token):
        self._token = token
        self._session = requests.Session()
        self._header["Circle-Token"] = token

    # ------------------------------------------------------------------
    # Token / identity
    # ------------------------------------------------------------------

    @staticmethod
    def checkToken(token):
        """Return True if the token is valid (GET /me returns 200)."""
        logger.verbose(f"Checking CircleCI token")
        headers = {
            "Circle-Token": token,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            r = requests.get(f"{CIRCLECI_API_URL}/me", headers=headers, timeout=10)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def getMe(self):
        """Return the /me response dict."""
        r = self._session.get(f"{CIRCLECI_API_URL}/me", headers=self._header)
        if r.status_code == 401:
            raise CircleCIBadCredentials("Invalid CircleCI token.")
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Organisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _isRFC4122UUID(value):
        """Return True only for standard 8-4-4-4-12 hex UUID strings."""
        import re
        return bool(re.match(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            value, re.I
        ))

    def getCollaborations(self):
        """
        Return the list of orgs the token has access to, from GET /me/collaborations.
        Each entry has: id (UUID), slug (vcsType/orgSlug), name, vcs_type.
        """
        logger.debug("Fetching collaborations from /me/collaborations")
        r = self._session.get(f"{CIRCLECI_API_URL}/me/collaborations", headers=self._header)
        if r.status_code in (401, 403):
            raise CircleCIBadCredentials("Invalid CircleCI token.")
        r.raise_for_status()
        return r.json()

    def getOrgId(self, vcsType, orgName):
        """
        Resolve the CircleCI organisation UUID for the given vcsType + orgName.

        Strategy by vcsType:
          "gh" / "gl"  → try GET /org/<github|gitlab>/<orgName>; fall back to
                          scanning /me/collaborations if 404.
          "circleci"   → the orgName is the slug portion of "circleci/<orgSlug>".
                         The /org endpoint does not support this format, so we
                         resolve the UUID via /me/collaborations by matching the
                         full slug "circleci/<orgName>".

        If orgName is already a standard UUID it is returned directly.
        """
        # Already a proper UUID — no lookup needed.
        if self._isRFC4122UUID(orgName):
            logger.debug(f"orgName '{orgName}' is already a UUID — using directly")
            return orgName

        # For "circleci" vcsType, /org endpoint returns 404.
        # Resolve via /me/collaborations instead.
        if vcsType == "circleci":
            return self._getOrgIdFromCollaborations(f"circleci/{orgName}")

        # Classic GitHub / GitLab OAuth integrations.
        vcs_slug_map = {"gh": "github", "gl": "gitlab"}
        slug_prefix = vcs_slug_map.get(vcsType, vcsType)
        slug = f"{slug_prefix}/{orgName}"

        logger.debug(f"Fetching org ID via /org/{slug}")
        r = self._session.get(f"{CIRCLECI_API_URL}/org/{slug}", headers=self._header)
        if r.status_code == 200:
            return r.json().get("id")

        # Fall back to collaborations scan (covers cases where /org returns 404).
        logger.debug(f"/org/{slug} returned {r.status_code}, falling back to collaborations")
        return self._getOrgIdFromCollaborations(slug)

    def _getOrgIdFromCollaborations(self, fullSlug):
        """
        Scan /me/collaborations and return the UUID for the entry whose slug
        matches fullSlug (e.g. "circleci/H3xy1JwUnkBcQApbzLKwzq" or
        "github/myorg").  Returns None if not found.
        """
        logger.debug(f"Resolving org UUID from collaborations for slug '{fullSlug}'")
        try:
            collabs = self.getCollaborations()
        except Exception as e:
            logger.debug(f"Could not fetch collaborations: {e}")
            return None

        for entry in collabs:
            if entry.get("slug", "").lower() == fullSlug.lower():
                org_id = entry.get("id")
                logger.debug(f"Resolved org UUID: {org_id}")
                return org_id

        logger.debug(f"No collaboration found matching slug '{fullSlug}'")
        return None

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def listProjects(self):
        """Return a list of followed project slugs."""
        logger.debug("Listing CircleCI followed projects")
        r = self._session.get(f"{CIRCLECI_API_URL}/me/projects", headers=self._header)
        r.raise_for_status()
        items = r.json().get("items", [])
        return [p.get("slug") for p in items if p.get("slug")]

    # ------------------------------------------------------------------
    # Project environment variables
    # ------------------------------------------------------------------

    def listProjectEnvVars(self, projectSlug):
        """
        Return a list of env var names for the given project.
        Values are NOT returned by the API (write-only).
        """
        logger.debug(f"Listing project env vars for {projectSlug}")
        r = self._session.get(
            f"{CIRCLECI_API_URL}/project/{projectSlug}/envvar",
            headers=self._header,
        )
        if r.status_code == 404:
            return []
        if r.status_code in (401, 403):
            raise CircleCIError(f"Not authorised to list env vars for {projectSlug}")
        r.raise_for_status()
        items = r.json().get("items", [])
        return [item.get("name") for item in items if item.get("name")]

    # ------------------------------------------------------------------
    # Contexts (org-level secrets)
    # ------------------------------------------------------------------

    def listContexts(self, orgIdOrSlug):
        """
        Return a list of dicts {id, name} for all contexts owned by the org.

        orgIdOrSlug: either the UUID returned by getOrgId(), or a vcs-prefixed
                     slug like "github/myorg" / "gitlab/mygroup" which the API
                     accepts via the owner-slug parameter.
        """
        logger.debug(f"Listing contexts for org {orgIdOrSlug}")
        contexts = []
        url = f"{CIRCLECI_API_URL}/context"

        # Decide whether to use owner-id or owner-slug
        if "/" in str(orgIdOrSlug):
            params = {"owner-slug": orgIdOrSlug}
        else:
            params = {"owner-id": orgIdOrSlug}

        while url:
            r = self._session.get(url, headers=self._header, params=params)
            if r.status_code in (401, 403):
                raise CircleCIError("Not authorised to list contexts.")
            r.raise_for_status()
            data = r.json()
            for ctx in data.get("items", []):
                contexts.append({"id": ctx.get("id"), "name": ctx.get("name")})
            next_token = data.get("next_page_token")
            if next_token:
                base_params = dict(params)
                base_params["page-token"] = next_token
                params = base_params
            else:
                url = None

        return contexts

    def listContextEnvVars(self, contextId):
        """
        Return a list of env var names stored in a context.
        Values are NOT returned by the API (write-only).
        """
        logger.debug(f"Listing env vars for context {contextId}")
        r = self._session.get(
            f"{CIRCLECI_API_URL}/context/{contextId}/environment-variable",
            headers=self._header,
        )
        if r.status_code in (401, 403):
            raise CircleCIError(f"Not authorised to list env vars for context {contextId}")
        r.raise_for_status()
        items = r.json().get("items", [])
        return [item.get("variable") for item in items if item.get("variable")]

    # ------------------------------------------------------------------
    # Pipeline / workflow lifecycle
    # ------------------------------------------------------------------

    def triggerPipeline(self, projectSlug, branch):
        """
        Trigger a new pipeline on the given branch (classic OAuth integrations only).
        Returns the pipeline id string, or None on failure.
        Not supported for GitHub App / GitLab App projects (vcsType "circleci") —
        use waitForPipelineOnBranch() instead.
        """
        logger.debug(f"Triggering pipeline for {projectSlug} on branch {branch}")
        payload = {"branch": branch}
        r = self._session.post(
            f"{CIRCLECI_API_URL}/project/{projectSlug}/pipeline",
            headers=self._header,
            json=payload,
        )
        if r.status_code in (401, 403):
            raise CircleCIError(f"Not authorised to trigger pipeline for {projectSlug}")
        r.raise_for_status()
        return r.json().get("id")

    def waitForPipelineOnBranch(self, projectSlug, branch):
        """
        For GitHub App / GitLab App integrations the git push automatically
        triggers a pipeline.  Poll GET /project/<slug>/pipeline until a pipeline
        for the given branch appears (most-recent first), then return its id.
        Returns None on timeout.
        """
        logger.info(f"Waiting for pipeline to appear on branch '{branch}'")
        for i in range(self._maxRetry):
            time.sleep(self._sleepTime)
            r = self._session.get(
                f"{CIRCLECI_API_URL}/project/{projectSlug}/pipeline",
                headers=self._header,
                params={"branch": branch},
            )
            if r.status_code != 200:
                logger.warning(f"Pipeline list returned {r.status_code}, retrying ({i+1}/{self._maxRetry})")
                continue
            items = r.json().get("items", [])
            if items:
                pipeline_id = items[0].get("id")
                logger.verbose(f"Found pipeline: {pipeline_id}")
                return pipeline_id
            logger.warning(f"No pipeline yet on branch '{branch}', retrying ({i+1}/{self._maxRetry})")
        logger.error(f"Timed out waiting for pipeline on branch '{branch}'")
        return None

    def getPipelineWorkflows(self, pipelineId):
        """Return the list of workflow dicts for a pipeline."""
        r = self._session.get(
            f"{CIRCLECI_API_URL}/pipeline/{pipelineId}/workflow",
            headers=self._header,
        )
        r.raise_for_status()
        return r.json().get("items", [])

    def waitPipeline(self, pipelineId):
        """
        Poll until the first workflow of the pipeline reaches a terminal state.
        Returns (workflowId, status) where status is one of:
            success | failed | error | canceled | unauthorized
        Returns (None, None) on timeout.
        """
        logger.info("Waiting for CircleCI pipeline to complete")
        terminal = {"success", "failed", "error", "canceled", "unauthorized"}

        for i in range(self._maxRetry):
            time.sleep(self._sleepTime)
            workflows = self.getPipelineWorkflows(pipelineId)
            if not workflows:
                logger.warning(f"No workflow yet, retrying ({i+1}/{self._maxRetry})")
                continue
            wf = workflows[0]
            status = wf.get("status")
            wfId = wf.get("id")
            logger.verbose(f"Workflow status: {status}")
            if status in terminal:
                return wfId, status
            logger.warning(f"Workflow not finished ({status}), sleeping for {self._sleepTime}s")

        logger.error("Timed out waiting for CircleCI pipeline.")
        return None, None

    def getWorkflowJobs(self, workflowId):
        """Return the list of job dicts for a workflow."""
        r = self._session.get(
            f"{CIRCLECI_API_URL}/workflow/{workflowId}/job",
            headers=self._header,
        )
        r.raise_for_status()
        return r.json().get("items", [])

    def cancelWorkflow(self, workflowId):
        """Request cancellation of a workflow."""
        logger.debug(f"Cancelling workflow {workflowId}")
        self._session.post(
            f"{CIRCLECI_API_URL}/workflow/{workflowId}/cancel",
            headers=self._header,
        )

    # ------------------------------------------------------------------
    # Job output
    # ------------------------------------------------------------------

    def getJobStepOutput(self, projectSlug, jobNumber):
        """
        Retrieve the raw output of the 'command' step for the given job.

        The v2 API /project/{slug}/job/{num} does not return step details for
        GitHub App / GitLab App projects.  The v1.1 API does, and it works for
        all integration types.

        Returns the raw log text (JSON array of message objects), or None.
        """
        logger.debug(f"Fetching step output for job {jobNumber} in {projectSlug}")

        # v1.1 returns steps[].actions[].output_url for all integration types.
        r = self._session.get(
            f"https://circleci.com/api/v1.1/project/{projectSlug}/{jobNumber}",
            headers=self._header,
        )
        if r.status_code == 404:
            logger.debug(f"v1.1 job endpoint returned 404 for job {jobNumber}")
            return None
        r.raise_for_status()
        job_data = r.json()

        # Walk through steps → actions to find the "command" step output URL
        for step in job_data.get("steps", []):
            for action in step.get("actions", []):
                if action.get("name") == "command" and action.get("output_url"):
                    output_url = action["output_url"]
                    logger.debug(f"Downloading output from {output_url}")
                    out_r = self._session.get(output_url, headers=self._header)
                    if out_r.status_code == 200:
                        return out_r.text
        return None

    def downloadJobOutput(self, projectSlug, jobNumber, outputDir, outputName):
        """
        Download and save the step output for the given job to disk.
        Returns the saved file path, or None if no output was found.
        """
        makedirs(outputDir, exist_ok=True)
        text = self.getJobStepOutput(projectSlug, jobNumber)
        if text is None:
            logger.error(f"No output found for job {jobNumber}")
            return None

        date = time.strftime("%Y-%m-%d_%H-%M-%S")
        filePath = f"{outputDir}/circleci_{outputName}_{date}.log"
        with open(filePath, "w") as f:
            f.write(text)
        logger.debug(f"Job output saved to {filePath}")
        return filePath

    @property
    def outputDir(self):
        return self._outputDir

    @outputDir.setter
    def outputDir(self, value):
        self._outputDir = value
