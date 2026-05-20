# LinkedIn Connections Search Tool
A web-based search tool for exploring LinkedIn connections data from multiple sources.


<!--
Additions:

* if password = guest, 
	- create 3 sample datasets for each person so users can test the functionality of the website

-->


## Features
- **Responsive Design**: Works on desktop and mobile devices
- **Modern UI**: Clean, professional interface with gradients and animations
- **Fast Search**: Optimized search with autocomplete
- **Data Statistics**: Shows count of results from each data source
- **Direct Links**: One-click access to LinkedIn profiles
- **Company Jobs Links**: Each company search includes a button to that company's LinkedIn jobs page

## Employment Verification Script

Use `verify_linkedin_employment.py` to update a `Still_Employed` column in `data/anvay_connections.csv` using LinkedIn profile pages.

- Rule: if the top Experience date range does **not** include `Present`, write `No`.
- Otherwise, `Still_Employed` is left blank.

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

Use `scan_company_jobs.py` to scrape LinkedIn's **"Recommended for you"** carousel on each company's `/company/{slug}/jobs/` page, classify titles into role buckets, and write results to `updated_data/top20_job_counts.csv` for the **Job Openings** tab.

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
