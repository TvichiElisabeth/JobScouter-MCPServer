"""Search logic for JobScouterMCP, kept separate from the MCP tools so it can be
tested without the network.

Three layers, each with one job:

    search_jobs  (server.py)  the door: checks Claude's arguments, downloads jobs, logs
      └─ search               builds the answer: sort, count, cut to 25, partial matches
           └─ filter_jobs     the sieve: which jobs pass the filters?
"""
from datetime import datetime, timedelta, timezone

from JobScouterMCP.sources import Job, Workplace

MAX_RESULTS = 25         # jobs returned to Claude; more would flood its context
MAX_UNKNOWN_SHOWN = 10   # partial matches shown; their full number is still counted


def filter_jobs(
    jobs: list[Job],
    query: str = "",
    workplace: Workplace | None = None,
    posted_within_days: int | None = None,
) -> list[Job]:
    """Keep only the jobs that match every filter given. A filter left as None/"" is ignored.

    This is the sieve: it only decides which jobs pass. It doesn't sort, count or
    limit anything; search() does that.
    """
    if posted_within_days is not None:
        today = datetime.now(timezone.utc).date()
        cutoff = (today - timedelta(days=posted_within_days)).isoformat()

    result = []
    for j in jobs:
        # Each check that fails skips the job; only jobs passing all checks are kept.
        if query and query.lower() not in j["title"].lower():
            continue
        if workplace and j["workplace"] != workplace:
            continue                      # unknown ("") never matches: no guessing
        if posted_within_days is not None and (not j["posted"] or j["posted"] < cutoff):
            continue                      # ISO dates compare correctly as plain text
        result.append(j)
    return result


def newest_first(jobs: list[Job]) -> list[Job]:
    """Sort jobs by posting date, newest first. Jobs without a date ("") go last,
    because "" is the smallest possible text."""
    return sorted(jobs, key=lambda j: j["posted"], reverse=True)


def search(
    jobs: list[Job],
    query: str = "",
    workplace: Workplace | None = None,
    posted_within_days: int | None = None,
) -> dict:
    """Filter jobs and return a structured result: how many matched, the newest
    matches, and (when filtering by workplace) the jobs left out only because
    they don't state their workplace.

    Uses filter_jobs twice with different settings, which is why filtering
    lives in its own function.
    """
    # 1st use of the sieve, with every filter: the real matches.
    matches = newest_first(filter_jobs(jobs, query, workplace, posted_within_days))

    # Counts come first, so Claude reads them before the long list of jobs.
    result = {
        "total_matches": len(matches),
        "showing": min(len(matches), MAX_RESULTS),
    }

    if workplace:
        # 2nd use of the sieve, with the workplace filter turned off (None):
        # every job that passes the other filters. From those, keep the ones
        # with unknown workplace ("").
        # These are the partial matches: they might be remote (or onsite/hybrid),
        # but the posting doesn't say. They are shown as a separate group
        # instead of being counted as matches (no guessing) or silently dropped.
        # Without a workplace filter, these jobs are already normal matches,
        # so the group is only added when one is set.
        unknown = [j for j in filter_jobs(jobs, query, None, posted_within_days) if j["workplace"] == ""]
        result["workplace_unknown"] = {
            "count": len(unknown),
            "jobs": newest_first(unknown)[:MAX_UNKNOWN_SHOWN],
        }

    # The jobs themselves go last, newest first, cut to MAX_RESULTS.
    result["jobs"] = matches[:MAX_RESULTS]
    return result