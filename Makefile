PY := .venv/bin/python

.PHONY: sync migrate test validate

validate:
	$(PY) -m coach.plan_loader

migrate:
	$(PY) migrate.py

sync:
	$(PY) -m ingest.sync
	$(PY) -m ingest.load
	$(PY) -m ingest.link

test:
	$(PY) -m pytest tests/ -q
