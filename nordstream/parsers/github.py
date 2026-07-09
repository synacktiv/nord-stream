"""Pure functions that turn raw GitHub workflow output into usable data.

No I/O, no logging, no network — this is the "manipulate" layer.
"""

import base64
import binascii


def decode_workflow_secret_line(last_line):
    """Decode the last line of a workflow output file into raw secret bytes.

    The extraction workflow pipes the environment through ``base64 -w0 |
    base64 -w0``; the resulting output line looks like ``"<label> <b64b64>"``.
    This returns the doubly-base64-decoded bytes of the second whitespace token.

    Raises:
        ValueError: if the line has no second token or it is not valid base64.
    """
    tokens = last_line.split(" ")
    if len(tokens) < 2:
        raise ValueError("workflow output line has no encoded token")

    try:
        return base64.b64decode(base64.b64decode(tokens[1]))
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"malformed base64 in workflow output line: {exc}")
