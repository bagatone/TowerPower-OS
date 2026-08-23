#!/bin/bash

set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 1
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)" || exit 1
RUNTIME_DIR="$ROOT/runtime"
LOG_DIR="$RUNTIME_DIR/logs"
LOCK_DIR="$RUNTIME_DIR/production-planning-scheduler.lock"
PYTHON="$ROOT/.venv/bin/python"
OCCURRENCE_HELPER="$ROOT/scripts/production_planning_occurrence.py"
SECRETS="$ROOT/runtime/secrets/production-planning-scheduler.env"
ADAPTER_IDENTIFIER="com.towerpower.production-planning-scheduler"
BUSINESS_TIME="06:30"

mkdir -p "$LOG_DIR" || exit 1
find "$LOG_DIR" -type f -name 'production-planning-scheduler-*.log' -mtime +30 \
    -exec rm -f -- {} + 2>/dev/null || true

INVOCATION_TIMESTAMP="$(TZ=Atlantic/Canary date '+%Y-%m-%dT%H:%M:%S%z')" || exit 1
NOMINAL_DATE="$(TZ=Atlantic/Canary date '+%Y-%m-%d')" || exit 1
CANARY_TIME="$(TZ=Atlantic/Canary date '+%H:%M')" || exit 1
LOG_STAMP="$(TZ=Atlantic/Canary date '+%Y%m%dT%H%M%S')" || exit 1
LOG_FILE="$LOG_DIR/production-planning-scheduler-${LOG_STAMP}-$$.log"

log_metadata() {
    printf '%s\n' \
        "INVOCATION_TIMESTAMP: $INVOCATION_TIMESTAMP" \
        "ADAPTER_IDENTIFIER: $ADAPTER_IDENTIFIER" \
        "NOMINAL_DATE: $NOMINAL_DATE" \
        "BUSINESS_TIME: $BUSINESS_TIME" \
        "$1" >>"$LOG_FILE"
}

launcher_failure() {
    log_metadata "LAUNCHER_STATUS: $1"
    printf '%s\n' "EXIT_CODE: $2" >>"$LOG_FILE"
    printf '%s\n' "$1" >&2
    exit "$2"
}

if [ "$CANARY_TIME" != "$BUSINESS_TIME" ]; then
    launcher_failure "MISSED_EXECUTION: outside authorized Atlantic/Canary schedule" 1
fi
if [ ! -x "$PYTHON" ] || [ ! -f "$OCCURRENCE_HELPER" ]; then
    launcher_failure "OPERATION_RUNTIME_UNAVAILABLE" 3
fi
if [ ! -f "$SECRETS" ] || [ ! -r "$SECRETS" ]; then
    launcher_failure "OPERATION_INPUT_INVALID: Production Planning secrets unavailable" 2
fi
if [ ! -O "$SECRETS" ] || [ "$(stat -f '%Lp' "$SECRETS" 2>/dev/null)" != "600" ]; then
    launcher_failure "OPERATION_INPUT_INVALID: Production Planning secrets permissions must be 0600" 2
fi

load_database_environment() {
    TPO_DATABASE_HOST_VALUE="" TPO_DATABASE_PORT_VALUE=""
    TPO_DATABASE_NAME_VALUE="" TPO_DATABASE_USER_VALUE=""
    TPO_DATABASE_PASSWORD_VALUE="" TPO_DATABASE_SSLMODE_VALUE=""
    TPO_DATABASE_CONNECT_TIMEOUT_VALUE=""
    HOST_SEEN=0 PORT_SEEN=0 NAME_SEEN=0 USER_SEEN=0
    PASSWORD_SEEN=0 SSLMODE_SEEN=0 TIMEOUT_SEEN=0
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue ;; *=*) ;; *) return 1 ;; esac
        key=${line%%=*}; value=${line#*=}
        case "$value" in ''|[[:space:]]*) return 1 ;; esac
        case "$key" in
            TPO_DATABASE_HOST) [ "$HOST_SEEN" -eq 0 ] || return 1; TPO_DATABASE_HOST_VALUE=$value; HOST_SEEN=1 ;;
            TPO_DATABASE_PORT) [ "$PORT_SEEN" -eq 0 ] || return 1; TPO_DATABASE_PORT_VALUE=$value; PORT_SEEN=1 ;;
            TPO_DATABASE_NAME) [ "$NAME_SEEN" -eq 0 ] || return 1; TPO_DATABASE_NAME_VALUE=$value; NAME_SEEN=1 ;;
            TPO_DATABASE_USER) [ "$USER_SEEN" -eq 0 ] || return 1; TPO_DATABASE_USER_VALUE=$value; USER_SEEN=1 ;;
            TPO_DATABASE_PASSWORD) [ "$PASSWORD_SEEN" -eq 0 ] || return 1; TPO_DATABASE_PASSWORD_VALUE=$value; PASSWORD_SEEN=1 ;;
            TPO_DATABASE_SSLMODE) [ "$SSLMODE_SEEN" -eq 0 ] || return 1; TPO_DATABASE_SSLMODE_VALUE=$value; SSLMODE_SEEN=1 ;;
            TPO_DATABASE_CONNECT_TIMEOUT) [ "$TIMEOUT_SEEN" -eq 0 ] || return 1; TPO_DATABASE_CONNECT_TIMEOUT_VALUE=$value; TIMEOUT_SEEN=1 ;;
            *) return 1 ;;
        esac
    done <"$SECRETS"
    [ "$HOST_SEEN" -eq 1 ] && [ "$PORT_SEEN" -eq 1 ] \
        && [ "$NAME_SEEN" -eq 1 ] && [ "$USER_SEEN" -eq 1 ] \
        && [ "$PASSWORD_SEEN" -eq 1 ] && [ "$SSLMODE_SEEN" -eq 1 ] \
        && [ "$TIMEOUT_SEEN" -eq 1 ] || return 1
    export TPO_DATABASE_HOST="$TPO_DATABASE_HOST_VALUE"
    export TPO_DATABASE_PORT="$TPO_DATABASE_PORT_VALUE"
    export TPO_DATABASE_NAME="$TPO_DATABASE_NAME_VALUE"
    export TPO_DATABASE_USER="$TPO_DATABASE_USER_VALUE"
    export TPO_DATABASE_PASSWORD="$TPO_DATABASE_PASSWORD_VALUE"
    export TPO_DATABASE_SSLMODE="$TPO_DATABASE_SSLMODE_VALUE"
    export TPO_DATABASE_CONNECT_TIMEOUT="$TPO_DATABASE_CONNECT_TIMEOUT_VALUE"
}

unset TPO_DATABASE_HOST TPO_DATABASE_PORT TPO_DATABASE_NAME
unset TPO_DATABASE_USER TPO_DATABASE_PASSWORD TPO_DATABASE_SSLMODE
unset TPO_DATABASE_CONNECT_TIMEOUT
load_database_environment || launcher_failure "OPERATION_INPUT_INVALID: Production Planning secrets format invalid" 2

BUSINESS_AT="$($PYTHON "$OCCURRENCE_HELPER" "$NOMINAL_DATE")" \
    || launcher_failure "OPERATION_INPUT_INVALID: nominal occurrence invalid" 2
CORRELATION_ID="production-planning-auto-v1:$BUSINESS_AT"

LOCK_ACQUIRED=0
cleanup() {
    if [ "${LOCK_ACQUIRED:-0}" -eq 1 ]; then
        rm -f -- "$LOCK_DIR/owner" 2>/dev/null || true
        rmdir "$LOCK_DIR" 2>/dev/null || true
    fi
    [ -z "${STDOUT_FILE:-}" ] || rm -f -- "$STDOUT_FILE"
    [ -z "${STDERR_FILE:-}" ] || rm -f -- "$STDERR_FILE"
}
trap cleanup EXIT
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    launcher_failure "OVERLAP_BLOCKED: Production Planning scheduler lock already present" 1
fi
LOCK_ACQUIRED=1
printf '%s\n' "$$" >"$LOCK_DIR/owner" \
    || launcher_failure "LOCK_ACQUISITION_FAILED" 1

umask 077
STDOUT_FILE="$(mktemp "$RUNTIME_DIR/.production-planning-scheduler.stdout.XXXXXX")" || exit 1
STDERR_FILE="$(mktemp "$RUNTIME_DIR/.production-planning-scheduler.stderr.XXXXXX")" || exit 1

set +e
"$PYTHON" -m src.tpo_core.cli.main \
    production-planning initial \
    --business-at "$BUSINESS_AT" \
    --policy-set-code DEFAULT \
    --policy-version 1 \
    --actor tpo.production-planning-scheduler \
    --reason "Automated Production Planning V1" \
    --correlation-id "$CORRELATION_ID" \
    >"$STDOUT_FILE" 2>"$STDERR_FILE"
CLI_EXIT=$?
set -e

sanitize_stream() {
    awk '
    {
        lowered = tolower($0)
        sensitive = lowered ~ /postgres(ql)?(\+[a-z0-9_.-]+)?:\/\//
        sensitive = sensitive || lowered ~ /password[[:space:]]*[:=]/
        sensitive = sensitive || lowered ~ /(^|[[:space:]])(host|hostaddr|port|dbname|user|password|sslmode|connect_timeout)[[:space:]]*=/
        sensitive = sensitive || lowered ~ /traceback|technical_cause/
        sensitive = sensitive || lowered ~ /(^|[^[:alnum:]_])(select|insert|update|delete|with|create|alter|drop|truncate|grant|revoke)([^[:alnum:]_]|$)/
        split("TPO_DATABASE_HOST TPO_DATABASE_PORT TPO_DATABASE_NAME TPO_DATABASE_USER TPO_DATABASE_PASSWORD TPO_DATABASE_SSLMODE TPO_DATABASE_CONNECT_TIMEOUT", keys, " ")
        for (key_index in keys) {
            secret_value = ENVIRON[keys[key_index]]
            if (secret_value != "" && index($0, secret_value) != 0) sensitive = 1
        }
        if (sensitive) print "[REDACTED]"; else print $0
    }'
}

log_metadata "LAUNCHER_STATUS: CLI_COMPLETED"
printf '%s\n' "BUSINESS_AT: $BUSINESS_AT" "CORRELATION_ID: $CORRELATION_ID" 'STDOUT:' >>"$LOG_FILE"
sanitize_stream <"$STDOUT_FILE" >>"$LOG_FILE"
printf '%s\n' 'STDERR:' >>"$LOG_FILE"
sanitize_stream <"$STDERR_FILE" >>"$LOG_FILE"
printf '%s\n' "EXIT_CODE: $CLI_EXIT" >>"$LOG_FILE"
exit "$CLI_EXIT"
