PYTHON ?= python3

.PHONY: test eval verify

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

eval:
	PYTHONPATH=src $(PYTHON) -m policy_triage.cli eval --summary

verify: test eval
