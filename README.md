# LinkedIn Connections Search Tool
A web-based search tool for exploring LinkedIn connections data from multiple sources.


<!--
Additions:

* if password = guest, 
	- create 3 sample datasets for each person so users can test the functionality of the website

-->


## Features
- **Responsive Design**: Works on desktop and mobile devices
- **Modern UI**: Clean interface with a quiet indigo/rose palette; the only large gradient is the page background
- **Accessible**: labelled inputs, keyboard-navigable tabs (arrow keys), descriptive link names, visible focus rings
- **Inline login**: a password form on the page (a page gate, not real security: the password is in `script.js`)
- **Fast Search**: Optimized search with autocomplete
- **Data Statistics**: Shows count of results from each data source
- **Direct Links**: One-click access to LinkedIn profiles
- **Company Jobs Links**: Each company search includes a button to that company's LinkedIn jobs page
- **Landing view**: before a search it shows totals and chips for the biggest overlaps
- **Companies Tab**: companies where two or more connections work, with who they are

## Companies Tab

The **Companies** tab answers "where does my network overlap?". It lists only companies where **two or more different people** work (about 24 of the ~270), biggest first. Each card shows the people as chips, with a coloured dot per list they appear in (teal = Anvay, amber = Anil, blue = Bilwa; two dots means the person is in two lists), plus the jobs button(s). Clicking a card, or pressing Enter on the company name, opens that company on the **Connections** tab.

Names that refer to the same company are grouped (see [Company grouping](#company-grouping)), so **Amazon** and **Amazon Web Services (AWS)** are one card with an "Includes: ..." note. Placeholders such as Freelance or Stealth Startup are never listed. Companies with a single connection are not listed: search for them on the Connections tab.

Filter the cards with the box at the top; it understands the same groupings (typing `aws` finds Amazon). The threshold is `MIN_SHARED` in `script.js`.

### Jobs links

| Situation | Button |
|---|---|
| A LinkedIn company jobs page is known (`linkedin_jobs_final.csv`) | **View Jobs on LinkedIn** |
| No known page | **Search jobs on LinkedIn** (a LinkedIn job search for the company name) |
| Placeholder such as Freelance, Self-employed, Stealth Startup, Career break | no button |

If `updated_data/company_linkedin_urls.csv` has a page for a company (written by the link verifier below), it takes priority over `linkedin_jobs_final.csv`. When a result covers several companies with different pages (Amazon and AWS), one button per page is shown.

## Company grouping

The CSVs store company as free text, so the same company can appear under several names. `script.js` groups them in two steps:

1. **Normalisation** lowercases the name and drops punctuation and legal suffixes, so `Oracle Corp.`, `Oracle Corporation` and `Oracle` match on their own.
2. **`COMPANY_ALIASES`** (top of the grouping section in `script.js`) lists names that really are different strings for one company: `AWS` for Amazon, `Facebook` for Meta, `Alphabet` for Google, and so on. Add a line there when you find another pair.

`COMPANY_ALIASES` is mirrored in `employment_parse.py` so the scraper does not report a rename as a job change. `tests/test_employment_parse.py` fails if the two lists differ.

Search behaviour: a name that is a known company or alias returns exactly that company. Otherwise every word you type must match the start of a word in the company name. Commas separate several companies (`Google, Microsoft`), except commas that are part of a name (`Reddit, Inc.`).

## Verify LinkedIn Links

Use `verify_company_linkedin_links.py` to resolve canonical LinkedIn company URLs from your **connection profile experience pages** (no Google search). For each unique company, the script visits a connection's `/details/experience/` page, finds an experience entry matching that company, and saves the `linkedin.com/company/...` href to `updated_data/company_linkedin_urls.csv`.

If the first connection's current job doesn't match the CSV company, it tries other connections at the same company. Companies with no company page link (e.g. **Freelance**, **5G Stealth**) get an empty URL, and the UI falls back to a LinkedIn job search (or no button for placeholders).

**Requires LinkedIn login** — use `.env` credentials or `--allow-manual-login` (same setup as employment verification).

### Run

Test with 5 companies (visible browser for debugging):

```bash
.venv/bin/python verify_company_linkedin_links.py --all-companies --resume --limit 5 --no-headless
```

Batch through all connection companies (25 companies per run):

```bash
.venv/bin/python verify_company_linkedin_links.py --all-companies --resume --limit 25
```

Or via Makefile:

```bash
make verify-links-batch
```

Retry only companies with an empty LinkedIn URL:

```bash
make verify-links-retry
```

Re-verify everything from scratch (e.g. after failed Google runs):

```bash
.venv/bin/python verify_company_linkedin_links.py --all-companies --force --limit 25
```

Run batch commands repeatedly until everything is verified (~11 runs for ~277 companies at 25 per batch). One profile visit per company (~5s delay ≈ 25 min full run).

Useful flags:

- `--headless` / `--no-headless` — background vs visible browser (default: headless)
- `--delay 5` — seconds between companies (default: 5)
- `--resume` — skip companies that already have a non-empty LinkedIn_URL
- `--retry-empty` — only verify companies already in the CSV with an empty LinkedIn_URL
- `--force` — re-verify all companies
- `--limit 25` — verify at most 25 companies from the remaining queue
- `--all-companies` — verify from all connection CSVs instead of the top-17 list
- `--allow-manual-login` — log in manually in the browser if needed

## Employment Verification Script

Use `verify_linkedin_employment.py` to update employment columns using LinkedIn profile pages. The parsing and decision logic lives in `employment_parse.py` (no Playwright needed, unit tested).

Rules for each profile's most recent experience entry:

- **No `Present` in the date range**: `Still_Employed = No`.
- **Same company** (compared after normalisation and aliases): nothing changes.
- **Different company that looks like a real employer**: `Company`/`Position` are updated, the old values are saved in `Previous_Company`/`Previous_Position`, and `Employment_Changed = Yes`.
- **Different "company" that does not look like an employer** (a page heading, a job title, a location, "Career break"): `Company`/`Position` are **not** touched. The scraped values go to `Scraped_Company`/`Scraped_Position` and `Employment_Changed = Review`.
- **Anything that fails** (timeout, login wall, unreadable page, missing URL): the row is left unchanged. A failure is never written as `Still_Employed = No`.

New columns: `Previous_Company`, `Previous_Position`, `Scraped_Company`, `Scraped_Position`.

To re-check people currently marked `No` (for example after upgrading from the old scraper, which wrote `No` on errors), run it on the updated file:

```bash
.venv/bin/python verify_linkedin_employment.py --recheck-no \
  --input updated_data/anvay-connections_updated.csv \
  --output updated_data/anvay-connections_updated.csv
```

### Setup

```bash
python3 -m venv .venv
.venv/bin/pip install playwright
.venv/bin/python -m playwright install chromium
```

### Run

```bash
.venv/bin/python verify_linkedin_employment.py --limit 5
```

Credential options:

Use a `.env` file (no `export` needed):

```bash
cp .env.example .env
# edit .env with your real LinkedIn email/password
.venv/bin/python verify_linkedin_employment.py
```

You can also point to a custom env file:

```bash
.venv/bin/python verify_linkedin_employment.py --env-file /path/to/custom.env
```

Or use exported shell env vars:

```bash
export LINKEDIN_EMAIL="you@example.com"
export LINKEDIN_PASSWORD="your_password"
.venv/bin/python verify_linkedin_employment.py
```

Or provide only the email and the script will securely prompt for the password (hidden input):

```bash
export LINKEDIN_EMAIL="you@example.com"
.venv/bin/python verify_linkedin_employment.py
```

Or use manual login fallback in the opened browser window:

```bash
.venv/bin/python verify_linkedin_employment.py --allow-manual-login
```

Optional hardcoded fallback is available at the top of `verify_linkedin_employment.py` (`HARDCODED_LINKEDIN_EMAIL` and `HARDCODED_LINKEDIN_PASSWORD`), but `.env` is preferred.

## Recommended Job Scanner

Use `scan_company_jobs.py` to scrape LinkedIn's **"Recommended for you"** carousel on each company's `/company/{slug}/jobs/` page, classify titles into role buckets, and write results to `updated_data/top20_job_counts.csv`.

### Role buckets

- **SWE** — software engineer, developer, SDE, backend/frontend, platform
- **Data Analyst** — data analyst, BI analyst, analytics/reporting analyst
- **Data Engineer** — data engineer, analytics engineer, ETL/pipeline
- **Data Scientist / ML** — data scientist, ML engineer, AI engineer, applied scientist

Each company row reflects up to **6 personalized recommendations** from LinkedIn (not total company-wide openings).

### Default company list (17)

Apple, Arteris, Google, Oracle, AWS, Honeywell, Amazon, MacDermid Alpha, Meta, Microsoft, Applied Materials, Entegris, KLA, Mariana Minerals, NVIDIA, PayPal, Sila Nanotechnologies Inc.

### Run

Test with 3 companies (visible browser for debugging):

```bash
.venv/bin/python scan_company_jobs.py --limit 3 --no-headless
```

Full top-17 re-scan (headless, runs in background):

```bash
.venv/bin/python scan_company_jobs.py --force
```

Batch through all connection companies (25 unscanned companies per run):

```bash
.venv/bin/python scan_company_jobs.py --all-companies --resume --limit 25
```

Run that batch command repeatedly until everything is scanned.

Useful flags:

- `--headless` / `--no-headless` — background vs visible browser (default: headless)
- `--delay 5` — seconds between companies (default: 5)
- `--resume` — skip companies already in the output CSV
- `--force` — rescan even if a company is already in the CSV
- `--limit 25` — scan at most 25 companies from the remaining queue (works correctly with `--resume`)
- `--all-companies` — scan from all connection CSVs instead of the top-17 list

## Repairing company data

Earlier versions of the employment scraper overwrote `Company` in place and sometimes saved a heading or job title ("Experience", "Research Assistant"). `fix_company_data.py` repairs this from the original exports in `old-data/`:

```bash
python3 -I fix_company_data.py           # dry run: prints what it would change
python3 -I fix_company_data.py --apply   # rewrites the CSVs and writes updated_data/review_company_changes.csv
```

Each `Employment_Changed=Yes` row is restored (scraped value was not an employer, or was only a rename), kept with `Previous_*` filled in (a genuine move), or kept and flagged for a human look. `review_company_changes.csv` lists every row and the decision.

## Tests

```bash
make test-search   # search, grouping, jobs links, Companies tab, load errors (Node, no browser)
make test-parse    # scraper parsing and row-update rules (Python stdlib, no LinkedIn login)
```

`make test` is the older script that scrapes live LinkedIn profiles and needs a login.

### CSV columns

`First Name, Last Name, URL, Company, Position, [Connected On], Still_Employed, Employment_Changed, Previous_Company, Previous_Position, Scraped_Company, Scraped_Position`. The app only needs the first four; the rest add notes to results ("may no longer work here", "Previously at ...").

