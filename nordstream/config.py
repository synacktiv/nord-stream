from dataclasses import dataclass, field

from nordstream.utils.constants import (
    OUTPUT_DIR,
    DEFAULT_BRANCH_NAME,
    GIT_USER,
    GIT_EMAIL,
)


@dataclass
class CommitIdentity:
    """Identity used when the tool creates git commits."""

    user: str = GIT_USER
    email: str = GIT_EMAIL
    key_id: str = None


@dataclass
class RunnerConfig:
    """Configuration shared by every platform runner.

    Platform-specific toggles are added by composing additional dataclasses
    in each platform's module; this holds only the common fields.
    """

    branch_name: str = DEFAULT_BRANCH_NAME
    output_dir: str = OUTPUT_DIR
    clean_logs: bool = True
    write_access_filter: bool = False
    force_deploy: bool = False
    sleep_time: int = 15
    max_retry: int = 10
    yaml_path: str = None
    commit: CommitIdentity = field(default_factory=CommitIdentity)
