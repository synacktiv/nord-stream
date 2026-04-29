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

    # ------------------------------------------------------------------
    # Project details
    # ------------------------------------------------------------------

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

    def listProjectsForOrg(self, orgSlug):
        """
        Discover all projects under an org by scanning recent pipelines.
        Uses GET /pipeline?org-slug=<orgSlug> which works for all VCS types.

        Returns a list of dicts:
          {
            "project_slug":   "circleci/H3xy.../RZ3k...",
            "project_id":     "c6d4d2bc-...",        # UUID, needed for pipeline defs
            "repo_full_name": "ScaumAcktiv/testrepo", # "org/repo" for the VCS host
            "repo_url":       "https://github.com/ScaumAcktiv/testrepo",
            "default_branch": "main",
            "repo_external_id": "1224368302",         # VCS provider repo ID
          }
        """
        logger.debug(f"Discovering projects for org slug '{orgSlug}'")
        # slug → partial info dict; we may need multiple pipelines to fill all fields
        partial = {}
        params = {"org-slug": orgSlug}
        next_token = None

        while True:
            if next_token:
                params["page-token"] = next_token
            r = self._session.get(
                f"{CIRCLECI_API_URL}/pipeline",
                headers=self._header,
                params=params,
            )
            if r.status_code in (401, 403):
                raise CircleCIError("Not authorised to list pipelines.")
            if r.status_code == 404:
                break
            r.raise_for_status()
            data = r.json()

            for pipeline in data.get("items", []):
                slug = pipeline.get("project_slug")
                if not slug:
                    continue

                # Extract git repo info from trigger_parameters
                tp = pipeline.get("trigger_parameters", {})
                gh_app = tp.get("github_app", {})
                git_params = tp.get("git", {})
                vcs_info = pipeline.get("vcs", {})

                repo_full_name = gh_app.get("repo_full_name")
                if not repo_full_name:
                    target_url = vcs_info.get("target_repository_url", "")
                    parts = target_url.rstrip("/").split("/")
                    if len(parts) >= 2:
                        repo_full_name = "/".join(parts[-2:])

                repo_url = (
                    gh_app.get("repo_url")
                    or git_params.get("repo_url")
                    or vcs_info.get("target_repository_url")
                )
                default_branch = (
                    gh_app.get("default_branch")
                    or git_params.get("default_branch")
                    or "main"
                )
                repo_external_id = gh_app.get("repo_id")

                # Merge into partial dict — keep the first non-None value per field
                entry = partial.setdefault(slug, {
                    "repo_full_name": None,
                    "repo_url": None,
                    "default_branch": "main",
                    "repo_external_id": None,
                })
                if repo_full_name and not entry["repo_full_name"]:
                    entry["repo_full_name"] = repo_full_name
                if repo_url and not entry["repo_url"]:
                    entry["repo_url"] = repo_url
                if default_branch and entry["default_branch"] == "main":
                    entry["default_branch"] = default_branch
                if repo_external_id and not entry["repo_external_id"]:
                    entry["repo_external_id"] = repo_external_id

            next_token = data.get("next_page_token")
            if not next_token:
                break

        # Post-process: resolve project UUIDs and build final list
        projects = []
        for slug, entry in partial.items():
            repo_full_name = entry["repo_full_name"]

            # Resolve project UUID and fallback repo name via project details API
            project_id = None
            details = self.getProjectDetails(slug)
            if details:
                project_id = details.get("id")
                if not repo_full_name:
                    # For classic integrations vcs_url may be the GitHub/GitLab URL
                    vcs = details.get("vcs_info", {})
                    vcs_url = vcs.get("vcs_url", "")
                    if "github.com" in vcs_url or "gitlab.com" in vcs_url:
                        parts = vcs_url.rstrip("/").split("/")
                        if len(parts) >= 2:
                            repo_full_name = "/".join(parts[-2:])

            if not repo_full_name:
                logger.verbose(f"Could not determine repo_full_name for {slug}, skipping")
                continue

            projects.append({
                "project_slug": slug,
                "project_id": project_id,
                "repo_full_name": repo_full_name,
                "repo_url": entry["repo_url"],
                "default_branch": entry["default_branch"],
                "repo_external_id": entry["repo_external_id"],
            })

        return projects

    # ------------------------------------------------------------------
    # Pipeline definitions (GitHub App / GitLab App projects)
    # ------------------------------------------------------------------

    def listPipelineDefinitions(self, projectId):
        """Return the list of pipeline definition dicts for a project UUID."""
        logger.debug(f"Listing pipeline definitions for project {projectId}")
        r = self._session.get(
            f"{CIRCLECI_API_URL}/projects/{projectId}/pipeline-definitions",
            headers=self._header,
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json().get("items", [])

    def createPipelineDefinition(self, projectId, name, filePath, repoExternalId, provider="github_app"):
        """
        Create a new pipeline definition that reads its config from a specific
        file path in the repo.  Returns the definition id (UUID).

        projectId:      project UUID
        name:           human-readable name (e.g. DEFAULT_PIPELINE_NAME)
        filePath:       path to the config file (e.g. ".circleci/init_ZkITM.yml")
        repoExternalId: numeric VCS repo ID (GitHub repo_id / GitLab project_id)
        provider:       "github_app" or "github_server" or "gitlab_app"
        """
        logger.debug(f"Creating pipeline definition '{name}' in project {projectId}")
        payload = {
            "name": name,
            "config_source": {
                "provider": provider,
                "repo": {"external_id": str(repoExternalId)},
                "file_path": filePath,
            },
            "checkout_source": {
                "provider": provider,
                "repo": {"external_id": str(repoExternalId)},
            },
        }
        r = self._session.post(
            f"{CIRCLECI_API_URL}/projects/{projectId}/pipeline-definitions",
            headers=self._header,
            json=payload,
        )
        if r.status_code in (401, 403):
            raise CircleCIError(f"Not authorised to create pipeline definition in {projectId}")
        r.raise_for_status()
        return r.json().get("id")

    def deletePipelineDefinition(self, projectId, definitionId):
        """Delete a pipeline definition by its UUID."""
        logger.debug(f"Deleting pipeline definition {definitionId} from project {projectId}")
        self._session.delete(
            f"{CIRCLECI_API_URL}/projects/{projectId}/pipeline-definitions/{definitionId}",
            headers=self._header,
        )

    def triggerPipelineRun(self, projectSlug, definitionId, branch):
        """
        Trigger a pipeline run using the recommended /pipeline/run endpoint.
        Used for GitHub App / GitLab App projects (vcsType "circleci").
        Returns the pipeline id, or None on failure.
        """
        logger.debug(f"Triggering pipeline/run for {projectSlug} def={definitionId} branch={branch}")
        # The slug format for this endpoint is {provider}/{org}/{project}
        provider, org, project = projectSlug.split("/", 2)
        payload = {
            "definition_id": definitionId,
            "config": {"branch": branch},
            "checkout": {"branch": branch},
        }
        r = self._session.post(
            f"{CIRCLECI_API_URL}/project/{provider}/{org}/{project}/pipeline/run",
            headers=self._header,
            json=payload,
        )
        if r.status_code in (401, 403):
            raise CircleCIError(f"Not authorised to trigger pipeline run for {projectSlug}")
        data = r.json()
        if data.get("message"):
            raise CircleCIError(f"triggerPipelineRun: {data['message']}")
        return data.get("id")
