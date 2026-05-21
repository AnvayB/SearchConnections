#!/usr/bin/env python3
"""
Verify LinkedIn company URLs from connection profile experience pages.

For each unique company, visits a connection's /details/experience/ page,
finds an experience entry matching that company, and saves the canonical
linkedin.com/company/... href to updated_data/company_linkedin_urls.csv.

Personal-use only. Requires LinkedIn login. Uses conservative delays.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

import verify_linkedin_employment as vle
from scan_company_jobs import (
    CONNECTION_CSVS,
    TOP_COMPANIES,
    normalize_company,
    polite_sleep,
)


DEFAULT_OUTPUT = Path("updated_data/company_linkedin_urls.csv")

OUTPUT_FIELDS = [
    "Company",
    "LinkedIn_URL",
]

LINKEDIN_COMPANY_RE = re.compile(
    r"https?://(?:[a-z0-9-]+\.)?linkedin\.com/company/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)

EXPERIENCE_ITEM_SELECTORS = [
    "main .pvs-list__paged-list-item",
    "main li.pvs-list__paged-list-item",
    "main ul.pvs-list > li",
    "main li.artdeco-list__item",
]


def linkedin_company_url_from_href(href: str) -> str | None:
    if not href:
        return None

    if href.startswith("/"):
        href = f"https://www.linkedin.com{href}"

    match = LINKEDIN_COMPANY_RE.search(href)
    if not match:
        return None

    slug = match.group(1).strip("/")
    if not slug or slug.lower() in {"login", "signup", "search"}:
        return None

    return f"https://www.linkedin.com/company/{slug}/"


def companies_match(target: str, found: str) -> bool:
    a = normalize_company(target).lower()
    b = normalize_company(found).lower()
    if not a or not b:
        return False
    if a == b:
        return True
    return a in b or b in a


def extract_company_name_from_entry_text(text: str) -> str:
    lines = vle.clean_lines(text)

    for i, line in enumerate(lines):
        date_match = vle.DATE_RANGE_RE.search(line)
        if not date_match:
            continue

        non_noise: list[str] = []
        noise_skipped = False
        j = i - 1
        while j >= 0 and len(non_noise) < 2:
            candidate = lines[j].strip()
            if vle.DATE_RANGE_RE.search(candidate):
                break
            if vle.is_noise_line(candidate):
                noise_skipped = True
            else:
                non_noise.append(candidate)
            j -= 1

        if len(non_noise) >= 2:
            if noise_skipped:
                company = non_noise[1].split("·")[0].strip()
            else:
                company = non_noise[0].split("·")[0].strip()
        elif len(non_noise) == 1:
            company = non_noise[0].split("·")[0].strip()
        else:
            continue

        if company:
            return company

    return ""


def extract_company_href_from_entry(entry) -> str:
    for selector in ('a[href*="/company/"]', 'a[href*="linkedin.com/company/"]'):
        locator = entry.locator(selector)
        try:
            count = min(locator.count(), 5)
        except Exception:
            continue

        for idx in range(count):
            try:
                href = locator.nth(idx).get_attribute("href") or ""
                url = linkedin_company_url_from_href(href)
                if url:
                    return url
            except Exception:
                continue

    return ""


def extract_company_link_from_experience(page, target_company: str) -> tuple[str, str]:
    for selector in EXPERIENCE_ITEM_SELECTORS:
        entries = page.locator(selector)
        try:
            count = min(entries.count(), 30)
        except Exception:
            count = 0

        if count == 0:
            continue

        for idx in range(count):
            entry = entries.nth(idx)
            try:
                text = entry.inner_text(timeout=2000)
            except Exception:
                continue

            company_name = extract_company_name_from_entry_text(text)
            if not company_name or not companies_match(target_company, company_name):
                continue

            url = extract_company_href_from_entry(entry)
            if url:
                return url, f"matched {company_name}"

        break

    return "", "no matching experience with company link"


def load_experience_page(
    page,
    profile_url: str,
    linkedin_email: str | None,
    linkedin_password: str | None,
    allow_manual_login: bool,
) -> None:
    exp_url = vle.profile_experience_url(profile_url)

    page.goto(exp_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)

    vle.login_if_needed(page, linkedin_email, linkedin_password, allow_manual_login)

    if page.url.rstrip("/") != exp_url.rstrip("/"):
        page.goto(exp_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1000)


def build_company_items(
    csv_paths: list[Path],
    top_companies: list[str],
    all_companies: bool,
) -> list[tuple[str, int]]:
    profiles = build_company_profiles(csv_paths)

    def connection_count(company: str) -> int:
        target = normalize_company(company)
        seen: set[str] = set()

        for path in csv_paths:
            if not path.exists():
                continue
            with path.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    row_company = normalize_company(row.get("Company") or "")
                    if row_company != target:
                        continue
                    url = (row.get("URL") or "").strip().lower().rstrip("/")
                    if url.startswith("http"):
                        seen.add(url)
                    else:
                        first = (row.get("First Name") or "").strip().lower()
                        last = (row.get("Last Name") or "").strip().lower()
                        seen.add(f"name:{first}|{last}")

        return len(seen)

    if all_companies:
        items = [(company, connection_count(company)) for company in profiles]
        items.sort(key=lambda item: (-item[1], item[0].lower()))
        return items

    return [(company, connection_count(company)) for company in top_companies]


def build_company_profiles(csv_paths: list[Path]) -> dict[str, list[str]]:
    profiles: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}

    for path in csv_paths:
        if not path.exists():
            print(f"Warning: missing CSV {path}", file=sys.stderr)
            continue

        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                company = (row.get("Company") or "").strip()
                url = (row.get("URL") or "").strip().rstrip("/")
                if not company or not url.startswith("http"):
                    continue

                profiles.setdefault(company, [])
                seen.setdefault(company, set())
                if url not in seen[company]:
                    seen[company].add(url)
                    profiles[company].append(url)

    return profiles


def load_existing_results(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    with path.open(newline="", encoding="utf-8") as f:
        return {row["Company"]: row for row in csv.DictReader(f) if row.get("Company")}


def has_linkedin_url(row: dict[str, str]) -> bool:
    return bool((row.get("LinkedIn_URL") or "").strip())


def prepare_verify_queue(
    company_items: list[tuple[str, int]],
    existing: dict[str, dict[str, str]],
    resume: bool,
    limit: int | None,
    force: bool,
    retry_empty: bool = False,
) -> list[tuple[str, int]]:
    queue = list(company_items)

    if force:
        pass
    elif retry_empty:
        queue = [
            (company, count)
            for company, count in queue
            if company in existing and not has_linkedin_url(existing[company])
        ]
    elif resume:
        queue = [
            (company, count)
            for company, count in queue
            if company not in existing or not has_linkedin_url(existing[company])
        ]
    else:
        queue = [
            (company, count)
            for company, count in queue
            if company not in existing
        ]

    if limit is not None:
        queue = queue[:limit]

    return queue


def write_results(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in OUTPUT_FIELDS})


def verify_company_via_profiles(
    page,
    company: str,
    profile_urls: list[str],
    linkedin_email: str | None,
    linkedin_password: str | None,
    allow_manual_login: bool,
) -> dict[str, str]:
    notes: list[str] = []

    for profile_url in profile_urls:
        try:
            load_experience_page(
                page,
                profile_url,
                linkedin_email,
                linkedin_password,
                allow_manual_login,
            )

            if vle.is_linkedin_login_page(page):
                return {
                    "Company": company,
                    "LinkedIn_URL": "",
                    "_notes": "login required",
                }

            linkedin_url, entry_note = extract_company_link_from_experience(page, company)
            if linkedin_url:
                notes.append(f"{profile_url}: {entry_note}")
                return {
                    "Company": company,
                    "LinkedIn_URL": linkedin_url,
                    "_notes": "; ".join(notes),
                }

            notes.append(f"{profile_url}: {entry_note}")
        except Exception as exc:
            notes.append(f"{profile_url}: error: {exc}")

    return {
        "Company": company,
        "LinkedIn_URL": "",
        "_notes": "; ".join(notes) if notes else "no profiles",
    }


def verify_companies(
    company_items: list[tuple[str, int]],
    company_profiles: dict[str, list[str]],
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
    retry_empty: bool,
) -> None:
    existing = load_existing_results(output_csv)
    results_by_company = dict(existing)

    company_items = prepare_verify_queue(
        company_items, existing, resume, limit, force, retry_empty
    )
    if not company_items:
        print("No companies left to verify.")
        return

    print(f"Verifying LinkedIn URLs for {len(company_items)} companies this run.")

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
            profile_urls = company_profiles.get(company, [])
            print(
                f"[{idx}/{total}] Verifying {company} "
                f"({connection_count} connections, {len(profile_urls)} profiles)"
            )

            if not profile_urls:
                row = {"Company": company, "LinkedIn_URL": ""}
                notes = "no profile URLs in connection CSVs"
            else:
                try:
                    row = verify_company_via_profiles(
                        page,
                        company,
                        profile_urls,
                        linkedin_email,
                        linkedin_password,
                        allow_manual_login,
                    )
                    notes = row.pop("_notes", "")
                except Exception as exc:
                    row = {"Company": company, "LinkedIn_URL": ""}
                    notes = f"error: {exc}"

            results_by_company[company] = row
            scanned += 1

            ordered_rows = [
                results_by_company[name]
                for name in sorted(results_by_company.keys(), key=str.lower)
            ]
            write_results(output_csv, ordered_rows)

            url_display = row["LinkedIn_URL"] or "(not found)"
            print(f"    url={url_display} | {notes or 'ok'}")

            polite_sleep(delay_s)

        context.close()

    print(f"\nVerified {scanned} companies.")
    print(f"Wrote {len(results_by_company)} rows to: {output_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify LinkedIn company URLs from connection profile experience pages."
        )
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
        help="Verify at most N companies from the remaining queue",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip companies that already have a non-empty LinkedIn_URL in the CSV",
    )
    parser.add_argument(
        "--retry-empty",
        action="store_true",
        help="Only verify companies already in the CSV with an empty LinkedIn_URL",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-verify companies even if LinkedIn_URL is already populated",
    )
    parser.add_argument(
        "--all-companies",
        action="store_true",
        help="Verify all companies from connection CSVs (for batch runs)",
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

        company_profiles = build_company_profiles(CONNECTION_CSVS)
        company_items = build_company_items(
            CONNECTION_CSVS,
            TOP_COMPANIES,
            args.all_companies,
        )

        if not company_items:
            raise ValueError("No companies to verify.")

        label = "all connection companies" if args.all_companies else "top company list"
        print(f"Prepared {len(company_items)} companies from {label}.")
        print(f"Headless={args.headless}, delay={args.delay}s")

        verify_companies(
            company_items=company_items,
            company_profiles=company_profiles,
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
            retry_empty=args.retry_empty,
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
