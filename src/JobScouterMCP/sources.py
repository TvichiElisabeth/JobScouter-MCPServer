from typing import TypedDict

import httpx


class Job(TypedDict):
    """One job posting, in the same shape no matter which job board it came from."""
    id: str
    company: str
    title: str
    location: str
    url: str


def normalize_greenhouse(company: str, data: dict) -> list[Job]:
    """Convert Greenhouse's JSON format into our Job format."""
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(Job(
            id=f"greenhouse:{company}:{j['id']}",
            company=company,
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
        ))
    return jobs


async def fetch_greenhouse(company: str, board: str) -> list[Job]:
    """Download a company's open jobs from Greenhouse and return them as Jobs."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        return normalize_greenhouse(company, resp.json())