"""
Pure parsing/validation helpers for LinkedIn experience pages.

Deliberately has no Playwright dependency so it can be unit tested offline
(see tests/test_employment_parse.py). verify_linkedin_employment.py imports
everything from here and re-exports the names other scripts rely on.
"""

from __future__ import annotations

import re

DATE_RANGE_RE = re.compile(
    r"\b"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+)?"  # optional month
    r"\d{4}"
    r"\s*[-–]\s*"
    r"(?:Present|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+)?\d{4})"
    r"\b",
    re.IGNORECASE,
)

EMPLOYMENT_TYPE_KEYWORDS = frozenset({
    "full-time", "part-time", "contract", "freelance", "self-employed",
    "internship", "temporary", "seasonal", "apprenticeship",
    "on-site", "remote", "hybrid",
})

# Employment-type words that LinkedIn also shows in the *company* slot for
# people who work for themselves. Treated as noise when walking back from the
# date line, but remembered so they can be used as the company if nothing else
# is found.
SELF_EMPLOYMENT_WORDS = frozenset({"self-employed", "freelance"})

DURATION_ONLY_RE = re.compile(
    r"^\d+\s+(yr|yrs|year|years|mo|mos|month|months)"
    r"(\s+\d+\s+(mo|mos|month|months))?\s*$",
    re.IGNORECASE,
)

# LinkedIn sometimes uses non-ASCII hyphens (e.g. U+2011 non-breaking hyphen)
# in strings like "Full‑time". Normalise before keyword lookup.
_UNICODE_DASH_RE = re.compile(r"[‐‑‒–—−]")

# Location lines (e.g. "Fresno, California, United States") should be skipped
# just like employment-type or duration-only lines.
_KNOWN_GEO_SUFFIXES = frozenset({
    "united states", "canada", "united kingdom", "india", "australia",
    "germany", "france", "singapore", "netherlands", "ireland",
    "pakistan", "area",
})

# Section headings that appear in the page text above the first entry. They are
# page chrome, never a title or a company.
HEADING_LINES = frozenset({
    "experience", "education", "licenses & certifications", "licenses and certifications",
    "skills", "volunteering", "volunteer experience", "projects", "publications",
    "honors & awards", "courses", "languages", "recommendations", "organizations",
    "show all", "show more", "show less", "about", "activity", "interests",
})

# Last words that mark a string as a job title rather than an employer.
JOB_TITLE_WORDS = frozenset({
    "analyst", "assistant", "associate", "architect", "consultant", "controller",
    "coordinator", "developer", "director", "engineer", "executive", "expert",
    "founder", "intern", "lead", "manager", "officer", "president", "researcher",
    "scientist", "specialist", "supervisor", "technician", "trustee", "tutor",
})

NON_COMPANY_VALUES = frozenset({"career break", "retired", "unemployed", "n/a", "none", "-"})

# A title like this means the "company" slot is a placeholder, not an employer
# (e.g. company "Life", title "Career Pause/Reset").
CAREER_GAP_TITLE_RE = re.compile(
    r"\b(career\s+(break|pause|reset|gap)|sabbatical|retire[dm]|unemployed|seeking\s+(new\s+)?opportunit)",
    re.IGNORECASE,
)

LEGAL_SUFFIXES = frozenset({
    "inc", "incorporated", "llc", "llp", "lp", "ltd", "limited",
    "corp", "corporation", "co", "company", "plc", "gmbh",
})


def clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _normalise_dashes(line: str) -> str:
    return _UNICODE_DASH_RE.sub("-", line.strip()).lower()


def is_heading_line(line: str) -> bool:
    return _normalise_dashes(line) in HEADING_LINES


def is_noise_line(line: str) -> bool:
    normalised = _normalise_dashes(line)
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


def parse_experience_text(text: str) -> dict | None:
    """
    Parse the text of a /details/experience/ page and return the top entry:
    {"title", "company", "date_range", "is_current"} or None.

    LinkedIn renders two layouts:
      Simple entry  -> Title, Company, Date  (no noise)
      Grouped entry -> Company (header), [duration noise], Title,
                       [employment-type noise], Date

    When no noise is skipped: non_noise[0]=company, [1]=title.
    When noise was skipped:   non_noise[0]=title,   [1]=company.

    Page headings ("Experience", ...) end the backwards walk and are never
    returned as a title or company. If the company cannot be determined the
    entry comes back with company == "" so callers can refuse to act on it.
    """
    lines = clean_lines(text)

    for i, line in enumerate(lines):
        date_match = DATE_RANGE_RE.search(line)
        if not date_match:
            continue

        date_range = date_match.group(0)

        non_noise: list[str] = []
        noise_skipped = False
        self_employment_word = ""
        hit_heading = False
        j = i - 1
        while j >= 0 and len(non_noise) < 2:
            candidate = lines[j].strip()
            if DATE_RANGE_RE.search(candidate):
                break
            if is_heading_line(candidate):
                hit_heading = True
                break
            if is_noise_line(candidate):
                noise_skipped = True
                primary = _normalise_dashes(candidate).split("·")[0].strip()
                if primary in SELF_EMPLOYMENT_WORDS and not self_employment_word:
                    self_employment_word = candidate.split("·")[0].strip()
            else:
                non_noise.append(candidate)
            j -= 1

        if len(non_noise) >= 2:
            if noise_skipped:
                title = non_noise[0].split("·")[0].strip()
                company = non_noise[1].split("·")[0].strip()
            else:
                company = non_noise[0].split("·")[0].strip()
                title = non_noise[1].split("·")[0].strip()
        elif len(non_noise) == 1:
            only = non_noise[0].split("·")[0].strip()
            if hit_heading or self_employment_word:
                # Only a title was found (heading reached): the employer is the
                # self-employment word if there was one, otherwise unknown.
                title = only
                company = self_employment_word
            else:
                company = only
                title = ""
        else:
            continue

        return {
            "title": title,
            "company": company,
            "date_range": date_range.strip(),
            "is_current": "present" in date_range.lower(),
        }

    return None


def normalize_company(name: str) -> str:
    """Python port of normalizeCompany() in script.js. Keep the two in sync."""
    s = (name or "").split("·")[0]
    s = re.sub(r"[-]", " ", s).lower().replace("&", " and ")
    tokens = [t for t in re.split(r"[\W_]+", s) if t]
    if len(tokens) > 1 and tokens[0] == "the":
        tokens.pop(0)
    while len(tokens) > 1 and (tokens[-1] in LEGAL_SUFFIXES or tokens[-1] == "and"):
        tokens.pop()
    return " ".join(tokens)


# Names that are different strings for the same company. MUST mirror
# COMPANY_ALIASES in script.js (tests/test_employment_parse.py checks the two
# match), so a Meta -> Facebook "change" is not reported as a job move.
COMPANY_ALIASES = {
    "Amazon": ["Amazon Web Services (AWS)", "Amazon Web Services", "AWS", "Amazon.com"],
    "Meta": ["Facebook", "Meta Platforms"],
    "Google": ["Alphabet", "Google LLC"],
    "Oracle": ["Oracle Corp[oration", "Oracle America"],
    "KLA": ["KLA-Tencor", "KLA Corporation"],
}

_ALIAS_INDEX = {}
for _canonical, _aliases in COMPANY_ALIASES.items():
    _key = normalize_company(_canonical)
    _ALIAS_INDEX[_key] = _key
    for _alias in _aliases:
        _ALIAS_INDEX[normalize_company(_alias)] = _key


def company_key(name: str) -> str:
    norm = normalize_company(name)
    return _ALIAS_INDEX.get(norm, norm)


def same_company(a: str, b: str) -> bool:
    ka, kb = company_key(a), company_key(b)
    return bool(ka) and ka == kb


def looks_like_valid_company(name: str, title: str = "") -> bool:
    """
    Cheap sanity check that a scraped 'company' is really an employer name and
    not a page heading, a placeholder, a location or a job title. Used to
    decide whether the scraper may overwrite a CSV row.
    """
    cleaned = (name or "").split("·")[0].strip()
    if not cleaned or len(cleaned) > 100:
        return False

    lowered = _normalise_dashes(cleaned)
    if lowered in HEADING_LINES or lowered in NON_COMPANY_VALUES:
        return False

    if title and normalize_company(cleaned) == normalize_company(title):
        return False

    if title and CAREER_GAP_TITLE_RE.search(title):
        return False

    if is_noise_line(cleaned) and lowered not in SELF_EMPLOYMENT_WORDS:
        return False   # duration / location / employment-type line

    words = [w for w in re.split(r"[\W_]+", lowered) if w]
    if words and words[-1] in JOB_TITLE_WORDS and len(words) > 1:
        return False   # "Research Assistant", "Senior Royalty Analyst", ...
    if len(words) == 1 and words[0] in JOB_TITLE_WORDS:
        return False

    return True


# Extra CSV columns the scraper may add. Company/Position are only ever changed
# when the scraped company passes looks_like_valid_company(); the previous values
# are kept so a change can always be undone.
EXTRA_COLUMNS = (
    "Still_Employed",
    "Employment_Changed",
    "Previous_Company",
    "Previous_Position",
    "Scraped_Company",
    "Scraped_Position",
)


def apply_experience_to_row(row: dict, experience: dict | None) -> str:
    """
    Update `row` in place from a parsed experience entry and return a short
    status string for logging.

    Rules:
      - No parse result: row is left untouched (an extraction failure is NOT
        evidence that the person left their job).
      - Top role has no "Present": Still_Employed = "No".
      - Current role, same company (normalised): nothing changes; a stale
        "Review" flag is cleared.
      - Current role, different company that looks like a real employer:
        Previous_Company/Previous_Position are saved (first time only), then
        Company/Position are updated and Employment_Changed = "Yes".
      - Current role, different company that does NOT look like an employer
        (heading, job title, location...): Company/Position are NOT touched;
        the scraped values go to Scraped_Company/Scraped_Position and
        Employment_Changed = "Review".
    """
    if not experience:
        return "no-extract"

    if not experience.get("is_current"):
        row["Still_Employed"] = "No"
        return "not-current"

    row["Still_Employed"] = ""

    scraped_company = (experience.get("company") or "").split("·")[0].strip()
    scraped_title = (experience.get("title") or "").strip()
    csv_company = (row.get("Company") or "").split("·")[0].strip()

    if not scraped_company:
        return "unknown-company"

    if same_company(scraped_company, csv_company):
        if row.get("Employment_Changed") == "Review":
            row["Employment_Changed"] = ""
            row["Scraped_Company"] = ""
            row["Scraped_Position"] = ""
        return "same-company"

    if not looks_like_valid_company(scraped_company, scraped_title):
        row["Scraped_Company"] = scraped_company
        row["Scraped_Position"] = scraped_title
        row["Employment_Changed"] = "Review"
        return "review"

    if not row.get("Previous_Company"):
        row["Previous_Company"] = row.get("Company") or ""
        row["Previous_Position"] = row.get("Position") or ""

    row["Company"] = scraped_company
    if "Position" in row:
        row["Position"] = scraped_title
    if "Title" in row:
        row["Title"] = scraped_title
    if "Start_Date" in row:
        row["Start_Date"] = (experience.get("date_range") or "").split("-")[0].strip()
    row["Employment_Changed"] = "Yes"
    row["Scraped_Company"] = ""
    row["Scraped_Position"] = ""
    return "changed"
