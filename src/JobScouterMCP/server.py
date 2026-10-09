import asyncio
import json
import logging
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from JobScouterMCP.sources import Job, fetch_company

log = logging.getLogger("JobScouterMCP")

COMPANIES_FILE = Path(__file__).parent / "companies.json"
COMPANIES = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))

mcp = MCPServer("JobScouterMCP")


async def all_jobs() -> list[Job]:
    """Fetch jobs from every tracked company at the same time. Boards that fail are skipped."""
    results = await asyncio.gather(
        *(fetch_company(c) for c in COMPANIES),
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
    return sorted(c["name"] for c in COMPANIES)


@mcp.tool()
async def search_jobs(query: str) -> list[dict]:
    """Search open jobs at all tracked companies by keyword in the job title,
    e.g. "engineer" or "machine learning"."""
    log.info("search_jobs called with query=%r", query)
    jobs = await all_jobs()
    return [j for j in jobs if query.lower() in j["title"].lower()]


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()