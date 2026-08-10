#!/bin/bash

set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 1
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)" || exit 1
RUNTIME_DIR="$ROOT/runtime"
LOG_DIR="$RUNTIME_DIR/logs"
LOCK_DIR="$RUNTIME_DIR/operational-scheduler.lock"
PYTHON="$ROOT/.venv/bin/python"
SETTINGS="$ROOT/config/settings.yaml"
SECRETS="$ROOT/runtime/secrets/operational-scheduler.env"
ADAPTER_IDENTIFIER="com.towerpower.operational-scheduler"

mkdir -p "$LOG_DIR" || exit 1

find "$LOG_DIR" -type f -name 'operational-scheduler-*.log' -mtime +30 \
    -exec rm -f -- {} + 2>/dev/null || true

INVOCATION_TIMESTAMP="$(TZ=Atlantic/Canary date '+%Y-%m-%dT%H:%M:%S%z')" || exit 1
BUSINESS_DATE="$(TZ=Atlantic/Canary date '+%Y-%m-%d')" || exit 1
CANARY_TIME="$(TZ=Atlantic/Canary date '+%H:%M')" || exit 1
BUSINESS_TIME="06:00"
LOG_STAMP="$(TZ=Atlantic/Canary date '+%Y%m%dT%H%M%S')" || exit 1
LOG_FILE="$LOG_DIR/operational-scheduler-${LOG_STAMP}-$$.log"

log_metadata() {
    printf '%s\n' \
        "INVOCATION_TIMESTAMP: $INVOCATION_TIMESTAMP" \
        "ADAPTER_IDENTIFIER: $ADAPTER_IDENTIFIER" \
        "BUSINESS_DATE: $BUSINESS_DATE" \
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

if [ ! -f "$SETTINGS" ] || [ ! -r "$SETTINGS" ]; then
    launcher_failure "OPERATION_INPUT_INVALID: operational settings unavailable" 2
fi

if [ ! -x "$PYTHON" ]; then
    launcher_failure "OPERATION_RUNTIME_UNAVAILABLE: project virtualenv unavailable" 3
fi

if [ ! -f "$SECRETS" ] || [ ! -r "$SECRETS" ]; then
    launcher_failure "OPERATION_INPUT_INVALID: operational secrets unavailable" 2
fi

if [ ! -O "$SECRETS" ] || [ "$(stat -f '%Lp' "$SECRETS" 2>/dev/null)" != "600" ]; then
    launcher_failure "OPERATION_INPUT_INVALID: operational secrets permissions must be 0600" 2
fi

load_operational_environment() {
    TPO_DATABASE_HOST_VALUE=""
    TPO_DATABASE_PORT_VALUE=""
    TPO_DATABASE_NAME_VALUE=""
    TPO_DATABASE_USER_VALUE=""
    TPO_DATABASE_PASSWORD_VALUE=""
    TPO_DATABASE_SSLMODE_VALUE=""
    TPO_DATABASE_CONNECT_TIMEOUT_VALUE=""
    TPO_DATABASE_HOST_SEEN=0
    TPO_DATABASE_PORT_SEEN=0
    TPO_DATABASE_NAME_SEEN=0
    TPO_DATABASE_USER_SEEN=0
    TPO_DATABASE_PASSWORD_SEEN=0
    TPO_DATABASE_SSLMODE_SEEN=0
    TPO_DATABASE_CONNECT_TIMEOUT_SEEN=0

    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|'#'*) continue ;;
            *=*) ;;
            *) return 1 ;;
        esac
        key=${line%%=*}
        value=${line#*=}
        case "$value" in
            ''|[[:space:]]*) return 1 ;;
        esac
        case "$key" in
            TPO_DATABASE_HOST)
                [ "$TPO_DATABASE_HOST_SEEN" -eq 0 ] || return 1
                TPO_DATABASE_HOST_VALUE=$value
                TPO_DATABASE_HOST_SEEN=1
                ;;
            TPO_DATABASE_PORT)
                [ "$TPO_DATABASE_PORT_SEEN" -eq 0 ] || return 1
                TPO_DATABASE_PORT_VALUE=$value
                TPO_DATABASE_PORT_SEEN=1
                ;;
            TPO_DATABASE_NAME)
                [ "$TPO_DATABASE_NAME_SEEN" -eq 0 ] || return 1
                TPO_DATABASE_NAME_VALUE=$value
                TPO_DATABASE_NAME_SEEN=1
                ;;
            TPO_DATABASE_USER)
                [ "$TPO_DATABASE_USER_SEEN" -eq 0 ] || return 1
                TPO_DATABASE_USER_VALUE=$value
                TPO_DATABASE_USER_SEEN=1
                ;;
            TPO_DATABASE_PASSWORD)
                [ "$TPO_DATABASE_PASSWORD_SEEN" -eq 0 ] || return 1
                TPO_DATABASE_PASSWORD_VALUE=$value
                TPO_DATABASE_PASSWORD_SEEN=1
                ;;
            TPO_DATABASE_SSLMODE)
                [ "$TPO_DATABASE_SSLMODE_SEEN" -eq 0 ] || return 1
                TPO_DATABASE_SSLMODE_VALUE=$value
                TPO_DATABASE_SSLMODE_SEEN=1
                ;;
            TPO_DATABASE_CONNECT_TIMEOUT)
                [ "$TPO_DATABASE_CONNECT_TIMEOUT_SEEN" -eq 0 ] || return 1
                TPO_DATABASE_CONNECT_TIMEOUT_VALUE=$value
                TPO_DATABASE_CONNECT_TIMEOUT_SEEN=1
                ;;
            *) return 1 ;;
        esac
    done <"$SECRETS"

    [ "$TPO_DATABASE_HOST_SEEN" -eq 1 ] || return 1
    [ "$TPO_DATABASE_PORT_SEEN" -eq 1 ] || return 1
    [ "$TPO_DATABASE_NAME_SEEN" -eq 1 ] || return 1
    [ "$TPO_DATABASE_USER_SEEN" -eq 1 ] || return 1
    [ "$TPO_DATABASE_PASSWORD_SEEN" -eq 1 ] || return 1
    [ "$TPO_DATABASE_SSLMODE_SEEN" -eq 1 ] || return 1
    [ "$TPO_DATABASE_CONNECT_TIMEOUT_SEEN" -eq 1 ] || return 1

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

if ! load_operational_environment; then
    launcher_failure "OPERATION_INPUT_INVALID: operational secrets format invalid" 2
fi

LOCK_ACQUIRED=0
LOCK_OWNER_FILE="$LOCK_DIR/owner"
LOCK_ACQUISITION_CRITICAL=0
SIGNAL_PENDING=0
STDOUT_FILE=""
STDERR_FILE=""
STDOUT_PIPE=""
STDERR_PIPE=""

cleanup() {
    if [ -n "$STDOUT_FILE" ]; then
        rm -f -- "$STDOUT_FILE"
    fi
    if [ -n "$STDERR_FILE" ]; then
        rm -f -- "$STDERR_FILE"
    fi
    if [ -n "$STDOUT_PIPE" ]; then
        rm -f -- "$STDOUT_PIPE"
    fi
    if [ -n "$STDERR_PIPE" ]; then
        rm -f -- "$STDERR_PIPE"
    fi
    if [ "${LOCK_ACQUIRED:-0}" -eq 1 ]; then
        rm -f -- "$LOCK_OWNER_FILE" 2>/dev/null || true
        rmdir "$LOCK_DIR" 2>/dev/null || true
    fi
}

handle_launcher_signal() {
    if [ "$LOCK_ACQUISITION_CRITICAL" -eq 1 ]; then
        SIGNAL_PENDING=1
        return
    fi
    exit 128
}

trap cleanup EXIT
trap handle_launcher_signal HUP INT TERM

# Signals are deferred only across the atomic mkdir and owner registration.
# Local state, never marker contents, is the authority for cleanup ownership.
LOCK_ACQUISITION_CRITICAL=1
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    LOCK_ACQUISITION_CRITICAL=0
    if [ "$SIGNAL_PENDING" -eq 1 ]; then
        exit 128
    fi
    launcher_failure "OVERLAP_BLOCKED: scheduler lock already present" 1
fi
LOCK_ACQUIRED=1
if ! printf '%s\n' "$$" >"$LOCK_OWNER_FILE"; then
    LOCK_ACQUISITION_CRITICAL=0
    launcher_failure "LOCK_ACQUISITION_FAILED: scheduler ownership registration failed" 1
fi
LOCK_ACQUISITION_CRITICAL=0
if [ "$SIGNAL_PENDING" -eq 1 ]; then
    exit 128
fi

umask 077
STDOUT_FILE="$(mktemp "$RUNTIME_DIR/.operational-scheduler.stdout.XXXXXX")" || exit 1
STDERR_FILE="$(mktemp "$RUNTIME_DIR/.operational-scheduler.stderr.XXXXXX")" || exit 1
STDOUT_PIPE="$RUNTIME_DIR/.operational-scheduler.stdout.pipe.$$"
STDERR_PIPE="$RUNTIME_DIR/.operational-scheduler.stderr.pipe.$$"
mkfifo "$STDOUT_PIPE" "$STDERR_PIPE" || exit 1

sanitize_stream() {
    awk '
    {
        lowered = tolower($0)
        sensitive = lowered ~ /postgres(ql)?(\+[a-z0-9_.-]+)?:\/\//
        sensitive = sensitive || lowered ~ /password[[:space:]]*[:=]/
        sensitive = sensitive || lowered ~ /(^|[[:space:]])(host|hostaddr|port|dbname|user|password|sslmode|connect_timeout)[[:space:]]*=/
        sensitive = sensitive || lowered ~ /tpo_database_password[[:space:]]*=/
        sensitive = sensitive || lowered ~ /tpo_test_database_url[[:space:]]*=/
        sensitive = sensitive || lowered ~ /technical_cause/
        sensitive = sensitive || lowered ~ /traceback/
        sensitive = sensitive || lowered ~ /(^|[^[:alnum:]_])(select|insert|update|delete|with|create|alter|drop|truncate|grant|revoke)([^[:alnum:]_]|$)/
        split("TPO_DATABASE_HOST TPO_DATABASE_PORT TPO_DATABASE_NAME TPO_DATABASE_USER TPO_DATABASE_PASSWORD TPO_DATABASE_SSLMODE TPO_DATABASE_CONNECT_TIMEOUT", keys, " ")
        for (key_index in keys) {
            secret_value = ENVIRON[keys[key_index]]
            if (secret_value != "" && index($0, secret_value) != 0) {
                sensitive = 1
            }
        }
        if (sensitive) {
            print "[REDACTED]"
        } else {
            print $0
        }
    }'
}

sanitize_stream <"$STDOUT_PIPE" >"$STDOUT_FILE" &
STDOUT_SANITIZER_PID=$!
sanitize_stream <"$STDERR_PIPE" >"$STDERR_FILE" &
STDERR_SANITIZER_PID=$!

set +e
"$PYTHON" -m src.tpo_core.cli.main \
    schedule execute \
    --settings "$SETTINGS" \
    --business-date "$BUSINESS_DATE" \
    --business-time "$BUSINESS_TIME" \
    --identity towerpower-scheduler \
    --confirm >"$STDOUT_PIPE" 2>"$STDERR_PIPE"
CLI_EXIT=$?
wait "$STDOUT_SANITIZER_PID"
wait "$STDERR_SANITIZER_PID"
set -e

log_metadata "LAUNCHER_STATUS: CLI_COMPLETED"
printf '%s\n' 'STDOUT:' >>"$LOG_FILE"
cat "$STDOUT_FILE" >>"$LOG_FILE"
printf '%s\n' 'STDERR:' >>"$LOG_FILE"
cat "$STDERR_FILE" >>"$LOG_FILE"
printf '%s\n' "EXIT_CODE: $CLI_EXIT" >>"$LOG_FILE"

exit "$CLI_EXIT"
