from collections import defaultdict


def resetRequiredStatusCheck(protections):

    res = defaultdict(dict)
    required_status_checks = protections.get("required_status_checks")
    if required_status_checks:

        res["strict"] = required_status_checks.get("strict")
        res["contexts"] = required_status_checks.get("contexts")

        if required_status_checks.get("checks"):
            res["checks"] = required_status_checks.get("checks")

        return dict(res)

    else:
        return None


def resetRequiredPullRequestReviews(protections):

    res = defaultdict(dict)
    required_pull_request_reviews = protections.get("required_pull_request_reviews")

    if required_pull_request_reviews:

        if required_pull_request_reviews.get("dismissal_restrictions"):
            res["dismissal_restrictions"]["users"] = getUsersArray(
                required_pull_request_reviews.get("dismissal_restrictions").get("users")
            )
            res["dismissal_restrictions"]["teams"] = getTeamsOrAppsArray(
                required_pull_request_reviews.get("dismissal_restrictions").get("teams")
            )
            res["dismissal_restrictions"]["apps"] = getTeamsOrAppsArray(
                required_pull_request_reviews.get("dismissal_restrictions").get("apps")
            )

        if required_pull_request_reviews.get("dismiss_stale_reviews"):
            res["dismiss_stale_reviews"] = required_pull_request_reviews.get("dismiss_stale_reviews")

        if required_pull_request_reviews.get("require_code_owner_reviews"):
            res["require_code_owner_reviews"] = required_pull_request_reviews.get("require_code_owner_reviews")

        if required_pull_request_reviews.get("required_approving_review_count"):
            res["required_approving_review_count"] = required_pull_request_reviews.get(
                "required_approving_review_count"
            )

        if required_pull_request_reviews.get("require_last_push_approval"):
            res["require_last_push_approval"] = required_pull_request_reviews.get("require_last_push_approval")

        if required_pull_request_reviews.get("bypass_pull_request_allowances"):
            res["bypass_pull_request_allowances"]["users"] = getUsersArray(
                required_pull_request_reviews.get("bypass_pull_request_allowances").get("users")
            )
            res["bypass_pull_request_allowances"]["teams"] = getTeamsOrAppsArray(
                required_pull_request_reviews.get("bypass_pull_request_allowances").get("teams")
            )
            res["bypass_pull_request_allowances"]["apps"] = getTeamsOrAppsArray(
                required_pull_request_reviews.get("bypass_pull_request_allowances").get("apps")
            )

        return dict(res)

    else:
        return None


def resetRestrictions(protections):

    res = defaultdict(dict)
    restrictions = protections.get("restrictions")

    if restrictions:
        res["users"] = getUsersArray(restrictions.get("users"))
        res["teams"] = getTeamsOrAppsArray(restrictions.get("teams"))
        res["apps"] = getTeamsOrAppsArray(restrictions.get("apps"))

        return dict(res)

    else:
        return None


def getUsersArray(users):
    res = []
    for user in users:
        res.append(user.get("login"))
    return res


def getTeamsOrAppsArray(data):
    res = []
    for e in data:
        res.append(e.get("slug"))
    return res
