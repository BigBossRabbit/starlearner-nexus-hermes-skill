# Makefile for StarLearner-Nexus skill
# Targets: smoke, install, verify

PYTHON ?= python3
PIP    ?= $(PYTHON) -m pip

.PHONY: install smoke verify

## install: install runtime dependencies from requirements.txt
install:
	$(PIP) install -r requirements.txt

## smoke: run the automated smoke test (CI gate)
smoke:
	$(PYTHON) tests/smoke_test.py

## verify: verify the installation (imports, scripts, references)
verify:
	$(PYTHON) scripts/verify_installation.py
