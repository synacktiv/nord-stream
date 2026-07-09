"""Pure functions for manipulating GitLab API data.

No I/O, no logging, no network — this is the "manipulate" layer.
"""

from datetime import datetime


def _parse_contacted_at(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")


def _merge_lists(current, new, key):
    merged = list(set(current[key] + new[key]))
    current[key] = merged
    new[key] = merged


def merge_runners(current, new):
    """Merge a project's runners (``new``) into the accumulator (``current``) in place.

    Runners are deduplicated by ``id``; their ``projects`` and ``tags`` lists are
    unioned; and when a duplicate has a more recent ``contacted_at`` its record
    replaces the existing scalar fields.
    """
    for runner in new:
        existing = next((c for c in current if c["id"] == runner["id"]), None)
        if not existing:
            current.append(runner)
            continue

        _merge_lists(existing, runner, "projects")
        _merge_lists(existing, runner, "tags")
        if _parse_contacted_at(runner["contacted_at"]) > _parse_contacted_at(existing["contacted_at"]):
            existing.update(runner)
