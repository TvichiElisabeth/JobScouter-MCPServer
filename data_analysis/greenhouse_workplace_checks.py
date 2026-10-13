"""Greenhouse workplace investigation: the checks behind the "workplace" section
of data_analysis/data-model.md.

Question: Greenhouse has no standard on-site/hybrid/remote field. Companies can
define their own custom fields ("metadata"). Which companies define one, under
what name, and can we trust it?

Dev tool, not part of the JobScouterMCP server. Run from the project root with
the virtual environment active:

    python data_analysis/greenhouse_workplace_checks.py

Findings from the first run (12 Oct 2026) are recorded in the comments above
each check, so the reasoning stays next to the code that produced it.
"""
import asyncio
from collections import Counter

import httpx

from JobScouterMCP.sources import fetch_greenhouse

# The Greenhouse companies tracked in companies.json (board names).
BOARDS = ["anthropic", "scbitdefendersrl", "showpad", "telnyx54", "hootsuite"]


# ---------- Helpers ----------

def raw_jobs(board: str) -> list[dict]:
    """Download a board's jobs exactly as Greenhouse sends them (no normalizing)."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json().get("jobs", [])


def metadata_value(job: dict, name: str):
    """Value of the custom field called `name`, or None if the job doesn't have it."""
    for field in job.get("metadata") or []:
        if field.get("name") == name:
            return field.get("value")
    return None


def header(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------- Check 1: coverage after normalizing ----------
# How many jobs end up with a known workplace and a posting date, per company?
# This goes through the real normalizer (fetch_greenhouse), so it measures what
# the server will actually return.
#
# Finding (before greenhouse_workplace was added): only Anthropic had known
# workplaces (onsite 558, remote 19, unknown 69 of 646); the other four
# companies were 100% unknown. No company was missing posting dates.
# That gap is what started the investigation below.
#
# Finding (after greenhouse_workplace + bracket rule, 13 Oct 2026):
#   anthropic         644 jobs: onsite 556, remote 19, hybrid 9, unknown 60
#   scbitdefendersrl   65 jobs: hybrid 45, remote 17, onsite 3, unknown 0
#   showpad / telnyx54 / hootsuite: still 100% unknown (no workplace field exists)
#   Greenhouse total: 649 of 792 jobs (82%) have a known workplace.

def check_coverage() -> None:
    header("Check 1: workplace and posted coverage after normalizing")
    for board in BOARDS:
        jobs = asyncio.run(fetch_greenhouse(board, board))
        workplace = dict(Counter(j["workplace"] for j in jobs))
        missing_posted = sum(not j["posted"] for j in jobs)
        print(f"{board:18} {len(jobs):4} jobs  workplace={workplace}  missing posted={missing_posted}")


# ---------- Check 2: which custom fields does each company define? ----------
# Finding:
#   anthropic        -> "Location Type" (the name the code originally looked for)
#   scbitdefendersrl -> "Work Type", "Contract type", "Backfill Name", "Radford job code"
#   showpad          -> no custom fields at all
#   telnyx54         -> only "Hiring Manager"
#   hootsuite        -> only pay ranges ("Pay Range - Applicant - Canada" / "- US")
# So Bitdefender stores the workplace under a different name, and three
# companies don't publish it at all.

def check_field_names() -> None:
    header("Check 2: custom field names per company")
    for board in BOARDS:
        names = Counter(m.get("name") for j in raw_jobs(board) for m in (j.get("metadata") or []))
        print(f"{board:18} {dict(names)}")


# ---------- Check 3: what does Bitdefender's "Work Type" contain? ----------
# Finding: Hybrid 45, Remote 17, Onsite 3. Only workplace words, and all three
# spellings are understood by normalize_workplace.

def check_field_values(board: str, field: str) -> None:
    header(f"Check: values of {field!r} at {board}")
    values = Counter(str(metadata_value(j, field)) for j in raw_jobs(board))
    print(dict(values))


# ---------- Check 4: is "Contract type" a separate field? ----------
# Uses the same function as check 3 with another field name.
# Finding: Full-time 64, Part-time 1. Contract information lives in its own
# field, so "Work Type" is the workplace, not the contract. The one Part-time
# job is titled "Sales Development Representative - ANZ ( Part Time )", so the
# field also agrees with the titles.


# ---------- Check 5: do the postings themselves agree? ----------
# Print a few jobs whose "Work Type" is "Remote", then open the URLs in a
# browser and read the posting.
# Finding: one job's location is literally "Remote", another is titled
# "Principal Security Researcher & Community Advocate (Remote UK or EU)".
# Side note: Bitdefender's URLs use job-boards.eu.greenhouse.io (Greenhouse's
# EU instance); the API at boards-api.greenhouse.io works for them anyway.

def check_sample_jobs(board: str, field: str, value: str, limit: int = 3) -> None:
    header(f"Check: sample jobs at {board} where {field!r} = {value!r}")
    matches = [j for j in raw_jobs(board) if metadata_value(j, field) == value]
    print(f"{len(matches)} matching jobs; first {limit}:")
    for j in matches[:limit]:  # slice BEFORE printing, so only `limit` jobs are shown
        print(f"  {j['title']} | {(j.get('location') or {}).get('name', '')} | {j['absolute_url']}")


# ---------- Check 6: why are 69 Anthropic jobs still unknown? ----------
# Anthropic does use "Location Type", yet 69 jobs end up unknown.
#   None in the result     -> those jobs don't have the field (real gap, nothing to fix)
#   an unfamiliar spelling -> decide whether normalize_workplace should map it
#  
#  Finding: On-Site 556, Remote 19, None 60, 'Hybrid (Travel-Required)' 9.
#   The 60 None jobs don't have the field: a real gap, left as "".
#   The 9 'Hybrid (Travel-Required)' were an unfamiliar spelling. normalize_workplace
#   now drops text in brackets, so they become "hybrid".

def check_anthropic_location_type() -> None:
    header("Check 6: Anthropic 'Location Type' values, including missing")
    values = Counter(repr(metadata_value(j, "Location Type")) for j in raw_jobs("anthropic"))
    print(dict(values))


# ---------- Run everything in order ----------

def main() -> None:
    check_coverage()
    check_field_names()
    check_field_values("scbitdefendersrl", "Work Type")       # check 3
    check_field_values("scbitdefendersrl", "Contract type")   # check 4
    check_sample_jobs("scbitdefendersrl", "Work Type", "Remote")
    check_anthropic_location_type()


if __name__ == "__main__":
    main()