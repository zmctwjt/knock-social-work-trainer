# 叩门后端常用命令（Windows MSYS / Linux 均可用）
# make install 依赖已建好的 venv；纯 Windows 环境也可直接复制命令执行。

PYTHON ?= python
HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: install dev test lint fmt migrate seed api-doc run smoke docker-build

install:
	$(PYTHON) -m pip install --no-cache-dir -r requirements.txt

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check app tests scripts
	$(PYTHON) -m mypy app

fmt:
	$(PYTHON) -m ruff format app tests scripts
	$(PYTHON) -m ruff check --fix app tests scripts

migrate:
	$(PYTHON) -m alembic upgrade head

seed:
	$(PYTHON) scripts/seed.py

api-doc:
	$(PYTHON) scripts/gen_api_doc.py

dev:
	$(PYTHON) -m uvicorn app.main:app --reload --host $(HOST) --port $(PORT)

run:
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --workers 4

smoke:
	$(PYTHON) scripts/smoke.py

docker-build:
	docker build -t knock-backend:local .
