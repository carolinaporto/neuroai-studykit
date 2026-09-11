.PHONY: up down api web test test-api test-web lint migrate upgrade

up:
	docker compose up -d

down:
	docker compose down

api:
	uv run uvicorn apps.api.main:app --reload

web:
	cd apps/web && npm run dev

test: test-api test-web

test-api:
	uv run pytest

test-web:
	cd apps/web && npm test -- --run

lint:
	uv run ruff check --fix .
	cd apps/web && npm run lint -- --fix && npx prettier --write .

migrate:
	uv run alembic revision --autogenerate -m "$(m)"

upgrade:
	uv run alembic upgrade head
