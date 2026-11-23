# Root Makefile. Pipelines: compile (deps, build, test) and deploy (deploy, check).
# Works on a laptop (override PREFIX/DATA) as well as on the Pi.

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

PREFIX ?= /opt/robotics
DATA   ?= /var/lib/robotics/data
ETC    ?= /etc/robotics
NODE_HOME ?= /opt/node
VENV   := $(PREFIX)/venv
APP    := $(PREFIX)/app
CACHE  := .deps-cache
COMPONENTS := api server web

export PATH := $(NODE_HOME)/bin:$(PATH)
export PREFIX DATA ETC

MAVEN := https://repo1.maven.org/maven2
JARS  := $(CACHE)/junit-4.13.2.jar $(CACHE)/hamcrest-core-1.3.jar

# Run a target in every component that has a Makefile.
each = for c in $(COMPONENTS); do if [ -f $$c/Makefile ]; then $(MAKE) -C $$c $(1); else echo "WARNING: $$c/Makefile not present; skipping '$(1)' for $$c"; fi; done

.PHONY: deps build test deploy check run clean bootstrap-teacher seed-lesson0

deps: $(JARS)
	cd $(CACHE) && sha256sum -c ../deps/checksums.txt

$(CACHE)/junit-4.13.2.jar:
	@mkdir -p $(CACHE)
	curl -fsSL --max-time 120 -o $@.tmp $(MAVEN)/junit/junit/4.13.2/junit-4.13.2.jar && mv $@.tmp $@

$(CACHE)/hamcrest-core-1.3.jar:
	@mkdir -p $(CACHE)
	curl -fsSL --max-time 120 -o $@.tmp $(MAVEN)/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar && mv $@.tmp $@

build:
	@$(call each,build)

test:
	@$(call each,test)

clean:
	@$(call each,clean)
	rm -rf $(CACHE)

deploy:
	scripts/deploy

check:
	scripts/self-check

# Development server (not the systemd unit).
run:
	ROBOTICS_DATA_DIR=$(CURDIR)/data-dev $(VENV)/bin/flask --app server.app run

# make bootstrap-teacher USER=<name>   (prompts for a password)
bootstrap-teacher:
	@[ "$(origin USER)" = "command line" ] || { echo "usage: make bootstrap-teacher USER=<name>"; exit 2; }
	set -a; . $(ETC)/server.env; set +a; \
	cd $(APP) && runuser -u robotics -- $(VENV)/bin/flask --app server.app bootstrap-teacher "$(USER)"

# Copy lessons/lesson0 into the data directory. Never overwrites an existing lesson.
seed-lesson0:
	@if [ -e $(DATA)/lessons/lesson0 ]; then echo "lesson0 already present; leaving it"; else \
	  install -d -o robotics -g robotics $(DATA)/lessons && \
	  cp -a $(APP)/lessons/lesson0 $(DATA)/lessons/lesson0 && \
	  chown -R robotics:robotics $(DATA)/lessons/lesson0 && echo "seeded lesson0"; fi
