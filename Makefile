# Common tasks. Tools come from requirements-dev.txt.
# Use a virtual environment, or override: make test PYTHON=.venv/bin/python

PYTHON ?= python3

.PHONY: install test test-live lint format check

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

test:
	$(PYTHON) -m pytest

# Calls the real API with read-only requests. Needs MAGIC_API_KEY in the environment.
test-live:
	$(PYTHON) -m pytest -m live

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

check: lint test
	$(PYTHON) scripts/check_copy.py
	$(PYTHON) scripts/check_links.py
