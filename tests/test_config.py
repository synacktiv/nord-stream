from nordstream.config import CommitIdentity, RunnerConfig
from nordstream.utils.constants import OUTPUT_DIR, DEFAULT_BRANCH_NAME, GIT_USER, GIT_EMAIL


def test_commit_identity_defaults():
    identity = CommitIdentity()
    assert identity.user == GIT_USER
    assert identity.email == GIT_EMAIL
    assert identity.key_id is None


def test_runner_config_defaults():
    config = RunnerConfig()
    assert config.branch_name == DEFAULT_BRANCH_NAME
    assert config.output_dir == OUTPUT_DIR
    assert config.clean_logs is True
    assert config.write_access_filter is False
    assert config.force_deploy is False
    assert config.sleep_time == 15
    assert config.max_retry == 10
    assert config.yaml_path is None
    assert isinstance(config.commit, CommitIdentity)
    assert config.commit.user == GIT_USER


def test_runner_config_is_mutable_and_overridable():
    config = RunnerConfig(branch_name="feature/x", clean_logs=False)
    assert config.branch_name == "feature/x"
    assert config.clean_logs is False
    config.output_dir = "/tmp/out"
    assert config.output_dir == "/tmp/out"


def test_each_runner_config_gets_its_own_commit_identity():
    a = RunnerConfig()
    b = RunnerConfig()
    a.commit.user = "changed"
    assert b.commit.user == GIT_USER
