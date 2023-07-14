class DevOpsError(Exception):
    pass


class GitHubError(Exception):
    pass


class GitLabError(Exception):
    pass


class GitError(Exception):
    pass


class GitPushError(GitError):
    pass


class RepoCreationError(Exception):
    pass
