start:
	python3 -m http.server 8080

test:
	python3 test_edge_cases.py

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
