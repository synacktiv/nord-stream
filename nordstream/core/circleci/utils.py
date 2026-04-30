"""Shared helpers for CircleCI secret extraction."""

import base64
import glob as globmod
import json
import logging

from nordstream.cicd.circleci import CircleCIError
from nordstream.utils.log import logger, NordStreamLog


def decodeCircleCIOutput(logFilePath):
    """
    Read a CircleCI step output log file and double-base64-decode its content.
    Returns the decoded bytes, or None if the log cannot be parsed.
    """
    try:
        with open(logFilePath, "r") as f:
            lines = f.readlines()
    except OSError as e:
        logger.error(f"Could not read log file {logFilePath}: {e}")
        return None

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
            raw_b64 = line
            break

    if not raw_b64:
        logger.error("Could not find encoded output in pipeline logs.")
        return None

    try:
        return base64.b64decode(base64.b64decode(raw_b64))
    except Exception as e:
        logger.error(f"Failed to decode pipeline output: {e}")
        return None


def extractAndSaveSecrets(outputDir, globPattern, informationType="Secrets"):
    """Decode the most recent log file and save extracted secrets to disk."""
    files = globmod.glob(f"{outputDir}/{globPattern}")
    if not files:
        logger.error("No output file found.")
        return False

    logFilePath = sorted(files)[-1]
    secrets = decodeCircleCIOutput(logFilePath)
    if secrets is None:
        return False

    logger.success(f"{informationType}:")
    logger.raw(secrets, logging.INFO)

    outFile = f"{outputDir}/{informationType.lower().replace(' ', '_')}.txt"
    with open(outFile, "ab") as f:
        f.write(secrets)
    return True


def displayProjectEnvVars(circleCicd, projectSlug):
    """List CircleCI project environment variable names via the API."""
    try:
        vars_ = circleCicd.listProjectEnvVars(projectSlug)
        if vars_:
            logger.info("Project environment variables:")
            for v in vars_:
                logger.raw(f"\t- {v}\n", logging.INFO)
        else:
            logger.info("No project environment variables found.")
    except CircleCIError as e:
        if logger.getEffectiveLevel() <= NordStreamLog.VERBOSE:
            logger.error(f"Can't list project env vars: {e}")


def displayContexts(circleCicd, vcsType, orgIdentifier):
    """List CircleCI context names and their environment variable names for an org."""
    try:
        orgId = circleCicd.getOrgId(vcsType, orgIdentifier)
        if not orgId:
            logger.verbose(f"Could not resolve org ID for {orgIdentifier}")
            return
        contexts = circleCicd.listContexts(orgId)
        if contexts:
            logger.info("Org contexts:")
            for ctx in contexts:
                logger.raw(f"\t- {ctx['name']}\n", logging.INFO)
                try:
                    envVars = circleCicd.listContextEnvVars(ctx["id"])
                    for v in envVars:
                        logger.raw(f"\t    - {v}\n", logging.INFO)
                except CircleCIError:
                    pass
        else:
            logger.info("No org contexts found.")
    except CircleCIError as e:
        if logger.getEffectiveLevel() <= NordStreamLog.VERBOSE:
            logger.error(f"Can't list contexts: {e}")
