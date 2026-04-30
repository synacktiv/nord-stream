import re
import requests
from requests.adapters import HTTPAdapter
import time
from os import makedirs
from nordstream.utils.log import logger
from nordstream.utils.constants import CIRCLECI_API_URL, OUTPUT_DIR, USER_AGENT


class _TimeoutHTTPAdapter(HTTPAdapter):
    """Requests HTTPAdapter that enforces a default timeout on every request."""

    def __init__(self, timeout, *args, **kwargs):
        self._timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        kwargs.setdefault("timeout", self._timeout)
        return super().send(request, **kwargs)


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
    _maxRetry = 40          # 40 × 15s = 10 minutes max wait
    _requestTimeout = 30    # seconds per individual HTTP request

    def __init__(self, token):
        self._token = token
        self._session = requests.Session()
        self._header["Circle-Token"] = token
        # Enforce a per-request timeout on every call made through this session
        # so slow/hanging API responses never block indefinitely.
        _adapter = _TimeoutHTTPAdapter(timeout=self._requestTimeout)
        self._session.mount("https://", _adapter)
        self._session.mount("http://", _adapter)

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

    _UUID_RE = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.I,
    )

    @classmethod
    def _isRFC4122UUID(cls, value):
        """Return True only for standard 8-4-4-4-12 hex UUID strings."""
        return bool(cls._UUID_RE.match(value))

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
        matches fullSlug (e.g. "circleci/<org-slug>" or "github/<org>").
        Returns None if not found.
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

        # Decide whether to use owner-id or owner-slug
        if "/" in str(orgIdOrSlug):
            params = {"owner-slug": orgIdOrSlug}
        else:
            params = {"owner-id": orgIdOrSlug}

        while True:
            r = self._session.get(f"{CIRCLECI_API_URL}/context", headers=self._header, params=params)
            if r.status_code in (401, 403):
                raise CircleCIError("Not authorised to list contexts.")
            r.raise_for_status()
            data = r.json()
            for ctx in data.get("items", []):
                contexts.append({"id": ctx.get("id"), "name": ctx.get("name")})
            next_token = data.get("next_page_token")
            if not next_token:
                break
            params = {**params, "page-token": next_token}

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

    def findPipelineOnBranch(self, projectSlug, branch, maxRetry=None):
        """
        Poll GET /project/<slug>/pipeline?branch=<branch> until a pipeline
        for the given branch appears (most-recent first), then return its id.

        Used after a git push to pick up the webhook-triggered pipeline before
        resorting to an explicit API trigger call.

        maxRetry: override the instance default for a shorter probe window.
        Returns None if no pipeline appears within the retry window.
        """
        retries = maxRetry if maxRetry is not None else self._maxRetry
        logger.verbose(f"Looking for pipeline on branch '{branch}' ({retries} retries)")
        for i in range(retries):
            time.sleep(self._sleepTime)
            r = self._session.get(
                f"{CIRCLECI_API_URL}/project/{projectSlug}/pipeline",
                headers=self._header,
                params={"branch": branch},
            )
            if r.status_code != 200:
                logger.verbose(f"Pipeline list returned {r.status_code}, retrying ({i+1}/{retries})")
                continue
            items = r.json().get("items", [])
            if items:
                pipeline_id = items[0].get("id")
                logger.verbose(f"Found webhook-triggered pipeline: {pipeline_id}")
                return pipeline_id
            logger.verbose(f"No pipeline yet on branch '{branch}', retrying ({i+1}/{retries})")
        return None

    def getPipelineWorkflows(self, pipelineId):
        """Return the list of workflow dicts for a pipeline."""
        r = self._session.get(
            f"{CIRCLECI_API_URL}/pipeline/{pipelineId}/workflow",
            headers=self._header,
        )
        r.raise_for_status()
        return r.json().get("items", [])

    def getPipeline(self, pipelineId):
        """Return the pipeline details dict for the given pipeline ID."""
        r = self._session.get(
            f"{CIRCLECI_API_URL}/pipeline/{pipelineId}",
            headers=self._header,
        )
        r.raise_for_status()
        return r.json()

    def waitPipeline(self, pipelineId):
        """
        Poll until the first workflow of the pipeline reaches a terminal state.
        Returns (workflowId, status) where status is one of:
            success | failed | error | canceled | unauthorized

        Raises CircleCIError immediately if the pipeline itself errored before
        creating any workflow (e.g. config file not found, validation error) —
        in that case retrying would never produce a workflow.

        Returns (None, None) only on genuine timeout (pipeline still running
        after all retries are exhausted).
        """
        logger.info("Waiting for CircleCI pipeline to complete")
        terminal = {"success", "failed", "error", "canceled", "unauthorized"}

        for i in range(self._maxRetry):
            time.sleep(self._sleepTime)

            # Check pipeline-level state first: "errored" means the pipeline
            # itself failed before spawning any workflow (e.g. bad config).
            # Raise immediately so the caller surfaces a clean error message
            # rather than looping until timeout.
            pipeline = self.getPipeline(pipelineId)
            pipeline_state = pipeline.get("state")
            if pipeline_state == "errored":
                errors = pipeline.get("errors", [])
                messages = [err.get("message", "") for err in errors if err.get("message")]
                detail = "; ".join(messages) if messages else "unknown error"
                raise CircleCIError(
                    f"Pipeline errored before creating a workflow: {detail}"
                )

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
        r = self._session.post(
            f"{CIRCLECI_API_URL}/workflow/{workflowId}/cancel",
            headers=self._header,
        )
        if r.status_code not in (200, 202):
            logger.verbose(f"cancelWorkflow returned HTTP {r.status_code} for {workflowId}")

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

    # ------------------------------------------------------------------
    # Project discovery by GitHub/GitLab repo
    # ------------------------------------------------------------------

    def listFollowedProjects(self):
        """
        Return all projects the token follows via GET /api/v1.1/projects.
        Each entry includes: vcs_type, username, reponame, vcs_url, default_branch.
        """
        logger.debug("Listing followed projects via v1.1 API")
        r = self._session.get(
            "https://circleci.com/api/v1.1/projects",
            headers=self._header,
        )
        if r.status_code in (401, 403):
            raise CircleCIBadCredentials("Invalid CircleCI token.")
        r.raise_for_status()
        return r.json()

    def findProjectByRepo(self, repoFullName):
        """
        Auto-discover the CircleCI project linked to a GitHub/GitLab repo.

        Strategy:
          1. GET /api/v1.1/projects — single request, all followed projects.
             For classic GitHub/GitLab OAuth entries (vcs_type "github"/"gitlab"),
             the repo can be matched directly by username+reponame with no further
             API calls.
          2. For GitHub App / GitLab App entries (vcs_type "circleci"), the v1.1
             entry does not expose the underlying GitHub repo name.  Fall back to
             scanning recent pipeline history for those orgs only.

        Returns a dict on success:
          {
            "project_slug":     "<vcs>/<org>/<project>",
            "project_id":       "<uuid>",
            "circle_org":       "<org-slug-or-uuid>",
            "circle_project":   "<project-slug-or-uuid>",
            "vcs_type":         "gh" | "gl" | "circleci",
            "repo_external_id": "<vcs-provider-repo-id>",
            "default_branch":   "main",
          }
        Returns None if no match is found.
        """
        logger.verbose(f"Auto-resolving CircleCI project for repo '{repoFullName}'")

        # vcs_type values returned by the v1.1 API → CircleCI slug prefix
        vcs_prefix_map = {"github": "gh", "gitlab": "gl", "circleci": "circleci"}

        circleci_type_entries = []  # fallback list for GitHub App / GitLab App projects

        try:
            projects = self.listFollowedProjects()
        except Exception as e:
            logger.debug(f"Could not list followed projects: {e}")
            projects = []

        for proj in projects:
            vcs_raw = proj.get("vcs_type", "")
            username = proj.get("username", "")
            reponame = proj.get("reponame", "")
            default_branch = proj.get("default_branch", "main")
            vcs_url = proj.get("vcs_url", "")

            if vcs_raw in ("github", "gitlab"):
                # Classic OAuth: username+reponame is the GitHub/GitLab org+repo directly.
                found_name = f"{username}/{reponame}"
                if found_name.lower() != repoFullName.lower():
                    continue

                vcs_type = vcs_prefix_map[vcs_raw]
                project_slug = f"{vcs_type}/{username}/{reponame}"
                details = self.getProjectDetails(project_slug)
                project_id = details.get("id") if details else None
                circle_org = username
                circle_project = reponame

                logger.verbose(f"Resolved via v1.1 projects: {project_slug}")
                return {
                    "project_slug":     project_slug,
                    "project_id":       project_id,
                    "circle_org":       circle_org,
                    "circle_project":   circle_project,
                    "vcs_type":         vcs_type,
                    "repo_external_id": None,
                    "default_branch":   default_branch,
                }

            elif vcs_raw == "circleci":
                # GitHub App / GitLab App: vcs_url = "//circleci.com/{orgUUID}/{projUUID}"
                # Cannot match by GitHub repo name here — defer to pipeline scan.
                circleci_type_entries.append(proj)

        # Fallback: scan recent pipeline history for GitHub App / GitLab App projects.
        # Scoped only to the circleci-type orgs found above, limiting scan surface.
        if circleci_type_entries:
            result = self._findProjectByRepoInPipelines(repoFullName, circleci_type_entries)
            if result:
                return result

        logger.verbose(f"No CircleCI project found for repo '{repoFullName}'")
        return None

    def _findProjectByRepoInPipelines(self, repoFullName, circleCIEntries):
        """
        Scan recent pipeline history for GitHub App / GitLab App projects to find
        one linked to the given GitHub/GitLab repo.
        Limited to 3 pages per org to avoid hanging on large pipeline histories.
        """
        max_pages_per_org = 3

        # Build the set of org slugs to scan from the v1.1 entries
        org_slugs_seen = set()
        for proj in circleCIEntries:
            vcs_url = proj.get("vcs_url", "")
            # vcs_url format: "//circleci.com/{orgUUID}/{projUUID}"
            parts = vcs_url.lstrip("/").split("/")
            if len(parts) >= 2:
                org_uuid = parts[1]  # second path component is orgUUID
                org_slug = f"circleci/{org_uuid}"
                org_slugs_seen.add(org_slug)

        for org_slug in org_slugs_seen:
            logger.verbose(f"Scanning org '{org_slug}' for repo '{repoFullName}'")
            params = {"org-slug": org_slug}
            next_token = None
            pages_scanned = 0

            while pages_scanned < max_pages_per_org:
                if next_token:
                    params["page-token"] = next_token
                try:
                    r = self._session.get(
                        f"{CIRCLECI_API_URL}/pipeline",
                        headers=self._header,
                        params=params,
                    )
                except requests.Timeout:
                    logger.verbose(f"Timeout scanning pipelines for '{org_slug}', skipping")
                    break
                if r.status_code != 200:
                    break
                pages_scanned += 1
                data = r.json()

                for pipeline in data.get("items", []):
                    tp = pipeline.get("trigger_parameters", {})
                    gh_app = tp.get("github_app", {})
                    git_params = tp.get("git", {})

                    found_name = gh_app.get("repo_full_name")
                    if not found_name:
                        repo_url = git_params.get("repo_url", "")
                        parts = repo_url.rstrip("/").split("/")
                        if len(parts) >= 2:
                            found_name = "/".join(parts[-2:])

                    if not found_name or found_name.lower() != repoFullName.lower():
                        continue

                    project_slug = pipeline.get("project_slug", "")
                    slug_parts = project_slug.split("/")
                    if len(slug_parts) != 3:
                        continue

                    vcs_type, circle_org, circle_project = slug_parts
                    details = self.getProjectDetails(project_slug)
                    project_id = details.get("id") if details else None
                    default_branch = (
                        gh_app.get("default_branch")
                        or git_params.get("default_branch")
                        or "main"
                    )

                    logger.verbose(f"Resolved via pipeline scan: {project_slug}")
                    return {
                        "project_slug":     project_slug,
                        "project_id":       project_id,
                        "circle_org":       circle_org,
                        "circle_project":   circle_project,
                        "vcs_type":         vcs_type,
                        "repo_external_id": gh_app.get("repo_id"),
                        "default_branch":   default_branch,
                    }

                next_token = data.get("next_page_token")
                if not next_token:
                    break

        return None

    def getProjectDetails(self, projectSlug):
        """
        Return the project details dict for the given slug.
        Includes: id (UUID), name, organization_id, vcs_info.
        """
        logger.debug(f"Getting project details for {projectSlug}")
        r = self._session.get(
            f"{CIRCLECI_API_URL}/project/{projectSlug}",
            headers=self._header,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


