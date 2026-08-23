#!/bin/bash

set -eu

LABEL="com.towerpower.production-planning-scheduler"
INSTALLED_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [ ! -e "$INSTALLED_PLIST" ]; then
    printf '%s\n' 'Production Planning LaunchAgent is not installed.'
    exit 0
fi
INSTALLED_LABEL="$(plutil -extract Label raw -o - "$INSTALLED_PLIST" 2>/dev/null)" || {
    printf '%s\n' 'Installed plist is invalid; refusing removal.' >&2
    exit 1
}
[ "$INSTALLED_LABEL" = "$LABEL" ] || {
    printf '%s\n' 'Installed plist does not belong to Tower Power; refusing removal.' >&2
    exit 1
}
if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    launchctl bootout "$DOMAIN/$LABEL"
fi
rm -f -- "$INSTALLED_PLIST"
printf '%s\n' 'Production Planning LaunchAgent removed. Secrets and logs were preserved.'
