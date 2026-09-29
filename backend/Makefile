# Amanah Backend Makefile
# Common commands for development

.PHONY: help install dev test lint format migrate run docker-up docker-down clean

help:
	@echo "Amanah Backend Commands:"
	@echo ""
	@echo "  install     Install dependencies"
	@echo "  dev         Run development server"
	@echo "  test        Run tests"
	@echo "  lint        Run linters (ruff, mypy)"
	@echo "  format      Format code (ruff, black)"
	@echo "  migrate     Run database migrations"
	@echo "  docker-up   Start Docker services"
	@echo "  docker-down Stop Docker services"
	@echo "  clean       Clean up cache files"
	@echo ""

install:
	pip install -r requirements-dev.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -v --cov=app --cov-report=term-missing

test-fast:
	pytest -v -x --tb=short

lint:
	ruff check app
	mypy app --ignore-missing-imports

format:
	ruff check app --fix
	ruff format app

migrate:
	alembic upgrade head

migrate-down:
	alembic downgrade -1

migrate-create:
	@read -p "Migration name: " name; \
	alembic revision --autogenerate -m "$$name"

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-build:
	docker compose build

docker-shell:
	docker compose exec api bash

celery-worker:
	celery -A app.workers.celery_app worker --loglevel=info

celery-beat:
	celery -A app.workers.celery_app beat --loglevel=info

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true

# Database shortcuts
db-shell:
	docker compose exec db psql -U amanah -d amanah

db-reset:
	docker compose exec db psql -U amanah -c "DROP DATABASE IF EXISTS amanah; CREATE DATABASE amanah;"
	$(MAKE) migrate

# Generate a secure secret key
gen-secret:
	python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate a 32-byte encryption key
gen-encryption-key:
	python -c "import secrets; print(secrets.token_urlsafe(32)[:32])"
