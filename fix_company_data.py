#!/usr/bin/env python3
"""
One-off repair for updated_data/*-connections_updated.csv.

Background: an earlier version of verify_linkedin_employment.py overwrote
Company/Position in place whenever it thought someone changed jobs, and
sometimes parsed a page heading or a job title as the company
("Experience", "Research Assistant", ...). The original values are still in
old-data/, so this script classifies every Employment_Changed=Yes row:

  RESTORED        scraped company is not a real employer (heading, job title,
                  placeholder): Company/Position restored from old-data, the
                  scraped values kept in Scraped_Company/Scraped_Position.
  ALIAS_RESTORED  "change" was only a rename (Meta -> Facebook): restored.
  KEPT            looks like a genuine move: new company kept, the old values
                  saved in Previous_Company/Previous_Position.
  KEPT_CHECK      kept, but worth a human look (e.g. "... platform").
  NO_ORIGINAL     no usable original found: left as is, listed for review.

It also strips private-use glyphs from Company names and fixes the
"Oracle Corp[oration" typo.

Default is a DRY RUN: prints a summary, writes nothing.
    python3 -I fix_company_data.py
    python3 -I fix_company_data.py --apply     # rewrite CSVs + review file
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from employment_parse import looks_like_valid_company, normalize_company, same_company  # noqa: E402

OWNERS = {
    "anvay": {
        "updated": Path("updated_data/anvay-connections_updated.csv"),
        "original": Path("old-data/Anvay Close Connections.csv"),
    },
    "anil": {
        "updated": Path("updated_data/anil-connections_updated.csv"),
        "original": Path("old-data/Anil Close Connections.xlsx"),
    },
    "bilwa": {
        "updated": Path("updated_data/bilwa-connections_updated.csv"),
        "original": Path("old-data/Bilwa Close Connections.csv"),
    },
}

REVIEW_OUT = Path("updated_data/review_company_changes.csv")
NEW_COLUMNS = ["Previous_Company", "Previous_Position", "Scraped_Company", "Scraped_Position"]
SUSPICIOUS_WORDS = re.compile(r"\b(platform|project|program|initiative|fellowship|club|team)\b", re.I)
PRIVATE_USE = re.compile(r"[-]")
TYPO_FIXES = {"Oracle Corp[oration": "Oracle Corporation"}
LINE_ENDING = "\r\n"   # the existing CSVs use CRLF; keep it so git diffs stay small

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def norm_url(url: str) -> str:
    return (url or "").strip().lower().rstrip("/")


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def read_xlsx(path: Path) -> list[dict]:
    """Minimal .xlsx reader (stdlib only; pandas/openpyxl are not installed)."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

    def col_of(ref: str) -> str:
        return re.match(r"[A-Z]+", ref).group(0)

    table = []
    for row in sheet.iter(f"{{{NS['m']}}}row"):
        cells = {}
        for c in row.findall("m:c", NS):
            t = c.get("t")
            v = c.find("m:v", NS)
            if t == "s" and v is not None:
                value = shared[int(v.text)]
            elif t == "inlineStr":
                value = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
            else:
                value = v.text if v is not None else ""
            cells[col_of(c.get("r"))] = value
        table.append(cells)

    if not table:
        return []
    header = table[0]
    return [{header[col]: cells.get(col, "") for col in header} for cells in table[1:]]


def load_original(path: Path) -> dict[str, dict]:
    rows = read_xlsx(path) if path.suffix == ".xlsx" else read_csv(path)[1]
    return {norm_url(r.get("URL", "")): r for r in rows if r.get("URL")}


def is_shortened_name(a: str, b: str) -> bool:
    """True when one normalised name is a whole-word prefix of the other
    ("Senseeker" vs "Senseeker Engineering, Inc."). Used only for this one-off
    repair, where we also know the original; too loose for general matching."""
    ta, tb = normalize_company(a).split(), normalize_company(b).split()
    if not ta or not tb:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return long_[: len(short)] == short


def classify(row: dict, original: dict | None) -> tuple[str, str]:
    """Return (action, reason) for one Employment_Changed=Yes row."""
    scraped_company = (row.get("Company") or "").strip()
    scraped_position = (row.get("Position") or "").strip()
    if not original or not (original.get("Company") or "").strip():
        return "NO_ORIGINAL", "no original company found in old-data"

    old_company = original["Company"].strip()
    if same_company(old_company, scraped_company) or is_shortened_name(old_company, scraped_company):
        return "ALIAS_RESTORED", "same company under another name"
    if not looks_like_valid_company(scraped_company, scraped_position):
        return "RESTORED", "scraped company is a heading, placeholder or job title"
    if SUSPICIOUS_WORDS.search(scraped_company):
        return "KEPT_CHECK", "looks like a project/platform rather than an employer"
    return "KEPT", "looks like a genuine move"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the CSVs and the review file")
    args = ap.parse_args()

    review: list[dict] = []
    outputs: dict[str, tuple[list[str], list[dict]]] = {}
    counts: dict[str, int] = {}
    cleaned = {"private_use": 0, "typo": 0}

    for owner, paths in OWNERS.items():
        fieldnames, rows = read_csv(paths["updated"])
        original_by_url = load_original(paths["original"])
        for col in NEW_COLUMNS:
            if col not in fieldnames:
                fieldnames.append(col)
        for row in rows:
            for col in NEW_COLUMNS:
                row.setdefault(col, "")

        for row in rows:
            company = row.get("Company") or ""
            fixed = TYPO_FIXES.get(company.strip(), PRIVATE_USE.sub("", company).strip())
            if fixed != company:
                cleaned["typo" if company.strip() in TYPO_FIXES else "private_use"] += 1
                row["Company"] = fixed

            if row.get("Employment_Changed") != "Yes":
                continue

            original = original_by_url.get(norm_url(row.get("URL", "")))
            action, reason = classify(row, original)
            counts[action] = counts.get(action, 0) + 1
            scraped_company, scraped_position = row.get("Company", ""), row.get("Position", "")

            review.append({
                "Owner": owner,
                "First Name": row.get("First Name", ""),
                "Last Name": row.get("Last Name", ""),
                "URL": row.get("URL", ""),
                "Original_Company": (original or {}).get("Company", ""),
                "Original_Position": (original or {}).get("Position", ""),
                "Scraped_Company": scraped_company,
                "Scraped_Position": scraped_position,
                "Action": action,
                "Reason": reason,
            })

            if action in ("RESTORED", "ALIAS_RESTORED"):
                row["Company"] = original["Company"].strip()
                row["Position"] = (original.get("Position") or "").strip()
                row["Employment_Changed"] = ""
                if action == "RESTORED":
                    row["Scraped_Company"] = scraped_company
                    row["Scraped_Position"] = scraped_position
            elif action in ("KEPT", "KEPT_CHECK"):
                row["Previous_Company"] = original["Company"].strip()
                row["Previous_Position"] = (original.get("Position") or "").strip()

        outputs[owner] = (fieldnames, rows)

    # ---- report -----------------------------------------------------------
    print(f"Employment_Changed=Yes rows: {sum(counts.values())}")
    for action in ("RESTORED", "ALIAS_RESTORED", "KEPT", "KEPT_CHECK", "NO_ORIGINAL"):
        print(f"  {action:<15} {counts.get(action, 0)}")
    print(f"Cleaned: {cleaned['private_use']} private-use glyph(s), {cleaned['typo']} typo(s)\n")
    for r in review:
        if r["Action"] in ("RESTORED", "ALIAS_RESTORED"):
            print(f"  {r['Action']:<14} {r['Owner']:<6} {r['First Name']} {r['Last Name']}: "
                  f"{r['Scraped_Company']!r} -> {r['Original_Company']!r}")
    print()
    for r in review:
        if r["Action"] in ("KEPT_CHECK", "NO_ORIGINAL"):
            print(f"  {r['Action']:<14} {r['Owner']:<6} {r['First Name']} {r['Last Name']}: "
                  f"{r['Original_Company']!r} -> {r['Scraped_Company']!r}")

    # ---- safety checks ----------------------------------------------------
    for owner, (fieldnames, rows) in outputs.items():
        before_fields, before_rows = read_csv(OWNERS[owner]["updated"])
        assert len(rows) == len(before_rows), f"{owner}: row count changed"
        assert [r["URL"] for r in rows] == [r["URL"] for r in before_rows], f"{owner}: URLs changed"

    if not args.apply:
        print("\nDRY RUN: nothing written. Re-run with --apply to rewrite the CSVs.")
        return 0

    for owner, (fieldnames, rows) in outputs.items():
        with OWNERS[owner]["updated"].open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator=LINE_ENDING)
            w.writeheader()
            w.writerows(rows)
    review_fields = list(review[0].keys()) if review else []
    with REVIEW_OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=review_fields, lineterminator=LINE_ENDING)
        w.writeheader()
        w.writerows(review)
    print(f"\nWrote {len(outputs)} CSVs and {REVIEW_OUT} ({len(review)} rows).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
