#!/bin/bash
# handler.sh — Convert SNMP Trap to RFC5424 Syslog and forward to OTel Collector
#
# snmptrapd calls this script for every received trap.
# Trap data is provided via stdin:
#   Line 1: Hostname of sender
#   Line 2: IP address of sender
#   Line 3+: OID = value pairs

OTEL_HOST="${OTEL_HOST:-otel-collector}"
OTEL_PORT="${OTEL_PORT:-514}"

# Read stdin (trap data from snmptrapd)
HOSTNAME=$(head -1)
SOURCE_IP=$(head -1)
TRAP_BODY=$(cat)

# Compose a human-readable trap message
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
MSG="SNMPTRAP host=${HOSTNAME} ip=${SOURCE_IP} ${TRAP_BODY}"

# Format as RFC5424 Syslog (facility=16=local0, severity=5=notice → priority=133)
# <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG
SYSLOG_MSG="<133>1 ${TIMESTAMP} ${HOSTNAME:-snmptrapd} snmptrapd - - - ${MSG}"

# Send to OTel Collector syslog receiver via UDP
echo -n "${SYSLOG_MSG}" | nc -u -w1 "${OTEL_HOST}" "${OTEL_PORT}"

# Also print to stdout for container logs
echo "[$(date)] Trap from ${HOSTNAME} (${SOURCE_IP}): forwarded to OTel"
