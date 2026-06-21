.PHONY: install lint typecheck test build run sync morning-smoke deepseek-smoke

PYTHON ?= python3

install:
	mkdir -p data

lint:
	$(PYTHON) -m compileall -q app scripts tests
	! grep -RIn "TODO\\|TBD" app scripts tests README.md env.example Dockerfile

typecheck:
	$(PYTHON) -m compileall -q app scripts tests

test:
	$(PYTHON) -m unittest discover -s tests -v

build: install lint typecheck test
	mkdir -p dist
	cp README.md env.example Dockerfile dist/

run:
	$(PYTHON) -m app.web --host 127.0.0.1 --port 8000

sync:
	$(PYTHON) scripts/sync_once.py

morning-smoke:
	$(PYTHON) scripts/morning_smoke.py

deepseek-smoke:
	$(PYTHON) scripts/deepseek_smoke.py
