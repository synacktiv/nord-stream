import base64

import pytest

from nordstream.parsers.github import decode_workflow_secret_line


def _double_b64(raw: bytes) -> str:
    return base64.b64encode(base64.b64encode(raw)).decode()


def test_decodes_double_base64_second_token():
    payload = b"secret_DB_PASS=hunter2\n"
    line = f"command {_double_b64(payload)}"
    assert decode_workflow_secret_line(line) == payload


def test_ignores_label_uses_second_whitespace_token():
    payload = b"secret_X=1"
    line = f"anything {_double_b64(payload)}"
    assert decode_workflow_secret_line(line) == payload


def test_missing_second_token_raises_value_error():
    with pytest.raises(ValueError):
        decode_workflow_secret_line("no-space-here")


def test_non_base64_second_token_raises_value_error():
    with pytest.raises(ValueError):
        decode_workflow_secret_line("command !!!not-base64!!!")
