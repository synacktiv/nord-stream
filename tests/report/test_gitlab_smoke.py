"""No-crash smoke tests for the GitLab display layer.

Display formatting is out of unit-test scope (we don't assert on the exact
strings), but these guard against typos/KeyErrors introduced when the display
code was moved out of the runner. Each function is called with representative
data and must simply not raise.
"""

from nordstream.report import gitlab as report


def test_display_runner():
    report.displayRunner(
        {
            "id": "1/sys",
            "runner_type": "project_type",
            "executor": "docker",
            "access_level": "not_protected",
            "status": "ONLINE",
            "contacted_at": "2026-01-01T00:00:00.000Z",
            "description": None,
            "tags": ["t1"],
            "platform": "linux",
            "architecture": "amd64",
            "ip_address": "1.2.3.4",
            "projects": ["grp/proj"],
        }
    )


def test_display_variable_and_secure_file():
    report.displayVariable({"key": "K", "value": "V", "protected": True, "hidden": "N/A"})
    report.displaySecureFile({"name": "cert.pem", "path": "/tmp/cert.pem"})


def test_display_project_user_group():
    report.displayProject({"path": "p", "name": "p", "id": 1, "path_with_namespace": "grp/p"})
    report.displayProject({"path": "p", "name": "Proj", "id": 1, "path_with_namespace": "grp/p"})
    report.displayUser({"id": 1, "username": "u", "email": "u@x", "is_admin": True})
    report.displayUser({"id": 2, "username": "u2", "email": None, "is_admin": None})
    report.displayGroup({"full_path": "grp/sub"})


def test_display_token_info():
    report.displayTokenInfo({"username": "u", "is_admin": None, "email": "u@x", "id": 5, "note": None})


def test_display_branch_protections():
    report.displayBranchesProtectionRulesPriv(
        [
            {
                "name": "main",
                "allow_force_push": False,
                "code_owner_approval_required": True,
                "push_access_levels": [{"access_level": 40, "access_level_description": "Maintainers"}],
                "unprotect_access_levels": [],
                "merge_access_levels": [{"user_id": 7, "access_level_description": "u"}],
            }
        ]
    )
    report.displayBranchesProtectionRulesPriv([])  # "No protection" path
    report.displayBranchesProtectionRulesUnpriv(
        [{"protected": True, "name": "main", "developers_can_push": False, "developers_can_merge": True}]
    )
