"""
Shared helpers for CircleCI secret extraction runners.

Both CircleCIRunner (git-based injection) and CircleCIStandaloneRunner
(API-only injection) use these functions to avoid code duplication.
"""

import base64
import glob as globmod
import json
import logging

from nordstream.cicd.circleci import CircleCIError
from nordstream.utils.log import logger, NordStreamLog


def decodeCircleCIOutput(logFilePath):
    """
    Read a CircleCI step output log file and double-base64-decode its content.

    CircleCI wraps each step output line as a JSON array of message objects:
        [{"message": "<base64>", "type": "out", ...}]

    The exfiltration command encodes the secret values with two rounds of base64
    to survive log sanitisation, so the message field itself must be decoded twice.

    Returns the decoded bytes on success, or None if the log cannot be parsed.
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
            # Fallback: plain-text output (some runner configurations)
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
    """
    Find the most recent log file matching globPattern under outputDir,
    decode its CircleCI step output, log the secrets, and append them to
    a <informationType>.txt file in outputDir.

    Returns True if secrets were successfully extracted, False otherwise.
    """
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
    """
    List and display CircleCI project environment variable names (values are not
    accessible via the API).  Errors are silently suppressed unless verbose mode
    is active.
    """
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
    """
    Resolve the org UUID for the given vcsType + orgIdentifier, then list all
    context names and their environment variable names.

    orgIdentifier: org slug or UUID (passed to getOrgId).
    """
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
