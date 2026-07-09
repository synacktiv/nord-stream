import base64

import pytest

from nordstream.parsers.devops import decode_double_b64, extract_github_authorization


def _double_b64(raw: bytes) -> bytes:
    return base64.b64encode(base64.b64encode(raw))


def _output_with_target_line(target_token: bytes) -> bytes:
    """Build file content whose 3rd-from-last line is ``command <target_token>``.

    Mirrors the real output shape: ``output.readlines()[-3].split(b" ")[1]``.
    """
    return b"header\n" + b"command " + target_token + b"\n" + b"tail1\n" + b"tail2"


def test_decode_double_b64_round_trips_third_from_last_line():
    payload = b"SECRET=value123"
    content = _output_with_target_line(_double_b64(payload))
    assert decode_double_b64(content) == payload


def test_decode_double_b64_raises_when_too_few_lines():
    with pytest.raises(IndexError):
        decode_double_b64(b"only-one-line")


def test_extract_github_authorization_returns_decoded_token_with_newline():
    secret = b"ghs_token_abc"
    inner = b"noise\nAUTHORIZATION " + base64.b64encode(secret) + b"\nmore-noise"
    content = _output_with_target_line(_double_b64(inner))
    assert extract_github_authorization(content) == secret + b"\n"


def test_extract_github_authorization_returns_none_when_absent():
    inner = b"line1\nline2\nline3"
    content = _output_with_target_line(_double_b64(inner))
    assert extract_github_authorization(content) is None
