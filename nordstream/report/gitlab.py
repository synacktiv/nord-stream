"""Display layer for GitLab — formats already-fetched data via ``logger``.

Pure presentation: these functions take plain data (dicts/lists returned by the
GitLab client) and print it. No network, no fetching, no business logic.
"""

import logging

from nordstream.utils.log import logger


def displayRunner(runner):
    logger.info(
        f'{runner["id"]} (scope: {runner["runner_type"].replace("_type", "")}, '
        f'executor: {runner["executor"]}, accesslevel: {runner["access_level"]})'
    )
    logger.raw(f'    - status: {runner["status"].lower()} (lastseen: {runner["contacted_at"]})\n', logging.INFO)
    logger.raw(f'    - description: {runner["description"] or "n/a"}\n', logging.INFO)
    logger.raw(f'    - tags: {runner["tags"]}\n', logging.INFO)
    logger.raw(f'    - platform: {runner["platform"]} ({runner["architecture"]})\n', logging.INFO)
    logger.raw(f'    - ipaddress: {runner["ip_address"]}\n', logging.INFO)
    if runner["projects"]:
        logger.raw(f"    - projects:\n", logging.INFO)
        for project in runner["projects"]:
            logger.raw(f"      - {project}\n", logging.INFO)


def displayVariable(variable):
    logger.raw(
        f'\t- {variable["key"]}={variable["value"]} '
        f'(protected:{variable["protected"]} / hidden:{variable["hidden"]})\n',
        logging.INFO,
    )


def displaySecureFile(secureFile):
    logger.raw(f'\t- {secureFile["name"]} ({secureFile["path"]})\n', logging.INFO)


def displayProject(project):
    repoPath = project.get("path")
    repoName = project.get("name")
    repoId = project.get("id")

    if repoPath != repoName:
        logger.raw(f'- {project["path_with_namespace"]} / {repoId} ({repoName})\n', level=logging.INFO)
    else:
        logger.raw(f'- {project["path_with_namespace"]} / {repoId}\n', level=logging.INFO)


def displayUser(user):
    id = user.get("id")
    username = user.get("username")
    email = user.get("email")
    is_admin = user.get("is_admin")

    res = f"- {id} {username}"
    if email != None:
        res += f" {email}"

    if is_admin != None:
        res += f"(is_admin: {is_admin})"

    logger.raw(f"{res}\n", level=logging.INFO)


def displayGroup(group):
    logger.raw(f'- {group["full_path"]}\n', level=logging.INFO)


def displayTokenInfo(response):
    username = response.get("username")
    if username != "":
        logger.raw(f"\t- Username: {username}\n", logging.INFO)

    isAdmin = response.get("is_admin")
    if isAdmin == None:
        logger.raw(f"\t- IsAdmin: False\n", logging.INFO)
    else:
        logger.raw(f"\t- IsAdmin: {isAdmin}\n", logging.INFO)

    email = response.get("email")
    if email != "":
        logger.raw(f"\t- Email: {email}\n", logging.INFO)

    id = response.get("id")
    if id != "":
        logger.raw(f"\t- Id: {id}\n", logging.INFO)

    note = response.get("note")
    if note != "" and note != None:
        logger.raw(f"\t- Note: {note}\n", logging.INFO)


def displayAccessLevel(access_levels):
    for al in access_levels:
        access_level = al.get("access_level", None)
        user_id = al.get("user_id", None)
        group_id = al.get("group_id", None)
        access_level_description = al.get("access_level_description")

        res = f"\t\t{access_level_description}"

        if access_level != None:
            res += f" (access_level={access_level})"
        if user_id != None:
            res += f" (user_id={user_id})"
        if group_id != None:
            res += f" (group_id={group_id})"

        logger.raw(f"{res}\n", logging.INFO)


def displayBranchesProtectionRulesPriv(protections):
    if len(protections) == 0:
        logger.success(f"No protection")

    for protection in protections:

        name = protection.get("name")
        logger.info(f'branch: "{name}"')

        allow_force_push = protection.get("allow_force_push")
        logger.raw(f"\t- Allow force push: {allow_force_push}\n", logging.INFO)

        code_owner_approval_required = protection.get("code_owner_approval_required", None)
        if code_owner_approval_required != None:
            logger.raw(f"\t- Code Owner approval required: {code_owner_approval_required}\n", logging.INFO)

        push_access_levels = protection.get("push_access_levels", [])
        logger.raw(f"\t- Push access level:\n", logging.INFO)
        displayAccessLevel(push_access_levels)

        unprotect_access_levels = protection.get("unprotect_access_levels", [])
        logger.raw(f"\t- Unprotect access level:\n", logging.INFO)
        displayAccessLevel(unprotect_access_levels)

        merge_access_levels = protection.get("merge_access_levels", [])
        logger.raw(f"\t- Merge access level:\n", logging.INFO)
        displayAccessLevel(merge_access_levels)


def displayBranchesProtectionRulesUnpriv(branches):
    for branch in branches:

        isProtected = branch.get("protected")
        if isProtected:

            name = branch.get("name")
            logger.info(f'branch: "{name}"')

            logger.raw(f"\t- Protected: True\n", logging.INFO)

            developers_can_push = branch.get("developers_can_push")
            logger.raw(f"\t- Developers can push: {developers_can_push}\n", logging.INFO)

            developers_can_merge = branch.get("developers_can_merge")
            logger.raw(f"\t- Developers can merge: {developers_can_merge}\n", logging.INFO)
