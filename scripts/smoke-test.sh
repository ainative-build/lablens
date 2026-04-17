#!/usr/bin/env bash
# Smoke test the prod URL from outside the box.
# Exits non-zero on any failure so `make deploy` halts.
#
# Override target via env: DOMAIN=https://staging.example.com bash scripts/smoke-test.sh

set -euo pipefail
URL="${DOMAIN:-lablens.ainative.build}"
URL="${URL#https://}"   # accept either form
URL="${URL#http://}"
BASE="https://${URL}"

ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$*" >&2; exit 1; }

echo "Smoke testing $BASE"

# 1. TLS + HTTP 200 on root (frontend)
code=$(curl -sk -o /dev/null -w "%{http_code}" "$BASE/")
[[ "$code" == "200" ]] && ok "frontend root → 200" || fail "frontend root → $code"

# 2. Backend health (canonical /api/health)
code=$(curl -sk -o /dev/null -w "%{http_code}" "$BASE/api/health")
[[ "$code" == "200" ]] && ok "backend /api/health → 200" || fail "backend /api/health → $code"

# 3. Health body shape
body=$(curl -sk "$BASE/api/health")
echo "$body" | grep -q '"status":"ok"' \
  && ok "health body has status=ok" \
  || fail "health body unexpected: $body"

# 4. CORS — preflight from a non-allowed origin should NOT echo the origin back
cors_resp=$(curl -sk -i \
  -H "Origin: https://evil.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -X OPTIONS "$BASE/api/chat" 2>/dev/null || true)
if echo "$cors_resp" | grep -qi "access-control-allow-origin: https://evil"; then
  fail "CORS allows evil.example.com (LABLENS_ALLOWED_ORIGINS too permissive?)"
else
  ok "CORS rejects unknown origin"
fi

# 5. TLS cert validity — warn if < 14 days
exp=$(echo | openssl s_client -servername "$URL" -connect "$URL:443" 2>/dev/null \
  | openssl x509 -noout -enddate \
  | sed 's/notAfter=//')

if [[ -z "$exp" ]]; then
  fail "TLS handshake or cert read failed"
fi

# Compute days remaining (macOS + Linux compatible)
exp_epoch=$(date -j -f "%b %e %T %Y %Z" "$exp" "+%s" 2>/dev/null \
            || date -d "$exp" "+%s" 2>/dev/null \
            || echo 0)
now=$(date "+%s")
days_left=$(( (exp_epoch - now) / 86400 ))

if (( days_left < 0 )); then
  fail "TLS cert EXPIRED $((-days_left)) days ago"
elif (( days_left < 14 )); then
  fail "TLS cert expires in $days_left days — RENEW NOW (make cert-renew)"
else
  ok "TLS cert valid for $days_left more days (until $exp)"
fi

echo
echo "All smoke checks passed."
