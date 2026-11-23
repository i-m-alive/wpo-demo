# wpo-reference: everyday commands.
.PHONY: up down logs test smoke mode

up:      ## build and start all 18 services (agents on localhost:8080)
	docker compose up --build --detach --wait --wait-timeout 180
down:    ## stop and remove everything
	docker compose down --remove-orphans
logs:    ## follow every service's log
	docker compose logs -f
test:    ## unit and API tests (no Docker, no network, no keys)
	.venv/bin/python -m pytest -q
smoke:   ## start everything, call both routes, check the answers and two failure modes, clean up
	./scripts/smoke.sh
mode:    ## switch one running stand-in: make mode SYSTEM=workday MODE=throttle (MODE=normal switches it back)
	@case "$(SYSTEM):$(MODE)" in \
	  workday:normal|workday:throttle|mes:normal|mes:empty|lms:normal|lms:empty|cuopt:normal|cuopt:infeasible|policy:normal|policy:empty) ;; \
	  *) echo "usage: make mode SYSTEM=<system> MODE=<mode>, one of: workday throttle, mes empty, lms empty," \
	          "cuopt infeasible, policy empty (or MODE=normal)"; exit 1 ;; \
	esac
	$(shell echo $(SYSTEM) | tr a-z A-Z)_MODE=$(MODE) docker compose up --detach --wait --no-deps stub-$(SYSTEM)
