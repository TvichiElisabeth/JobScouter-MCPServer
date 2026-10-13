import asyncio
import json
import logging
from pathlib import Path
from mcp.server.mcpserver import MCPServer
from JobScouterMCP.search import search
from JobScouterMCP.sources import Job, Workplace, fetch_company
from mcp.server.mcpserver.exceptions import ToolError
log = logging.getLogger("JobScouterMCP")

COMPANIES_FILE = Path(__file__).parent / "companies.json"
COMPANIES = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))
COMPANY_NAMES = sorted(c["name"] for c in COMPANIES)

mcp = MCPServer("JobScouterMCP")

FETCH_DEADLINE = 8  # seconds; a company slower than this is skipped for this search

async def all_jobs() -> list[Job]:
    """Fetch jobs from every tracked company at the same time. Boards that fail
    or take longer than FETCH_DEADLINE seconds are skipped."""
    results = await asyncio.gather(
        *(asyncio.wait_for(fetch_company(c), timeout=FETCH_DEADLINE) for c in COMPANIES),
        return_exceptions=True,
    )
    jobs: list[Job] = []
    ok = 0
    for company, result in zip(COMPANIES, results):
        if isinstance(result, Exception):
            log.warning("skipping %s (%s): %r", company["name"], company["source"], result)
        else:
            log.info("%s (%s): %d jobs", company["name"], company["source"], len(result))
            jobs.extend(result)
            ok += 1
    log.info("fetched %d jobs from %d of %d companies", len(jobs), ok, len(COMPANIES))
    return jobs


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
    If workplace_unknown is present, mention its count and present those jobs
    separately as possible matches whose workplace isn't stated.
    Then list the jobs. If total_matches is larger than showing, say so and
    suggest narrowing the search with more filters.
    """
    if company and company.lower() not in {name.lower() for name in COMPANY_NAMES}:
          raise ToolError(
              f"Unknown company {company!r}. Tracked companies: {', '.join(COMPANY_NAMES)}"
          )
    
    log.info("search_jobs query=%r workplace=%r posted_within_days=%r company=%r,location=%r",
               query, workplace, posted_within_days, company, location)
    jobs = await all_jobs()
    result = search(jobs, query=query, workplace=workplace,
                      posted_within_days=posted_within_days, company=company, location=location)
    unknown = result.get("workplace_unknown", {}).get("count", "-")
    log.info("search_jobs: %d of %d jobs match, showing %d, workplace unknown: %s",
             result["total_matches"], len(jobs), result["showing"], unknown)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()