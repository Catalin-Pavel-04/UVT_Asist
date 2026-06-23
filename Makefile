.PHONY: setup qdrant build-index build-vector-index backend smoke test compile eval demo-check

PYTHON ?= python

ifeq ($(OS),Windows_NT)
VENV_PY := .venv/Scripts/python.exe
else
VENV_PY := .venv/bin/python
endif

PYCMD := $(if $(wildcard $(VENV_PY)),$(VENV_PY),$(PYTHON))

setup:
	$(PYTHON) -m venv .venv
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r backend/requirements.txt
	$(VENV_PY) -m pip install -r requirements-dev.txt
	$(VENV_PY) -c "from pathlib import Path; src=Path('backend/.env.example'); dst=Path('backend/.env'); dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8') if src.exists() and not dst.exists() else None"

qdrant:
	docker compose up -d qdrant

build-index:
	$(PYCMD) backend/build_index.py

build-vector-index:
	$(PYCMD) backend/scripts/build_vector_index.py

backend:
	$(PYCMD) backend/app.py

compile:
	$(PYCMD) -m compileall backend

smoke:
	$(PYCMD) backend/scripts/smoke_retrieval.py

test: compile
	$(PYCMD) -m pytest

eval:
	$(PYCMD) backend/scripts/evaluate_rag.py

demo-check:
	$(PYCMD) backend/scripts/demo_check.py
