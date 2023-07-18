from nordstream.utils.log import logger
import logging
from nordstream.core.github.protections import getUsersArray, getTeamsOrAppsArray


def displayRepoSecrets(secrets):
    if len(secrets) != 0:
        logger.info("Repo secrets:")
        for secret in secrets:
            logger.raw(f"\t- {secret}\n", logging.INFO)


def displayEnvSecrets(env, secrets):
    if len(secrets) != 0:
        logger.info(f"{env} secrets:")
        for secret in secrets:
            logger.raw(f"\t- {secret}\n", logging.INFO)


def displayOrgSecrets(secrets):
    if len(secrets) != 0:
        logger.info("Repository organization secrets:")
        for secret in secrets:
            logger.raw(f"\t- {secret}\n", logging.INFO)


def displayEnvSecurity(envDetails):
    protectionRules = envDetails.get("protection_rules")
    envName = envDetails.get("name")

    if len(protectionRules) > 0:
        logger.info(f'Environment protection for: "{envName}":')
        for protection in protectionRules:
            if protection.get("type") == "required_reviewers":
                for reviewer in protection.get("reviewers"):
                    reviewerType = reviewer.get("type")
                    login = reviewer.get("reviewer").get("login")
                    userId = reviewer.get("reviewer").get("id")
                    logger.raw(
                        f"\t- reviewer ({reviewerType}): {login}/{userId}\n",
                        logging.INFO,
                    )
            elif protection.get("type") == "wait_timer":
                wait = protection.get("wait_timer")
                logger.raw(f"\t- timer: {wait} min\n", logging.INFO)
            else:
                branchPolicy = envDetails.get("deployment_branch_policy")
                if branchPolicy.get("custom_branch_policies", False):
                    logger.raw(f"\t- deployment branch policy: custom\n", logging.INFO)
                else:
                    logger.raw(f"\t- deployment branch policy: protected\n", logging.INFO)
    else:
        logger.info(f'No environment protection rule found for: "{envName}"')


def displayBranchProtectionRules(protections):
    logger.info("Branch protections:")

    logger.raw(
        f'\t- enforce admins: {protections.get("enforce_admins").get("enabled")}\n',
        logging.INFO,
    )
    logger.raw(
        "\t- block creations:" f' {protections.get("block_creations").get("enabled")}\n',
        logging.INFO,
    )
    logger.raw(
        "\t- required signatures:" f' {protections.get("required_signatures").get("enabled")}\n',
        logging.INFO,
    )
    logger.raw(
        "\t- allow force pushes:" f' {protections.get("allow_force_pushes").get("enabled")}\n',
        logging.INFO,
    )
    logger.raw(
        "\t- allow deletions:" f' {protections.get("allow_deletions").get("enabled")}\n',
        logging.INFO,
    )

    if protections.get("restrictions"):
        displayRestrictions(protections.get("restrictions"))

    if protections.get("required_pull_request_reviews"):
        displayRequiredPullRequestReviews(protections.get("required_pull_request_reviews"))
    else:
        logger.raw(f"\t- required pull request reviews: False\n", logging.INFO)

    if protections.get("required_status_checks"):
        displayRequiredStatusChecks(protections.get("required_status_checks"))

    logger.raw(
        "\t- required linear history:" f' {protections.get("required_linear_history").get("enabled")}\n',
        logging.INFO,
    )
    logger.raw(
        "\t- required conversation resolution:"
        f' {protections.get("required_conversation_resolution").get("enabled")}\n',
        logging.INFO,
    )
    logger.raw(
        f'\t- lock branch: {protections.get("lock_branch").get("enabled")}\n',
        logging.INFO,
    )
    logger.raw(
        "\t- allow fork syncing:" f' {protections.get("allow_fork_syncing").get("enabled")}\n',
        logging.INFO,
    )


def displayRequiredStatusChecks(data):

    logger.raw(f"\t- required status checks:\n", logging.INFO)
    logger.raw(f'\t    - strict: {data.get("strict")}\n', logging.INFO)

    if len(data.get("contexts")) != 0:
        logger.raw(f'\t    - contexts: {data.get("contexts")}\n', logging.INFO)

    if len(data.get("checks")) != 0:
        logger.raw(f'\t    - checks: {data.get("checks")}\n', logging.INFO)


def displayRequiredPullRequestReviews(data):

    logger.raw(f"\t- pull request reviews:\n", logging.INFO)
    logger.raw(f'\t    - approving review count: {data.get("required_approving_review_count")}\n', logging.INFO)
    logger.raw(f'\t    - require code owner reviews: {data.get("require_code_owner_reviews")}\n', logging.INFO)
    logger.raw(f'\t    - require last push approval: {data.get("require_last_push_approval")}\n', logging.INFO)
    logger.raw(f'\t    - dismiss stale reviews: {data.get("dismiss_stale_reviews")}\n', logging.INFO)

    if data.get("dismissal_restrictions"):
        users = getUsersArray(data.get("dismissal_restrictions").get("users"))
        teams = getTeamsOrAppsArray(data.get("dismissal_restrictions").get("teams"))
        apps = getTeamsOrAppsArray(data.get("dismissal_restrictions").get("apps"))

        if len(users) != 0 or len(teams) != 0 or len(apps) != 0:
            logger.raw(f"\t    - dismissal_restrictions:\n", logging.INFO)

            if len(users) != 0:
                logger.raw(f"\t        - users: {users}\n", logging.INFO)
            if len(teams) != 0:
                logger.raw(f"\t        - teams: {teams}\n", logging.INFO)
            if len(apps) != 0:
                logger.raw(f"\t        - apps: {apps}\n", logging.INFO)

    if data.get("bypass_pull_request_allowances"):
        users = getUsersArray(data.get("bypass_pull_request_allowances").get("users"))
        teams = getTeamsOrAppsArray(data.get("bypass_pull_request_allowances").get("teams"))
        apps = getTeamsOrAppsArray(data.get("bypass_pull_request_allowances").get("apps"))

        if len(users) != 0 or len(teams) != 0 or len(apps) != 0:
            logger.raw(f"\t    - bypass pull request allowances:\n", logging.INFO)

            if len(users) != 0:
                logger.raw(f"\t        - users: {users}\n", logging.INFO)
            if len(teams) != 0:
                logger.raw(f"\t        - teams: {teams}\n", logging.INFO)
            if len(apps) != 0:
                logger.raw(f"\t        - apps: {apps}\n", logging.INFO)


def displayRestrictions(data):
    users = getUsersArray(data.get("users"))
    teams = getTeamsOrAppsArray(data.get("teams"))
    apps = getTeamsOrAppsArray(data.get("apps"))

    if len(users) != 0 or len(teams) != 0 or len(apps) != 0:
        logger.raw(f"\t- person allowed to push to restricted branches (restrictions):\n", logging.INFO)

        if len(users) != 0:
            logger.raw(f"\t    - users: {users}\n", logging.INFO)
        if len(teams) != 0:
            logger.raw(f"\t    - teams: {teams}\n", logging.INFO)
        if len(apps) != 0:
            logger.raw(f"\t    - apps: {apps}\n", logging.INFO)
