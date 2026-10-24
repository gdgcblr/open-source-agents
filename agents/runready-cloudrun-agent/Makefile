# RunReady — convenience targets.
#
# This Makefile ONLY automates the commands already documented in README.md so
# they cannot drift. It changes NOTHING about the safety model: workspace
# confinement, approval gating, and honest status all still live in
# runready/policy.py. `make demo` runs on a THROWAWAY COPY of sample_app so the
# committed broken fixture is never mutated.

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

.PHONY: help install test demo clean

help:
	@echo "make install  - create .venv and install agent + sample-app deps"
	@echo "make test     - run the 13 model-free safety tests (no API key)"
	@echo "make demo      - diagnose+fix the bundled broken app on a throwaway copy (no API key)"
	@echo "make clean    - remove .venv and Python caches"

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip >/dev/null
	$(PIP) install -r requirements.txt -r sample_app/requirements.txt

# The safety proof. Needs no GOOGLE_API_KEY.
test:
	$(PY) -m pytest tests/ -q

# Copy the fixture to a temp dir first, then run the full deterministic path
# (--no-model so no key is needed; --yes to auto-approve for a scripted demo).
# The committed sample_app/ is never touched.
demo:
	@tmp=$$(mktemp -d) && cp -r sample_app "$$tmp/app" && \
		$(PY) main.py "$$tmp/app" --log "$$tmp/app/startup.log" --no-model --yes; \
		rm -rf "$$tmp"

clean:
	rm -rf $(VENV) .pytest_cache tests/__pycache__ runready/__pycache__ __pycache__
