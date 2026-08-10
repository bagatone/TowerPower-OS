#!/bin/bash

set -eu

INSTALLED_PLIST="$HOME/Library/LaunchAgents/com.towerpower.operational-scheduler.plist"
LABEL="com.towerpower.operational-scheduler"
DOMAIN="gui/$(id -u)"

if [ ! -e "$INSTALLED_PLIST" ]; then
    printf '%s\n' 'LaunchAgent is not installed.'
    exit 0
fi

INSTALLED_LABEL="$(plutil -extract Label raw -o - "$INSTALLED_PLIST" 2>/dev/null)" || {
    printf '%s\n' 'Installed plist is invalid; refusing removal.' >&2
    exit 1
}
if [ "$INSTALLED_LABEL" != "$LABEL" ]; then
    printf '%s\n' 'Installed plist does not belong to Tower Power; refusing removal.' >&2
    exit 1
fi

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    launchctl bootout "$DOMAIN/$LABEL"
fi
rm -f -- "$INSTALLED_PLIST"
printf '%s\n' 'LaunchAgent removed. Operational settings and logs were preserved.'
