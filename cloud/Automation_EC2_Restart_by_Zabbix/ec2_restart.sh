#!/bin/bash
############################################
# Author: karthick_Dk
# Version: v1.0
############################################

set -euo pipefail

# ---------------- CONFIG ----------------
AWS_CLI="aws"
TIMEOUT=500        # max wait time in seconds
POLL_INTERVAL=10   # seconds
# ----------------------------------------

usage() {
    echo "Usage: $0 <PRIVATE_IP>"
    exit 1
}

log() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $*"
}

error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $*" >&2
    exit 1
}

# ----------- INPUT VALIDATION -----------
IP="${1:-}"
[ -z "$IP" ] && usage
# ----------------------------------------

log "Searching EC2 instance for IP: $IP"

INSTANCE_ID=$(  $AWS_CLI ec2 describe-instances \
    --filters "Name=private-ip-address,Values=$IP" \
    --query "Reservations[].Instances[].InstanceId" \
    --output text)

[ -z "$INSTANCE_ID" ] && error "No instance found for IP $IP"

log "Found Instance ID: $INSTANCE_ID"

# ----------- STOP INSTANCE --------------
log "Stopping instance $INSTANCE_ID"
  $AWS_CLI ec2 stop-instances --instance-ids "$INSTANCE_ID" >/dev/null

log "Waiting for instance to stop..."
START_TIME=$(date +%s)
while true; do
    STATE=$(  $AWS_CLI ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --query "Reservations[].Instances[].State.Name" \
        --output text)

    [ "$STATE" = "stopped" ] && break

    NOW=$(date +%s)
    [ $((NOW - START_TIME)) -ge $TIMEOUT ] && error "Timeout waiting for stop"

    sleep $POLL_INTERVAL
done

log "Instance stopped successfully"

# ----------- START INSTANCE -------------
log "Starting instance $INSTANCE_ID"
  $AWS_CLI ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null

log "Waiting for instance to run..."
START_TIME=$(date +%s)
while true; do
    STATE=$(  $AWS_CLI ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --query "Reservations[].Instances[].State.Name" \
        --output text)

    [ "$STATE" = "running" ] && break

    NOW=$(date +%s)
    [ $((NOW - START_TIME)) -ge $TIMEOUT ] && error "Timeout waiting for start"

    sleep $POLL_INTERVAL
done

log "Restart completed successfully"
log "IP: $IP | Instance ID: $INSTANCE_ID | State: $STATE"
