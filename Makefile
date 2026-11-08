# EdgeForge Engine — developer convenience targets.
#
# These wrap the commands documented in docs/suite-architecture.md §5.
# Product = EdgeForge; Python module/CLI = appbuilder. POSIX-simple; uses .venv.

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.DEFAULT_GOAL := help
.PHONY: help setup test generate-sample mcp sbom lock

help:
	@echo "EdgeForge Engine — make targets:"
	@echo "  make setup            Create .venv and install deps (requirements.txt + editable appbuilder)"
	@echo "  make test             Run the Python test suite (pytest)"
	@echo "  make generate-sample  Generate the Workspace/Item sample into /tmp"
	@echo "  make mcp              Run the local stdio Engine MCP server"
	@echo "  make sbom             Regenerate Python-only SBOM, audit, and licenses in the reference image"
	@echo "  make lock             Re-resolve the Python reference lock in the reference image"

setup:
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

test:
	$(PY) -m pytest -v

generate-sample:
	$(PY) -m appbuilder.cli generate \
	  --manifest examples/input-projects/workspace-items/app-definition.yaml \
	  --output /tmp/edgeforge-sample-app

mcp:
	$(PY) -m appbuilder.mcp_server

sbom:
	bash scripts/generate-python-dependency-evidence.sh

lock:
	bash scripts/refresh-python-reference-lock.sh
