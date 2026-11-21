# Bound to localhost on purpose: the default (all interfaces) would serve .git and
# old-data/ (raw exports with email addresses) to anyone on the same network.
start:
	python3 -m http.server 8080 --bind 127.0.0.1

test:
	python3 test_edge_cases.py

test-search:
	node --test "tests/*.test.js"

test-parse:
	python3 tests/test_employment_parse.py -v

scan-jobs:
	.venv/bin/python scan_company_jobs.py --force

scan-jobs-test:
	.venv/bin/python scan_company_jobs.py --limit 3 --force --no-headless

scan-jobs-batch:
	.venv/bin/python scan_company_jobs.py --all-companies --resume --limit 25

verify-links-batch:
	.venv/bin/python verify_company_linkedin_links.py --all-companies --resume --limit 25

verify-links-retry:
	.venv/bin/python verify_company_linkedin_links.py --all-companies --retry-empty --limit 25

add:
	git status
	git add .
	git status

# git commit -m "message"

push:
	git push origin main

pull:
	git pull origin main

check:
	git branch
	git status

user-reset:
	git config user.name "AnvayB"
	git config user.email "anvay.bhanap@gmail.com"

user-check:
	git config user.name
	git config user.email
