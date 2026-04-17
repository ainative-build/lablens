# LabLens Deployment Guide

Single-VM deployment to Alibaba Cloud ECS (Singapore), behind Nginx with TLS, served at `https://lablens.ainative.build`.

## Architecture

```
name.com DNS  →  A record  →  ECS Elastic IP
                                   │
                              443 (HTTPS)
                                   ▼
        ┌─────────────────────────────────────────┐
        │ Alibaba ECS  (Ubuntu 22.04, ap-se-1)    │
        │                                         │
        │  Nginx ──┬─ /api/*           → backend  │
        │          ├─ /analyze-report  → backend  │
        │          ├─ /analysis/*      → backend  │
        │          └─ /*               → frontend │
        │                                         │
        │  backend (uvicorn :8000, --workers 1)   │
        │  frontend (next start :3000)            │
        └─────────────────────────────────────────┘
```

**Cost:** ~$25-50/mo (ECS + EIP + bandwidth; cert + DNS free).

**Constraints:**
- Single-worker uvicorn (in-memory `job_store`). Restart loses in-flight jobs. Documented; revisit when traffic warrants Redis.
- TLS cert is 1-year DV from Alibaba (manual renewal via `make cert-renew`).

## Prerequisites — local laptop

| Tool | Why | Install |
|---|---|---|
| `aliyun` CLI | provisioning + cert renewal | `brew install aliyun-cli` |
| `jq` | parse aliyun JSON output | `brew install jq` |
| `openssl` | TLS expiry check | preinstalled |
| Docker (only for local image testing) | optional | Docker Desktop |

### One-time aliyun CLI setup

```bash
# Console: RAM → Users → create user `lablens-deploy` → AccessKey
# Permissions to attach: AliyunECSFullAccess, AliyunVPCFullAccess, AliyunYundunCertFullAccess
aliyun configure --profile lablens-deploy
#   AccessKeyId / Secret  → from RAM user
#   RegionId              → ap-southeast-1
#   Output format         → json

# Sanity
aliyun ecs DescribeRegions --profile lablens-deploy | jq '.Regions.Region[].RegionId'
```

### One-time SSH config (after first provisioning prints the EIP)

Add to `~/.ssh/config`:
```
Host ecs-lablens
  HostName <EIP_FROM_PROVISIONING>
  User root
  IdentityFile ~/.ssh/lablens_ecs
  IdentitiesOnly yes
```

Verify: `ssh ecs-lablens "echo ok"` returns `ok`.

## First-time setup (run once)

### 1. Provision ECS + EIP + security group

```bash
bash scripts/provision-ecs.sh
```

The script prints the EIP and the next steps. Save the EIP.

### 2. DNS at name.com

1. name.com → My Domains → `ainative.build` → Manage DNS
2. Add A record: host `lablens` → answer `<EIP>` → TTL 300
3. Verify: `dig +short lablens.ainative.build` returns the EIP within ~5 min

### 3. Issue TLS cert

```bash
make cert-renew
```

Script asks you to add a TXT record at name.com mid-flow (Alibaba can't do this since name.com isn't an Alibaba product). Paste the `_dnsauth.lablens` TXT record, hit Enter, wait for issuance.

### 4. Install Docker on the ECS box

```bash
ssh ecs-lablens "curl -fsSL https://get.docker.com | sh && \
                 apt-get install -y docker-compose-plugin git"
```

### 5. First clone + env + deploy

```bash
ssh ecs-lablens "cd /opt && git clone https://github.com/ainative-build/lablens.git"
ssh ecs-lablens "cp /opt/lablens/.env.production.example /opt/lablens/.env.production"
ssh ecs-lablens "nano /opt/lablens/.env.production"
# Set the real LABLENS_DASHSCOPE_API_KEY value, save + exit.

make deploy
```

First build takes ~5-8 min (Next.js build dominates).

## Day-to-day ops

```bash
make help          # list all targets
make deploy        # pull main + rebuild + restart
make logs          # tail compose logs
make restart       # docker compose restart (no rebuild)
make ssh           # shell into the box
make smoke-test    # curl-based health checks
make tls-check     # print cert dates
make cert-renew    # apply for + install new cert
make ecs-status    # describe ECS instance state
make down          # stop the stack
```

## Rollback

```bash
ssh ecs-lablens
cd /opt/lablens
git log --oneline -10
git checkout <good-sha>
docker compose -f docker/docker-compose.prod.yml up -d --build
```

## Update env vars

```bash
ssh ecs-lablens "nano /opt/lablens/.env.production"
make restart
```

## Common issues

| Symptom | Cause | Fix |
|---|---|---|
| `502 Bad Gateway` in browser | backend or frontend container down | `make logs` — find which crashed; `make restart` |
| Browser shows TLS warning | cert expired | `make cert-renew` (or `make tls-check` to confirm) |
| CORS error in browser console | `LABLENS_ALLOWED_ORIGINS` mismatch | check `.env.production`; must include `https://lablens.ainative.build` |
| `Session expired` error from chat | in-memory `job_store` lost on restart | expected after deploy; user re-uploads |
| `make deploy` hangs at smoke-test | health endpoint not yet responding | wait 30s; if persistent, check `make logs` |
| Disk full on ECS | Docker images + logs accumulate | `ssh ecs-lablens "docker system prune -af && journalctl --vacuum-time=7d"` |

## TLS renewal

Alibaba SSL Certificates emails warnings 30 / 15 / 7 days before expiry.

When you get the email:
1. `make cert-renew` (interactive — paste TXT record at name.com when prompted)
2. `make tls-check` to confirm new dates
3. Remove the old TXT record from name.com (housekeeping)

## Secrets handling

| Secret | Lives in | Never goes |
|---|---|---|
| `LABLENS_DASHSCOPE_API_KEY` | `/opt/lablens/.env.production` (gitignored) | git, image layer, logs |
| TLS private key | `/etc/lablens/certs/lablens.key` (chmod 600) | git, image layer |
| `aliyun` access key | `~/.aliyun/config.json` (local only) | git, ECS box |
| SSH private key | `~/.ssh/lablens_ecs` (local only) | git, ECS box |

## Cost (recurring)

| Item | ~Monthly |
|---|---|
| ECS `ecs.t6-c1m2.large` (Singapore, PAYG) | $15-25 |
| Elastic IP | $3 |
| Bandwidth (PAYG) | $5-15 (depends on traffic) |
| Alibaba SSL DV cert | $0 |
| DNS at name.com | $0 |
| **Total** | **~$25-45/mo** |

DashScope (Qwen) API usage is separate.

## Future improvements (deferred)

- Redis-backed `job_store` (when single-worker becomes a bottleneck)
- Auto-scaling via Alibaba SAE (when traffic justifies)
- Centralized logging via Alibaba SLS / CloudMonitor
- WAF (Alibaba WAF in front of ECS)
- Backup strategy (when persistent state lands)
- Staging environment + blue-green deploys
- name.com API automation for DNS changes (skip cert TXT manual step)
