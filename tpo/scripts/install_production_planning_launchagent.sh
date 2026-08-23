#!/bin/bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)"
LABEL="com.towerpower.production-planning-scheduler"
LAUNCHER="$ROOT/scripts/run_production_planning_schedule.sh"
HELPER="$ROOT/scripts/production_planning_occurrence.py"
TEMPLATE="$ROOT/deploy/macos/$LABEL.plist"
PYTHON="$ROOT/.venv/bin/python"
SECRETS="$ROOT/runtime/secrets/production-planning-scheduler.env"
INSTALL_DIR="$HOME/Library/LaunchAgents"
INSTALLED_PLIST="$INSTALL_DIR/$LABEL.plist"
DOMAIN="gui/$(id -u)"

diagnostic() { printf '%s: %s\n' "$LABEL" "$1" >&2; }

for executable in "$LAUNCHER" "$HELPER" "$PYTHON"; do
    [ -x "$executable" ] || {
        diagnostic 'required executable unavailable; installation unchanged'
        exit 1
    }
done
[ -f "$TEMPLATE" ] || {
    diagnostic 'LaunchAgent template unavailable; installation unchanged'
    exit 1
}
[ -f "$SECRETS" ] && [ -r "$SECRETS" ] || {
    diagnostic 'Production Planning secrets unavailable; installation unchanged'
    exit 2
}
[ -O "$SECRETS" ] && [ "$(stat -f '%Lp' "$SECRETS" 2>/dev/null)" = "600" ] || {
    diagnostic 'Production Planning secrets ownership or permissions invalid; installation unchanged'
    exit 2
}
case "$ROOT" in
    *'&'*|*'<'*|*'>'*|*'|'*|*'\'*|*$'\n'*)
        diagnostic 'application root contains unsupported plist characters'
        exit 1 ;;
esac

mkdir -p "$ROOT/runtime/logs" "$INSTALL_DIR"

validate_secret_boundary() {
    HOST_SEEN=0 PORT_SEEN=0 NAME_SEEN=0 USER_SEEN=0
    PASSWORD_SEEN=0 SSLMODE_SEEN=0 TIMEOUT_SEEN=0
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue ;; *=*) ;; *) return 1 ;; esac
        key=${line%%=*}; value=${line#*=}
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
validate_secret_boundary || {
    diagnostic 'Production Planning secrets format invalid; installation unchanged'
    exit 2
}

TEMP_PLIST="" BACKUP_PLIST="" RESTORE_TEMP=""
PREVIOUS_EXISTS=0 PREVIOUS_LOADED=0 BACKUP_VALID=0 MUTATED=0

cleanup() {
    [ -z "$TEMP_PLIST" ] || [ ! -e "$TEMP_PLIST" ] || rm -f -- "$TEMP_PLIST" 2>/dev/null || true
    [ -z "$RESTORE_TEMP" ] || [ ! -e "$RESTORE_TEMP" ] || rm -f -- "$RESTORE_TEMP" 2>/dev/null || true
}
trap cleanup EXIT

rollback() {
    if [ "$PREVIOUS_EXISTS" -eq 0 ]; then
        set +e
        launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
        ROLLBACK_PRINT_STATUS=$?
        set -e
        case "$ROLLBACK_PRINT_STATUS" in
            0) launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || return 1 ;;
            113) ;;
            *) return 1 ;;
        esac
        rm -f -- "$INSTALLED_PLIST" 2>/dev/null || return 1
        return 0
    fi
    RESTORE_TEMP="$(mktemp "$INSTALL_DIR/.$LABEL.restore.XXXXXX")" || return 1
    cp -p -- "$BACKUP_PLIST" "$RESTORE_TEMP" 2>/dev/null || return 1
    chmod 600 "$RESTORE_TEMP" 2>/dev/null || return 1
    mv -f -- "$RESTORE_TEMP" "$INSTALLED_PLIST" 2>/dev/null || return 1
    RESTORE_TEMP=""
    if [ "$PREVIOUS_LOADED" -eq 1 ]; then
        launchctl bootstrap "$DOMAIN" "$INSTALLED_PLIST" >/dev/null 2>&1 || return 1
    fi
    rm -f -- "$BACKUP_PLIST" 2>/dev/null || return 1
    BACKUP_VALID=0
}

interrupted() {
    trap - HUP INT TERM
    diagnostic 'installation interrupted'
    if [ "$MUTATED" -eq 1 ]; then
        launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
        rollback || {
            diagnostic 'ROLLBACK FAILED'
            diagnostic 'MANUAL RECOVERY REQUIRED'
        }
    fi
    exit 128
}
trap interrupted HUP INT TERM

TEMP_PLIST="$(mktemp "$INSTALL_DIR/.$LABEL.candidate.XXXXXX")" || {
    diagnostic 'candidate preparation failed; installation unchanged'
    exit 1
}
sed "s|__TPO_ROOT__|$ROOT|g" "$TEMPLATE" >"$TEMP_PLIST" 2>/dev/null || {
    diagnostic 'candidate materialization failed; installation unchanged'
    exit 1
}
plutil -lint "$TEMP_PLIST" >/dev/null 2>&1 || {
    diagnostic 'candidate plist validation failed; installation unchanged'
    exit 1
}
chmod 600 "$TEMP_PLIST" || {
    diagnostic 'candidate permission validation failed; installation unchanged'
    exit 1
}

if [ -e "$INSTALLED_PLIST" ]; then
    PREVIOUS_EXISTS=1
    INSTALLED_LABEL="$(plutil -extract Label raw -o - "$INSTALLED_PLIST" 2>/dev/null)" || {
        diagnostic 'existing LaunchAgent plist is invalid; refusing replacement'
        exit 1
    }
    [ "$INSTALLED_LABEL" = "$LABEL" ] || {
        diagnostic 'existing plist does not belong to Tower Power; refusing replacement'
        exit 1
    }
fi

set +e
launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
PRINT_STATUS=$?
set -e
case "$PRINT_STATUS" in
    0) PREVIOUS_LOADED=1 ;;
    113) PREVIOUS_LOADED=0 ;;
    *) diagnostic 'LaunchAgent state query failed; installation unchanged'; exit 1 ;;
esac
[ "$PREVIOUS_LOADED" -eq 0 ] || [ "$PREVIOUS_EXISTS" -eq 1 ] || {
    diagnostic 'loaded LaunchAgent has no recoverable plist; refusing replacement'
    exit 1
}

if [ "$PREVIOUS_EXISTS" -eq 1 ]; then
    BACKUP_PLIST="$(mktemp "$INSTALL_DIR/.$LABEL.backup.XXXXXX")" || exit 1
    cp -p -- "$INSTALLED_PLIST" "$BACKUP_PLIST" 2>/dev/null || {
        diagnostic 'previous plist preservation failed; installation unchanged'
        exit 1
    }
    chmod 600 "$BACKUP_PLIST" || exit 1
    BACKUP_VALID=1
fi

MUTATED=1
if [ "$PREVIOUS_LOADED" -eq 1 ]; then
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || {
        diagnostic 'bootout failed; previous installation preserved'
        exit 1
    }
fi
mv -f -- "$TEMP_PLIST" "$INSTALLED_PLIST" || {
    diagnostic 'candidate plist replacement failed; attempting rollback'
    rollback || { diagnostic 'ROLLBACK FAILED'; diagnostic 'MANUAL RECOVERY REQUIRED'; }
    exit 1
}
TEMP_PLIST=""

if ! launchctl bootstrap "$DOMAIN" "$INSTALLED_PLIST" >/dev/null 2>&1; then
    diagnostic 'new LaunchAgent bootstrap failed; attempting rollback'
    rollback || { diagnostic 'ROLLBACK FAILED'; diagnostic 'MANUAL RECOVERY REQUIRED'; }
    exit 1
fi

if [ "$BACKUP_VALID" -eq 1 ]; then
    rm -f -- "$BACKUP_PLIST" || {
        launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
        rollback || { diagnostic 'ROLLBACK FAILED'; diagnostic 'MANUAL RECOVERY REQUIRED'; }
        exit 1
    }
fi
MUTATED=0
printf '%s\n' "$LABEL: LaunchAgent installed: $INSTALLED_PLIST"
