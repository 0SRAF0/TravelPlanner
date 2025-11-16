# Use the backend virtual environment by default
VENV ?= venv
PYTHON := $(VENV)/bin/python
RUFF := $(VENV)/bin/ruff

.PHONY: lint fix-lint format fix-all

lint:
	$(RUFF) check app tests

fix-lint:
	$(RUFF) check --fix app tests

format:
	$(RUFF) format app tests

fix-all:
	$(RUFF) check --fix --unsafe-fixes app tests
	$(RUFF) format app tests


