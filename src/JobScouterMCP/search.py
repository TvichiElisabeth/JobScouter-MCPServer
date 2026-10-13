from datetime import datetime, timedelta, timezone

from JobScouterMCP.sources import Job, Workplace


def filter_jobs(
    jobs: list[Job],
    query: str = "",
    workplace: Workplace | None = None,
    posted_within_days: int | None = None,
) -> list[Job]:
    """Keep only the jobs that match every filter given. A filter left as None/"" is ignored."""
    if posted_within_days is not None:
        today = datetime.now(timezone.utc).date()
        cutoff = (today - timedelta(days=posted_within_days)).isoformat()

    result = []
    for j in jobs:
        if query and query.lower() not in j["title"].lower():
            continue
        if workplace and j["workplace"] != workplace:
            continue                      # unknown ("") never matches: no guessing
        if posted_within_days is not None and (not j["posted"] or j["posted"] < cutoff):
            continue
        result.append(j)
    return result