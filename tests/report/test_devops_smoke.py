"""No-crash smoke tests for the Azure DevOps display layer.

Display formatting is out of unit-test scope; these guard against typos/KeyErrors
introduced when the display code was moved out of the runner.
"""

from nordstream.report import devops as report


def test_display_project_and_repository():
    report.displayProject("MyProject")
    report.displayRepository("MyProject", "repo1")


def test_display_user():
    report.displayUser({"origin": "aad", "displayName": "Jane", "mailAddress": "jane@x"})
    report.displayUser({"origin": "vsts", "displayName": "NoMail", "mailAddress": ""})


def test_display_variable_group():
    report.displayVariableGroup({"name": "prod-secrets", "variables": ["API_KEY", "DB_PASS"]})


def test_display_secure_file_and_service_connection():
    report.displaySecureFile({"name": "cert.pfx"})
    report.displayServiceConnection({"name": "azure-sc", "type": "azurerm"})


def test_display_failure_reasons():
    report.displayFailureReasons(["boom", "kaboom"])
    report.displayFailureReasons([])
