.PHONY: test compile doctor api acceptance schemas ui-dev ui-build security-kernel-test clean

PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PYTHONPATH := src

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest -q

compile:
	$(PYTHON) -m compileall -q src tests scripts

doctor:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m systemai.main doctor

api:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m systemai.api.run

acceptance:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_v1_acceptance.py

schemas:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/generate_contract_schemas.py

ui-dev:
	cd apps/desktop/ui && npm run dev

ui-build:
	cd apps/desktop/ui && npm run build

security-kernel-test:
	cd native/security-kernel && cargo test

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '.pytest_cache' -type d -prune -exec rm -rf {} +
