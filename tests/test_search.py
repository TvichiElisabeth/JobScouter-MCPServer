"""Unit tests for search.py: location matching, title matching, filters and the
structured search result. No network: every job is a small fake built by make_job."""
from datetime import date, timedelta

import pytest

from JobScouterMCP.search import (MAX_RESULTS, filter_jobs, matches_location,
                                  query_pattern, search)


def make_job(**fields) -> dict:
    """A fake job with harmless defaults. Each test overrides only the fields it cares about."""
    job = {"id": "greenhouse:Test:1", "company": "Test", "title": "Engineer",
           "location": "", "url": "", "posted": "2026-09-01",
           "workplace": "", "country": ""}
    job.update(fields)
    return job


# matches_location -----------------------------------------------------------

@pytest.mark.parametrize("job, place, expected", [
    (make_job(country="RO", location="Bucharest"), "Romania", True),         # Lever/Ashby: country code
    (make_job(location="Bucharest"), "Romania", True),                       # Greenhouse: city in the text
    (make_job(location="Cluj-Napoca, Romania"), "RO", True),                 # ISO code finds city text too
    (make_job(location="Bucharest"), "bucharest", True),                     # city, any case
    (make_job(location="Berlin, Germany"), "Germany", True),                 # country name in the text
    (make_job(location="Berlin, Germany"), "Romania", False),
    (make_job(country="US", location="Austin"), "US", True),                 # code match
    (make_job(location="Austin, TX"), "US", False),                          # "us" is never matched as text
])
def test_matches_location(job, place, expected):
    assert matches_location(job, place) is expected


# query_pattern --------------------------------------------------------------

TITLES = ["ML Engineer", "HTML Developer", "Senior Engineering Manager",
          "AI Research Scientist", "Training Specialist", "C++ Developer",
          "MLOps Engineer", "Machine Learning Engineer"]


@pytest.mark.parametrize("query, expected", [
    ("ml", ["ML Engineer"]),                                   # short = whole word: not HTML, not MLOps
    ("ai", ["AI Research Scientist"]),                         # not "Training"
    ("engineer", ["ML Engineer", "Senior Engineering Manager",
                  "MLOps Engineer", "Machine Learning Engineer"]),   # long = start of a word
    ("c++", ["C++ Developer"]),                                # special characters are escaped
    ("Machine Learning", ["Machine Learning Engineer"]),       # case doesn't matter
])
def test_query_pattern(query, expected):
    pattern = query_pattern(query)
    assert [t for t in TITLES if pattern.search(t)] == expected


# filter_jobs ----------------------------------------------------------------

def test_filters_combine_with_and():
    jobs = [make_job(title="ML Engineer", company="Aleph", workplace="remote"),
            make_job(title="ML Engineer", company="Aleph", workplace="onsite"),
            make_job(title="Accountant", company="Aleph", workplace="remote")]
    assert filter_jobs(jobs, query="ml", workplace="remote") == [jobs[0]]


def test_unknown_workplace_never_matches_a_workplace_filter():
    assert filter_jobs([make_job(workplace="")], workplace="remote") == []


def test_company_filter_ignores_case():
    jobs = [make_job(company="Bitdefender"), make_job(company="Aleph")]
    assert filter_jobs(jobs, company="bitdefender") == [jobs[0]]


def test_posted_within_days():
    today = date.today()
    recent = make_job(posted=(today - timedelta(days=3)).isoformat())
    old = make_job(posted=(today - timedelta(days=60)).isoformat())
    undated = make_job(posted="")
    assert filter_jobs([recent, old, undated], posted_within_days=14) == [recent]


# search ---------------------------------------------------------------------

def thirty_remote_and_three_unknown() -> list[dict]:
    jobs = [make_job(title=f"Engineer {d}", workplace="remote", posted=f"2026-09-{d:02d}")
            for d in range(1, 31)]
    jobs += [make_job(title=f"Engineer X{i}", workplace="", posted="2026-09-15") for i in range(3)]
    return jobs


def test_search_counts_sorts_and_cuts():
    result = search(thirty_remote_and_three_unknown(), query="engineer", workplace="remote")
    assert result["total_matches"] == 30
    assert result["showing"] == MAX_RESULTS == 25
    assert result["jobs"][0]["posted"] == "2026-09-30"      # newest first
    assert result["jobs"][-1]["posted"] == "2026-09-06"     # the 25th newest


def test_search_lists_jobs_without_a_workplace_separately():
    result = search(thirty_remote_and_three_unknown(), query="engineer", workplace="remote")
    assert result["workplace_unknown"]["count"] == 3


def test_search_without_workplace_filter_has_no_partial_group():
    result = search(thirty_remote_and_three_unknown(), query="engineer")
    assert result["total_matches"] == 33
    assert "workplace_unknown" not in result