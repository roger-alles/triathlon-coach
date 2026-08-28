PY := .venv/bin/python

.PHONY: sync migrate test

migrate:
	$(PY) migrate.py

sync:
	$(PY) -m ingest.sync
	$(PY) -m ingest.load

test:
	$(PY) -m pytest tests/ -q
