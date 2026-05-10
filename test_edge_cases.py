#!/usr/bin/env python3
"""
Quick regression runner – verifies only the profiles that have previously
tripped the parser.  Much faster than re-running the full 100-row CSV.

Usage:
    python test_edge_cases.py
    python test_edge_cases.py --headless --delay 1.5

Results are written to data/edge_cases_result.csv.
Add new entries to EDGE_CASES whenever a new parsing bug is found.
"""

import argparse
import csv
import getpass
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import verify_linkedin_employment as vle

# (first_name_lower, last_name_lower) matched case-insensitively against the CSV.
# Each entry is annotated with the bug it guards against.
EDGE_CASES: list[tuple[str, str]] = [
    # ("pranav",    "vaish"),          # Amazon grouped entry – must NOT flag as change
    # ("soham",     "ashodiya"),       # PayPal grouped entry – "Full-time" noise
    # ("shweta",    "shinde"),         # SJSU sub-role – standalone duration noise
    # ("poonam",    "hadavale, pmp"),  # Location line ("Fresno, California…") noise
    # ("thomas",    "dvorochkin"),     # Correct change: NASA → SI-BONE
    # ("prathmesh", "munoth"),         # Correct change: Sdaemon → VISHVDHARA
    ("nina",      "bhanap"),         # Year-only date range: "2001 - Present"
]


def build_test_csv(source: Path, dest: Path) -> int:
    """Copy only the EDGE_CASES rows from source into dest. Returns row count."""
    targets = set(EDGE_CASES)

    with source.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(rows[0].keys()) if rows else []

    selected = [
        r for r in rows
        if (
            r.get("First Name", "").strip().lower(),
            r.get("Last Name", "").strip().lower(),
        ) in targets
    ]

    not_found = targets - {
        (r.get("First Name", "").strip().lower(), r.get("Last Name", "").strip().lower())
        for r in selected
    }
    if not_found:
        for fn, ln in sorted(not_found):
            print(f"  WARNING: '{fn} {ln}' not found in {source}", file=sys.stderr)

    with dest.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selected)

    return len(selected)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify LinkedIn edge-case profiles only.")
    p.add_argument(
        "--input", type=Path, default=Path("data/anil-connections.csv"),
        help="Source CSV to pull edge-case rows from",
    )
    p.add_argument(
        "--output", type=Path, default=Path("data/edge_cases_result.csv"),
        help="Where to write results",
    )
    p.add_argument("--profile-dir", type=Path, default=Path(".playwright-linkedin-profile"))
    p.add_argument("--browser-channel", default="chrome")
    p.add_argument("--env-file", type=Path, default=Path(".env"))
    p.add_argument("--linkedin-email", default=None)
    p.add_argument("--linkedin-password", default=None)
    p.add_argument("--allow-manual-login", action="store_true")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--delay", type=float, default=2.5, help="Seconds between profiles")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    env = vle.load_env_file(args.env_file)

    email = (
        args.linkedin_email
        or os.getenv("LINKEDIN_EMAIL")
        or env.get("LINKEDIN_EMAIL")
        or vle.HARDCODED_LINKEDIN_EMAIL
        or None
    )
    password = (
        args.linkedin_password
        or os.getenv("LINKEDIN_PASSWORD")
        or env.get("LINKEDIN_PASSWORD")
        or vle.HARDCODED_LINKEDIN_PASSWORD
        or None
    )

    if email and not password:
        password = getpass.getpass("LinkedIn password: ")
    if password and not email:
        email = input("LinkedIn email: ").strip()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        n = build_test_csv(args.input, tmp_path)
        if n == 0:
            print("No matching rows found in input CSV. Check EDGE_CASES names.")
            return 1

        print(f"Running against {n} edge-case profile(s) → {args.output}\n")

        vle.process_csv(
            input_csv=tmp_path,
            output_csv=args.output,
            profile_dir=args.profile_dir,
            browser_channel=args.browser_channel or None,
            linkedin_email=email,
            linkedin_password=password,
            allow_manual_login=args.allow_manual_login,
            headless=args.headless,
            delay_s=args.delay,
            limit=None,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
