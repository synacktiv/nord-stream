"""Display layer for Azure DevOps — formats already-fetched data via ``logger``.

Pure presentation: these functions take plain data (dicts/lists returned by the
DevOps client) and print it. No network, no fetching, no business logic.
"""

import logging

from nordstream.utils.log import logger


def displayProject(name):
    logger.raw(f"- {name}\n", level=logging.INFO)


def displayRepository(projectName, name):
    logger.raw(f"- {projectName}/{name}\n", level=logging.INFO)


def displayUser(user):
    origin = user.get("origin")
    displayName = user.get("displayName")
    mailAddress = user.get("mailAddress")
    res = f"- {displayName}"

    if mailAddress != "":
        res += f" / {mailAddress}"

    res += f" ({origin})\n"
    logger.raw(res, level=logging.INFO)


def displayVariableGroup(variableGroup):
    logger.info(f"Variable group: \"{variableGroup.get('name')}\"")
    for sec in variableGroup.get("variables"):
        logger.raw(f"\t- {sec}\n", logging.INFO)


def displaySecureFile(secureFile):
    logger.info(f'Secure file: "{secureFile["name"]}"')


def displayServiceConnection(sc):
    scType = sc.get("type")
    scName = sc.get("name")
    logger.raw(f"\t- {scName} ({scType})\n", logging.INFO)


def displayFailureReasons(reasons):
    logger.error("Workflow failure:")
    for reason in reasons:
        logger.error(f"{reason}")
