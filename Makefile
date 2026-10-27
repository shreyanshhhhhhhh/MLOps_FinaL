.PHONY: setup repro exp test lint dag push

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
DVC := $(VENV)/bin/dvc

export PATH := $(CURDIR)/.venv/bin:$(PATH)
export DVC_NO_ANALYTICS := 1
export MLFLOW_DISABLE_AGENT_HINT := 1
export MLFLOW_ALLOW_FILE_STORE := true

setup:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

repro:
	$(DVC) repro

# Always rerun the sweep and the downstream promotion, even when DVC cache is warm.
exp:
	$(DVC) repro --force train evaluate select_best

test:
	$(PYTHON) -m pytest

pipeline-check:
	SKIP_DVC_PULL=1 bash scripts/ci_pipeline_check.sh

lint:
	$(PYTHON) -m ruff check src app tests

serve:
	MODEL_AUTOLOAD=1 $(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port $${PORT:-8000}

dag:
	$(DVC) dag

push:
	$(DVC) push
