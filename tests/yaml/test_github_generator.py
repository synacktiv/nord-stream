"""Characterization tests for the GitHub workflow YAML generator.

These lock the exact generated pipeline structure before the refactor, so any
later change that alters the payload is caught. Assertions are on the produced
``defaultTemplate`` dict (not the serialized YAML string) to avoid formatting
brittleness.

The generator mutates class-level template dicts (shared state). The autouse
fixture restores pristine templates around each test so results are independent
of test order.
"""

import copy

import pytest

from nordstream.yaml.github import WorkflowGenerator

_PRISTINE_DEFAULT = copy.deepcopy(WorkflowGenerator._defaultTemplate)
_PRISTINE_AZURE = copy.deepcopy(WorkflowGenerator._OIDCAzureTokenTemplate)
_PRISTINE_AWS = copy.deepcopy(WorkflowGenerator._OIDCAWSTokenTemplate)


@pytest.fixture(autouse=True)
def _reset_templates():
    WorkflowGenerator._defaultTemplate = copy.deepcopy(_PRISTINE_DEFAULT)
    WorkflowGenerator._OIDCAzureTokenTemplate = copy.deepcopy(_PRISTINE_AZURE)
    WorkflowGenerator._OIDCAWSTokenTemplate = copy.deepcopy(_PRISTINE_AWS)
    yield


def test_repo_secrets():
    g = WorkflowGenerator()
    g.generateWorkflowForSecretsExtraction(["AWS_KEY", "DB_PASS"])
    assert g.defaultTemplate == {
        "name": "GitHub Actions",
        "on": "push",
        "jobs": {
            "init": {
                "runs-on": "ubuntu-latest",
                "steps": [
                    {
                        "run": "env -0 | awk -v RS='\\0' '/^secret_/ {print $0}' | base64 -w0 | base64 -w0",
                        "name": "command",
                        "env": {
                            "secret_AWS_KEY": "${{secrets.AWS_KEY}}",
                            "secret_DB_PASS": "${{secrets.DB_PASS}}",
                        },
                    }
                ],
            }
        },
    }


def test_secrets_with_env():
    g = WorkflowGenerator()
    g.generateWorkflowForSecretsExtraction(["AWS_KEY"], "prod")
    init = g.defaultTemplate["jobs"]["init"]
    assert init["environment"] == "prod"
    assert init["steps"][0]["env"] == {"secret_AWS_KEY": "${{secrets.AWS_KEY}}"}


def test_azure_oidc():
    g = WorkflowGenerator()
    g.generateWorkflowForOIDCAzureTokenGeneration("tid", "sid", "cid")
    with_block = g.defaultTemplate["jobs"]["init"]["steps"][0]["with"]
    assert g.defaultTemplate["permissions"] == {"id-token": "write", "contents": "read"}
    assert with_block["tenant-id"] == "tid"
    assert with_block["client-id"] == "cid"
    assert with_block["subscription-id"] == "sid"
    assert with_block["allow-no-subscriptions"] is True


def test_azure_oidc_without_subscription_omits_key():
    g = WorkflowGenerator()
    g.generateWorkflowForOIDCAzureTokenGeneration("tid", None, "cid")
    with_block = g.defaultTemplate["jobs"]["init"]["steps"][0]["with"]
    assert "subscription-id" not in with_block


def test_aws_oidc():
    g = WorkflowGenerator()
    g.generateWorkflowForOIDCAWSTokenGeneration("role-arn", "us-east-1")
    with_block = g.defaultTemplate["jobs"]["init"]["steps"][0]["with"]
    assert with_block["role-to-assume"] == "role-arn"
    assert with_block["aws-region"] == "us-east-1"
    assert with_block["role-session-name"] == "oidcrolesession"
