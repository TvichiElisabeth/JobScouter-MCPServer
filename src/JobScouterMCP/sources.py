from typing import TypedDict

import httpx


class Job(TypedDict):
    """One job posting, in the same shape no matter which job board it came from."""
    id: str
    company: str
    title: str
    location: str
    url: str

async def _get_json(url: str):
    """Download a URL and return its parsed JSON. Raises on HTTP errors (404, 500...)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()

    
 # Greenhouse Normalizer + Fetcher---------------------------
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
    data = await _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
    return normalize_greenhouse(company, data)

# Lever Normalizer + Fetcher---------------------------------------
def normalize_lever(company: str, data: list) -> list[Job]:
    """Convert Lever's JSON format into our Job format. Lever returns a plain list, not {"jobs": [...]}."""
    jobs = []
    for j in data:
        jobs.append(Job(
            id=f"lever:{company}:{j['id']}",
            company=company,
            title=j.get("text", ""),
            location=(j.get("categories") or {}).get("location", ""),
            url=j.get("hostedUrl", ""),
        ))
    return jobs


async def fetch_lever(company: str, board: str) -> list[Job]:
    """Download a company's open jobs from Lever and return them as Jobs."""
    data = await _get_json(f"https://api.lever.co/v0/postings/{board}?mode=json")
    return normalize_lever(company, data)


# Ashby Normalizer + Fetcher---------------------------------------
def normalize_ashby(company: str, data: dict) -> list[Job]:
    """Convert Ashby's JSON format into our Job format."""
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(Job(
            id=f"ashby:{company}:{j['id']}",
            company=company,
            title=j.get("title", ""),
            location=j.get("location") or "",
            url=j.get("jobUrl", ""),
        ))
    return jobs


async def fetch_ashby(company: str, board: str) -> list[Job]:
    """Download a company's open jobs from Ashby and return them as Jobs."""
    data = await _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
    return normalize_ashby(company, data)

# Dispatch -----------------------------
FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "ashby": fetch_ashby,
    "lever": fetch_lever,
}


async def fetch_company(company: dict) -> list[Job]:
    """Fetch one company's jobs using the right fetcher for its "source" in companies.json."""
    fetcher = FETCHERS.get(company["source"])
    if fetcher is None:
        raise ValueError(f"unknown source {company['source']!r}")
    return await fetcher(company["name"], company["board"])