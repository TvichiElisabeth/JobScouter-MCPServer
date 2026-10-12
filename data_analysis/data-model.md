# JobScouterMCP data model

JobScouterMCP reads open jobs from three applicant tracking systems (ATS): **Greenhouse**, **Lever** and **Ashby**. Each one publishes jobs through a public API, and each uses its own field names, formats and conventions. Every source is converted ("normalized") into one shared `Job` shape, so the rest of the server, and the LLM using it, never needs to know where a job came from.

This document records, field by field, what each ATS actually returns, what JobScouterMCP stores, and why.

**How the findings were gathered:** one raw job per ATS was inspected field by field (Greenhouse: `anthropic`, Lever: `aleph`, Ashby: `emagine` and `openai`), and the results were compared side by side. Observations based on a single example are marked as such.

---

## Current `Job` fields

| Field | Greenhouse | Lever | Ashby |
|---|---|---|---|
| `id` | `greenhouse:{company}:{id}` | `lever:{company}:{id}` | `ashby:{company}:{id}` |
| `company` | from `companies.json` | from `companies.json` | from `companies.json` |
| `title` | `title` | `text` (may contain emoji) | `title` |
| `location` | `location.name` | `categories.location` | `location` |
| `url` | `absolute_url` | `hostedUrl` | `jobUrl` |

The `id` prefix records the source, so a later `get_job_details(job_id)` tool knows which API to ask.

Greenhouse has two IDs: `id` (public, appears in the job URL) and `internal_job_id` (Greenhouse-internal). JobScouterMCP uses `id`.

---

## country

**Question it answers:** in which country is the job?

| ATS | Raw field | Example | Notes |
|---|---|---|---|
| Lever | `country` | `"HK"` | ISO 3166-1 alpha-2 code. `HK` is Hong Kong, not China (`CN`). |
| Ashby | `address.postalAddress.addressCountry` | `"Poland"` | Full country name. `location` alone is often only a city (`"Warsaw"`). |
| Greenhouse | none | `"New York City, NY; San Francisco, CA \| New York City, NY"` | Only free text in `location.name`; can contain several places, and may name a state rather than a country. |

**Decision:** `country` stores an ISO 3166-1 alpha-2 code (`"RO"`, `"PL"`, `"HK"`), or `""` when unknown.

| ATS | How `country` is filled |
|---|---|
| Lever | `country` as given (already a code) |
| Ashby | `addressCountry` converted with a small name → code lookup (`"Poland"` → `"PL"`) |
| Greenhouse | always `""` (no country field) |

**Why:** codes are unambiguous and stable, while names vary ("Czechia" vs "Czech Republic", "UK" vs "United Kingdom"). Lever already uses codes, so only Ashby needs converting, and a lookup table gives an exact answer instead of a guess.

**Filtering "jobs in Romania":** a job matches when `country == "RO"` **or** the `location` text contains "Romania" or a Romanian city (e.g. "Bucharest"). The text fallback is what finds Greenhouse jobs, which never have a country.

**Known limitations:**
-Our lookup table is small. If Ashby says “Moldova” and Moldova isn’t in our table, we can’t convert it, so the job ends up with no country.
-The text check only knows the cities we list. If a Greenhouse job just says “Cluj” and “Cluj” isn’t on our list, we miss it.
-Some jobs have no single country. “Remote, EU” could be anywhere in Europe, so there’s no one code to give it.

---

## workplace

**Question it answers:** where does the person work: on site, hybrid, or remote?

| ATS | Raw field(s) | Values seen | Notes |
|---|---|---|---|
| Lever | `workplaceType` | `hybrid`, `onsite` | Lowercase. `remote` expected per Lever's documentation, not yet seen. |
| Ashby | `workplaceType`, `isRemote` | `Hybrid`, `null` / `true`, `null` | Two fields describe the same thing and can disagree: emagine has `isRemote: true` with `workplaceType: "Hybrid"`. |
| Greenhouse | `metadata[]` entry with `name == "Location Type"`, its `value` | `On-Site` | A custom field each company defines for itself; other companies may name it differently or not have it. |

**Not the same concept:** `employmentType` (Ashby) and `categories.commitment` (Lever) describe the contract (full-time, part-time…), not the workplace. See [employment type](#employment-type-later).

**Decision, spelling:** `workplace` is one of `"onsite"`, `"hybrid"`, `"remote"`, or `""` when unknown. Lowercase, no hyphens: the spelling Lever already uses. Other spellings are mapped to it (`"On-Site"` → `"onsite"`, `"Hybrid"` → `"hybrid"`).

**Decision, Ashby conflict:** `workplaceType` wins. `isRemote` is used only when `workplaceType` is `null`, and then only `isRemote: true` → `"remote"`.

**Decision, missing values:** `""`. No guessing.

| ATS | How `workplace` is filled |
|---|---|
| Lever | `workplaceType`, lowercased |
| Ashby | `workplaceType` normalized; if `null`, `"remote"` when `isRemote` is `true`, else `""` |
| Greenhouse | value of the `metadata` entry named `"Location Type"`, normalized; `""` if the entry doesn't exist |

**Why:** `workplaceType` has three values and `isRemote` only two, so only `workplaceType` can express "hybrid". When `isRemote` says `true` but the job is hybrid, `isRemote` is the less precise field. Storing `""` instead of a guess means a "remote only" filter skips unknown jobs rather than showing wrong ones.

**Known limitations:**
- Greenhouse only has workplace data when the company defines a "Location Type" custom field, so many Greenhouse jobs will be `""`.
- When Ashby's `workplaceType` is `null` and `isRemote` is `false`, the job could be onsite or hybrid, so it stays `""`.
- Lever's `remote` value comes from Lever's documentation and hasn't been seen in the sampled data yet.

---

## posted

**Question it answers:** when was the job posted? Used for filters like "posted in the last 14 days".

| ATS | Raw field | Example | Format |
|---|---|---|---|
| Greenhouse | `first_published` | `"2024-12-20T13:53:38-05:00"` | ISO 8601 text with UTC offset |
| Lever | `createdAt` | `1787737476033` | Milliseconds since 1970 (UTC) → 26 Aug 2026 |
| Ashby | `publishedAt` | `"2026-10-09T08:09:39.605+00:00"` | ISO 8601 text with UTC offset |

**Greenhouse fields not used, and why:**
- `updated_at` changes whenever a recruiter edits the posting. The example job was first published in December 2024 and updated in August 2026; filtering on `updated_at` would make it look new.
- `application_deadline` is a closing date, not a posting date (and `null` in the sample). Possible separate field later.

**Decision, precision and format:** `posted` stores the date only, as `"YYYY-MM-DD"` text, or `""` when missing.

**Decision, time zone:** every timestamp is converted to UTC first, then the date is kept.

| ATS | How `posted` is filled |
|---|---|
| Greenhouse | `first_published` → UTC → date |
| Lever | `createdAt` ÷ 1000 (milliseconds → seconds) → UTC → date |
| Ashby | `publishedAt` → UTC → date |

**Why:** day precision is enough for filters like "posted in the last 14 days". ISO dates sort correctly as plain text (`"2026-08-20" > "2026-03-01"`), so filtering and sorting need no date parsing. Converting to UTC first means all three sources count days the same way.

**Known limitations:**
- "posted" does not mean exactly the same thing in each ATS. Lever's `createdAt` is when the posting was created in Lever, which can be before it went public. Ashby's `publishedAt` may reset if a job is republished.
- Converting to UTC can shift the date by one day: a job posted at 23:00 in New York on the 20th is stored as the 21st. That's acceptable for "last N days" filters, and the rule is the same for every source.

---

## employment type (later)

Not part of Step 7, recorded for later.

| ATS | Raw field | Example |
|---|---|---|
| Lever | `categories.commitment` | `"Full time"` |
| Ashby | `employmentType` | `"FullTime"` |
| Greenhouse | not in `/jobs` data | |

---

## Other observations

- **Descriptions:** Lever (`descriptionPlain`, `descriptionBodyPlain`) and Ashby (`descriptionPlain`) include plain-text descriptions. Greenhouse only returns descriptions with `?content=true`, as HTML.
- **Response shape:** Greenhouse and Ashby return `{"jobs": [...]}`; Lever returns a bare list `[...]`.
- **Language:** Greenhouse has `language` (`"en"`), which could later filter out postings in languages the user doesn't speak.
