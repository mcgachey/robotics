# Web: npm workspaces (common, ide, instructor). Node comes from $(NODE_HOME) via the root Makefile's PATH.
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

.PHONY: build test clean
build: node_modules/.stamp
	npm run build

node_modules/.stamp: package-lock.json package.json
	npm ci --no-audit --no-fund
	touch $@

test: node_modules/.stamp
	npm test

clean:
	rm -rf ide/dist instructor/dist node_modules
