"""Mocked-HTTP tests for the GitHub fetch layer.

No real API is contacted. Construction calls the GraphQL login endpoint, so
every test registers a mocked login response first via ``_make_client``.
"""

import pytest
import responses

from nordstream.cicd.github import GitHub
from nordstream.utils.errors import GitHubBadCredentials


def _register_login(login="tester"):
    responses.add(
        responses.POST,
        "https://api.github.com/graphql",
        json={"data": {"viewer": {"login": login}}},
        status=200,
    )


def _make_client(token="ghp_test", org=None):
    _register_login()
    client = GitHub(token)
    if org is not None:
        client.org = org
    return client


@responses.activate
def test_inherits_baseclient_defaults():
    client = _make_client()
    # properties inherited from BaseClient
    assert client.token == "ghp_test"
    assert client.branchName == client.defaultBranchName
    assert client.repos == []


@responses.activate
def test_list_secrets_from_repo_parses_names_across_pages():
    client = _make_client()
    url = "https://api.github.com/repos/org/repo/actions/secrets"
    responses.add(responses.GET, url, json={"secrets": [{"name": "A"}, {"name": "B"}]}, status=200)
    responses.add(responses.GET, url, json={"secrets": []}, status=200)

    assert client.listSecretsFromRepo("org/repo") == ["A", "B"]


@responses.activate
def test_list_repos_filters_by_org():
    client = _make_client(org="myorg")
    responses.add(
        responses.GET,
        "https://api.github.com/user/repos",
        json=[
            {"full_name": "myorg/repo1", "owner": {"login": "myorg"}},
            {"full_name": "other/repo2", "owner": {"login": "other"}},
        ],
        status=200,
    )
    responses.add(responses.GET, "https://api.github.com/user/repos", json=[], status=200)

    client.listRepos()
    assert client.repos == ["myorg/repo1"]


@responses.activate
def test_add_repo_raises_on_bad_credentials():
    client = _make_client(org="myorg")
    responses.add(
        responses.GET,
        "https://api.github.com/repos/myorg/repo",
        json={"message": "Bad credentials"},
        status=401,
    )
    with pytest.raises(GitHubBadCredentials):
        client.addRepo("repo")


@responses.activate
def test_repos_is_per_instance_not_shared():
    a = _make_client()
    b = _make_client()
    a.repos.append("x")
    assert b.repos == []
