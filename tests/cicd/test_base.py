import responses

from nordstream.cicd.base import BaseClient
from nordstream.utils.constants import OUTPUT_DIR, DEFAULT_BRANCH_NAME, USER_AGENT


def test_init_sets_defaults():
    client = BaseClient("tok123")
    assert client.token == "tok123"
    assert client.outputDir == OUTPUT_DIR
    assert client.branchName == DEFAULT_BRANCH_NAME
    assert client.defaultBranchName == DEFAULT_BRANCH_NAME


def test_output_dir_and_branch_are_writable():
    client = BaseClient("tok")
    client.outputDir = "/tmp/logs"
    client.branchName = "feature/y"
    assert client.outputDir == "/tmp/logs"
    assert client.branchName == "feature/y"


def test_default_branch_name_is_the_constant():
    client = BaseClient("tok")
    assert client.defaultBranchName == DEFAULT_BRANCH_NAME


def test_session_sends_user_agent_header():
    client = BaseClient("tok")
    assert client.session.headers["User-Agent"] == USER_AGENT


@responses.activate
def test_get_issues_request_and_returns_response():
    responses.add(responses.GET, "https://example.test/data", json={"ok": True}, status=200)
    client = BaseClient("tok")
    resp = client._get("https://example.test/data")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@responses.activate
def test_post_issues_request_and_returns_response():
    responses.add(responses.POST, "https://example.test/submit", json={"id": 1}, status=201)
    client = BaseClient("tok")
    resp = client._post("https://example.test/submit", json={"x": 1})
    assert resp.status_code == 201
    assert resp.json() == {"id": 1}
