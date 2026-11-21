#!/usr/bin/env python3
"""
Verify and update LinkedIn employment information.

New behavior:
- Opens LinkedIn Experience page
- Extracts MOST RECENT experience entry
- Checks whether current role is still active ("Present")
- Compares extracted company against CSV company
- Updates:
    - Company
    - Position
    - Start_Date
- Adds:
    - Still_Employed
    - Employment_Changed

Rules:
- If no current role exists:
    Still_Employed = "No"

- If current role exists at SAME company:
    Still_Employed = ""
    Employment_Changed = ""

- If current role exists at DIFFERENT company:
    Still_Employed = ""
    Employment_Changed = "Yes"
    Update Company / Position / Start_Date
"""

from __future__ import annotations

import argparse
import csv
import getpass
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


# Parsing/validation lives in employment_parse.py (no Playwright dependency, so it
# can be unit tested offline). Names are re-exported here because
# scan_company_jobs.py and verify_company_linkedin_links.py use them via `vle.`.
from employment_parse import (  # noqa: F401
    DATE_RANGE_RE,
    DURATION_ONLY_RE,
    EMPLOYMENT_TYPE_KEYWORDS,
    EXTRA_COLUMNS,
    apply_experience_to_row,
    clean_lines,
    is_noise_line,
    looks_like_valid_company,
    normalize_company,
    parse_experience_text,
)

HARDCODED_LINKEDIN_EMAIL = ""
HARDCODED_LINKEDIN_PASSWORD = ""


def profile_experience_url(profile_url: str) -> str:
    cleaned = profile_url.strip().split("?", 1)[0].rstrip("/")
    return f"{cleaned}/details/experience/"


def extract_top_experience(page) -> dict | None:
    """
    Read the page text and parse the most recent experience entry.
    The line-walking logic is in employment_parse.parse_experience_text().
    """
    for selector in ("main", "body"):
        try:
            text = page.locator(selector).first.inner_text(timeout=5000)
        except PlaywrightTimeoutError:
            continue
        except Exception as exc:
            print(f"extract_top_experience error: {exc}")
            continue

        entry = parse_experience_text(text)
        if entry:
            return entry

    return None


def is_linkedin_login_page(page) -> bool:
    current_url = page.url.lower()
    return "linkedin.com/login" in current_url or "checkpoint" in current_url


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)

        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        values[key] = value

    return values


def first_visible_locator(page, selectors: list[str]):
    for selector in selectors:
        candidate = page.locator(selector).first

        try:
            if candidate.count() and candidate.is_visible():
                return candidate
        except Exception:
            continue

    return None


def login_if_needed(page, email: str | None, password: str | None, allow_manual_login: bool) -> None:
    if not is_linkedin_login_page(page):
        return

    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass

    if email and password:
        email_selectors = [
            "#username",
            "input[name='session_key']",
            "input[type='email']",
            "input[autocomplete='username']",
        ]

        password_selectors = [
            "#password",
            "input[name='session_password']",
            "input[type='password']",
            "input[autocomplete='current-password']",
        ]

        sign_in_selectors = [
            "button[type='submit']",
            "button:has-text('Sign in')",
            "button:has-text('Continue')",
            "button:has-text('Log in')",
        ]

        email_field = first_visible_locator(page, email_selectors)
        password_field = first_visible_locator(page, password_selectors)

        if email_field is None or password_field is None:
            prelogin_click_selectors = [
                "a:has-text('Sign in')",
                "button:has-text('Sign in')",
                "a:has-text('Log in')",
                "button:has-text('Log in')",
            ]

            prelogin_btn = first_visible_locator(page, prelogin_click_selectors)

            if prelogin_btn is not None:
                prelogin_btn.click()
                page.wait_for_timeout(1200)

                email_field = first_visible_locator(page, email_selectors)
                password_field = first_visible_locator(page, password_selectors)

        if email_field is None or password_field is None:
            if allow_manual_login or sys.stdin.isatty():
                print(
                    "Could not find LinkedIn login fields automatically. "
                    "Please complete login manually in browser and press Enter."
                )

                input()

                page.wait_for_timeout(1000)

                if is_linkedin_login_page(page):
                    raise RuntimeError("Still on login page after manual login.")

                return

            raise RuntimeError(
                f"Login page detected but fields could not be found. URL={page.url}"
            )

        email_field.fill(email)
        password_field.fill(password)

        clicked = False

        for selector in sign_in_selectors:
            btn = first_visible_locator(page, [selector])

            if btn is not None:
                btn.click()
                clicked = True
                break

        if not clicked:
            password_field.press("Enter")

        page.wait_for_timeout(2500)

        if is_linkedin_login_page(page):
            raise RuntimeError("LinkedIn login failed.")

        return

    if allow_manual_login:
        print("Login required. Complete login in browser and press Enter.")
        input()

        page.wait_for_timeout(800)

        if is_linkedin_login_page(page):
            raise RuntimeError("Still on login page after manual login.")

        return

    raise RuntimeError(
        "LinkedIn authentication required. "
        "Provide credentials or use --allow-manual-login."
    )


def ensure_linkedin_authenticated(
    page,
    email: str | None,
    password: str | None,
    allow_manual_login: bool,
) -> None:
    page.goto(
        "https://www.linkedin.com/login",
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1000)

    if is_linkedin_login_page(page):
        login_if_needed(page, email, password, allow_manual_login)

    page.goto(
        "https://www.linkedin.com/feed/",
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1000)

    if is_linkedin_login_page(page):
        raise RuntimeError("Could not authenticate LinkedIn session.")


def process_csv(
    input_csv: Path,
    output_csv: Path,
    profile_dir: Path,
    browser_channel: str | None,
    linkedin_email: str | None,
    linkedin_password: str | None,
    allow_manual_login: bool,
    headless: bool,
    delay_s: float,
    limit: int | None,
    only_still_no: bool = False,
) -> None:

    with input_csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

        if not rows:
            raise ValueError("Input CSV has no rows.")

        fieldnames = list(rows[0].keys())

    for column in EXTRA_COLUMNS:
        if column not in fieldnames:
            fieldnames.append(column)

    checked = 0

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel=browser_channel,
            headless=headless,
            viewport={"width": 1360, "height": 900},
        )

        page = context.new_page()

        ensure_linkedin_authenticated(
            page,
            linkedin_email,
            linkedin_password,
            allow_manual_login,
        )

        for idx, row in enumerate(rows, start=1):

            if limit is not None and checked >= limit:
                break

            url = (row.get("URL") or "").strip()

            full_name = (
                f"{row.get('First Name', '').strip()} "
                f"{row.get('Last Name', '').strip()}"
            ).strip()

            if only_still_no and row.get("Still_Employed") != "No":
                continue

            if (row.get("Hidden") or "").strip().lower() in ("yes", "true", "1"):
                continue  # deliberately hidden from the site; no need to re-check

            if not url.startswith("http"):
                # A missing URL says nothing about employment; leave the row alone.
                print(f"[{idx}] {full_name}: missing profile URL, skipped")

                checked += 1
                continue

            print(f"[{idx}] Checking {full_name}")

            try:
                exp_url = profile_experience_url(url)

                page.goto(
                    exp_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                page.wait_for_timeout(1500)

                login_if_needed(
                    page,
                    linkedin_email,
                    linkedin_password,
                    allow_manual_login,
                )

                if page.url != exp_url:
                    page.goto(
                        exp_url,
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )

                    page.wait_for_timeout(1000)

                experience = extract_top_experience(page)

                if experience:
                    print(f"    Current Company: {experience['company']}")
                    print(f"    Current Title: {experience['title']}")
                    print(f"    Current Dates: {experience['date_range']}")

                old_company = row.get("Company") or ""
                status = apply_experience_to_row(row, experience)

                if status == "no-extract":
                    print("    Could not extract experience; row left unchanged.")
                elif status == "not-current":
                    print("    No current employment found.")
                elif status == "unknown-company":
                    print("    Current role found but company unreadable; row left unchanged.")
                elif status == "changed":
                    print("    Employment changed.")
                    print(f"       OLD: {old_company}")
                    print(f"       NEW: {row.get('Company')}")
                elif status == "review":
                    print("    New company does not look like an employer; Company NOT changed.")
                    print(f"       KEPT:    {old_company}")
                    print(f"       SCRAPED: {row.get('Scraped_Company')}  (flagged Review)")

                checked += 1

                time.sleep(delay_s)

            except Exception as exc:
                # An error (timeout, login wall, layout change) is not evidence
                # that the person left their job, so the row is left unchanged.
                print(f"    Error: {exc}; row left unchanged.")

                checked += 1

        context.close()

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to: {output_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify and update LinkedIn employment data."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/bilwa-connections.csv"),
        help="Input CSV path",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("updated_data/bilwa-connections_updated.csv"),
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
        action="store_true",
        help="Run browser headlessly",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=2.5,
        help="Delay between profiles",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process first N rows",
    )

    parser.add_argument(
        "--recheck-no",
        action="store_true",
        help=(
            "Only re-verify rows currently marked Still_Employed=No (use the "
            "already-updated CSV as --input/--output). Fixes false 'No' values "
            "written by earlier runs that treated errors as 'left the job'."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        env_values = load_env_file(args.env_file)

        linkedin_email = (
            args.linkedin_email
            or os.getenv("LINKEDIN_EMAIL")
            or env_values.get("LINKEDIN_EMAIL")
            or HARDCODED_LINKEDIN_EMAIL
            or None
        )

        linkedin_password = (
            args.linkedin_password
            or os.getenv("LINKEDIN_PASSWORD")
            or env_values.get("LINKEDIN_PASSWORD")
            or HARDCODED_LINKEDIN_PASSWORD
            or None
        )

        if linkedin_email and not linkedin_password:
            linkedin_password = getpass.getpass("LinkedIn password: ")

        if linkedin_password and not linkedin_email:
            linkedin_email = input("LinkedIn email: ").strip()

        process_csv(
            input_csv=args.input,
            output_csv=args.output,
            profile_dir=args.profile_dir,
            browser_channel=(args.browser_channel or None),
            linkedin_email=linkedin_email,
            linkedin_password=linkedin_password,
            allow_manual_login=args.allow_manual_login,
            headless=args.headless,
            delay_s=args.delay,
            limit=args.limit,
            only_still_no=args.recheck_no,
        )

        return 0

    except KeyboardInterrupt:
        print("\nStopped by user.")
        return 130

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())