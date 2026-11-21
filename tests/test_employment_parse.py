"""
Offline tests for the employment scraper's parsing and row-update logic.
Run with: make test-parse   (or: python3 tests/test_employment_parse.py -v)

No Playwright, network or LinkedIn login needed: employment_parse.py is pure.
The "bad" examples are real values that earlier scraper runs wrote into Company.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from employment_parse import (  # noqa: E402
    COMPANY_ALIASES,
    apply_experience_to_row,
    same_company,
    looks_like_valid_company,
    normalize_company,
    parse_experience_text,
)

SIMPLE_ENTRY = """Experience
Software Engineer
Google · Full-time
Jan 2022 - Present · 3 yrs 2 mos
Mountain View, California, United States
Intern
Acme Corp
Jun 2020 - Aug 2020 · 3 mos
"""

GROUPED_ENTRY = """Experience
Persistent Systems
Full-time · 5 yrs 4 mos
Chief Domain Expert
Jan 2020 - Present · 5 yrs
Senior Engineer
Jan 2015 - Dec 2019 · 5 yrs
"""

# The layout behind the "Experience" bug: the employer slot says "Self-employed",
# which used to be dropped as noise so the page heading was taken as the company.
SELF_EMPLOYED = """Experience
French Tutor
Self-employed
Mar 2019 - Present · 6 yrs
"""

NO_PRESENT = """Experience
Analyst
Initech
Jan 2015 - Dec 2018 · 4 yrs
"""

HEADING_ONLY_TITLE = """Experience
Swiss Army Knife
Jan 2010 - Present
"""


class ParseExperienceText(unittest.TestCase):
    def test_simple_entry(self):
        e = parse_experience_text(SIMPLE_ENTRY)
        self.assertEqual((e["company"], e["title"], e["is_current"]), ("Google", "Software Engineer", True))

    def test_grouped_entry(self):
        e = parse_experience_text(GROUPED_ENTRY)
        self.assertEqual((e["company"], e["title"]), ("Persistent Systems", "Chief Domain Expert"))

    def test_self_employed_is_the_company_not_the_page_heading(self):
        e = parse_experience_text(SELF_EMPLOYED)
        self.assertEqual(e["company"], "Self-employed")
        self.assertEqual(e["title"], "French Tutor")
        self.assertNotEqual(e["company"], "Experience")

    def test_heading_is_never_returned_as_company_or_title(self):
        e = parse_experience_text(HEADING_ONLY_TITLE)
        self.assertEqual(e["title"], "Swiss Army Knife")
        self.assertEqual(e["company"], "", "unknown company must come back empty, not 'Experience'")

    def test_not_current(self):
        self.assertFalse(parse_experience_text(NO_PRESENT)["is_current"])

    def test_no_dates_returns_none(self):
        self.assertIsNone(parse_experience_text("Experience\nNothing here\n"))


class LooksLikeValidCompany(unittest.TestCase):
    def test_rejects_values_earlier_runs_wrote_into_company(self):
        for bad in [
            "Experience", "Career break", "Research Assistant", "Senior Royalty Analyst",
            "Senior Account Executive", "SP Finance FP&A Controller", "Senior Lead Data Scientist",
            "Grants & Scholarships Trustee", "Chief Domain Expert", "", "   ",
        ]:
            self.assertFalse(looks_like_valid_company(bad), bad)

    def test_accepts_real_employers(self):
        for good in [
            "SI-BONE", "Hear Your Song", "Hanna Center", "ÆON", "City of Goodness", "Courage Schools",
            "Neurotech@Berkeley", "Chief", "Self-employed", "Freelance", "Stealth Startup",
            "NASA - National Aeronautics and Space Administration", "Wells Fargo",
            "Richard Heath & Associates, Inc. (RHA)", "Facebook",
        ]:
            self.assertTrue(looks_like_valid_company(good), good)

    def test_rejects_company_equal_to_title(self):
        self.assertFalse(looks_like_valid_company("Product Lead Team", title="Product Lead Team"))

    def test_rejects_career_gap_placeholder_by_title(self):
        # real row: company "Life", title "Career Pause/Reset"
        self.assertFalse(looks_like_valid_company("Life", title="Career Pause/Reset"))
        self.assertFalse(looks_like_valid_company("Time Off", title="Sabbatical"))
        self.assertTrue(looks_like_valid_company("Life", title="Engineer"))

    def test_rejects_location_and_duration_lines(self):
        self.assertFalse(looks_like_valid_company("Pune District, Maharashtra, India"))
        self.assertFalse(looks_like_valid_company("3 yrs 2 mos"))


class NormalizeCompany(unittest.TestCase):
    # These must agree with normalizeCompany() in script.js.
    def test_matches_js_behaviour(self):
        self.assertEqual(normalize_company("Intel Corporation"), "intel")
        self.assertEqual(normalize_company("Sila Nanotechnologies, Inc."), "sila nanotechnologies")
        self.assertEqual(normalize_company("Benjamin Moore & Co."), "benjamin moore")
        self.assertEqual(normalize_company("The Clorox Company"), "clorox")
        self.assertEqual(normalize_company("AC Wellness Medical Group @ Apple "), "ac wellness medical group apple")
        self.assertEqual(normalize_company("Inc"), "inc")


class ApplyExperienceToRow(unittest.TestCase):
    def row(self, **kw):
        base = {"First Name": "A", "Last Name": "B", "URL": "https://x/in/a",
                "Company": "Persistent Systems", "Position": "Chief Domain Expert",
                "Still_Employed": "", "Employment_Changed": ""}
        base.update(kw)
        return base

    def exp(self, company, title="Engineer", current=True):
        return {"company": company, "title": title, "date_range": "Jan 2024 - Present", "is_current": current}

    def test_extraction_failure_leaves_row_untouched(self):
        r = self.row()
        before = dict(r)
        self.assertEqual(apply_experience_to_row(r, None), "no-extract")
        self.assertEqual(r, before, "an extraction failure must not mark anyone as 'No'")

    def test_not_current_marks_no_but_keeps_company(self):
        r = self.row()
        apply_experience_to_row(r, self.exp("Initech", current=False))
        self.assertEqual(r["Still_Employed"], "No")
        self.assertEqual(r["Company"], "Persistent Systems")

    def test_same_company_after_normalisation_is_not_a_change(self):
        r = self.row(Company="Intel Corporation")
        self.assertEqual(apply_experience_to_row(r, self.exp("Intel")), "same-company")
        self.assertEqual(r["Employment_Changed"], "")
        self.assertEqual(r["Company"], "Intel Corporation")

    def test_genuine_change_updates_company_and_keeps_previous(self):
        r = self.row(Company="NASA Ames Research Center", Position="Engineer")
        self.assertEqual(apply_experience_to_row(r, self.exp("SI-BONE", "Sr Manager")), "changed")
        self.assertEqual((r["Company"], r["Position"]), ("SI-BONE", "Sr Manager"))
        self.assertEqual((r["Previous_Company"], r["Previous_Position"]), ("NASA Ames Research Center", "Engineer"))
        self.assertEqual(r["Employment_Changed"], "Yes")

    def test_previous_company_keeps_the_first_original_on_repeat_changes(self):
        r = self.row(Company="Old Co")
        apply_experience_to_row(r, self.exp("Middle Co"))
        apply_experience_to_row(r, self.exp("Newest Co"))
        self.assertEqual(r["Previous_Company"], "Old Co")
        self.assertEqual(r["Company"], "Newest Co")

    def test_invalid_scraped_company_never_overwrites(self):
        for junk in ["Experience", "Career break", "Research Assistant", "SP Finance FP&A Controller"]:
            r = self.row(Company="Wells Fargo", Position="Analyst")
            self.assertEqual(apply_experience_to_row(r, self.exp(junk, "Whatever")), "review", junk)
            self.assertEqual((r["Company"], r["Position"]), ("Wells Fargo", "Analyst"), junk)
            self.assertEqual(r["Employment_Changed"], "Review")
            self.assertEqual(r["Scraped_Company"], junk)

    def test_unknown_company_leaves_company_alone(self):
        r = self.row()
        self.assertEqual(apply_experience_to_row(r, self.exp("")), "unknown-company")
        self.assertEqual(r["Company"], "Persistent Systems")

    def test_a_stale_review_flag_clears_when_company_matches(self):
        r = self.row(Employment_Changed="Review", Scraped_Company="Experience", Scraped_Position="x")
        apply_experience_to_row(r, self.exp("Persistent Systems"))
        self.assertEqual((r["Employment_Changed"], r["Scraped_Company"]), ("", ""))

    def test_a_current_job_clears_a_false_no(self):
        r = self.row(Still_Employed="No")
        apply_experience_to_row(r, self.exp("Persistent Systems"))
        self.assertEqual(r["Still_Employed"], "")


class AliasParity(unittest.TestCase):
    def test_alias_table_matches_script_js(self):
        import re
        js = (Path(__file__).resolve().parent.parent / "script.js").read_text(encoding="utf-8")
        block = re.search(r"const COMPANY_ALIASES = \{(.*?)\n\};", js, re.S).group(1)
        parsed = {}
        for name, items in re.findall(r"'([^']+)':\s*\[(.*?)\]", block):
            parsed[name] = re.findall(r"'([^']+)'", items)
        self.assertEqual(parsed, COMPANY_ALIASES, "update COMPANY_ALIASES in BOTH script.js and employment_parse.py")

    def test_same_company(self):
        self.assertTrue(same_company("Meta", "Facebook"))
        self.assertTrue(same_company("Amazon", "Amazon Web Services (AWS)"))
        self.assertTrue(same_company("Oracle Corp.", "Oracle"))
        self.assertFalse(same_company("Meta", "Metanoia Technologies"))
        self.assertFalse(same_company("", ""))

    def test_alias_change_is_not_reported_as_a_move(self):
        r = {"Company": "Meta", "Position": "Engineer", "Still_Employed": "", "Employment_Changed": ""}
        status = apply_experience_to_row(r, {"company": "Facebook", "title": "Engineer",
                                             "date_range": "Jan 2020 - Present", "is_current": True})
        self.assertEqual(status, "same-company")
        self.assertEqual((r["Company"], r["Employment_Changed"]), ("Meta", ""))


if __name__ == "__main__":
    unittest.main()
