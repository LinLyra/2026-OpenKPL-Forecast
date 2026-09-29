PYTHON ?= python3

setup:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt && pip install -e .

audit:
	. .venv/bin/activate && python -m openkpl.cli audit

ingest:
	. .venv/bin/activate && python -m openkpl.cli ingest

build-draft:
	. .venv/bin/activate && python -m openkpl.cli build-draft

build-temporal:
	. .venv/bin/activate && python -m openkpl.cli build-temporal

quality:
	. .venv/bin/activate && python -m openkpl.cli quality

hero-features:
	. .venv/bin/activate && python -m openkpl.cli hero-features

identity-audit:
	. .venv/bin/activate && python -m openkpl.cli identity-audit

baseline:
	. .venv/bin/activate && python -m openkpl.cli baseline

canonicalize:
	. .venv/bin/activate && python -m openkpl.cli canonicalize

temporal-benchmark:
	. .venv/bin/activate && python -m openkpl.cli temporal-benchmark

refresh-snapshot:
	. .venv/bin/activate && python -m openkpl.cli refresh-snapshot

refresh-audit:
	. .venv/bin/activate && python -m openkpl.cli refresh-audit

data: build-draft build-temporal quality hero-features

test:
	. .venv/bin/activate && python -m unittest discover -s tests -v
