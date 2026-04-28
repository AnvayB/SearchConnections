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
