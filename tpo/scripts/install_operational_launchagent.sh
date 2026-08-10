#!/bin/bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)"
LAUNCHER="$ROOT/scripts/run_operational_schedule.sh"
TEMPLATE="$ROOT/deploy/macos/com.towerpower.operational-scheduler.plist"
PYTHON="$ROOT/.venv/bin/python"
SETTINGS="$ROOT/config/settings.yaml"
SECRETS="$ROOT/runtime/secrets/operational-scheduler.env"
INSTALL_DIR="$HOME/Library/LaunchAgents"
INSTALLED_PLIST="$INSTALL_DIR/com.towerpower.operational-scheduler.plist"
LABEL="com.towerpower.operational-scheduler"
DOMAIN="gui/$(id -u)"

diagnostic() {
    printf '%s: %s\n' "$LABEL" "$1" >&2
}

for executable in "$LAUNCHER" "$PYTHON"; do
    if [ ! -x "$executable" ]; then
        diagnostic 'required executable unavailable; installation unchanged'
        exit 1
    fi
done

if [ ! -f "$TEMPLATE" ]; then
    diagnostic 'LaunchAgent template unavailable; installation unchanged'
    exit 1
fi
if [ ! -f "$SETTINGS" ] || [ ! -r "$SETTINGS" ]; then
    diagnostic 'operational settings unavailable; installation unchanged'
    exit 2
fi
if [ ! -f "$SECRETS" ] || [ ! -r "$SECRETS" ]; then
    diagnostic 'operational secrets unavailable; installation unchanged'
    exit 2
fi
if [ ! -O "$SECRETS" ] || [ "$(stat -f '%Lp' "$SECRETS" 2>/dev/null)" != "600" ]; then
    diagnostic 'operational secrets ownership or permissions invalid; installation unchanged'
    exit 2
fi

case "$ROOT" in
    *'&'*|*'<'*|*'>'*|*'|'*|*'\'*|*$'\n'*)
        diagnostic 'application root contains unsupported plist characters'
        exit 1
        ;;
esac

mkdir -p "$ROOT/runtime/logs" "$INSTALL_DIR"

validate_secret_boundary() {
    HOST_SEEN=0 PORT_SEEN=0 NAME_SEEN=0 USER_SEEN=0
    PASSWORD_SEEN=0 SSLMODE_SEEN=0 TIMEOUT_SEEN=0
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|'#'*) continue ;;
            *=*) ;;
            *) return 1 ;;
        esac
        key=${line%%=*}
        value=${line#*=}
        case "$value" in ''|[[:space:]]*) return 1 ;; esac
        case "$key" in
            TPO_DATABASE_HOST) [ "$HOST_SEEN" -eq 0 ] || return 1; HOST_SEEN=1 ;;
            TPO_DATABASE_PORT) [ "$PORT_SEEN" -eq 0 ] || return 1; PORT_SEEN=1 ;;
            TPO_DATABASE_NAME) [ "$NAME_SEEN" -eq 0 ] || return 1; NAME_SEEN=1 ;;
            TPO_DATABASE_USER) [ "$USER_SEEN" -eq 0 ] || return 1; USER_SEEN=1 ;;
            TPO_DATABASE_PASSWORD) [ "$PASSWORD_SEEN" -eq 0 ] || return 1; PASSWORD_SEEN=1 ;;
            TPO_DATABASE_SSLMODE) [ "$SSLMODE_SEEN" -eq 0 ] || return 1; SSLMODE_SEEN=1 ;;
            TPO_DATABASE_CONNECT_TIMEOUT) [ "$TIMEOUT_SEEN" -eq 0 ] || return 1; TIMEOUT_SEEN=1 ;;
            *) return 1 ;;
        esac
    done <"$SECRETS"
    [ "$HOST_SEEN" -eq 1 ] && [ "$PORT_SEEN" -eq 1 ] \
        && [ "$NAME_SEEN" -eq 1 ] && [ "$USER_SEEN" -eq 1 ] \
        && [ "$PASSWORD_SEEN" -eq 1 ] && [ "$SSLMODE_SEEN" -eq 1 ] \
        && [ "$TIMEOUT_SEEN" -eq 1 ]
}

if ! validate_secret_boundary; then
    diagnostic 'operational secrets format invalid; installation unchanged'
    exit 2
fi

TEMP_PLIST=""
BACKUP_PLIST=""
BACKUP_VALID=0
RESTORE_TEMP=""
PREVIOUS_EXISTS=0
PREVIOUS_LOADED=0
PHASE=validation
MUTATION_STAGE=none
COMPENSATION_ATTEMPTED=0

cleanup_installer() {
    if [ -n "$TEMP_PLIST" ] && [ -e "$TEMP_PLIST" ]; then
        rm -f -- "$TEMP_PLIST" 2>/dev/null || true
    fi
    if [ -n "$RESTORE_TEMP" ] && [ -e "$RESTORE_TEMP" ]; then
        rm -f -- "$RESTORE_TEMP" 2>/dev/null || true
    fi
    if [ "$BACKUP_VALID" -eq 0 ] && [ -n "$BACKUP_PLIST" ] && [ -e "$BACKUP_PLIST" ]; then
        rm -f -- "$BACKUP_PLIST" 2>/dev/null || true
    fi
    if [ "$BACKUP_VALID" -eq 1 ] && [ "$PHASE" != mutation ] \
        && [ -n "$BACKUP_PLIST" ] && [ -e "$BACKUP_PLIST" ]; then
        rm -f -- "$BACKUP_PLIST" 2>/dev/null || true
        BACKUP_VALID=0
        BACKUP_PLIST=""
    fi
}
trap cleanup_installer EXIT

rollback_reinstall() {
    [ "$COMPENSATION_ATTEMPTED" -eq 0 ] || return 1
    COMPENSATION_ATTEMPTED=1
    RESTORE_TEMP="$(mktemp "$INSTALL_DIR/.com.towerpower.operational-scheduler.restore.XXXXXX")" || return 1
    cp -p -- "$BACKUP_PLIST" "$RESTORE_TEMP" 2>/dev/null || return 1
    chmod 600 "$RESTORE_TEMP" 2>/dev/null || return 1
    mv -f -- "$RESTORE_TEMP" "$INSTALLED_PLIST" 2>/dev/null || return 1
    RESTORE_TEMP=""
    if [ "$PREVIOUS_LOADED" -eq 1 ]; then
        launchctl bootstrap "$DOMAIN" "$INSTALLED_PLIST" >/dev/null 2>&1 || return 1
    fi
    rm -f -- "$BACKUP_PLIST" 2>/dev/null || return 1
    BACKUP_VALID=0
    BACKUP_PLIST=""
    diagnostic 'ROLLBACK SUCCESSFUL'
    return 0
}

rollback_failed() {
    diagnostic 'ROLLBACK FAILED'
    diagnostic 'MANUAL RECOVERY REQUIRED'
    exit 1
}

compensate_first_install() {
    [ "$COMPENSATION_ATTEMPTED" -eq 0 ] || return 1
    COMPENSATION_ATTEMPTED=1
    rm -f -- "$INSTALLED_PLIST" 2>/dev/null
}

compensate_first_install_signal() {
    [ "$COMPENSATION_ATTEMPTED" -eq 0 ] || return 1
    COMPENSATION_ATTEMPTED=1
    if [ "$MUTATION_STAGE" = bootstrap_pending ] \
        || [ "$MUTATION_STAGE" = new_bootstrapped ]; then
        set +e
        launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
        SIGNAL_PRINT_STATUS=$?
        set -e
        case "$SIGNAL_PRINT_STATUS" in
            0) launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || return 1 ;;
            113) ;;
            *) return 1 ;;
        esac
    fi
    rm -f -- "$INSTALLED_PLIST" 2>/dev/null
}

handle_signal() {
    trap - HUP INT TERM
    diagnostic 'installation interrupted'
    if [ "$PHASE" = mutation ]; then
        if [ "$PREVIOUS_EXISTS" -eq 1 ]; then
            if [ "$MUTATION_STAGE" = bootstrap_pending ] \
                || [ "$MUTATION_STAGE" = new_bootstrapped ]; then
                launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
            fi
            if ! rollback_reinstall; then
                rollback_failed
            fi
        elif [ -e "$INSTALLED_PLIST" ]; then
            if ! compensate_first_install_signal; then
                diagnostic 'CLEANUP FAILED'
                diagnostic 'MANUAL RECOVERY REQUIRED'
            fi
        fi
    fi
    exit 128
}
trap handle_signal HUP INT TERM

if ! TEMP_PLIST="$(mktemp "$INSTALL_DIR/.com.towerpower.operational-scheduler.candidate.XXXXXX")"; then
    diagnostic 'candidate preparation failed; installation unchanged'
    exit 1
fi
if ! sed "s|__TPO_ROOT__|$ROOT|g" "$TEMPLATE" >"$TEMP_PLIST" 2>/dev/null; then
    diagnostic 'candidate materialization failed; installation unchanged'
    exit 1
fi
if ! plutil -lint "$TEMP_PLIST" >/dev/null 2>&1; then
    diagnostic 'candidate plist validation failed; installation unchanged'
    exit 1
fi
if ! chmod 600 "$TEMP_PLIST" 2>/dev/null; then
    diagnostic 'candidate permission validation failed; installation unchanged'
    exit 1
fi

if [ -e "$INSTALLED_PLIST" ]; then
    PREVIOUS_EXISTS=1
    if ! INSTALLED_LABEL="$(plutil -extract Label raw -o - "$INSTALLED_PLIST" 2>/dev/null)"; then
        diagnostic 'existing LaunchAgent plist is invalid; refusing replacement'
        exit 1
    fi
    if [ "$INSTALLED_LABEL" != "$LABEL" ]; then
        diagnostic 'existing plist does not belong to Tower Power; refusing replacement'
        exit 1
    fi
fi

set +e
launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
PRINT_STATUS=$?
set -e
case "$PRINT_STATUS" in
    0) PREVIOUS_LOADED=1 ;;
    113) PREVIOUS_LOADED=0 ;;
    *)
        diagnostic 'LaunchAgent state query failed; installation unchanged'
        exit 1
        ;;
esac

if [ "$PREVIOUS_LOADED" -eq 1 ] && [ "$PREVIOUS_EXISTS" -eq 0 ]; then
    diagnostic 'loaded LaunchAgent has no recoverable plist; refusing replacement'
    exit 1
fi

if [ "$PREVIOUS_EXISTS" -eq 1 ]; then
    if ! BACKUP_PLIST="$(mktemp "$INSTALL_DIR/.com.towerpower.operational-scheduler.backup.XXXXXX")"; then
        diagnostic 'previous plist preservation failed; installation unchanged'
        exit 1
    fi
    if ! cp -p -- "$INSTALLED_PLIST" "$BACKUP_PLIST" 2>/dev/null; then
        diagnostic 'previous plist preservation failed; installation unchanged'
        exit 1
    fi
    BACKUP_VALID=1
    PHASE=pre_mutation
    if ! chmod 600 "$BACKUP_PLIST" 2>/dev/null; then
        diagnostic 'previous plist preservation failed; installation unchanged'
        exit 1
    fi
fi

PHASE=mutation
if [ "$PREVIOUS_LOADED" -eq 1 ]; then
    MUTATION_STAGE=bootout_pending
    if ! launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1; then
        PHASE=complete
        diagnostic 'bootout failed; previous installation preserved'
        exit 1
    fi
fi

MUTATION_STAGE=replacement_pending
if ! mv -f -- "$TEMP_PLIST" "$INSTALLED_PLIST" 2>/dev/null; then
    diagnostic 'candidate plist replacement failed; attempting rollback'
    if [ "$PREVIOUS_EXISTS" -eq 0 ]; then
        exit 1
    fi
    rollback_reinstall || rollback_failed
    exit 1
fi
TEMP_PLIST=""

MUTATION_STAGE=bootstrap_pending
if ! launchctl bootstrap "$DOMAIN" "$INSTALLED_PLIST" >/dev/null 2>&1; then
    if [ "$PREVIOUS_EXISTS" -eq 0 ]; then
        diagnostic 'first install bootstrap failed; attempting cleanup'
        if ! compensate_first_install; then
            diagnostic 'CLEANUP FAILED'
            diagnostic 'MANUAL RECOVERY REQUIRED'
            exit 1
        fi
        diagnostic 'first install failed; state is Not Installed'
        exit 1
    fi
    diagnostic 'new LaunchAgent bootstrap failed; attempting rollback'
    rollback_reinstall || rollback_failed
    exit 1
fi
MUTATION_STAGE=new_bootstrapped

if [ "$BACKUP_VALID" -eq 1 ]; then
    if ! rm -f -- "$BACKUP_PLIST" 2>/dev/null; then
        diagnostic 'backup cleanup failed; attempting rollback'
        launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || rollback_failed
        rollback_reinstall || rollback_failed
        exit 1
    fi
    BACKUP_VALID=0
    BACKUP_PLIST=""
fi
PHASE=complete
printf '%s\n' "$LABEL: LaunchAgent installed: $INSTALLED_PLIST"
