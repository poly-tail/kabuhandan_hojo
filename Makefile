PYTHON ?= python

.PHONY: install test compile check-current sync-current render-graphs ci

install:
	$(PYTHON) -m pip install -e .[dev]

test:
	$(PYTHON) -m pytest

compile:
	$(PYTHON) -m compileall src scripts

check-current:
	$(PYTHON) scripts/sync_current_files.py --check

sync-current:
	$(PYTHON) scripts/sync_current_files.py --write

render-graphs:
	$(PYTHON) scripts/render_docs_graphs.py

ci: compile check-current test

