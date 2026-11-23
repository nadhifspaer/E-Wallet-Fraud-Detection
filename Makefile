PY := .venv/bin/python

.PHONY: setup check

# create the virtual environment and install dependencies
setup:
	python3.11 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

# lint and run tests
check:
	$(PY) -m ruff check .
	$(PY) -m pytest -q; rc=$$?; [ $$rc -eq 0 ] || [ $$rc -eq 5 ]
