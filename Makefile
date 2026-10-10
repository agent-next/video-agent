# OpenVideo baseline targets (agent-next agent standard): setup + check wrap
# the repo's existing tooling — editable pip install with dev extras, then the
# same pytest gate the CI test job runs.

PYTHON ?= python3

.PHONY: setup check

setup:
	$(PYTHON) -m pip install -e ".[dev]"

check:
	$(PYTHON) -m pytest tests/ -q --tb=short
