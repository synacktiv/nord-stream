from nordstream.parsers.gitlab import merge_runners


def _runner(rid, contacted_at, projects, tags, status="online"):
    return {
        "id": rid,
        "contacted_at": contacted_at,
        "projects": list(projects),
        "tags": list(tags),
        "status": status,
    }


def test_new_runner_id_is_appended():
    current = []
    merge_runners(current, [_runner("1", "2026-01-01T00:00:00.000Z", ["p1"], ["t1"])])
    assert len(current) == 1
    assert current[0]["id"] == "1"


def test_same_id_unions_projects_and_tags():
    current = [_runner("1", "2026-01-01T00:00:00.000Z", ["p1"], ["t1"])]
    merge_runners(current, [_runner("1", "2026-01-01T00:00:00.000Z", ["p2"], ["t2"])])
    assert len(current) == 1
    assert set(current[0]["projects"]) == {"p1", "p2"}
    assert set(current[0]["tags"]) == {"t1", "t2"}


def test_newer_contacted_at_overwrites_scalar_fields():
    current = [_runner("1", "2026-01-01T00:00:00.000Z", ["p1"], ["t1"], status="offline")]
    merge_runners(current, [_runner("1", "2026-06-01T00:00:00.000Z", ["p2"], ["t2"], status="online")])
    assert current[0]["status"] == "online"
    assert set(current[0]["projects"]) == {"p1", "p2"}


def test_older_contacted_at_does_not_overwrite_scalar_fields():
    current = [_runner("1", "2026-06-01T00:00:00.000Z", ["p1"], ["t1"], status="online")]
    merge_runners(current, [_runner("1", "2026-01-01T00:00:00.000Z", ["p2"], ["t2"], status="offline")])
    assert current[0]["status"] == "online"
    # lists are still unioned regardless of recency
    assert set(current[0]["projects"]) == {"p1", "p2"}
