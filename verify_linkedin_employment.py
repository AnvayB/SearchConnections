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


DATE_RANGE_RE = re.compile(
    r"\b"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+)?"  # optional month
    r"\d{4}"
    r"\s*[-\u2013]\s*"
    r"(?:Present|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+)?\d{4})"
    r"\b",
    re.IGNORECASE,
)

EMPLOYMENT_TYPE_KEYWORDS = frozenset({
    "full-time", "part-time", "contract", "freelance", "self-employed",
    "internship", "temporary", "seasonal", "apprenticeship",
    "on-site", "remote", "hybrid",
})

DURATION_ONLY_RE = re.compile(
    r"^\d+\s+(yr|yrs|year|years|mo|mos|month|months)"
    r"(\s+\d+\s+(mo|mos|month|months))?\s*$",
    re.IGNORECASE,
)

# LinkedIn sometimes uses non-ASCII hyphens (e.g. U+2011 non-breaking hyphen)
# in strings like "Full‑time". Normalise before keyword lookup.
_UNICODE_DASH_RE = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")

# Location lines (e.g. "Fresno, California, United States") should be skipped
# just like employment-type or duration-only lines.
_KNOWN_GEO_SUFFIXES = frozenset({
    "united states", "canada", "united kingdom", "india", "australia",
    "germany", "france", "singapore", "netherlands", "ireland",
    "pakistan", "area",
})

HARDCODED_LINKEDIN_EMAIL = ""
HARDCODED_LINKEDIN_PASSWORD = ""


def clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def is_noise_line(line: str) -> bool:
    # Normalise non-ASCII dashes (LinkedIn uses U+2011 non-breaking hyphen, etc.)
    normalised = _UNICODE_DASH_RE.sub("-", line.strip()).lower()
    # Also inspect only the segment before any · separator.
    # This catches compound group-header lines like "Full-time · 4 yrs 10 mos"
    # where just the primary part is an employment-type keyword.
    primary = normalised.split("·")[0].strip()
    if normalised in EMPLOYMENT_TYPE_KEYWORDS or primary in EMPLOYMENT_TYPE_KEYWORDS:
        return True
    if DURATION_ONLY_RE.match(normalised):
        return True
    # Location lines like "Fresno, California, United States"
    if any(normalised.endswith(suffix) for suffix in _KNOWN_GEO_SUFFIXES):
        return True
    return False


def profile_experience_url(profile_url: str) -> str:
    cleaned = profile_url.strip().split("?", 1)[0].rstrip("/")
    return f"{cleaned}/details/experience/"


def extract_top_experience(page) -> dict | None:
    """
    Attempts to extract:
    - title
    - company
    - date range
    - current employment status

    Uses lightweight text heuristics.
    """

    selectors = [
        "main",
        "body",
    ]

    for selector in selectors:
        try:
            text = page.locator(selector).first.inner_text(timeout=5000)
            lines = clean_lines(text)

            for i, line in enumerate(lines):
                date_match = DATE_RANGE_RE.search(line)

                if not date_match:
                    continue

                date_range = date_match.group(0)

                # Walk backward from the date line, collecting the first two
                # non-noise, non-date lines. Track whether any noise was skipped.
                #
                # LinkedIn renders two layouts:
                #   Simple entry  → Title, Company, Date  (no noise)
                #   Grouped entry → Company (header), [duration noise], Title,
                #                   [employment-type noise], Date
                #
                # When no noise is skipped: non_noise[0]=company, [1]=title
                # When noise was skipped:   non_noise[0]=title,   [1]=company
                non_noise: list[str] = []
                noise_skipped = False
                j = i - 1
                while j >= 0 and len(non_noise) < 2:
                    candidate = lines[j].strip()
                    if DATE_RANGE_RE.search(candidate):
                        break
                    if is_noise_line(candidate):
                        noise_skipped = True
                    else:
                        non_noise.append(candidate)
                    j -= 1

                if len(non_noise) >= 2:
                    if noise_skipped:
                        title   = non_noise[0].split("·")[0].strip()
                        company = non_noise[1].split("·")[0].strip()
                    else:
                        company = non_noise[0].split("·")[0].strip()
                        title   = non_noise[1].split("·")[0].strip()
                elif len(non_noise) == 1:
                    company = non_noise[0].split("·")[0].strip()
                    title   = ""
                else:
                    continue

                return {
                    "title": title,
                    "company": company,
                    "date_range": date_range.strip(),
                    "is_current": "present" in date_range.lower(),
                }

        except PlaywrightTimeoutError:
            continue
        except Exception as exc:
            print(f"extract_top_experience error: {exc}")

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
) -> None:

    with input_csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

        if not rows:
            raise ValueError("Input CSV has no rows.")

        fieldnames = list(rows[0].keys())

    if "Still_Employed" not in fieldnames:
        fieldnames.append("Still_Employed")

    if "Employment_Changed" not in fieldnames:
        fieldnames.append("Employment_Changed")

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

            if not url.startswith("http"):
                row["Still_Employed"] = "No"

                print(f"[{idx}] {full_name}: missing profile URL -> No")

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

                if not experience:
                    row["Still_Employed"] = "No"

                    print("    Could not extract experience.")

                else:
                    current_company_raw = experience["company"]
                    current_company = (
                        current_company_raw
                        .split("·")[0]
                        .strip()
                    )
                    current_title = experience["title"]
                    current_dates = experience["date_range"]

                    csv_company = (
                        (row.get("Company") or "")
                        .split("·")[0]
                        .strip()
                    )

                    print(f"    Current Company: {current_company}")
                    print(f"    Current Title: {current_title}")
                    print(f"    Current Dates: {current_dates}")

                    if not experience["is_current"]:
                        row["Still_Employed"] = "No"

                        print("    No current employment found.")

                    else:
                        row["Still_Employed"] = ""

                        if (
                            csv_company.lower()
                            != current_company.lower()
                        ):
                            print("    Employment changed detected.")

                            print(f"       OLD: {csv_company}")
                            print(f"       NEW: {current_company}")

                            row["Company"] = current_company

                            if "Position" in row:
                                row["Position"] = current_title

                            if "Title" in row:
                                row["Title"] = current_title

                            if "Start_Date" in row:
                                row["Start_Date"] = (
                                    current_dates.split("-")[0].strip()
                                )

                            row["Employment_Changed"] = "Yes"

                        else:
                            row["Employment_Changed"] = ""

                checked += 1

                time.sleep(delay_s)

            except Exception as exc:
                row["Still_Employed"] = "No"

                print(f"    Error: {exc}")

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