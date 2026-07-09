"""Mocked-HTTP tests for the GitLab fetch layer.

Construction calls ``/api/v4/user`` (login); every test registers it first.
"""

import pytest
import responses

from nordstream.cicd.gitlab import GitLab
from nordstream.utils.errors import GitLabError

BASE = "https://gitlab.example"


def _register_login(username="tester"):
    responses.add(responses.GET, f"{BASE}/api/v4/user", json={"username": username}, status=200)


def _make_client(tmp_path, token="glpat-test"):
    _register_login()
    client = GitLab(BASE, token, verifCert=False)
    client.outputDir = str(tmp_path)
    return client


@responses.activate
def test_inherits_baseclient_defaults(tmp_path):
    client = _make_client(tmp_path)
    assert client.token == "glpat-test"
    assert client.url == BASE
    assert client.branchName == client.defaultBranchName
    assert client.projects == []
    assert client.groups == []


@responses.activate
def test_private_token_header_set_on_session(tmp_path):
    client = _make_client(tmp_path)
    assert client.session.headers["PRIVATE-TOKEN"] == "glpat-test"


@responses.activate
def test_list_variables_from_project_parses_and_defaults_hidden(tmp_path):
    client = _make_client(tmp_path)
    url = f"{BASE}/api/v4/projects/42/variables"
    responses.add(
        responses.GET,
        url,
        json=[{"key": "K1", "value": "V1", "protected": True}],  # no "hidden" key
        status=200,
    )
    responses.add(responses.GET, url, json=[], status=200)

    result = client.listVariablesFromProject({"id": 42, "path_with_namespace": "grp/proj"})
    assert result == [{"key": "K1", "value": "V1", "protected": True, "hidden": "N/A"}]


@responses.activate
def test_list_variables_from_group_uses_group_endpoint(tmp_path):
    client = _make_client(tmp_path)
    url = f"{BASE}/api/v4/groups/7/variables"
    responses.add(
        responses.GET, url, json=[{"key": "GK", "value": "GV", "protected": False, "hidden": True}], status=200
    )
    responses.add(responses.GET, url, json=[], status=200)

    result = client.listVariablesFromGroup({"id": 7, "full_path": "grp"})
    assert result == [{"key": "GK", "value": "GV", "protected": False, "hidden": True}]


@responses.activate
def test_list_variables_from_instance_raises_on_403(tmp_path):
    client = _make_client(tmp_path)
    responses.add(
        responses.GET,
        f"{BASE}/api/v4/admin/ci/variables",
        json={"message": "403 Forbidden"},
        status=403,
    )
    with pytest.raises(GitLabError):
        client.listVariablesFromInstance()


@responses.activate
def test_projects_is_per_instance_not_shared(tmp_path):
    a = _make_client(tmp_path)
    b = _make_client(tmp_path)
    a.projects.append({"id": 1})
    assert b.projects == []
