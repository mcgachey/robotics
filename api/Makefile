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

.PHONY: build test docs clean
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
	$(JAVA) -cp "build/test-classes:build/robotics-api.jar:$(JUNIT)" org.junit.runner.JUnitCore robotics.MockRobotTest robotics.DroidRobotTest robotics.ControllerDroidLinkTest

# Javadoc for the student-facing interfaces, served by the IDE's Documentation tab.
DOCS_OUT := ../web/ide/public/javadoc
JAVADOC  ?= javadoc
docs:
	rm -rf $(DOCS_OUT) && mkdir -p $(DOCS_OUT)
	$(JAVADOC) -quiet -Xdoclint:all,-missing -notimestamp --no-platform-links -noindex -nohelp -notree -nodeprecated \
	    -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 --release 8 \
	    -windowtitle "Robot documentation" -doctitle "Robot documentation" \
	    -d $(DOCS_OUT) src/main/java/robotics/Robot.java src/main/java/robotics/DriveMotor.java

clean:
	rm -rf build $(DOCS_OUT)
