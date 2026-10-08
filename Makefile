.PHONY: install api web test lint build e2e demo clean

install:
	python3.14 -m venv .venv
	.venv/bin/python -m pip install -r requirements-dev.txt
	npm ci

api:
	.venv/bin/uvicorn neuroresect_api.main:app --reload --host 127.0.0.1 --port 8000

web:
	npm run dev

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check packages apps/api workers tests
	npm run typecheck

build:
	npm run build

e2e:
	npm run test:e2e
