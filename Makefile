PYTHON ?= python3
PYTHONPATH ?= src

.PHONY: format lint test smoke validate-example plan-example dry-run-example registry-summary-example registry-list-agents-example registry-list-benchmarks-example devices-list-example devices-health-check-example worker-run-example emulator-demo-example run-example

format:
	$(PYTHON) scripts/devtools.py format

lint:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/devtools.py lint

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/devtools.py test

smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile --help

validate-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile validate-config project.example.yml

plan-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile plan project.example.yml

dry-run-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile dry-run project.example.yml

registry-summary-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile registry summary

registry-list-agents-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile registry list-agents

registry-list-benchmarks-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile registry list-benchmarks

devices-list-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile devices list --config project.example.yml --device-mode fake

devices-health-check-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile devices health-check --config project.example.yml --device-mode fake

worker-run-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile worker-run project.example.yml

emulator-demo-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile emulator-demo project.example.yml

run-example:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m snowl_mobile run project.example.yml
