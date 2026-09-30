import logging

from mcp.server.mcpserver import MCPServer

from JobScouterMCP.sources import fetch_greenhouse

log = logging.getLogger("JobScouterMCP")

mcp = MCPServer("JobScouterMCP")


@mcp.tool()
def list_companies() -> list[str]:
    """Names of all companies whose job boards JobScouterMCP tracks."""
    return ["Anthropic"]


@mcp.tool()
async def search_jobs(query: str) -> list[dict]:
    """Search open jobs by keyword in the job title, e.g. "engineer" or "research"."""
    log.info("search_jobs called with query=%r", query)
    jobs = await fetch_greenhouse("Anthropic", "anthropic")
    matches = [j for j in jobs if query.lower() in j["title"].lower()]
    log.info("found %d matching jobs out of %d", len(matches), len(jobs))
    return matches


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()