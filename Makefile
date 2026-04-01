.PHONY: up down build restart logs shell-backend migrate db-upgrade db-reset test health

up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build --no-cache

restart:
	docker-compose restart backend

logs:
	docker-compose logs -f backend

shell-backend:
	docker-compose exec backend bash

migrate:
	docker-compose exec backend alembic upgrade head

db-upgrade:
	docker-compose exec backend alembic upgrade head

db-reset:
	docker-compose exec backend alembic downgrade base && docker-compose exec backend alembic upgrade head

test:
	docker-compose exec backend pytest -v

health:
	curl -s http://localhost:8000/health | python -m json.tool

.env:
	cp .env.example .env
	@echo "Created .env from .env.example — fill in your API keys"
