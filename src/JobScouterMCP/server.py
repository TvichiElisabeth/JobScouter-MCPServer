import asyncio
import json
import logging
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from JobScouterMCP.sources import Job, fetch_greenhouse

log = logging.getLogger("JobScouterMCP")

COMPANIES_FILE = Path(__file__).parent / "companies.json"
COMPANIES = json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))

mcp = MCPServer("JobScouterMCP")


async def all_jobs() -> list[Job]:
    """Fetch jobs from every tracked company at the same time. Boards that fail are skipped."""
    greenhouse = [c for c in COMPANIES if c["source"] == "greenhouse"]
    results = await asyncio.gather(
        *(fetch_greenhouse(c["name"], c["board"]) for c in greenhouse),
        return_exceptions=True,
    )
    jobs: list[Job] = []
    for company, result in zip(greenhouse, results):
        if isinstance(result, Exception):
            log.warning("skipping %s: %s", company["name"], result)
        else:
            jobs.extend(result)
    log.info("fetched %d jobs from %d companies", len(jobs), len(greenhouse))
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