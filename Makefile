COMPOSE = docker compose -f infra/docker-compose.yml --env-file infra/.env

.PHONY: init up down reset logs seed seed-field-surveyors test migrate psql bulk-import-buildings \
	import-existing-network-survey import-existing-network-survey-commit

init:      ## Create infra/.env with a generated JWT secret
	@test -f infra/.env && echo "infra/.env already exists — not overwritten" || ( \
	  cp infra/.env.example infra/.env && \
	  sed -i '' "s|^JWT_SECRET=.*|JWT_SECRET=$$(openssl rand -hex 32)|" infra/.env && \
	  echo "Created infra/.env." && \
	  echo "Now set POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD and SEED_ADMIN_PASSWORD.")

up:        ## Build and start the full stack
	$(COMPOSE) up --build

down:      ## Stop containers, keep data
	$(COMPOSE) down

reset:     ## Stop containers AND destroy all data
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f api

migrate:
	$(COMPOSE) exec api alembic upgrade head

seed:      ## Create org, admin account, data source registry, sample project
	$(COMPOSE) exec api python -m app.seed

seed-field-surveyors: ## Create field-surveyor accounts from the NEW_SURVEYORS list (run seed first)
	$(COMPOSE) exec api python -m app.seed_field_surveyors

bulk-import-buildings: ## Create a project + import Overture buildings for every Abuja district (needs `pip install overturemaps` in the api container; run seed first)
	$(COMPOSE) exec api pip show overturemaps > /dev/null 2>&1 || $(COMPOSE) exec api pip install overturemaps
	$(COMPOSE) exec api python -m app.bulk_import_overture

import-existing-network-survey: ## Dry run: load the monday.com "Existing Network Survey Map" export into the recorded-street matching queue with photos attached (default district Wuye)
	$(COMPOSE) exec api python -m app.import_existing_network_survey

import-existing-network-survey-commit: ## Same, but actually writes RecordedStreet rows and uploads photos to MinIO
	$(COMPOSE) exec api python -m app.import_existing_network_survey --commit

test:
	$(COMPOSE) exec api python -m pytest -q

psql:
	$(COMPOSE) exec db psql -U geoplan -d geoplan
