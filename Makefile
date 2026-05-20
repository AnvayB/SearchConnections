start:
	python3 -m http.server 8080

test:
	python3 test_edge_cases.py

scan-jobs:
	.venv/bin/python scan_company_jobs.py --force

scan-jobs-test:
	.venv/bin/python scan_company_jobs.py --limit 3 --force --no-headless

scan-jobs-batch:
	.venv/bin/python scan_company_jobs.py --all-companies --resume --limit 25

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
