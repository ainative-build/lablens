#!/usr/bin/env bash
# Apply for / renew the Alibaba SSL Certificates free DV cert for $DOMAIN,
# wait for DNS validation, download PEM + KEY, scp to ECS, restart nginx.
#
# Manual step: pasting the DNS validation TXT record into name.com
# (name.com is not an Alibaba product → no CLI integration).
#
# Run from local laptop. Re-run this script ~30 days before cert expiry
# (Alibaba SSL Certificates emails warnings 30/15/7 days prior).

set -euo pipefail

PROFILE="${ALI_PROFILE:-lablens-deploy}"
REGION="${REGION:-ap-southeast-1}"
DOMAIN="${DOMAIN:-lablens.ainative.build}"
SSH_HOST="${SSH_HOST:-ecs-lablens}"
CERT_DIR_REMOTE="${CERT_DIR_REMOTE:-/etc/lablens/certs}"

ALI="aliyun --profile $PROFILE --region $REGION"
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

step() { printf "\n\033[36m→ %s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }

# ── Preflight ──────────────────────────────────────────────────────────────
command -v aliyun >/dev/null || { echo "aliyun CLI required"; exit 1; }
command -v jq     >/dev/null || { echo "jq required"; exit 1; }

# ── 1. Discover the current free DV SKU (Alibaba renames these) ────────────
step "Listing available cert products to find current free DV SKU"
echo "  (Pick one that includes 'free' in the name and DV trust level.)"
$ALI cas ListUserCertificateOrder 2>/dev/null \
  | jq -r '.CertificateOrderList[]? | "\(.ProductCode)\t\(.ProductName)"' \
  | head -20 || true

PRODUCT_CODE="${PRODUCT_CODE:-digicert-free-1-free}"
echo
read -r -p "Use ProductCode [$PRODUCT_CODE]: " input
PRODUCT_CODE="${input:-$PRODUCT_CODE}"

# ── 2. Apply for cert ──────────────────────────────────────────────────────
step "Applying for free DV cert for $DOMAIN ($PRODUCT_CODE)"
ORDER_ID=$($ALI cas CreateCertificateForPackageRequest \
  --Domain "$DOMAIN" \
  --ValidateType DNS \
  --ProductCode "$PRODUCT_CODE" \
  | jq -r '.OrderId')
ok "OrderId=$ORDER_ID"

# ── 3. Get DNS validation TXT record ───────────────────────────────────────
step "Fetching DNS validation TXT record"
sleep 5
ORDER_DETAIL=$($ALI cas DescribeCertificateState --OrderId "$ORDER_ID")
TXT_HOST=$(echo "$ORDER_DETAIL" | jq -r '.RecordDomain // empty')
TXT_VALUE=$(echo "$ORDER_DETAIL" | jq -r '.RecordValue // empty')

if [[ -z "$TXT_HOST" || -z "$TXT_VALUE" ]]; then
  echo "Could not extract TXT record from order. Full response:"
  echo "$ORDER_DETAIL" | jq .
  exit 1
fi

cat <<EOF

╭─────────────────────────────────────────────────────────────────╮
│  MANUAL STEP — add this TXT record at name.com                  │
╰─────────────────────────────────────────────────────────────────╯

  Type   : TXT
  Host   : $TXT_HOST
  Value  : $TXT_VALUE
  TTL    : 300

After adding the record, press Enter to continue (we'll then poll for
Alibaba to verify the record — usually takes 1-5 min).
EOF
read -r

# ── 4. Poll until issued ───────────────────────────────────────────────────
step "Waiting for cert issuance"
for _ in {1..30}; do
  STATE=$($ALI cas DescribeCertificateState --OrderId "$ORDER_ID" \
    | jq -r '.Type // .State // "unknown"')
  echo "  $(date +%H:%M:%S)  state=$STATE"
  case "$STATE" in
    domain_verify_ok|issued|ISSUED) ok "cert issued"; break ;;
    domain_verify_fail|FAILED)      echo "  ✗ verification failed"; exit 1 ;;
  esac
  sleep 30
done

# ── 5. Download cert (PEM + KEY) ───────────────────────────────────────────
step "Downloading cert + key"
CERT_ID=$($ALI cas DescribeCertificateState --OrderId "$ORDER_ID" | jq -r '.CertId // empty')
if [[ -z "$CERT_ID" ]]; then
  echo "CertId not returned. Manually run: aliyun cas DescribeCertificateState --OrderId $ORDER_ID"
  exit 1
fi

DETAIL=$($ALI cas DescribeUserCertificateDetail --CertId "$CERT_ID")
echo "$DETAIL" | jq -r '.Cert' > "$WORK_DIR/lablens.pem"
echo "$DETAIL" | jq -r '.Key' > "$WORK_DIR/lablens.key"
chmod 600 "$WORK_DIR/lablens.key"
ok "saved to $WORK_DIR/{lablens.pem,lablens.key}"

# ── 6. scp to ECS + restart nginx ──────────────────────────────────────────
step "Uploading to $SSH_HOST:$CERT_DIR_REMOTE"
scp "$WORK_DIR/lablens.pem" "$WORK_DIR/lablens.key" "$SSH_HOST:/tmp/" >/dev/null
ssh "$SSH_HOST" bash <<REMOTE
  set -e
  mkdir -p $CERT_DIR_REMOTE
  mv /tmp/lablens.pem /tmp/lablens.key $CERT_DIR_REMOTE/
  chmod 600 $CERT_DIR_REMOTE/lablens.key
  chmod 644 $CERT_DIR_REMOTE/lablens.pem
  cd /opt/lablens
  docker compose -f docker/docker-compose.prod.yml restart nginx
REMOTE
ok "nginx restarted with new cert"

step "Verifying TLS"
sleep 3
echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null \
  | openssl x509 -noout -dates -subject

cat <<EOF

╭─────────────────────────────────────────────────────────────────╮
│  ✓ Cert renewed.                                                │
│  Don't forget: remove the validation TXT record at name.com.    │
╰─────────────────────────────────────────────────────────────────╯
EOF
