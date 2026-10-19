import asyncio
import json
import logging
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from JobScouterMCP.cache import BoardCache
from JobScouterMCP.search import search
from JobScouterMCP.sources import (Job, JobNotFound, Workplace, fetch_company,
                                   fetch_job_details, parse_job_id)

log = logging.getLogger("JobScouterMCP")

COMPANIES_FILE = Path(__file__).parent / "companies.json"
COMPANIES = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))
COMPANY_NAMES = sorted(c["name"] for c in COMPANIES)
COMPANIES_BY_KEY = {(c["source"], c["name"].lower()): c for c in COMPANIES} # (source, lowercase name) -> company entry, so a job id finds its board in one lookup.

mcp = MCPServer("JobScouterMCP")

FETCH_DEADLINE = 8  # seconds; a slower board uses its last cached copy, or is skipped if it has none
MAX_DESCRIPTION_CHARS = 12_000  # above every description measured (max 10,297); protects Claude's context
CACHE_TTL = 60 * 60   # seconds; job boards change slowly, an hour-old copy is fine

cache = BoardCache(ttl=CACHE_TTL)

# Utils----------------------------------------------------------------

async def get_company_jobs(company: dict) -> list[Job]:
    """One company's jobs: a fresh cached copy if there is one, otherwise a new
    download. If the download fails, fall back to the last copy, however old."""
    key = (company["source"], company["board"])

    jobs = cache.fresh(key)
    if jobs is not None:                 # [] is a valid answer (0 jobs), so not "if jobs:"
        return jobs

    try:
        jobs = await asyncio.wait_for(fetch_company(company), timeout=FETCH_DEADLINE)
    except (httpx.HTTPError, TimeoutError) as e:
        old = cache.stale(key)
        if old is None:
            raise                        # never downloaded: get_all_jobs skips it, as before
        log.warning("%s (%s): download failed (%r), using the last copy",
                    company["name"], company["source"], e)
        return old

    cache.put(key, jobs)
    return jobs

async def get_all_jobs() -> tuple[list[Job], list[str]]:
    """Jobs from every tracked company, fetched at the same time. Each company comes
    from the cache when possible (see get_company_jobs). Returns (jobs, names of the
    companies that could not be loaded and have no cached copy)."""
    results = await asyncio.gather(
        *(get_company_jobs(c) for c in COMPANIES),
        return_exceptions=True,
    )
    jobs: list[Job] = []
    unavailable: list[str] = []
    for company, result in zip(COMPANIES, results):
        if isinstance(result, Exception):
            log.warning("skipping %s (%s): %r", company["name"], company["source"], result)
            unavailable.append(company["name"])
        else:
            log.info("%s (%s): %d jobs", company["name"], company["source"], len(result))
            jobs.extend(result)
    log.info("%d jobs from %d of %d companies",
             len(jobs), len(COMPANIES) - len(unavailable), len(COMPANIES))
    return jobs, unavailable

def find_company_for_job(job_id: str) -> tuple[dict, str]:
    """Find the tracked company a job id belongs to. Returns (company entry, job number).
    Raises ToolError for ids Claude could fix, before any download."""
    try:
        source, name, raw_id = parse_job_id(job_id)
    except ValueError as e:
        raise ToolError(f"{e}. Use the id field of a job returned by search_jobs.") from e

    company = COMPANIES_BY_KEY.get((source, name.lower()))
    if company is None:
        raise ToolError(f"No tracked company {name!r} on {source!r}. "
                        f"Tracked companies: {', '.join(COMPANY_NAMES)}")
    return company, raw_id

# Tools----------------------------------------------------------------

@mcp.tool()
def list_companies() -> list[str]:
    """Names of all companies whose job boards JobScouterMCP tracks."""
    return COMPANY_NAMES


@mcp.tool()
async def search_jobs(
    query: str = "",
    workplace: Workplace | None = None,
    posted_within_days: int | None = None,
    company: str | None = None,
    location: str | None = None
) -> dict:
    """Search open jobs at all tracked companies. Returns at most 25 jobs, newest first.

    query: keyword in the job title, e.g. "engineer" or "machine learning". Empty = all jobs.

    workplace: only jobs that are "onsite", "hybrid" or "remote". Jobs that don't state
        their workplace are not counted as matches; they are listed separately under
        workplace_unknown.

    posted_within_days: only jobs posted in the last N days, e.g. 14.

    company: only jobs at this company, e.g. "Bitdefender". Must be one of the names
    returned by list_companies (case doesn't matter).

    location: only jobs in this place: a country ("Romania", "Germany"), an ISO
         country code ("RO") or a city ("Berlin"). For remote jobs use workplace instead.

    How to present the result: first say how many jobs matched (total_matches).
    If companies_unavailable is present, those companies could not be searched
    right now (their job boards did not respond). Say so, and do not claim they
    have no matching jobs.
    If workplace_unknown is present, mention its count and present those jobs
    separately as possible matches whose workplace isn't stated.
    Then list the jobs. If total_matches is larger than showing, say so and
    suggest narrowing the search with more filters.
    """
    company = company.strip() if company else company   # pasted input can carry spaces or a newline

    if company and company.lower() not in {name.lower() for name in COMPANY_NAMES}:
      raise ToolError(
              f"Unknown company {company!r}. Tracked companies: {', '.join(COMPANY_NAMES)}"
          )
    
    log.info("search_jobs query=%r workplace=%r posted_within_days=%r company=%r,location=%r",
               query, workplace, posted_within_days, company, location)
    jobs, unavailable = await get_all_jobs()
    result = search(jobs, query=query, workplace=workplace,
                      posted_within_days=posted_within_days, company=company, location=location)
    if company:
        # Searching one company: only that company's availability matters.
        unavailable = [n for n in unavailable if n.lower() == company.lower()]
    if unavailable:
        shown = result.pop("jobs")                  # keep "jobs" as the last, longest field
        result["companies_unavailable"] = unavailable
        result["jobs"] = shown
    unknown = result.get("workplace_unknown", {}).get("count", "-")
    log.info("search_jobs: %d of %d jobs match, showing %d, workplace unknown: %s",
             result["total_matches"], len(jobs), result["showing"], unknown)
    return result


@mcp.tool()
async def get_job_details(job_id: str) -> dict:
    """Full details of one job, including its plain-text description.

    job_id: the id field of a job returned by search_jobs,
        e.g. "greenhouse:Anthropic:5436293008".

    Use this after search_jobs, when the user wants to know more about a specific
    job (what the role involves, requirements, benefits). Call it only for the jobs
    the user asks about, not for every search result.

    How to present the result: summarise what the role involves and what it
    requires; quote the description only where exact wording matters. If
    description_truncated is true, say the description was cut and give the url
    for the full posting.
    """
    log.info("get_job_details job_id=%r", job_id)
    company, raw_id = find_company_for_job(job_id)
    try:
        job = await fetch_job_details(company, raw_id)
    except JobNotFound as e:
        raise ToolError(
            f"Job {job_id!r} is no longer on {company['name']}'s job board; it has "
            f"probably closed. Run search_jobs again to see current jobs."
        ) from e

    description = job.pop("description")
    truncated = len(description) > MAX_DESCRIPTION_CHARS
    log.info("get_job_details: %s, %d characters, truncated=%s",
             job["id"], len(description), truncated)
    return {**job,
            "description_truncated": truncated,
            "description": description[:MAX_DESCRIPTION_CHARS]}

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()