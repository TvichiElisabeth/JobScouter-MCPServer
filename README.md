# JobScouterMCP

[![tests](https://github.com/TvichiElisabeth/JobScouter-MCPServer/actions/workflows/tests.yml/badge.svg)](https://github.com/TvichiElisabeth/JobScouter-MCPServer/actions/workflows/tests.yml)

**LinkedIn is where you find people and apply. JobScouterMCP is your research assistant: it searches the companies you care about, reads every posting, and (soon) tells you where you fit and what to learn next.**

<!-- TODO: demo GIF of Claude using search_jobs -->

**Status:** work in progress. Search works locally over stdio; deployment, caching and CV matching are on the [roadmap](#roadmap).

---

## What you can ask

With JobScouterMCP connected, Claude can answer questions like:

- *"Which remote engineering jobs were posted in the last two weeks?"*
- *"Show me ML jobs in Romania."*
- *"What is Bitdefender hiring for right now?"*
- *"Which companies do you track?"*
- *"What does the second job require? Is it a fit for a junior?"* (This is related to the tool get_job_details => This one shows the new ability, reading one posting in depth, and it shows how people will actually use it: as a follow-up to a search, not with an id typed by hand.)

Claude picks the tool and its arguments; JobScouterMCP fetches the jobs, filters them in code and returns a structured result.

---

## Tools

### `list_companies()`
Names of all companies whose job boards JobScouterMCP tracks.

### `search_jobs(...)`

| Argument | Example | What it does |
|---|---|---|
| `query` | `"engineer"`, `"ml"` | Keyword in the job title. Short queries (≤ 3 characters, usually acronyms) must be a whole word, so `ml` doesn't match "HTML"; longer ones match the start of a word, so `engineer` also finds "Engineering". |
| `workplace` | `"remote"` | `"onsite"`, `"hybrid"` or `"remote"`. Only these three values are accepted. |
| `posted_within_days` | `14` | Only jobs posted in the last N days. |
| `company` | `"Bitdefender"` | One tracked company (case doesn't matter). Unknown names return an error listing the tracked companies. |
| `location` | `"Romania"`, `"RO"`, `"Berlin"` | A country name, ISO country code or city. |

All arguments are optional and combine with AND.

**Result:**

```json
{
  "total_matches": 37,
  "showing": 25,
  "workplace_unknown": {
    "count": 216,
    "jobs": ["... the 10 newest jobs that don't state their workplace ..."]
  },
  "jobs": ["... the 25 newest matches ..."]
}
```

Each job has the same shape, whichever hiring system it came from:

```json
{
  "id": "greenhouse:Anthropic:5436293008",
  "company": "Anthropic",
  "title": "Staff+ Software Engineer, Account Abuse (Machine Learning)",
  "location": "San Francisco, CA | New York City, NY",
  "url": "https://job-boards.greenhouse.io/anthropic/jobs/5436293008",
  "posted": "2026-09-28",
  "workplace": "onsite",
  "country": ""
}
```
### `get_job_details(job_id)`

Full details of one job, including its description as plain text. `job_id` is the `id` of a job returned by `search_jobs`, e.g. `"lever:Aleph:0db5cfae-..."`.

```json
{
  "id": "lever:Aleph:0db5cfae-3bc7-4268-804a-effa0a012efc",
  "company": "Aleph",
  "title": "Audit & Compliance Manager, Europe",
  "...": "... the same fields as in search results ...",
  "description_truncated": false,
  "description": "Are you ready to join our digital revolution journey?\n\n...\n\nWhat You'll Do:\n- Audit Lifecycle Ownership: ..."
}
```

If the job has closed, the tool returns an error telling Claude to search again.

---

## Data sources

Jobs come only from **public job-board APIs** that companies publish through their applicant tracking system (ATS). No scraping, and no LinkedIn.

| ATS | Companies tracked |
|---|---|
| Greenhouse | Anthropic, Bitdefender, Hootsuite, Showpad, Telnyx |
| Ashby | Alchemy, Emagine, OpenAI, UiPath |
| Lever | Aleph, Caseware, Shield AI, TSMG |

About 6,937 with TSMG, about 2,560 without open jobs in total. Companies are listed in [`companies.json`](src/JobScouterMCP/companies.json); adding one is a single line.

---

## Design decisions

The full field-by-field analysis is in [`data_analysis/data-model.md`](data_analysis/data-model.md). The short version:

**One `Job` shape for three different APIs.** Greenhouse, Lever and Ashby name, format and nest the same information differently: dates as ISO text or Unix milliseconds, countries as codes, names or not at all. Each source has its own normalizer (adapter pattern), so the rest of the server and the LLM never need to know where a job came from.

**Unknown values are never guessed.** If a posting doesn't say whether it's remote, its `workplace` is `""`, not a guess. A "remote only" search therefore never shows a job that might be onsite.

**...but unknown jobs aren't silently dropped either.** When you filter by workplace, jobs that don't state one are returned as a separate group of possible matches. This matters more than it sounds: for `engineer` + `remote`, **37 jobs are listed as remote, and 216 more don't say**. A plain filter would hide all 216.

**Measure coverage, don't trust one example.** Greenhouse has no standard workplace field; each company defines its own custom field, if any. Checking every tracked company showed Anthropic uses "Location Type", Bitdefender uses "Work Type", and three companies publish nothing. Supporting both names (plus spellings like "Hybrid (Travel-Required)") raised known Greenhouse workplaces from 577 to 649 of ~790 jobs. The investigation is reproducible: [`data_analysis/greenhouse_workplace_checks.py`](data_analysis/greenhouse_workplace_checks.py).

**Location works even without a country field.** Lever and Ashby give a country; Greenhouse only has free text like "Bucharest". A location search matches the country code *or* the country's name and main cities in the text, so "Romania" finds jobs from all three sources.

**Small, structured results for the LLM.** At most 25 jobs (newest first), with counts first, so Claude's context isn't flooded and it knows when to suggest narrowing the search. The tool's docstring also tells Claude how to present the result.

**Validate at the boundary.** Tool arguments are checked by the MCP SDK against type hints before any code runs (e.g. `workplace` is a fixed set of values in the schema). Mistakes the caller can fix, like an unknown company, return a clear `ToolError` instead of an empty result, so Claude can't mistake an untracked company for one with no jobs.

**Search small, read on demand.** `search_jobs` never returns descriptions (5–10k characters each would flood Claude's context with 25 jobs). Claude calls `get_job_details` only for the jobs the user asks about. Descriptions are capped at 12,000 characters, above every one measured, with a `description_truncated` flag so Claude knows if text was cut.

**One description format for three ATS.** Greenhouse double-escapes its HTML, Lever splits a posting into an intro, titled lists and a closing part, and Ashby wraps each bullet in a styled paragraph. Every description goes through the same HTML-to-text cleaner, so Claude always sees paragraphs and `- ` bullets, whichever system a job came from. Each cleaning rule comes from a real case found in the data.

---

## Run it locally

Requirements: Python 3.11+, Node.js (only for the Inspector).

```bash
git clone https://github.com/TvichiElisabeth/JobScouter-MCPServer.git
cd JobScouter-MCPServer
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"
```

Try the tools in the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector JobScouterMCP
```

Then: **Connect → Tools → search_jobs**, fill in some arguments and run. Copy an `id` from the results into **get_job_details** to read that posting.

---

## Project structure

```
src/JobScouterMCP/
├── server.py        MCP tools: argument checks, downloading, logging
├── search.py        search logic (no network): filtering, matching, building the result
├── sources.py       one adapter per ATS: fetch + normalize into the shared Job shape
└── companies.json   tracked companies and their job boards
data_analysis/
├── data-model.md                    what each ATS returns, what is stored, and why
└── greenhouse_workplace_checks.py   reproducible coverage checks
```

---

## Roadmap

- [x] Greenhouse, Lever and Ashby sources, fetched concurrently with a per-company deadline
- [x] Normalized posting date, workplace and country, with documented coverage
- [x] Filters: query, workplace, posting date, company, location
- [x] Structured results with partial matches
- [x] `get_job_details(job_id)`: full description of one job
- [x] Unit tests (pytest, no network)
- [x] Caching (download hourly instead of on every search)
- [ ] Claude Desktop setup guide
- [ ] Remote deployment (HTTP transport, Docker), install by URL
- [ ] CV matching and skill-gap report, with an evaluation on hand-labelled job/CV pairs
- [ ] Tool-use evals in CI: does Claude pick the right tool and arguments?

---

## Known limitations

- Each search currently re-downloads all job boards (~10 s); slow boards can be skipped for that search. Caching is next.
- Workplace is unknown for about a third of OpenAI jobs and for every job at companies that don't publish it (see the data model).
- The country/city lookup is intentionally small and Europe-focused; it's easy to extend.
- Ashby has no public one-job endpoint, so `get_job_details` downloads the whole board to find one Ashby job. Caching will remove this cost.
- Job boards are cached in memory for an hour, so the first search after starting the server takes ~10 s and later ones are instant. Restarting the server empties the cache.

