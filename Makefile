PYTHON ?= python

.PHONY: demo test check
demo:
	$(PYTHON) -m enterprise_agent.cli demo

test:
	$(PYTHON) -m pytest -q

check:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m pytest -q
