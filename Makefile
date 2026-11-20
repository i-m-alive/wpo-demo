# wpo-reference: everyday commands.
.PHONY: up down logs test smoke

up:      ## build and start all 15 services (agents on localhost:8080)
	docker compose up --build --detach --wait --wait-timeout 180
down:    ## stop and remove everything
	docker compose down --remove-orphans
logs:    ## follow every service's log
	docker compose logs -f
test:    ## unit and API tests (no Docker, no network, no keys)
	.venv/bin/python -m pytest -q
smoke:   ## start everything, call both routes, check the answers, clean up
	./scripts/smoke.sh
