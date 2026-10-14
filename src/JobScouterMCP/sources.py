from typing import Literal, TypedDict
from datetime import datetime, timezone
import httpx
import html
import re

class Job(TypedDict):
    """One job posting, in the same shape no matter which job board it came from."""
    id: str
    company: str
    title: str
    location: str
    url: str
    posted: str      # "YYYY-MM-DD" in UTC, or "" if unknown
    workplace: str   # "onsite", "hybrid", "remote", or "" if unknown
    country: str     # ISO 3166-1 alpha-2 code like "RO", or "" if unknown

def parse_job_id(job_id: str) -> tuple[str, str, str]:
    """Split a job id like "greenhouse:Anthropic:5436293008" into
    (source, company, id), the reverse of how the normalizers build ids.
    Raises ValueError if the id doesn't have that shape."""
    parts = job_id.strip().split(":", 2)
    if len(parts) != 3 or not all(parts):      # all(): no empty piece like "greenhouse::123"
        raise ValueError(f"not a JobScouterMCP job id: {job_id!r}")
    source, company, raw_id = parts
    return source, company, raw_id

async def _get_json(url: str):
    """Download a URL and return its parsed JSON. Raises on HTTP errors (404, 500...)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    
# PostedDate Normalizer************************************
def to_utc_date(value) -> str:
    """Convert an ISO 8601 string (Greenhouse, Ashby) or a Unix timestamp in
    milliseconds (Lever) to "YYYY-MM-DD" in UTC. Returns "" if missing or unreadable."""
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:            # no offset given: assume UTC
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date().isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return ""

# Workplace Normalizer************************************
WORKPLACES = {"onsite", "hybrid", "remote"}
Workplace = Literal["onsite", "hybrid", "remote"]

def normalize_workplace(value) -> str:
    """Map any spelling of a workplace type ("On-Site", "OnSite", "Hybrid", "remote",
    "Hybrid (Travel-Required)") to "onsite", "hybrid" or "remote".
    Returns "" for missing or unrecognised values."""
    if not isinstance(value, str):
        return ""
    value = value.split("(")[0]          # drop extra detail like "(Travel-Required)"
    key = value.lower().replace("-", "").replace(" ", "").replace("_", "")
    return key if key in WORKPLACES else ""

# Country Normalizer****************************************
# Country name -> ISO 3166-1 alpha-2 code. Keys are lowercase.
# Covers Europe (the project's focus) plus common hiring countries; extend as needed.
COUNTRY_CODES = {
    "romania": "RO", "moldova": "MD", "bulgaria": "BG", "hungary": "HU",
    "poland": "PL", "czechia": "CZ", "czech republic": "CZ", "slovakia": "SK",
    "austria": "AT", "germany": "DE", "switzerland": "CH",
    "netherlands": "NL", "the netherlands": "NL", "belgium": "BE",
    "france": "FR", "spain": "ES", "portugal": "PT", "italy": "IT", "greece": "GR",
    "ireland": "IE", "united kingdom": "GB", "uk": "GB", "great britain": "GB",
    "denmark": "DK", "sweden": "SE", "norway": "NO", "finland": "FI",
    "estonia": "EE", "latvia": "LV", "lithuania": "LT",
    "croatia": "HR", "serbia": "RS", "ukraine": "UA",
    "united states": "US", "united states of america": "US", "usa": "US",
    "canada": "CA", "israel": "IL", "united arab emirates": "AE",
    "india": "IN", "singapore": "SG", "japan": "JP", "australia": "AU",
    "south korea": "KR", "brazil": "BR"
}

def country_code(name) -> str:
    """Convert a country name ("Poland", "Czech Republic") to its ISO code ("PL", "CZ").
    Returns "" for missing or unknown names."""
    if not isinstance(name, str):
        return ""
    return COUNTRY_CODES.get(name.strip().lower(), "")

# Main cities per country, so a country search also finds jobs whose location
# Text only names a city (Greenhouse has no country field). 
COUNTRY_CITIES = {
    "RO": ["bucharest", "bucuresti", "cluj", "iasi", "timisoara", "brasov", "sibiu", "constanta"],
}

# Description Normalizer************************************
def html_to_text(raw) -> str:
    """Turn an HTML job description into readable plain text: paragraphs on
    their own lines, list items as "- " bullets. Greenhouse escapes its HTML
    (&lt;p&gt;), so it is unescaped once before the tags are removed and once after.
    Returns "" for missing descriptions."""
    if not isinstance(raw, str):
        return ""
    text = html.unescape(raw)                                              # 1. &lt;p&gt; -> <p>
    text = re.sub(r"<li\b[^>]*>", "\n- ", text, flags=re.I)                # 2. list item -> bullet
    text = re.sub(r"<(br|/p|/div|/h\d|/ul|/ol)\b[^>]*>", "\n", text, flags=re.I)  # 3. block end -> new line
    text = re.sub(r"<[^>]+>", "", text)                                    # 4. drop all remaining inline or opening HTML tags that don't need dedicated line breaks
    text = html.unescape(text).replace("\xa0", " ")                        # 5. R&amp;D -> R&D, &nbsp; -> space
    lines = [" ".join(line.split()) for line in text.splitlines()]         # 6. tidy spaces on each line
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()             # 7. at most one blank line


#************************************************************************************************
# Greenhouse Normalizer + Fetcher---------------------------
def greenhouse_metadata(job: dict, name: str):
    """Return the value of the Greenhouse custom field called `name`
    (e.g. "Location Type"), or None if this company doesn't define it."""
    for field in job.get("metadata") or []:
        if (field.get("name") or "").strip().lower() == name.lower():
            return field.get("value")
    return None 

# Greenhouse has no standard workplace field; each company names its own custom field.
# Found by checking every tracked company (see data_analysis/greenhouse_workplace_checks.py).
GREENHOUSE_WORKPLACE_FIELDS = ("Location Type", "Work Type")
def greenhouse_workplace(job: dict) -> str:
    """Workplace for a Greenhouse job, from the first known custom field the company defines."""
    for name in GREENHOUSE_WORKPLACE_FIELDS:
        value = greenhouse_metadata(job, name)
        if value is not None:
            return normalize_workplace(value)
    return ""

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
            posted=to_utc_date(j.get("first_published")),
            workplace=greenhouse_workplace(j),
            country="",  # Greenhouse has no country field; filters fall back to the location text
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
            posted=to_utc_date(j.get("createdAt")),
            workplace=normalize_workplace(j.get("workplaceType")),
            country=(j.get("country") or "").upper(),
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
        # workplaceType wins; isRemote is only a fallback when workplaceType is missing.
        workplace = normalize_workplace(j.get("workplaceType"))
        if not workplace and j.get("isRemote") is True:
            workplace = "remote"

        address = (j.get("address") or {}).get("postalAddress") or {}

        jobs.append(Job(
            id=f"ashby:{company}:{j['id']}",
            company=company,
            title=j.get("title", ""),
            location=j.get("location") or "",
            url=j.get("jobUrl", ""),
            posted=to_utc_date(j.get("publishedAt")),
            workplace=workplace,
            country=country_code(address.get("addressCountry")),
        ))
    return jobs

async def fetch_ashby(company: str, board: str) -> list[Job]:
    """Download a company's open jobs from Ashby and return them as Jobs."""
    data = await _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
    return normalize_ashby(company, data)

# Dispatch -----------------------------------------------------------
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