# LabLens — local-machine ops commands for the prod ECS box.
#
# Prerequisites (all documented in docs/deployment-guide.md):
#   - SSH config block at ~/.ssh/config has  Host ecs-lablens
#   - aliyun CLI installed + configured with profile `lablens-deploy`
#   - jq, openssl on local PATH
#
# Override defaults via env: `make deploy SSH="ssh other-host"`

SSH      ?= ssh ecs-lablens
APP_DIR  ?= /opt/lablens
COMPOSE  ?= docker compose -f docker/docker-compose.prod.yml
ALI      ?= aliyun --profile lablens-deploy
DOMAIN   ?= lablens.ainative.build
BRANCH   ?= main

.PHONY: help deploy logs restart ssh down smoke-test tls-check cert-renew ecs-status

help:
	@echo "LabLens deploy targets (run from repo root):"
	@echo "  make deploy [BRANCH=foo]  → pull BRANCH (default: main) + rebuild + restart"
	@echo "  make logs        → tail logs from all services"
	@echo "  make restart     → docker compose restart (no rebuild)"
	@echo "  make ssh         → open shell on the box"
	@echo "  make down        → stop the stack (keeps containers + volumes)"
	@echo "  make smoke-test  → curl-based health checks against $(DOMAIN)"
	@echo "  make tls-check   → print cert dates"
	@echo "  make cert-renew  → apply for new TLS cert via aliyun cas + scp to ECS"
	@echo "  make ecs-status  → describe ECS instance state via aliyun ecs"

deploy:
	@echo "→ Deploying latest $(BRANCH) to $(DOMAIN)…"
	$(SSH) "cd $(APP_DIR) && git fetch origin && git reset --hard origin/$(BRANCH) && $(COMPOSE) up -d --build"
	@echo "→ Waiting 20s for services to settle…"
	@sleep 20
	@$(MAKE) smoke-test
	@echo "✓ Deploy complete"

logs:
	$(SSH) "cd $(APP_DIR) && $(COMPOSE) logs -f --tail=100"

restart:
	$(SSH) "cd $(APP_DIR) && $(COMPOSE) restart"

ssh:
	$(SSH)

down:
	$(SSH) "cd $(APP_DIR) && $(COMPOSE) down"

smoke-test:
	@DOMAIN=$(DOMAIN) bash scripts/smoke-test.sh

tls-check:
	@echo | openssl s_client -servername $(DOMAIN) \
	  -connect $(DOMAIN):443 2>/dev/null \
	  | openssl x509 -noout -dates -subject -issuer

cert-renew:
	@bash scripts/cert-renew.sh

ecs-status:
	@$(ALI) ecs DescribeInstances --InstanceName lablens-prod-sg \
	  | jq '.Instances.Instance[] | {Id: .InstanceId, Status: .Status, IP: .PublicIpAddress.IpAddress, EipAddress: .EipAddress.IpAddress}'
