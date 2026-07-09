"""Mocked-HTTP tests for the Azure DevOps fetch layer.

Construction calls the ConnectionData endpoint (login); every test registers it
first. Note DevOps builds URLs as ``{baseURL}/_apis/...`` where baseURL already
ends in ``/``, producing a ``//`` — the mocks match that exact shape.
"""

import responses

from nordstream.cicd.devops import DevOps
from nordstream.utils.constants import DEFAULT_REPO_NAME

ORG = "myorg"
LOGIN_URL = f"https://dev.azure.com/{ORG}//_apis/ConnectionData"
PROJECTS_URL = f"https://dev.azure.com/{ORG}//_apis/projects"

# a token that satisfies isAZDOBearerToken: starts with eyJ0, len > 52, two dots
BEARER = "eyJ0" + "A" * 30 + ".payloadpayloadpayload." + "signature"
BASIC = "pat_token_value"


def _register_login(user_id="user-123"):
    responses.add(
        responses.GET,
        LOGIN_URL,
        json={"authenticatedUser": {"id": user_id}},
        status=200,
    )


def _make_client(token=BASIC, org=ORG):
    _register_login()
    return DevOps(token, org, verifCert=False)


@responses.activate
def test_inherits_baseclient_defaults():
    client = _make_client()
    assert client.token == BASIC
    assert client.org == ORG
    assert client.branchName == client.defaultBranchName
    assert client.projects == []
    assert client.repoName == DEFAULT_REPO_NAME


@responses.activate
def test_basic_token_sets_session_auth():
    client = _make_client(token=BASIC)
    assert client.session.auth == ("", BASIC)


@responses.activate
def test_bearer_token_sets_authorization_header():
    client = _make_client(token=BEARER)
    assert client.session.headers["Authorization"] == f"Bearer {BEARER}"


@responses.activate
def test_list_projects_parses_across_pages():
    client = _make_client()
    responses.add(responses.GET, PROJECTS_URL, json={"value": [{"id": "1", "name": "P1"}], "count": 1}, status=200)
    responses.add(responses.GET, PROJECTS_URL, json={"value": []}, status=200)

    client.listProjects()
    assert client.projects == [{"id": "1", "name": "P1"}]


@responses.activate
def test_projects_is_per_instance_not_shared():
    a = _make_client()
    b = _make_client()
    a._projects.append({"id": "x", "name": "X"})
    assert b.projects == []
