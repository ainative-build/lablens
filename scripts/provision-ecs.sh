#!/usr/bin/env bash
# One-shot ECS + EIP + security-group provisioning for LabLens prod.
#
# Run from local laptop. NOT idempotent — run once. If you need to recreate,
# delete the existing instance + EIP + SG via console first OR via:
#   aliyun ecs DeleteInstance --InstanceId i-xxx --Force true
#
# Cost: spawns paid resources (~$15-30/mo). Read each step before running.
# Recommended: run line-by-line first time so you can paste IDs as they're created.

set -euo pipefail

PROFILE="${ALI_PROFILE:-lablens-deploy}"
REGION="${REGION:-ap-southeast-1}"
INSTANCE_NAME="${INSTANCE_NAME:-lablens-prod-sg}"
SG_NAME="${SG_NAME:-lablens-prod}"
KEY_NAME="${KEY_NAME:-lablens-prod-key}"
KEY_FILE="${KEY_FILE:-$HOME/.ssh/lablens_ecs}"
INSTANCE_TYPE="${INSTANCE_TYPE:-ecs.t6-c1m2.large}"   # 2 vCPU / 4 GB burstable
DISK_SIZE_GB="${DISK_SIZE_GB:-40}"
EIP_BANDWIDTH="${EIP_BANDWIDTH:-5}"

ALI="aliyun --profile $PROFILE --region $REGION"

step() { printf "\n\033[36m→ %s\033[0m\n" "$*"; }

# ── Preflight ──────────────────────────────────────────────────────────────
command -v aliyun >/dev/null || { echo "aliyun CLI not installed (brew install aliyun-cli)"; exit 1; }
command -v jq     >/dev/null || { echo "jq not installed (brew install jq)"; exit 1; }
$ALI ecs DescribeRegions >/dev/null || { echo "aliyun profile $PROFILE not configured (aliyun configure --profile $PROFILE)"; exit 1; }

# ── 1. Pick VPC + VSwitch ──────────────────────────────────────────────────
step "Discovering default VPC + VSwitch in $REGION"
VPC_ID=$($ALI vpc DescribeVpcs | jq -r '.Vpcs.Vpc[0].VpcId')
VSWITCH_ID=$($ALI vpc DescribeVSwitches --VpcId "$VPC_ID" | jq -r '.VSwitches.VSwitch[0].VSwitchId')
echo "  VPC=$VPC_ID  VSwitch=$VSWITCH_ID"

# ── 2. Create security group ───────────────────────────────────────────────
step "Creating security group $SG_NAME"
SG_ID=$($ALI ecs CreateSecurityGroup \
  --VpcId "$VPC_ID" \
  --SecurityGroupName "$SG_NAME" \
  --Description "LabLens prod — SSH + HTTP/HTTPS only" \
  | jq -r '.SecurityGroupId')
echo "  SG=$SG_ID"

# ── 3. Security group rules ────────────────────────────────────────────────
step "Adding security group rules"
MY_IP=$(curl -s ifconfig.me)
echo "  Detected your public IP: $MY_IP (used for SSH allowlist)"
$ALI ecs AuthorizeSecurityGroup --SecurityGroupId "$SG_ID" \
  --IpProtocol tcp --PortRange 22/22 --SourceCidrIp "${MY_IP}/32" >/dev/null
$ALI ecs AuthorizeSecurityGroup --SecurityGroupId "$SG_ID" \
  --IpProtocol tcp --PortRange 80/80 --SourceCidrIp 0.0.0.0/0 >/dev/null
$ALI ecs AuthorizeSecurityGroup --SecurityGroupId "$SG_ID" \
  --IpProtocol tcp --PortRange 443/443 --SourceCidrIp 0.0.0.0/0 >/dev/null
echo "  ✓ SSH from $MY_IP/32, HTTP/HTTPS from 0.0.0.0/0"

# ── 4. SSH keypair ─────────────────────────────────────────────────────────
step "Generating ECS-specific SSH keypair at $KEY_FILE"
if [[ -f "$KEY_FILE" ]]; then
  echo "  Key already exists at $KEY_FILE — reusing"
else
  ssh-keygen -t ed25519 -f "$KEY_FILE" -N "" -C "lablens-prod"
fi
$ALI ecs ImportKeyPair --KeyPairName "$KEY_NAME" \
  --PublicKeyBody "$(cat ${KEY_FILE}.pub)" >/dev/null \
  || echo "  (keypair $KEY_NAME may already exist — continuing)"

# ── 5. Create ECS instance ─────────────────────────────────────────────────
step "Creating ECS instance ($INSTANCE_TYPE, ${DISK_SIZE_GB}GB)"
# Latest Ubuntu 22.04 image ID — discover dynamically (Alibaba rotates these)
IMAGE_ID=$($ALI ecs DescribeImages \
  --OSType linux --Architecture x86_64 \
  --ImageOwnerAlias system \
  --InstanceType "$INSTANCE_TYPE" \
  | jq -r '[.Images.Image[] | select(.OSName | test("Ubuntu 22"; "i"))] | .[0].ImageId')
echo "  Image: $IMAGE_ID"

INSTANCE_ID=$($ALI ecs RunInstances \
  --ImageId "$IMAGE_ID" \
  --InstanceType "$INSTANCE_TYPE" \
  --SecurityGroupId "$SG_ID" \
  --VSwitchId "$VSWITCH_ID" \
  --InstanceName "$INSTANCE_NAME" \
  --HostName "$INSTANCE_NAME" \
  --SystemDisk.Category cloud_essd_entry \
  --SystemDisk.Size "$DISK_SIZE_GB" \
  --InternetMaxBandwidthOut 0 \
  --KeyPairName "$KEY_NAME" \
  --Amount 1 \
  | jq -r '.InstanceIdSets.InstanceIdSet[0]')
echo "  InstanceId=$INSTANCE_ID  (booting…)"
sleep 15

# ── 6. Allocate + bind Elastic IP ──────────────────────────────────────────
step "Allocating Elastic IP"
EIP_RESP=$($ALI vpc AllocateEipAddress --Bandwidth "$EIP_BANDWIDTH" --InternetChargeType PayByTraffic)
EIP_ID=$(echo "$EIP_RESP" | jq -r '.AllocationId')
EIP=$(echo "$EIP_RESP" | jq -r '.EipAddress')
echo "  EIP=$EIP  AllocationId=$EIP_ID"

# Wait for instance to be Running before binding EIP
echo "  Waiting for instance to be Running…"
for _ in {1..30}; do
  STATE=$($ALI ecs DescribeInstances --InstanceIds "[\"$INSTANCE_ID\"]" \
    | jq -r '.Instances.Instance[0].Status')
  [[ "$STATE" == "Running" ]] && break
  sleep 5
done
$ALI vpc AssociateEipAddress --AllocationId "$EIP_ID" --InstanceId "$INSTANCE_ID" >/dev/null
echo "  ✓ EIP $EIP bound to $INSTANCE_ID"

# ── 7. Print everything you need next ──────────────────────────────────────
cat <<EOF

╭─────────────────────────────────────────────────────────────────╮
│  ✓ ECS provisioned successfully.                                │
╰─────────────────────────────────────────────────────────────────╯

  InstanceId           : $INSTANCE_ID
  ECS public IP (EIP)  : $EIP
  SG                   : $SG_ID
  KeyPair              : $KEY_NAME (private key at $KEY_FILE)

Next steps (see docs/deployment-guide.md for details):

  1. Add to ~/.ssh/config:
       Host ecs-lablens
         HostName $EIP
         User root
         IdentityFile $KEY_FILE
         IdentitiesOnly yes

  2. Test SSH: ssh ecs-lablens "echo ok"

  3. name.com DNS — add A record:
       lablens.ainative.build  →  $EIP   (TTL 300)

  4. Issue TLS cert: aliyun cas (see scripts/cert-renew.sh)

  5. Install Docker on ECS:
       ssh ecs-lablens "curl -fsSL https://get.docker.com | sh && \\
                         apt-get install -y docker-compose-plugin git"

  6. First deploy:
       ssh ecs-lablens "cd /opt && git clone https://github.com/ainative-build/lablens.git"
       ssh ecs-lablens "cp /opt/lablens/.env.production.example /opt/lablens/.env.production"
       ssh ecs-lablens "nano /opt/lablens/.env.production"   # set real DASHSCOPE key
       make deploy
EOF
