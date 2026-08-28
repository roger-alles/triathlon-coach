PY := .venv/bin/python

.PHONY: sync migrate test

migrate:
	$(PY) migrate.py

sync:
	$(PY) -m ingest.sync

test:
	$(PY) -m pytest tests/ -q
