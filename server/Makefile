# Server: venv at $(PREFIX)/venv with hash-pinned requirements; tests run from the repo root.
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

PREFIX ?= /opt/robotics
VENV   := $(PREFIX)/venv
PY     := $(VENV)/bin/python

.PHONY: build test clean
build: $(VENV)/.requirements-stamp

$(VENV)/.requirements-stamp: requirements.txt
	[ -x $(PY) ] || python3 -m venv $(VENV)
	$(PY) -m pip install --quiet --require-hashes -r requirements.txt
	touch $@

test: build
	cd .. && $(PY) -m pytest -q server/tests

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache
