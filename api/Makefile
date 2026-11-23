# robotics-api (Java 8 target) and the JUnit harness. Needs `make deps` from the root first (JUnit jars).
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

JAVAC ?= javac
JAVA  ?= java
JAR   ?= jar
CACHE := ../.deps-cache
JUNIT := $(CACHE)/junit-4.13.2.jar:$(CACHE)/hamcrest-core-1.3.jar
JFLAGS := --release 8 -Xlint:all,-options -encoding UTF-8 -proc:none

API_SRC     := $(filter-out src/main/java/robotics/harness/%,$(wildcard src/main/java/robotics/*.java))
HARNESS_SRC := $(wildcard src/main/java/robotics/harness/*.java)

.PHONY: build test clean
build: build/robotics-api.jar build/robotics-harness.jar

build/robotics-api.jar: $(API_SRC)
	rm -rf build/api-classes && mkdir -p build/api-classes
	$(JAVAC) $(JFLAGS) -d build/api-classes $(API_SRC)
	$(JAR) cf $@ -C build/api-classes .

build/robotics-harness.jar: $(HARNESS_SRC) build/robotics-api.jar
	rm -rf build/harness-classes && mkdir -p build/harness-classes
	$(JAVAC) $(JFLAGS) -cp "$(JUNIT)" -d build/harness-classes $(HARNESS_SRC)
	$(JAR) cf $@ -C build/harness-classes .

test: build
	rm -rf build/test-classes && mkdir -p build/test-classes
	$(JAVAC) $(JFLAGS) -cp "build/robotics-api.jar:$(JUNIT)" -d build/test-classes $(wildcard src/test/java/robotics/*.java)
	$(JAVA) -cp "build/test-classes:build/robotics-api.jar:$(JUNIT)" org.junit.runner.JUnitCore robotics.MockRobotTest robotics.DroidRobotTest

clean:
	rm -rf build
