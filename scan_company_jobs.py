#!/usr/bin/env python3
"""
Scan LinkedIn "Recommended for you" jobs on company /jobs pages.

For each company, opens https://www.linkedin.com/company/{slug}/jobs/,
scrapes titles from the personalized recommendation carousel, and classifies
them into role buckets. Writes results to CSV for the web UI.

Personal-use only. Uses conservative delays between page loads.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

import verify_linkedin_employment as vle


CONNECTION_CSVS = [
    Path("updated_data/anvay-connections_updated.csv"),
    Path("updated_data/anil-connections_updated.csv"),
    Path("updated_data/bilwa-connections_updated.csv"),
]

DEFAULT_OUTPUT = Path("updated_data/top20_job_counts.csv")

TOP_COMPANIES = [
    "Apple",
    "Arteris",
    "Google",
    "Oracle",
    "Amazon Web Services (AWS)",
    "Honeywell",
    "Amazon",
    "MacDermid Alpha Electronics Solutions",
    "Meta",
    "Microsoft",
    "Applied Materials",
    "Entegris",
    "KLA",
    "Mariana Minerals",
    "NVIDIA",
    "PayPal",
    "Sila Nanotechnologies Inc.",
]

COMPANY_SLUG_OVERRIDES: dict[str, str] = {
    "Intel Corporation": "intel",
    "Amazon Web Services (AWS)": "amazon-web-services",
    "Meta": "meta",
    "Google": "google",
    "Microsoft": "microsoft",
    "Apple": "apple",
    "NVIDIA": "nvidia",
    "Netflix": "netflix",
    "Oracle": "oracle",
    "IBM": "ibm",
    "Salesforce": "salesforce",
    "Adobe": "adobe",
    "Uber": "uber",
    "Airbnb": "airbnb",
    "LinkedIn": "linkedin",
    "Tesla": "tesla",
    "SpaceX": "spacex",
    "Palantir Technologies": "palantir-technologies",
    "Snowflake": "snowflake-computing",
    "Databricks": "databricks",
    "Stripe": "stripe",
    "Coinbase": "coinbase",
    "Robinhood": "robinhood",
    "DoorDash": "doordash",
    "Instacart": "instacart",
    "Roche": "roche",
    "Abbott": "abbott",
    "AMD": "amd",
    "Agilent Technologies": "agilent-technologies",
    "BAE Systems, Inc.": "bae-systems",
    "Honeywell": "honeywell",
    "Applied Materials": "applied-materials",
    "Entegris": "entegris",
    "KLA": "kla",
    "PayPal": "paypal",
    "Sila Nanotechnologies Inc.": "sila-nanotechnologies",
    "MacDermid Alpha Electronics Solutions": "macdermid-alpha-electronics-solutions",
    "Mariana Minerals": "mariana-minerals",
    "Arteris": "arteris",
    "Albertsons Companies": "albertsons",
    "Aya Healthcare": "aya-healthcare",
    "Benjamin Moore & Co.": "benjamin-moore-co",
    "Berkeley Lab": "lawrence-berkeley-national-laboratory",
    "Axtria - Ingenious Insights": "axtria",
    "Athos Therapeutics Inc": "athos-therapeutics",
    "Actemium Avanceon": "actemium-avanceon",
    "Amberoon Inc.": "amberoon-inc",
    "Accelon Inc.": "accelon-inc",
    "AdventHealth Central Florida": "adventhealth",
    "BD": "bd",
    "AC Wellness Medical Group @ Apple": "ac-wellness",
    "Atreya Innovations": "atreya-innovations",
    "Ayurvedamrut": "ayurvedamrut",
}

OUTPUT_FIELDS = [
    "Company",
    "Connection_Count",
    "SWE",
    "Data_Analyst",
    "Data_Engineer",
    "Data_Scientist_ML",
    "Total_Matched",
    "Recommended_Count",
    "Recommended_Titles",
    "Last_Scanned",
    "Scan_Notes",
]

# Order matters: more specific buckets first.
ROLE_BUCKETS: list[tuple[str, list[re.Pattern[str]]]] = [
    (
        "Data_Scientist_ML",
        [
            re.compile(p, re.I)
            for p in (
                r"data scientist",
                r"machine learning engineer",
                r"\bml engineer\b",
                r"\bai engineer\b",
                r"research scientist",
                r"applied scientist",
                r"deep learning",
            )
        ],
    ),
    (
        "Data_Engineer",
        [
            re.compile(p, re.I)
            for p in (
                r"data engineer",
                r"analytics engineer",
                r"\betl engineer\b",
                r"data platform",
                r"pipeline engineer",
                r"big data engineer",
            )
        ],
    ),
    (
        "Data_Analyst",
        [
            re.compile(p, re.I)
            for p in (
                r"data analyst",
                r"business intelligence",
                r"\bbi analyst\b",
                r"analytics analyst",
                r"reporting analyst",
                r"insights analyst",
            )
        ],
    ),
    (
        "SWE",
        [
            re.compile(p, re.I)
            for p in (
                r"software engineer",
                r"software developer",
                r"\bsde\b",
                r"\bswe\b",
                r"backend engineer",
                r"frontend engineer",
                r"full.?stack",
                r"platform engineer",
                r"applications engineer",
                r"member of technical staff",
                r"\bmtse\b",
                r"firmware engineer",
                r"embedded engineer",
            )
        ],
    ),
]

SENIOR_TITLE_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\bsenior\b",
        r"\bsr\.?\b",
        r"\bstaff\b",
        r"\bprincipal\b",
        r"\bdirector\b",
        r"\bvice president\b",
        r"\bvp\b",
        r"\bhead of\b",
        r"\bdistinguished\b",
        r"\bfellow\b",
        r"\barchitect\b",
        r"\bmanager\b",
        r"\btech lead\b",
        r"\bteam lead\b",
        r"\bleading\b",
    )
]


def is_senior_title(title: str) -> bool:
    normalized = title.strip()
    if not normalized:
        return False
    return any(p.search(normalized) for p in SENIOR_TITLE_PATTERNS)


def filter_non_senior_titles(titles: list[str], max_count: int = 6) -> tuple[list[str], int]:
    kept: list[str] = []
    skipped = 0

    for title in titles:
        if is_senior_title(title):
            skipped += 1
            continue
        kept.append(title)
        if len(kept) >= max_count:
            break

    return kept, skipped


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_company(name: str) -> str:
    normalized = name.split("·")[0].strip()
    normalized = re.sub(r"[\uF8FF\uE000-\uF8FF\s]+$", "", normalized).strip()
    return normalized


def company_to_slug(company: str) -> str:
    normalized = normalize_company(company)
    if normalized in COMPANY_SLUG_OVERRIDES:
        return COMPANY_SLUG_OVERRIDES[normalized]

    slug = normalized.lower()
    slug = slug.replace("'", "").replace("'", "")
    slug = re.sub(r"\([^)]*\)", " ", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def company_jobs_url(company: str) -> str:
    slug = company_to_slug(company)
    return f"https://www.linkedin.com/company/{slug}/jobs/"


def person_key(row: dict[str, str]) -> str:
    url = (row.get("URL") or "").strip().lower().rstrip("/")
    if url.startswith("http"):
        return url
    first = (row.get("First Name") or "").strip().lower()
    last = (row.get("Last Name") or "").strip().lower()
    return f"name:{first}|{last}"


def collect_connection_counts(csv_paths: list[Path]) -> dict[str, int]:
    company_people: dict[str, set[str]] = {}

    for path in csv_paths:
        if not path.exists():
            print(f"Warning: missing CSV {path}", file=sys.stderr)
            continue

        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                company = normalize_company(row.get("Company") or "")
                if not company:
                    continue
                company_people.setdefault(company, set()).add(person_key(row))

    return {company: len(keys) for company, keys in company_people.items()}


def classify_title(title: str) -> str | None:
    normalized = title.strip()
    if not normalized:
        return None

    for bucket, patterns in ROLE_BUCKETS:
        if any(p.search(normalized) for p in patterns):
            return bucket
    return None


def polite_sleep(base_delay: float, jitter: float = 0.35) -> None:
    spread = base_delay * jitter
    delay = base_delay + random.uniform(-spread, spread)
    time.sleep(max(delay, 1.0))


def clean_title(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def extract_titles_from_locator(locator, limit: int = 6) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()

    try:
        count = min(locator.count(), 20)
    except Exception:
        return titles

    for idx in range(count):
        try:
            card = locator.nth(idx)
            title = ""

            title_selectors = [
                ".job-card-list__title",
                ".base-search-card__title",
                "h3",
                "strong",
                "a[aria-label]",
            ]
            for selector in title_selectors:
                nested = card.locator(selector).first
                try:
                    if nested.count():
                        if selector == "a[aria-label]":
                            title = (nested.get_attribute("aria-label") or "").strip()
                        else:
                            title = nested.inner_text(timeout=800).strip()
                        if title:
                            break
                except Exception:
                    continue

            if not title:
                title = card.inner_text(timeout=800).strip().splitlines()[0].strip()

            title = clean_title(title)
            if title and title not in seen and len(title) > 2:
                seen.add(title)
                titles.append(title)
                if len(titles) >= limit:
                    break
        except Exception:
            continue

    return titles


def scrape_recommended_titles(page, company: str, delay_s: float) -> tuple[list[str], str]:
    url = company_jobs_url(company)
    notes: list[str] = []

    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(int(delay_s * 1000))

    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        page.wait_for_timeout(1200)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(800)
    except Exception:
        pass

    if vle.is_linkedin_login_page(page):
        return [], "login required"

    titles: list[str] = []
    seen: set[str] = set()

    # Strategy 1: find a heading like "Recommended for you" and grab nearby cards.
    heading_candidates = page.locator("h1, h2, h3, h4, span, div").filter(
        has_text=re.compile(r"recommended for you|recommended jobs|jobs you might be interested in", re.I)
    )

    try:
        heading_count = min(heading_candidates.count(), 5)
    except Exception:
        heading_count = 0

    for idx in range(heading_count):
        try:
            heading = heading_candidates.nth(idx)
            container = heading.locator("xpath=ancestor::section[1]")
            if container.count() == 0:
                container = heading.locator("xpath=ancestor::div[contains(@class,'jobs')][1]")

            if container.count() == 0:
                continue

            card_locators = [
                container.locator("li"),
                container.locator(".job-card-container"),
                container.locator(".base-card"),
                container.locator("article"),
            ]
            for cards in card_locators:
                extracted = extract_titles_from_locator(cards, limit=15)
                for title in extracted:
                    if title not in seen:
                        seen.add(title)
                        titles.append(title)
                if titles:
                    notes.append("carousel via recommended heading")
                    break
            if titles:
                break
        except Exception:
            continue

    # Strategy 2: semantic carousel / list regions on the company jobs page.
    if not titles:
        fallback_selectors = [
            "section:has-text('Recommended for you')",
            "section:has-text('Recommended jobs')",
            "[aria-label*='Recommended']",
            "[data-test-recommended-jobs]",
            ".org-jobs-recommended",
            ".jobs-company__jobs-list",
            ".org-jobs-job-search-form-module",
        ]
        for selector in fallback_selectors:
            try:
                region = page.locator(selector).first
                if region.count() == 0:
                    continue
                extracted = extract_titles_from_locator(
                    region.locator("li, article, .job-card-container, .base-card"),
                    limit=15,
                )
                for title in extracted:
                    if title not in seen:
                        seen.add(title)
                        titles.append(title)
                if titles:
                    notes.append(f"carousel via selector {selector}")
                    break
            except Exception:
                continue

    # Strategy 3: first visible job cards on the page (last resort).
    if not titles:
        for selector in (".job-card-list__title", ".base-search-card__title", "a.job-card-container__link"):
            try:
                loc = page.locator(selector)
                count = min(loc.count(), 15)
                for idx in range(count):
                    text = clean_title(loc.nth(idx).inner_text(timeout=800))
                    if text and text not in seen:
                        seen.add(text)
                        titles.append(text)
                if titles:
                    notes.append("fallback job cards on company jobs page")
                    break
            except Exception:
                continue

    if not titles:
        return [], "no recommended jobs found"

    return titles[:15], "; ".join(notes) if notes else "ok"


def load_existing_results(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    with path.open(newline="", encoding="utf-8") as f:
        return {row["Company"]: row for row in csv.DictReader(f) if row.get("Company")}


def write_results(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in OUTPUT_FIELDS})


def build_scan_list(
    companies: list[str],
    connection_counts: dict[str, int],
    all_companies: bool,
) -> list[tuple[str, int]]:
    if all_companies:
        items = sorted(connection_counts.items(), key=lambda x: (-x[1], x[0].lower()))
        return items

    result: list[tuple[str, int]] = []
    for company in companies:
        result.append((company, connection_counts.get(company, 0)))
    return result


def prepare_scan_queue(
    company_items: list[tuple[str, int]],
    existing: dict[str, dict[str, str]],
    resume: bool,
    limit: int | None,
    force: bool,
) -> list[tuple[str, int]]:
    queue = list(company_items)

    if resume and not force:
        queue = [
            (company, count)
            for company, count in queue
            if company not in existing or not existing[company].get("Last_Scanned")
        ]

    if limit is not None:
        queue = queue[:limit]

    return queue


def scan_company(
    page,
    company: str,
    connection_count: int,
    linkedin_email: str | None,
    linkedin_password: str | None,
    allow_manual_login: bool,
    delay_s: float,
) -> dict[str, str]:
    vle.login_if_needed(page, linkedin_email, linkedin_password, allow_manual_login)

    titles, notes = scrape_recommended_titles(page, company, delay_s)
    titles, senior_skipped = filter_non_senior_titles(titles)

    if senior_skipped:
        notes = f"{notes}; filtered {senior_skipped} senior role(s)" if notes else f"filtered {senior_skipped} senior role(s)"

    bucket_counts = {bucket: 0 for bucket, _ in ROLE_BUCKETS}

    for title in titles:
        bucket = classify_title(title)
        if bucket:
            bucket_counts[bucket] += 1

    total_matched = sum(bucket_counts.values())

    return {
        "Company": company,
        "Connection_Count": str(connection_count),
        "SWE": str(bucket_counts["SWE"]),
        "Data_Analyst": str(bucket_counts["Data_Analyst"]),
        "Data_Engineer": str(bucket_counts["Data_Engineer"]),
        "Data_Scientist_ML": str(bucket_counts["Data_Scientist_ML"]),
        "Total_Matched": str(total_matched),
        "Recommended_Count": str(len(titles)),
        "Recommended_Titles": " | ".join(titles),
        "Last_Scanned": utc_now_iso(),
        "Scan_Notes": notes,
    }


def scan_companies(
    company_items: list[tuple[str, int]],
    output_csv: Path,
    profile_dir: Path,
    browser_channel: str | None,
    linkedin_email: str | None,
    linkedin_password: str | None,
    allow_manual_login: bool,
    headless: bool,
    delay_s: float,
    limit: int | None,
    resume: bool,
    force: bool,
) -> None:
    existing = load_existing_results(output_csv)
    results_by_company = dict(existing)

    company_items = prepare_scan_queue(company_items, existing, resume, limit, force)
    if not company_items:
        print("No companies left to scan.")
        return

    print(f"Scanning {len(company_items)} companies this run.")

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel=browser_channel,
            headless=headless,
            viewport={"width": 1360, "height": 900},
        )
        page = context.new_page()

        vle.ensure_linkedin_authenticated(
            page,
            linkedin_email,
            linkedin_password,
            allow_manual_login,
        )

        scanned = 0
        total = len(company_items)

        for idx, (company, connection_count) in enumerate(company_items, start=1):
            print(f"[{idx}/{total}] Scanning {company} ({connection_count} connections)")

            try:
                row = scan_company(
                    page,
                    company,
                    connection_count,
                    linkedin_email,
                    linkedin_password,
                    allow_manual_login,
                    delay_s,
                )
            except Exception as exc:
                row = {
                    "Company": company,
                    "Connection_Count": str(connection_count),
                    "SWE": "",
                    "Data_Analyst": "",
                    "Data_Engineer": "",
                    "Data_Scientist_ML": "",
                    "Total_Matched": "",
                    "Recommended_Count": "0",
                    "Recommended_Titles": "",
                    "Last_Scanned": utc_now_iso(),
                    "Scan_Notes": f"error: {exc}",
                }

            results_by_company[company] = row
            scanned += 1

            ordered_rows = [
                results_by_company[name]
                for name in sorted(results_by_company.keys(), key=str.lower)
            ]
            write_results(output_csv, ordered_rows)

            print(
                f"    recommended={row['Recommended_Count']} | "
                f"SWE={row['SWE'] or '0'} | DA={row['Data_Analyst'] or '0'} | "
                f"DE={row['Data_Engineer'] or '0'} | DS/ML={row['Data_Scientist_ML'] or '0'} | "
                f"matched={row['Total_Matched'] or '0'}"
            )

            polite_sleep(delay_s)

        context.close()

    print(f"\nScanned {scanned} companies.")
    print(f"Wrote {len(results_by_company)} rows to: {output_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan LinkedIn recommended jobs from company /jobs pages."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output CSV path",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path(".playwright-linkedin-profile"),
        help="Persistent Playwright profile directory",
    )
    parser.add_argument(
        "--browser-channel",
        default="chrome",
        help="Browser channel (default: chrome)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help=".env file path",
    )
    parser.add_argument(
        "--linkedin-email",
        default=None,
        help="LinkedIn email",
    )
    parser.add_argument(
        "--linkedin-password",
        default=None,
        help="LinkedIn password",
    )
    parser.add_argument(
        "--allow-manual-login",
        action="store_true",
        help="Allow manual login in browser",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run browser headlessly (default: true)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Delay in seconds between companies (default: 5.0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Scan at most N companies from the remaining queue (after --resume filtering)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip companies already present in the output CSV",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rescan companies even if they already exist in the output CSV",
    )
    parser.add_argument(
        "--all-companies",
        action="store_true",
        help="Scan all companies from connection CSVs (for batch runs)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        env_values = vle.load_env_file(args.env_file)

        linkedin_email = (
            args.linkedin_email
            or os.getenv("LINKEDIN_EMAIL")
            or env_values.get("LINKEDIN_EMAIL")
            or vle.HARDCODED_LINKEDIN_EMAIL
            or None
        )

        linkedin_password = (
            args.linkedin_password
            or os.getenv("LINKEDIN_PASSWORD")
            or env_values.get("LINKEDIN_PASSWORD")
            or vle.HARDCODED_LINKEDIN_PASSWORD
            or None
        )

        if linkedin_email and not linkedin_password:
            linkedin_password = getpass.getpass("LinkedIn password: ")

        if linkedin_password and not linkedin_email:
            linkedin_email = input("LinkedIn email: ").strip()

        connection_counts = collect_connection_counts(CONNECTION_CSVS)
        company_items = build_scan_list(
            TOP_COMPANIES,
            connection_counts,
            args.all_companies,
        )

        if not company_items:
            raise ValueError("No companies to scan.")

        label = "all connection companies" if args.all_companies else "top company list"
        print(f"Prepared {len(company_items)} companies from {label}.")
        print(f"Headless={args.headless}, delay={args.delay}s")

        scan_companies(
            company_items=company_items,
            output_csv=args.output,
            profile_dir=args.profile_dir,
            browser_channel=(args.browser_channel or None),
            linkedin_email=linkedin_email,
            linkedin_password=linkedin_password,
            allow_manual_login=args.allow_manual_login,
            headless=args.headless,
            delay_s=args.delay,
            limit=args.limit,
            resume=args.resume,
            force=args.force,
        )

        return 0

    except KeyboardInterrupt:
        print("\nStopped by user. Partial results were saved.")
        return 130

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
