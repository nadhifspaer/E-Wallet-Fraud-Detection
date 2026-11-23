PY := .venv/bin/python

.PHONY: setup check train ablation

# create the virtual environment and install dependencies
setup:
	python3.11 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

# lint and run tests
check:
	$(PY) -m ruff check .
	$(PY) -m pytest -q

# train the classifier and write metrics
train:
	$(PY) -m src.train

# run the additive feature ablation
ablation:
	$(PY) -m src.ablation
