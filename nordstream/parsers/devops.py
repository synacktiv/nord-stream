"""Pure functions that decode Azure DevOps pipeline output.

No I/O, no logging, no network — this is the "manipulate" layer. Callers read
the output file and pass its raw bytes here.
"""

import base64
import binascii


def decode_double_b64(content):
    """Decode the doubly-base64-encoded payload from pipeline output bytes.

    The extraction pipeline pipes data through ``base64 | base64``; the payload
    sits on the 3rd-from-last line as the 2nd whitespace-separated token. This
    matches the original ``output.readlines()[-3].split(b" ")[1]`` behaviour, so
    line splitting keeps trailing newlines.

    Raises:
        IndexError: if the output has fewer than three lines.
    """
    lines = content.splitlines(keepends=True)
    data = lines[-3].split(b" ")[1]
    return base64.b64decode(base64.b64decode(data))


def extract_github_authorization(content):
    """Return the decoded token from the ``AUTHORIZATION`` line, or ``None``.

    The GitHub service-connection payload is itself doubly-base64-encoded; once
    decoded, the ``AUTHORIZATION`` line carries a base64 token as its last
    whitespace token. Returns that token decoded, with a trailing newline.
    """
    decoded = decode_double_b64(content)
    for line in decoded.split(b"\n"):
        if b"AUTHORIZATION" in line:
            try:
                return base64.b64decode(line.split(b" ")[-1]) + b"\n"
            except (binascii.Error, ValueError):
                continue
    return None
