start:
	python app.py

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
