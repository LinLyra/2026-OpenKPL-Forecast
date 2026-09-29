PYTHON ?= python3

setup:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt && pip install -e .

audit:
	. .venv/bin/activate && python -m openkpl.cli audit

ingest:
	. .venv/bin/activate && python -m openkpl.cli ingest

baseline:
	. .venv/bin/activate && python -m openkpl.cli baseline

test:
	. .venv/bin/activate && python -m unittest discover -s tests
