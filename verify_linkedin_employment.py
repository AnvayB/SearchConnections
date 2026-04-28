#!/usr/bin/env python3
"""
Verify current employment for LinkedIn connection rows.

Rule implemented:
- If the top Experience date range does NOT contain "Present", set Still_Employed = "No".
- Otherwise leave Still_Employed blank.
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
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s*-\s*(?:Present|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})\b",
    re.IGNORECASE,
)

# Optional fallback credentials (least preferred). Leave blank unless needed.
HARDCODED_LINKEDIN_EMAIL = ""
HARDCODED_LINKEDIN_PASSWORD = ""


def clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def profile_experience_url(profile_url: str) -> str:
    cleaned = profile_url.strip().split("?", 1)[0].rstrip("/")
    return f"{cleaned}/details/experience/"


def extract_top_experience_date(page) -> str | None:
    selectors = [
        "main",
        "body",
    ]
    for selector in selectors:
        try:
            text = page.locator(selector).first.inner_text(timeout=5000)
            for line in clean_lines(text):
                match = DATE_RANGE_RE.search(line)
                if match:
                    return match.group(0)
        except PlaywrightTimeoutError:
            continue
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
        # Some pages never reach full idle due to trackers; continue with best effort.
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
            # LinkedIn sometimes lands on a variant page with a second "Sign in" action before fields appear.
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
                    "Please complete login manually in the browser, then press Enter."
                )
                input()
                page.wait_for_timeout(1000)
                if is_linkedin_login_page(page):
                    raise RuntimeError("Still on login page after manual login.")
                return
            raise RuntimeError(
                f"Login page detected but could not find login fields. URL={page.url}"
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
            raise RuntimeError("LinkedIn login failed or requires additional verification.")
        return

    if allow_manual_login:
        print("Login required. Please complete LinkedIn login in the opened browser window, then press Enter.")
        input()
        page.wait_for_timeout(800)
        if is_linkedin_login_page(page):
            raise RuntimeError("Still on login page after manual login.")
        return

    raise RuntimeError(
        "LinkedIn authentication required. Provide credentials via .env/env vars, "
        "or run with --allow-manual-login."
    )


def ensure_linkedin_authenticated(page, email: str | None, password: str | None, allow_manual_login: bool) -> None:
    # Proactively hit LinkedIn login so credential-based auth runs before row processing.
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1000)

    if is_linkedin_login_page(page):
        login_if_needed(page, email, password, allow_manual_login)

    # Final sanity check: go to feed and ensure we are not bounced back to login/checkpoint.
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1000)
    if is_linkedin_login_page(page):
        raise RuntimeError("Could not authenticate LinkedIn session before processing rows.")


def decide_still_employed(top_date_range: str | None) -> str:
    if top_date_range is None:
        return "No"
    if "present" not in top_date_range.lower():
        return "No"
    return ""


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
            raise ValueError("Input CSV has no data rows.")
        fieldnames = list(rows[0].keys())

    if "Still_Employed" not in fieldnames:
        fieldnames.append("Still_Employed")

    checked = 0
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel=browser_channel,
            headless=headless,
            viewport={"width": 1360, "height": 900},
        )
        page = context.new_page()
        ensure_linkedin_authenticated(page, linkedin_email, linkedin_password, allow_manual_login)

        for idx, row in enumerate(rows, start=1):
            if limit is not None and checked >= limit:
                break

            url = (row.get("URL") or "").strip()
            full_name = f"{row.get('First Name', '').strip()} {row.get('Last Name', '').strip()}".strip()

            if not url.startswith("http"):
                row["Still_Employed"] = "No"
                print(f"[{idx}] {full_name}: missing profile URL -> No")
                checked += 1
                continue

            print(f"[{idx}] Checking {full_name} ({url})")
            try:
                exp_url = profile_experience_url(url)
                page.goto(exp_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1200)

                login_if_needed(page, linkedin_email, linkedin_password, allow_manual_login)
                if page.url != exp_url:
                    page.goto(exp_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(800)

                top_date = extract_top_experience_date(page)
                result = decide_still_employed(top_date)
                row["Still_Employed"] = result
                print(
                    f"    top_date={top_date!r}, Still_Employed={result!r}"
                )
                checked += 1
                time.sleep(delay_s)
            except Exception as exc:
                row["Still_Employed"] = "No"
                print(f"    error={exc} -> No")
                checked += 1

        context.close()

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to: {output_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Still_Employed from LinkedIn Experience section.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/anvay_connections.csv"),
        help="Input CSV path (default: data/anvay_connections.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/anvay_connections.csv"),
        help="Output CSV path (default: overwrite input)",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path(".playwright-linkedin-profile"),
        help="Browser profile directory for persistent LinkedIn login session",
    )
    parser.add_argument(
        "--browser-channel",
        default="chrome",
        help="Playwright browser channel (default: chrome). Use empty string to use bundled Chromium.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to .env file for credentials (default: .env).",
    )
    parser.add_argument(
        "--linkedin-email",
        default=None,
        help="LinkedIn email. Prefer using env var LINKEDIN_EMAIL.",
    )
    parser.add_argument(
        "--linkedin-password",
        default=None,
        help="LinkedIn password. Prefer using env var LINKEDIN_PASSWORD.",
    )
    parser.add_argument(
        "--allow-manual-login",
        action="store_true",
        help="Allow pausing for manual login in browser if auth is required.",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument(
        "--delay",
        type=float,
        default=2.5,
        help="Delay (seconds) between profile checks (default: 2.5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N rows (useful for testing)",
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
